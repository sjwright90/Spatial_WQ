# CLAUDE.md

Plotly Dash app for exploring water-quality lab data spatially: upload CSV → map its
columns to semantic roles (location ID, lat/lon, analytes, date, plotting groups, etc.)
via an in-app modal → run PCA/PaCMAP dimensionality reduction on selected
analytes/locations → linked map + biplot views. Optional Redis session persistence.
Deployed via Docker Compose behind nginx.

See [docs/agent-context/GOTCHAS.md](docs/agent-context/GOTCHAS.md) for known-broken
areas before touching Redis, caching, docker-compose, or the column-mapping/validation
logic. Full architecture detail:
[docs/agent-context/codebase-map.md](docs/agent-context/codebase-map.md).

## Architecture

One flat Flask+Dash app, no blueprints/router:

- `app/app.py` — `server = Flask(...)`, `app = dash.Dash(..., server=server)`, and
  **every** `@app.callback` (~1270 lines total). This is the file to read/edit for any
  interactivity change. Upload is a two-step flow: `stage_raw_upload` (opens the
  column-mapping modal) → `confirm_mapping` (builds a `ColumnMapping`, runs
  `DataPreprocessor`, populates the session stores).
- `app/pages/home.py` — layout only (`create_page_map()` builds the `dcc.Store`-based
  layout: `meta-data`, `session`, `working-data`, `side_click`, `map-relayout-store`,
  `raw-upload-store`). Also builds `mapping_modal`, generated programmatically from
  `data_model.ROLE_REGISTRY` (one dropdown per column role, via Dash pattern-matching
  ids) rather than one hand-authored component per role.
- `app/src/data_model.py` — declarative schema for column mapping: `ColumnRole` enum,
  `RoleSpec`, `ROLE_REGISTRY` (source of truth the mapping UI iterates over),
  `ColumnMapping` dataclass (the user's completed mapping).
- `app/src/data_mapping.py` — `build_mapped_dataset(df_raw, mapping)`: validates +
  coerces a raw upload against a `ColumnMapping`, returns `ValidationIssue`/
  `ValidationResult` (structured field/severity/message, not just booleans) plus the
  canonical `df_master`/`cols_key_plot`/`cols_key_meta`.
- `app/src/data_manager.py` — `DataPreprocessor` (CSV ingest, now mapping-driven —
  takes `(content_string, mapping)`), `DataPlotter` (render prep), `SessionManager`
  (packing for stores). `DataPreprocessor.get_session_dict()`'s output shape is
  unchanged from before the mapping refactor, so downstream callbacks/`DataPlotter`
  needed minimal edits.
- `app/src/data_process.py` — column-reshaping/color-dict/coordinate-extraction
  helpers, `pandas_to_json`/`json_to_pandas` (de)serialization. The old regex column
  classifiers (`get_key_cols_*`, `rename_cols_*`) are gone — see below. `make_color_dict`
  always assigns `DEFAULT_UNASSIGNED_CATEGORY` (`"Unassigned"`) the fixed
  `LIGHT_GREY_COLOR` (`#D3D3D3`) rather than letting it fall wherever it lands in the
  alphabetically-sorted palette-zip — it's excluded from that zip entirely so it doesn't
  also consume a palette slot from the other categories.
- `app/src/compositional_data_functions.py` — CLR transform + scaling.
- `app/src/dimension_reduction_functions.py` — PCA/PaCMAP pipeline
  (`process_dimension_reduction`). `run_pca` computes up to `MAX_PCA_COMPONENTS` (5,
  capped by available analytes/samples), not just PC1/PC2, so the biplot can plot any
  computed component pair.
- `app/src/clustering_functions.py` — KMeans "auto-cluster" pipeline
  (`process_clustering`), feeding the custom-group workflow. Mirrors
  `process_dimension_reduction`'s subset/CLR-transform steps on the same
  analytes/locations last applied to the PCA/PaCMAP plots
  (`plotting_data.feature_selection_dropdown_value`/`loc_id_dropdown_value`),
  then clusters on a chosen `feature_space`: `"clr"` (the CLR-transformed
  analyte matrix) or `"pca"` (unscaled PCA scores over all computed
  components, via `build_pca_feature_matrix` — deliberately NOT the min-max
  `pc_scaler`-scaled scores `make_df_for_biplot` produces for the biplot,
  since that scaling would distort each component's variance-proportional
  range before clustering on it).
- `app/src/plotting.py` — all Plotly figure builders (`make_map`, `make_fig_pca`,
  `make_fig_pmap`). Mostly untouched by the mapping refactor — see "Explicit column
  mapping" below for why — but `make_fig_pca` does take an arbitrary `x_col`/`y_col`
  component pair (not hardcoded PC1/PC2) to support the selectable-PC biplot.
  `make_base_scatter_plot` (shared by `make_fig_pca`/`make_fig_pmap`) wraps long
  split-category legend labels (`"{loc_code} [{date_min}->{date_max}]"`) via
  `_wrap_legend_label`, which exploits that fixed 2-token shape rather than doing
  generic word-wrap: break at the loc_code/bracket space first, fall back to the `->`
  (kept intact) only if the bracketed date range alone still doesn't fit, and never
  fractures a `loc_code` or a single date token — an over-length line is preferred over
  a mid-token break.
- `app/src/session_manager.py` — Redis read/write helpers. Wired up and working from
  `app/app.py` (fixed during the hardening pass — see GOTCHAS for history).
- `app/src/cache_initialize.py` — Flask-Caching key/hash helpers. `generate_df_hash_version`
  is actively used by `DataPreprocessor`; only `make_custom_cache_key_dimensionReduction`
  (the actual caching wiring) is unused — see GOTCHAS.
- `app/src/logging_config.py` — `get_logger(__name__)`/`configure_logging()`, the app's
  `logging` setup (see Conventions below).
- `app/src/error_handling.py` — `log_and_prevent_update`/`log_and_surface_error`
  decorators used on `app.py` callbacks for consistent error logging.
- `app/src/store_utils.py` — `load_store`/`dump_store`, thin json.loads/dumps wrappers
  for dcc.Store string payloads.

**State model**: no server-side session — all cross-callback state round-trips through
`dcc.Store` as JSON strings via `pandas_to_json`/`json_to_pandas`. Every callback that
touches data does a full `json.loads`/`json.dumps` on the session blob.

**Explicit column mapping (not an implicit naming convention)**: uploaded CSVs can use
any column names. The user maps columns to roles (`ColumnRole` in `data_model.py`) via
a modal; `data_mapping.build_mapped_dataset()` validates and applies that mapping. There
is **no schema doc or sample CSV** and none is needed — `data_model.ROLE_REGISTRY` is
the authoritative list of roles, and it's what the mapping UI is generated from. The
only two literal column names still hardcoded anywhere are `LATITUDE`/`LONGITUDE`,
because `plotting.make_map` reads those names directly with no override kwarg —
`build_mapped_dataset` renames the user's mapped lat/lon columns to match rather than
touching `plotting.py`. (This replaces the old implicit prefix convention —
`NUMERIC-ANALYTE_`, `CLR-ANALYTE_`, `LOCATION-ID_`, `DATETIME`, `LABELS_*`, `COLORS_*`,
`MARKERS-PLOT-DOMAIN`, `MAP-MARKER-SIZE` — which no longer exists in the codebase at
all, deleted with no backward-compat path.)

## Build / Test / Run

```bash
# Tests (pytest, unittest-style classes) - repo root must be on PYTHONPATH,
# there's no app/__init__.py or pytest.ini setting it for you
PYTHONPATH=. pytest test/

# Docker build (from repo root — only ./app is copied into the image)
docker build -t <tag> .

# Local dev without Docker (Dash dev server, port 8050, debug=True)
python app/app.py

# Local desktop launch (Waitress + auto-open browser, port 8080)
python server.py   # NOT included in the Docker image (.dockerignore) — dev/desktop only
```

No CI config in the repo — tests run locally/manually only.

- **Agents: never run `python app/app.py` (or `server.py`) yourselves, including in the
  background for smoke-testing a change.** The user runs the app/smoke tests themselves.
  A backgrounded dev server that's forgotten about survives past the session that
  started it (`debug=False` — no hot reload) and silently keeps serving stale code on
  port 8050; a later `python app/app.py` from the user (or another agent) can bind to a
  *different* port or the user's browser can simply still be pointed at the old
  process, making a already-fixed bug look unfixed. This exact failure mode burned a
  full debugging cycle once already — see
  [docs/agent-context/CUSTOM-CATEGORY-COLOR-BUGS-HANDOFF.md](docs/agent-context/CUSTOM-CATEGORY-COLOR-BUGS-HANDOFF.md).
  Verify changes via `PYTHONPATH=. pytest test/`, direct callback invocation, or reading
  the layout/diff — not by launching the server.
  - If a headless smoke test of the running app is genuinely needed (and the user has
    asked for one), never bind port 8050 — that's the user's own dev-server port and a
    stray background process there causes exactly the stale-code confusion described
    above. Use an ephemeral port (`port=0`, or a fixed high port like `8055` that isn't
    8050/8080) and wrap the server start/`app.run`/thread or process lifetime in a
    `try...finally` so it's guaranteed to shut down even if the smoke test assertion
    fails — don't leave it running in the background for a later call to check.

- Dependencies live in `app/pyproject.toml` (PEP 621 `[project.dependencies]`), not a
  `requirements.txt` — the old file was UTF-16LE encoded and has been removed. It's
  intentionally not an installable package (flat `app.py`/`pages`/`src` layout, no
  `__init__.py`); `[tool.setuptools] packages = []` just gives `pip install .` a
  dependency list to resolve. The Dockerfile `COPY`s only `pyproject.toml` first (for
  layer caching) before `pip install .`, then copies the rest of `./app`.
- `docker-compose.yml` is mid-refactor and will not stand up the `app` service as
  committed (no `build:`/`image:` directive; nginx/certbot volume mounts commented out).
  Don't assume `docker compose up` works — see GOTCHAS.

## Conventions

- **Use `logging`, never `print()`, for status/debug/error output.** Call
  `get_logger(__name__)` from `app/src/logging_config.py` at module scope, then
  `logger.info(...)`/`logger.warning(...)`/`logger.exception(...)` as appropriate. Each
  process entrypoint (`app/app.py`, `server.py`) calls `configure_logging()` once at
  import time — don't call it from library modules. This supersedes an earlier
  print()-only convention (replaced during the hardening pass that also fixed Redis and
  added type hints/docstrings across `app.py`/`data_manager.py`/`plotting.py`); if you
  find a stray `print()` in older code, it's a leftover, not the standard to follow.
- `app.py` callbacks use the `log_and_prevent_update`/`log_and_surface_error` decorators
  (`app/src/error_handling.py`) for consistent exception logging instead of hand-rolled
  try/except — reach for those instead of writing a new bespoke try/except block. Load
  dcc.Store JSON payloads via `store_utils.load_store` rather than a bare `json.loads(...)`.
- Docstrings (numpy-style, at least a one-liner) are now present across all of
  `app/src/` and `app/app.py`'s callbacks, not just the four files that originally had
  them (`data_process.py`, `data_mapping.py`, `dimension_reduction_functions.py`,
  `compositional_data_functions.py`). Match the target file's existing density when
  adding new functions.
- Type hints on function signatures are now the norm throughout `app/src/` and
  `app/app.py`'s callbacks — add them to new functions rather than leaving them untyped.
- Adding/removing a column-mapping role? Edit `data_model.ROLE_REGISTRY` (and the
  corresponding checks in `data_mapping.build_mapped_dataset`) — the mapping UI in
  `home.py` is generated from the registry, not hand-authored per role.

## Before making a change here

- Editing callbacks? They're all in `app/app.py`. Error handling is now consistent —
  wrap with `log_and_prevent_update`/`log_and_surface_error`
  (`app/src/error_handling.py`) rather than a bespoke try/except; see an existing
  callback for the pattern.
- Touching Redis save/load/list UI? The app-level wiring is fixed and working (see
  GOTCHAS for history) — `save_to_redis`/`load_from_redis`/`list_keys` are imported and
  called normally in `app/app.py`. `docker-compose.yml`'s Redis *service* wiring is
  still separately broken (see GOTCHAS/below) — don't assume `docker compose up` gives
  you a working Redis to test against.
- Touching PCA/PaCMAP performance? Flask-Caching is scaffolded but not wired up (see
  GOTCHAS) — don't assume caching exists.
- Touching column mapping/validation? Read
  [docs/agent-context/codebase-map.md](docs/agent-context/codebase-map.md)'s CSV-upload
  workflow section first for the design decisions already made (required vs. optional
  roles, what blocks vs. warns, why lat/lon get renamed) before changing
  `data_model.py`/`data_mapping.py`.
- Touching date handling? Per-row coercion + graceful degradation now lives in
  `data_mapping._coerce_date` — the old whole-column `datetime.now()` corruption
  fallback is gone (see GOTCHAS for the pre-refactor history if you need context).
- Touching `plotting.py`? It's deliberately untouched by the column-mapping refactor —
  confirm with the user before changing its hardcoded `LATITUDE`/`LONGITUDE`/
  `MAP-MARKER-SIZE`/`PMAP1`/`PMAP2`/`metals` expectations, since the mapping layer was
  specifically designed to satisfy them without edits here. `PC1`/`PC2` are no longer
  hardcoded there - `make_fig_pca`/`DataPlotter.plot_pca` take an explicit `x_col`/`y_col`
  component pair (selectable-PC biplot feature) - so this exception doesn't apply to PCA
  axis selection.

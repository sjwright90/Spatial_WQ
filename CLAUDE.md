# CLAUDE.md

Plotly Dash app for exploring water-quality lab data spatially: upload CSV → map its
columns to semantic roles (location ID, lat/lon, analytes, date, plotting groups, etc.)
via an in-app modal → run PCA/PaCMAP dimensionality reduction on selected
analytes/locations → linked map + biplot views. Optional Redis session persistence.
Deployed via Docker Compose behind nginx.

See [docs/agent-context/GOTCHAS.md](docs/agent-context/GOTCHAS.md) for known-broken
areas before touching Redis, caching, docker-compose, or the column-mapping/validation
logic. Full architecture detail:
[docs/agent-context/codebase-map.md](docs/agent-context/codebase-map.md). Technical
record of the CSV-ingestion refactor (why it changed, what decisions were made):
[docs/agent-context/REFACTOR-HANDOFF.md](docs/agent-context/REFACTOR-HANDOFF.md).

## Architecture

One flat Flask+Dash app, no blueprints/router:

- `app/app.py` — `server = Flask(...)`, `app = dash.Dash(..., server=server)`, and
  **every** `@app.callback` (lines ~48-607). This is the file to read/edit for any
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
  classifiers (`get_key_cols_*`, `rename_cols_*`) are gone — see below.
- `app/src/compositional_data_functions.py` — CLR transform + scaling.
- `app/src/dimension_reduction_functions.py` — PCA/PaCMAP pipeline
  (`process_dimension_reduction`).
- `app/src/plotting.py` — all Plotly figure builders (`make_map`, `make_fig_pca`,
  `make_fig_pmap`). Untouched by the mapping refactor — see "Explicit column mapping"
  below for why.
- `app/src/session_manager.py` — Redis read/write helpers (currently unreachable, see
  GOTCHAS).
- `app/src/cache_initialize.py` — Flask-Caching key/hash helpers (currently unused, see
  GOTCHAS).

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

- `app/requirements.txt` is **UTF-16LE encoded**. If `pip install -r requirements.txt`
  misbehaves, check encoding before debugging anything else.
- `docker-compose.yml` is mid-refactor and will not stand up the `app` service as
  committed (no `build:`/`image:` directive; nginx/certbot volume mounts commented out).
  Don't assume `docker compose up` works — see GOTCHAS.

## Conventions

- Use `print()` for status/debug — the codebase does not use `logging`, be consistent
  with existing files rather than introducing it ad hoc mid-file.
- Commented-out dead code is generally left in place elsewhere (e.g. `app/src/data_manager.py`'s
  legacy `SessionManager.package_session_data`) rather than deleted — but the old
  regex-based column-classification code was fully **deleted**, not commented out, when
  the mapping refactor replaced it (explicit no-backward-compat decision). Don't treat
  "leave dead code in place" as covering removals like that one.
- Docstrings (numpy-style) are present in `data_process.py`, `data_mapping.py`,
  `dimension_reduction_functions.py`, `compositional_data_functions.py`; largely absent
  in `app.py`/`data_manager.py`. Match the target file's existing density.
- Adding/removing a column-mapping role? Edit `data_model.ROLE_REGISTRY` (and the
  corresponding checks in `data_mapping.build_mapped_dataset`) — the mapping UI in
  `home.py` is generated from the registry, not hand-authored per role.

## Before making a change here

- Editing callbacks? They're all in `app/app.py` — check for an existing similar
  callback's error-handling style (inconsistent across the file: some wrap in
  `try/except: print(...)`, some have none) rather than assuming one pattern.
- Touching Redis save/load/list UI? It's currently broken (see GOTCHAS) — confirm with
  the user whether you're expected to fix the import or whether that's out of scope.
- Touching PCA/PaCMAP performance? Flask-Caching is scaffolded but not wired up (see
  GOTCHAS) — don't assume caching exists.
- Touching column mapping/validation? Read
  [docs/agent-context/REFACTOR-HANDOFF.md](docs/agent-context/REFACTOR-HANDOFF.md)
  first for the design decisions already made (required vs. optional roles, what blocks
  vs. warns, why lat/lon get renamed) before changing `data_model.py`/`data_mapping.py`.
- Touching date handling? Per-row coercion + graceful degradation now lives in
  `data_mapping._coerce_date` — the old whole-column `datetime.now()` corruption
  fallback is gone (see GOTCHAS for the pre-refactor history if you need context).
- Touching `plotting.py`? It's deliberately untouched by the column-mapping refactor —
  confirm with the user before changing its hardcoded `LATITUDE`/`LONGITUDE`/
  `MAP-MARKER-SIZE`/`PC1`/`PC2`/`PMAP1`/`PMAP2`/`metals` expectations, since the mapping
  layer was specifically designed to satisfy them without edits here.

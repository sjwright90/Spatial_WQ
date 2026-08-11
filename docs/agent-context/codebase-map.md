# Codebase Map: 00_SPATIAL_WQ (Spatial_WQ)

## Orientation
A single-page Plotly Dash web app for exploring water-quality lab data spatially. Users upload a CSV, map its columns to semantic roles (location ID, latitude/longitude, analytes, date, plotting groups, etc.) via an in-app modal, and the app maps sample locations, runs PCA and PaCMAP dimensionality reduction on selected analytes/locations, and renders linked map + biplot views. Sessions (uploaded/derived data) can optionally be persisted to Redis, keyed by a user-entered "session ID" and a named key, with a 1-week TTL. Deployment target is Docker Compose behind nginx with Let's Encrypt/certbot, run via gunicorn; there's also a Waitress-based desktop-launch entry point (`server.py`). Repo root README (`README.md`) is just a UTF-16 title stub ("# Spatial_WQ") — no real docs exist there.

**As of the `refactor/declarative-data-model` branch**, CSV ingestion is driven by an explicit, user-supplied column-to-role mapping rather than regex-matched column-name prefixes — see [Workflow 1](#1-csv-upload---column-mapping---validation---session-bootstrap) and `docs/agent-context/REFACTOR-HANDOFF.md` for the full rationale/design record.

## Entry Points & Execution Flow
Two independent ways to run the same Dash `server`/`app` object defined in `app/app.py`:

1. **Docker/production**: `Dockerfile` → `CMD ["gunicorn", "--workers=3", "-b", "0.0.0.0:8080", "app:server"]`, run from `WORKDIR /app` (only `./app` dir is copied into the image, `COPY ./app /app`). Gunicorn imports `app.py`'s `server` (the raw Flask app wrapping the Dash app). The `if __name__ == "__main__"` block at the bottom of `app/app.py` (lines 611-614) is dead in this path since gunicorn imports the module rather than executing it as `__main__`.
2. **Local/desktop**: `server.py` (repo root, **not** copied into the Docker image per `.dockerignore` line 7) does `from app import server` then launches a browser via `webbrowser.open_new` and serves with `waitress.serve(server)` on port 8080. This assumes `app/` is on `sys.path` or is run from a location where `app` resolves as a package — not verified how this is actually invoked (no wrapper script present).
3. `app/app.py:612-614` also supports `python app.py` directly for Dash's built-in dev server on port 8050 (`app.run(debug=True, port=port)`), gated behind `__name__ == "__main__"` and explicitly commented "TURN OFF FOR DEPLOYMENT WITH GUNICORN" (`app/app.py:610`).

All three entry points converge on the same Dash app/layout built in `app/app.py`:
- `server = Flask(__name__)`, `app = dash.Dash(__name__, server=server, ...)` (`app/app.py:42-43`)
- `app.layout = create_page_map()` from `app/pages/home.py:355-376`, which assembles a `dcc.Store`-based state model (`meta-data`, `session`, `working-data`, `side_click`, `map-relayout-store`, `raw-upload-store`) plus navbar/sidebar/map/plot divs and the column-mapping modal (`mapping_modal`, `app/pages/home.py`).
- All interactivity is via `@app.callback` functions registered directly in `app/app.py` (lines 48-607) — no blueprint/router split, it's one flat callback module.

## Module/Directory Map
```
00_SPATIAL_WQ/
├── server.py                 # Waitress/browser launcher (excluded from Docker image)
├── Dockerfile                # gunicorn image build
├── docker-compose.yml        # app + redis + nginx + certbot services
├── nginx/
│   ├── nginx.conf            # base http block, includes conf.d/*.conf
│   └── conf.d/app.conf       # HTTP->HTTPS redirect + reverse-proxy to app, template SERVER_NAME/BACKEND_NAME placeholders
├── app/
│   ├── app.py                 # Flask+Dash server object, ALL callbacks (upload stage/confirm, redis save/load, map, dropdowns, dimension reduction, plots)
│   ├── requirements.txt       # UTF-16LE encoded (see Fragile section)
│   ├── pages/
│   │   ├── home.py             # layout components, mapping modal (generated from ROLE_REGISTRY), create_page_map()
│   │   └── www/style/style.py  # dict-based inline CSS style constants
│   └── src/
│       ├── data_model.py                 # NEW: ColumnRole enum, RoleSpec, ROLE_REGISTRY, ColumnMapping dataclass - declarative schema for the column-mapping UI
│       ├── data_mapping.py               # NEW: build_mapped_dataset() - validates a raw upload against a ColumnMapping, returns ValidationIssue/ValidationResult + canonical df/cols_key_plot/cols_key_meta
│       ├── data_manager.py               # DataPreprocessor (CSV ingest, now mapping-driven), DataPlotter (render prep), SessionManager (packing)
│       ├── data_process.py               # column-reshaping/color-dict/coordinate-extraction helpers, JSON<->pandas (de)serialization (regex column classifiers removed - see below)
│       ├── compositional_data_functions.py # CLR (centered log-ratio) transform + StandardScaler for compositional geochem data
│       ├── dimension_reduction_functions.py # PCA + PaCMAP pipeline (process_dimension_reduction, run_pca, run_pmap)
│       ├── plotting.py                   # Plotly figure builders: make_map (mapbox), make_fig_pca, make_fig_pmap, empty_fig
│       ├── cache_initialize.py           # Flask-Caching cache-key builder + dataframe content hashing (md5 of hash_pandas_object)
│       ├── session_manager.py            # Redis read/write helpers (save_to_redis/load_from_redis/list_keys/...)
│       └── callbacks.py                  # callback_prevent_initial_output decorator (wraps dash callback_context)
└── test/
    └── src/
        ├── test_data_model.py            # NEW
        ├── test_data_mapping.py          # NEW
        ├── test_data_manager.py
        ├── test_data_process.py
        ├── test_compositional_data_functions.py
        ├── test_plotting.py
        └── test_cache_initialize.py
```
A hardening pass (post-dating the numbers above) added `test_session_manager.py`,
`test_error_handling.py`, `test_dimension_reduction_functions.py`, and a minimal
`test_app_callbacks.py` import-level smoke test for `app/app.py`. Still no
per-callback behavioral test coverage for `app/app.py`, and still none for
`app/src/callbacks.py` or `app/pages/*` — see GOTCHAS.md's "Test coverage gaps" for
the current state.

**Note**: the hardening pass also added `app/src/logging_config.py`,
`app/src/error_handling.py`, and `app/src/store_utils.py`, and touched most files
listed below (type hints, docstrings, `logging` instead of `print()`, the Redis
import fix). Line-number citations throughout this document predate that pass and
may be off by a few lines in touched files — treat them as approximate pointers, not
exact addresses.

## Key Workflows (traced end-to-end)

### 1. CSV upload -> column mapping -> validation -> session bootstrap
Ingestion is now a **two-step, mapping-driven** flow (replaces the old single-shot regex-classification upload):

- **Stage**: user uploads a file via `dcc.Upload(id="upload-data", ...)` (`app/pages/home.py:174-184`). `stage_raw_upload()` (`app/app.py:92-108`) base64-decodes the payload, reads just the CSV header (`pd.read_csv(..., nrows=0)`), stores `{content_string, columns}` JSON in the `raw-upload-store` `dcc.Store`, opens the mapping modal (`mapping-modal`, `is_open=True`), and populates every role dropdown's `options` with the raw column list.
- **Map**: the modal (`app/pages/home.py`, built by `_role_mapping_row()` at line 188, iterating `data_model.ROLE_REGISTRY`) shows one dropdown per `ColumnRole` (location ID, latitude, longitude, numeric analytes (simple/CLR), date, plotting group(s), marker symbol, map marker size), using Dash pattern-matching ids `{"type": "role-mapping", "role": <role.value>}`. A separate callback, `update_group_color_dropdowns()` (`app/app.py:120-140`), dynamically renders one optional "predefined color column" dropdown per selected plotting-group column (`{"type": "group-color-mapping", "group": <group_col>}`).
- **Confirm**: `confirm_mapping()` (`app/app.py:167-238`) reconstructs a `ColumnMapping` (`app/src/data_model.py:158`) from the modal's pattern-matching `State`s, then constructs `DataPreprocessor(content_string, mapping)` (`app/src/data_manager.py:25-131`):
  - Reads CSV into `df_raw` via `pd.read_csv(io.BytesIO(decoded), float_precision="high")`.
  - Hashes the frame with `generate_df_hash_version` (`app/src/cache_initialize.py:17-33`, sorts rows/cols then md5 of `hash_pandas_object`).
  - Delegates to `build_mapped_dataset(df_raw, mapping)` (`app/src/data_mapping.py:270-355`), which validates the mapping (duplicate/missing/required-role checks) and coerces each mapped column per its role (lat/lon range, numeric, CLR positivity, date, hex color), collecting `ValidationIssue(field, severity, message, offending_values)` into a `ValidationResult` (`app/src/data_mapping.py:31-68`) instead of the old whole-column silent-corruption/aggregate-boolean approach. On success it also renames the mapped lat/lon columns to literal `LATITUDE`/`LONGITUDE` (required by `plotting.make_map`, which hardcodes those names) and returns the canonical `cols_key_plot`/`cols_key_meta` dicts — same shape as before this refactor.
  - If `validation.has_errors`, `DataPreprocessor` leaves `df_master`/`cols_key_plot`/etc. as `None`; `confirm_mapping()` renders the issues as a list inside the modal and keeps it open.
  - On success, builds coordinate table (`extract_coordinate_dataframe`, now takes an optional `col_marker_size` and synthesizes a constant `MAP-MARKER-SIZE` column when unmapped), marker-symbol dict (defaults every location to `"circle"` when no marker role is mapped, since `plotting.py` indexes this dict directly with no `.get()` fallback), and per-plot-group color dict (`make_plotting_group_color_dicts`, driven by `mapping.group_colors` instead of a regex/format flag).
- `DataPreprocessor.get_session_dict()` (`app/src/data_manager.py`) packages everything into the shape stored in the `session` `dcc.Store`, including default dropdown values for downstream callbacks — **this output shape is unchanged from before the refactor**, which is why `app.py`'s dropdown/map/plot callbacks and `DataPlotter` needed minimal edits.
- Required roles that block upload with an error: location ID, latitude, longitude, ≥1 numeric analyte (simple or CLR), ≥1 plotting group. Optional roles (date, marker symbol, marker size, group colors) degrade gracefully with a warning instead of blocking — see `docs/agent-context/REFACTOR-HANDOFF.md` for the full list of validation rules.

### 2. Dimension reduction ("Apply" button) -> PCA/PaCMAP -> plots
- `process_working_data()` (`app/app.py:499-546`, decorated with `@callback_prevent_initial_output` from `app/src/callbacks.py`) fires on `apply-button` clicks.
- Deserializes `session` JSON, extracts selected features/loc_ids/n_neighbors/group choices, calls `process_dimension_reduction(...)` (`app/src/dimension_reduction_functions.py:147-164`):
  1. `subset_df_locIds` — filter rows to selected location IDs (`app/src/data_process.py:196-215`).
  2. `subset_df_numericFeatures` — filter columns to selected analytes while preserving original column order via `reindex` (`app/src/data_process.py:218-238`).
  3. `clr_transform_scale` (`app/src/compositional_data_functions.py:52-74`) — CLR-transforms the `cols_numeric_clr` subset, then `StandardScaler` on all numeric columns. `clr_transform` (lines 23-49) raises `ValueError` if zeros/NaNs are present in the CLR columns (zeros are first mapped to NaN, line 38) — this is now a secondary guard, since `build_mapped_dataset` already blocks CLR columns with zeros/negatives at upload time.
  4. `run_pca` (PCA n_components=2, sklearn) and `run_pmap` (PaCMAP, `pacmap.PaCMAP(n_neighbors=..., random_state=42)`) each build a "biplot" dataframe via `make_df_for_biplot` (`app/src/data_process.py:274-319`, applies `pc_scaler` min-max scaling to PC1/PC2 or PMAP1/PMAP2).
- Result packaged by `SessionManager.package_plotting_data` (`app/src/data_manager.py:245-256`) into `working-data` store, and `session["plotting_data"]` is updated in place with the current dropdown selections (persisted for reload).
- `plot_data()` callback (`app/app.py:585-607`) instantiates `DataPlotter` (`app/src/data_manager.py:134-241`), which reloads the PCA/PMAP dataframes from JSON, subsets by map-selected location IDs, filters by date-range slider (`df_between_dates` now no-ops when no date column was mapped, rather than crashing), then calls `plot_pca()`/`plot_pmap()` → `app/src/plotting.py` `make_fig_pca`/`make_fig_pmap` (built on `make_base_scatter_plot`, one Plotly trace per unique location, marker symbol from `dict_marker_map`, PCA plot additionally gets loading-vector annotations via `annotate_loadings`). `plotting.py` itself is untouched by the mapping refactor.

### 3. Map rendering and map-selection -> location filter
- `update_map()` (`app/app.py:434-465`) builds a Mapbox scatter (`make_map`, `app/src/plotting.py:50-110`) colored by the chosen `map-group-dropdown` value, using an Esri World_Imagery raster tile layer (`mapbox_layers` in `make_map`). Zoom is heuristically estimated from lat/lon spread (`estimate_mapbox_zoom`, `app/src/plotting.py:24-47`, hardcoded breakpoints, not a real Web Mercator calculation).
- It preserves user pan/zoom across re-renders by re-applying a filtered subset of `map-relayout-store` data (only `mapbox.center/zoom/bearing/pitch` keys) when the triggering input was the dropdown (`ctx.triggered_id == "map-group-dropdown"`).
- `map-selected-snapshot` button (`update_loc_id_dropdown`, `app/app.py:556-563`) reads `map.selectedData` (lasso/box select) and repopulates the `loc-id-dropdown` value with selected `customdata` (location IDs) — this is the "Grab map select for PCA/PacMAP" workflow tying map selection to the dimension-reduction subset.

### 4. Redis session persistence (app-level wiring FIXED; docker-compose's Redis service still broken)
- `app/src/session_manager.py` implements `save_to_redis`/`load_from_redis`/`list_keys`/`delete_session`/`session_exists`/`key_exists` using a Redis hash keyed `session:{session_id}` with 1-week TTL (`r.expire(..., 604800)`), connecting to `REDIS_HOST`/`REDIS_PORT` env vars (default `redis`:`6379`), matching the `redis` service name in `docker-compose.yml`.
- **Fixed during the hardening pass**: `app/app.py` used to have the import of these functions commented out while three callbacks (`update_redis_keys`, `load_session_data`, `save_session_data_to_redis`) called `list_keys`/`load_from_redis`/`save_to_redis` unconditionally, raising `NameError` at call time. The import is now restored and those three callbacks are wrapped with `log_and_surface_error`/`log_and_prevent_update` (`app/src/error_handling.py`) so a `redis.exceptions.ConnectionError` is caught/logged/surfaced instead of crashing. Untouched by the mapping refactor either way: Redis round-trips the whole `session` dict as one opaque blob, so the `meta_data` shape (unchanged) is transparent to it. `docker-compose.yml`'s Redis service wiring is separately still broken — see GOTCHAS.md.

## External Dependencies & Integrations
- **Redis** (`docker-compose.yml` service `redis`, image `redis:latest`) — session storage, see workflow 4 above. Env vars `REDIS_HOST`, `REDIS_PORT` read in `app/src/session_manager.py:7-8` (default `redis`/`6379`).
- **nginx** (`docker-compose.yml` service `nginx`, image `nginx:latest`) — reverse proxy + TLS termination + HTTP->HTTPS redirect. Config templates in `nginx/nginx.conf` and `nginx/conf.d/app.conf` contain **unfilled placeholders** (`SERVER_NAME`, `BACKEND_NAME`, `BACKEND_PORT`, `/path/to/.htpasswd`) — not usable as-is, needs templating/substitution before deploy. Also requires basic auth (`auth_basic`/`auth_basic_user_file`) on the proxied route.
- **certbot** (`docker-compose.yml` service `certbot`) — Let's Encrypt renewal loop (`certbot renew` every 12h). Volume mounts for certs/webroot are commented out in `docker-compose.yml:43-46`, and the equivalent nginx volume mounts (`nginx.conf`, `conf.d`, `certbot/conf`, `certbot/www`, `.htpasswd`) are also commented out (`docker-compose.yml:24-30`) — as committed, the nginx container would run with its stock default config, not the repo's `nginx/` files, and certbot has nowhere to persist certs. This looks like a deploy config that's mid-refactor (matches recent commit `b034711 "reconfigure docker-compose and nginx/app.conf"`).
- **app service in docker-compose.yml has no `build:` or `image:` directive** (both commented out, lines 3-4) — `docker compose up` cannot actually create the `app` container as committed; it must be built/tagged separately and the compose file updated, or this is intentionally left to external CI/CD (unverified).
- **Esri World Imagery tile server** (`https://server.arcgisonline.com/...`) — external basemap tiles fetched client-side by Plotly Mapbox layer (`app/src/plotting.py:87`), no API key handling visible, so presumably a public tile endpoint.
- **Mapbox/Plotly** — `px.scatter_mapbox` used without a Mapbox access token in code (style `"white-bg"` + custom raster layer avoids needing a Mapbox token — inferred from `mapbox_style="white-bg"` usage, unverified whether Plotly's default still requires any token for this style).
- No SQL database, no message queue, no other third-party API calls found.

## Build / Test / Run / Deploy
- **Python deps**: `app/requirements.txt` (UTF-16LE with CRLF — see Fragile section). Pinned versions include `dash==2.14.2`, `Flask==2.2.5`, `Flask-Caching==2.1.0` (imported nowhere directly found in `app/src` or `app/app.py` besides `cache_initialize.py`'s `make_custom_cache_key_dimensionReduction`, which isn't wired into a `Cache` object anywhere — **that one function is unused/dead**, but `cache_initialize.py`'s other function, `generate_df_hash_version`, is live and called from `DataPreprocessor.__init__`; see Fragile section), `pacmap==0.7.2`, `scikit-learn==1.4.1.post1`, `gunicorn==20.1.0`, `redis==3.5.3`.
- **Docker build**: `docker build -t <tag> .` from repo root (`Dockerfile` uses `python:3.11-slim`, installs `gcc g++ make python3-dev libffi-dev`, `pip install -r requirements.txt`, copies only `./app`, exposes 8080, runs gunicorn 3 workers).
- **docker-compose**: `docker compose up` — as committed, will fail/no-op for the `app` service (no build/image) and will not mount the repo's custom nginx configs or certbot volumes (all commented out). Needs local fixes before this compose file is deploy-ready.
- **Local dev without Docker**: `python server.py` from repo root (imports `from app import server`, implying `app/` must be importable — likely requires `cd app` first or `app` installed/symlinked; not verified, no `setup.py`/`pyproject.toml` found) — opens a browser tab and serves via Waitress on port 8080. Alternatively `python app/app.py` runs the Dash dev server directly on port 8050 with `debug=True`.
- **Tests**: `unittest`-based (`import unittest`, `class Test...(unittest.TestCase)`), run via `pytest` (evidenced by `.pytest_cache/` and `test/.pytest_cache/` directories). No CI config file (no `.github/`, no `azure-pipelines.yml`, etc. found in repo listing) — tests appear to be run locally/manually only. **Gotcha discovered while adding tests for this refactor**: since there's no top-level `app/__init__.py` and no `pytest.ini`/`pyproject.toml` setting `pythonpath`, `pytest test/` alone fails with `ModuleNotFoundError: No module named 'app'` unless the repo root is explicitly on `PYTHONPATH` — run as `PYTHONPATH=. pytest test/` (or `conda run -n <env> pytest test/` from repo root with `PYTHONPATH=.` set) instead of a bare `pytest test/`.
- **Encoding gotcha**: `app/requirements.txt` is UTF-16LE — `pip install -r requirements.txt` in the Dockerfile may fail or silently misparse depending on pip/Python locale defaults; not confirmed whether the Docker build actually succeeds (not run in this session).

## Observed Conventions
- **Declarative column-mapping model** (replaces the old naming-convention contract): the CSV "schema" is no longer implicit. `app/src/data_model.py`'s `ROLE_REGISTRY` is the single source of truth for what roles exist (location ID, lat, lon, numeric simple/CLR analytes, date, plotting group(s), marker symbol, map marker size, group color) and whether each is required/multi-valued; the mapping UI (`app/pages/home.py`) is generated programmatically from it, and `app/src/data_mapping.py`'s `build_mapped_dataset()` is the single place that validates a user's mapping and coerces the raw dataframe into the canonical internal shape. Adding/removing a role means editing `ROLE_REGISTRY` + the validation/build logic — no layout hand-editing required for the role dropdowns themselves.
- **State management**: All cross-callback state lives in `dcc.Store` components as JSON strings (`session`, `meta-data`, `working-data`, plus the new `raw-upload-store` staging area) rather than server-side/Flask session; every callback repeats `json.loads`/`json.dumps` on the full session blob. `pandas_to_json`/`json_to_pandas` (`app/src/data_process.py:240-252`) standardize dataframe (de)serialization (`orient="split"`, ISO dates, precise floats).
- **Error handling is now consistent (FIXED during the hardening pass)**: `app/app.py` callbacks use the `log_and_prevent_update`/`log_and_surface_error` decorators (`app/src/error_handling.py`) instead of ad hoc try/except+print. `DataPlotter.initialize_data` (`app/src/data_manager.py`) now logs and re-raises the *original* exception rather than wrapping it in a generic `ValueError`. The upload/mapping flow's structured, per-field `ValidationIssue`/`ValidationResult` reporting (`app/src/data_mapping.py`) is unchanged and remains the pattern for expected-bad-input, as opposed to the decorators, which are for unexpected exceptions.
- **`logging` is now the standard** (FIXED during the hardening pass) — `get_logger(__name__)` from `app/src/logging_config.py`, `configure_logging()` called once per process entrypoint. The old `print()`-for-status convention is gone; a stray `print()` anywhere is a leftover, not the standard.
- Docstrings (at least a one-liner, numpy-style where more detail helps) are now present across `app/app.py`'s callbacks and all of `app/src/`, not just the four files that originally had them (`data_process.py`, `data_mapping.py`, `dimension_reduction_functions.py`, `compositional_data_functions.py`).
- Commented-out dead code blocks are generally left in place rather than deleted elsewhere in the repo — **the regex-based column-classification code this refactor replaced was fully deleted, not commented out**, since the user explicitly ruled out maintaining a backward-compat path; don't take the general "leave dead code in place" pattern as covering that removal. (A separate, smaller dead-code deletion — ~48 lines of rejected/superseded implementations in `app/src/plotting.py` — happened during the hardening pass; also an explicit one-off, not a change to the general convention.)

## Fragile / Risky Areas
- **Redis save/load/list callbacks — FIXED during the hardening pass** (`app/app.py` — see Workflow 4). `docker-compose.yml`'s Redis *service* wiring is still separately broken.
- **`app/requirements.txt` is UTF-16LE encoded** — atypical for a requirements file, could break `pip install` in some environments/locales; worth verifying the Docker build actually succeeds today.
- **`docker-compose.yml` app service has no build/image directive** and the **nginx/certbot volume mounts are all commented out**, meaning the checked-in `nginx/` configs (with their `SERVER_NAME`/`BACKEND_NAME` placeholders) are not actually wired into the compose stack as committed.
- **Flask-Caching is a declared dependency and `app/src/cache_initialize.py` builds a cache key function (`make_custom_cache_key_dimensionReduction`) and a df-hash function**, but no `Cache(app, ...)` object or `@cache.memoize`/`@cache.cached` decorator was found anywhere in `app/app.py` or `app/src/`. PCA/PaCMAP re-runs on every "Apply" click regardless of the hash. Only `make_custom_cache_key_dimensionReduction` is actually dead code, though — `generate_df_hash_version` in the same file is live, called from `DataPreprocessor.__init__`.
- **Test coverage — partially improved during the hardening pass**: `app/src/session_manager.py`, `app/src/error_handling.py` (new), and `app/src/dimension_reduction_functions.py` now have tests, plus a minimal import-level smoke test for `app/app.py`. Still no per-callback behavioral coverage for `app/app.py`, and none for `app/src/callbacks.py` or `app/pages/*` (layout).
- **`clr_transform`'s in-place-mutation-before-validation bug — FIXED during the hardening pass**: it now copies its input (`X = X.copy()`) before mutating, so a caught `ValueError` no longer leaves the caller holding a corrupted array.
- **`make_map`'s color-column handling is destructive**: `df.rename(columns={_col_group_id: "."}, inplace=True)` (`app/src/plotting.py:69`) renames the caller's dataframe column in place to `"."` before plotting — the input `df_coords` object from `update_map` (`app/app.py`) is mutated as a side effect of a supposedly pure "make figure" function. `plotting.py` also hardcodes literal `LATITUDE`/`LONGITUDE` column reads with no override kwarg — the mapping layer (`data_mapping.build_mapped_dataset`) works around this by renaming the user's chosen lat/lon columns to those literal names rather than touching `plotting.py`.
- **`server.py` is excluded from the Docker image** (`.dockerignore:7`) — confirms the Docker deployment path only ever uses gunicorn/`app:server`, so `server.py`'s browser-launch behavior is dev/desktop-only, but this isn't documented anywhere.
- Two different "session ID" concepts are conflated in the UI copy vs code: the sidebar text input `user-session-id` is described as "Enter your user ID" but is used directly as the Redis hash key namespace (`session:{session_id}`) — i.e., it's a shared namespace with no auth.
- **No end-to-end browser verification of the new upload -> mapping-modal -> confirm -> map/PCA/PaCMAP flow has been done yet** (as of the refactor commit) — the automated test suite and a Python-level import smoke test have been run, but not a real click-through. See `docs/agent-context/REFACTOR-HANDOFF.md`.
- **Mapping is one-time per upload, not persisted** — there is no way to save/reuse a `ColumnMapping` across uploads of the same recurring data source (explicitly deferred, see REFACTOR-HANDOFF.md). Redis, if fixed, would be the natural place to persist mapping profiles.

## Open Questions
- Does the Docker build currently succeed given the UTF-16 `requirements.txt`? Not tested in this session.
- What actually builds/publishes the `app` image referenced (commented out) in `docker-compose.yml`? Is there external CI/CD, a manual `docker build && docker push` step, or is compose expected to be edited locally before each deploy?
- Is Flask-Caching intended to wrap `process_dimension_reduction` (the expensive PCA/PaCMAP step) but the integration was never finished, or was it abandoned? `cache_initialize.py`'s key-builder function has no visible caller.
- Was the Redis save/load feature intentionally disabled or is the commented-out import in `app/app.py:26-31` an accidental regression? Given three call sites still reference the unimported names, this looks like an unintentional break, but only a maintainer can confirm intent.
- Is `server.py` actually used by anyone, or is it dead/legacy now that gunicorn+Docker is the deployment path?
- Are the nginx `SERVER_NAME`, `BACKEND_NAME`/`BACKEND_PORT`, and `.htpasswd` placeholders filled in via some deploy-time templating step (e.g., `sed`, Ansible, manual edit) that isn't captured in this repo?
- What does "session ID" mean operationally — is it meant to be a real user identity, a project/site code, or just a free-text bucket?
- Should column-mapping profiles be persisted/reusable (e.g. saved per recurring data source)? Explicitly deferred during the declarative-data-model refactor — worth revisiting if users re-map the same CSV shape repeatedly.

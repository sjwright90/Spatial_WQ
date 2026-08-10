# Known-broken / fragile areas

Evidence and file:line detail in [codebase-map.md](codebase-map.md). Summary here of
what to check before touching adjacent code.

## Redis session save/load is broken as committed

`app/app.py` comments out the import of `save_to_redis`/`load_from_redis`/`list_keys`
(around line 26-31), but three callbacks (`update_redis_keys`, `load_session_data`,
`save_session_data_to_redis`) call them anyway — `NameError` at
runtime. The sidebar "Load-Save Session" UI is non-functional on `main`. Unclear if this
is an intentional mid-refactor state or a regression — ask before assuming either.
Unaffected by the declarative-data-model refactor: Redis round-trips the whole `session`
dict as one opaque JSON blob, and the `meta_data` shape inside it is unchanged, so
fixing Redis doesn't need to account for the mapping refactor.

## docker-compose.yml is mid-refactor

- `app` service has no `build:`/`image:` directive (both commented out) — `docker
  compose up` cannot create the app container as committed.
- nginx/certbot volume mounts (repo's `nginx/conf.d/app.conf`, cert paths, `.htpasswd`)
  are all commented out — the checked-in nginx config isn't wired into the compose
  stack; nginx would run with its stock default config.
- `nginx/nginx.conf` / `nginx/conf.d/app.conf` also have unfilled template placeholders
  (`SERVER_NAME`, `BACKEND_NAME`, `BACKEND_PORT`, `.htpasswd` path).

## Flask-Caching is scaffolded but not applied

`app/src/cache_initialize.py` builds a cache-key function and a dataframe-hash function,
but no `Cache(app, ...)` object or `@cache.cached`/`@cache.memoize` decorator exists
anywhere. PCA/PaCMAP (`process_dimension_reduction`) reruns from scratch on every
"Apply" click regardless of whether inputs are unchanged. If asked to add caching, this
is the intended hook point but it needs the actual `Cache` object wired up, not just the
key builder.

## CSV ingestion is now mapping-driven, not naming-convention-driven

As of the `refactor/declarative-data-model` branch, the old regex/column-name-prefix
convention (`NUMERIC-ANALYTE_`, `CLR-ANALYTE_`, `LOCATION-ID_`, `DATETIME`, `LABELS_*`,
`COLORS_*`, `MARKERS-PLOT-DOMAIN`, literal `LONGITUDE`/`LATITUDE`) has been **deleted
entirely, with no backward-compat fallback**. The functions that implemented it
(`get_key_cols_meta`, `get_key_cols_plot`, `rename_cols_plot_groups`,
`rename_cols_analyte`, the old/new label-format branch in
`DataPreprocessor.__init__`) no longer exist. Column classification now comes from a
user-supplied `ColumnMapping` (`app/src/data_model.py`), validated/applied by
`build_mapped_dataset()` (`app/src/data_mapping.py`). If you're looking for "the schema"
of an uploaded CSV, there isn't one anymore — any CSV works as long as the user maps its
columns via the modal in `app/pages/home.py`.

**Old fixtures/tests referencing the prefix convention were rewritten**, not adapted —
if you find a stray reference to `LOCATION-ID_`/`NUMERIC-ANALYTE_`/etc. anywhere, it's
either a deliberate historical comment or a bug, not a live code path. Full design
record + list of decisions made: `docs/agent-context/REFACTOR-HANDOFF.md`.

**No end-to-end browser click-through of the new upload -> map -> confirm -> plot flow
has been verified yet** as of the refactor commit — only the automated test suite and a
Python-level import smoke test have run. Do a manual pass before relying on this in
production.

## Silent date-corruption fallback (FIXED in the declarative-data-model refactor)

The old `set_key_col_date` (`app/src/data_process.py`, now deleted) used to replace the
**entire** date column with `datetime.now()` if `pd.to_datetime` failed on any row.
Date coercion now happens in `data_mapping._coerce_date` (`app/src/data_mapping.py`),
which uses `pd.to_datetime(..., errors="coerce")` per-row and reports a structured
warning listing how many rows failed. If **every** row in the mapped date column is
unparseable, the date role degrades to unmapped (`cols_key_meta["date"] = None`) with a
warning, rather than silently fabricating dates — the date-range slider then disables
itself (`update_date_range_slider` in `app/app.py` guards on `col_date` being falsy) and
`DataPlotter.df_between_dates` (`app/src/data_manager.py`) skips date filtering
entirely rather than crashing.

## In-place mutation side effects

- `clr_transform` (`app/src/compositional_data_functions.py`) mutates its input array in
  place (`X[X == 0.0] = np.nan`).
- `make_map` (`app/src/plotting.py`) renames the caller's dataframe column in place to
  `"."` before plotting — `df_coords` in `update_map` is mutated as a side effect of a
  supposedly pure figure-builder. `make_map` also hardcodes literal `LATITUDE`/
  `LONGITUDE` column reads with no override kwarg; `data_mapping.build_mapped_dataset`
  works around this by renaming the user's mapped lat/lon columns to those literal names
  rather than touching `plotting.py`.

Watch for these if refactoring either function or any caller that reuses the source
data/array afterward.

## requirements.txt encoding

`app/requirements.txt` is UTF-16LE. If a Docker build or local `pip install` fails or
misparses in a new environment, check encoding first.

## pytest needs the repo root on PYTHONPATH

There's no top-level `app/__init__.py` and no `pytest.ini`/`pyproject.toml` setting
`pythonpath`, so `pytest test/` run bare fails with `ModuleNotFoundError: No module
named 'app'`. Run `PYTHONPATH=. pytest test/` (repo root) instead — discovered while
adding tests for the declarative-data-model refactor; this is a pre-existing repo gap,
not something introduced by that refactor.

## server.py vs app/app.py entry points

`server.py` (Waitress + browser launcher) is excluded from the Docker image
(`.dockerignore`). Only `gunicorn app:server` (Dockerfile) is the real deployment path.
`server.py` is dev/desktop-only and undocumented as such — don't assume it's what
production runs.

## Test coverage gaps

No tests for `app/app.py` (all callback logic, including the new upload-stage /
confirm-mapping / group-color-dropdown callbacks introduced by the declarative-data-model
refactor), `app/src/dimension_reduction_functions.py` (PCA/PaCMAP),
`app/src/session_manager.py` (Redis), `app/src/callbacks.py`, or `app/pages/*`. Covered:
`data_manager`, `data_process`, `data_model`, `data_mapping`, `compositional_data_functions`,
`plotting`, `cache_initialize`. Be extra careful making changes in the uncovered files —
no regression safety net.

## "Session ID" is an unauthenticated shared namespace

The sidebar `user-session-id` text input is UI-labeled "Enter your user ID" but is used
directly as the Redis key namespace (`session:{session_id}`) with no access control —
two users entering the same ID collide/share sessions. Unverified whether this is
intentional for a small trusted user base; flag if asked to touch session-ID handling.

## Column mapping is not persisted

There's no way to save/reuse a `ColumnMapping` across uploads — every upload requires
re-mapping columns from scratch, even for the same recurring CSV shape. This was an
explicit scope decision during the declarative-data-model refactor (see
REFACTOR-HANDOFF.md), not an oversight. If asked to add persistence, Redis (once fixed)
is the natural place, or a new lightweight local store.

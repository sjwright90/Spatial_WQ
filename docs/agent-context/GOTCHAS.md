# Known-broken / fragile areas

Evidence and file:line detail in [codebase-map.md](codebase-map.md). Summary here of
what to check before touching adjacent code.

## Redis session save/load — app-level wiring fixed (docker-compose still broken)

**FIXED during the hardening pass** that also introduced `logging`/`error_handling.py`.
Previously, `app/app.py` commented out the import of
`save_to_redis`/`load_from_redis`/`list_keys` (around line 26-31) while three callbacks
(`update_redis_keys`, `load_session_data`, `save_session_data_to_redis`) called them
anyway — `NameError` at runtime, so the sidebar "Load-Save Session" UI was
non-functional. The import is now restored and those three callbacks are wrapped with
`log_and_surface_error`/`log_and_prevent_update` (`app/src/error_handling.py`) so a
`redis.exceptions.ConnectionError` (e.g. Redis unreachable) is caught, logged, and
surfaced as a message rather than crashing.

**Still broken**: `docker-compose.yml`'s `redis` service wiring (see below) — the app-level
code works, but you need a real Redis instance reachable at `REDIS_HOST`/`REDIS_PORT` to
exercise it, and `docker compose up` doesn't currently give you one as committed.
Unaffected by the declarative-data-model refactor: Redis round-trips the whole `session`
dict as one opaque JSON blob, and the `meta_data` shape inside it is unchanged.

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

Of the two functions in that file, only `make_custom_cache_key_dimensionReduction` is
actually unused/dead (no caller anywhere). `generate_df_hash_version` **is** live —
`DataPreprocessor.__init__` (`app/src/data_manager.py`) calls it to fingerprint every
uploaded dataframe. Don't assume the whole file is unused just because caching isn't
wired up.

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
record + list of decisions made: `docs/agent-context/codebase-map.md`'s CSV-upload
workflow section (a `REFACTOR-HANDOFF.md` was referenced here previously but never
actually existed in the repo history — don't go looking for it).

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

## In-place mutation side effects (FIXED during the hardening pass)

- `clr_transform` (`app/src/compositional_data_functions.py`) used to mutate its input
  array in place (`X[X == 0.0] = np.nan`) *before* validating it, so a caught
  `ValueError` still left the caller holding a corrupted array. It now copies
  (`X = X.copy()`) before mutating.
- `make_map` (`app/src/plotting.py`) used to rename the caller's dataframe column in
  place to `"."` before plotting — `df_coords` in `update_map` was mutated as a side
  effect of a supposedly pure figure-builder. It now does a non-mutating
  `df = df.rename(...)`. `make_map` still hardcodes literal `LATITUDE`/`LONGITUDE`
  column reads with no override kwarg; `data_mapping.build_mapped_dataset` works around
  this by renaming the user's mapped lat/lon columns to those literal names rather than
  touching `plotting.py`'s contract.

If you find code elsewhere still relying on either function's old mutating behavior
(unlikely, since neither caller reused the mutated object), that's a bug now, not a
documented gotcha.

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

`app/src/session_manager.py` (`test_session_manager.py`, mocks the Redis client),
`app/src/error_handling.py` (`test_error_handling.py`), and a minimal `app/app.py`
import-level smoke test (`test_app_callbacks.py` — loads `app/app.py` directly via
`importlib` since it isn't a normal package-relative import, see that file's comments)
were added during the hardening pass. `app/src/dimension_reduction_functions.py` now has
a basic test too (`test_dimension_reduction_functions.py`).

Still no tests for the bulk of `app/app.py`'s callback *logic* (only the import-level
smoke test exists — no per-callback behavioral tests), `app/src/callbacks.py`, or
`app/pages/*`. Be extra careful making changes there — still no regression safety net
beyond manual/browser testing.

## "Session ID" is an unauthenticated shared namespace

The sidebar `user-session-id` text input is UI-labeled "Enter your user ID" but is used
directly as the Redis key namespace (`session:{session_id}`) with no access control —
two users entering the same ID collide/share sessions. Unverified whether this is
intentional for a small trusted user base; flag if asked to touch session-ID handling.

## Column mapping is not persisted

There's no way to save/reuse a `ColumnMapping` across uploads — every upload requires
re-mapping columns from scratch, even for the same recurring CSV shape. This was an
explicit scope decision during the declarative-data-model refactor, not an oversight.
If asked to add persistence, Redis (once fixed) is the natural place, or a new
lightweight local store.

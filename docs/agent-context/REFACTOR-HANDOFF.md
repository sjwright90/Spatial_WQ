# Handoff: declarative data model refactor

Branch: `refactor/declarative-data-model`. Full original design doc (context,
rationale, alternatives considered):
`C:\Users\SamWright\.claude\plans\a-major-refactor-needs-purrfect-fern.md`
(local plan file, not in repo).

## Status

All three planned steps are implemented and `pytest test/` passes (58 tests,
run via `PYTHONPATH=. pytest test/ -q` — see Fragile note below on why
`PYTHONPATH=.` is required). User has smoke-tested the Dash app import
manually; **no browser/end-to-end run of the actual upload → mapping →
plot flow has been done yet** — that's the first thing to verify by hand
before trusting this in production.

## What changed

The old regex/column-name-prefix convention (`NUMERIC-ANALYTE_`,
`CLR-ANALYTE_`, `LOCATION-ID_`, `DATETIME`, `LABELS_*`, `COLORS_*`,
`MARKERS-PLOT-DOMAIN`, `MAP-MARKER-SIZE`, literal `LONGITUDE`/`LATITUDE`) is
gone entirely — no backward-compat fallback. Users now upload any CSV and
map columns to semantic roles via a modal UI.

- **`app/src/data_model.py`** (new) — pure schema: `ColumnRole` enum,
  `RoleSpec`, `ROLE_REGISTRY` (single source of truth the mapping UI iterates
  over), `ColumnMapping` dataclass (the user's completed mapping).
- **`app/src/data_mapping.py`** (new) — `build_mapped_dataset(df_raw, mapping)
  -> MappedDataset`. Runs duplicate/required-role/existence checks, then
  per-value type coercion (lat/lon range, numeric, CLR positivity, date,
  hex color), collecting `ValidationIssue(field, severity, message,
  offending_values)` into a `ValidationResult` instead of the old
  dict-of-bools. Only blocks (`has_errors`) on: missing required role,
  duplicate column-to-role mapping, missing raw column, out-of-range lat/lon,
  CLR value ≤0. Everything else (missing date/marker/marker-size/colors, bad
  hex, some unparseable dates) degrades gracefully with a warning. Also does
  the two canonical renames downstream plotting needs: mapped lat/lon →
  literal `LATITUDE`/`LONGITUDE` columns (plotting.make_map hardcodes these,
  no override kwarg exists).
- **`app/src/data_process.py`** — deleted `get_key_cols_meta`,
  `get_key_cols_plot`, `rename_cols_plot_groups`, `rename_cols_analyte`, the
  old/new label-format branching, dead commented-out code. Kept
  `df_col_group_to_dict`, `make_color_dict`, `subset_df_*`,
  `pandas_to_json`/`json_to_pandas`, `pc_scaler`, `make_df_for_biplot`
  unchanged. `extract_coordinate_dataframe` gained an optional
  `col_marker_size` param (synthesizes a constant `MAP-MARKER-SIZE` column
  when not mapped). `find_make_color_dict`/`make_plotting_group_color_dicts`
  now take an explicit `group_colors` dict (from `ColumnMapping.group_colors`)
  instead of a `new_format` bool + regex search.
- **`app/src/data_manager.py`** — `DataPreprocessor.__init__(content_string,
  mapping: ColumnMapping)` now delegates to `build_mapped_dataset`; exposes
  `self.validation: ValidationResult`. On `validation.has_errors`, all other
  attributes (`df_master`, `cols_key_plot`, etc.) are `None` — callers must
  check `has_errors` first. `run_all_checks`/`check_*` methods removed
  (superseded by `ValidationResult`). `get_session_dict()`'s output shape is
  **unchanged** — this is what let `app.py`'s dropdown/map/plot callbacks and
  `DataPlotter` stay almost untouched. `dict_marker_map` defaults every
  location to `"circle"` when no marker-symbol role is mapped (plotting.py
  indexes this dict directly with `[]`, no `.get()` fallback exists, so this
  default-fill was required to avoid a `KeyError`). `DataPlotter.df_between_dates`
  now no-ops when `cols_key_meta["date"]` is `None` instead of crashing.
- **`app/app.py`** — upload is now two callbacks: `stage_raw_upload` (reads
  just the CSV header, opens the mapping modal, populates all role dropdowns'
  `options` with the raw column list) and `confirm_mapping` (reconstructs a
  `ColumnMapping` from the modal's pattern-matching component state, runs
  `DataPreprocessor`, renders `ValidationResult` issues in the modal on
  error, or populates `meta-data`/`session` stores and closes the modal on
  success). A third callback, `update_group_color_dropdowns`, dynamically
  renders one optional color-column dropdown per selected plotting-group
  column. `update_date_range_slider` guards against `col_date` being `None`.
- **`app/pages/home.py`** — `mapping_modal` (a `dbc.Modal`) is generated
  programmatically from `ROLE_REGISTRY` using Dash pattern-matching ids
  (`{"type": "role-mapping", "role": <role.value>}`), so adding/removing a
  role in `data_model.py` requires no layout edits. New
  `dcc.Store(id="raw-upload-store")` holds the staged upload
  (`content_string` + raw column list) between the two upload steps.
- **Tests** — new `test_data_model.py`, `test_data_mapping.py` (table-driven
  validation cases: happy path, each missing-required-role, duplicates,
  missing columns, bad lat/lon, numeric coercion, CLR positivity, date
  degradation, hex colors, all-optional-roles-absent). Rewrote
  `test_data_manager.py`/`test_data_process.py` to use `ColumnMapping`
  fixtures with arbitrary (non-prefixed) column names, proving the old
  convention is no longer load-bearing.

## Explicitly untouched (by design)

`app/src/plotting.py`, `app/src/dimension_reduction_functions.py`,
`app/src/compositional_data_functions.py`, `app/src/cache_initialize.py` —
zero edits. Confirmed via full-file review that they're either fully
parameterized or self-produce the only hardcoded names they need
(`PC1`/`PC2`/`metals`, `PMAP1`/`PMAP2`).

## Decisions made during planning (binding, don't relitigate without asking)

- Full replacement, no backward-compat auto-detection of the old convention.
- Column mapping is one-time per upload — no persisted/reusable mapping
  profiles. (Natural next feature if requested, but out of scope here.)
- Optional roles (date, marker symbol, marker size, group colors) degrade
  gracefully with a warning; required roles (location id, lat, lon, ≥1
  numeric analyte, ≥1 plotting group) block with an error.
- Lat/lon: rename-workaround chosen over adding `lat=`/`lon=` override kwargs
  to `make_map` (kept `plotting.py` untouched).
- CLR positivity (`<=0`) stays a **blocking error**, not a soft warning with
  auto-exclusion (matches pre-refactor behavior).

## Known gaps / natural follow-ups

- **No end-to-end browser verification yet** of upload → mapping modal →
  confirm → map/PCA/PaCMAP render. Do this first.
- No new tests for the `app.py` callbacks themselves (`stage_raw_upload`,
  `confirm_mapping`, `update_group_color_dropdowns`) — `app.py` had zero
  callback coverage before this refactor too (see GOTCHAS.md), unchanged gap.
- The mapping modal uses only existing generic dropdown/button styles from
  `app/pages/www/style/style.py` — no modal-specific styling was added; the
  UI is functional but not polished.
- Redis save/load (`app.py` `update_redis_keys`/`load_session_data`/
  `save_session_data_to_redis`) is still broken exactly as documented in
  GOTCHAS.md — untouched, out of scope here. Note if you fix it: Redis
  round-trips the whole `session` dict as one opaque blob, so the
  `meta_data` shape change in this refactor is transparent to it, no extra
  work needed there.
- Mapping-profile persistence (save/reuse a `ColumnMapping` across uploads)
  was explicitly deferred — would need a small new store/UI plus probably a
  fixed Redis layer if it should survive a session.

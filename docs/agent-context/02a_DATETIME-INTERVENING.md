# Handoff: upstream datetime Filter - implementation done, tests unverified

**Status when this was written:** all planned code changes are written and
believed complete per the plan below. **Tests have never successfully run** -
every attempt to run the suite hung with zero output for 10-20+ minutes and
was killed. Root cause not diagnosed; the user's machine was "bogged down"
for unrelated reasons and a restart was requested before continuing. This is
the single blocking item before this PO can close.

Prior session: branch `feature/selectable-pca-components`, this work builds on
top of `docs/agent-context/02_NEXT-STEPS-DATETIMEFILTER-HANDOFF.md` (the
original feature request/spec - read that first for full context/rationale).
Session that did this work:
`https://claude.ai/code/session_018V4LysJrDWDMRWgy145nXq` - if the user pastes
this doc back to the same Claude Code session/job, it already has full
context; a fresh agent should read this doc plus the spec doc plus the plan
file below.

**Full implementation plan (all design decisions already resolved with the
user)**: `C:\Users\SamWright\.claude\plans\you-are-a-senior-graceful-tarjan-agent-ab0ac521fd7b6978c.md`
- This is the authoritative diff-level spec. Everything in it has been coded
  (see file list below) - it is not a "to-do", it's a record of what was
  built and why. Re-read it before making further changes so new work stays
  consistent with the confirmed design decisions (day-level `DatePickerRange`,
  Filter/Mask fully independent, manual entity-picker restricted to the
  Filter range instead of an export-time precedence rule).

## What "Filter" means here (terminology, don't confuse with existing "Mask")

- **Filter** (new, this PO): upstream, pre-pipeline date range. Subsets
  `df_master` before PCA/PaCMAP/KMeans run, so it actually changes the
  computed variance/embedding/clusters. UI: new `dcc.DatePickerRange` in the
  "Plot filters" sidebar (`date-filter-range-picker`).
- **Mask** (pre-existing, untouched): `date-range-slider` below the plots.
  Only trims already-computed PCA/PaCMAP output for display. Left completely
  alone per user's explicit "fully independent" decision.

## Files changed (all in working tree, uncommitted)

Verified via `git status --short` at hand-off time:

```
 M app/app.py
 M app/pages/home.py
 M app/src/clustering_functions.py
 M app/src/data_manager.py
 M app/src/data_process.py
 M app/src/dimension_reduction_functions.py
 M test/src/test_app_callbacks.py
 M test/src/test_clustering_functions.py
 M test/src/test_data_manager.py
 M test/src/test_data_process.py
 M test/src/test_dimension_reduction_functions.py
?? docs/agent-context/02_NEXT-STEPS-DATETIMEFILTER-HANDOFF.md   (the spec)
?? docs/agent-context/02a_DATETIME-INTERVENING.md               (this file)
```

`docs/agent-context/03_NEXT-STEPS-UX-HANDOFF.md` (also untracked) and the
deletion of `docs/agent-context/02_NEXT-STEPS-UX-HANDOFF.md` are **unrelated**
leftovers from a *different* prior task (legend-width shrinking on long
category labels) - not part of this Filter work, don't let them distract
during review/commit.

### `app/src/data_process.py`
- New `subset_df_dateRange(df, col_date, date_range)` - day-level (not
  year-level) inclusive range filter, no-op passthrough copy when either arg
  is falsy. Mirrors `subset_df_locIds`'s style, placed right after it.
- `build_custom_group_export_df(...)` gained optional `date_filter_range=None`
  kwarg: when given, any cell still at `DEFAULT_UNASSIGNED_CATEGORY` on a row
  outside that range is overwritten with `DATE-FILTERED-[start->end]`
  (day-precision date strings). Cells that already hold a real assignment are
  never touched.

### `app/src/dimension_reduction_functions.py`
- `process_dimension_reduction(...)` gained optional `col_date=None,
  date_range=None` trailing kwargs; applies `subset_df_dateRange` first,
  before `subset_df_locIds`. Backward compatible (existing callers/tests
  without the new kwargs are unaffected).

### `app/src/clustering_functions.py`
- `process_clustering(...)` same trailing-kwarg pattern (`col_date=None,
  date_range=None`), same subset-first placement. Confirms in its docstring
  that this closes the handoff's "ESSENTIAL CONSIDERATION" about clustering's
  PCA-feature-space branch needing to see Filter-aware data.

### `app/src/data_manager.py`
- `SessionManager.get_session_dict()`'s `plotting_data` dict gained
  `"date_filter_range_dropdown_value": None` default, so a freshly-uploaded
  session has the key present before any Apply.

### `app/pages/home.py`
- Deleted the dead `check_list_plot_date`/`date-checklist`
  ("DATE GROUPING COMING SOON" placeholder, zero callback wiring) - replaced
  with `date_filter_picker` (`dcc.DatePickerRange`, id
  `date-filter-range-picker`, plus a `date-filter-reset-button`), placed in
  `sidebar` where the placeholder was.
- Added `date_filter_indicator` (`html.Div(id="date-filter-indicator")`) into
  `apply_row`, so a "Filter pending" badge is visible even when the sidebar
  is collapsed.
- Existing `range_slider_date_filter`/`date-range-slider` (the Mask):
  untouched.

### `app/app.py`
- New imports: `subset_df_dateRange` from `src.data_process`.
- Three new callbacks (inserted after `update_date_range_slider`, before
  `update_dropdowns`):
  - `update_date_filter_picker` - populates
    `date-filter-range-picker`'s `min_date_allowed`/`max_date_allowed`/
    `start_date`/`end_date`/`disabled` from the mapped date column, restoring
    the last-Applied value from
    `session["plotting_data"]["date_filter_range_dropdown_value"]` if
    present, else defaulting to full range. Disabled when no date column is
    mapped.
  - `reset_date_filter` - "Reset filter" button resets picker to full range.
  - `update_date_filter_indicator` - shows a `dbc.Badge` when the live
    (not-yet-Applied) picker position is narrower than the full range.
- `process_working_data` (the Apply-button callback): added
  `State("date-filter-range-picker", "start_date"/"end_date")`, builds
  `date_filter_range`, passes `col_date=`/`date_range=` into
  `process_dimension_reduction`, and persists
  `"date_filter_range_dropdown_value"` into `session["plotting_data"]`
  alongside the existing `feature_selection_dropdown_value`/
  `loc_id_dropdown_value`.
- `open_blank_custom_group_modal` and `populate_custom_group_from_selection`
  (manual lasso-select entity picker): both now subset `df_master` via
  `subset_df_dateRange(df_master, col_date, date_filter_range)` **before**
  calling `_build_entity_dropdown_options`, using the persisted
  `plotting_data["date_filter_range_dropdown_value"]`. This is the resolution
  of the "manual assignment could target a Filter-excluded entity" gap the
  user flagged - closed structurally (the entity can't be picked at all)
  rather than arbitrated at export time.
- `run_clustering_into_draft`: reads `date_filter_range` from
  `plotting_data`, passes `col_date=`/`date_range=` into `process_clustering`,
  and also subsets `df_master` before building its post-cluster entity
  dropdown options (same reasoning as above).
- `download_custom_groups_csv`: reads `date_filter_range` from
  `session["plotting_data"]`, passes it to `build_custom_group_export_df`.

## Design decisions already confirmed with the user (do not re-litigate)

1. **Widget = two `dcc.DatePickerRange` boxes**, day-level precision - user
   explicitly rejected a RangeSlider (sidebar too small, wanted a visually
   distinct control from the existing Mask slider, day precision worth it).
2. **Filter and Mask are fully independent** - no linkage/clamping between
   them, existing Mask code untouched.
3. **No export-time precedence rule** - user flagged that a manual/lasso
   assignment landing on a Filter-excluded entity would be a real
   data-integrity leak, not just an export cosmetic. Resolved by restricting
   the entity picker itself to the Filter range (section above), so a new
   assignment can never target an excluded entity. The
   `DATE-FILTERED-[...]` export marker still only overwrites cells still at
   `DEFAULT_UNASSIGNED_CATEGORY`, which now only matters for the residual
   case of a group created earlier under a wider/no Filter.
4. **Marker format**: `DATE-FILTERED-[YYYY-MM-DD->YYYY-MM-DD]`.

## What's NOT done / open items

1. **Tests were written but never run.** New/extended test coverage exists
   in all five touched test files (see list above) - `subset_df_dateRange`
   correctness/passthrough/no-mutation, `build_custom_group_export_df`
   marker behavior (including the "don't overwrite a real assignment" case),
   `process_dimension_reduction`/`process_clustering` date-filter narrowing +
   regression-guard default-None cases, `SessionManager.get_session_dict`'s
   new default key, and an `app.py`-level test that a Filter-excluded entity
   never appears in the manual entity-picker's options. **None of this has
   been executed even once.** This is the top priority on resume.
2. **Test-run fail on import when user runs.** 
  "test_clustering_functions.py"
  "test_data_manager.py"
  "test_data_process.py"
  "test_dimension_reduction_functions.py"
  All fail with (or similar):
          "(daily_driver) PS C:\deployment\wq_spatial_app\00_SPATIAL_WQ> conda run -n daily_driver pytest .\test\src\test_clustering_functions.py
          ============================= test session starts =============================
          platform win32 -- Python 3.11.15, pytest-9.0.2, pluggy-1.6.0
          rootdir: C:\deployment\wq_spatial_app\00_SPATIAL_WQ
          plugins: anyio-4.13.0, dash-4.1.0, cov-7.1.0
          collected 0 items / 1 error

          =================================== ERRORS ====================================
          ___________ ERROR collecting test/src/test_clustering_functions.py ____________
          ImportError while importing test module 'C:\deployment\wq_spatial_app\00_SPATIAL_WQ\test\src\test_clustering_functions.py'.
          Hint: make sure your test modules/packages have valid Python names.
          Traceback:
          C:\Users\SamWright\miniforge3\envs\daily_driver\Lib\importlib\__init__.py:126: in import_module
              return _bootstrap._gcd_import(name[level:], package, level)
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
          test\src\test_clustering_functions.py:3: in <module>
              from app.src.clustering_functions import (
          E   ModuleNotFoundError: No module named 'app'
          =========================== short test summary info ===========================
          ERROR test/src/test_clustering_functions.py
          !!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
          ============================== 1 error in 7.39s ===============================
          ERROR conda.cli.main_run:execute(142): `conda run pytest .\test\src\test_clustering_functions.py` failed. (See above for error)"
3. **Not yet reviewed for correctness beyond the plan/design** - no
   `/code-review` pass run against the diff yet.
4. **Not manually smoke-tested in the browser.** Per this repo's `CLAUDE.md`,
   agents must not launch `python app/app.py`/`server.py` themselves - the
   user runs that. Once tests pass, the user should Apply with a narrowed
   Filter and confirm: the biplot/PaCMAP actually changes (not just row
   count - variance should shift), the "Filter pending" badge
   appears/disappears correctly, Reset works, the custom-group entity picker
   excludes filtered-out rows, and the exported custom-groups CSV shows the
   `DATE-FILTERED-[...]` marker correctly.
5. **Optional UX nicety, explicitly deferred, not implemented**: when a
   map/plot lasso selection includes Filter-excluded points, those points
   silently drop out of the entity picker's selection with no user-facing
   count/notice (e.g. "3 of your 10 selected points were excluded by the
   active date Filter"). Flagged in the plan as a nicety, not required for
   correctness - revisit only if the user wants it.
6. **Not committed.** Working tree is dirty on `feature/selectable-pca-components`
   (see file list above); nothing has been committed this session.

## Suggested next steps on resume

1. Replicate test fails, might be user error.
2. Fix any real errors
3. Once green, optionally run `/code-review` on the diff.
4. Ask the user to smoke-test in their own already-running dev server (per
   `CLAUDE.md`, don't launch it yourself) using the checklist in item 4
   above.
5. Commit on `feature/selectable-pca-components` (new branch not needed -
   already off `main`).

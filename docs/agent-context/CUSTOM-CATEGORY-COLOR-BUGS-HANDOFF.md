Task 1: Fix Bug 1 (Live Map Recoloring on "Customize Colors") — **FIXED**

    Goal: Allow the map to update when color overrides are applied, without locking or resetting the user's pan/zoom view.

    Fix, round 1: `update_map` (`app/app.py`) still only takes `map-group-dropdown`/`meta-data` as Inputs and rebuilds the full figure. A new callback, `patch_map_colors`, takes `custom-color-overrides` as its Input and returns a `dash.Patch()` that sets `data[i].marker.color` per trace (matched by trace name against the override's effective color dict) — it never touches `layout`, so `layout.map` (center/zoom/bearing/pitch) is left exactly as the user set it. Both callbacks write to `Output("map", "figure", allow_duplicate=True)`.

    Fix, round 2 (user re-tested, reported colors "flicker on for a second, then revert"): root cause was that `apply_color_overrides`/`reset_color_overrides` write to the `"session"` store, and `update_dropdowns` (`Input("session","data")`) unconditionally resets `map-group-dropdown`'s `value` on *every* session write, including ones that only touched `custom_color_overrides`. Dash treats an Output write as a change and re-fires downstream Inputs even when the written value is identical to what's already there, so this resets `update_map`'s `map-group-dropdown` Input, forcing a full rebuild moments after `patch_map_colors` patched the visible colors. That rebuild read colors straight from `meta_data["dict_generic_colors"]` with no override applied — hence the instant revert. Fixed by having `update_map` also read `custom-color-overrides` as a **State** (not Input — that would reintroduce the original pan/zoom-reset bug) and merge it into `color_discrete_map` via `merge_color_overrides` before building the figure, so *every* full rebuild is override-correct regardless of what triggered it, not just the instant-patch path.

Task 2: Fix Bug 2 (Custom Group Sub-Trace Splitting in plotting.py) — **FIXED**

    Goal: Fix marker recoloring for ENTITY_ID-scoped custom groups where multiple dates at the same LOCATION_ID belong to different categories, while preserving legend structure.

    Fix, round 1: `make_base_scatter_plot` (`app/src/plotting.py`) no longer takes `group_df[ctx.col_primary_domain].unique()[0]` as representative for the whole location. For each `col_loc_id` group it finds the distinct `(col_primary_domain, col_secondary_domain)` pairs actually present and adds one sub-trace per pair (correct face/line color per point).

    Fix, round 2 (user: PCA/PaCMAP now color correctly, but "legend should show each trace... in instances where ENTITY_ID results in multiple categories for a given location we DO need to show that on the legend"): round 1 collapsed all of a location's split sub-traces under one shared `legendgroup`/`showlegend=True`-on-first-only, so only one (arbitrary) category's legend entry was visible per location. Now: a location with only one category keeps the plain single-trace, single-legend-entry behavior (`name=loc_code`) exactly as before the whole ENTITY_ID-splitting feature; a location with multiple categories gives **every** sub-trace its own visible legend entry, named `f"{loc_code} [{date_min}->{date_max}]"` (single date if the sub-trace only has one, via new helper `_format_date_range`) so the legend disambiguates which points belong to which category. `legendgroup` is still set to `str(loc_code)` per sub-trace (harmless/unused for grouping purposes now that all entries show, but keeps hover/selection-group semantics consistent).

Step 3: Verification & Hand-off — **DONE (automated); live-browser check still needed from user**

    Regression tests added and passing (`PYTHONPATH=. pytest test/` — 115/115 green, run via `conda run -n daily_driver`):
    - `test/src/test_app_callbacks.py::TestMapColorPatchPreservesRelayout`:
      - `test_patch_map_colors_leaves_layout_map_untouched` / `test_patch_map_colors_updates_overridden_trace_marker_color` — the instant-patch path.
      - `test_update_map_full_rebuild_still_honors_color_overrides` — a full `update_map` rebuild (as forced by `update_dropdowns`' side effect) still reflects an applied override.
    - `test/src/test_plotting.py::test_make_base_scatter_plot_splits_by_category_within_location` — a location with two ENTITY_ID rows in different categories renders as two correctly-colored sub-traces, each with its own `"loc_code [date]"` legend entry; a location with one category keeps a plain single legend entry.
    - `test/src/test_data_manager.py::TestDataPlotter::test_plot_pca_with_entity_id_splits_location_by_custom_category` — same case end-to-end through `DataPlotter.plot_pca`.

    User Hand-Off: please run the server and confirm live in the browser:
    - Change a category color in "Customize Colors" and confirm the map updates live and *stays* updated (no flicker/revert), without resetting zoom/pan.
    - Assign different dates at the same location to different custom categories and confirm: hover text and marker colors match on the map; the PCA/PaCMAP legends show a separate, correctly-labeled (`loc_code [date]`) entry per category for that location, not one collapsed entry.

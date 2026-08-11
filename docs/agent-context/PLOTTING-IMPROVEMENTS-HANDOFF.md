# plotting.py improvement backlog

Written at the end of a hardening-pass session (see CLAUDE.md Conventions/GOTCHAS.md
for that pass's context) as a handoff to a fresh session. User wants all 7 items done.
Read `app/src/plotting.py` fresh before starting — don't assume line numbers below
still match exactly.

CLAUDE.md flags `plotting.py` as sensitive: confirm with the user before changing its
hardcoded `LATITUDE`/`LONGITUDE`/`MAP-MARKER-SIZE`/`PC1`/`PC2`/`PMAP1`/`PMAP2`/`metals`
column-name contract (relevant to item 7 below).

## Quick, low-risk wins

1. **Dead `title` parameter.** `make_base_scatter_plot` accepts `title`, and
   `make_fig_pca`/`make_fig_pmap` both compute a real title string (e.g.
   `f"PCA ({expl_var[0]*100:.2f}%, ...)"`) to pass in, but the layout call does
   `title=None` unconditionally — the computed title is silently discarded. Either
   wire it up (`title=title` in `update_layout`) or drop the dead param/computation.
   Confirm with the user which they want (visible title vs. removing dead code) before
   picking - it's a visible UI behavior change either way.

2. **Fragile kwarg filtering in `make_map`.** Currently:
   `{k: v for k, v in kwargs.items() if k in px.scatter_mapbox.__code__.co_varnames}`
   — this introspects the function's *local variable names* via `__code__`, not its
   actual parameters; it happens to work because Plotly Express functions assign every
   param to a same-named local, but that's accidental. Replace with
   `inspect.signature(px.scatter_mapbox).parameters` for a correct, intentional filter.

3. **Deprecated Plotly API.** The test suite already emits `DeprecationWarning`s:
   `*scatter_mapbox* is deprecated! Use *scatter_map* instead` (also
   `*scattermapbox* is deprecated! Use *scattermap* instead`). Migrate
   `px.scatter_mapbox`/the `"scattermapbox"` selector to `px.scatter_map`/`"scattermap"`
   before Plotly actually removes the old API. Bonus: `scattermap` (MapLibre-based)
   supports `fitbounds="locations"`, which could replace `estimate_mapbox_zoom`'s
   hand-rolled breakpoint table entirely (its own comment admits it's "not a real Web
   Mercator calculation") - worth doing as part of this item since they're related, but
   confirm with the user since it changes the auto-zoom behavior, not just the API call.

## Medium — structural cleanup

4. **Long, repetitive signatures.** `make_base_scatter_plot`/`make_fig_pca`/
   `make_fig_pmap` each take 10-14 params, and the same cluster (`col_loc_id`,
   `col_primary_domain`, `col_secondary_domain`, `col_date`, `col_entity_id`, the two
   color dicts, the marker dict) travels through every call unchanged. Introduce a
   small dataclass (e.g. `PlotContext`) bundling that cluster - matches this repo's
   stated preference for dataclasses over loose params/dicts for structured data. Only
   caller is `app/src/data_manager.py`'s `DataPlotter.plot_pca`/`plot_pmap`, so it's a
   contained change - update those two call sites too. Primary/secondary domain args
   are positionally adjacent today and easy to swap by accident; a dataclass with named
   fields removes that footgun.

5. **Underscore the internal-only helpers.** `find_axis_limits`, `generate_text`,
   `annotate_loadings`, `estimate_mapbox_zoom` aren't called from outside
   `plotting.py` (verify with `grep -rn` across `app/` before renaming - only
   `make_map`/`make_fig_pca`/`make_fig_pmap`/`empty_fig` are called externally, from
   `data_manager.py`). Rename to `_find_axis_limits` etc. so the public surface is
   obvious at a glance. Check `test/src/test_plotting.py` for any direct imports of
   these that would need updating too.

## Bigger — do last, most likely to need its own back-and-forth

6. **No behavioral test coverage.** `test/src/test_plotting.py` currently just
   smoke-tests that figures get built without error. Add real assertions for: legend
   collapsing to one trace per site (not one per group/date - see
   `test_data_manager.py::test_plot_pca_with_entity_id_and_repeat_visits_collapses_legend`
   for the existing analogous test in the sibling module, same behavior originates
   here), the color/marker fallback-to-default behavior added during the hardening
   pass (`_DEFAULT_COLOR`/`_DEFAULT_MARKER_SYMBOL`), hover-text content
   (`generate_text`'s two branches - same vs. different primary/secondary domain), and
   `customdata` shape (`[col_loc_id, entity_col]` pairs). This is the item most likely
   to catch a regression from items 1-5 and 7, so doing it last (after the other
   changes land) means it can assert the *new* intended behavior directly rather than
   being written twice.

7. **Loosen the hardcoded column-name contract**
   (`LATITUDE`/`LONGITUDE`/`MAP-MARKER-SIZE`/`PC1`/`PC2`/`PMAP1`/`PMAP2`/`metals`).
   Deliberate per CLAUDE.md/`docs/agent-context/REFACTOR-HANDOFF.md` - `data_mapping.py`
   currently renames columns to match these literals specifically so `plotting.py`
   doesn't need overrides. Turning these into parameters with today's values as
   defaults would decouple the two files with **no behavior change**, but explicitly
   confirm with the user first per CLAUDE.md's standing instruction on this file - this
   is the one item where "the user already said do all 7" may not cover the specific
   design of *how* (e.g. which literals become params vs. stay fixed, whether
   `data_mapping.py` should also stop renaming once `plotting.py` accepts overrides).

## Suggested order
1 → 2 → 3 → 5 → 4 → 7 → 6, running `PYTHONPATH=. pytest test/` after each item
(repo root must be on PYTHONPATH - see CLAUDE.md Build/Test/Run). Format touched files
with `black --line-length 100`, lint with `ruff check`, after each item rather than
saving formatting to the end.

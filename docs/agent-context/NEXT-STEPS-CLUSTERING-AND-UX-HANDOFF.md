# Handoff: next steps after the custom-category-color bug fixes

## Quick summary of what was just fixed

See [CUSTOM-CATEGORY-COLOR-BUGS-HANDOFF.md](CUSTOM-CATEGORY-COLOR-BUGS-HANDOFF.md)
for full detail. In short, two rounds of fixes landed and are merged to `main`:

1. **Map color overrides now recolor live and stay recolored.** `patch_map_colors`
   (`app/app.py`) does an in-place `dash.Patch()` on `marker.color` so pan/zoom
   survive. The "flickers on then reverts" follow-up bug was
   `update_dropdowns` resetting `map-group-dropdown`'s value on every
   `session` write (color overrides live in `session` too), which re-triggered
   `update_map`'s full rebuild with un-overridden colors; `update_map` now
   also merges `custom-color-overrides` (as a `State`) so *any* rebuild,
   whatever triggers it, stays override-correct.
2. **PCA/PaCMAP legend now shows one entry per category when a location's
   ENTITY_ID rows split across categories** (`make_base_scatter_plot` in
   `app/src/plotting.py`), labeled `"{loc_code} [{date_min}->{date_max}]"`
   via the new `_format_date_range` helper. Locations with a single category
   are unaffected (plain `loc_code` legend entry, unchanged from before the
   whole ENTITY_ID-splitting feature).

114→115 tests added/passing, `PYTHONPATH=. pytest test/` all green. Not yet
confirmed live in-browser by the user as of this handoff - if you're picking
this up and that hasn't happened yet, check with the user before assuming
these are fully closed.

---

## Next step 1: clustering workflow feeding into "Create Group"

**Goal:** expose a clustering algorithm through the UI and let its output
auto-generate a custom group, instead of (or in addition to) the current
manual lasso-select-then-name-a-category workflow.

**Not yet designed - needs a decision with the user before building:**

- **Which algorithm(s)?** `scikit-learn==1.4.1.post1` is already a pinned
  dependency (`app/requirements.txt`, used today for `PCA` in
  `dimension_reduction_functions.py`) - `KMeans`, `DBSCAN`,
  `AgglomerativeClustering` etc. are all available with **zero new
  dependencies**. Worth confirming with the user whether they want one
  algorithm to start (KMeans is the simplest UX: just "how many clusters?")
  or a chooser between a couple.
- **What feature space does it cluster on?** Candidates, in roughly
  increasing complexity:
  - The already-computed `PC1`/`PC2` (or `PMAP1`/`PMAP2`) biplot
    coordinates (`working-data` store) - cheapest, reuses data already on
    screen, but only 2D and tied to whichever biplot the user last ran.
  - The full selected-analyte feature matrix that fed PCA/PaCMAP
    (`cols_numeric_simple`/`cols_numeric_clr`, CLR-transformed via
    `compositional_data_functions.clr_transform_scale` the same way
    `dimension_reduction_functions.py` already does) - more faithful
    clustering, more design work to wire the same feature-selection state
    into a new callback.
  - Raw analyte columns, no CLR/scaling - probably wrong for compositional
    water-quality data, flag if suggested.

  Recommend starting from the PCA/PaCMAP coordinates already in
  `working-data` (least new plumbing) unless the user specifically wants
  full-feature-space clustering.

- **How does a cluster result become a custom group?** The existing manual
  flow is: lasso on map/plot → `populate_custom_group_from_selection`
  (`app/app.py:~896`) pre-fills `custom-group-draft` → repeat per category →
  `commit_category_to_draft` (`app/app.py:~1023`) appends
  `{category_name: [entity_ids]}` → `custom-group-modal`'s finalize callback
  (`app/app.py:~1043`, look for `Output("custom-group-draft", ...,
  allow_duplicate=True)` near there) calls `SessionManager.add_custom_group`
  to actually create the column. The cleanest integration is almost
  certainly: run clustering → build the same
  `{f"Cluster {label}": [entity_ids...]}` shape (keyed by whatever
  `cols_key_meta["entity_id"]` is, same as the manual flow's `customdata`
  values) → write it straight into `custom-group-draft` → let the user
  review/rename before hitting the existing "Finalize" button, rather than
  bypassing the draft/review step entirely. Reusing the draft step for free
  gets you the existing preview UI and the existing
  `SessionManager.add_custom_group` column-creation logic without touching
  either.
- **UI surface:** a new control (button + n_clusters/eps input, or an
  "Auto-cluster" tab/section inside the existing `custom-group-modal`
  offcanvas) is needed to trigger this - not designed yet.
- **Noise/outlier points:** DBSCAN-style algorithms produce a "noise" label
  (-1) - decide whether those become their own category, get dropped from
  the draft, or block finalize until the user manually reassigns them.

**Suggested first slice:** KMeans only, clustering on the current
`working-data` PC1/PC2 (or PMAP1/PMAP2, whichever biplot is showing) with a
single "number of clusters" input, writing straight into
`custom-group-draft` for the user to review/rename before finalizing. Small
enough to ship and validate the integration pattern before adding more
algorithms/feature-space options.

---

## Next step 2: UI/UX - plots shrink when legend names get long

**Symptom:** the new `"{loc_code} [{date_min}->{date_max}]"` legend labels
(this session's Task 2 fix, see summary above) are long. Plotly's default
legend layout eats into the plotting area's width to fit long entries,
making the actual PCA/PaCMAP biplot visibly smaller whenever a location
splits into per-category sub-traces.

**Not investigated yet - options to weigh, roughly in increasing effort:**

- **Shorten the label.** E.g. just the date range without the location
  prefix inside the legend if the location is already visually obvious from
  proximity, or truncate/abbreviate the date format
  (`2023-01-01` → `01/23`), or drop to year-only when the split is
  infrequent enough that day-level precision isn't the point of the label.
- **Cap legend width and let it wrap/truncate instead of stealing plot
  width.** `plotly.graph_objects.Layout.legend` supports
  `entrywidth`/`entrywidthmode` to fix a max column width per entry
  (long labels would then wrap or truncate depending on
  `itemwidth`/`tracegroupgap` settings - needs experimentation) instead of
  auto-sizing to the longest label.
  See `plotly` legend layout docs (`fig.update_layout(legend=dict(...))`)
  - `make_base_scatter_plot`/`make_fig_pca`/`make_fig_pmap` in
    `app/src/plotting.py` already set `fig_height_px_plot`/
    `fig_width_px_plot` (module-level constants) and `xaxis`/`yaxis`
    `range=[...]` explicitly (not autorange), so the plot's *data* area
    is already fixed-size in principle - confirm whether the shrinkage is
    actually the legend eating into that fixed `width`, or Plotly
    overriding the fixed width to make room, before picking a fix.
- **Move the legend below/beside in a way that doesn't compete for the
  same axis** - e.g. `legend=dict(orientation="h", ...)` at the bottom
  (already done for the *map* in `plotting.make_map`, not for
  `make_base_scatter_plot`'s PCA/PaCMAP figures) so it wraps across full
  width instead of squeezing the plot horizontally. Worth trying first
  since it's a small, localized change and there's already a working
  precedent for it elsewhere in this same file.
- **Separate legend panel entirely** (a `dbc.Offcanvas`-style side list,
  similar to the color-picker panel) if in-figure legend layout tuning
  isn't enough - much bigger effort, only worth it if the simpler options
  are tried and insufficient.

**Suggested first slice:** try the horizontal-bottom-legend approach (same
pattern `make_map` already uses) on `make_base_scatter_plot` first - lowest
effort, and there's already a working reference implementation two
functions above it in the same file. Fall back to `entrywidth`/truncation
tuning if that alone doesn't recover enough plot area.

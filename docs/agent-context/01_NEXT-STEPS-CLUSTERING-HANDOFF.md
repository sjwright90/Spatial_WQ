# Handoff: next steps after the selectable-PC biplot extension

## Quick summary of what was just fixed

Selectable Principal Components on the PCA biplot landed and are merged to
`main` (see the now-deleted `00_NEXT-STEPS-PCA-BIPLOT-EXTENSION-HANDOFF.md`
for the original spec). In short:

- `dimension_reduction_functions.run_pca` now computes up to
  `MAX_PCA_COMPONENTS` (5, capped by available analytes/samples) instead of
  a hardcoded 2, and `make_df_for_biplot` keeps all of them.
- `plotting.make_fig_pca` takes an arbitrary `x_col`/`y_col` component pair
  and labels each axis with *that* component's own explained variance
  (`_component_explained_variance`), not always `expl_var[0]`/`[1]`.
- `DataPlotter.plot_pca(x_col, y_col)` (`data_manager.py`) plumbs the
  selection through; `pca_component_options()` lists whatever PCs were
  actually computed.
- New `pca-x-component`/`pca-y-component` dropdowns in `home.py`, populated
  by a new `app.py` callback keyed off `working-data` (keeps the current
  selection if still valid, else defaults to PC1/PC2). `plot_data` now
  takes both as `Input`s.
- UI layout: Apply button + "Select number of neighbors"/"PCA X
  axis"/"PCA Y axis" dropdowns now render in one horizontal row
  (`apply_row` in `home.py`, `d-flex flex-row align-items-end`) instead of
  stacked.
- `CLAUDE.md`/`GOTCHAS.md`/`codebase-map.md` updated to match (PC1/PC2 is
  no longer hardcoded in `plotting.py`; also scrubbed several dead
  `REFACTOR-HANDOFF.md` references that pointed at a file that never
  existed in repo history).

120 tests passing (`PYTHONPATH=. pytest test/`), plus a user smoke test in
the running app - confirmed working.

---
## Next step: clustering workflow feeding into "Create Group"

**Goal:** expose a clustering algorithm through the UI and let its output
auto-generate a custom group, in addition to the current
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
  - The already-computed `PC1`/`PC2`* biplot
    coordinates (`working-data` store) - cheapest, reuses data already on
    screen, but only 2D and tied to whichever biplot the user last ran.*
  - The full selected-analyte feature matrix that fed PCA/PaCMAP
    (`cols_numeric_simple`/`cols_numeric_clr`, CLR-transformed via
    `compositional_data_functions.clr_transform_scale` the same way
    `dimension_reduction_functions.py` already does) - more faithful
    clustering, more design work to wire the same feature-selection state
    into a new callback.
  - Subset of `PC[x]` scores as chosen by user. Possibly use an explained variance 
    cumsum threshold to slice.*
  - Pipeline: best architecture would be to use a custom sklearn pipeline to facilitate
    clustering. column transformer->preprocessor(scale if needed, see PC WARNING below)->
    clustering algorithm. All run against pd.DataFrame object to preserve column labels.
    Exportable as binary with joblib/pickle
  - *PC WARNING: for plot PCs are scaled so as not to mask the loading vectors.
    If PC scaling used ensure a version of hte PC scores is captured and preserved
    BEFORE any scaling is done (PCs should not be scaled/normalized since the range 
    of values recorded in components directly correspond to explained variance; e.g. 
    PC1 should have a larger range than PC5 b/c it is more important)
    

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

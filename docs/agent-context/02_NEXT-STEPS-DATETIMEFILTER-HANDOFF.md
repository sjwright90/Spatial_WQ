# Handoff: next steps after the custom-category-color bug fixes

## Quick summary of what was just fixed

Two more increments landed on top of the custom-category-color bug fixes,
both on `feature/selectable-pca-components` (not yet merged to `main`):

**Selectable PCA biplot axes** (see now-deleted
`00_NEXT-STEPS-PCA-BIPLOT-EXTENSION-HANDOFF.md` for the original spec):

- `dimension_reduction_functions.run_pca` computes up to `MAX_PCA_COMPONENTS`
  (5, capped by available analytes/samples) instead of a hardcoded 2.
- `plotting.make_fig_pca`/`DataPlotter.plot_pca` take an arbitrary
  `x_col`/`y_col` component pair, each axis labeled with its own explained
  variance - PC1/PC2 are no longer hardcoded in `plotting.py`.
- New `pca-x-component`/`pca-y-component` dropdowns in `home.py`
  (`apply_row`, one horizontal row with the Apply button and neighbor-count
  dropdown), populated/kept-in-sync by a new `app.py` callback keyed off
  `working-data`.

**KMeans auto-cluster workflow** (see now-deleted
`01_NEXT-STEPS-CLUSTERING-HANDOFF.md` for the original spec/design
questions):

- New `app/src/clustering_functions.py` (`process_clustering`): subsets to
  the analytes/locations last `Apply`'d to the PCA/PaCMAP plots (mirroring
  `process_dimension_reduction`'s subset/CLR-transform steps), then clusters
  with `sklearn.cluster.KMeans` on a user-chosen feature space - `"clr"`
  (the CLR-transformed analyte matrix) or `"pca"` (unscaled PCA scores over
  all computed components, via `build_pca_feature_matrix` - deliberately
  *not* the min-max-scaled scores `make_df_for_biplot` produces for the
  biplot, since that scaling would distort each component's
  variance-proportional range before clustering on it; see the PC WARNING in
  the now-deleted clustering handoff for the full rationale).
- New "Run Clustering" callback in `app.py`
  (`run_clustering_into_draft`) writes the resulting
  `{f"Cluster {label}": [entity_id, ...]}` categories straight into
  `custom-group-draft`, **replacing** any existing draft, reusing the
  existing manual-flow review/rename/Finalize UI and
  `SessionManager.add_custom_group` column-creation logic unchanged.
- New "Auto-cluster (KMeans)" section (feature-space dropdown + n-clusters
  input + button) inside the existing `custom-group-modal` offcanvas in
  `home.py`, alongside the manual lasso-select workflow rather than
  replacing it.
- Algorithm scope for this first slice is KMeans only (no DBSCAN/noise-label
  handling) - see the deleted handoff if a second algorithm is wanted later.
- `CLAUDE.md`/`codebase-map.md` updated to match.

128 tests passing (`PYTHONPATH=. pytest test/`); no user smoke test yet for
the clustering workflow specifically.

---

## Next step: DATETIME FILTER - Require a datetime filter to mask data frame prior to dimension reduction

**Feature:** existing datetime range selector (slider beneath plot) only masks calculated PCA/PaCMAP
datasets prior to plotting. Existing datetime range selector **does not** filter data prior to
Scaler->PCA/PacMAP (dimension reduction pipeline) calculations, thus never changing the variance of the system.
**Require** a new datetime range selecter which acts on the dataset prior to dimension reduction pipeline.

**Solution identified - implementation not determined:**

- **Include date range slider or entry boxes in left pop-out ["Plot filters"].**
  E.g. use existing placeholder "DATE GROUPING COMING SOON" for date range slider
  or two entr/dropdown boxes.
  Cleaner separation of "filter" and "mask" datetime range sliders.
  More wiring but long term benefit.

**Downstream considerations**
- Fundamentally changing the dataset prior to processing by an external filter
  (datetime less obvious that highlight select used in visual plot tools) requires
  ample user notificaiton and tracking.
- Include a clear indicator (*where?*) that data is filtered by datetime
- Include easy *Reset* button near datetime manipulator
- **ESSENTIAL CONSIDERATIONS**:
  - What is the impact on downstream custom group creation
  - What is the impact on downstream clustering+
    - +: clustering re-runs PCA pipeline when using PCA scores for clustering
      b/c PCA scores generated for plotting are scaled for visual purposes
      ensure this implementation of PCA scores is filtered
      - *Optional*: consider calculating a "PCA for clustering" separately
        when "Apply" is run and storing in session memory for downstream clustering.
        Running PCA is very cheap, so only consider if easy to wire.
  - In both cases how does export work?
    - **Proposed**: export ENTIRE data frame with clear notation
      in date filtered rows that they were filtered. E.g.:
      LocID, Date, Cluster_group_0
      0000,1900-01-01,DATE-FILTERED-[DATEMIN->DATEMAX]
      0001,1910-01-01,Cluster_0
      0002,1950-01-01,Cluster_1
      0004,1970-01-01,DATE-FILTERED-[DATEMIN->DATEMAX]
- **Language:** refer to the two types of datetime selecting separately
  - Proposed:
    - **Filter:** datetime selection applied UPSTREAM of dimension reduction pipeline
    - **Mask:** datetime selection applied DOWNSTREAM of dimension reduction pipeline
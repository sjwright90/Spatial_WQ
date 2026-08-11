# Handoff: next steps after the custom-category-color bug fixes

## Quick summary of what was just fixed

**TO BE FILLED OUT AFTER @docs/agent-context/NEXT-STEPS-PCA-BIPLOT-EXTENSION-HANDOFF.md and NEXT-STEPS-CLUSTERING-HANDOFF.md complete**


---

## Next step: UI/UX - plots shrink when legend names get long

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

**Suggested first slice:** try the `entrywidth`/truncation
tuning.

import unittest
import pandas as pd
import numpy as np
from plotly.graph_objects import Figure

from app.src.plotting import (
    empty_fig,
    make_map,
    PlotContext,
    _find_axis_limits,
    _generate_text,
    make_base_scatter_plot,
    _annotate_loadings,
    make_fig_pmap,
    make_fig_pca,
    _DEFAULT_COLOR,
    _DEFAULT_MARKER_SYMBOL,
    _wrap_legend_label,
)


class TestPlottingFunctions(unittest.TestCase):
    def setUp(self):
        # Sample data for testing
        self.df = pd.DataFrame(
            {
                "LATITUDE": [34.05, 36.16],
                "LONGITUDE": [-118.24, -115.15],
                "LOC_ID": ["Site1", "Site2"],
                "MAP-MARKER-SIZE": [10, 20],
                "color": ["A", "B"],
                "PMAP1": [1.0, 2.0],
                "PMAP2": [3.0, 4.0],
                "PC1": [0.5, 0.7],
                "PC2": [0.2, 0.4],
                "PrimaryDomain": ["Domain1", "Domain2"],
                "SecondaryDomain": ["SubDomain1", "SubDomain2"],
                "Date": ["2023-01-01", "2023-01-02"],
            }
        )
        self.ldg_df = pd.DataFrame(
            {
                "PC1": [0.1, 0.2],
                "PC2": [0.3, 0.4],
                "metals": ["Metal1", "Metal2"],
            }
        )
        self.dict_color_map_primary = {"Domain1": "red", "Domain2": "blue"}
        self.dict_color_map_secondary = {"SubDomain1": "green", "SubDomain2": "yellow"}
        self.name_marker_map = {"Site1": 1, "Site2": 2}
        self.expl_var = [0.6, 0.4]

    def _make_ctx(self, **overrides) -> PlotContext:
        defaults = dict(
            col_loc_id="LOC_ID",
            col_primary_domain="PrimaryDomain",
            col_secondary_domain="SecondaryDomain",
            col_date="Date",
            dict_color_map_primary=self.dict_color_map_primary,
            dict_color_map_secondary=self.dict_color_map_secondary,
            name_marker_map=self.name_marker_map,
        )
        defaults.update(overrides)
        return PlotContext(**defaults)

    def test_empty_fig(self):
        fig = empty_fig()
        self.assertIsInstance(fig, Figure)

    def test_make_map(self):
        fig = make_map(self.df, lat="LATITUDE", lon="LONGITUDE", color="color")
        self.assertIsInstance(fig, Figure)
        self.assertEqual(fig.data[0].type, "scattermap")

    def test_find_axis_limits(self):
        x_min, x_max, y_min, y_max = _find_axis_limits(self.df, "PMAP1", "PMAP2")
        self.assertAlmostEqual(x_min, 0.9)
        self.assertAlmostEqual(x_max, 2.1)
        self.assertAlmostEqual(y_min, 2.9)
        self.assertAlmostEqual(y_max, 4.1)

    def test_wrap_legend_label_breaks_at_space_when_bracket_part_fits(self):
        label = "SITE-01 [2023-06-15]"
        wrapped = _wrap_legend_label(label, max_len=15)
        self.assertEqual(wrapped, "SITE-01<br>[2023-06-15]")

    def test_wrap_legend_label_falls_back_to_arrow_break(self):
        label = "SITE-01 [2023-01-01->2023-06-15]"
        wrapped = _wrap_legend_label(label, max_len=20)
        self.assertEqual(wrapped, "SITE-01<br>[2023-01-01-><br>2023-06-15]")
        # "->" stays intact, attached to the end of the first line - never
        # split into "-" and ">" on separate lines.
        self.assertIn("->", wrapped.split("<br>")[1])

    def test_wrap_legend_label_never_fractures_a_token(self):
        # loc_code alone exceeds max_len - left intact on its own
        # (over-length) line rather than hard-split mid-token.
        label = "VERY-LONG-LOCATION-ID-0001 [2023-01-01->2023-06-15]"
        wrapped = _wrap_legend_label(label, max_len=20)
        lines = wrapped.split("<br>")
        self.assertEqual(lines[0], "VERY-LONG-LOCATION-ID-0001")
        for line in lines:
            self.assertNotIn(" ", line.strip())  # no stray mid-token breaks

    def test_wrap_legend_label_single_date_no_arrow_left_unbroken(self):
        # No "->" to break on if start/end date collapse to one date
        # (_format_date_range's single-date case) - can't split further
        # without fracturing the date, so the bracket part stays on one
        # (possibly over-length) line.
        label = "SITE-01 [2023-06-15]"
        wrapped = _wrap_legend_label(label, max_len=10)
        self.assertEqual(wrapped, "SITE-01<br>[2023-06-15]")

    def test_wrap_legend_label_short_label_unchanged(self):
        label = "Site1"
        self.assertEqual(_wrap_legend_label(label, max_len=20), label)

    def test_wrap_legend_label_unrecognized_shape_unchanged(self):
        label = "not-a-legend-label-shape"
        self.assertEqual(_wrap_legend_label(label, max_len=10), label)

    def test_generate_text(self):
        texts = _generate_text("Site1", self.df, "PrimaryDomain", "SecondaryDomain", "Date")
        self.assertEqual(len(texts), len(self.df))
        self.assertIn("<b>Site1</b><br><b>Primary Domain:</b>", texts[0])
        self.assertIn("<b>Secondary Domain:</b>", texts[0])

    def test_generate_text_same_domain_omits_secondary(self):
        # primary_domain and secondary_domain resolve to the same value for
        # every row - the "Secondary Domain" line should be dropped, not
        # repeated.
        df = self.df.copy()
        df["SecondaryDomain"] = df["PrimaryDomain"]
        texts = _generate_text("Site1", df, "PrimaryDomain", "SecondaryDomain", "Date")
        self.assertNotIn("Secondary Domain", texts[0])
        self.assertIn("<b>Site1</b><br><b>Primary Domain:</b>", texts[0])

    def test_make_base_scatter_plot(self):
        fig = make_base_scatter_plot(
            df=self.df,
            ctx=self._make_ctx(),
            x_col="PMAP1",
            y_col="PMAP2",
            x_label="X Axis",
            y_label="Y Axis",
        )
        self.assertIsInstance(fig, Figure)

    def test_make_base_scatter_plot_customdata_defaults_to_loc_id(self):
        # No col_entity_id passed - customdata should still be populated,
        # falling back to loc_id for both columns.
        fig = make_base_scatter_plot(
            df=self.df,
            ctx=self._make_ctx(),
            x_col="PMAP1",
            y_col="PMAP2",
            x_label="X Axis",
            y_label="Y Axis",
        )
        for trace in fig.data:
            for row in trace.customdata:
                self.assertEqual(row[0], row[1])

    def test_make_base_scatter_plot_collapses_repeat_visits_by_location(self):
        df = pd.concat([self.df, self.df], ignore_index=True)
        df["ENTITY_ID"] = [
            "Site1_2023-01-01",
            "Site2_2023-01-02",
            "Site1_2023-06-01",
            "Site2_2023-06-02",
        ]
        fig = make_base_scatter_plot(
            df=df,
            ctx=self._make_ctx(col_entity_id="ENTITY_ID"),
            x_col="PMAP1",
            y_col="PMAP2",
            x_label="X Axis",
            y_label="Y Axis",
        )
        # One trace per location - legend does not explode per sample/date.
        self.assertEqual(len(fig.data), 2)
        trace_site1 = next(t for t in fig.data if t.name == "Site1")
        self.assertEqual(len(trace_site1.x), 2)
        self.assertEqual(
            [row[1] for row in trace_site1.customdata],
            ["Site1_2023-01-01", "Site1_2023-06-01"],
        )

    def test_make_base_scatter_plot_splits_by_category_within_location(self):
        # Same LOC_ID, but two ENTITY_ID rows (different dates) assigned to
        # different PrimaryDomain categories - the location must be split
        # into per-category sub-traces (correct color/hover per point),
        # each getting its own legend entry (loc_code [date_range]) since a
        # bare "Site1" name would otherwise be ambiguous between them.
        df = pd.concat([self.df, self.df], ignore_index=True)
        df["ENTITY_ID"] = [
            "Site1_2023-01-01",
            "Site2_2023-01-02",
            "Site1_2023-06-01",
            "Site2_2023-06-02",
        ]
        # Second visit to Site1 belongs to a different category than the
        # first; Site2's two visits stay in the same category.
        df.loc[2, "PrimaryDomain"] = "Domain2"
        df.loc[2, "SecondaryDomain"] = "SubDomain2"
        df.loc[2, "Date"] = "2023-06-01"
        self.dict_color_map_primary["Domain2"] = "blue"
        self.dict_color_map_secondary["SubDomain2"] = "yellow"

        fig = make_base_scatter_plot(
            df=df,
            ctx=self._make_ctx(col_entity_id="ENTITY_ID"),
            x_col="PMAP1",
            y_col="PMAP2",
            x_label="X Axis",
            y_label="Y Axis",
        )

        site1_traces = [t for t in fig.data if t.name.startswith("Site1")]
        # Split into two sub-traces (one per category) ...
        self.assertEqual(len(site1_traces), 2)
        # ... each with its own legend entry, distinguished by date range.
        self.assertTrue(all(t.showlegend is not False for t in site1_traces))
        self.assertEqual(
            {t.name for t in site1_traces},
            {"Site1 [2023-01-01]", "Site1 [2023-06-01]"},
        )
        colors = {t.marker.color for t in site1_traces}
        self.assertEqual(colors, {"red", "blue"})
        entity_ids = sorted(row[1] for t in site1_traces for row in t.customdata)
        self.assertEqual(entity_ids, ["Site1_2023-01-01", "Site1_2023-06-01"])

        # Site2's two visits share a category - still a single sub-trace,
        # plain loc_code legend entry (no split, no date-range suffix).
        site2_traces = [t for t in fig.data if t.name == "Site2"]
        self.assertEqual(len(site2_traces), 1)
        self.assertEqual(len(site2_traces[0].x), 2)

    def test_make_base_scatter_plot_falls_back_to_defaults_on_missing_group(self):
        # PrimaryDomain/SecondaryDomain/loc_id values with no entry in the
        # lookup dicts should degrade to the default color/marker (and log a
        # warning) rather than raising.
        ctx = self._make_ctx(
            dict_color_map_primary={},
            dict_color_map_secondary={},
            name_marker_map={},
        )
        with self.assertLogs("wq_spatial_app.app.src.plotting", level="WARNING"):
            fig = make_base_scatter_plot(
                df=self.df,
                ctx=ctx,
                x_col="PMAP1",
                y_col="PMAP2",
                x_label="X Axis",
                y_label="Y Axis",
            )
        for trace in fig.data:
            self.assertEqual(trace.marker.color, _DEFAULT_COLOR)
            self.assertEqual(trace.marker.symbol, _DEFAULT_MARKER_SYMBOL)

    def test_annotate_loadings(self):
        fig = empty_fig()
        fig = _annotate_loadings(self.ldg_df, fig, "PC1", "PC2")
        self.assertIsInstance(fig, Figure)

    def test_make_fig_pmap(self):
        fig = make_fig_pmap(df=self.df, ctx=self._make_ctx())
        self.assertIsInstance(fig, Figure)

    def test_make_fig_pca(self):
        fig = make_fig_pca(
            df_pca=self.df,
            ldg_df=self.ldg_df,
            expl_var=self.expl_var,
            ctx=self._make_ctx(),
        )
        self.assertIsInstance(fig, Figure)

    def test_make_fig_pca_selectable_component_pair(self):
        # PC1 vs PC3 (not the PC1/PC2 default) must plot the right columns
        # and label each axis with *its own* component's explained variance,
        # not always expl_var[0]/[1].
        df = self.df.copy()
        df["PC3"] = [1.1, 1.3]
        ldg_df = self.ldg_df.copy()
        ldg_df["PC3"] = [0.5, 0.6]
        expl_var = [0.6, 0.3, 0.1]
        fig = make_fig_pca(
            df_pca=df,
            ldg_df=ldg_df,
            expl_var=expl_var,
            ctx=self._make_ctx(),
            x_col="PC1",
            y_col="PC3",
        )
        self.assertIn("10.00%", fig.layout.yaxis.title.text)
        self.assertIn("PC3", fig.layout.yaxis.title.text)
        self.assertTrue(all(trace.y[0] in df["PC3"].values for trace in fig.data))


if __name__ == "__main__":
    unittest.main()

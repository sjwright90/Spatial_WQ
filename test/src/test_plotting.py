import unittest
import pandas as pd
import numpy as np
from plotly.graph_objects import Figure

from app.src.plotting import (
    empty_fig,
    make_map,
    find_axis_limits,
    generate_text,
    make_base_scatter_plot,
    annotate_loadings,
    make_fig_pmap,
    make_fig_pca,
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

    def test_empty_fig(self):
        fig = empty_fig()
        self.assertIsInstance(fig, Figure)

    def test_make_map(self):
        fig = make_map(self.df, lat="LATITUDE", lon="LONGITUDE", color="color")
        self.assertIsInstance(fig, Figure)

    def test_find_axis_limits(self):
        x_min, x_max, y_min, y_max = find_axis_limits(self.df, "PMAP1", "PMAP2")
        self.assertAlmostEqual(x_min, 0.9)
        self.assertAlmostEqual(x_max, 2.1)
        self.assertAlmostEqual(y_min, 2.9)
        self.assertAlmostEqual(y_max, 4.1)

    def test_generate_text(self):
        texts = generate_text(
            "Site1", self.df, "PrimaryDomain", "SecondaryDomain", "Date"
        )
        self.assertEqual(len(texts), len(self.df))
        self.assertIn("<b>Site1</b><br><b>Primary Domain:</b>", texts[0])

    def test_make_base_scatter_plot(self):
        fig = make_base_scatter_plot(
            df=self.df,
            dict_color_map_primary=self.dict_color_map_primary,
            dict_color_map_secondary=self.dict_color_map_secondary,
            name_marker_map=self.name_marker_map,
            col_loc_id="LOC_ID",
            col_primary_domain="PrimaryDomain",
            col_secondary_domain="SecondaryDomain",
            col_date="Date",
            x_col="PMAP1",
            y_col="PMAP2",
            title="Test Plot",
            x_label="X Axis",
            y_label="Y Axis",
        )
        self.assertIsInstance(fig, Figure)

    def test_annotate_loadings(self):
        fig = empty_fig()
        fig = annotate_loadings(self.ldg_df, fig, "PC1", "PC2")
        self.assertIsInstance(fig, Figure)

    def test_make_fig_pmap(self):
        fig = make_fig_pmap(
            df=self.df,
            dict_color_map_primary=self.dict_color_map_primary,
            dict_color_map_secondary=self.dict_color_map_secondary,
            name_marker_map=self.name_marker_map,
            col_loc_id="LOC_ID",
            col_primary_domain="PrimaryDomain",
            col_secondary_domain="SecondaryDomain",
            col_date="Date",
        )
        self.assertIsInstance(fig, Figure)

    def test_make_fig_pca(self):
        fig = make_fig_pca(
            df_pca=self.df,
            ldg_df=self.ldg_df,
            expl_var=self.expl_var,
            dict_color_map_primary=self.dict_color_map_primary,
            dict_color_map_secondary=self.dict_color_map_secondary,
            name_marker_map=self.name_marker_map,
            col_loc_id="LOC_ID",
            col_primary_domain="PrimaryDomain",
            col_secondary_domain="SecondaryDomain",
            col_date="Date",
        )
        self.assertIsInstance(fig, Figure)


if __name__ == "__main__":
    unittest.main()

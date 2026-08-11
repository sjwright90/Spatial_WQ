import unittest
import pandas as pd
from app.src.dimension_reduction_functions import (
    process_dimension_reduction,
    run_pca,
    MAX_PCA_COMPONENTS,
)


class TestProcessDimensionReduction(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            {
                "Site_Name": ["1", "2", "3"],
                "Group": ["A", "B", "A"],
                "Copper": [1.0, 2.0, 3.0],
                "Zinc": [4.0, 5.0, 6.0],
            }
        )

    def test_empty_feature_selection_raises_clear_error(self):
        # Regression test: an empty feature_selection used to propagate into
        # PCA(...).fit_transform(df[[]]) and fail deep inside sklearn with a
        # confusing error - it must now raise a clear ValueError up front.
        with self.assertRaises(ValueError):
            process_dimension_reduction(
                self.df,
                "Site_Name",
                ["Group"],
                ["Copper", "Zinc"],
                [],
                feature_selection=[],
                loc_id_selection=["1", "2", "3"],
                n_neighbors=2,
            )


class TestRunPcaComponentCount(unittest.TestCase):
    """Selectable PC-pair plotting (PC1 vs PC3, etc.) needs run_pca to
    compute more than 2 components whenever the data supports it."""

    def setUp(self):
        # 6 analytes, 6 samples -> enough for MAX_PCA_COMPONENTS (5).
        self.analytes = ["A", "B", "C", "D", "E", "F"]
        self.df = pd.DataFrame(
            {a: [1.0, 2.0, 3.0, 4.0, 5.0, 6.0][::-1] if i % 2 else [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
             for i, a in enumerate(self.analytes)}
        )
        self.df["Group"] = ["A", "B", "A", "B", "A", "B"]

    def test_computes_more_than_two_components_when_data_supports_it(self):
        df_plot, ldg_df, expl_var = run_pca(self.df, ["Group"], self.analytes)
        pc_cols = [c for c in ldg_df.columns if c != "metals"]
        self.assertEqual(len(pc_cols), MAX_PCA_COMPONENTS)
        self.assertEqual(len(expl_var), MAX_PCA_COMPONENTS)
        self.assertIn("PC3", df_plot.columns)
        self.assertIn("PC5", df_plot.columns)

    def test_caps_at_available_features_and_samples(self):
        # Only 2 analytes/3 samples available - n_components must be capped,
        # not raise from sklearn asking for more components than features.
        small_df = self.df[["A", "B", "Group"]].iloc[:3]
        df_plot, ldg_df, expl_var = run_pca(small_df, ["Group"], ["A", "B"])
        pc_cols = [c for c in ldg_df.columns if c != "metals"]
        self.assertEqual(len(pc_cols), 2)
        self.assertEqual(len(expl_var), 2)


if __name__ == "__main__":
    unittest.main()

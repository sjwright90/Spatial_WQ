import unittest
import pandas as pd
from app.src.clustering_functions import (
    process_clustering,
    build_pca_feature_matrix,
    FEATURE_SPACE_CLR,
    FEATURE_SPACE_PCA,
)
from app.src.compositional_data_functions import clr_transform_scale


def _make_df(n_groups: int = 3, n_per_group: int = 4) -> pd.DataFrame:
    # Two clearly separated clusters in Copper/Zinc space, `n_groups` repeats
    # of a small offset so KMeans has an unambiguous partition to recover.
    rows = []
    loc_id = 0
    for g in range(n_groups):
        offset = g * 100
        for _ in range(n_per_group):
            loc_id += 1
            rows.append(
                {
                    "Site_Name": str(loc_id),
                    "Entity_Id": f"e{loc_id}",
                    "Group": "A",
                    "Copper": 1.0 + offset,
                    "Zinc": 2.0 + offset,
                    "Lead": 3.0 + offset,
                }
            )
    return pd.DataFrame(rows)


class TestProcessClusteringValidation(unittest.TestCase):
    def setUp(self):
        self.df = _make_df()
        self.loc_ids = self.df["Site_Name"].tolist()

    def test_empty_feature_selection_raises(self):
        with self.assertRaises(ValueError):
            process_clustering(
                self.df,
                "Site_Name",
                "Entity_Id",
                ["Copper", "Zinc", "Lead"],
                [],
                feature_selection=[],
                loc_id_selection=self.loc_ids,
                feature_space=FEATURE_SPACE_CLR,
                n_clusters=3,
            )

    def test_empty_loc_id_selection_raises(self):
        with self.assertRaises(ValueError):
            process_clustering(
                self.df,
                "Site_Name",
                "Entity_Id",
                ["Copper", "Zinc", "Lead"],
                [],
                feature_selection=["Copper", "Zinc", "Lead"],
                loc_id_selection=[],
                feature_space=FEATURE_SPACE_CLR,
                n_clusters=3,
            )

    def test_unknown_feature_space_raises(self):
        with self.assertRaises(ValueError):
            process_clustering(
                self.df,
                "Site_Name",
                "Entity_Id",
                ["Copper", "Zinc", "Lead"],
                [],
                feature_selection=["Copper", "Zinc", "Lead"],
                loc_id_selection=self.loc_ids,
                feature_space="tsne",
                n_clusters=3,
            )

    def test_n_clusters_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            process_clustering(
                self.df,
                "Site_Name",
                "Entity_Id",
                ["Copper", "Zinc", "Lead"],
                [],
                feature_selection=["Copper", "Zinc", "Lead"],
                loc_id_selection=self.loc_ids,
                feature_space=FEATURE_SPACE_CLR,
                n_clusters=1,
            )
        with self.assertRaises(ValueError):
            process_clustering(
                self.df,
                "Site_Name",
                "Entity_Id",
                ["Copper", "Zinc", "Lead"],
                [],
                feature_selection=["Copper", "Zinc", "Lead"],
                loc_id_selection=self.loc_ids,
                feature_space=FEATURE_SPACE_CLR,
                n_clusters=len(self.df) + 1,
            )


class TestProcessClusteringOutput(unittest.TestCase):
    def setUp(self):
        self.df = _make_df(n_groups=3, n_per_group=4)
        self.loc_ids = self.df["Site_Name"].tolist()

    def test_clr_feature_space_recovers_partition(self):
        result = process_clustering(
            self.df,
            "Site_Name",
            "Entity_Id",
            ["Copper", "Zinc", "Lead"],
            [],
            feature_selection=["Copper", "Zinc", "Lead"],
            loc_id_selection=self.loc_ids,
            feature_space=FEATURE_SPACE_CLR,
            n_clusters=3,
        )
        self.assertEqual(list(result.columns), ["Entity_Id", "cluster"])
        self.assertEqual(len(result), len(self.df))
        self.assertEqual(result["cluster"].nunique(), 3)
        # Every well-separated group of 4 should land in a single cluster.
        for g in range(3):
            entity_ids = self.df.iloc[g * 4 : g * 4 + 4]["Entity_Id"]
            group_clusters = result[result["Entity_Id"].isin(entity_ids)]["cluster"]
            self.assertEqual(group_clusters.nunique(), 1)

    def test_pca_feature_space_recovers_partition(self):
        result = process_clustering(
            self.df,
            "Site_Name",
            "Entity_Id",
            ["Copper", "Zinc", "Lead"],
            [],
            feature_selection=["Copper", "Zinc", "Lead"],
            loc_id_selection=self.loc_ids,
            feature_space=FEATURE_SPACE_PCA,
            n_clusters=3,
        )
        self.assertEqual(result["cluster"].nunique(), 3)

    def test_original_df_not_mutated(self):
        original = self.df.copy()
        process_clustering(
            self.df,
            "Site_Name",
            "Entity_Id",
            ["Copper", "Zinc", "Lead"],
            [],
            feature_selection=["Copper", "Zinc", "Lead"],
            loc_id_selection=self.loc_ids,
            feature_space=FEATURE_SPACE_CLR,
            n_clusters=3,
        )
        pd.testing.assert_frame_equal(self.df, original)


class TestBuildPcaFeatureMatrixUnscaled(unittest.TestCase):
    """PC WARNING regression: clustering must use raw PCA scores, not the
    min-max-scaled scores the biplot uses - scaling would compress PC1's
    naturally wider (higher-explained-variance) range down to match PC5's."""

    def test_scores_are_not_min_max_scaled(self):
        df = _make_df(n_groups=3, n_per_group=4)
        analytes = ["Copper", "Zinc", "Lead"]
        df_clr = clr_transform_scale(df.copy(), analytes, [])
        pca_scores = build_pca_feature_matrix(df_clr, analytes)
        # A min-max-scaled column is bounded to roughly [0, 1]; raw PCA scores
        # on separated clusters should exceed that range.
        self.assertGreater(pca_scores["PC1"].max() - pca_scores["PC1"].min(), 1.0)


if __name__ == "__main__":
    unittest.main()

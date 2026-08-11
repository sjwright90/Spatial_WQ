import unittest
import pandas as pd
from app.src.dimension_reduction_functions import process_dimension_reduction


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


if __name__ == "__main__":
    unittest.main()

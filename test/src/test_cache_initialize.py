import unittest
import pandas as pd
from app.src.cache_initialize import (
    make_custom_cache_key_dimensionReduction,
    generate_df_hash_version,
)


class TestCacheInitialize(unittest.TestCase):
    def test_make_custom_cache_key_dimensionReduction(self):
        # Test with sample inputs
        kwargs = {
            "feature_selection": "PCA",
            "loc_id_selection": "Location_1",
            "n_neighbors": 5,
            "data_hash": "abc123",
        }
        expected_key = "PCA_Location_1_5_abc123"
        result = make_custom_cache_key_dimensionReduction(**kwargs)
        self.assertEqual(result, expected_key)

        # Test with missing keys
        kwargs = {
            "feature_selection": None,
            "loc_id_selection": None,
            "n_neighbors": None,
            "data_hash": None,
        }
        expected_key = "None_None_None_None"
        result = make_custom_cache_key_dimensionReduction(**kwargs)
        self.assertEqual(result, expected_key)

    def test_generate_df_hash_version(self):
        # Create a sample DataFrame
        data = {
            "A": [1, 2, 3],
            "B": [4, 5, 6],
        }
        df = pd.DataFrame(data)

        # Generate hash for the DataFrame
        hash1 = generate_df_hash_version(df)

        # Ensure the hash is consistent for the same DataFrame
        hash2 = generate_df_hash_version(df)
        self.assertEqual(hash1, hash2)

        # Ensure the hash changes when the DataFrame changes
        df_modified = df.copy()
        df_modified.loc[0, "A"] = 10
        hash3 = generate_df_hash_version(df_modified)
        self.assertNotEqual(hash1, hash3)

        # Ensure the hash is consistent even if the DataFrame is reordered
        df_reordered = df.sample(frac=1).reset_index(drop=True)
        hash4 = generate_df_hash_version(df_reordered)
        self.assertEqual(hash1, hash4)


if __name__ == "__main__":
    unittest.main()

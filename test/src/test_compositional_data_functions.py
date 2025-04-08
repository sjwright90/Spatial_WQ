import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from app.src.compositional_data_functions import (
    array_anynull,
    clr_transform,
    clr_transform_scale,
)


class TestCompositionalDataFunctions(unittest.TestCase):

    def test_array_anynull(self):
        # Test with no nulls
        data = np.array([[1.0, 2.0], [3.0, 4.0]])
        self.assertFalse(array_anynull(data))

        # Test with NaN values
        data_with_nan = np.array([[1, 2], [np.nan, 4]])
        self.assertTrue(array_anynull(data_with_nan))

    def test_clr_transform(self):
        # Test with valid data
        data = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        transformed = clr_transform(data)
        self.assertEqual(transformed.shape, data.shape)

        # Test with zeros in data
        data_with_zeros = np.array([[1.0, 0.0, 3.0], [4.0, 5.0, 6.0]])
        with self.assertRaises(ValueError):
            clr_transform(data_with_zeros)

        # Test with NaN in data
        data_with_nan = np.array([[1.0, np.nan, 3.0], [4.0, 5.0, 6.0]])
        with self.assertRaises(ValueError):
            clr_transform(data_with_nan)

    def test_clr_transform_scale(self):
        # Test with valid data
        df = pd.DataFrame(
            {"A": [1.0, 2.0, 3.0], "B": [4.0, 5.0, 6.0], "C": [7.0, 8.0, 9.0]}
        )
        cols_numeric_all = ["A", "B", "C"]
        cols_numeric_clr = ["A", "B"]
        transformed_df = clr_transform_scale(
            df.copy(), cols_numeric_all, cols_numeric_clr
        )

        # Ensure the transformed DataFrame has the same shape
        self.assertEqual(transformed_df.shape, df.shape)

        # Ensure the columns are transformed
        self.assertFalse(transformed_df.equals(df))

        # Test with zeros in CLR columns
        df_with_zeros = pd.DataFrame(
            {"A": [1.0, 0.0, 3.0], "B": [4.0, 5.0, 6.0], "C": [7.0, 8.0, 9.0]}
        )
        with self.assertRaises(ValueError):
            clr_transform_scale(df_with_zeros, cols_numeric_all, cols_numeric_clr)


if __name__ == "__main__":
    unittest.main()

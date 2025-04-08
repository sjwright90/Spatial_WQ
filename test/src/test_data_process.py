import unittest
import pandas as pd
from pandas.testing import assert_frame_equal
from datetime import datetime
import numpy as np

from app.src.data_process import (
    df_col_group_to_dict,
    get_key_cols_meta,
    make_color_dict,
    find_make_color_dict,
    make_plotting_group_color_dicts,
    set_key_col_date,
    get_key_cols_plot,
    rename_cols_analyte,
    extract_coordinate_dataframe,
    subset_df_locIds,
    subset_df_numericFeatures,
    pandas_to_json,
    json_to_pandas,
    pc_scaler,
)


class TestDataProcess(unittest.TestCase):

    def setUp(self):
        self.df = pd.DataFrame(
            {
                "LOCATION-ID_1": [1, 2, 3],
                "DATETIME": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "PLOTTING-GROUPS-DOMAIN-1_LABELS": ["A", "B", "A"],
                "MARKERS-PLOT-DOMAIN": [1, 2, 3],
                "LONGITUDE": [10.5, -20.0, 30.0],
                "LATITUDE": [50.0, 60.0, 70.1],
                "CLR-ANALYTE_X": [0.1, 0.2, 0.3],
                "NUMERIC-ANALYTE_Y": [1, 2, 3],
                "MAP-MARKER-SIZE": [10, 10, 10],
            }
        )
        self.df["DATETIME"] = pd.to_datetime(self.df["DATETIME"])

    def test_df_col_group_to_dict(self):
        result = df_col_group_to_dict(
            self.df, "PLOTTING-GROUPS-DOMAIN-1_LABELS", "LOCATION-ID_1"
        )
        expected = {"A": 1, "B": 2}
        self.assertEqual(result, expected)

    def test_get_key_cols_meta(self):
        result = get_key_cols_meta(self.df)
        expected = (
            "LOCATION-ID_1",
            "DATETIME",
            ["PLOTTING-GROUPS-DOMAIN-1_LABELS"],
            ["LONGITUDE", "LATITUDE"],
        )
        self.assertEqual(result, expected)

    def test_make_color_dict(self):
        result = make_color_dict(self.df, "PLOTTING-GROUPS-DOMAIN-1_LABELS")
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_find_make_color_dict(self):
        result = find_make_color_dict(self.df, "PLOTTING-GROUPS-DOMAIN-1_LABELS")
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_make_plotting_group_color_dicts(self):
        result = make_plotting_group_color_dicts(
            self.df, ["PLOTTING-GROUPS-DOMAIN-1_LABELS"]
        )
        self.assertIn("PLOTTING-GROUPS-DOMAIN-1_LABELS", result)

    def test_set_key_col_date(self):
        df = self.df.copy()
        result = set_key_col_date(df, "DATETIME")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["DATETIME"]))

    def test_get_key_cols_plot(self):
        result = get_key_cols_plot(self.df)
        expected = (
            [
                "DATETIME",
                "LATITUDE",
                "LOCATION-ID_1",
                "LONGITUDE",
                "MAP-MARKER-SIZE",
                "MARKERS-PLOT-DOMAIN",
                "PLOTTING-GROUPS-DOMAIN-1_LABELS",
            ],
            ["NUMERIC-ANALYTE_Y", "CLR-ANALYTE_X"],
            ["NUMERIC-ANALYTE_Y"],
            ["CLR-ANALYTE_X"],
        )
        self.assertEqual(result, expected)

    def test_rename_cols_analyte(self):
        df, (cols_all, cols_simple, cols_clr) = rename_cols_analyte(
            self.df,
            ["NUMERIC-ANALYTE_Y", "CLR-ANALYTE_X"],
            ["NUMERIC-ANALYTE_Y"],
            ["CLR-ANALYTE_X"],
        )
        self.assertIn("Y", df.columns)
        self.assertIn("X", df.columns)

    def test_extract_coordinate_dataframe(self):
        result = extract_coordinate_dataframe(
            self.df,
            ["PLOTTING-GROUPS-DOMAIN-1_LABELS"],
            "LOCATION-ID_1",
            "LONGITUDE",
            "LATITUDE",
        )
        self.assertEqual(result.shape[0], 3)

    def test_subset_df_locIds(self):
        result = subset_df_locIds(self.df, "LOCATION-ID_1", [1, 2])
        self.assertEqual(result.shape[0], 2)

    def test_subset_df_numericFeatures(self):
        result, cols_all, cols_clr = subset_df_numericFeatures(
            self.df, ["NUMERIC-ANALYTE_Y"], ["CLR-ANALYTE_X"], ["NUMERIC-ANALYTE_Y"]
        )
        self.assertIn("NUMERIC-ANALYTE_Y", cols_all)

    def test_pandas_to_json(self):
        result = pandas_to_json(self.df, "DATETIME")
        self.assertIsInstance(result, str)

    def test_json_to_pandas(self):
        json_data = pandas_to_json(self.df, "DATETIME")
        result = json_to_pandas({"key": json_data}, "key", "DATETIME")
        assert_frame_equal(result, self.df)

    def test_pc_scaler(self):
        lst_input = [10, 20, 30, 40, 50]
        lst_output = [0.25, 0.5, 0.75, 1.0, 1.25]
        data = pd.Series(lst_input)
        # Expected output after applying min-max scaling
        expected_output = pd.Series(lst_output)
        # Test
        scaled_data = pc_scaler(data)
        # Check if the scaled data matches the expected output
        pd.testing.assert_series_equal(scaled_data, expected_output)

        # Test with a numpy array
        np_data = np.array(lst_input)
        expected_np_output = np.array(lst_output)
        scaled_np_data = pc_scaler(np_data)
        np.testing.assert_array_almost_equal(scaled_np_data, expected_np_output)

        # Test with edge cases like zero range
        zero_range_data = pd.Series([5, 5, 5, 5])
        # should return the same series
        scaled_zero_range_data = pc_scaler(zero_range_data)
        pd.testing.assert_series_equal(scaled_zero_range_data, zero_range_data)


if __name__ == "__main__":
    unittest.main()

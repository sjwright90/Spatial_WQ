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
    rename_cols_plot_groups,
    rename_cols_analyte,
    extract_coordinate_dataframe,
    subset_df_locIds,
    subset_df_numericFeatures,
    pandas_to_json,
    json_to_pandas,
    pc_scaler,
    make_df_for_biplot,
)


class TestDataProcess(unittest.TestCase):

    def setUp(self):
        self.df = pd.DataFrame(
            {
                "LOCATION-ID_1": [1, 2, 3],
                "DATETIME": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "LABELS_PLOTTINGGROUP1": ["A", "B", "A"],
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
        result = df_col_group_to_dict(self.df, "LABELS_PLOTTINGGROUP1", "LOCATION-ID_1")
        expected = {"A": 1, "B": 2}
        self.assertEqual(result, expected)

    def test_get_key_cols_meta(self):
        result = get_key_cols_meta(self.df)
        expected = (
            "LOCATION-ID_1",
            "DATETIME",
            ["LABELS_PLOTTINGGROUP1"],
            ["LONGITUDE", "LATITUDE"],
        )
        self.assertEqual(result, expected)

    def test_make_color_dict(self):
        result = make_color_dict(self.df, "LABELS_PLOTTINGGROUP1")
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_find_make_color_dict(self):
        result = find_make_color_dict(self.df, "LABELS_PLOTTINGGROUP1")
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_make_plotting_group_color_dicts(self):
        result = make_plotting_group_color_dicts(self.df, ["LABELS_PLOTTINGGROUP1"])
        self.assertIn("LABELS_PLOTTINGGROUP1", result)

    def test_set_key_col_date(self):
        df = self.df.copy()
        result = set_key_col_date(df, "DATETIME")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["DATETIME"]))

    def test_get_key_cols_plot(self):
        result = get_key_cols_plot(self.df)
        expected = (
            [
                "DATETIME",
                "LABELS_PLOTTINGGROUP1",
                "LATITUDE",
                "LOCATION-ID_1",
                "LONGITUDE",
                "MAP-MARKER-SIZE",
                "MARKERS-PLOT-DOMAIN",
            ],
            ["NUMERIC-ANALYTE_Y", "CLR-ANALYTE_X"],
            ["NUMERIC-ANALYTE_Y"],
            ["CLR-ANALYTE_X"],
        )
        self.assertEqual(result, expected)

    def test_rename_cols_plot_groups(self):
        df = self.df.copy()
        renamed_df, new_names, renamed_meta = rename_cols_plot_groups(
            df, ["LABELS_PLOTTINGGROUP1"], ["LABELS_PLOTTINGGROUP1"]
        )
        self.assertIn("PLOTTINGGROUP1", renamed_df.columns)
        self.assertEqual(new_names, ["PLOTTINGGROUP1"])
        self.assertEqual(renamed_meta, ["PLOTTINGGROUP1"])

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
            ["LABELS_PLOTTINGGROUP1"],
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

    def test_make_df_for_biplot(self):
        from numpy import array

        df = self.df.copy()
        trnf_data = array([[1, 2], [3, 4], [5, 6]])
        biplot_df = make_df_for_biplot(
            trnf_data, df, col_list=["LABELS_PLOTTINGGROUP1"], num_comp=2
        )
        self.assertIn("PC1", biplot_df.columns)
        self.assertIn("PC2", biplot_df.columns)
        self.assertIn("LABELS_PLOTTINGGROUP1", biplot_df.columns)
        self.assertEqual(biplot_df.shape[1], 3)


if __name__ == "__main__":
    unittest.main()

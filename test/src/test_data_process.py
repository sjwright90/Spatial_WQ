import unittest
import pandas as pd
from pandas.testing import assert_frame_equal
import numpy as np

from app.src.data_process import (
    df_col_group_to_dict,
    make_color_dict,
    find_make_color_dict,
    make_plotting_group_color_dicts,
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
        # Arbitrary column names - the old NUMERIC-ANALYTE_/LOCATION-ID_/etc.
        # prefix convention is no longer required by any of these functions.
        self.df = pd.DataFrame(
            {
                "Site_Name": [1, 2, 3],
                "Sample_Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "Group": ["A", "B", "A"],
                "Marker": [1, 2, 3],
                "Longitude": [10.5, -20.0, 30.0],
                "Latitude": [50.0, 60.0, 70.1],
                "Zinc": [0.1, 0.2, 0.3],
                "Copper": [1, 2, 3],
                "MarkerSize": [10, 20, 10],
            }
        )
        self.df["Sample_Date"] = pd.to_datetime(self.df["Sample_Date"])

    def test_df_col_group_to_dict(self):
        result = df_col_group_to_dict(self.df, "Group", "Site_Name")
        expected = {"A": 1, "B": 2}
        self.assertEqual(result, expected)

    def test_make_color_dict(self):
        result = make_color_dict(self.df, "Group")
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_find_make_color_dict_auto_palette(self):
        result = find_make_color_dict(self.df, "Group")
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_find_make_color_dict_predefined_column(self):
        df = self.df.copy()
        df["GroupColor"] = ["#FF0000", "#00FF00", "#FF0000"]
        result = find_make_color_dict(df, "Group", col_predefined_color="GroupColor")
        self.assertEqual(result, {"A": "#FF0000", "B": "#00FF00"})

    def test_find_make_color_dict_missing_predefined_column_falls_back(self):
        result = find_make_color_dict(self.df, "Group", col_predefined_color="DoesNotExist")
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_make_plotting_group_color_dicts(self):
        result = make_plotting_group_color_dicts(self.df, ["Group"])
        self.assertIn("Group", result)

    def test_make_plotting_group_color_dicts_with_group_colors(self):
        df = self.df.copy()
        df["GroupColor"] = ["#FF0000", "#00FF00", "#FF0000"]
        result = make_plotting_group_color_dicts(
            df, ["Group"], group_colors={"Group": "GroupColor"}
        )
        self.assertEqual(result["Group"], {"A": "#FF0000", "B": "#00FF00"})

    def test_extract_coordinate_dataframe_with_marker_size_column(self):
        result = extract_coordinate_dataframe(
            self.df,
            ["Group"],
            "Site_Name",
            "Longitude",
            "Latitude",
            col_marker_size="MarkerSize",
        )
        self.assertEqual(result.shape[0], 3)
        self.assertIn("MAP-MARKER-SIZE", result.columns)

    def test_extract_coordinate_dataframe_synthesizes_marker_size(self):
        result = extract_coordinate_dataframe(
            self.df,
            ["Group"],
            "Site_Name",
            "Longitude",
            "Latitude",
        )
        self.assertIn("MAP-MARKER-SIZE", result.columns)
        self.assertTrue((result["MAP-MARKER-SIZE"] == 10).all())

    def test_subset_df_locIds(self):
        result = subset_df_locIds(self.df, "Site_Name", [1, 2])
        self.assertEqual(result.shape[0], 2)

    def test_subset_df_numericFeatures(self):
        result, cols_all, cols_clr = subset_df_numericFeatures(
            self.df, ["Copper"], ["Zinc"], ["Copper"]
        )
        self.assertIn("Copper", cols_all)

    def test_pandas_to_json(self):
        result = pandas_to_json(self.df, "Sample_Date")
        self.assertIsInstance(result, str)

    def test_json_to_pandas(self):
        json_data = pandas_to_json(self.df, "Sample_Date")
        result = json_to_pandas({"key": json_data}, "key", "Sample_Date")
        assert_frame_equal(result, self.df)

    def test_pc_scaler(self):
        lst_input = [10, 20, 30, 40, 50]
        lst_output = [0.25, 0.5, 0.75, 1.0, 1.25]
        data = pd.Series(lst_input)
        expected_output = pd.Series(lst_output)
        scaled_data = pc_scaler(data)
        pd.testing.assert_series_equal(scaled_data, expected_output)

        np_data = np.array(lst_input)
        expected_np_output = np.array(lst_output)
        scaled_np_data = pc_scaler(np_data)
        np.testing.assert_array_almost_equal(scaled_np_data, expected_np_output)

        zero_range_data = pd.Series([5, 5, 5, 5])
        scaled_zero_range_data = pc_scaler(zero_range_data)
        pd.testing.assert_series_equal(scaled_zero_range_data, zero_range_data)

    def test_make_df_for_biplot(self):
        from numpy import array

        df = self.df.copy()
        trnf_data = array([[1, 2], [3, 4], [5, 6]])
        biplot_df = make_df_for_biplot(trnf_data, df, col_list=["Group"], num_comp=2)
        self.assertIn("PC1", biplot_df.columns)
        self.assertIn("PC2", biplot_df.columns)
        self.assertIn("Group", biplot_df.columns)
        self.assertEqual(biplot_df.shape[1], 3)


if __name__ == "__main__":
    unittest.main()

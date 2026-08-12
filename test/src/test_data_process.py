import unittest
import pandas as pd
from pandas.testing import assert_frame_equal
import numpy as np

from app.src.data_process import (
    df_col_group_to_dict,
    make_color_dict,
    find_make_color_dict,
    make_plotting_group_color_dicts,
    merge_color_overrides,
    assign_custom_group_column,
    build_color_mapping_export_df,
    build_custom_group_export_df,
    extract_coordinate_dataframe,
    subset_df_locIds,
    subset_df_dateRange,
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
                "EntityId": ["e1", "e2", "e3"],
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

    def test_merge_color_overrides_no_overrides_returns_same_values(self):
        default_colors = {"Group": {"A": "#111111", "B": "#222222"}}
        result = merge_color_overrides(default_colors, None)
        self.assertEqual(result, default_colors)
        result_empty = merge_color_overrides(default_colors, {})
        self.assertEqual(result_empty, default_colors)

    def test_merge_color_overrides_applies_override_for_matching_group(self):
        default_colors = {"Group": {"A": "#111111", "B": "#222222"}}
        overrides = {"Group": {"A": "#FF0000"}}
        result = merge_color_overrides(default_colors, overrides)
        self.assertEqual(result["Group"]["A"], "#FF0000")
        self.assertEqual(result["Group"]["B"], "#222222")

    def test_merge_color_overrides_does_not_mutate_input_dict(self):
        default_colors = {"Group": {"A": "#111111", "B": "#222222"}}
        original_group_dict = default_colors["Group"]
        overrides = {"Group": {"A": "#FF0000"}}
        merge_color_overrides(default_colors, overrides)
        self.assertIs(default_colors["Group"], original_group_dict)
        self.assertEqual(default_colors["Group"]["A"], "#111111")

    def test_merge_color_overrides_string_key_matches_numeric_group_value(self):
        default_colors = {"Group": {1: "#111111", 2: "#222222"}}
        overrides = {"Group": {"1": "#FF0000"}}
        result = merge_color_overrides(default_colors, overrides)
        self.assertEqual(result["Group"][1], "#FF0000")

    def test_merge_color_overrides_group_not_present_in_overrides_untouched(self):
        default_colors = {"Group": {"A": "#111111"}, "Other": {"X": "#333333"}}
        overrides = {"Group": {"A": "#FF0000"}}
        result = merge_color_overrides(default_colors, overrides)
        self.assertEqual(result["Other"], {"X": "#333333"})

    def test_assign_custom_group_column_default_and_assigned_values(self):
        result = assign_custom_group_column(
            self.df, "EntityId", "CustomGroup", {"Cat1": ["e1"]}
        )
        self.assertEqual(
            result.set_index("EntityId")["CustomGroup"].to_dict(),
            {"e1": "Cat1", "e2": "Unassigned", "e3": "Unassigned"},
        )

    def test_assign_custom_group_column_unknown_entity_id_raises(self):
        with self.assertRaises(ValueError):
            assign_custom_group_column(self.df, "EntityId", "CustomGroup", {"Cat1": ["does-not-exist"]})

    def test_assign_custom_group_column_conflicting_assignment_last_wins(self):
        result = assign_custom_group_column(
            self.df, "EntityId", "CustomGroup", {"Cat1": ["e1"], "Cat2": ["e1"]}
        )
        self.assertEqual(result.set_index("EntityId").loc["e1", "CustomGroup"], "Cat2")

    def test_assign_custom_group_column_does_not_mutate_input_df(self):
        assign_custom_group_column(self.df, "EntityId", "CustomGroup", {"Cat1": ["e1"]})
        self.assertNotIn("CustomGroup", self.df.columns)

    def test_build_color_mapping_export_df_shape_and_values(self):
        effective_colors = {"Group": {"A": "#FF0000", "B": "#222222"}}
        result = build_color_mapping_export_df(self.df, ["Group"], "EntityId", effective_colors)
        self.assertEqual(list(result.columns), ["ENTITY_ID", "CATEGORY_COL", "CATEGORY_VALUE", "CATEGORY_COLOR"])
        self.assertEqual(result.shape[0], 3)
        row_e1 = result[result["ENTITY_ID"] == "e1"].iloc[0]
        self.assertEqual(row_e1["CATEGORY_COLOR"], "#FF0000")

    def test_build_custom_group_export_df_columns_with_date(self):
        df = self.df.copy()
        df["CustomGroup"] = ["Cat1", "Cat2", "Cat1"]
        result = build_custom_group_export_df(df, "EntityId", "Site_Name", "Sample_Date", ["CustomGroup"])
        self.assertEqual(list(result.columns), ["ENTITY_ID", "LOCATION_ID", "DATE", "CustomGroup"])

    def test_build_custom_group_export_df_columns_without_date(self):
        df = self.df.copy()
        df["CustomGroup"] = ["Cat1", "Cat2", "Cat1"]
        result = build_custom_group_export_df(df, "EntityId", "Site_Name", None, ["CustomGroup"])
        self.assertEqual(list(result.columns), ["ENTITY_ID", "LOCATION_ID", "CustomGroup"])

    def test_build_custom_group_export_df_empty_custom_columns(self):
        result = build_custom_group_export_df(self.df, "EntityId", "Site_Name", "Sample_Date", [])
        self.assertEqual(result.shape[0], 0)
        self.assertEqual(list(result.columns), ["ENTITY_ID", "LOCATION_ID", "DATE"])

    def test_build_custom_group_export_df_no_date_filter_unchanged(self):
        # date_filter_range=None (default) is a regression guard - identical
        # to the pre-feature behavior.
        df = self.df.copy()
        df["CustomGroup"] = ["Unassigned", "Unassigned", "Unassigned"]
        result = build_custom_group_export_df(
            df, "EntityId", "Site_Name", "Sample_Date", ["CustomGroup"]
        )
        self.assertTrue((result["CustomGroup"] == "Unassigned").all())

    def test_build_custom_group_export_df_marks_unassigned_out_of_range_rows(self):
        # self.df's Sample_Date is 2023-01-01..2023-01-03; filter to just day 1.
        df = self.df.copy()
        df["CustomGroup"] = ["Unassigned", "Unassigned", "Unassigned"]
        result = build_custom_group_export_df(
            df,
            "EntityId",
            "Site_Name",
            "Sample_Date",
            ["CustomGroup"],
            date_filter_range=["2023-01-01", "2023-01-01"],
        )
        values = result.set_index("ENTITY_ID")["CustomGroup"].to_dict()
        self.assertEqual(values["e1"], "Unassigned")
        self.assertEqual(values["e2"], "DATE-FILTERED-[2023-01-01->2023-01-01]")
        self.assertEqual(values["e3"], "DATE-FILTERED-[2023-01-01->2023-01-01]")

    def test_build_custom_group_export_df_preserves_preexisting_assignment_out_of_range(self):
        # A real (non-default) assignment on an out-of-range row (e.g. from a
        # group created under a wider/no Filter) must not be overwritten.
        df = self.df.copy()
        df["CustomGroup"] = ["Unassigned", "Cat1", "Unassigned"]
        result = build_custom_group_export_df(
            df,
            "EntityId",
            "Site_Name",
            "Sample_Date",
            ["CustomGroup"],
            date_filter_range=["2023-01-01", "2023-01-01"],
        )
        values = result.set_index("ENTITY_ID")["CustomGroup"].to_dict()
        self.assertEqual(values["e2"], "Cat1")
        self.assertEqual(values["e3"], "DATE-FILTERED-[2023-01-01->2023-01-01]")

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

    def test_subset_df_dateRange_inclusive_range(self):
        result = subset_df_dateRange(self.df, "Sample_Date", ["2023-01-01", "2023-01-02"])
        self.assertEqual(sorted(result["EntityId"]), ["e1", "e2"])

    def test_subset_df_dateRange_boundary_dates_included(self):
        # Single-day range equal to a boundary date row should include just that row.
        result = subset_df_dateRange(self.df, "Sample_Date", ["2023-01-03", "2023-01-03"])
        self.assertEqual(list(result["EntityId"]), ["e3"])

    def test_subset_df_dateRange_no_col_date_passthrough(self):
        result = subset_df_dateRange(self.df, None, ["2023-01-01", "2023-01-02"])
        self.assertEqual(result.shape[0], self.df.shape[0])

    def test_subset_df_dateRange_no_date_range_passthrough(self):
        result = subset_df_dateRange(self.df, "Sample_Date", None)
        self.assertEqual(result.shape[0], self.df.shape[0])

    def test_subset_df_dateRange_does_not_mutate_input(self):
        subset_df_dateRange(self.df, "Sample_Date", ["2023-01-01", "2023-01-01"])
        self.assertEqual(self.df.shape[0], 3)

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

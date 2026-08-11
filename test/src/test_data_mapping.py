import unittest

import pandas as pd

from app.src.data_mapping import build_mapped_dataset
from app.src.data_model import ColumnMapping


def make_raw_df():
    return pd.DataFrame(
        {
            "Site_Name": ["1A", "2B", "3C"],
            "lat_dd": [50.0, 60.0, 70.1],
            "lon_dd": [10.5, -20.0, 30.0],
            "Sample_Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
            "Group": ["A", "B", "A"],
            "Marker": ["circle", "square", "circle"],
            "MarkerSize": [10, 12, 8],
            "Group_Color": ["#FF0000", "#00FF00", "#FF0000"],
            "Copper": [1.0, 2.0, 3.0],
            "Zinc": [0.1, 0.2, 0.3],
        }
    )


def make_full_mapping():
    return ColumnMapping(
        location_id="Site_Name",
        latitude="lat_dd",
        longitude="lon_dd",
        plotting_groups=["Group"],
        numeric_simple=["Copper"],
        numeric_clr=["Zinc"],
        date="Sample_Date",
        marker_symbol="Marker",
        map_marker_size="MarkerSize",
        group_colors={"Group": "Group_Color"},
    )


class TestBuildMappedDatasetHappyPath(unittest.TestCase):
    def test_happy_path_no_errors_no_warnings(self):
        result = build_mapped_dataset(make_raw_df(), make_full_mapping())
        self.assertFalse(result.validation.has_errors)
        self.assertEqual(result.validation.warnings, [])
        self.assertIn("LATITUDE", result.df_master.columns)
        self.assertIn("LONGITUDE", result.df_master.columns)
        self.assertEqual(result.cols_key_meta["loc_id"], "Site_Name")
        self.assertEqual(result.cols_key_meta["date"], "Sample_Date")
        self.assertEqual(result.cols_key_meta["plotting_groups"], ["Group"])
        self.assertEqual(result.cols_key_plot["numeric_simple"], ["Copper"])
        self.assertEqual(result.cols_key_plot["numeric_clr"], ["Zinc"])

    def test_arbitrary_column_names_work(self):
        # Proves the old prefix convention (LOCATION-ID_, NUMERIC-ANALYTE_, ...)
        # is no longer required at all.
        result = build_mapped_dataset(make_raw_df(), make_full_mapping())
        self.assertFalse(result.validation.has_errors)


class TestBuildMappedDatasetRequiredRoles(unittest.TestCase):
    def test_missing_location_id_blocks(self):
        mapping = make_full_mapping()
        mapping.location_id = None
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertTrue(result.validation.has_errors)
        self.assertIsNone(result.df_master)

    def test_missing_lat_lon_blocks(self):
        mapping = make_full_mapping()
        mapping.latitude = None
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertTrue(result.validation.has_errors)

    def test_no_numeric_columns_blocks(self):
        mapping = make_full_mapping()
        mapping.numeric_simple = []
        mapping.numeric_clr = []
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertTrue(result.validation.has_errors)

    def test_no_plotting_group_blocks(self):
        mapping = make_full_mapping()
        mapping.plotting_groups = []
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertTrue(result.validation.has_errors)


class TestBuildMappedDatasetDuplicateAndMissingColumns(unittest.TestCase):
    def test_duplicate_column_mapped_twice_errors(self):
        mapping = make_full_mapping()
        mapping.numeric_simple = ["Copper", "Site_Name"]
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertTrue(result.validation.has_errors)

    def test_missing_raw_column_errors(self):
        mapping = make_full_mapping()
        mapping.numeric_simple = ["DoesNotExist"]
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertTrue(result.validation.has_errors)


class TestBuildMappedDatasetCoercion(unittest.TestCase):
    def test_bad_lat_lon_values_error(self):
        df = make_raw_df()
        df.loc[0, "lat_dd"] = 999.0
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertTrue(result.validation.has_errors)

    def test_non_numeric_junk_in_numeric_column_warns_and_coerces(self):
        df = make_raw_df()
        df.loc[0, "Copper"] = "not-a-number"
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertFalse(result.validation.has_errors)
        self.assertTrue(
            any(w.field == "numeric_simple" for w in result.validation.warnings)
        )

    def test_clr_zero_or_negative_errors(self):
        df = make_raw_df()
        df.loc[0, "Zinc"] = 0.0
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertTrue(result.validation.has_errors)

    def test_partially_unparseable_dates_warns_but_usable(self):
        df = make_raw_df()
        df.loc[0, "Sample_Date"] = "not-a-date"
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertFalse(result.validation.has_errors)
        self.assertEqual(result.cols_key_meta["date"], "Sample_Date")
        self.assertTrue(any(w.field == "date" for w in result.validation.warnings))

    def test_fully_unparseable_dates_degrades_to_none(self):
        df = make_raw_df()
        df["Sample_Date"] = ["not-a-date", "also-bad", "still-bad"]
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertFalse(result.validation.has_errors)
        self.assertIsNone(result.cols_key_meta["date"])
        self.assertTrue(any(w.field == "date" for w in result.validation.warnings))

    def test_invalid_hex_color_warns_non_blocking(self):
        df = make_raw_df()
        df.loc[0, "Group_Color"] = "not-a-hex-color"
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertFalse(result.validation.has_errors)
        self.assertTrue(any(w.field == "group_color" for w in result.validation.warnings))


class TestBuildMappedDatasetEntityId(unittest.TestCase):
    def test_entity_id_combines_location_and_date(self):
        result = build_mapped_dataset(make_raw_df(), make_full_mapping())
        self.assertEqual(result.cols_key_meta["entity_id"], "ENTITY_ID")
        self.assertEqual(
            result.df_master["ENTITY_ID"].tolist(),
            ["1A_2023-01-01", "2B_2023-01-02", "3C_2023-01-03"],
        )

    def test_entity_id_falls_back_to_location_id_when_no_date_mapped(self):
        mapping = ColumnMapping(
            location_id="Site_Name",
            latitude="lat_dd",
            longitude="lon_dd",
            plotting_groups=["Group"],
            numeric_simple=["Copper"],
        )
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertEqual(
            result.df_master["ENTITY_ID"].tolist(), ["1A", "2B", "3C"]
        )

    def test_entity_id_falls_back_to_location_id_when_date_fully_unusable(self):
        df = make_raw_df()
        df["Sample_Date"] = ["not-a-date", "also-bad", "still-bad"]
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertIsNone(result.cols_key_meta["date"])
        self.assertEqual(
            result.df_master["ENTITY_ID"].tolist(), ["1A", "2B", "3C"]
        )

    def test_entity_id_falls_back_per_row_on_unparseable_date(self):
        df = make_raw_df()
        df.loc[0, "Sample_Date"] = "not-a-date"
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertEqual(
            result.df_master["ENTITY_ID"].tolist(),
            ["1A", "2B_2023-01-02", "3C_2023-01-03"],
        )

    def test_duplicate_entity_id_warns_non_blocking(self):
        df = make_raw_df()
        df.loc[1, "Site_Name"] = "1A"
        df.loc[1, "Sample_Date"] = "2023-01-01"
        result = build_mapped_dataset(df, make_full_mapping())
        self.assertFalse(result.validation.has_errors)
        self.assertTrue(any(w.field == "entity_id" for w in result.validation.warnings))

    def test_no_duplicate_entity_id_no_warning(self):
        result = build_mapped_dataset(make_raw_df(), make_full_mapping())
        self.assertFalse(any(w.field == "entity_id" for w in result.validation.warnings))


class TestBuildMappedDatasetOptionalRolesAbsent(unittest.TestCase):
    def test_all_optional_roles_absent_still_builds(self):
        mapping = ColumnMapping(
            location_id="Site_Name",
            latitude="lat_dd",
            longitude="lon_dd",
            plotting_groups=["Group"],
            numeric_simple=["Copper"],
        )
        result = build_mapped_dataset(make_raw_df(), mapping)
        self.assertFalse(result.validation.has_errors)
        self.assertIsNone(result.cols_key_meta["date"])
        self.assertIsNone(result.cols_key_meta["marker_symbol"])
        self.assertIsNone(result.cols_key_meta["map_marker_size"])
        self.assertIn("LATITUDE", result.df_master.columns)
        self.assertIn("LONGITUDE", result.df_master.columns)


if __name__ == "__main__":
    unittest.main()

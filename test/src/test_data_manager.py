import unittest
import base64
import json
import pandas as pd
from app.src.data_manager import DataPreprocessor, DataPlotter
from app.src.data_model import ColumnMapping


def encode_csv(csv_content: str) -> str:
    return base64.b64encode(csv_content.encode()).decode()


class TestDataPreprocessor(unittest.TestCase):
    def setUp(self):
        # Arbitrary column names - proves the old LOCATION-ID_/DATETIME/etc.
        # prefix convention is no longer required.
        csv_content = (
            "Site_Name,Sample_Date,Group,Marker,Longitude,Latitude,Zinc,Copper,MarkerSize\n"
            "1,2023-01-01,A,circle,10.5,50.0,0.1,1,10\n"
            "2,2023-01-02,B,square,-20.0,60.0,0.2,2,10\n"
            "3,2023-01-03,A,circle,30.0,70.1,0.3,3,10\n"
        )
        self.content_string = encode_csv(csv_content)
        self.mapping = ColumnMapping(
            location_id="Site_Name",
            latitude="Latitude",
            longitude="Longitude",
            plotting_groups=["Group"],
            numeric_simple=["Copper"],
            numeric_clr=["Zinc"],
            date="Sample_Date",
            marker_symbol="Marker",
            map_marker_size="MarkerSize",
        )

    def test_initialization(self):
        preprocessor = DataPreprocessor(self.content_string, self.mapping)
        self.assertFalse(preprocessor.validation.has_errors)
        self.assertIsInstance(preprocessor.df_master, pd.DataFrame)
        self.assertIsInstance(preprocessor.cols_key_plot, dict)
        self.assertIsInstance(preprocessor.cols_key_meta, dict)
        self.assertIsInstance(preprocessor.dict_marker_map, dict)
        self.assertIsInstance(preprocessor.dict_generic_colors, dict)
        self.assertIsInstance(preprocessor.loc_id_all, list)
        self.assertIsInstance(preprocessor.cols_numeric_all, list)

    def test_get_session_dict(self):
        preprocessor = DataPreprocessor(self.content_string, self.mapping)
        session_dict = preprocessor.get_session_dict()

        expected_keys = {
            "df_master",
            "meta_data",
            "data_hash",
            "working_data",
            "plotting_data",
            "version",
        }
        self.assertTrue(expected_keys.issubset(session_dict.keys()))

        self.assertIsInstance(session_dict["df_master"], str)  # JSON string
        self.assertIsInstance(session_dict["meta_data"], dict)
        self.assertIsInstance(session_dict["data_hash"], dict)
        self.assertIsNone(session_dict["working_data"])
        self.assertIsInstance(session_dict["plotting_data"], dict)
        self.assertEqual(session_dict["version"], 1)

        plotting_data = session_dict["plotting_data"]
        self.assertEqual(
            plotting_data["feature_selection_dropdown_options"],
            preprocessor.cols_key_plot["numeric_all"],
        )
        self.assertEqual(
            plotting_data["map_group_dropdown_value"],
            preprocessor.cols_key_meta["plotting_groups"][0],
        )
        self.assertEqual(plotting_data["pmap_neighbors"], 15)

    def test_missing_required_role_leaves_validation_error_and_no_data(self):
        bad_mapping = ColumnMapping(location_id="Site_Name", latitude="Latitude", longitude="")
        preprocessor = DataPreprocessor(self.content_string, bad_mapping)
        self.assertTrue(preprocessor.validation.has_errors)
        self.assertIsNone(preprocessor.df_master)
        self.assertIsNone(preprocessor.cols_key_plot)

    def test_unmapped_marker_symbol_defaults_every_location(self):
        mapping = ColumnMapping(
            location_id="Site_Name",
            latitude="Latitude",
            longitude="Longitude",
            plotting_groups=["Group"],
            numeric_simple=["Copper"],
        )
        preprocessor = DataPreprocessor(self.content_string, mapping)
        self.assertFalse(preprocessor.validation.has_errors)
        self.assertEqual(set(preprocessor.dict_marker_map.keys()), set(preprocessor.loc_id_all))
        self.assertTrue(all(v == "circle" for v in preprocessor.dict_marker_map.values()))


class TestDataPlotter(unittest.TestCase):
    def setUp(self):
        _df_pca = pd.DataFrame(
            {
                "Site_Name": ["1A", "2B", "3C"],
                "Sample_Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "Group1": ["A", "B", "A"],
                "Group2": ["A", "B", "A"],
                "Marker": [1, 2, 3],
                "PC1": [0.1, 0.2, 0.3],
                "PC2": [0.4, 0.5, 0.6],
                "date": ["2023-01-01", "2023-01-02", "2023-01-03"],
            }
        )
        _df_pmap = _df_pca.rename(columns={"PC1": "PMAP1", "PC2": "PMAP2"})
        _ldg_df = pd.DataFrame(
            {
                "PC1": [0.1, 0.2, 0.3],
                "PC2": [0.4, 0.5, 0.6],
                "metals": ["A", "B", "C"],
            }
        )
        # Mock data for testing
        self.working_data = json.dumps(
            {
                "df_plot_pca": _df_pca.to_json(orient="split"),
                "df_plot_pmap": _df_pmap.to_json(orient="split"),
                "ldg_df": _ldg_df.to_json(),
                "expl_var": [0.1, 0.2],
            }
        )
        self.meta_data = json.dumps(
            {
                "cols_key_plot": {"numeric_all": ["value1", "value2"]},
                "cols_key_meta": {"loc_id": "Site_Name", "date": "date"},
                "dict_marker_map": {"1A": 1, "2B": 2, "3C": 3},
                "dict_generic_colors": {
                    "Group1": {"A": "red", "B": "blue"},
                    "Group2": {"A": "green", "B": "yellow"},
                },
                "loc_id_all": ["1A", "2B", "3C"],
            }
        )
        self.selected_loc_ids = {"points": [{"customdata": ["1A"]}]}
        self.selected_loc_ids_none = None
        self.plot_groups = ["Group1", "Group1"]
        self.date_range = [2023, 2023]

    def test_initialization(self):
        plotter = DataPlotter(
            self.working_data,
            self.meta_data,
            self.selected_loc_ids,
            self.plot_groups,
            self.date_range,
        )
        self.assertIsInstance(plotter.df_plot_pca, pd.DataFrame)
        self.assertIsInstance(plotter.df_plot_pmap, pd.DataFrame)

    def test_empty_figs(self):
        fig1, fig2 = DataPlotter.empty_figs()
        self.assertIsNotNone(fig1)
        self.assertIsNotNone(fig2)

    def test_plot_pmap(self):
        plotter = DataPlotter(
            self.working_data,
            self.meta_data,
            self.selected_loc_ids,
            self.plot_groups,
            self.date_range,
        )
        fig = plotter.plot_pmap(n_neighbors=5)
        self.assertIsNotNone(fig)

        plotter_none = DataPlotter(
            self.working_data,
            self.meta_data,
            self.selected_loc_ids_none,
            self.plot_groups,
            self.date_range,
        )
        fig_none = plotter_none.plot_pmap(n_neighbors=5)
        self.assertIsNotNone(fig_none)

    def test_plot_pca(self):
        plotter = DataPlotter(
            self.working_data,
            self.meta_data,
            self.selected_loc_ids,
            self.plot_groups,
            self.date_range,
        )
        fig = plotter.plot_pca()
        self.assertIsNotNone(fig)

        plotter_none = DataPlotter(
            self.working_data,
            self.meta_data,
            self.selected_loc_ids_none,
            self.plot_groups,
            self.date_range,
        )
        fig_none = plotter_none.plot_pca()
        self.assertIsNotNone(fig_none)

    def test_no_date_column_skips_date_filtering(self):
        meta_data_no_date = json.loads(self.meta_data)
        meta_data_no_date["cols_key_meta"]["date"] = None
        plotter = DataPlotter(
            self.working_data,
            json.dumps(meta_data_no_date),
            self.selected_loc_ids_none,
            self.plot_groups,
            self.date_range,
        )
        self.assertEqual(len(plotter.df_plot_pca), 3)


if __name__ == "__main__":
    unittest.main()

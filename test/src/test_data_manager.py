import unittest
import base64
import io
import json
import pandas as pd
from app.src.data_manager import DataPreprocessor, DataPlotter, SessionManager
from app.src.data_model import ColumnMapping
from app.src.data_process import json_to_pandas


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

    def test_cols_key_meta_includes_entity_id(self):
        preprocessor = DataPreprocessor(self.content_string, self.mapping)
        self.assertEqual(preprocessor.cols_key_meta["entity_id"], "ENTITY_ID")
        self.assertIn("ENTITY_ID", preprocessor.df_master.columns)
        # loc_id_all/dropdown stay location-only (not composite) even though
        # rows repeat per location across dates. loc_id is coerced to string
        # at the source (DataPreprocessor.__init__) regardless of the raw
        # CSV's dtype, so it stays consistent with dict_marker_map's string
        # keys after a JSON round-trip (see the comment in data_manager.py).
        self.assertEqual(sorted(preprocessor.loc_id_all), ["1", "2", "3"])

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
        # Upstream date Filter starts unset (no filtering) on a fresh session.
        self.assertIsNone(plotting_data["date_filter_range_dropdown_value"])

    def test_missing_required_role_leaves_validation_error_and_no_data(self):
        bad_mapping = ColumnMapping(location_id="Site_Name", latitude="Latitude", longitude="")
        preprocessor = DataPreprocessor(self.content_string, bad_mapping)
        self.assertTrue(preprocessor.validation.has_errors)
        self.assertIsNone(preprocessor.df_master)
        self.assertIsNone(preprocessor.cols_key_plot)

    def test_repeat_visits_collapse_loc_id_but_not_entity_id(self):
        csv_content = (
            "Site_Name,Sample_Date,Group,Marker,Longitude,Latitude,Zinc,Copper,MarkerSize\n"
            "1,2023-01-01,A,circle,10.5,50.0,0.1,1,10\n"
            "1,2023-06-01,A,circle,10.5,50.0,0.15,1.5,10\n"
            "2,2023-01-02,B,square,-20.0,60.0,0.2,2,10\n"
        )
        preprocessor = DataPreprocessor(encode_csv(csv_content), self.mapping)
        self.assertFalse(preprocessor.validation.has_errors)
        self.assertEqual(sorted(preprocessor.loc_id_all), ["1", "2"])
        self.assertEqual(preprocessor.df_master["ENTITY_ID"].nunique(), 3)

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

    def test_numeric_loc_id_is_coerced_to_string_consistently(self):
        # Regression test: a numeric loc_id column used to keep its original
        # dtype in df_master/loc_id_all while dict_marker_map's keys became
        # strings after a JSON round-trip (JSON object keys are always
        # strings), desyncing lookups downstream. loc_id is now coerced to
        # string once, at the source, so df_master's column, loc_id_all, and
        # dict_marker_map's keys are all consistently strings from the start
        # - no round-trip needed to expose the mismatch.
        preprocessor = DataPreprocessor(self.content_string, self.mapping)
        self.assertFalse(preprocessor.validation.has_errors)
        self.assertTrue(all(isinstance(v, str) for v in preprocessor.loc_id_all))
        self.assertTrue(all(isinstance(v, str) for v in preprocessor.df_master["Site_Name"]))
        self.assertEqual(set(preprocessor.dict_marker_map.keys()), set(preprocessor.loc_id_all))


class TestSessionManagerAddCustomGroup(unittest.TestCase):
    def setUp(self):
        csv_content = (
            "Site_Name,Sample_Date,Group,Marker,Longitude,Latitude,Zinc,Copper,MarkerSize\n"
            "1,2023-01-01,A,circle,10.5,50.0,0.1,1,10\n"
            "2,2023-01-02,B,square,-20.0,60.0,0.2,2,10\n"
            "3,2023-01-03,A,circle,30.0,70.1,0.3,3,10\n"
        )
        mapping = ColumnMapping(
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
        preprocessor = DataPreprocessor(encode_csv(csv_content), mapping)
        self.session = preprocessor.get_session_dict()
        self.entity_ids = json_to_pandas(self.session, "df_master", "Sample_Date")[
            "ENTITY_ID"
        ].tolist()

    def test_add_custom_group_appends_column_and_updates_meta(self):
        assignments = {"MyCat": [self.entity_ids[0]]}
        session = SessionManager.add_custom_group(self.session, "CustomGroup", assignments)

        df_master = json_to_pandas(session, "df_master", "Sample_Date")
        self.assertIn("CustomGroup", df_master.columns)

        meta_data = session["meta_data"]
        self.assertIn("CustomGroup", meta_data["cols_key_meta"]["plotting_groups"])
        self.assertIn("CustomGroup", meta_data["cols_key_plot"]["meta"])
        self.assertIn("CustomGroup", meta_data["dict_generic_colors"])
        self.assertIn("CustomGroup", meta_data["custom_group_columns"])

        for key in (
            "map_group_dropdown_options",
            "plot_group_dropdown_1_options",
            "plot_group_dropdown_2_options",
        ):
            self.assertIn("CustomGroup", session["plotting_data"][key])

    def test_add_custom_group_recomputes_df_coordinate(self):
        assignments = {"MyCat": [self.entity_ids[0]]}
        session = SessionManager.add_custom_group(self.session, "CustomGroup", assignments)
        df_coordinate = pd.read_json(io.StringIO(session["meta_data"]["df_coordinate"]))
        self.assertIn("CustomGroup", df_coordinate.columns)

    def test_add_custom_group_rejects_reserved_or_duplicate_name(self):
        for bad_name in ("LATITUDE", "Group", "Copper"):
            with self.assertRaises(ValueError):
                SessionManager.add_custom_group(
                    self.session, bad_name, {"MyCat": [self.entity_ids[0]]}
                )

    def test_add_custom_group_auto_colors_new_category_values(self):
        assignments = {"MyCat": [self.entity_ids[0]]}
        session = SessionManager.add_custom_group(self.session, "CustomGroup", assignments)
        color_dict = session["meta_data"]["dict_generic_colors"]["CustomGroup"]
        self.assertIn("MyCat", color_dict)
        self.assertIn("Unassigned", color_dict)


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

    def test_pca_component_options_lists_computed_pcs_in_order(self):
        plotter = DataPlotter(
            self.working_data,
            self.meta_data,
            self.selected_loc_ids,
            self.plot_groups,
            self.date_range,
        )
        self.assertEqual(plotter.pca_component_options(), ["PC1", "PC2"])

    def test_plot_pca_accepts_selectable_component_pair(self):
        # working_data only computes PC1/PC2 here, but plot_pca must still
        # accept (and use) an explicit x_col/y_col rather than hardcoding
        # PC1/PC2.
        plotter = DataPlotter(
            self.working_data,
            self.meta_data,
            self.selected_loc_ids,
            self.plot_groups,
            self.date_range,
        )
        fig = plotter.plot_pca(x_col="PC2", y_col="PC1")
        self.assertIn("PC2", fig.layout.xaxis.title.text)
        self.assertIn("PC1", fig.layout.yaxis.title.text)

    def test_plot_pca_with_entity_id_and_repeat_visits_collapses_legend(self):
        # Same Site_Name ("1A") twice with different dates - should collapse
        # into one legend entry, not explode into two.
        _df_pca = pd.DataFrame(
            {
                "Site_Name": ["1A", "1A", "2B"],
                "ENTITY_ID": ["1A_2023-01-01", "1A_2023-06-01", "2B_2023-01-02"],
                "Sample_Date": ["2023-01-01", "2023-06-01", "2023-01-02"],
                "Group1": ["A", "A", "B"],
                "Group2": ["A", "A", "B"],
                "Marker": [1, 1, 2],
                "PC1": [0.1, 0.2, 0.3],
                "PC2": [0.4, 0.5, 0.6],
                "date": ["2023-01-01", "2023-06-01", "2023-01-02"],
            }
        )
        _df_pmap = _df_pca.rename(columns={"PC1": "PMAP1", "PC2": "PMAP2"})
        _ldg_df = pd.DataFrame(
            {"PC1": [0.1, 0.2, 0.3], "PC2": [0.4, 0.5, 0.6], "metals": ["A", "B", "C"]}
        )
        working_data = json.dumps(
            {
                "df_plot_pca": _df_pca.to_json(orient="split"),
                "df_plot_pmap": _df_pmap.to_json(orient="split"),
                "ldg_df": _ldg_df.to_json(),
                "expl_var": [0.1, 0.2],
            }
        )
        meta_data = json.dumps(
            {
                "cols_key_plot": {"numeric_all": ["value1", "value2"]},
                "cols_key_meta": {
                    "loc_id": "Site_Name",
                    "entity_id": "ENTITY_ID",
                    "date": "date",
                },
                "dict_marker_map": {"1A": 1, "2B": 2},
                "dict_generic_colors": {
                    "Group1": {"A": "red", "B": "blue"},
                    "Group2": {"A": "green", "B": "yellow"},
                },
                "loc_id_all": ["1A", "2B"],
            }
        )
        plotter = DataPlotter(
            working_data,
            meta_data,
            None,
            self.plot_groups,
            self.date_range,
        )
        fig = plotter.plot_pca()
        # One trace per location (1A, 2B) - legend does not explode per date.
        self.assertEqual(len(fig.data), 2)
        trace_1a = next(t for t in fig.data if t.name == "1A")
        self.assertEqual(len(trace_1a.x), 2)
        self.assertEqual(
            [row[1] for row in trace_1a.customdata],
            ["1A_2023-01-01", "1A_2023-06-01"],
        )

    def test_plot_pca_with_entity_id_splits_location_by_custom_category(self):
        # Same Site_Name ("1A") twice, but the two ENTITY_ID rows belong to
        # different Group1 categories (e.g. a custom, ENTITY_ID-scoped
        # group) - each point must get its own category's color rather
        # than both being painted with the first date's category.
        _df_pca = pd.DataFrame(
            {
                "Site_Name": ["1A", "1A", "2B"],
                "ENTITY_ID": ["1A_2023-01-01", "1A_2023-06-01", "2B_2023-01-02"],
                "Sample_Date": ["2023-01-01", "2023-06-01", "2023-01-02"],
                "Group1": ["A", "B", "B"],
                "Group2": ["A", "B", "B"],
                "Marker": [1, 1, 2],
                "PC1": [0.1, 0.2, 0.3],
                "PC2": [0.4, 0.5, 0.6],
                "date": ["2023-01-01", "2023-06-01", "2023-01-02"],
            }
        )
        _df_pmap = _df_pca.rename(columns={"PC1": "PMAP1", "PC2": "PMAP2"})
        _ldg_df = pd.DataFrame(
            {"PC1": [0.1, 0.2, 0.3], "PC2": [0.4, 0.5, 0.6], "metals": ["A", "B", "C"]}
        )
        working_data = json.dumps(
            {
                "df_plot_pca": _df_pca.to_json(orient="split"),
                "df_plot_pmap": _df_pmap.to_json(orient="split"),
                "ldg_df": _ldg_df.to_json(),
                "expl_var": [0.1, 0.2],
            }
        )
        meta_data = json.dumps(
            {
                "cols_key_plot": {"numeric_all": ["value1", "value2"]},
                "cols_key_meta": {
                    "loc_id": "Site_Name",
                    "entity_id": "ENTITY_ID",
                    "date": "date",
                },
                "dict_marker_map": {"1A": 1, "2B": 2},
                "dict_generic_colors": {
                    "Group1": {"A": "red", "B": "blue"},
                    "Group2": {"A": "green", "B": "yellow"},
                },
                "loc_id_all": ["1A", "2B"],
            }
        )
        plotter = DataPlotter(
            working_data,
            meta_data,
            None,
            self.plot_groups,
            self.date_range,
        )
        fig = plotter.plot_pca()

        site_1a_traces = [t for t in fig.data if t.name.startswith("1A")]
        # 1A's two dates land in different categories - split into two
        # sub-traces, each with the correct color for its own row.
        self.assertEqual(len(site_1a_traces), 2)
        colors_by_entity = {
            row[1]: t.marker.color for t in site_1a_traces for row in t.customdata
        }
        self.assertEqual(
            colors_by_entity,
            {"1A_2023-01-01": "red", "1A_2023-06-01": "blue"},
        )
        # Each split sub-trace gets its own legend entry, distinguished by
        # date range, instead of both collapsing under one ambiguous "1A".
        self.assertEqual(
            {t.name for t in site_1a_traces},
            {"1A [2023-01-01]", "1A [2023-06-01]"},
        )
        self.assertTrue(all(t.showlegend is not False for t in site_1a_traces))

        # 2B has only one category - unaffected, single trace as before.
        site_2b_traces = [t for t in fig.data if t.name == "2B"]
        self.assertEqual(len(site_2b_traces), 1)
        self.assertEqual(site_2b_traces[0].marker.color, "blue")

    def test_missing_meta_data_key_raises_clear_error(self):
        # Regression test: a session blob missing an expected meta_data key
        # (e.g. from an older/incompatible app version) used to raise a bare
        # KeyError('cols_key_meta') with no context. _require() now raises a
        # descriptive error naming the missing key and which dict it's from.
        meta_data_missing_key = json.loads(self.meta_data)
        del meta_data_missing_key["cols_key_meta"]
        with self.assertRaisesRegex(KeyError, "cols_key_meta"):
            DataPlotter(
                self.working_data,
                json.dumps(meta_data_missing_key),
                self.selected_loc_ids_none,
                self.plot_groups,
                self.date_range,
            )

    def test_initialize_data_reraises_original_exception_type(self):
        # Regression test: initialize_data used to catch any exception and
        # re-raise a generic ValueError("Error initializing data"), discarding
        # the original error type/message. It must now re-raise as-is.
        with self.assertRaises(json.JSONDecodeError):
            DataPlotter(
                "not valid json",
                self.meta_data,
                self.selected_loc_ids_none,
                self.plot_groups,
                self.date_range,
            )

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

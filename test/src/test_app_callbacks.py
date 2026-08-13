import importlib.util
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

from dash._callback_context import context_value
from dash._utils import AttributeDict


@contextmanager
def _fake_callback_context(triggered_prop_id: str):
    """update_map/patch_map_colors read `dash.ctx.triggered_id` internally,
    which raises MissingCallbackContextException outside a real Dash
    request cycle - fake just enough of the context Dash sets up per
    request so these callbacks can be invoked directly in a test."""
    token = context_value.set(
        AttributeDict(triggered_inputs=[{"prop_id": triggered_prop_id, "value": True}])
    )
    try:
        yield
    finally:
        context_value.reset(token)

# app/app.py uses `from src.plotting import ...` (not `from app.src...` or
# relative imports) - it's designed to run with the `app/` directory itself on
# sys.path (as `python app/app.py` does), not as a submodule of the `app`
# namespace package the rest of the test suite imports from (`app.src.*`).
# A plain `import app.app` collides with that already-imported namespace
# package, so load app/app.py directly from its file path instead, under a
# name that can't collide with the `app` package.
_APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _import_app_entrypoint():
    sys.path.insert(0, str(_APP_DIR))
    try:
        spec = importlib.util.spec_from_file_location("app_entrypoint", _APP_DIR / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(_APP_DIR))


class TestAppImport(unittest.TestCase):
    def test_app_module_imports_cleanly(self):
        # Regression test: app.py used to import save_to_redis/load_from_redis/
        # list_keys from a commented-out block while calling them live in 3
        # callbacks, which would raise NameError the first time those
        # callbacks fired. Loading the module must succeed and expose the
        # restored Redis functions.
        app_module = _import_app_entrypoint()

        self.assertTrue(callable(app_module.save_to_redis))
        self.assertTrue(callable(app_module.load_from_redis))
        self.assertTrue(callable(app_module.list_keys))
        self.assertTrue(callable(app_module.load_session_data))

    def test_date_filter_callbacks_importable(self):
        # The new upstream date-Filter callbacks (distinct from the existing
        # downstream date-range-slider "Mask") must wire up cleanly.
        app_module = _import_app_entrypoint()

        self.assertTrue(callable(app_module.update_date_filter_picker))
        self.assertTrue(callable(app_module.reset_date_filter))
        self.assertTrue(callable(app_module.update_date_filter_indicator))


class TestCustomGroupEntityPickerRespectsDateFilter(unittest.TestCase):
    """The manual custom-group entity picker must only ever offer entities
    within the last-Applied upstream date Filter - see the DATE-FILTERED
    export-marker design decision in
    docs/agent-context/02_NEXT-STEPS-DATETIMEFILTER-HANDOFF.md."""

    def setUp(self):
        self.app_module = _import_app_entrypoint()
        import pandas as pd

        self.df_master = pd.DataFrame(
            {
                "LOC_ID": ["Site1", "Site2", "Site3"],
                "ENTITY_ID": ["e1", "e2", "e3"],
                "Sample_Date": pd.to_datetime(["2020-01-01", "2020-06-01", "2023-01-01"]),
            }
        )

    def test_filtered_entity_excluded_from_options(self):
        filtered = self.app_module.subset_df_dateRange(
            self.df_master, "Sample_Date", ["2020-01-01", "2020-12-31"]
        )
        options = self.app_module._build_entity_dropdown_options(
            filtered, "LOC_ID", "ENTITY_ID", "Sample_Date"
        )
        option_values = {opt["value"] for opt in options}
        self.assertEqual(option_values, {"e1", "e2"})
        self.assertNotIn("e3", option_values)

    def test_no_date_filter_offers_every_entity(self):
        filtered = self.app_module.subset_df_dateRange(self.df_master, "Sample_Date", None)
        options = self.app_module._build_entity_dropdown_options(
            filtered, "LOC_ID", "ENTITY_ID", "Sample_Date"
        )
        option_values = {opt["value"] for opt in options}
        self.assertEqual(option_values, {"e1", "e2", "e3"})


class TestMapColorPatchPreservesRelayout(unittest.TestCase):
    """Regression tests for
    docs/agent-context/CUSTOM-CATEGORY-COLOR-BUGS-HANDOFF.md Task 1:
    applying/resetting a color override must recolor the map's markers
    in-place without resetting the user's pan/zoom (layout.map)."""

    def setUp(self):
        self.app_module = _import_app_entrypoint()
        import pandas as pd

        df_coords = pd.DataFrame(
            {
                "LATITUDE": [34.05, 36.16],
                "LONGITUDE": [-118.24, -115.15],
                "LOC_ID": ["Site1", "Site2"],
                "MAP-MARKER-SIZE": [10, 20],
                "Group1": ["A", "B"],
            }
        )
        self.meta_data = {
            "df_coordinate": df_coords.to_json(),
            "cols_key_meta": {"loc_id": "LOC_ID"},
            "dict_generic_colors": {"Group1": {"A": "red", "B": "blue"}},
        }

    def test_patch_map_colors_leaves_layout_map_untouched(self):
        with _fake_callback_context("map-group-dropdown.value"):
            current_fig = self.app_module.update_map(
                "Group1", self.app_module.dump_store(self.meta_data), None, None
            )
        current_fig_dict = current_fig.to_plotly_json()

        overrides = {"Group1": {"A": "#123456"}}
        patched = self.app_module.patch_map_colors(
            self.app_module.dump_store(overrides),
            "Group1",
            self.app_module.dump_store(self.meta_data),
            current_fig_dict,
        )

        # The patch only ever touches "data" (trace) locations - layout.map
        # (center/zoom/bearing/pitch) must never appear in the Patch's
        # operations, so an already-rendered figure's view is left exactly
        # as the user set it.
        operations = patched.to_plotly_json()["operations"]
        self.assertTrue(operations)
        for op in operations:
            self.assertEqual(op["location"][0], "data")

    def test_patch_map_colors_updates_overridden_trace_marker_color(self):
        with _fake_callback_context("map-group-dropdown.value"):
            current_fig = self.app_module.update_map(
                "Group1", self.app_module.dump_store(self.meta_data), None, None
            )
        current_fig_dict = current_fig.to_plotly_json()
        trace_a_idx = next(
            i for i, t in enumerate(current_fig_dict["data"]) if t.get("name") == "A"
        )

        overrides = {"Group1": {"A": "#123456"}}
        patched = self.app_module.patch_map_colors(
            self.app_module.dump_store(overrides),
            "Group1",
            self.app_module.dump_store(self.meta_data),
            current_fig_dict,
        )
        operations = patched.to_plotly_json()["operations"]
        color_ops = {
            tuple(op["location"]): op["params"]["value"] for op in operations
        }
        self.assertEqual(
            color_ops[("data", trace_a_idx, "marker", "color")], "#123456"
        )

    def test_update_map_full_rebuild_still_honors_color_overrides(self):
        # Regression test: apply_color_overrides only writes "session" data,
        # but update_dropdowns (Input("session","data")) resets
        # "map-group-dropdown"'s value on every session write regardless of
        # whether it actually changed - Dash still treats that Output write
        # as a change and re-triggers update_map's Input on it. Before this
        # fix, that rebuild pulled colors straight from
        # meta_data["dict_generic_colors"] with no override merge, so an
        # applied override would flash on screen (via patch_map_colors) and
        # then immediately revert. update_map must merge
        # custom-color-overrides (State) into color_discrete_map so any
        # full rebuild - whatever triggers it - stays override-correct.
        overrides = self.app_module.dump_store({"Group1": {"A": "#123456"}})
        with _fake_callback_context("map-group-dropdown.value"):
            fig = self.app_module.update_map(
                "Group1", self.app_module.dump_store(self.meta_data), None, overrides
            )
        trace_a = next(t for t in fig.data if t.name == "A")
        self.assertEqual(trace_a.marker.color, "#123456")


if __name__ == "__main__":
    unittest.main()

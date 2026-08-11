# %%
import base64
import io
from typing import Any, List, Optional, Tuple

import dash
from dash.dependencies import ALL, Input, Output, State
from dash import ctx
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html, dcc
from flask import Flask

import pandas as pd

from src.plotting import make_map, empty_fig
from src.data_manager import DataPreprocessor, DataPlotter, SessionManager
from src.data_model import ROLE_REGISTRY, ColumnRole, ColumnMapping
from src.data_mapping import ValidationIssue

from src.data_process import json_to_pandas

# from src.compositional_data_functions import clr_transform_scale
from src.dimension_reduction_functions import process_dimension_reduction
from src.callbacks import callback_prevent_initial_output
from src.logging_config import configure_logging, get_logger
from src.error_handling import log_and_prevent_update, log_and_surface_error
from src.store_utils import load_store, dump_store

from src.session_manager import (
    save_to_redis,
    load_from_redis,
    list_keys,
)

from pages.home import (
    create_page_map,
    SIDEBAR_STYLE,
    SIDEBAR_HIDEN,
    CONTENT_STYLE,
    CONTENT_STYLE1,
)

configure_logging()
logger = get_logger(__name__)

# define the Flask server
server = Flask(__name__)
app = dash.Dash(__name__, server=server, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = create_page_map()


@app.callback(
    [
        Output("sidebar", "style"),
        Output("page-content", "style"),
        Output("side_click", "data"),
    ],
    [Input("btn_sidebar", "n_clicks")],
    [
        State("side_click", "data"),
    ],
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.sidebar", fallback=(dash.no_update,) * 3)
def toggle_sidebar(n: Optional[int], nclick: Optional[str]) -> Tuple[dict, dict, str]:
    """Collapse/expand the sidebar when its toggle button is clicked."""
    if n:
        if nclick == "SHOW":
            sidebar_style = SIDEBAR_HIDEN
            content_style = CONTENT_STYLE1
            cur_nclick = "HIDDEN"
        else:
            sidebar_style = SIDEBAR_STYLE
            content_style = CONTENT_STYLE
            cur_nclick = "SHOW"
    else:
        sidebar_style = SIDEBAR_STYLE
        content_style = CONTENT_STYLE
        cur_nclick = "SHOW"

    return sidebar_style, content_style, cur_nclick


# UPLOAD STEP 1: stage the raw CSV, open the column-mapping modal
# Computed once at import time from data_model.ROLE_REGISTRY; read-only for the
# lifetime of the process - safe to share across all users/sessions since it's
# never mutated in place.
_MAPPED_ROLE_SPECS = [spec for spec in ROLE_REGISTRY if spec.role != ColumnRole.GROUP_COLOR]


@app.callback(
    Output("raw-upload-store", "data"),
    Output("mapping-modal", "is_open"),
    Output({"type": "role-mapping", "role": ALL}, "options"),
    Output({"type": "role-mapping", "role": ALL}, "value"),
    Output("mapping-issues-container", "children", allow_duplicate=True),
    Output("mapping-issues-container", "is_open", allow_duplicate=True),
    Input("upload-data", "contents"),
    prevent_initial_call=True,
)
def stage_raw_upload(
    contents: Optional[str],
) -> Tuple[Optional[str], bool, List[list], List[Any], list, bool]:
    """Decode an uploaded CSV's header row and open the column-mapping modal
    with one dropdown per mapped role, populated with the file's columns."""
    if contents is None:
        raise PreventUpdate
    n_roles = len(_MAPPED_ROLE_SPECS)
    try:
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        columns = pd.read_csv(io.BytesIO(decoded), nrows=0).columns.to_list()
    except Exception as e:
        logger.warning("Could not parse uploaded file: %s", e)
        return (
            dash.no_update,
            True,  # keep the modal open so the user sees the error
            [dash.no_update] * n_roles,
            [dash.no_update] * n_roles,
            [html.Li(f"❌ Could not parse uploaded file: {e}")],
            True,
        )
    options = [{"label": col, "value": col} for col in columns]
    reset_values = [[] if spec.multi else None for spec in _MAPPED_ROLE_SPECS]
    return (
        dump_store({"content_string": content_string, "columns": columns}),
        True,  # open the mapping modal
        [options] * n_roles,
        reset_values,
        [],
        False,
    )


# Rebuild the per-plotting-group color dropdowns whenever the plotting-group
# mapping changes, so users can optionally supply a predefined color column
# per group without hand-authoring a fixed number of color dropdowns.
@app.callback(
    Output("mapping-group-color-container", "children"),
    Input({"type": "role-mapping", "role": ColumnRole.PLOTTING_GROUP.value}, "value"),
    State("raw-upload-store", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.upload", fallback=[])
def update_group_color_dropdowns(
    plotting_groups: Optional[List[str]], raw_upload_data: Optional[str]
) -> list:
    """Render one optional color-column dropdown per mapped plotting group."""
    if not plotting_groups or raw_upload_data is None:
        return []
    raw = load_store(raw_upload_data)
    options = [{"label": col, "value": col} for col in raw["columns"]]
    return [
        html.Div(
            [
                html.P(f"Color column for '{group_col}' (optional)"),
                dcc.Dropdown(
                    id={"type": "group-color-mapping", "group": group_col},
                    options=options,
                    value=None,
                    multi=False,
                    placeholder="Auto-generate colors",
                ),
            ],
            style={"margin-bottom": "8px"},
        )
        for group_col in plotting_groups
    ]


def _validation_issues_to_list_items(issues: List[ValidationIssue]) -> List[html.Li]:
    """Render ValidationIssue objects as bulleted list items for the mapping modal."""
    return [
        html.Li(f"{'❌' if issue.severity == 'error' else '⚠️'} [{issue.field}] {issue.message}")
        for issue in issues
    ]


# UPLOAD STEP 2: user confirms their column mapping - build the session
@app.callback(
    Output("meta-data", "data"),
    Output("session", "data"),
    Output("working-data", "data", allow_duplicate=True),
    Output("global-alert-container", "children"),
    Output("mapping-modal", "is_open", allow_duplicate=True),
    Output("mapping-issues-container", "children", allow_duplicate=True),
    Output("mapping-issues-container", "is_open", allow_duplicate=True),
    Input("confirm-mapping-button", "n_clicks"),
    State("raw-upload-store", "data"),
    State({"type": "role-mapping", "role": ALL}, "value"),
    State({"type": "role-mapping", "role": ALL}, "id"),
    State({"type": "group-color-mapping", "group": ALL}, "value"),
    State({"type": "group-color-mapping", "group": ALL}, "id"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.mapping", fallback=(dash.no_update,) * 7)
def confirm_mapping(
    n_clicks: Optional[int],
    raw_upload_data: Optional[str],
    role_values: List[Any],
    role_ids: List[dict],
    group_color_values: List[Optional[str]],
    group_color_ids: List[dict],
) -> tuple:
    """Build a ColumnMapping from the modal's dropdowns, validate/ingest the
    upload via DataPreprocessor, and populate the session stores."""
    if raw_upload_data is None:
        raise PreventUpdate

    raw = load_store(raw_upload_data)
    role_value_map = {id_["role"]: value for id_, value in zip(role_ids, role_values)}
    group_colors = {
        id_["group"]: value for id_, value in zip(group_color_ids, group_color_values) if value
    }

    mapping = ColumnMapping(
        location_id=role_value_map.get(ColumnRole.LOCATION_ID.value),
        latitude=role_value_map.get(ColumnRole.LATITUDE.value),
        longitude=role_value_map.get(ColumnRole.LONGITUDE.value),
        plotting_groups=role_value_map.get(ColumnRole.PLOTTING_GROUP.value) or [],
        numeric_simple=role_value_map.get(ColumnRole.NUMERIC_SIMPLE.value) or [],
        numeric_clr=role_value_map.get(ColumnRole.NUMERIC_CLR.value) or [],
        date=role_value_map.get(ColumnRole.DATE.value) or None,
        marker_symbol=role_value_map.get(ColumnRole.MARKER_SYMBOL.value) or None,
        map_marker_size=role_value_map.get(ColumnRole.MAP_MARKER_SIZE.value) or None,
        group_colors=group_colors,
    )

    data_preprocessor = DataPreprocessor(raw["content_string"], mapping)
    issue_items = _validation_issues_to_list_items(data_preprocessor.validation.issues)

    if data_preprocessor.validation.has_errors:
        return (
            None,
            None,
            None,
            dash.no_update,
            True,  # keep the modal open so the user can fix the mapping
            issue_items,
            True,
        )

    session_dict = data_preprocessor.get_session_dict()

    if data_preprocessor.validation.warnings:
        alert = dbc.Alert(
            "✅ Data loaded with warnings - see mapping details.",
            color="warning",
            dismissable=True,
            duration=10000,
        )
        # mapping-issues-container lives inside mapping-modal's body, so it's
        # invisible if the modal is closed - keep the modal open whenever
        # there are warnings to show. User can dismiss it manually once
        # they've reviewed the details (data is already loaded either way).
        keep_modal_open = True
    else:
        alert = dbc.Alert(
            "✅ All data QA/QC checks passed successfully!",
            color="success",
            dismissable=True,
            duration=5000,
        )
        keep_modal_open = False

    return (
        dump_store(session_dict["meta_data"]),
        dump_store(session_dict),
        None,  # clear working data on new upload
        alert,
        keep_modal_open,
        issue_items,  # warnings, if any, stay visible after closing
        bool(issue_items),
    )


# POPULATE SESSION LOAD OPTIONS
@app.callback(
    Output("user-redis-key-dropdown", "options"),
    Output("user-redis-key-dropdown", "value"),
    Input("button-list-redis-keys", "n_clicks"),
    State("user-session-id", "value"),
)
@log_and_prevent_update("app.callbacks.redis")
def update_redis_keys(n_clicks: Optional[int], session_id: Optional[str]) -> Any:
    """List saved Redis session keys for the given user session ID."""
    if n_clicks is None or session_id is None:
        return dash.no_update
    logger.info("Loading Redis keys for session: %s", session_id)
    keys = list_keys(session_id)
    options = [{"label": key, "value": key} for key in keys]
    return options, options[0]["value"] if options else None


# IMPORT DATA FROM REDIS
@app.callback(
    Output("save-session-output", "children", allow_duplicate=True),
    Output("clear-save-output", "disabled", allow_duplicate=True),
    Output("session", "data", allow_duplicate=True),
    Output("meta-data", "data", allow_duplicate=True),
    Output("working-data", "data", allow_duplicate=True),
    Input("redis-import-button", "n_clicks"),
    State("user-session-id", "value"),
    State("user-redis-key-dropdown", "value"),
    prevent_initial_call=True,
)
@log_and_surface_error(
    "app.callbacks.redis",
    error_output_index=0,
    fallback=(False, dash.no_update, dash.no_update, dash.no_update),
)
def load_session_data(
    n_clicks: Optional[int], session_id: Optional[str], key: Optional[str]
) -> Tuple[str, bool, Any, Any, Any]:
    """Load a previously saved session blob from Redis and repopulate the stores."""
    if session_id is None or key is None:
        return (
            "No session ID or key provided.",
            False,  # Disable clear save output
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )
    logger.info("Loading session - User: %s, Session: %s", session_id, key)
    session = load_store(load_from_redis(session_id, key))
    if session is None:
        return (
            f"No session data found for user '{session_id}' with key '{key}'.",
            False,  # Disable clear save output
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )
    logger.info("Session loaded successfully: %s", key)
    meta_data = session.get("meta_data", {})
    working_data = session.get("working_data", {})
    if not working_data:
        working_data = None
    else:
        working_data = dump_store(working_data)

    return (
        f"Session '{key}' loaded successfully for user '{session_id}'.",
        False,
        dump_store(session),
        dump_store(meta_data),
        working_data,
    )


# STORE SESSION IN REDIS
@app.callback(
    Output("save-session-output", "children"),
    Output("clear-save-output", "disabled"),
    Input("redis-save-button", "n_clicks"),
    State("session", "data"),
    State("user-session-id", "value"),
    State("user-redis-key-text", "value"),
    prevent_initial_call=True,
)
@log_and_surface_error("app.callbacks.redis", error_output_index=0, fallback=(False,))
def save_session_data_to_redis(
    n_clicks: Optional[int],
    session: Optional[str],
    session_id: Optional[str],
    key: Optional[str],
) -> Tuple[str, bool]:
    """Save the current session blob to Redis under `session_id`/`key`."""
    if session is None or session_id is None or key is None or len(key) == 0:
        return "No session data to save or missing session ID/key.", False
    logger.info("Saving session - User: %s, Session: %s", session_id, key)
    save_to_redis(session_id, key, session)
    logger.info("Session saved successfully: %s", key)
    return (
        f"Session '{key}' saved successfully for user '{session_id}'.\nExpires in 1 week.",
        False,
    )


# DOWNLOAD SESSION AS JSON
@app.callback(
    Output("download-session-json", "data"),
    Input("download-session-button", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.redis")
def download_session_as_json(n_clicks: Optional[int], session: Optional[str]) -> Any:
    """Offer the current session blob as a downloadable JSON file."""
    if session is None:
        return dash.no_update
    logger.info("Downloading session as JSON...")
    return dcc.send_string(session, filename="session_data.json", mime_type="application/json")


# CLEAR SAVE OUTPUT
@app.callback(
    Output("save-session-output", "children", allow_duplicate=True),
    Output("clear-save-output", "disabled", allow_duplicate=True),
    Input("clear-save-output", "n_intervals"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.redis", fallback=(dash.no_update,) * 2)
def clear_save_message(n: Optional[int]) -> Tuple[None, bool]:
    """Clear the save/load status message once its display interval elapses."""
    return None, True  # Clear and disable interval


# GENERATE DATA RANGE SLIDER
@app.callback(
    Output("date-range-slider", "min"),
    Output("date-range-slider", "max"),
    Output("date-range-slider", "marks"),
    Output("date-range-slider", "value"),
    Input("session", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.session", fallback=(0, 0, {}, [0, 0]))
def update_date_range_slider(
    session: Optional[str],
) -> Tuple[int, int, dict, List[int]]:
    """Rebuild the date-range slider's bounds/marks from the mapped date column."""
    if session is None:
        return 0, 0, {}, [0, 0]
    session = load_store(session)
    col_date = session["meta_data"]["cols_key_meta"]["date"]
    if not col_date:
        # No date column mapped - date-range filtering is disabled.
        return 0, 0, {}, [0, 0]
    df_master = json_to_pandas(session, "df_master", col_date)
    date_min = int(df_master[col_date].dt.year.min())
    date_max = int(df_master[col_date].dt.year.max())
    marks = {i: str(i) for i in range(date_min, date_max + 1, 5)}
    marks[date_max] = str(date_max)
    return date_min, date_max, marks, [date_min, date_max]


# GENERATE DROPDOWNS FOR GROUPS
@app.callback(
    [
        Output("map-group-dropdown", "options"),
        Output("map-group-dropdown", "value"),
        Output("plot-group-dropdown-1", "options"),
        Output("plot-group-dropdown-1", "value"),
        Output("plot-group-dropdown-2", "options"),
        Output("plot-group-dropdown-2", "value"),
        Output("feature-selection-dropdown", "options"),
        Output("feature-selection-dropdown", "value"),
        Output("loc-id-dropdown", "options"),
        Output("loc-id-dropdown", "value"),
        Output("pmap-neighbors", "value"),
    ],
    Input("session", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.session", fallback=([],) * 11)
def update_dropdowns(session: Optional[str]) -> tuple:
    """Populate every plotting/feature/location dropdown from the session's
    remembered plotting_data defaults."""
    if session is None:
        return [], [], [], [], [], [], [], [], [], [], []
    session = load_store(session)
    plotting_data = session["plotting_data"]
    return (
        plotting_data["map_group_dropdown_options"],
        plotting_data["map_group_dropdown_value"],
        plotting_data["plot_group_dropdown_1_options"],
        plotting_data["plot_group_dropdown_1_value"],
        plotting_data["plot_group_dropdown_2_options"],
        plotting_data["plot_group_dropdown_2_value"],
        plotting_data["feature_selection_dropdown_options"],
        plotting_data["feature_selection_dropdown_value"],
        plotting_data["loc_id_dropdown_options"],
        plotting_data["loc_id_dropdown_value"],
        plotting_data["pmap_neighbors"],  # Default value for neighbors
    )


# GENERATE THE MAP
@app.callback(
    Output("map", "figure"),
    [Input("map-group-dropdown", "value")],
    [Input("meta-data", "data")],
    State("map-relayout-store", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.map", fallback=empty_fig())
@callback_prevent_initial_output
def update_map(
    map_group: Optional[str], meta_data: Optional[str], relayoutData: Optional[dict]
) -> Any:
    """Rebuild the map figure for the selected plotting group, preserving the
    user's current pan/zoom state where possible."""
    if meta_data is None or not map_group:
        return empty_fig()
    # find what is triggering the callback
    ctx_call = ctx.triggered_id

    meta_data = load_store(meta_data)

    df_coords = pd.read_json(io.StringIO(meta_data["df_coordinate"]))

    col_color = map_group
    color_discrete_map = meta_data["dict_generic_colors"].get(col_color)
    if color_discrete_map is None:
        # Stale/mismatched dropdown state (e.g. group renamed after this
        # dropdown's options were last built) - fall back to an
        # auto-generated palette instead of KeyError-ing.
        logger.debug("No color mapping found for group '%s'; using default palette", col_color)
    dict_kwargs_map = {
        "color": col_color,
        "color_discrete_map": color_discrete_map,
        "custom_data": meta_data["cols_key_meta"]["loc_id"],
        "hover_name": meta_data["cols_key_meta"]["loc_id"],
    }
    fig = make_map(df_coords, **dict_kwargs_map)
    if ctx_call == "map-group-dropdown" and relayoutData:
        allowed_relayout_keys = {
            "map.center",
            "map.zoom",
            "map.bearing",
            "map.pitch",
        }
        relayoutData = {k: v for k, v in relayoutData.items() if k in allowed_relayout_keys}
        if relayoutData:
            fig.update_layout(relayoutData)
    return fig


# STORE THE MAP RELAYOUT DATA
@app.callback(
    Output("map-relayout-store", "data"),
    Input("map", "relayoutData"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.map")
def store_map_relayout_data(relayoutData: Optional[dict]) -> Any:
    """Remember the map's current pan/zoom/bearing/pitch across re-renders."""
    if relayoutData is None:
        return dash.no_update
    return relayoutData


# PROCESS WORKING DATA
@app.callback(
    Output("working-data", "data"),
    Output("session", "data", allow_duplicate=True),
    [
        Input(component_id="apply-button", component_property="n_clicks"),
    ],
    [
        State("session", "data"),
        State(component_id="feature-selection-dropdown", component_property="value"),
        State(component_id="loc-id-dropdown", component_property="value"),
        State(component_id="pmap-neighbors", component_property="value"),
        State("map-group-dropdown", "value"),
        State("plot-group-dropdown-1", "value"),
        State("plot-group-dropdown-2", "value"),
    ],
    prevent_initial_call=True,
)
@callback_prevent_initial_output
def process_working_data(
    n_clicks: Optional[int],
    session: Optional[str],
    feature_selection: Optional[List[str]],
    loc_id_selection: Optional[List[str]],
    n_neighbors: Optional[int],
    map_group: Optional[str],
    plot_group_1: Optional[str],
    plot_group_2: Optional[str],
) -> Tuple[Optional[str], Any]:
    """Run PCA/PaCMAP on the selected analytes/locations and store the results."""
    if session is None:
        return None, dash.no_update
    if not feature_selection or not loc_id_selection:
        return None, dash.no_update

    session = load_store(session)
    meta_data = session["meta_data"]
    df_master = json_to_pandas(session, "df_master", meta_data["cols_key_meta"]["date"])

    if not isinstance(n_neighbors, int) or not (1 <= n_neighbors < len(df_master)):
        logger.warning(
            "Invalid pmap-neighbors=%r for %d row(s); skipping dimension reduction",
            n_neighbors,
            len(df_master),
        )
        return None, dash.no_update

    cols_meta = meta_data["cols_key_plot"]["meta"]
    cols_numeric_simple = meta_data["cols_key_plot"]["numeric_simple"]
    cols_numeric_clr = meta_data["cols_key_plot"]["numeric_clr"]
    col_loc_id = meta_data["cols_key_meta"]["loc_id"]
    plot_components_pca, plot_components_pmap = process_dimension_reduction(
        df_master,
        col_loc_id,
        cols_meta,
        cols_numeric_simple,
        cols_numeric_clr,
        feature_selection,
        loc_id_selection,
        n_neighbors,
    )

    dict_working_data = SessionManager.package_plotting_data(
        plot_components_pca, plot_components_pmap, meta_data
    )
    session["working_data"] = dict_working_data
    dct_plotting_data = {
        "feature_selection_dropdown_value": feature_selection,
        "loc_id_dropdown_value": loc_id_selection,
        "map_group_dropdown_value": map_group,
        "plot_group_dropdown_1_value": plot_group_1,
        "plot_group_dropdown_2_value": plot_group_2,
        "pmap_neighbors": n_neighbors,
    }
    session["plotting_data"].update(dct_plotting_data)
    return dump_store(dict_working_data), dump_store(session)


# grab the selected data from the map and update the loc_id-dropdown
@app.callback(
    Output("loc-id-dropdown", "value", allow_duplicate=True),
    Input("map-selected-snapshot", "n_clicks"),
    State("map", "selectedData"),
    State("meta-data", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.map", fallback=[])
def update_loc_id_dropdown(
    n_clicks: Optional[int], selectedData: Optional[dict], meta_data: Optional[str]
) -> List[str]:
    """Sync the location-ID dropdown to the map's current lasso/box selection."""
    if selectedData is None:
        if meta_data is None:
            return []
        meta_data = load_store(meta_data)
        return meta_data["loc_id_all"]
    selected_loc_ids = []
    for point in selectedData.get("points", []):
        customdata = point.get("customdata")
        if not customdata:
            logger.debug("Selected map point missing customdata; skipping")
            continue
        selected_loc_ids.append(customdata[0])
    return selected_loc_ids


# plotting callbacks
@app.callback(
    [
        Output(component_id="pca-plot", component_property="figure"),
        Output(component_id="pmap-plot", component_property="figure"),
    ],
    [
        Input("working-data", "data"),
        Input("map", "selectedData"),
        Input("plot-group-dropdown-1", "value"),
        Input("plot-group-dropdown-2", "value"),
        Input("date-range-slider", "value"),
    ],
    [
        State(component_id="meta-data", component_property="data"),
        State(component_id="pmap-neighbors", component_property="value"),
    ],
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.plotting", fallback=DataPlotter.empty_figs())
def plot_data(
    working_data: Optional[str],
    selectedData: Optional[dict],
    plot_group_1: Optional[str],
    plot_group_2: Optional[str],
    date_range: Optional[List[int]],
    meta_data: Optional[str],
    n_neighbors: Optional[int],
) -> Tuple[Any, Any]:
    """Rebuild the PCA and PaCMAP biplots from the current working data/selection."""
    if working_data is None:
        return DataPlotter.empty_figs()

    data_plotter = DataPlotter(
        working_data,
        meta_data,
        selectedData,
        [plot_group_1, plot_group_2],
        date_range,
    )
    fig_pca = data_plotter.plot_pca()
    fig_pmap = data_plotter.plot_pmap(n_neighbors=n_neighbors)
    return fig_pca, fig_pmap


# TURN OFF FOR DEPLOYMENT WITH GUNICORN
port = 8050
if __name__ == "__main__":
    app.run(debug=False, port=port)
    # app.run(debug=True, port=port)

# %%
import base64
import io
from typing import Any, Dict, List, Optional, Tuple

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

from src.data_process import (
    json_to_pandas,
    merge_color_overrides,
    build_color_mapping_export_df,
    build_custom_group_export_df,
)

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


# COLOR PICKER: open the modal, populate the group dropdown
@app.callback(
    Output("color-picker-group-dropdown", "options"),
    Output("color-picker-group-dropdown", "value"),
    Output("color-picker-modal", "is_open"),
    Input("open-color-picker-button", "n_clicks"),
    State("meta-data", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.color_picker", fallback=([], None, False))
def populate_color_picker_group_dropdown(
    n_clicks: Optional[int], meta_data: Optional[str]
) -> Tuple[list, Optional[str], bool]:
    """Populate the color-picker's group dropdown with every active plotting
    group (including user-created custom groups) and open the modal."""
    if meta_data is None:
        raise PreventUpdate
    meta_data = load_store(meta_data)
    plotting_groups = meta_data["cols_key_meta"]["plotting_groups"]
    return plotting_groups, None, True


def _color_swatch_row(value: Any, hex_color: str) -> html.Div:
    """One labeled `<input type="color">` row for the color-picker modal.
    dash.html has no Input component (that's dcc.Input, which renders a real
    `<input>` tag and does accept type="color" - html.Button/html.Span etc.
    are the only interactive dash.html elements)."""
    return html.Div(
        [
            html.Span(str(value), style={"margin-right": "8px"}),
            dcc.Input(
                type="color",
                id={"type": "color-swatch-input", "value": str(value)},
                value=hex_color,
            ),
        ],
        style={"margin-bottom": "4px"},
    )


# COLOR PICKER: render one swatch row per category value of the selected group
@app.callback(
    Output("color-picker-value-list", "children"),
    Input("color-picker-group-dropdown", "value"),
    State("meta-data", "data"),
    State("custom-color-overrides", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.color_picker", fallback=[])
def populate_color_picker_value_list(
    group_col: Optional[str], meta_data: Optional[str], custom_color_overrides: Optional[str]
) -> list:
    """Render a color-input row per value of the selected plotting group,
    pre-filled with its effective (override-merged) color."""
    if not group_col or meta_data is None:
        return []
    meta_data = load_store(meta_data)
    overrides = load_store(custom_color_overrides) or {}
    default_colors = meta_data["dict_generic_colors"].get(group_col, {})
    effective_colors = merge_color_overrides({group_col: default_colors}, overrides)[group_col]
    return [
        _color_swatch_row(value, hex_color)
        for value, hex_color in sorted(effective_colors.items(), key=lambda kv: str(kv[0]))
    ]


# COLOR PICKER: commit the picked hex colors into session["custom_color_overrides"]
@app.callback(
    Output("session", "data", allow_duplicate=True),
    Output("custom-color-overrides", "data", allow_duplicate=True),
    Output("color-picker-modal", "is_open", allow_duplicate=True),
    Input("apply-color-overrides-button", "n_clicks"),
    State("color-picker-group-dropdown", "value"),
    State({"type": "color-swatch-input", "value": ALL}, "value"),
    State({"type": "color-swatch-input", "value": ALL}, "id"),
    State("session", "data"),
    State("custom-color-overrides", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.color_picker", fallback=(dash.no_update,) * 3)
def apply_color_overrides(
    n_clicks: Optional[int],
    group_col: Optional[str],
    swatch_values: List[str],
    swatch_ids: List[dict],
    session: Optional[str],
    custom_color_overrides: Optional[str],
) -> Tuple[str, str, bool]:
    """Write the modal's current swatch values into
    session["custom_color_overrides"][group_col] and close the modal."""
    if not group_col or session is None:
        raise PreventUpdate
    session = load_store(session)
    overrides = load_store(custom_color_overrides) or {}
    group_overrides = dict(overrides.get(group_col, {}))
    for id_, hex_color in zip(swatch_ids, swatch_values):
        group_overrides[id_["value"]] = hex_color
    overrides[group_col] = group_overrides
    session["custom_color_overrides"] = overrides
    logger.info("Applied %d color override(s) for group '%s'", len(group_overrides), group_col)
    return dump_store(session), dump_store(overrides), False


# COLOR PICKER: reset a group's colors back to the auto-generated/predefined defaults
@app.callback(
    Output("session", "data", allow_duplicate=True),
    Output("custom-color-overrides", "data", allow_duplicate=True),
    Output("color-picker-value-list", "children", allow_duplicate=True),
    Input("reset-color-overrides-button", "n_clicks"),
    State("color-picker-group-dropdown", "value"),
    State("meta-data", "data"),
    State("session", "data"),
    State("custom-color-overrides", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.color_picker", fallback=(dash.no_update,) * 3)
def reset_color_overrides(
    n_clicks: Optional[int],
    group_col: Optional[str],
    meta_data: Optional[str],
    session: Optional[str],
    custom_color_overrides: Optional[str],
) -> Tuple[str, str, list]:
    """Drop `group_col`'s entry from custom_color_overrides, falling back to
    the default palette, and re-render the now-unoverridden swatch rows."""
    if not group_col or session is None or meta_data is None:
        raise PreventUpdate
    session = load_store(session)
    meta_data = load_store(meta_data)
    overrides = load_store(custom_color_overrides) or {}
    overrides.pop(group_col, None)
    session["custom_color_overrides"] = overrides
    default_colors = meta_data["dict_generic_colors"].get(group_col, {})
    rows = [
        _color_swatch_row(value, hex_color)
        for value, hex_color in sorted(default_colors.items(), key=lambda kv: str(kv[0]))
    ]
    logger.info("Reset color overrides for group '%s'", group_col)
    return dump_store(session), dump_store(overrides), rows


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
    user's current pan/zoom state where possible.

    Reverted: this used to also take custom-color-overrides as an Input so
    the map recolored instantly on Apply/Reset, but that made every color
    change rebuild the figure on a trigger other than "map-group-dropdown",
    which skipped the relayoutData-reapply branch below and reset the view -
    see docs/agent-context/CUSTOM-CATEGORY-COLOR-BUGS-HANDOFF.md. Color
    overrides now apply to the map the next time it naturally rebuilds
    (group dropdown change or new upload) instead of live.
    """
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


def _build_entity_dropdown_options(
    df_master: pd.DataFrame, loc_id_col: str, entity_id_col: str, date_col: Optional[str]
) -> List[dict]:
    """`{label: "loc_id (date)", value: entity_id}` per row - the assignment
    dropdown's option list for the custom-group-creation modal."""
    if date_col:
        labels = df_master[loc_id_col].astype(str) + " (" + df_master[date_col].astype(str) + ")"
    else:
        labels = df_master[loc_id_col].astype(str)
    return [
        {"label": label, "value": entity_id}
        for label, entity_id in zip(labels, df_master[entity_id_col])
    ]


def _render_custom_group_preview(draft: Dict[str, List[str]]) -> List[html.P]:
    """`"CategoryA: 12 sample(s)"` per committed category in the draft."""
    return [html.P(f"{name}: {len(ids)} sample(s)") for name, ids in draft.items()]


# CUSTOM GROUP: manual entry - open the panel, list every entity ID
@app.callback(
    Output("custom-group-modal", "is_open", allow_duplicate=True),
    Output("custom-group-assign-entity-dropdown", "options"),
    Output("custom-group-assign-entity-dropdown", "value"),
    Output("custom-group-draft", "data"),
    Output("custom-group-categories-preview", "children"),
    Input("open-custom-group-button", "n_clicks"),
    State("session", "data"),
    State("custom-group-draft", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.custom_group", fallback=(dash.no_update,) * 5)
def open_blank_custom_group_modal(
    n_clicks: Optional[int], session: Optional[str], existing_draft: Optional[dict]
) -> tuple:
    """Open the custom-group panel with an empty pending selection.

    Preserves any already-committed categories in `existing_draft` - this is
    just "(re)open the panel", not "start over". The draft only actually
    resets on Cancel/Finish (see cancel_custom_group_modal/
    finalize_custom_group).
    """
    if session is None:
        raise PreventUpdate
    session = load_store(session)
    meta_data = session["meta_data"]
    cols_key_meta = meta_data["cols_key_meta"]
    df_master = json_to_pandas(session, "df_master", cols_key_meta["date"])
    options = _build_entity_dropdown_options(
        df_master, cols_key_meta["loc_id"], cols_key_meta["entity_id"], cols_key_meta["date"]
    )
    draft = existing_draft or {}
    return True, options, [], draft, _render_custom_group_preview(draft)


# CUSTOM GROUP: pre-populate the assignment dropdown from a map/plot lasso select
@app.callback(
    Output("custom-group-modal", "is_open", allow_duplicate=True),
    Output("custom-group-assign-entity-dropdown", "options", allow_duplicate=True),
    Output("custom-group-assign-entity-dropdown", "value", allow_duplicate=True),
    Output("custom-group-draft", "data", allow_duplicate=True),
    Output("custom-group-categories-preview", "children", allow_duplicate=True),
    Input("create-group-from-selection-button", "n_clicks"),
    State("map", "selectedData"),
    State("pca-plot", "selectedData"),
    State("pmap-plot", "selectedData"),
    State("session", "data"),
    State("custom-group-draft", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.custom_group", fallback=(dash.no_update,) * 5)
def populate_custom_group_from_selection(
    n_clicks: Optional[int],
    map_selected: Optional[dict],
    pca_selected: Optional[dict],
    pmap_selected: Optional[dict],
    session: Optional[str],
    existing_draft: Optional[dict],
) -> tuple:
    """Open the custom-group panel pre-populated with the union of the map's
    and both biplots' current lasso/box selection, converted to entity IDs.

    Since this panel is a non-blocking dbc.Offcanvas (not a dbc.Modal), the
    map/plots stay interactive while it's open - the user can lasso, commit a
    category, lasso a different set of points, click this button again to
    load the new selection, and commit another category, repeating as many
    times as needed. `existing_draft` (already-committed categories) is
    preserved across every call - only the pending (uncommitted) selection in
    the dropdown is replaced.

    Map selections carry only `loc_id` in `customdata` (see `update_map`), so
    they're expanded to every entity_id at that location - i.e. every sample
    date at each selected site, not just the specific point clicked.
    """
    if session is None:
        raise PreventUpdate
    session = load_store(session)
    meta_data = session["meta_data"]
    cols_key_meta = meta_data["cols_key_meta"]
    loc_id_col = cols_key_meta["loc_id"]
    entity_id_col = cols_key_meta["entity_id"]
    date_col = cols_key_meta["date"]
    df_master = json_to_pandas(session, "df_master", date_col)

    selected_entity_ids: List[str] = []
    if map_selected:
        selected_loc_ids = [
            point["customdata"][0] for point in map_selected.get("points", []) if point.get("customdata")
        ]
        if selected_loc_ids:
            # loc_id is coerced to string at ingestion (DataPreprocessor), but
            # a JSON round-trip through the session/dcc.Store can let pandas'
            # dtype inference turn a numeric-looking loc_id column back into
            # int64 (see data_manager.py's astype(str) comment) - compare as
            # strings on both sides so a numeric loc_id in customdata still
            # matches.
            selected_loc_ids_str = {str(v) for v in selected_loc_ids}
            selected_entity_ids.extend(
                df_master[df_master[loc_id_col].astype(str).isin(selected_loc_ids_str)][
                    entity_id_col
                ].tolist()
            )
    for plot_selected in (pca_selected, pmap_selected):
        if plot_selected:
            selected_entity_ids.extend(
                point["customdata"][1]
                for point in plot_selected.get("points", [])
                if point.get("customdata") and len(point["customdata"]) > 1
            )

    # de-dupe, preserve order
    selected_entity_ids = list(dict.fromkeys(selected_entity_ids))

    options = _build_entity_dropdown_options(df_master, loc_id_col, entity_id_col, date_col)
    draft = existing_draft or {}
    return True, options, selected_entity_ids, draft, _render_custom_group_preview(draft)


# CUSTOM GROUP: commit a category name + its entity-ID selection into the draft
@app.callback(
    Output("custom-group-draft", "data", allow_duplicate=True),
    Output("custom-group-categories-preview", "children", allow_duplicate=True),
    Output("custom-group-category-name-input", "value", allow_duplicate=True),
    Output("custom-group-assign-entity-dropdown", "value", allow_duplicate=True),
    Input("custom-group-commit-category-button", "n_clicks"),
    State("custom-group-category-name-input", "value"),
    State("custom-group-assign-entity-dropdown", "value"),
    State("custom-group-draft", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.custom_group", fallback=(dash.no_update,) * 4)
def commit_category_to_draft(
    n_clicks: Optional[int],
    category_name: Optional[str],
    entity_ids: Optional[List[str]],
    draft: Optional[dict],
) -> Tuple[dict, list, None, list]:
    """Add/overwrite one category in the in-progress draft and clear the
    category-name/selection inputs so the user can add another."""
    if not category_name or not category_name.strip() or not entity_ids:
        raise PreventUpdate
    draft = draft or {}
    draft[category_name] = entity_ids
    return draft, _render_custom_group_preview(draft), None, []


# CUSTOM GROUP: finalize - create the column and assign every committed category
@app.callback(
    Output("session", "data", allow_duplicate=True),
    Output("meta-data", "data", allow_duplicate=True),
    Output("custom-group-modal", "is_open", allow_duplicate=True),
    Output("custom-group-draft", "data", allow_duplicate=True),
    Output("global-alert-container", "children", allow_duplicate=True),
    Input("custom-group-finalize-button", "n_clicks"),
    State("custom-group-name-input", "value"),
    State("custom-group-draft", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
@log_and_surface_error(
    "app.callbacks.custom_group",
    error_output_index=4,
    fallback=(dash.no_update, dash.no_update, dash.no_update, dash.no_update),
)
def finalize_custom_group(
    n_clicks: Optional[int],
    new_col_name: Optional[str],
    draft: Optional[dict],
    session: Optional[str],
) -> Tuple[str, str, bool, dict, Any]:
    """Create the new group column from the draft's categories and populate
    every downstream dropdown/color dict with it."""
    if not new_col_name or not new_col_name.strip():
        return (
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dbc.Alert("Custom group name cannot be empty.", color="danger", dismissable=True),
        )
    if not draft:
        return (
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dbc.Alert(
                "Add at least one category before creating the group.",
                color="danger",
                dismissable=True,
            ),
        )

    session = load_store(session)
    session = SessionManager.add_custom_group(session, new_col_name.strip(), draft)
    alert = dbc.Alert(
        f"✅ Custom group '{new_col_name}' created. Click 'Apply' to include it in "
        "PCA/PaCMAP plots.",
        color="success",
        dismissable=True,
        duration=10000,
    )
    return dump_store(session), dump_store(session["meta_data"]), False, {}, alert


# CUSTOM GROUP: cancel out of the modal without creating anything
@app.callback(
    Output("custom-group-modal", "is_open", allow_duplicate=True),
    Output("custom-group-draft", "data", allow_duplicate=True),
    Input("custom-group-cancel-button", "n_clicks"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.custom_group", fallback=(dash.no_update,) * 2)
def cancel_custom_group_modal(n_clicks: Optional[int]) -> Tuple[bool, dict]:
    """Close the custom-group modal and discard its in-progress draft."""
    return False, {}


# EXPORT: color mapping CSV (ENTITY_ID -> CATEGORY_COL -> CATEGORY_VALUE -> CATEGORY_COLOR)
@app.callback(
    Output("download-color-mapping-csv", "data"),
    Input("download-color-mapping-button", "n_clicks"),
    State("session", "data"),
    State("custom-color-overrides", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.export")
def download_color_mapping_csv(
    n_clicks: Optional[int], session: Optional[str], custom_color_overrides: Optional[str]
) -> Any:
    """Export every row's effective (override-merged) color per plotting group."""
    if session is None:
        return dash.no_update
    session = load_store(session)
    meta_data = session["meta_data"]
    overrides = load_store(custom_color_overrides) or {}
    effective_colors = merge_color_overrides(meta_data["dict_generic_colors"], overrides)
    df_master = json_to_pandas(session, "df_master", meta_data["cols_key_meta"]["date"])
    df_export = build_color_mapping_export_df(
        df_master,
        meta_data["cols_key_meta"]["plotting_groups"],
        meta_data["cols_key_meta"]["entity_id"],
        effective_colors,
    )
    logger.info("Downloading color mapping CSV (%d rows)", len(df_export))
    return dcc.send_data_frame(df_export.to_csv, "color_mapping.csv", index=False)


# EXPORT: custom group assignment CSV (ENTITY_ID -> LOCATION_ID -> DATE -> [custom columns...])
@app.callback(
    Output("download-custom-groups-csv", "data"),
    Input("download-custom-groups-button", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
@log_and_prevent_update("app.callbacks.export")
def download_custom_groups_csv(n_clicks: Optional[int], session: Optional[str]) -> Any:
    """Export the ENTITY_ID -> LOCATION_ID -> DATE -> custom-group-columns lookup."""
    if session is None:
        return dash.no_update
    session = load_store(session)
    meta_data = session["meta_data"]
    custom_group_columns = meta_data.get("custom_group_columns", [])
    if not custom_group_columns:
        logger.warning("Download custom groups CSV requested but no custom groups exist yet.")
        return dash.no_update
    cols_key_meta = meta_data["cols_key_meta"]
    df_master = json_to_pandas(session, "df_master", cols_key_meta["date"])
    df_export = build_custom_group_export_df(
        df_master,
        cols_key_meta["entity_id"],
        cols_key_meta["loc_id"],
        cols_key_meta["date"],
        custom_group_columns,
    )
    logger.info("Downloading custom groups CSV (%d rows)", len(df_export))
    return dcc.send_data_frame(df_export.to_csv, "custom_groups.csv", index=False)


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
        Input("custom-color-overrides", "data"),
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
    custom_color_overrides: Optional[str],
    meta_data: Optional[str],
    n_neighbors: Optional[int],
) -> Tuple[Any, Any]:
    """Rebuild the PCA and PaCMAP biplots from the current working data/selection."""
    if working_data is None:
        return DataPlotter.empty_figs()

    overrides = load_store(custom_color_overrides) or {}
    if overrides and meta_data is not None:
        meta_data_loaded = load_store(meta_data)
        meta_data_loaded["dict_generic_colors"] = merge_color_overrides(
            meta_data_loaded["dict_generic_colors"], overrides
        )
        meta_data = dump_store(meta_data_loaded)

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

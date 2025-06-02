# %%
import io
import json

import dash
from dash.dependencies import Input, Output, State
from dash import ctx
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html, dcc
from flask import Flask

import pandas as pd

from src.plotting import make_map, empty_fig
from src.data_manager import DataPreprocessor, DataPlotter, SessionManager

from src.data_process import json_to_pandas, pandas_to_json

# from src.compositional_data_functions import clr_transform_scale
from src.dimension_reduction_functions import process_dimension_reduction
from src.callbacks import callback_prevent_initial_output

from src.session_manager import (
    save_to_redis,
    load_from_redis,
    list_keys,
    key_exists,
)

from pages.home import (
    create_page_map,
    SIDEBAR_STYLE,
    SIDEBAR_HIDEN,
    CONTENT_STYLE,
    CONTENT_STYLE1,
)

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
def toggle_sidebar(n, nclick):
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


# IMPORT DATA FROM .CSV
# @app.callback(
#     Output("meta-data", "data"),  # still needed
#     Output("session", "data"),
#     Output("working-data", "data", allow_duplicate=True),  # need to clear output
#     Input("upload-data", "contents"),
#     prevent_initial_call=True,
# )
# def process_data(contents):
#     if contents is None:
#         return None, None, None  # No data to process
#     content_type, content_string = contents.split(",")
#     data_preprocessor = DataPreprocessor(content_string)
#     session_dict = data_preprocessor.get_session_dict()
#     return (
#         json.dumps(session_dict["meta_data"]),
#         json.dumps(session_dict),
#         None,  # Clear working data on new upload
#     )


@app.callback(
    Output("meta-data", "data"),
    Output("session", "data"),
    Output("working-data", "data", allow_duplicate=True),
    Output("global-alert-container", "children"),  # ← NEW OUTPUT
    Input("upload-data", "contents"),
    prevent_initial_call=True,
)
def process_data(contents):
    if contents is None:
        raise PreventUpdate
    content_type, content_string = contents.split(",")
    data_preprocessor = DataPreprocessor(content_string)
    session_dict = data_preprocessor.get_session_dict()

    alerts = []
    results = data_preprocessor.run_all_checks()
    if results["lat_lon_check"]:
        alerts.append("❌ Some lat/lon values are out of bounds.")
    if results["numeric_no_nan_check"]:
        alerts.append("❌ Missing values found in numeric columns.")
    if results["clr_columns_positive_check"]:
        alerts.append("❌ CLR values must be real and > 0.")
    if len(results["color_columns_check"]) > 0:
        invalids_string = ", ".join(results["color_columns_check"])
        alerts.append(
            f"❌ Some color codes are not valid hex values. Must start with '#' only including 0-9 and letters a-f. Bad codes: {invalids_string}"
        )

    if alerts:
        alert = dbc.Alert(
            " ".join(alerts),
            color="danger",
            dismissable=True,
            duration=10000,  # 10 seconds
        )
        return (
            None,
            None,
            None,  # Clear working data on new upload
            alert,  # Return the alert with all issues
        )
    else:
        alert = dbc.Alert(
            "✅ All data QA/QC checks passed successfully!",
            color="success",
            dismissable=True,
            duration=5000,  # 5 seconds
        )

    return (
        json.dumps(session_dict["meta_data"]),
        json.dumps(session_dict),
        None,
        alert,
    )


# POPULATE SESSION LOAD OPTIONS
@app.callback(
    Output("user-redis-key-dropdown", "options"),
    Output("user-redis-key-dropdown", "value"),
    Input("button-list-redis-keys", "n_clicks"),
    State("user-session-id", "value"),
)
def update_redis_keys(n_clicks, session_id):
    if n_clicks is None or session_id is None:
        return dash.no_update
    print(f"Loading Redis keys for session: {session_id}")
    try:
        keys = list_keys(session_id)
    except Exception as e:
        print(f"Error loading keys from Redis: {e}")
        return dash.no_update
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
def load_session_data(n_clicks, session_id, key):
    if session_id is None or key is None:
        return (
            "No session ID or key provided.",
            False,  # Disable clear save output
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )
    print(f"Loading session - User: {session_id}, Session: {key}")
    session = load_from_redis(session_id, key)
    session = json.loads(session) if session else None
    if session is None:
        return (
            f"No session data found for user '{session_id}' with key '{key}'.",
            False,  # Disable clear save output
            dash.no_update,
            dash.no_update,
        )
    print(f"Session loaded successfully: {key}")
    meta_data = session.get("meta_data", {})
    working_data = session.get("working_data", {})
    if not working_data:
        working_data = None
    else:
        working_data = json.dumps(working_data)

    return (
        f"Session '{key}' loaded successfully for user '{session_id}'.",
        False,
        json.dumps(session),
        json.dumps(meta_data),
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
def save_session_data_to_redis(n_clicks, session, session_id, key):
    if session is None or session_id is None or key is None or len(key) == 0:
        return "No session data to save or missing session ID/key.", False
    print(f"Saving session - User: {session_id}, Session: {key}")
    try:
        save_to_redis(session_id, key, session)
        print(f"Session saved successfully: {key}")
        return (
            f"Session '{key}' saved successfully for user '{session_id}'.\nExpires in 1 week.",
            False,
        )
    except Exception as e:
        print(f"Error saving session to Redis: {e}")
        return f"Error saving session: {e}", False


# DOWNLOAD SESSION AS JSON
@app.callback(
    Output("download-session-json", "data"),
    Input("download-session-button", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def download_session_as_json(n_clicks, session):
    if session is None:
        return dash.no_update
    print("Downloading session as JSON...")
    return dcc.send_string(
        session, filename="session_data.json", mime_type="application/json"
    )


# CLEAR SAVE OUTPUT
@app.callback(
    Output("save-session-output", "children", allow_duplicate=True),
    Output("clear-save-output", "disabled", allow_duplicate=True),
    Input("clear-save-output", "n_intervals"),
    prevent_initial_call=True,
)
def clear_save_message(n):
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
def update_date_range_slider(session):
    if session is None:
        return 0, 0, {}, [0, 0]
    session = json.loads(session)
    col_date = session["meta_data"]["cols_key_meta"]["date"]
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
def update_dropdowns(session):
    if session is None:
        return [], [], [], [], [], [], [], [], [], [], []
    session = json.loads(session)
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
@callback_prevent_initial_output
def update_map(map_group, meta_data, relayoutData):
    if meta_data is None or not map_group:
        return empty_fig()
    # find what is triggering the callback
    ctx_call = ctx.triggered_id

    meta_data = json.loads(meta_data)

    df_coords = pd.read_json(io.StringIO(meta_data["df_coordinate"]))

    col_color = map_group
    color_discrete_map = meta_data["dict_generic_colors"][col_color]
    dict_kwargs_map = {
        "color": col_color,
        "color_discrete_map": color_discrete_map,
        "custom_data": meta_data["cols_key_meta"]["loc_id"],
        "hover_name": meta_data["cols_key_meta"]["loc_id"],
    }
    fig = make_map(df_coords, **dict_kwargs_map)
    if ctx_call == "map-group-dropdown" and relayoutData:
        allowed_relayout_keys = {
            "mapbox.center",
            "mapbox.zoom",
            "mapbox.bearing",
            "mapbox.pitch",
        }
        relayoutData = {
            k: v for k, v in relayoutData.items() if k in allowed_relayout_keys
        }
        if relayoutData:
            fig.update_layout(relayoutData)
    return fig


# STORE THE MAP RELAYOUT DATA
@app.callback(
    Output("map-relayout-store", "data"),
    Input("map", "relayoutData"),
    prevent_intial_call=True,
)
def store_map_relayout_data(relayoutData):
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
    n_clicks,
    session,
    feature_selection,
    loc_id_selection,
    n_neighbors,
    map_group,
    plot_group_1,
    plot_group_2,
):
    if session is None:
        return None, dash.no_update
    if not feature_selection or not loc_id_selection:
        return None, dash.no_update

    session = json.loads(session)
    meta_data = session["meta_data"]
    df_master = json_to_pandas(session, "df_master", meta_data["cols_key_meta"]["date"])
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
    return json.dumps(dict_working_data), json.dumps(session)


# grab the selected data from the map and update the loc_id-dropdown
@app.callback(
    Output("loc-id-dropdown", "value", allow_duplicate=True),
    Input("map-selected-snapshot", "n_clicks"),
    State("map", "selectedData"),
    State("meta-data", "data"),
    prevent_initial_call=True,
)
def update_loc_id_dropdown(n_clicks, selectedData, meta_data):
    if selectedData is None:
        if meta_data is None:
            return []
        meta_data = json.loads(meta_data)
        return meta_data["loc_id_all"]
    selected_loc_ids = [point["customdata"][0] for point in selectedData["points"]]
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
def plot_data(
    working_data,
    selectedData,
    plot_group_1,
    plot_group_2,
    date_range,
    meta_data,
    n_neighbors,
):

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
# port = 8050
# if __name__ == "__main__":
#     # app.run_server(debug=False, port=port)
#     app.run_server(debug=True, port=port)

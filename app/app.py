# %%
import io
import json

import dash
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
from dash import html, dcc
from flask import Flask

import pandas as pd

from src.plotting import make_map, empty_fig
from src.data_manager import DataPreprocessor, DataPlotter

from src.data_process import json_to_pandas, pandas_to_json

# from src.compositional_data_functions import clr_transform_scale
from src.dimension_reduction_functions import process_dimension_reduction
from src.callbacks import callback_prevent_initial_output

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
@app.callback(
    Output("master-data", "data"),
    Output("meta-data", "data"),
    Output("data-hash", "data"),
    Output("feature-selection-dropdown", "options"),
    Output("feature-selection-dropdown", "value"),
    Output("loc-id-dropdown", "options", allow_duplicate=True),
    Output("loc-id-dropdown", "value", allow_duplicate=True),
    Input("upload-data", "contents"),
    prevent_initial_call=True,
)
def process_data(contents):
    if contents is None:
        return None, None, None, [], [], [], []
    content_type, content_string = contents.split(",")
    data_preprocessor = DataPreprocessor(content_string)
    dict_master_data, dict_meta_data, dict_hash_data = (
        data_preprocessor.generate_dict_data_structure()
    )
    return (
        dict_master_data,
        dict_meta_data,
        dict_hash_data,
        data_preprocessor.cols_key_plot["numeric_all"],
        data_preprocessor.cols_key_plot["numeric_all"],
        data_preprocessor.loc_id_all,
        data_preprocessor.loc_id_all,
    )


@app.callback(
    Output("date-range-slider", "min"),
    Output("date-range-slider", "max"),
    Output("date-range-slider", "marks"),
    Output("date-range-slider", "value"),
    Input("master-data", "data"),
    State("meta-data", "data"),
    prevent_initial_call=True,
)
def update_date_range_slider(master_data, meta_data):
    if master_data is None or meta_data is None:
        return 0, 1, {}, [0, 1]
    meta_data = json.loads(meta_data)
    master_data = json.loads(master_data)
    df_master = json_to_pandas(
        master_data, "df_master", meta_data["cols_key_meta"]["date"]
    )
    date_min = df_master[meta_data["cols_key_meta"]["date"]].dt.year.min()
    date_max = df_master[meta_data["cols_key_meta"]["date"]].dt.year.max()
    marks = {i: str(i) for i in range(date_min, date_max + 1, 5)}
    marks[date_max] = str(date_max)
    return date_min, date_max, marks, [date_min, date_max]


@app.callback(
    [
        Output("map-group-dropdown", "options"),
        Output("map-group-dropdown", "value"),
        Output("plot-group-dropdown-1", "options"),
        Output("plot-group-dropdown-1", "value"),
        Output("plot-group-dropdown-2", "options"),
        Output("plot-group-dropdown-2", "value"),
    ],
    Input("meta-data", "data"),
    prevent_initial_call=True,
)
def update_dropdowns(meta_data):
    if meta_data is None:
        return [], [], [], [], [], []
    meta_data = json.loads(meta_data)
    dict_generic_colors = meta_data["dict_generic_colors"]
    # col_date = meta_data["cols_key_meta"]["date"]
    cols_plot_groups = list(dict_generic_colors.keys())
    # cols_map_groups = cols_plot_groups.copy()
    # cols_map_groups.remove(col_date)
    return (
        cols_plot_groups,
        cols_plot_groups[0],
        cols_plot_groups,
        cols_plot_groups[0],
        cols_plot_groups,
        cols_plot_groups[0],
    )


# GENERATE THE MAP
@app.callback(
    Output("map", "figure"),
    [Input("map-group-dropdown", "value")],
    [Input("meta-data", "data")],
    prevent_initial_call=True,
)
@callback_prevent_initial_output
def update_map(map_group, meta_data):
    if meta_data is None:
        return empty_fig()
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
    return fig


@app.callback(
    Output("working-data", "data"),
    [
        Input(component_id="apply-button", component_property="n_clicks"),
    ],
    [
        State("master-data", "data"),
        State("meta-data", "data"),
        State("data-hash", "data"),
        State(component_id="feature-selection-dropdown", component_property="value"),
        State(component_id="loc-id-dropdown", component_property="value"),
        State(component_id="pmap-neighbors", component_property="value"),
    ],
)
@callback_prevent_initial_output
def process_working_data(
    n_clicks,
    master_data,
    meta_data,
    data_hash,
    feature_selection,
    loc_id_selection,
    n_neighbors,
):
    if master_data is None or meta_data is None:
        return None
    if not feature_selection or not loc_id_selection:
        return None
    master_data = json.loads(master_data)
    meta_data = json.loads(meta_data)
    df_master = json_to_pandas(
        master_data, "df_master", meta_data["cols_key_meta"]["date"]
    )
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

    dict_working_data = {
        "df_plot_pca": pandas_to_json(
            plot_components_pca[0], meta_data["cols_key_meta"]["date"]
        ),
        "ldg_df": plot_components_pca[1].to_json(),
        "expl_var": plot_components_pca[2],
        "df_plot_pmap": pandas_to_json(
            plot_components_pmap, meta_data["cols_key_meta"]["date"]
        ),
    }
    return json.dumps(dict_working_data)


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
        Input("date-step-dropdown", "value"),
        Input("date-range-slider", "value"),
    ],
    [
        State(component_id="meta-data", component_property="data"),
        State(component_id="pmap-neighbors", component_property="value"),
    ],
    prevent_initial_call=True,
)
# @callback_prevent_initial_output  # this is stopping the plots from updating when deselect all
def plot_data(
    working_data,
    selectedData,
    plot_group_1,
    plot_group_2,
    date_step,
    date_range,
    meta_data,
    n_neighbors,
):
    # ctx = dash.callback_context
    # if not ctx.triggered:
    #     return DataPlotter.empty_figs()
    # trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    # print(trigger_id)
    if working_data is None:
        return DataPlotter.empty_figs()
    if plot_group_1 == "DATETIME" or plot_group_2 == "DATETIME":
        plot_group_1 = "DATETIME"
        plot_group_2 = "DATETIME"
        notification = dbc.Toast(
            "Datetime will be used for both plotting groups",
            id="auto-toast",
            header="Invalid Plotting Group",
            is_open=True,
            dismissable=True,
            icon="warning",
            duration=4000,
            style={"position": "fixed", "top": 66, "right": 10, "width": 350},
        )

    data_plotter = DataPlotter(
        working_data,
        meta_data,
        selectedData,
        [plot_group_1, plot_group_2],
        date_step,
        date_range,
    )
    fig_pca = data_plotter.plot_pca()
    fig_pmap = data_plotter.plot_pmap(n_neighbors=n_neighbors)
    return fig_pca, fig_pmap


# TURN OFF FOR DEPLOYMENT WITH GUNICORN
port = 8050
if __name__ == "__main__":
    app.run_server(debug=False, port=port)

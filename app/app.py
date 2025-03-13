# %%
import io
import json

import dash
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
from dash import html, dcc
from flask import Flask

import pandas as pd

from src.plotting import make_map
from src.data_manager import DataPreprocessor, DataPlotter

# from src.data_process import subset_df_locIds, subset_df_numericFeatures
# from src.compositional_data_functions import clr_transform_scale
from src.dimension_reduction_functions import process_dimension_reduction
from src.callbacks import callback_prevent_initial_output


# define the Flask server
server = Flask(__name__)
app = dash.Dash(__name__, server=server, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = html.Div(
    children=[
        dcc.Store(id="data-hash"),
        dcc.Store(id="master-data"),
        dcc.Store(id="meta-data"),
        dcc.Store(id="working-data"),
        html.Div(
            children=[
                dcc.Upload(
                    id="upload-data",
                    children=html.Button("Upload File"),
                    multiple=False,
                ),
            ],
            className="d-flex justify-content-center",
            style={"padding-bottom": "10px"},
        ),
        html.Div(
            children=[
                dcc.Graph(
                    id="map",
                    config={"scrollZoom": True, "displayModeBar": True},
                ),
                dcc.Graph(id="pmap-plot"),
                dcc.Graph(id="pca-plot"),
            ],
            className="d-flex flex-row",
        ),
        html.Div(
            children=[
                html.Button("Apply", id="apply-button"),
                dcc.Dropdown(
                    id="pmap-neighbors",
                    options=[{"label": i, "value": i} for i in range(10, 151, 5)],
                    value=15,
                ),
                dcc.Dropdown(
                    id="loc-id-dropdown",
                    options=[],
                    value=[],
                    multi=True,
                ),
                dcc.Dropdown(
                    id="feature-selection-dropdown",
                    options=[],
                    value=[],
                    multi=True,
                    style={"flex-grow": 1},
                ),
            ],
            className="d-flex flex-row",
            style={"min-width": "100%"},
        ),
    ],
)

# IMPORT DATA FROM .CSV
@app.callback(
    Output("master-data", "data"),
    Output("meta-data", "data"),
    Output("data-hash", "data"),
    Output("feature-selection-dropdown", "options"),
    Output("feature-selection-dropdown", "value"),
    Output("loc-id-dropdown", "options"),
    Output("loc-id-dropdown", "value"),
    Input("upload-data", "contents"),
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


# GENERATE THE MAP
@app.callback(
    Output("map", "figure"),
    [Input("meta-data", "data")],
    prevent_initial_call=True,
)
@callback_prevent_initial_output
def update_map(meta_data):
    print("Updating map")
    print(meta_data)
    meta_data = json.loads(meta_data)

    df_coords = pd.read_json(io.StringIO(meta_data["df_coordinate"]))

    dict_kwargs_map = {
        "color": meta_data["cols_key_meta"]["map_group"],
        "color_discrete_map": meta_data["dict_color_map"],
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
    # if feature_selection or loc_id_selection is not populated, prevent update
    if not feature_selection or not loc_id_selection:
        # print to console
        print("Feature or loc ID not populated")
        return None
    df_master = pd.read_json(io.StringIO(json.loads(master_data)["df_master"]))
    meta_data = json.loads(meta_data)
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

    # put the two into dcc.Store("working-data")
    dict_working_data = {
        "df_plot_pca": plot_components_pca[0].to_json(),
        "ldg_df": plot_components_pca[1].to_json(),
        "expl_var": plot_components_pca[2],
        "df_plot_pmap": plot_components_pmap.to_json(),
    }
    return json.dumps(dict_working_data)


# plotting callbacks
@app.callback(
    [
        Output(component_id="pca-plot", component_property="figure"),
        Output(component_id="pmap-plot", component_property="figure"),
    ],
    [
        Input("working-data", "data"),
        Input("map", "selectedData"),
    ],
    [
        State(component_id="meta-data", component_property="data"),
        State(component_id="pmap-neighbors", component_property="value"),
    ],
    prevent_initial_call=True,
)
# @callback_prevent_initial_output  # this is stopping the plots from updating when deselect all
def plot_data(working_data, selectedData, meta_data, n_neighbors):
    data_plotter = DataPlotter(working_data, meta_data, selectedData)
    fig_pca = data_plotter.plot_pca()
    fig_pmap = data_plotter.plot_pmap(n_neighbors=n_neighbors)
    return fig_pca, fig_pmap


# TURN OFF FOR DEPLOYMENT WITH GUNICORN
# port = str(8050)
# if __name__ == "__main__":
#     app.run_server(debug=False, port=port)

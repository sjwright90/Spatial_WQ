from dash import html, dcc
import dash_bootstrap_components as dbc
from .www.style.style import *

navbar = dbc.NavbarSimple(
    children=[
        dbc.Button(
            "Plot filters",
            outline=True,
            color="secondary",
            className="mr-1",
            id="btn_sidebar",
        ),
    ],
    brand="Water Quality Dashboard",
    brand_href="#",
    color="dark",
    dark=True,
    fluid=True,
    sticky="top",
)

textenter_user_id = html.Div(
    children=[
        dcc.Input(  # user enters their id
            id="user-session-id",
            type="text",
            placeholder="Enter your user ID",
            value=None,
        ),
    ]
)

dropdown_button_redis_import = html.Div(
    [
        html.Button(
            "List sessions",
            id="button-list-redis-keys",
            style=BUTTON_STYLE,
        ),
        dcc.Dropdown(
            id="user-redis-key-dropdown",
            options=[],
            value=None,
            multi=False,
            style=DROPDOWN_UNI_STYLE,
            placeholder="Select a session to load",
        ),
        html.Button(
            "Import session",
            id="redis-import-button",
            style=BUTTON_STYLE,
        ),
    ]
)

dropdown_map_group = html.Div(
    [
        html.P("Select Map Group Column"),
        dcc.Dropdown(
            id="map-group-dropdown",
            options=[],
            value=[],
            multi=False,
            style=DROPDOWN_UNI_STYLE,
        ),
    ]
)

dropdown_plot_group_1 = html.Div(
    [
        html.P("Select Plot Primary Group"),
        dcc.Dropdown(
            id="plot-group-dropdown-1",
            options=[],
            value=[],
            multi=False,
            style=DROPDOWN_UNI_STYLE,
        ),
    ]
)

dropdown_plot_group_2 = html.Div(
    [
        html.P("Select Plot Secondary Group"),
        dcc.Dropdown(
            id="plot-group-dropdown-2",
            options=[],
            value=[],
            multi=False,
            style=DROPDOWN_UNI_STYLE,
        ),
    ]
)

check_list_plot_date = html.Div(
    [
        html.H3("DATE GROUPING COMING SOON"),
        dcc.Checklist(
            id="date-checklist",
            options=["Plot by Date"],
            value=[],
            style=CHECK_BOX_STYLE,
        ),
    ]
)

textenter_redis_save = html.Div(
    children=[
        dcc.Input(
            id="user-redis-key-text",
            type="text",
            value=None,
            placeholder="Store session as:",
        ),
        html.Button(
            "Store session",
            id="redis-save-button",
            style=BUTTON_STYLE,
        ),
        html.Div(id="save-session-output"),
        dcc.Interval(
            id="clear-save-output", interval=5000, n_intervals=0, disabled=True
        ),
    ]
)

download_button = html.Div(
    children=[
        dcc.Download(id="download-session-json"),
        html.Button(
            "Download JSON",
            id="download-session-button",
            style=BUTTON_STYLE,
        ),
    ]
)
# SIDEBAR
sidebar = html.Div(
    children=[
        html.P("Load-Save Session", className="lead"),
        textenter_user_id,
        dropdown_button_redis_import,
        textenter_redis_save,
        html.P("Download Session", className="lead"),
        download_button,
        html.Hr(),
        html.P("Customize plotting options", className="lead"),
        dropdown_map_group,
        dropdown_plot_group_1,
        dropdown_plot_group_2,
        check_list_plot_date,
    ],
    id="sidebar",
    style=SIDEBAR_HIDEN,
)


range_slider_date_filter = html.Div(
    [
        html.P("Select Date Range"),
        dcc.RangeSlider(
            id="date-range-slider",
            min=0,
            max=100,
            step=1,
            value=[20, 20],
            marks={i: str(i) for i in range(0, 101, 10)},
        ),
    ]
)


uploaders = html.Div(
    children=[
        dcc.Upload(
            id="upload-data",
            children=html.Button("Upload File"),
            multiple=False,
        ),
    ],
    className="d-flex justify-content-center",
    style=BUTTON_STYLE,
)

map_div = html.Div(
    children=[
        dcc.Graph(
            id="map",
            config={"scrollZoom": True, "displayModeBar": True},
            relayoutData=None,
        ),
    ],
    className="d-flex flex-row",
)
scatter_div = html.Div(
    children=[
        dcc.Graph(id="pmap-plot"),
        dcc.Graph(id="pca-plot"),
    ],
    className="d-flex flex-row",
)
plots_div = html.Div(
    children=[
        map_div,
        scatter_div,
    ],
)

action_buttons = html.Div(
    children=[
        html.Button("Grab map select for PCA/PacMAP", id="map-selected-snapshot")
    ],
    # className="d-flex justify-content-center",
    style=BUTTON_STYLE,
)

dropdown_n_neighbers = html.Div(
    [
        html.P("Select number of neighbors"),
        dcc.Dropdown(
            id="pmap-neighbors",
            options=[{"label": i, "value": i} for i in range(10, 151, 5)],
            value=15,
            style=DROPDOWN_NUM_STYLE,
        ),
    ]
)

dropdown_loc_ids = html.Div(
    [
        html.P("Select Location IDs"),
        dcc.Dropdown(
            id="loc-id-dropdown",
            options=[],
            value=[],
            multi=True,
            style=DROPDOWN_MULTI_STYLE,
        ),
    ]
)

dropdown_features = html.Div(
    [
        html.P("Select Features"),
        dcc.Dropdown(
            id="feature-selection-dropdown",
            options=[],
            value=[],
            multi=True,
            style=DROPDOWN_MULTI_STYLE,
        ),
    ]
)

selector_div = html.Div(
    children=[
        range_slider_date_filter,
        html.Button(
            "Apply",
            id="apply-button",
            style=BUTTON_STYLE,
        ),
        dropdown_n_neighbers,
        dropdown_loc_ids,
        dropdown_features,
    ],
)

floating_alert_container = html.Div(
    id="global-alert-container",
    children=[],
    style=ALERT_STYLE,
)

main_content = html.Div(
    children=[
        uploaders,
        plots_div,
        action_buttons,
        selector_div,
    ],
    className="d-flex flex-column",
    style=CONTENT_STYLE1,
    id="page-content",
)


def create_page_map():
    layout = html.Div(
        children=[
            dcc.Store(
                id="meta-data", storage_type="memory"
            ),  # needed still to not unpack entire session data each time
            dcc.Store(id="session", storage_type="memory"),
            dcc.Store(
                id="working-data"
            ),  # TODO: consider using 'session' storage for plotting data to reduce parsing/unparsing JSON each time plot is updated
            dcc.Store(id="side_click"),
            dcc.Store(id="map-relayout-store"),
            navbar,
            sidebar,
            floating_alert_container,
            main_content,
        ],
    )
    return layout

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

sidebar = html.Div(
    children=[
        html.H3("Plot filters", className="display-4"),
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
            dcc.Store(id="data-hash"),
            dcc.Store(id="master-data"),
            dcc.Store(id="meta-data"),
            dcc.Store(
                id="working-data"
            ),  # TODO: consider using 'session' storage for plotting data to reduce parsing/unparsing JSON each time plot is updated
            dcc.Store(id="side_click"),
            navbar,
            sidebar,
            main_content,
        ],
    )
    return layout

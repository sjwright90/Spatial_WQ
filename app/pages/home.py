from dash import html, dcc
import dash_bootstrap_components as dbc
from .www.style.style import *
from src.data_model import ROLE_REGISTRY, ColumnRole

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

# Upstream date "Filter" - subsets df_master before PCA/PaCMAP/clustering
# run (unlike the downstream, display-only date-range-slider "Mask" below
# apply_row, which only trims already-computed plot output). Two independent
# DatePickerSingle boxes rather than one linked DatePickerRange - clearer at
# the sidebar's narrow width, and each opens its calendar via with_portal
# (a document-level overlay) so it isn't clipped/z-ordered behind the plots.
# No min_date_allowed/max_date_allowed constraint is applied - typed/picked
# dates outside the data's actual range are accepted rather than silently
# reverted; date-filter-hint shows the actual available range instead.
date_filter_picker = html.Div(
    [
        html.P("Select Date Filter Range (affects PCA/PaCMAP/clustering)"),
        html.Div(id="date-filter-hint", className="text-muted", style={"font-size": "10px"}),
        html.Label("Min Date", style={"display": "block"}),
        dcc.DatePickerSingle(
            id="date-filter-start-picker",
            date=None,
            disabled=True,
            with_portal=True,
        ),
        html.Label("Max Date", style={"display": "block", "margin-top": "0.5rem"}),
        dcc.DatePickerSingle(
            id="date-filter-end-picker",
            date=None,
            disabled=True,
            with_portal=True,
        ),
        dcc.Store(id="date-filter-bounds-store", data=None),
        html.Button(
            "Reset filter",
            id="date-filter-reset-button",
            style=BUTTON_STYLE,
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
        dcc.Download(id="download-color-mapping-csv"),
        html.Button(
            "Download Color Mapping CSV",
            id="download-color-mapping-button",
            style=BUTTON_STYLE,
        ),
        dcc.Download(id="download-custom-groups-csv"),
        html.Button(
            "Download Custom Groups CSV",
            id="download-custom-groups-button",
            style=BUTTON_STYLE,
        ),
    ]
)

# COLOR PICKER (custom per-category color overrides for any plotting group)
open_color_picker_button = html.Button(
    "Customize Colors",
    id="open-color-picker-button",
    style=BUTTON_STYLE,
)

# A dbc.Offcanvas, not a dbc.Modal: modals backdrop the whole page while
# open, which blocks interacting with the map/plots behind them - a plain
# color-swatch tweak shouldn't require closing the panel first. backdrop=False
# + scrollable=True keep the rest of the page fully clickable/scrollable while
# this is open (see docs/agent-context/CUSTOM-CATEGORY-COLOR-BUGS-HANDOFF.md).
color_picker_modal = dbc.Offcanvas(
    [
        dcc.Dropdown(
            id="color-picker-group-dropdown",
            options=[],
            value=None,
            multi=False,
            style=DROPDOWN_UNI_STYLE,
            placeholder="Select a plotting-group column",
        ),
        html.Div(id="color-picker-value-list", children=[]),
        html.Hr(),
        html.Div(
            [
                html.Button(
                    "Reset group to defaults",
                    id="reset-color-overrides-button",
                    style=BUTTON_STYLE,
                ),
                html.Button(
                    "Apply",
                    id="apply-color-overrides-button",
                    style=BUTTON_STYLE,
                ),
            ]
        ),
    ],
    id="color-picker-modal",
    title="Customize category colors",
    is_open=False,
    placement="end",
    backdrop=False,
    scrollable=True,
)

# CUSTOM CATEGORY/GROUP CREATION
open_custom_group_button = html.Button(
    "+ Add Custom Group",
    id="open-custom-group-button",
    style=BUTTON_STYLE,
)

# dbc.Offcanvas (see color_picker_modal above for why, not dbc.Modal) - the
# whole point of this panel is that the user lassoes points on the map/plots
# *while* it's open, repeatedly, to build up multiple categories, so it must
# not block interaction with the rest of the page.
cluster_feature_space_dropdown = dcc.Dropdown(
    id="cluster-feature-space",
    options=[
        {"label": "CLR feature space (selected analytes)", "value": "clr"},
        {"label": "PCA space (all computed components)", "value": "pca"},
    ],
    value="clr",
    clearable=False,
    style=DROPDOWN_UNI_STYLE,
)

cluster_n_clusters_input = dcc.Input(
    id="cluster-n-clusters",
    type="number",
    min=2,
    step=1,
    value=3,
    placeholder="Number of clusters",
)

run_clustering_button = html.Button(
    "Run Clustering",
    id="run-clustering-button",
    style=BUTTON_STYLE,
)

auto_cluster_section = html.Div(
    [
        html.P(
            "Auto-cluster (KMeans) - runs on the analytes/locations currently "
            "applied ('Apply' button) to the PCA/PaCMAP plots. Writes the "
            "resulting clusters below as categories, replacing any "
            "categories already added - review/rename before finishing.",
            style={"font-size": "0.85em"},
        ),
        html.Div(
            [cluster_feature_space_dropdown, cluster_n_clusters_input, run_clustering_button],
            className="d-flex flex-row align-items-end",
            style={"gap": "8px"},
        ),
    ]
)

custom_group_modal = dbc.Offcanvas(
    [
        dcc.Input(
            id="custom-group-name-input",
            type="text",
            placeholder="New group column name",
        ),
        html.Hr(),
        auto_cluster_section,
        html.Hr(),
        html.P(
            "Lasso/box-select points on the map or a biplot, then click "
            "'Create Group From Selection' to load them below - repeat for "
            "each category, then Finish.",
            style={"font-size": "0.85em"},
        ),
        dcc.Input(
            id="custom-group-category-name-input",
            type="text",
            placeholder="Category value name",
        ),
        dcc.Dropdown(
            id="custom-group-assign-entity-dropdown",
            options=[],
            value=[],
            multi=True,
            style=DROPDOWN_MULTI_STYLE,
            placeholder="Sample IDs assigned to this category (editable)",
        ),
        html.Button(
            "Add/Update category",
            id="custom-group-commit-category-button",
            style=BUTTON_STYLE,
        ),
        html.Div(id="custom-group-categories-preview", children=[]),
        html.Hr(),
        html.Div(
            [
                html.Button(
                    "Cancel",
                    id="custom-group-cancel-button",
                    style=BUTTON_STYLE,
                ),
                html.Button(
                    "Finish & Create Group",
                    id="custom-group-finalize-button",
                    style=BUTTON_STYLE,
                ),
            ]
        ),
    ],
    id="custom-group-modal",
    title="Create custom category group",
    is_open=False,
    placement="end",
    backdrop=False,
    scrollable=True,
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
        date_filter_picker,
        html.Hr(),
        html.P("Custom categories & colors", className="lead"),
        open_color_picker_button,
        color_picker_modal,
        open_custom_group_button,
        custom_group_modal,
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


def _role_mapping_row(role_spec):
    """Build one labeled dropdown for a RoleSpec, driven entirely by
    data_model.ROLE_REGISTRY - adding/removing a role there is reflected here
    automatically, no per-role component authoring needed."""
    return html.Div(
        [
            html.P(
                role_spec.label + (" *" if role_spec.required else " (optional)"),
                style={"margin-bottom": "2px"},
            ),
            dcc.Dropdown(
                id={"type": "role-mapping", "role": role_spec.role.value},
                options=[],
                value=[] if role_spec.multi else None,
                multi=role_spec.multi,
                style=DROPDOWN_MULTI_STYLE if role_spec.multi else DROPDOWN_UNI_STYLE,
                placeholder="Select column(s)..." if role_spec.multi else "Select column...",
            ),
        ],
        style={"margin-bottom": "8px"},
    )


# One dropdown per role except GROUP_COLOR, which is rendered dynamically
# (per selected plotting-group) in mapping_group_color_section below.
mapping_role_rows = [
    _role_mapping_row(spec) for spec in ROLE_REGISTRY if spec.role != ColumnRole.GROUP_COLOR
]

mapping_group_color_section = html.Div(
    [
        html.P("Plotting group colors (optional)", style={"margin-bottom": "2px"}),
        html.Div(id="mapping-group-color-container", children=[]),
    ]
)

mapping_issues_container = dbc.Alert(
    id="mapping-issues-container",
    children=[],
    color="danger",
    is_open=False,
)

mapping_modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("Map CSV columns")),
        dbc.ModalBody(
            html.Div(mapping_role_rows + [mapping_group_color_section, mapping_issues_container])
        ),
        dbc.ModalFooter(
            html.Button(
                "Confirm mapping",
                id="confirm-mapping-button",
                style=BUTTON_STYLE,
            )
        ),
    ],
    id="mapping-modal",
    is_open=False,
    size="lg",
    backdrop="static",
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
        html.Button("Grab map select for PCA/PacMAP", id="map-selected-snapshot"),
        html.Button("Create Group From Selection", id="create-group-from-selection-button"),
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

dropdown_pca_x_component = html.Div(
    [
        html.P("PCA X axis"),
        dcc.Dropdown(
            id="pca-x-component",
            options=[{"label": "PC1", "value": "PC1"}],
            value="PC1",
            clearable=False,
            style=DROPDOWN_NUM_STYLE,
        ),
    ]
)

dropdown_pca_y_component = html.Div(
    [
        html.P("PCA Y axis"),
        dcc.Dropdown(
            id="pca-y-component",
            options=[{"label": "PC2", "value": "PC2"}],
            value="PC2",
            clearable=False,
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

# Shows "Date filter pending" (warning) whenever the live start/end pickers
# differ from what's actually Applied, or "Date filter active" (success) once
# a narrower-than-full range has been Applied and the pickers still match it.
# Stays visible even when the "Plot filters" sidebar holding the pickers
# themselves is collapsed.
date_filter_indicator = html.Div(id="date-filter-indicator", children=[])

apply_row = html.Div(
    children=[
        html.Button(
            "Apply",
            id="apply-button",
            style=BUTTON_STYLE,
        ),
        dropdown_n_neighbers,
        dropdown_pca_x_component,
        dropdown_pca_y_component,
        date_filter_indicator,
    ],
    className="d-flex flex-row align-items-end",
)

selector_div = html.Div(
    children=[
        range_slider_date_filter,
        apply_row,
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
        mapping_modal,
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
            dcc.Store(
                id="raw-upload-store"
            ),  # {content_string, columns} for the pending upload, staged until mapping is confirmed
            dcc.Store(
                id="custom-color-overrides", storage_type="memory"
            ),  # mirrors session["custom_color_overrides"], cheap Input for update_map/plot_data
            dcc.Store(
                id="custom-group-draft", storage_type="memory"
            ),  # {category_value: [entity_id, ...]} while custom-group-modal is open
            navbar,
            sidebar,
            floating_alert_container,
            main_content,
        ],
    )
    return layout

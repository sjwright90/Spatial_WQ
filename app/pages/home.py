from dash import html, dcc

uploaders = html.Div(
    children=[
        dcc.Upload(
            id="upload-data",
            children=html.Button("Upload File"),
            multiple=False,
        ),
    ],
    className="d-flex justify-content-center",
    style={"padding-bottom": "10px"},
)

plots_div = html.Div(
    children=[
        dcc.Graph(
            id="map",
            config={"scrollZoom": True, "displayModeBar": True},
        ),
        dcc.Graph(id="pmap-plot"),
        dcc.Graph(id="pca-plot"),
    ],
    className="d-flex flex-row",
)

map_select_button = html.Div(
    children=[
        html.Button(
            "Grab map select for PCA/PacMAP", id="map-selected-snapshot"
        )
    ]
)

selector_div = html.Div(
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
            # style={"flex-grow": 1},
        ),
    ],
    className="d-flex flex-row",
    style={"min-width": "100%"},
)

def create_page_map():
    layout =  html.Div(
        children=[
            dcc.Store(id="data-hash"),
            dcc.Store(id="master-data"),
            dcc.Store(id="meta-data"),
            dcc.Store(id="working-data"),
            uploaders,
            plots_div,
            map_select_button,
            selector_div,
        ],
    )
    return layout



            # html.Div(
            #     children=[
            #         dcc.Upload(
            #             id="upload-data",
            #             children=html.Button("Upload File"),
            #             multiple=False,
            #         ),
            #     ],
            #     className="d-flex justify-content-center",
            #     style={"padding-bottom": "10px"},
            # ),
            # html.Div(
            #     children=[
            #         dcc.Graph(
            #             id="map",
            #             config={"scrollZoom": True, "displayModeBar": True},
            #         ),
            #         dcc.Graph(id="pmap-plot"),
            #         dcc.Graph(id="pca-plot"),
            #     ],
            #     className="d-flex flex-row",
            # ),
            # html.Div(
            #     children=[
            #         html.Button(
            #             "Grab map select for PCA/PacMAP", id="map-selected-snapshot"
            #         )
            #     ]
            # ),
        #     html.Div(
        #         children=[
        #             html.Button("Apply", id="apply-button"),
        #             dcc.Dropdown(
        #                 id="pmap-neighbors",
        #                 options=[{"label": i, "value": i} for i in range(10, 151, 5)],
        #                 value=15,
        #             ),
        #             dcc.Dropdown(
        #                 id="loc-id-dropdown",
        #                 options=[],
        #                 value=[],
        #                 multi=True,
        #             ),
        #             dcc.Dropdown(
        #                 id="feature-selection-dropdown",
        #                 options=[],
        #                 value=[],
        #                 multi=True,
        #                 style={"flex-grow": 1},
        #             ),
        #         ],
        #         className="d-flex flex-row",
        #         style={"min-width": "100%"},
        #     ),
        # ],
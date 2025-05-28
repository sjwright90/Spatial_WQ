import plotly.graph_objects as go
import numpy as np
import plotly.express as px

# map size
fig_height_px_map = 650
fig_width_px_map = 1400
# plot size
fig_height_px_plot = 650
fig_width_px_plot = 700

size_marker = 11
size_line_1 = 1.2
size_line_2 = 0.2

# primary_domain = "MAP-GROUPS-DOMAIN_primary_domain"
# secondary_domain = "PLOT-GROUPS-DOMAIN-1_secondary_domain"


def empty_fig():
    return go.Figure()


def estimate_mapbox_zoom(latitudes, longitudes):
    lat_diff = np.max(latitudes) - np.min(latitudes)
    lon_diff = np.max(longitudes) - np.min(longitudes)
    max_diff = max(lat_diff, lon_diff)

    # Rough empirical formula to match visible bounds to zoom level
    if max_diff < 0.0005:
        return 15
    elif max_diff < 0.005:
        return 14
    elif max_diff < 0.05:
        return 13
    elif max_diff < 0.1:
        return 12
    elif max_diff < 0.5:
        return 10
    elif max_diff < 1:
        return 9
    elif max_diff < 5:
        return 7
    elif max_diff < 10:
        return 6
    else:
        return 4


def make_map(df, **kwargs):
    _kwargs = {
        "lat": "LATITUDE",
        "lon": "LONGITUDE",
        "hover_data": {},
        "size": "MAP-MARKER-SIZE",
        "size_max": 8,
        "opacity": 1,
        "height": fig_height_px_map,
        "width": fig_width_px_map,
    }
    zoom = estimate_mapbox_zoom(df["LATITUDE"].values, df["LONGITUDE"].values)
    _kwargs["zoom"] = zoom
    kwargs = {
        k: v for k, v in kwargs.items() if k in px.scatter_mapbox.__code__.co_varnames
    }
    _kwargs.update(kwargs)
    _col_group_id = _kwargs["color"]
    _kwargs["color"] = "."
    df.rename(columns={_col_group_id: "."}, inplace=True)
    fig = px.scatter_mapbox(
        df,
        **_kwargs,
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}",
        selector={"type": "scattermapbox"},
    )
    # legend at the bottom
    fig.update_layout(
        clickmode="event+select",
        mapbox_style="white-bg",
        mapbox_layers=[
            {
                "below": "traces",
                "sourcetype": "raster",
                "sourceattribution": "Esri",
                "source": [
                    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                ],
            }
        ],
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        # legend=dict(
        #     orientation="h", yanchor="bottom", y=-0.01, xanchor="center", x=0.5
        # ),
        legend=dict(
            # orientation="v",  # Vertical orientation
            # yanchor="top",  # Places legend to the top of the plot
            # y=-0.1,  # Adjust these parameters to position the legend vertically
            # xanchor="center",
            # x=0.5,  # Places legend to the right side
            orientation="h",
            yanchor="top",
            y=-0.1,
            xanchor="center",
            x=0.5,
            itemsizing="constant",
        ),
    )
    return fig


def find_axis_limits(df, x_col, y_col, margin=0.1):
    x_min = df[x_col].min()
    x_max = df[x_col].max()
    y_min = df[y_col].min()
    y_max = df[y_col].max()
    x_margin = margin * (x_max - x_min)
    y_margin = margin * (y_max - y_min)
    return x_min - x_margin, x_max + x_margin, y_min - y_margin, y_max + y_margin


def generate_text(site, df, primary_domain, secondary_domain, date_col):
    # Pre-format the date column for easier access later
    if date_col:
        formatted_dates = df[date_col]
        # try:
        #     formatted_dates = df[date_col].dt.strftime("%Y-%m-%d")
        # except AttributeError:
        #     formatted_dates = df[date_col]
    else:
        formatted_dates = ["N/A"] * len(df)

    # Create a list comprehension to generate the text entries
    if df[primary_domain].iloc[0] == df[secondary_domain].iloc[0]:
        texts = [
            f"<b>{site}</b><br><b>Primary Domain:</b> {p}<br><b>Date:</b> {date}"
            for p, date in zip(df[primary_domain], formatted_dates)
        ]
    else:
        texts = [
            f"<b>{site}</b><br><b>Primary Domain:</b> {p}<br><b>Secondary Domain:</b> {s}<br><b>Date:</b> {date}"
            for p, s, date in zip(
                df[primary_domain], df[secondary_domain], formatted_dates
            )
        ]

    return texts


# can adjust to display multiple groups per site
def make_base_scatter_plot(
    df,
    dict_color_map_primary,
    dict_color_map_secondary,
    name_marker_map,
    col_loc_id,
    col_primary_domain,
    col_secondary_domain,
    col_date,
    x_col,
    y_col,
    title,
    x_label,
    y_label,
):
    plotly_fig = go.Figure()
    xmin, xmax, ymin, ymax = find_axis_limits(df, x_col, y_col)
    plotly_fig.update_layout(
        xaxis_title=x_label,
        yaxis_title=y_label,
        showlegend=True,
        height=fig_height_px_plot,
        width=fig_width_px_plot,
        xaxis=dict(autorange=False, range=[xmin, xmax]),
        yaxis=dict(autorange=False, range=[ymin, ymax]),
        # title=title,
        title=None,
    )
    for loc_code, group_df in df.groupby(col_loc_id):
        # group_df = df[df[col_loc_id] == loc_code]
        show_legend = True
        for prim_dom, df_prim_dom in group_df.groupby(col_primary_domain):
            for sec_dom, df_sec_dom in df_prim_dom.groupby(col_secondary_domain):
                color_face = dict_color_map_primary[prim_dom]
                color_line = dict_color_map_secondary[sec_dom]
                size_line = size_line_1 if color_line != color_face else size_line_2
                color_line = color_line if color_line != color_face else "black"
                plotly_fig.add_trace(
                    go.Scatter(
                        x=df_sec_dom[x_col],
                        y=df_sec_dom[y_col],
                        mode="markers",
                        name=loc_code,
                        legendgroup=loc_code,
                        marker=dict(
                            size=size_marker,
                            color=color_face,
                            line={"color": color_line, "width": size_line},
                            symbol=name_marker_map[loc_code],
                        ),
                        text=generate_text(
                            loc_code,
                            df_sec_dom,
                            col_primary_domain,
                            col_secondary_domain,
                            col_date,
                        ),
                        hoverinfo="text",
                        showlegend=show_legend,
                    )
                )
                show_legend = False
        # color_face = dict_color_map_primary[group_df[col_primary_domain].unique()[0]]
        # color_line = dict_color_map_secondary[
        #     group_df[col_secondary_domain].unique()[0]
        # ]
        # size_line = size_line_1 if color_line != color_face else size_line_2
        # color_line = color_line if color_line != color_face else "black"
        # plotly_fig.add_trace(
        #     go.Scatter(
        #         x=group_df[x_col],
        #         y=group_df[y_col],
        #         mode="markers",
        #         name=loc_code,  # site_df["domain_1"].map(palette)
        #         marker=dict(
        #             size=size_marker,
        #             color=color_face,
        #             line={
        #                 "color": color_line,
        #                 "width": size_line,
        #             },
        #             symbol=name_marker_map[loc_code],
        #         ),
        #         text=generate_text(
        #             loc_code,
        #             group_df,
        #             col_primary_domain,
        #             col_secondary_domain,
        #             col_date,
        #         ),
        #         hoverinfo="text",
        #     )
        # )
    return plotly_fig


def annotate_loadings(ldg_df, plotly_fig, x_col, y_col):
    for x, y, metal in zip(ldg_df[x_col], ldg_df[y_col], ldg_df["metals"]):
        # Arrow annotation
        plotly_fig.add_annotation(
            x=x,
            y=y,
            ax=0,
            ay=0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=3,
            arrowsize=1.5,
            arrowwidth=0.8,
            arrowcolor="black",
        )

        # Text annotation slightly offset from the arrow tip
        direction = np.array([x, y]) / np.linalg.norm([x, y])
        offset_distance = 0.02
        text_offset = direction * offset_distance
        plotly_fig.add_annotation(
            x=x + text_offset[0],
            y=y + text_offset[1],
            xref="x",
            yref="y",
            text=metal,
            showarrow=False,
            font=dict(size=13, color="black"),
        )
    return plotly_fig


def make_fig_pmap(
    df,
    dict_color_map_primary,
    dict_color_map_secondary,
    name_marker_map,
    col_loc_id,
    col_primary_domain,
    col_secondary_domain,
    col_date,
    n_neighbors=10,
):
    plotly_fig = make_base_scatter_plot(
        df=df,
        dict_color_map_primary=dict_color_map_primary,
        dict_color_map_secondary=dict_color_map_secondary,
        name_marker_map=name_marker_map,
        col_loc_id=col_loc_id,
        col_primary_domain=col_primary_domain,
        col_secondary_domain=col_secondary_domain,
        col_date=col_date,
        x_col="PMAP1",
        y_col="PMAP2",
        title=f"PMAP nNeighbors={n_neighbors}",
        x_label=f"PMAP1 (nNeighbors={n_neighbors})",
        y_label=f"PMAP2 (nNeighbors={n_neighbors})",
    )
    return plotly_fig


def make_fig_pca(
    df_pca,
    ldg_df,
    expl_var,
    dict_color_map_primary,
    dict_color_map_secondary,
    name_marker_map,
    col_loc_id,
    col_primary_domain,
    col_secondary_domain,
    col_date,
):
    plotly_fig = make_base_scatter_plot(
        df=df_pca,
        dict_color_map_primary=dict_color_map_primary,
        dict_color_map_secondary=dict_color_map_secondary,
        name_marker_map=name_marker_map,
        col_loc_id=col_loc_id,
        col_primary_domain=col_primary_domain,
        col_secondary_domain=col_secondary_domain,
        col_date=col_date,
        x_col="PC1",
        y_col="PC2",
        title=f"PCA ({expl_var[0]*100:.2f}%, {expl_var[1]*100:.2f}%)",
        x_label=f"PC1 ({expl_var[0]*100:.2f}%)",
        y_label=f"PC2 ({expl_var[1]*100:.2f}%)",
    )

    plotly_fig = annotate_loadings(ldg_df, plotly_fig, "PC1", "PC2")
    return plotly_fig

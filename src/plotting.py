import plotly.graph_objects as go
import numpy as np
import plotly.express as px

# map size
fig_height_px_map = 700
fig_width_px_map = 700
# plot size
fig_height_px_plot = 800
fig_width_px_plot = 800

size_marker = 11
size_line_1 = 1.2
size_line_2 = 0.2

primary_domain = "MAP-GROUPS-DOMAIN_primary_domain"
secondary_domain = "PLOT-GROUPS-DOMAIN-1_secondary_domain"


def make_map(df, **kwargs):
    _kwargs = {
        "lat": "LATITUDE",
        "lon": "LONGITUDE",
        "hover_data": {},
        "zoom": 12,
        "size": "MAP-MARKER-SIZE",
        "size_max": 8,
        "opacity": 1,
        "height": fig_height_px_map,
        "width": fig_width_px_map,
    }
    kwargs = {
        k: v for k, v in kwargs.items() if k in px.scatter_mapbox.__code__.co_varnames
    }
    _kwargs.update(kwargs)
    fig = px.scatter_mapbox(
        df,
        **_kwargs,
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}", selector={"type": "scattermapbox"}
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
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.01, xanchor="center", x=0.5
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


def generate_text(site, df, primary_domain, secondary_domain):
    if df[primary_domain].iloc[0] == df[secondary_domain].iloc[0]:
        _t = [
            "<b>{}</b><br><b>Primary Domain:</b> {}<br>".format(loc, p)
            for loc, p in zip(
                [site] * len(df),
                df[primary_domain],
            )
        ]
    else:
        _t = [
            "<b>{}</b><br><b>Primary Domain:</b> {}<br><b>Secondary Domain:</b> {}".format(
                loc, p, s
            )
            for loc, p, s in zip(
                [site] * len(df),
                df[primary_domain],
                df[secondary_domain],
            )
        ]
    return _t


# can adjust to display multiple groups per site
def make_base_scatter_plot(
    df,
    name_color_map,
    name_marker_map,
    plot_group,
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
        title=title,
    )
    for loc_code in df[plot_group].unique():
        group_df = df[df[plot_group] == loc_code]
        color_face = name_color_map[group_df[primary_domain].unique()[0]]
        color_line = name_color_map[group_df[secondary_domain].unique()[0]]
        size_line = size_line_1 if color_line != color_face else size_line_2
        color_line = color_line if color_line != color_face else "black"
        plotly_fig.add_trace(
            go.Scatter(
                x=group_df[x_col],
                y=group_df[y_col],
                mode="markers",
                name=loc_code,  # site_df["domain_1"].map(palette)
                marker=dict(
                    size=size_marker,
                    color=color_face,
                    line={
                        "color": color_line,
                        "width": size_line,
                    },
                    symbol=name_marker_map[loc_code],
                ),
                text=generate_text(
                    loc_code,
                    group_df,
                    primary_domain,
                    secondary_domain,
                ),
                hoverinfo="text",
            )
        )
    return plotly_fig


def make_fig_pmap(
    df,
    name_color_map,
    name_marker_map,
    plot_group,
    n_neighbors=10,
):
    plotly_fig = make_base_scatter_plot(
        df,
        name_color_map,
        name_marker_map,
        plot_group,
        "PMAP1",
        "PMAP2",
        f"PMAP nNeighbors={n_neighbors}",
        "PMAP1",
        "PMAP2",
    )
    return plotly_fig


def make_fig_pca(
    df_pca,
    ldg_df,
    expl_var,
    name_color_map,
    name_marker_map,
    plot_group,
):
    plotly_fig = make_base_scatter_plot(
        df_pca,
        name_color_map,
        name_marker_map,
        plot_group,
        "PC1",
        "PC2",
        f"PCA ({expl_var[0]*100:.2f}%, {expl_var[1]*100:.2f}%)",
        f"PC1 ({expl_var[0]*100:.2f}%)",
        f"PC2 ({expl_var[1]*100:.2f}%)",
    )
    for x, y, metal in zip(ldg_df["PC1"], ldg_df["PC2"], ldg_df["metals"]):
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
        # add scatter plot of the data points

    return plotly_fig

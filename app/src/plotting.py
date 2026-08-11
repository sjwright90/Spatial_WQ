import inspect
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import numpy as np
import pandas as pd
import plotly.express as px

from .logging_config import get_logger

logger = get_logger(__name__)

# map size
fig_height_px_map = 650
fig_width_px_map = 1400
# plot size
fig_height_px_plot = 650
fig_width_px_plot = 700

size_marker = 11
size_line_1 = 1.2
size_line_2 = 0.2

# Fallbacks used when a plotting-group value or location has no entry in the
# color/marker lookup dicts built at upload time (e.g. stale dropdown state,
# or the JSON round-trip dict-key type coercion noted in data_manager.py) -
# degrade to a visible-but-generic mark rather than raising.
_DEFAULT_COLOR = "#808080"
_DEFAULT_MARKER_SYMBOL = "circle"


@dataclass
class PlotContext:
    """Bundles the plotting-group/lookup-dict cluster that travels unchanged
    through make_base_scatter_plot/make_fig_pca/make_fig_pmap. Named fields
    (vs. loose positional params) remove the risk of accidentally swapping
    the primary/secondary domain args, which are positionally adjacent."""

    col_loc_id: str
    col_primary_domain: str
    col_secondary_domain: str
    col_date: Optional[str]
    dict_color_map_primary: Dict[Any, str]
    dict_color_map_secondary: Dict[Any, str]
    name_marker_map: Dict[Any, str]
    col_entity_id: Optional[str] = None


def empty_fig() -> go.Figure:
    """A blank placeholder figure shown before any data is loaded."""
    return go.Figure()


def _bounds_from_coordinates(
    latitudes: np.ndarray, longitudes: np.ndarray, padding: float = 0.1
) -> Dict[str, float]:
    """west/east/south/north bounds enclosing all points, padded by
    `padding` fraction of the coordinate spread (with a small floor so a
    single point / identical points still yield a visible, non-zero-size
    box). Replaces the old hand-rolled zoom-level breakpoint table:
    `px.scatter_map` (unlike the deprecated `scatter_mapbox`) has no
    `fitbounds="locations"` support, so the bounds are computed directly
    here and passed to the figure as `map_bounds`.
    """
    lat_min, lat_max = np.min(latitudes), np.max(latitudes)
    lon_min, lon_max = np.min(longitudes), np.max(longitudes)
    lat_pad = max(padding * (lat_max - lat_min), 0.01)
    lon_pad = max(padding * (lon_max - lon_min), 0.01)
    return {
        "west": lon_min - lon_pad,
        "east": lon_max + lon_pad,
        "south": lat_min - lat_pad,
        "north": lat_max + lat_pad,
    }


def make_map(
    df: pd.DataFrame,
    col_lat: str = "LATITUDE",
    col_lon: str = "LONGITUDE",
    col_marker_size: str = "MAP-MARKER-SIZE",
    **kwargs: Any,
) -> go.Figure:
    """Build the location scatter-map figure. Expects `df` to already have
    `col_lat`/`col_lon`/`col_marker_size` columns (data_mapping.py renames
    the user's mapped columns to these names' defaults for exactly this
    reason). Requires a `color` kwarg naming the column to color/group
    markers by.
    """
    _kwargs = {
        "lat": col_lat,
        "lon": col_lon,
        "hover_data": {},
        "size": col_marker_size,
        "size_max": 8,
        "opacity": 1,
        "height": fig_height_px_map,
        "width": fig_width_px_map,
    }
    bounds = _bounds_from_coordinates(df[col_lat].values, df[col_lon].values)
    kwargs = {k: v for k, v in kwargs.items() if k in inspect.signature(px.scatter_map).parameters}
    _kwargs.update(kwargs)
    if "color" not in _kwargs:
        raise KeyError("make_map requires a 'color' kwarg naming the group column")
    _col_group_id = _kwargs["color"]
    _kwargs["color"] = "."
    # Non-mutating rename - the caller's dataframe (e.g. update_map's
    # df_coords) must not be altered as a side effect of building this figure.
    df = df.rename(columns={_col_group_id: "."})
    fig = px.scatter_map(
        df,
        **_kwargs,
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}",
        selector={"type": "scattermap"},
    )
    fig.update_layout(
        clickmode="event+select",
        map_bounds=bounds,
        map_style="white-bg",
        map_layers=[
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
        # legend at the bottom
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.1,
            xanchor="center",
            x=0.5,
            itemsizing="constant",
        ),
    )
    return fig


def _find_axis_limits(df: pd.DataFrame, x_col: str, y_col: str, margin: float = 0.1) -> tuple:
    """Axis (min, max) bounds for x_col/y_col, padded by `margin` fraction."""
    x_min = df[x_col].min()
    x_max = df[x_col].max()
    y_min = df[y_col].min()
    y_max = df[y_col].max()
    x_margin = margin * (x_max - x_min)
    y_margin = margin * (y_max - y_min)
    return x_min - x_margin, x_max + x_margin, y_min - y_margin, y_max + y_margin


def _generate_text(
    site: str,
    df: pd.DataFrame,
    primary_domain: str,
    secondary_domain: str,
    date_col: Optional[str],
) -> List[str]:
    """Per-point hover text for a scatter trace, one entry per row of `df`."""
    if date_col:
        formatted_dates = df[date_col]
    else:
        formatted_dates = ["N/A"] * len(df)

    if df[primary_domain].iloc[0] == df[secondary_domain].iloc[0]:
        texts = [
            f"<b>{site}</b><br><b>Primary Domain:</b> {p}<br><b>Date:</b> {date}"
            for p, date in zip(df[primary_domain], formatted_dates)
        ]
    else:
        texts = [
            f"<b>{site}</b><br><b>Primary Domain:</b> {p}<br><b>Secondary Domain:</b> {s}<br><b>Date:</b> {date}"
            for p, s, date in zip(df[primary_domain], df[secondary_domain], formatted_dates)
        ]

    return texts


def make_base_scatter_plot(
    df: pd.DataFrame,
    ctx: PlotContext,
    x_col: str,
    y_col: str,
    x_label: str,
    y_label: str,
) -> go.Figure:
    """Shared scatter-plot builder behind make_fig_pca/make_fig_pmap: one trace
    per location (ctx.col_loc_id), colored/outlined by the primary/secondary
    plotting-group domains."""
    plotly_fig = go.Figure()
    xmin, xmax, ymin, ymax = _find_axis_limits(df, x_col, y_col)
    plotly_fig.update_layout(
        xaxis_title=x_label,
        yaxis_title=y_label,
        showlegend=True,
        height=fig_height_px_plot,
        width=fig_width_px_plot,
        xaxis=dict(autorange=False, range=[xmin, xmax]),
        yaxis=dict(autorange=False, range=[ymin, ymax]),
    )
    for loc_code, group_df in df.groupby(ctx.col_loc_id):
        primary_value = group_df[ctx.col_primary_domain].unique()[0]
        secondary_value = group_df[ctx.col_secondary_domain].unique()[0]
        color_face = ctx.dict_color_map_primary.get(primary_value)
        color_line = ctx.dict_color_map_secondary.get(secondary_value)
        if color_face is None or color_line is None:
            # Stale/mismatched group value (e.g. dropdown state built before
            # a re-upload) - fall back to a generic color rather than
            # KeyError-ing the whole plot.
            logger.warning(
                "No color mapping for group value(s) %r/%r; using default color",
                primary_value,
                secondary_value,
            )
            color_face = color_face or _DEFAULT_COLOR
            color_line = color_line or _DEFAULT_COLOR
        size_line = size_line_1 if color_line != color_face else size_line_2
        color_line = color_line if color_line != color_face else "black"
        marker_symbol = ctx.name_marker_map.get(loc_code)
        if marker_symbol is None:
            logger.warning(
                "No marker symbol mapped for location %r; using default marker",
                loc_code,
            )
            marker_symbol = _DEFAULT_MARKER_SYMBOL
        # customdata carries per-point identity (site + composite site/date
        # entity id) without affecting trace grouping/legend, which stays
        # collapsed to one entry per site (loc_code) above.
        entity_col = ctx.col_entity_id if ctx.col_entity_id else ctx.col_loc_id
        plotly_fig.add_trace(
            go.Scatter(
                x=group_df[x_col],
                y=group_df[y_col],
                mode="markers",
                name=loc_code,
                marker=dict(
                    size=size_marker,
                    color=color_face,
                    line={
                        "color": color_line,
                        "width": size_line,
                    },
                    symbol=marker_symbol,
                ),
                customdata=group_df[[ctx.col_loc_id, entity_col]].values,
                text=_generate_text(
                    loc_code,
                    group_df,
                    ctx.col_primary_domain,
                    ctx.col_secondary_domain,
                    ctx.col_date,
                ),
                hoverinfo="text",
            )
        )
    return plotly_fig


def _annotate_loadings(
    ldg_df: pd.DataFrame,
    plotly_fig: go.Figure,
    x_col: str,
    y_col: str,
    col_metal: str = "metals",
) -> go.Figure:
    """Draw PCA loading-vector arrows + labels for each analyte in `ldg_df`."""
    for x, y, metal in zip(ldg_df[x_col], ldg_df[y_col], ldg_df[col_metal]):
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
    df: pd.DataFrame,
    ctx: PlotContext,
    n_neighbors: int = 10,
    x_col: str = "PMAP1",
    y_col: str = "PMAP2",
) -> go.Figure:
    """PaCMAP biplot (PMAP1/PMAP2 columns by default) for the current plot
    groups."""
    plotly_fig = make_base_scatter_plot(
        df=df,
        ctx=ctx,
        x_col=x_col,
        y_col=y_col,
        x_label=f"{x_col} (nNeighbors={n_neighbors})",
        y_label=f"{y_col} (nNeighbors={n_neighbors})",
    )
    return plotly_fig


def make_fig_pca(
    df_pca: pd.DataFrame,
    ldg_df: pd.DataFrame,
    expl_var: List[float],
    ctx: PlotContext,
    x_col: str = "PC1",
    y_col: str = "PC2",
    col_metal: str = "metals",
) -> go.Figure:
    """PCA biplot (PC1/PC2 columns by default + loading-vector annotations)
    for the current plot groups."""
    plotly_fig = make_base_scatter_plot(
        df=df_pca,
        ctx=ctx,
        x_col=x_col,
        y_col=y_col,
        x_label=f"{x_col} ({expl_var[0]*100:.2f}%)",
        y_label=f"{y_col} ({expl_var[1]*100:.2f}%)",
    )

    plotly_fig = _annotate_loadings(ldg_df, plotly_fig, x_col, y_col, col_metal)
    return plotly_fig

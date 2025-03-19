# This file contains functions to process data for the app
#
# Functions
# ---------
# get_key_cols_meta
# get_key_cols_plot
# rename_cols_analyte
# extract_coordinate_dataframe
# extract_color_dict
# extract_marker_dict
# pc_scaler
# make_df_for_biplot
from typing import List, Tuple
from pandas import DataFrame, read_json, to_datetime
import io
from datetime import datetime

# import 'alphabet' from plotly
import plotly.colors as pc

DISCRETE_COLOR_LIST = pc.qualitative.Alphabet
COLOR_BREWER_1 = pc.qualitative.Set1


def get_key_cols_meta(df):
    col_loc_id = df.filter(regex=r"^LOCATION-ID_").columns.to_list()[0]
    # col_map_group = df.filter(regex=r"^MAP-GROUPS-DOMAIN_").columns.to_list()[0]
    # col_plot_groups = df.filter(regex=r"^PLOT-GROUPS-DOMAIN-1_").columns.to_list()[0]
    col_date = df.filter(regex=r"^DATETIME$").columns.to_list()
    cols_plot_groups = df.filter(
        regex=r"^PLOTTING-GROUPS-DOMAIN-[0-9]{0,1}_LABELS$"
    ).columns.to_list()
    # will use this to then populate n color dictionaries
    # and pass them around for color mapping
    print(cols_plot_groups)
    if len(col_date) == 0:
        col_date = None
    else:
        col_date = col_date[0]
    col_long_lat = ["LONGITUDE", "LATITUDE"]
    return (
        col_loc_id,
        col_date,
        cols_plot_groups,
        # col_map_group,
        # col_plot_groups,
        col_long_lat,
    )


def make_color_dict_date(df, col_plot_group):
    _n_unique_colors = df[col_plot_group].nunique()
    _unique_color_list = COLOR_BREWER_1 * (_n_unique_colors // len(COLOR_BREWER_1) + 1)
    _dict_color = {
        k: v for k, v in zip(sorted(df[col_plot_group].unique()), _unique_color_list)
    }
    return _dict_color


def make_color_dict(df, col_plot_group):
    _n_unique_colors = df[col_plot_group].nunique()
    _unique_color_list = DISCRETE_COLOR_LIST * (
        _n_unique_colors // len(DISCRETE_COLOR_LIST) + 1
    )
    _dict_color = {
        k: v for k, v in zip(sorted(df[col_plot_group].unique()), _unique_color_list)
    }
    return _dict_color


def find_make_color_dict(df, col_plot_group):
    _col_prefix = col_plot_group.split("_LABELS")[0]
    _col_predefined_color = df.filter(regex=f"^{_col_prefix}_COLORS$").columns.to_list()
    if len(_col_predefined_color) == 0:
        _dict_color = make_color_dict(df, col_plot_group)
    else:
        _dict_color = (
            df.groupby(col_plot_group)[_col_predefined_color[0]].first().to_dict()
        )
    return _dict_color


def make_plotting_group_color_dicts(df, cols_plot_groups, col_date=None):
    _dict_col_colors = {}
    for col in cols_plot_groups:
        _dict_col_colors[col] = find_make_color_dict(df, col)
    if col_date:
        print("adding date color dict")
        _dict_col_colors[col_date] = {}
    return _dict_col_colors


def set_key_col_date(df, col_datetime):
    if col_datetime:
        try:
            df[col_datetime] = to_datetime(df[col_datetime])
        except ValueError as e:
            df[col_datetime] = datetime.now()
            print("Could not parse date column, setting to current date")
            print(f"Error: {e}")
            pass
    else:
        print("No date column provided")
    return df


def get_key_cols_plot(df):
    cols_clr = df.filter(regex=r"^CLR-ANALYTE_").columns.to_list()
    cols_simple = df.filter(regex=r"^NUMERIC-ANALYTE_").columns.to_list()
    cols_numeric_all = cols_simple + cols_clr
    cols_meta = df.columns.difference(cols_numeric_all).to_list()
    return cols_meta, cols_numeric_all, cols_simple, cols_clr


def rename_cols_analyte(df, cols_numeric_all, cols_numeric_simple, cols_numeric_clr):
    dict_rename = {col: col.split("-ANALYTE_")[-1] for col in cols_numeric_all}
    cols_numeric_all = [dict_rename[col] for col in cols_numeric_all]
    cols_numeric_simple = [dict_rename[col] for col in cols_numeric_simple]
    cols_numeric_clr = [dict_rename[col] for col in cols_numeric_clr]
    return df.rename(columns=dict_rename), (
        cols_numeric_all,
        cols_numeric_simple,
        cols_numeric_clr,
    )


def extract_coordinate_dataframe(
    df, list_plot_groups, col_loc_id, col_longitude, col_latitude
):
    _cols_grab = list_plot_groups + [
        col_loc_id,
        col_longitude,
        col_latitude,
        "MAP-MARKER-SIZE",
    ]
    return df.groupby(col_loc_id)[_cols_grab].first().copy()


def extract_color_dict(df, col_color_groups, col_color_colors):
    return df.groupby(col_color_groups)[col_color_colors].first().to_dict()


def extract_marker_dict(df, col_marker_groups, col_marker_markers):
    return df.groupby(col_marker_groups)[col_marker_markers].first().to_dict()


def subset_df_locIds(df, col_loc_id, loc_ids_subset):
    return df[df[col_loc_id].isin(loc_ids_subset)].copy()  # .reset_index(drop=True)


def subset_df_numericFeatures(
    df, cols_numeric_simple, cols_numeric_clr, cols_numeric_subset
) -> Tuple[DataFrame, List[str], List[str]]:
    _cols_original = df.columns.to_list()
    _cols_meta = df.columns.difference(cols_numeric_simple + cols_numeric_clr).to_list()
    _cols_numeric_simple_subset = [
        col for col in cols_numeric_simple if col in cols_numeric_subset
    ]
    _cols_numeric_clr_subset = [
        col for col in cols_numeric_clr if col in cols_numeric_subset
    ]
    _cols_numeric_all_subset = _cols_numeric_simple_subset + _cols_numeric_clr_subset
    df = (
        df[_cols_meta + _cols_numeric_all_subset].copy().reindex(columns=_cols_original)
    )
    return (
        df,
        _cols_numeric_all_subset,
        _cols_numeric_clr_subset,
    )


def pandas_to_json(df: DataFrame, col_datetime: str = None) -> str:
    if col_datetime:
        df[col_datetime] = df[col_datetime].dt.strftime("%Y-%m-%d")
    return df.to_json(orient="split", date_format="iso")


def json_to_pandas(json_dict, key, col_datetime=None):
    df = read_json(io.StringIO(json_dict[key]), orient="split")
    if col_datetime:
        df[col_datetime] = to_datetime(df[col_datetime])
    return df
    # return read_json(io.StringIO(json_dict[key]))


def pc_scaler(series):
    """
    Min-max scaler

    Parameters
    ----------
    trnf_data : pandas series, pandas df, or numpy array
        Values to be scaled.

    Returns
    -----
    series
        All items in series with a min-max scaler applied.
    """
    return series / (series.max() - series.min())


def make_df_for_biplot(
    trnf_data, full_df, col_list=None, num_comp=2, scale=True, prefix="PC"
):
    """
    Extract PCs and relevant columns for bi-plots

    Parameters
    ----------
    trnf_data : numpy array
        Matrix output of dimension reduction algorithm of form nxm where
        n is observations and m are dimensions.

    full_df : pandas df
        Pandas dataframe of full data set, from which to extract non-numeric
        columns to be used in bi-plot

    col_list : str, default ['lith','lab']
        Columns to extract from full_df.
        To extract nothing from full_df pass an empty list.

    num_comp : int, default 2
        Number of dimensions to extract from 'trnf_data'.
        Must have num_comp <= number of columns in trnf_data

    scale : bool, default True
        Whether to apply min-max scaler to extracted columns.

    Returns
    -----
    temp
        Dataframe. Components have a min-max scaler applied to them.
    """

    if col_list is None:
        col_list = full_df.columns.to_list()

    colnames = [f"{prefix}{x+1}" for x in range(num_comp)]
    temp = DataFrame(
        trnf_data[:, :num_comp], columns=colnames, index=full_df.index
    ).join(full_df[col_list])
    temp.columns = colnames + col_list

    if scale:
        temp[colnames] = pc_scaler(temp[colnames])

    return temp

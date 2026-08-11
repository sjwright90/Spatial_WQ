# This file contains functions to process data for the app
#
# Functions
# ---------
# df_col_group_to_dict
# make_color_dict
# find_make_color_dict
# make_plotting_group_color_dicts
# extract_coordinate_dataframe
# subset_df_locIds
# subset_df_numericFeatures
# pandas_to_json
# json_to_pandas
# pc_scaler
# make_df_for_biplot
#
# NOTE: column classification is no longer done here via regex/prefix
# conventions (LOCATION-ID_, DATETIME, LABELS_*, NUMERIC-ANALYTE_,
# CLR-ANALYTE_, etc.) - see data_model.py/data_mapping.py for the
# declarative-mapping replacement. Date coercion also now lives in
# data_mapping.py (per-row errors="coerce" + structured warnings, replacing
# the old whole-column datetime.now() fallback that used to live here).
from typing import Any, Dict, List, Optional, Tuple
from pandas import DataFrame, read_json, to_datetime
import io

# import 'alphabet' from plotly
import plotly.colors as pc

DISCRETE_COLOR_LIST = pc.qualitative.Alphabet

DEFAULT_MAP_MARKER_SIZE = 10


def df_col_group_to_dict(df: DataFrame, col_key: str, col_value: str) -> Dict[Any, Any]:
    """
    Convert a DataFrame column to a dictionary.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to convert to a dictionary.

    col_key : str
        Column name to use as the keys in the dictionary.

    col_value : str
        Column name to use as the values in the dictionary.

    Returns
    -------
    dict
        Dictionary with the keys from col_key and the values from col_value.
    """
    return df.groupby(col_key)[col_value].first().to_dict()


def make_color_dict(df: DataFrame, col_plot_group: str) -> Dict[Any, str]:
    """
    Create a color dictionary for the plotting groups.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to create the color dictionary from.

    col_plot_group : str
        Column name to use for the plotting groups.

    Returns
    -------
    dict
        Dictionary with the plotting groups as keys and the colors as values.
    """
    _n_unique_colors = df[col_plot_group].nunique()
    _unique_color_list = DISCRETE_COLOR_LIST * (_n_unique_colors // len(DISCRETE_COLOR_LIST) + 1)
    _dict_color = {k: v for k, v in zip(sorted(df[col_plot_group].unique()), _unique_color_list)}
    return _dict_color


def find_make_color_dict(
    df: DataFrame, col_plot_group: str, col_predefined_color: Optional[str] = None
) -> Dict[Any, str]:
    """
    Find the color dictionary for the plotting groups. If none is available
    (no predefined color column was mapped for this group), auto-generate one.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to find the color dictionary from.

    col_plot_group : str
        Column name to use for the plotting groups.

    col_predefined_color : str, optional
        Name of a column in `df` holding a predefined hex color per value of
        `col_plot_group` (user-mapped via ColumnRole.GROUP_COLOR). If None or
        not present in `df`, an auto-generated palette is used instead.

    Returns
    -------
    dict
        Dictionary with the plotting groups as keys and the colors as values.
    """
    if col_predefined_color and col_predefined_color in df.columns:
        _dict_color = df_col_group_to_dict(df, col_plot_group, col_predefined_color)
    else:
        _dict_color = make_color_dict(df, col_plot_group)
    return _dict_color


def make_plotting_group_color_dicts(
    df: DataFrame, cols_plot_groups: List[str], group_colors: Optional[Dict[str, str]] = None
) -> Dict[str, Dict[Any, str]]:
    """
    Create a dictionary of color dictionaries for the plotting groups and combine them.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to create the color dictionaries from.

    cols_plot_groups : list
        List of the plotting groups columns.

    group_colors : dict, optional
        Mapping of plotting-group column name -> predefined color column name
        (from ColumnMapping.group_colors). Groups without an entry fall back
        to an auto-generated palette.

    Returns
    -------
    dict
        Dictionary with the plotting groups as keys and the colors as values.
    """
    group_colors = group_colors or {}
    _dict_col_colors = {}
    for col in cols_plot_groups:
        _dict_col_colors[col] = find_make_color_dict(df, col, group_colors.get(col))
    return _dict_col_colors


def extract_coordinate_dataframe(
    df: DataFrame,
    list_plot_groups: List[str],
    col_loc_id: str,
    col_longitude: str,
    col_latitude: str,
    col_marker_size: Optional[str] = None,
    default_marker_size: float = DEFAULT_MAP_MARKER_SIZE,
) -> DataFrame:
    """
    Extracts a DataFrame containing unique location coordinates and associated metadata.

    This function groups the input DataFrame by a specified location identifier column
    and extracts the first occurrence of specified columns for each unique location.
    The resulting DataFrame includes the specified plot group columns, location ID,
    longitude, latitude, and a "MAP-MARKER-SIZE" column (renamed from
    `col_marker_size` if mapped, else synthesized as a constant - `plotting.make_map`
    hardcodes the literal column name "MAP-MARKER-SIZE" by default).

    Parameters
    ----------
        df (pd.DataFrame): The input DataFrame containing the data to process.
        list_plot_groups (list): A list of column names representing plot group metadata.
        col_loc_id (str): The name of the column representing unique location identifiers.
        col_longitude (str): The name of the column containing longitude values.
        col_latitude (str): The name of the column containing latitude values.
        col_marker_size (str, optional): Name of the column holding per-row marker
            size values. If None, a constant `default_marker_size` column is used.
        default_marker_size (numeric): Constant marker size used when
            `col_marker_size` is not provided.

    Returns
    -------
        pd.DataFrame: A new DataFrame containing the specified columns for each unique
        location, with one row per unique location ID.
    """
    _cols_grab = list_plot_groups + [col_loc_id, col_longitude, col_latitude]
    if col_marker_size:
        _cols_grab = _cols_grab + [col_marker_size]

    result = df.groupby(col_loc_id)[_cols_grab].first().reset_index(drop=True).copy()

    if col_marker_size:
        if col_marker_size != "MAP-MARKER-SIZE":
            result = result.rename(columns={col_marker_size: "MAP-MARKER-SIZE"})
    else:
        result["MAP-MARKER-SIZE"] = default_marker_size

    return result


def subset_df_locIds(df: DataFrame, col_loc_id: str, loc_ids_subset) -> DataFrame:
    """
    Subset a DataFrame based on a list of location IDs.

    This function filters the rows of a DataFrame where the values in the specified
    column match any of the location IDs provided in the subset list. A copy of the
    filtered DataFrame is returned to avoid modifying the original DataFrame.

    Parameters
    ----------
        df (pandas.DataFrame): The input DataFrame to be filtered.
        col_loc_id (str): The name of the column in the DataFrame containing location IDs.
        loc_ids_subset (list or set): A list or set of location IDs to filter the DataFrame by.

    Returns
    -------
        pandas.DataFrame: A new DataFrame containing only the rows where the values in
                          the specified column match the provided location IDs.
    """
    return df[df[col_loc_id].isin(loc_ids_subset)].copy()


def subset_df_numericFeatures(
    df: DataFrame,
    cols_numeric_simple: List[str],
    cols_numeric_clr: List[str],
    cols_numeric_subset: List[str],
) -> Tuple[DataFrame, List[str], List[str]]:
    """
    Restrict `df`'s numeric analyte columns to `cols_numeric_subset`, keeping
    all non-numeric (metadata) columns and the original column order.

    Parameters
    ----------
    df : pandas DataFrame
        Dataframe to subset.
    cols_numeric_simple, cols_numeric_clr : list
        The full set of simple/CLR analyte columns before subsetting.
    cols_numeric_subset : list
        The analyte columns the user actually selected.

    Returns
    -------
    df : pandas DataFrame
        `df` restricted to metadata columns + the selected analytes.
    cols_numeric_all_subset : list
        `cols_numeric_simple`/`cols_numeric_clr` intersected with `cols_numeric_subset`.
    cols_numeric_clr_subset : list
        Just the CLR subset of `cols_numeric_all_subset`.
    """
    _cols_original = df.columns.to_list()
    _cols_meta = df.columns.difference(cols_numeric_simple + cols_numeric_clr).to_list()
    _cols_numeric_simple_subset = [col for col in cols_numeric_simple if col in cols_numeric_subset]
    _cols_numeric_clr_subset = [col for col in cols_numeric_clr if col in cols_numeric_subset]
    _cols_numeric_all_subset = _cols_numeric_simple_subset + _cols_numeric_clr_subset
    df = df[_cols_meta + _cols_numeric_all_subset].copy().reindex(columns=_cols_original)
    return (
        df,
        _cols_numeric_all_subset,
        _cols_numeric_clr_subset,
    )


def pandas_to_json(df: DataFrame, col_datetime: Optional[str] = None) -> str:
    """
    Serialize `df` to a JSON string (orient="split"), formatting `col_datetime`
    (if given) as an ISO date string first so it round-trips cleanly.

    Parameters
    ----------
    df : pandas DataFrame
        Dataframe to serialize.
    col_datetime : str, optional
        Name of a datetime column to format as "%Y-%m-%d" before serializing.

    Returns
    -------
    str
        JSON string, ready to store in a dcc.Store/Redis session blob.
    """
    df = df.copy()
    if col_datetime:
        df[col_datetime] = df[col_datetime].dt.strftime("%Y-%m-%d")
    return df.to_json(orient="split", date_format="iso", double_precision=15)


def json_to_pandas(
    json_dict: Dict[str, Any], key: str, col_datetime: Optional[str] = None
) -> DataFrame:
    """
    Deserialize `json_dict[key]` (as produced by pandas_to_json) back into a
    DataFrame, re-parsing `col_datetime` (if given) back into datetimes.

    Parameters
    ----------
    json_dict : dict
        A session/store dict whose `key` entry is a pandas_to_json JSON string.
    key : str
        Which entry of `json_dict` to deserialize.
    col_datetime : str, optional
        Name of a column to parse back into datetime dtype.

    Returns
    -------
    pandas DataFrame
    """
    df = read_json(io.StringIO(json_dict[key]), orient="split", precise_float=True)
    if col_datetime:
        df[col_datetime] = to_datetime(df[col_datetime])
    return df


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
    if series.max() == series.min():
        # return series
        return series
    return series / (series.max() - series.min())


def make_df_for_biplot(trnf_data, full_df, col_list=None, num_comp=2, scale=True, prefix="PC"):
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
    temp = DataFrame(trnf_data[:, :num_comp], columns=colnames, index=full_df.index).join(
        full_df[col_list]
    )
    temp.columns = colnames + col_list

    if scale:
        temp[colnames] = temp[colnames].apply(pc_scaler)

    return temp

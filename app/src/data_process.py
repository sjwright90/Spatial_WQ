# This file contains functions to process data for the app
#
# Functions
# ---------
# get_key_cols_meta
# rename_cols_plot_groups
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


def df_col_group_to_dict(df, col_key, col_value):
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


def get_key_cols_meta(df):
    """
    Get the key columns for the metadata.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to get the key columns from.

    Returns
    -------
    tuple
        Tuple of the key columns for the metadata.
        The tuple contains the following elements:
        - col_loc_id: str, name of the location id column
        - col_date: str, name of the date column
        - cols_plot_groups: list, list of the plotting groups columns
        - col_long_lat: list, list of the longitude and latitude columns
    """
    col_loc_id = df.filter(regex=r"^LOCATION-ID_").columns.to_list()[0]
    col_date = df.filter(regex=r"^DATETIME$").columns.to_list()
    # EDITS
    cols_plot_groups = df.filter(regex=r"^LABELS_[0-9A-Za-z]*$").columns.to_list()
    # For backwards compatibility

    # will use this to then populate n color dictionaries
    # and pass them around for color mapping
    if len(col_date) == 0:
        col_date = None
    else:
        col_date = col_date[0]
    col_long_lat = ["LONGITUDE", "LATITUDE"]
    return (
        col_loc_id,
        col_date,
        cols_plot_groups,
        col_long_lat,
    )


def rename_cols_plot_groups(df, cols_plot_groups, cols_key_plot_meta):
    """
    Rename the plotting groups columns to a more readable format.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to rename the plotting groups columns in.

    cols_plot_groups : list
        List of the plotting groups columns to rename.

    Returns
    -------
    pandas DataFrame
        DataFrame with the plotting groups columns renamed.
    """
    _dict_rename = {col: col.split("LABELS_")[-1] for col in cols_plot_groups}
    cols_key_plot_meta = [col.replace("LABELS_", "") for col in cols_key_plot_meta]
    return (
        df.rename(columns=_dict_rename),
        list(_dict_rename.values()),
        cols_key_plot_meta,
    )


def make_color_dict(df, col_plot_group):
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
    _unique_color_list = DISCRETE_COLOR_LIST * (
        _n_unique_colors // len(DISCRETE_COLOR_LIST) + 1
    )
    _dict_color = {
        k: v for k, v in zip(sorted(df[col_plot_group].unique()), _unique_color_list)
    }
    return _dict_color


def find_make_color_dict(df, col_plot_group, new_format=True):
    """
    Find the color dictionary for the plotting groups. If it does not exist,
    make a new one.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to find the color dictionary from.

    col_plot_group : str
        Column name to use for the plotting groups.

    new_format : bool, default True
        Whether to use the new format for the plotting groups.
        If True, it will look for columns starting with "COLORS_".
        If False, it will look for columns ending with "_COLORS".
        For backwards compatibility only, will be removed in the future.


    Returns
    -------
    dict
        Dictionary with the plotting groups as keys and the colors as values.
    """

    if new_format:
        _col_prefix = col_plot_group
        _col_predefined_color = df.filter(
            regex=f"^COLORS_{_col_prefix}$"
        ).columns.to_list()
    else:
        _col_prefix = col_plot_group.split("_LABELS")[0]
        _col_predefined_color = df.filter(
            regex=f"^{_col_prefix}_COLORS$"
        ).columns.to_list()

    if len(_col_predefined_color) == 0:
        _dict_color = make_color_dict(df, col_plot_group)
    else:
        _dict_color = df_col_group_to_dict(df, col_plot_group, _col_predefined_color[0])
    return _dict_color


def make_plotting_group_color_dicts(df, cols_plot_groups, new_format=True):
    """
    Create a dictionary of color dictionaries for the plotting groups and combine them.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to create the color dictionaries from.

    cols_plot_groups : list
        List of the plotting groups columns.

    new_format : bool, default True
        Whether to use the new format for the plotting groups.
        If True, it will look for columns starting with "COLORS_".
        If False, it will look for columns ending with "_COLORS".
        For backwards compatibility only, will be removed in the future.

    Returns
    -------
    dict
        Dictionary with the plotting groups as keys and the colors as values.
    """
    _dict_col_colors = {}
    for col in cols_plot_groups:
        _dict_col_colors[col] = find_make_color_dict(df, col, new_format=new_format)
    return _dict_col_colors


def set_key_col_date(df, col_datetime):
    """
    Set the date column to datetime format. If it fails, set to current date.
    If no date column is provided, print a message.

    Parameters
    ---------
    df : pandas DataFrame
        DataFrame to set the date column for.
    col_datetime : str
        Name of the date column to set.

    Returns
    -------
    df : pandas DataFrame
        DataFrame with the date column set to datetime format.
    """
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
    """
    Extracts and categorizes columns from a DataFrame based on specific naming patterns.

    Parameters
    ----------
        df (pandas.DataFrame): The input DataFrame containing the data.

    Returns
    -------
        tuple: A tuple containing four lists:
            - cols_meta (list): Columns that do not match the specified patterns.
            - cols_numeric_all (list): Combined list of columns matching the "CLR-ANALYTE_"
              and "NUMERIC-ANALYTE_" patterns.
            - cols_simple (list): Columns matching the "NUMERIC-ANALYTE_" pattern.
            - cols_clr (list): Columns matching the "CLR-ANALYTE_" pattern.
    """
    cols_clr = df.filter(regex=r"^CLR-ANALYTE_").columns.to_list()
    cols_simple = df.filter(regex=r"^NUMERIC-ANALYTE_").columns.to_list()
    cols_numeric_all = cols_simple + cols_clr
    cols_meta = df.columns.difference(cols_numeric_all).to_list()
    return cols_meta, cols_numeric_all, cols_simple, cols_clr


def rename_cols_analyte(df, cols_numeric_all, cols_numeric_simple, cols_numeric_clr):
    """
    Parameters
    ----------
    df : pandas.DataFrame
        The input DataFrame whose columns need to be renamed.
    cols_numeric_all : list of str
        A list of column names to be renamed and updated.
    cols_numeric_simple : list of str
        A subset of `cols_numeric_all` to be renamed and updated.
    cols_numeric_clr : list of str
        Another subset of `cols_numeric_all` to be renamed and updated.
    Returns
    -------
    tuple
        A tuple containing:
    """
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
    """
    Extracts a DataFrame containing unique location coordinates and associated metadata.

    This function groups the input DataFrame by a specified location identifier column
    and extracts the first occurrence of specified columns for each unique location.
    The resulting DataFrame includes the specified plot group columns, location ID,
    longitude, latitude, and a "MAP-MARKER-SIZE" column.

    Parameters
    ----------
        df (pd.DataFrame): The input DataFrame containing the data to process.
        list_plot_groups (list): A list of column names representing plot group metadata.
        col_loc_id (str): The name of the column representing unique location identifiers.
        col_longitude (str): The name of the column containing longitude values.
        col_latitude (str): The name of the column containing latitude values.

    Returns
    -------
        pd.DataFrame: A new DataFrame containing the specified columns for each unique
        location, with one row per unique location ID.
    """
    _cols_grab = list_plot_groups + [
        col_loc_id,
        col_longitude,
        col_latitude,
        "MAP-MARKER-SIZE",
    ]
    return df.groupby(col_loc_id)[_cols_grab].first().reset_index(drop=True).copy()


def subset_df_locIds(df, col_loc_id, loc_ids_subset):
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
    df = df.copy()
    if col_datetime:
        df[col_datetime] = df[col_datetime].dt.strftime("%Y-%m-%d")
    return df.to_json(orient="split", date_format="iso", double_precision=15)


def json_to_pandas(json_dict, key, col_datetime=None):
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
        temp[colnames] = temp[colnames].apply(pc_scaler)

    return temp

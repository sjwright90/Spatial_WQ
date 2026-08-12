# This file contains functions to process data for the app
#
# Functions
# ---------
# df_col_group_to_dict
# make_color_dict
# find_make_color_dict
# make_plotting_group_color_dicts
# merge_color_overrides
# assign_custom_group_column
# build_color_mapping_export_df
# build_custom_group_export_df
# extract_coordinate_dataframe
# subset_df_locIds
# subset_df_dateRange
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
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pandas import DataFrame, Timestamp, concat, read_json, to_datetime
import io

# import 'alphabet' from plotly
import plotly.colors as pc

from .logging_config import get_logger

logger = get_logger(__name__)

DISCRETE_COLOR_LIST = pc.qualitative.Alphabet

DEFAULT_MAP_MARKER_SIZE = 10

DEFAULT_CATEGORY_COLOR = "#808080"  # matches plotting._DEFAULT_COLOR
DEFAULT_UNASSIGNED_CATEGORY = "Unassigned"


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


def merge_color_overrides(
    dict_generic_colors: Dict[str, Dict[Any, str]],
    custom_color_overrides: Optional[Dict[str, Dict[str, str]]],
) -> Dict[str, Dict[Any, str]]:
    """
    Non-destructively overlay user-picked colors on top of the default
    per-group color dicts (`meta_data["dict_generic_colors"]`).

    Never mutates `dict_generic_colors` or its nested dicts - returns a new
    dict, so the default palette stays intact and a group/value can always be
    reset back to it. Override keys are matched against the (possibly
    non-string, e.g. numeric) original group values via `str()`, since
    override keys round-trip through a dcc.Store/dropdown as strings.

    Parameters
    ----------
    dict_generic_colors : dict
        `{group_col: {value: hex_color}}`, the auto-generated/predefined
        default color dicts.
    custom_color_overrides : dict, optional
        `{group_col: {str(value): hex_color}}`, user overrides
        (`session["custom_color_overrides"]`). Groups/values absent here pass
        through unchanged.

    Returns
    -------
    dict
        `{group_col: {value: hex_color}}` with overrides applied.
    """
    if not custom_color_overrides:
        return dict_generic_colors

    merged: Dict[str, Dict[Any, str]] = {}
    for group_col, color_dict in dict_generic_colors.items():
        overrides = custom_color_overrides.get(group_col)
        if not overrides:
            merged[group_col] = color_dict
            continue
        _merged_group = dict(color_dict)
        _str_to_key = {str(value): value for value in color_dict}
        for str_value, hex_color in overrides.items():
            key = _str_to_key.get(str_value, str_value)
            _merged_group[key] = hex_color
        merged[group_col] = _merged_group
    return merged


def assign_custom_group_column(
    df_master: DataFrame,
    col_entity_id: str,
    new_col_name: str,
    assignments: Dict[str, List[str]],
    default_value: str = DEFAULT_UNASSIGNED_CATEGORY,
) -> DataFrame:
    """
    Add a new user-defined categorical column to `df_master`, assigning each
    row a category value based on its `col_entity_id` membership in
    `assignments`.

    Parameters
    ----------
    df_master : pandas DataFrame
        The master dataframe to extend. Not mutated - a copy is returned.
    col_entity_id : str
        Name of the composite entity-ID column (`ENTITY_ID`) used to identify
        rows.
    new_col_name : str
        Name of the new column to add.
    assignments : dict
        `{category_value: [entity_id, ...]}` - the rows to assign to each
        category. Every `entity_id` must be present in
        `df_master[col_entity_id]`.
    default_value : str, default "Unassigned"
        Category value for rows not covered by `assignments`.

    Returns
    -------
    pandas DataFrame
        Copy of `df_master` with `new_col_name` added.

    Raises
    ------
    ValueError
        If `assignments` references an `entity_id` not present in
        `df_master[col_entity_id]`.
    """
    known_entity_ids = set(df_master[col_entity_id])
    unknown_ids = set()
    for entity_ids in assignments.values():
        unknown_ids.update(set(entity_ids) - known_entity_ids)
    if unknown_ids:
        raise ValueError(
            f"assignments reference entity_id(s) not present in df_master: {sorted(unknown_ids)}"
        )

    df_master = df_master.copy()
    df_master[new_col_name] = default_value

    reassigned_count = 0
    already_assigned: Dict[str, str] = {}
    for category_value, entity_ids in assignments.items():
        for entity_id in entity_ids:
            if entity_id in already_assigned:
                reassigned_count += 1
            already_assigned[entity_id] = category_value
        df_master.loc[df_master[col_entity_id].isin(entity_ids), new_col_name] = category_value

    if reassigned_count:
        logger.warning(
            "assign_custom_group_column: %d entity_id(s) appeared in more than one "
            "category for '%s' - later category in `assignments` wins.",
            reassigned_count,
            new_col_name,
        )

    return df_master


def build_color_mapping_export_df(
    df_master: DataFrame,
    plotting_groups: List[str],
    col_entity_id: str,
    effective_colors: Dict[str, Dict[Any, str]],
    default_color: str = DEFAULT_CATEGORY_COLOR,
) -> DataFrame:
    """
    Build a long-format export of every row's effective color per plotting
    group: `ENTITY_ID`, `CATEGORY_COL`, `CATEGORY_VALUE`, `CATEGORY_COLOR`.

    Parameters
    ----------
    df_master : pandas DataFrame
        The master dataframe.
    plotting_groups : list
        Plotting-group column names to include.
    col_entity_id : str
        Name of the composite entity-ID column (`ENTITY_ID`).
    effective_colors : dict
        `{group_col: {value: hex_color}}`, typically the output of
        `merge_color_overrides`.
    default_color : str
        Fallback hex color for a value with no entry in `effective_colors`.

    Returns
    -------
    pandas DataFrame
        Columns: `ENTITY_ID`, `CATEGORY_COL`, `CATEGORY_VALUE`, `CATEGORY_COLOR`.
    """
    frames = []
    for group_col in plotting_groups:
        color_dict = effective_colors.get(group_col, {})
        _df = df_master[[col_entity_id, group_col]].copy()
        _df.columns = ["ENTITY_ID", "CATEGORY_VALUE"]
        _df["CATEGORY_COL"] = group_col
        _df["CATEGORY_COLOR"] = _df["CATEGORY_VALUE"].map(
            lambda value: color_dict.get(value, default_color)
        )
        frames.append(_df[["ENTITY_ID", "CATEGORY_COL", "CATEGORY_VALUE", "CATEGORY_COLOR"]])

    if not frames:
        return DataFrame(columns=["ENTITY_ID", "CATEGORY_COL", "CATEGORY_VALUE", "CATEGORY_COLOR"])

    return concat(frames, ignore_index=True)


def build_custom_group_export_df(
    df_master: DataFrame,
    col_entity_id: str,
    col_loc_id: str,
    col_date: Optional[str],
    custom_group_columns: List[str],
    date_filter_range: Optional[Sequence[str]] = None,
) -> DataFrame:
    """
    Build a lookup export of `ENTITY_ID -> LOCATION_ID -> DATE -> [custom
    category columns...]`.

    Parameters
    ----------
    df_master : pandas DataFrame
        The master dataframe.
    col_entity_id, col_loc_id : str
        Names of the composite entity-ID and location-ID columns.
    col_date : str, optional
        Name of the mapped date column, if any. Omitted from the export if
        None.
    custom_group_columns : list
        Names of user-created custom group columns to include. If empty, an
        empty-with-headers frame is returned.
    date_filter_range : list or tuple of str, optional
        `[start_date, end_date]` of the last-Applied upstream date Filter
        (`session["plotting_data"]["date_filter_range_dropdown_value"]`). If
        given (and `col_date` is mapped), any still-`DEFAULT_UNASSIGNED_CATEGORY`
        cell on a row outside this range is overwritten with a
        `DATE-FILTERED-[start->end]` marker in every `custom_group_columns`
        column, so a reader can tell "excluded by the date Filter" apart from
        "in scope but never categorized". A cell that already holds a real
        category value is left untouched - the entity picker used to create
        custom groups already only offers Filter-included entities, so a
        non-default value here can only come from a group created under a
        wider/no Filter and must not be silently overwritten.

    Returns
    -------
    pandas DataFrame
        Columns: `ENTITY_ID`, `LOCATION_ID`, `DATE` (if `col_date` given),
        followed by `custom_group_columns`.
    """
    _cols_source = [col_entity_id, col_loc_id]
    _cols_export = ["ENTITY_ID", "LOCATION_ID"]
    if col_date:
        _cols_source.append(col_date)
        _cols_export.append("DATE")
    _cols_source += custom_group_columns
    _cols_export += custom_group_columns

    if not custom_group_columns:
        return DataFrame(columns=_cols_export)

    df_export = df_master[_cols_source].copy()
    df_export.columns = _cols_export

    if date_filter_range and col_date:
        start, end = Timestamp(date_filter_range[0]), Timestamp(date_filter_range[1])
        # Negation of subset_df_dateRange's exact inclusive test, so NaT
        # (unparseable) dates - which subset_df_dateRange already excludes
        # from the Filter-included entity picker/PCA/clustering - are
        # likewise treated as out-of-range here, not left "Unassigned".
        in_range = (df_master[col_date] >= start) & (df_master[col_date] <= end)
        out_of_range = ~in_range
        marker = f"DATE-FILTERED-[{start.date()}->{end.date()}]"
        for col in custom_group_columns:
            still_unassigned = df_export[col] == DEFAULT_UNASSIGNED_CATEGORY
            df_export.loc[out_of_range.values & still_unassigned, col] = marker

    return df_export


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


def subset_df_dateRange(
    df: DataFrame, col_date: Optional[str], date_range: Optional[Sequence[str]]
) -> DataFrame:
    """
    Subset a DataFrame to rows whose `col_date` falls within an inclusive
    `[start, end]` date range - the upstream "Filter" (as opposed to the
    downstream, display-only "Mask" applied in `DataPlotter.df_between_dates`
    after PCA/PaCMAP have already been computed). Day-level, not year-level -
    matches the `dcc.DatePickerRange` filter control's precision.

    A no-op copy passthrough when `col_date` is falsy (no date column mapped)
    or `date_range` is falsy/None (no filter applied) - callers do not need
    to special-case "date filtering is disabled".

    Parameters
    ----------
    df : pandas DataFrame
        The input DataFrame to be filtered.
    col_date : str, optional
        Name of the datetime64 column in `df` to filter on.
    date_range : list or tuple of str, optional
        `[start_date, end_date]`, inclusive, as ISO date strings (e.g. from
        `dcc.DatePickerRange`) or anything `pandas.Timestamp` can parse.

    Returns
    -------
    pandas.DataFrame
        A copy of `df`, restricted to `date_range` if both `col_date` and
        `date_range` are given, otherwise an unfiltered copy.
    """
    if not col_date or not date_range:
        return df.copy()
    start, end = Timestamp(date_range[0]), Timestamp(date_range[1])
    return df[(df[col_date] >= start) & (df[col_date] <= end)].copy()


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

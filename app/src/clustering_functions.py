"""KMeans clustering feeding the "auto-cluster" custom-group workflow.

Mirrors `dimension_reduction_functions.process_dimension_reduction`'s
subset/CLR-transform steps so clustering runs on the same selected
locations/analytes currently applied to the PCA/PaCMAP plots, then adds a
choice of feature space (`FEATURE_SPACE_CLR` vs `FEATURE_SPACE_PCA`) and a
KMeans fit on top.
"""

from typing import List, Optional, Sequence

import numpy as np
from pandas import DataFrame
from sklearn.cluster import KMeans

from .data_process import subset_df_dateRange, subset_df_locIds, subset_df_numericFeatures
from .compositional_data_functions import clr_transform_scale
from .dimension_reduction_functions import pca_loading_matrix, MAX_PCA_COMPONENTS
from .logging_config import get_logger

logger = get_logger(__name__)

FEATURE_SPACE_CLR = "clr"
FEATURE_SPACE_PCA = "pca"
FEATURE_SPACE_CHOICES = (FEATURE_SPACE_CLR, FEATURE_SPACE_PCA)


def run_kmeans(df_features: DataFrame, n_clusters: int) -> np.ndarray:
    """Fit KMeans on `df_features` and return one integer cluster label
    (0-indexed) per row.

    Parameters
    ----------
    df_features : pandas DataFrame
        Fully numeric feature matrix, one row per sample.
    n_clusters : int
        Number of clusters to fit.

    Returns
    -------
    np.ndarray
        Cluster label per row, same order as `df_features`.
    """
    return KMeans(n_clusters=n_clusters, random_state=42, n_init=10).fit_predict(
        df_features.values
    )


def build_pca_feature_matrix(df_clr: DataFrame, analytes: List[str]) -> DataFrame:
    """Raw (unscaled) PCA scores for every computed component.

    This is deliberately NOT `dimension_reduction_functions.make_df_for_biplot`'s
    min-max-scaled scores - those are scaled per-component purely so the
    biplot's loading vectors aren't visually masked, which would distort each
    component's variance-proportional range (PC1 should have a wider range
    than PC5) before clustering on it.

    Parameters
    ----------
    df_clr : pandas DataFrame
        CLR-transformed + scaled analyte dataframe (see `clr_transform_scale`).
    analytes : list
        Analyte columns of `df_clr` to run PCA on.

    Returns
    -------
    pandas DataFrame
        Columns `PC1..PCn` (n capped at `MAX_PCA_COMPONENTS`/available
        analytes/samples), same index as `df_clr`.
    """
    n_components = max(1, min(MAX_PCA_COMPONENTS, len(analytes), len(df_clr)))
    _, trns_df, _ = pca_loading_matrix(df_clr[analytes], n_components=n_components)
    columns = [f"PC{i + 1}" for i in range(n_components)]
    return DataFrame(trns_df, columns=columns, index=df_clr.index)


def process_clustering(
    df: DataFrame,
    col_loc_id: str,
    col_entity_id: str,
    cols_numeric_simple: List[str],
    cols_numeric_clr: List[str],
    feature_selection: List[str],
    loc_id_selection: List[str],
    feature_space: str,
    n_clusters: int,
    col_date: Optional[str] = None,
    date_range: Optional[Sequence[str]] = None,
) -> DataFrame:
    """Subset `df` to the selected date range/locations/analytes, build a
    feature matrix in `feature_space`, and run KMeans on it.

    Parameters
    ----------
    df : pandas DataFrame
        Full master dataframe to subset and transform.
    col_loc_id, col_entity_id : str
        Location-ID / composite entity-ID column names.
    cols_numeric_simple, cols_numeric_clr : list
        Analyte columns to standard-scale only, vs. CLR-transform then scale.
    feature_selection : list
        Subset of analyte columns the user selected (mirrors the PCA/PaCMAP
        "Apply" selection).
    loc_id_selection : list
        Subset of location IDs to include.
    feature_space : str
        `FEATURE_SPACE_CLR` to cluster on the CLR-transformed analyte matrix,
        or `FEATURE_SPACE_PCA` to cluster on the unscaled PCA scores of that
        same matrix.
    n_clusters : int
        Number of KMeans clusters; must be between 2 and the number of
        selected samples.
    col_date : str, optional
        Name of the mapped date column. Together with `date_range`, this is
        the upstream date "Filter" (see
        `dimension_reduction_functions.process_dimension_reduction`) -
        applied before clustering so excluded rows can never end up in a
        cluster assignment.
    date_range : list of str, optional
        `[start_date, end_date]`, inclusive. No filtering applied if None.

    Returns
    -------
    pandas DataFrame
        Two columns: `col_entity_id`, `"cluster"` (0-indexed int label) - one
        row per sample in the selection.

    Raises
    ------
    ValueError
        Empty feature_selection/loc_id_selection, an unrecognized
        feature_space, or n_clusters outside [2, n_samples].
    """
    if not feature_selection:
        logger.error("process_clustering called with empty feature_selection")
        raise ValueError("No analytes selected for clustering")
    if not loc_id_selection:
        logger.error("process_clustering called with empty loc_id_selection")
        raise ValueError("No locations selected for clustering")
    if feature_space not in FEATURE_SPACE_CHOICES:
        raise ValueError(f"Unknown feature_space {feature_space!r}")

    df = subset_df_dateRange(df, col_date, date_range)
    df = subset_df_locIds(df, col_loc_id, loc_id_selection)
    df, cols_numeric_all, cols_numeric_clr_subset = subset_df_numericFeatures(
        df, cols_numeric_simple, cols_numeric_clr, feature_selection
    )
    df_clr = clr_transform_scale(df, cols_numeric_all, cols_numeric_clr_subset)

    if not isinstance(n_clusters, int) or not (2 <= n_clusters <= len(df_clr)):
        raise ValueError(
            "n_clusters must be an integer between 2 and "
            f"{len(df_clr)} (number of selected samples), got {n_clusters!r}"
        )

    if feature_space == FEATURE_SPACE_PCA:
        feature_matrix = build_pca_feature_matrix(df_clr, cols_numeric_all)
    else:
        feature_matrix = df_clr[cols_numeric_all]

    labels = run_kmeans(feature_matrix, n_clusters)
    return DataFrame({col_entity_id: df_clr[col_entity_id].values, "cluster": labels})

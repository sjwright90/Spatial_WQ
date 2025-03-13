from pandas import DataFrame
from sklearn.decomposition import PCA
import pacmap

from typing import Type, Tuple

from .data_process import (
    make_df_for_biplot,
    subset_df_locIds,
    subset_df_numericFeatures,
)
from .compositional_data_functions import clr_transform_scale


# cache function for PCA
def run_pca(df: DataFrame, cat_cols: list, analytes: list) -> tuple:
    """
    Run PCA on a dataframe.

    Parameters
    ----------
    df : pandas dataframe
        Dataframe to run PCA on.
    cat_cols : list-like
        Categorical columns in df.
    analytes : list-like
        Analytes to run PCA on.

    Returns
    -----
    df_plot
        Dataframe for plotting biplot.
    ldg_df
        Loading matrix.
    expl_var
        Explained variance.
    """
    pca_obj, trns_df, ldg_df = pca_loading_matrix(
        df[analytes],
        n_components=2,
    )
    df_plot = make_df_for_biplot(trns_df, df, col_list=cat_cols)
    expl_var = pca_obj.explained_variance_ratio_.tolist()
    return df_plot, ldg_df, expl_var


# cache function for PacMAP with 100 neighbors
# @cache.memoize()
def run_pmap(df: DataFrame, cat_cols: list, analytes: list, n_neighbors: int = 15):
    """
    Run PacMAP on a dataframe.

    Parameters
    ----------
    df : pandas dataframe
        Dataframe to run PCA on.
    cat_cols : list-like
        Categorical columns in df.
    analytes : list-like
        Analytes to run PCA on.
    n_neighbors : int, default 15
        Number of neighbors for PacMAP.

    Returns
    -----
    df_pmap
        Dataframe for plotting biplot.
    """
    pmap_trns = pacmap.PaCMAP(n_neighbors=n_neighbors, random_state=42).fit_transform(
        df[analytes]
    )
    df_pmap = make_df_for_biplot(pmap_trns, df, col_list=cat_cols, prefix="PMAP")
    return df_pmap


def pca_loading_matrix(df, n_components=2):
    """
    Performs PCA and calculates loading matrix.

    Parameters
    ----------
    df : pandas dataframe
        Fully numeric dataframe to appy PCA to.

    label_list : list-like, default None
        List of labels for loading matrix, if None the columns of df will be
        used.

    n_components : int, default 6
        Number of PCA components.

    Returns
    -----
    temp_pca
        sklearn PCA object.

    df_pca
        numpy.array object of PCA transformed df

    ld_mat
        pd.dataframe format of loading matrix
    """

    # if labels list not given assign columns of df
    labels_list = df.columns.tolist()

    # build PCA
    temp_pca = PCA(n_components=n_components, random_state=42)

    # transform
    df_pca = temp_pca.fit_transform(df)

    # call loading matrix function
    ld_mat = loading_matrix(temp_pca, labels_list)

    return temp_pca, df_pca, ld_mat


def loading_matrix(pca_obj, labels_list):
    """
    Calculates loading matrix from a PCA object.

    Parameters
    ----------
    pca_obj : sklearn PCA object
        Used to get PCA components.

    label_list : list-like
        Labels associated with PCA object must have #rows==#columns in PCA
        object.

    Returns
    -----
    ld_mat
        pandas dataframe.
    """

    mat = pca_obj.components_.T
    # build data frame
    ld_mat = DataFrame(
        mat,
        columns=[f"PC{x+1}" for x in range(pca_obj.components_.shape[0])],
        index=labels_list,
    )
    # add metals to data frame
    ld_mat["metals"] = labels_list
    return ld_mat


def process_dimension_reduction(
    df,
    col_loc_id,
    cols_meta,
    cols_numeric_simple,
    cols_numeric_clr,
    feature_selection,
    loc_id_selection,
    n_neighbors,
) -> Type[Tuple[DataFrame, DataFrame, DataFrame]]:
    df = subset_df_locIds(df, col_loc_id, loc_id_selection)
    df, cols_numeric_all, cols_numeric_clr = subset_df_numericFeatures(
        df, cols_numeric_simple, cols_numeric_clr, feature_selection
    )
    df_clr = clr_transform_scale(df, cols_numeric_all, cols_numeric_clr)
    df_plot_pca, ldg_df, expl_var = run_pca(df_clr, cols_meta, cols_numeric_all)
    df_plot_pmap = run_pmap(df_clr, cols_meta, cols_numeric_all, n_neighbors)
    return (df_plot_pca, ldg_df, expl_var), df_plot_pmap

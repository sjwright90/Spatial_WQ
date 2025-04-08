import numpy as np
from sklearn.preprocessing import StandardScaler
from pandas import DataFrame


def array_anynull(X: np.ndarray) -> bool:
    """
    Test is any NaN/null cells in a pandas dataframe

    Inputs
    ----------
    X: np.ndarray
        Data to be tested

    Returns
    -----

        bool, True if NaN present, False otherwise
    """
    return np.isnan(X).any()


def clr_transform(X: np.ndarray) -> np.ndarray:
    """
    Centred Log Ratio transformation.

    Parameters
    ----------
    X : np.ndarray
        Data to be transformed.

    Returns
    -----
    np.ndarray
        Transformed data.
    """
    # check missing values
    X[X == 0.0] = np.nan
    if array_anynull(X):
        raise ValueError(
            "Missing values or zeros detected in data, please remove before transformation"
        )
    X = np.array(X)
    X = np.divide(X, np.sum(X, axis=1).reshape(-1, 1))  # Closure operation
    Y = np.log(X)  # Log operation
    nvars = max(X.shape[1], 1)  # if the array is empty we'd get a div-by-0 error
    G = (1 / nvars) * np.nansum(Y, axis=1)[:, np.newaxis]
    Y -= G
    return Y


def clr_transform_scale(df: DataFrame, cols_numeric_all, cols_numeric_clr) -> DataFrame:
    """
    Centred Log Ratio transformation.

    Parameters
    ----------
    df : DataFrame
        Data to be transformed.

    cols_numeric_all : list
        Columns to transform with StandardScaler

    cols_numeric_clr : list
        Columns to transform with CLR before StandardScaler

    Returns
    -----
    DataFrame
        Transformed data.
    """
    df[cols_numeric_clr] = clr_transform(df[cols_numeric_clr].values)
    df[cols_numeric_all] = StandardScaler().fit_transform(df[cols_numeric_all].values)
    return df

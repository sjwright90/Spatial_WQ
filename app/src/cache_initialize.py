import hashlib
from typing import Any
from pandas import DataFrame
from pandas.util import hash_pandas_object


def make_custom_cache_key_dimensionReduction(*args: Any, **kwargs: Any) -> str:
    """
    Generate a cache key for the dimension reduction functions.

    Not currently wired up to any Flask-Caching decorator - caching is
    scaffolded but unused (see GOTCHAS.md). Kept as ordinary unused code, not
    a dead-code block to remove.
    """
    keys = []
    keys.append(str(kwargs.get("feature_selection")))
    keys.append(str(kwargs.get("loc_id_selection")))
    keys.append(str(kwargs.get("n_neighbors")))
    keys.append(str(kwargs.get("data_hash")))
    return "_".join(keys)  # Joining the keys into a single string for the cache key


def generate_df_hash_version(df: DataFrame) -> str:
    """
    Generate a hash for the dataframe by sorting it first to ensure consistency,
    even if the order of rows or columns changes.

    Actively used by DataPreprocessor.__init__ (data_manager.py) to fingerprint
    uploaded data - unlike make_custom_cache_key_dimensionReduction above, this
    function is not dead/unused code.
    """
    # Sort the DataFrame to ensure consistent ordering
    sorted_df = df.sort_values(by=list(df.columns), kind="mergesort").sort_index(
        axis=1, kind="mergesort"
    )

    # Using hash_pandas_object to generate a hashable representation of the DataFrame
    hashable_data = hash_pandas_object(sorted_df, index=False).values

    # Creating a hash from the hashable data
    data_hash = hashlib.md5(hashable_data).hexdigest()

    return data_hash

import hashlib
from pandas.util import hash_pandas_object


def make_custom_cache_key_dimensionReduction(*args, **kwargs):
    """
    Generate a cache key for the dimension reduction functions.
    """
    keys = []
    keys.append(str(kwargs.get("feature_selection")))
    keys.append(str(kwargs.get("loc_id_selection")))
    keys.append(str(kwargs.get("n_neighbors")))
    keys.append(str(kwargs.get("data_hash")))
    return "_".join(keys)  # Joining the keys into a single string for the cache key


def generate_df_hash_version(df):
    """
    Generate a hash for the dataframe by sorting it first to ensure consistency,
    even if the order of rows or columns changes.
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

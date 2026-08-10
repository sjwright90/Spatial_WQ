from .plotting import make_fig_pca, make_fig_pmap, empty_fig
from .data_process import (
    df_col_group_to_dict,
    make_plotting_group_color_dicts,
    extract_coordinate_dataframe,
    subset_df_locIds,
    pandas_to_json,
    json_to_pandas,
)
from .data_model import ColumnMapping
from .data_mapping import build_mapped_dataset

from .cache_initialize import generate_df_hash_version

import pandas as pd

import base64
import io
import json


DEFAULT_MARKER_SYMBOL = "circle"


class DataPreprocessor:
    """Ingests a raw uploaded CSV plus a user-supplied ColumnMapping (see
    data_model.py) and builds the internal structures the rest of the app
    consumes. Column classification is driven entirely by `mapping` -
    see data_mapping.build_mapped_dataset for validation/coercion details.

    If the mapping fails validation, `self.validation.has_errors` is True and
    every other data attribute (`df_master`, `cols_key_plot`, `cols_key_meta`,
    `df_coordinate`, `dict_marker_map`, `dict_generic_colors`, `loc_id_all`,
    `cols_numeric_all`) is left as None - callers must check
    `self.validation.has_errors` before calling `get_session_dict()`.
    """

    def __init__(self, content_string: str, mapping: ColumnMapping):
        decoded = base64.b64decode(content_string)
        df_raw = pd.read_csv(io.BytesIO(decoded), float_precision="high")

        self.content_hash = generate_df_hash_version(df_raw)

        mapped = build_mapped_dataset(df_raw, mapping)
        self.validation = mapped.validation

        self.df_master = None
        self.cols_key_plot = None
        self.cols_key_meta = None
        self.df_coordinate = None
        self.dict_marker_map = None
        self.dict_generic_colors = None
        self.loc_id_all = None
        self.cols_numeric_all = None

        if self.validation.has_errors:
            return

        self.df_master = mapped.df_master
        self.cols_key_plot = mapped.cols_key_plot
        self.cols_key_meta = mapped.cols_key_meta

        self.df_master = self.df_master.sort_values(
            by=[
                *self.cols_key_meta["plotting_groups"],
                self.cols_key_meta["loc_id"],
            ]
        ).reset_index(drop=True)

        self.df_coordinate = extract_coordinate_dataframe(
            self.df_master,
            self.cols_key_meta["plotting_groups"],
            self.cols_key_meta["loc_id"],
            self.cols_key_meta["long_lat"][0],
            self.cols_key_meta["long_lat"][1],
            col_marker_size=self.cols_key_meta["map_marker_size"],
        )

        self.loc_id_all = self.df_master[self.cols_key_meta["loc_id"]].unique().tolist()

        if self.cols_key_meta["marker_symbol"]:
            self.dict_marker_map = df_col_group_to_dict(
                self.df_master,
                self.cols_key_meta["loc_id"],
                self.cols_key_meta["marker_symbol"],
            )
        else:
            # No marker-symbol role mapped - fill every location with a
            # constant default so plotting.py's direct dict indexing
            # (name_marker_map[loc_code]) never KeyErrors.
            self.dict_marker_map = {loc: DEFAULT_MARKER_SYMBOL for loc in self.loc_id_all}

        self.dict_generic_colors = make_plotting_group_color_dicts(
            self.df_master,
            self.cols_key_meta["plotting_groups"],
            group_colors=mapping.group_colors,
        )

        self.cols_numeric_all = self.cols_key_plot["numeric_all"]

    def get_session_dict(self):
        return {
            "df_master": pandas_to_json(self.df_master, self.cols_key_meta["date"]),
            "meta_data": {
                "cols_key_plot": self.cols_key_plot,
                "cols_key_meta": self.cols_key_meta,
                "dict_marker_map": self.dict_marker_map,
                "dict_generic_colors": self.dict_generic_colors,
                "loc_id_all": self.loc_id_all,
                "cols_numeric_all": self.cols_numeric_all,
                "df_coordinate": self.df_coordinate.to_json(),
            },
            "data_hash": {
                "data_hash": self.content_hash,
            },
            "working_data": None,  # Placeholder for working data
            "plotting_data": {
                "feature_selection_dropdown_options": self.cols_key_plot["numeric_all"],
                "feature_selection_dropdown_value": self.cols_key_plot["numeric_all"],
                "loc_id_dropdown_options": self.loc_id_all,
                "loc_id_dropdown_value": self.loc_id_all,
                "map_group_dropdown_options": self.cols_key_meta["plotting_groups"],
                "map_group_dropdown_value": self.cols_key_meta["plotting_groups"][0],
                "plot_group_dropdown_1_options": self.cols_key_meta["plotting_groups"],
                "plot_group_dropdown_1_value": self.cols_key_meta["plotting_groups"][0],
                "plot_group_dropdown_2_options": self.cols_key_meta["plotting_groups"],
                "plot_group_dropdown_2_value": self.cols_key_meta["plotting_groups"][0],
                "pmap_neighbors": 15,  # Default value for neighbors in pmap
            },
            "version": 1,
        }


class DataPlotter:
    def __init__(
        self,
        working_data,
        meta_data,
        selected_loc_ids,
        plot_groups,
        date_range,
    ):
        self.initialize_data(
            working_data,
            meta_data,
            selected_loc_ids,
            plot_groups,
            date_range,
        )

    def initialize_data(
        self,
        working_data,
        meta_data,
        selected_loc_ids,
        plot_groups,
        date_range,
    ):
        try:
            self.working_data = json.loads(working_data)
            self.meta_data = json.loads(meta_data)
            self.cols_key_plot = self.meta_data["cols_key_plot"]
            self.cols_key_meta = self.meta_data["cols_key_meta"]
            self.dict_marker_map = self.meta_data["dict_marker_map"]
            self.load_dataframes(selected_loc_ids)
            self.df_between_dates(date_range)
            self.ldg_df = pd.read_json(io.StringIO(self.working_data["ldg_df"]))
            self.expl_var = self.working_data["expl_var"]
            self.plot_groups = plot_groups
        except Exception as e:
            print(f"Error in initialize_data: {e}")
            raise ValueError("Error initializing data") from e

    def load_dataframes(self, selected_loc_ids):
        self.df_plot_pca = json_to_pandas(
            self.working_data, "df_plot_pca", self.meta_data["cols_key_meta"]["date"]
        )
        self.df_plot_pmap = json_to_pandas(
            self.working_data, "df_plot_pmap", self.meta_data["cols_key_meta"]["date"]
        )
        if selected_loc_ids is not None:
            self.selected_loc_ids = [
                point["customdata"][0] for point in selected_loc_ids["points"]
            ]
            self.df_plot_pca = self._subset_df_locIds(self.df_plot_pca)
            self.df_plot_pmap = self._subset_df_locIds(self.df_plot_pmap)
        else:
            self.selected_loc_ids = self.meta_data["loc_id_all"]

    def df_between_dates(self, date_range):
        assert self.df_plot_pca.index.equals(self.df_plot_pmap.index)
        col_date = self.cols_key_meta["date"]
        if not col_date:
            # No date column mapped - date-range filtering is disabled, keep
            # all rows.
            return
        _series_years = self.df_plot_pca[col_date].dt.year
        _idx_between_dates = self.df_plot_pca[
            (_series_years >= date_range[0]) & (_series_years <= date_range[1])
        ].index
        self.df_plot_pca = self.df_plot_pca.loc[_idx_between_dates].copy()
        self.df_plot_pmap = self.df_plot_pmap.loc[_idx_between_dates].copy()

    def _subset_df_locIds(self, df):
        return subset_df_locIds(
            df,
            self.cols_key_meta["loc_id"],
            self.selected_loc_ids,
        ).reset_index(drop=True)

    @staticmethod
    def empty_figs():
        return empty_fig(), empty_fig()

    def plot_pmap(self, n_neighbors):
        return make_fig_pmap(
            self.df_plot_pmap,
            self.meta_data["dict_generic_colors"][self.plot_groups[0]],
            self.meta_data["dict_generic_colors"][self.plot_groups[1]],
            self.dict_marker_map,
            self.cols_key_meta["loc_id"],
            self.plot_groups[0],
            self.plot_groups[1],
            self.cols_key_meta["date"],
            n_neighbors,
        )

    def plot_pca(self):
        return make_fig_pca(
            self.df_plot_pca,
            self.ldg_df,
            self.expl_var,
            self.meta_data["dict_generic_colors"][self.plot_groups[0]],
            self.meta_data["dict_generic_colors"][self.plot_groups[1]],
            self.dict_marker_map,
            self.cols_key_meta["loc_id"],
            self.plot_groups[0],
            self.plot_groups[1],
            self.cols_key_meta["date"],
        )


class SessionManager:
    @staticmethod
    def package_plotting_data(plot_components_pca, plot_components_pmap, meta_data):
        dict_working_data = {
            "df_plot_pca": pandas_to_json(
                plot_components_pca[0], meta_data["cols_key_meta"]["date"]
            ),
            "ldg_df": plot_components_pca[1].to_json(),
            "expl_var": plot_components_pca[2],
            "df_plot_pmap": pandas_to_json(
                plot_components_pmap, meta_data["cols_key_meta"]["date"]
            ),
        }
        return dict_working_data

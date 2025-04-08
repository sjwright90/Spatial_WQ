from .plotting import make_fig_pca, make_fig_pmap, empty_fig
from .data_process import (
    get_key_cols_plot,
    set_key_col_date,
    df_col_group_to_dict,
    get_key_cols_meta,
    make_plotting_group_color_dicts,
    extract_coordinate_dataframe,
    rename_cols_analyte,
    subset_df_locIds,
    pandas_to_json,
    json_to_pandas,
)

from .cache_initialize import generate_df_hash_version

import pandas as pd

import base64
import io
import json

from datetime import datetime


# TODO: make date parsing more 'generous'
class DataPreprocessor:
    def __init__(self, content_string):
        decoded = base64.b64decode(content_string)

        self.df_master = pd.read_csv(io.BytesIO(decoded), float_precision="high")
        # get hash of content
        self.content_hash = generate_df_hash_version(self.df_master)

        self.cols_key_plot = dict(
            zip(
                ["meta", "numeric_all", "numeric_simple", "numeric_clr"],
                get_key_cols_plot(self.df_master),
            )
        )
        self.df_master, cols_key_plot_new = rename_cols_analyte(
            self.df_master,
            self.cols_key_plot["numeric_all"],
            self.cols_key_plot["numeric_simple"],
            self.cols_key_plot["numeric_clr"],
        )
        self.cols_key_plot["numeric_all"] = cols_key_plot_new[0]
        self.cols_key_plot["numeric_simple"] = cols_key_plot_new[1]
        self.cols_key_plot["numeric_clr"] = cols_key_plot_new[2]

        self.cols_key_meta = dict(
            zip(
                [
                    "loc_id",
                    "date",
                    "plotting_groups",
                    "long_lat",
                ],
                get_key_cols_meta(self.df_master),
            )
        )
        self.df_master = set_key_col_date(
            self.df_master,
            self.cols_key_meta["date"],
        )

        self.df_master = self.df_master[
            self.cols_key_plot["meta"] + self.cols_key_plot["numeric_all"]
        ].copy()

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
        )

        self.dict_marker_map = df_col_group_to_dict(
            self.df_master,
            self.cols_key_meta["loc_id"],
            "MARKERS-PLOT-DOMAIN",
        )

        self.dict_generic_colors = make_plotting_group_color_dicts(
            self.df_master,
            self.cols_key_meta["plotting_groups"],
        )

        self.loc_id_all = self.df_master[self.cols_key_meta["loc_id"]].unique().tolist()
        self.cols_numeric_all = self.cols_key_plot["numeric_all"]

    def generate_dict_data_structure(self):

        return (
            json.dumps(
                {
                    "df_master": pandas_to_json(
                        self.df_master, self.cols_key_meta["date"]
                    ),
                }
            ),
            json.dumps(
                {
                    "cols_key_plot": self.cols_key_plot,
                    "cols_key_meta": self.cols_key_meta,
                    "dict_marker_map": self.dict_marker_map,
                    "dict_generic_colors": self.dict_generic_colors,
                    "loc_id_all": self.loc_id_all,
                    "cols_numeric_all": self.cols_numeric_all,
                    "df_coordinate": self.df_coordinate.to_json(),
                },
            ),
            json.dumps(
                {
                    "data_hash": self.content_hash,
                }
            ),
        )


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
        _series_years = self.df_plot_pca[self.cols_key_meta["date"]].dt.year
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

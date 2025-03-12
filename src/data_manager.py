from .plotting import make_fig_pca, make_fig_pmap
from .data_process import (
    get_key_cols_plot,
    extract_color_dict,
    extract_marker_dict,
    get_key_cols_meta,
    extract_coordinate_dataframe,
    rename_cols_analyte,
)

from .cache_initialize import generate_df_hash_version

import pandas as pd

import base64
import io
import json


class DataPreprocessor:
    def __init__(self, content_string):
        decoded = base64.b64decode(content_string)

        self.df_master = pd.read_csv(io.BytesIO(decoded))

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
        self.df_master = self.df_master[
            self.cols_key_plot["meta"] + self.cols_key_plot["numeric_all"]
        ].copy()
        self.cols_key_meta = dict(
            zip(
                ["loc_id", "map_group", "plot_group", "long_lat"],
                get_key_cols_meta(self.df_master),
            )
        )
        self.df_coordinate = extract_coordinate_dataframe(
            self.df_master,
            self.cols_key_meta["map_group"],
            self.cols_key_meta["loc_id"],
            self.cols_key_meta["long_lat"][0],
            self.cols_key_meta["long_lat"][1],
        )
        self.dict_color_map = extract_color_dict(
            self.df_master,
            self.cols_key_meta["map_group"],
            "COLORS-ALL-DOMAIN",
        )
        self.dict_marker_map = extract_marker_dict(
            self.df_master,
            self.cols_key_meta["loc_id"],
            "MARKERS-PLOT-DOMAIN",
        )

        self.loc_id_all = self.df_master[self.cols_key_meta["loc_id"]].unique().tolist()
        self.cols_numeric_all = self.cols_key_plot["numeric_all"]

    def generate_dict_data_structure(self):
        return (
            json.dumps(
                {
                    "df_master": self.df_master.to_json(),
                }
            ),
            json.dumps(
                {
                    "cols_key_plot": self.cols_key_plot,
                    "cols_key_meta": self.cols_key_meta,
                    "dict_color_map": self.dict_color_map,
                    "dict_marker_map": self.dict_marker_map,
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
    ):
        self.working_data = json.loads(working_data)
        self.meta_data = json.loads(meta_data)

        # load the meta data
        self.cols_key_plot = self.meta_data["cols_key_plot"]
        self.cols_key_meta = self.meta_data["cols_key_meta"]
        self.dict_color_map = self.meta_data["dict_color_map"]
        self.dict_marker_map = self.meta_data["dict_marker_map"]

        # load the dataframes and subset if necessary
        if not selected_loc_ids is None:
            selected_loc_ids = [
                point["customdata"][0] for point in selected_loc_ids["points"]
            ]
            self.df_plot_pca = pd.read_json(
                io.StringIO(self.working_data["df_plot_pca"])
            )
            self.df_plot_pca = (
                self.df_plot_pca[
                    self.df_plot_pca[self.cols_key_meta["loc_id"]].isin(
                        selected_loc_ids
                    )
                ]
                .copy()
                .reset_index(drop=True)
            )

            self.df_plot_pmap = pd.read_json(
                io.StringIO(self.working_data["df_plot_pmap"])
            )

            self.df_plot_pmap = (
                self.df_plot_pmap[
                    self.df_plot_pmap[self.cols_key_meta["loc_id"]].isin(
                        selected_loc_ids
                    )
                ]
                .copy()
                .reset_index(drop=True)
            )
        else:
            self.df_plot_pca = pd.read_json(
                io.StringIO(self.working_data["df_plot_pca"])
            )
            self.df_plot_pmap = pd.read_json(
                io.StringIO(self.working_data["df_plot_pmap"])
            )

        # load the additional PCA plotting data
        self.ldg_df = pd.read_json(io.StringIO(self.working_data["ldg_df"]))
        self.expl_var = self.working_data["expl_var"]

    def plot_pmap(self):
        return make_fig_pmap(
            self.df_plot_pmap,
            self.dict_color_map,
            self.dict_marker_map,
            self.cols_key_meta["loc_id"],
        )

    def plot_pca(self):
        return make_fig_pca(
            self.df_plot_pca,
            self.ldg_df,
            self.expl_var,
            self.dict_color_map,
            self.dict_marker_map,
            self.cols_key_meta["loc_id"],
        )

from .plotting import make_fig_pca, make_fig_pmap, empty_fig, PlotContext
from .data_process import (
    df_col_group_to_dict,
    make_plotting_group_color_dicts,
    make_color_dict,
    assign_custom_group_column,
    extract_coordinate_dataframe,
    subset_df_locIds,
    pandas_to_json,
    json_to_pandas,
)
from .data_model import ColumnMapping
from .data_mapping import build_mapped_dataset
from .dimension_reduction_functions import MAX_PCA_COMPONENTS

from .cache_initialize import generate_df_hash_version
from .logging_config import get_logger

import pandas as pd

import base64
import io
import json
from typing import Any, Dict, List, Optional, Tuple

logger = get_logger(__name__)

DEFAULT_MARKER_SYMBOL = "circle"


def _require(mapping: Dict[str, Any], key: str, context: str) -> Any:
    """Look up `key` in `mapping` (a cols_key_meta/cols_key_plot/meta_data
    dict), raising a clear, diagnostic KeyError instead of the bare one dict
    indexing gives. These dicts round-trip through JSON/dcc.Store/Redis, so a
    missing key usually means a stale/incompatible session blob (e.g. from an
    older app version) rather than a local bug - `context` names which dict,
    so the error is actionable."""
    try:
        return mapping[key]
    except KeyError:
        logger.error("Missing expected key '%s' in %s", key, context)
        raise KeyError(
            f"'{key}' missing from {context} - the session data may be from an "
            "incompatible/older version of the app."
        ) from None


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

    def __init__(self, content_string: str, mapping: ColumnMapping) -> None:
        try:
            decoded = base64.b64decode(content_string)
            df_raw = pd.read_csv(io.BytesIO(decoded), float_precision="high")
            self.content_hash = generate_df_hash_version(df_raw)
        except Exception:
            logger.exception("Failed to decode/parse uploaded CSV content")
            raise

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

        plotting_groups = _require(self.cols_key_meta, "plotting_groups", "cols_key_meta")
        loc_id = _require(self.cols_key_meta, "loc_id", "cols_key_meta")
        long_lat = _require(self.cols_key_meta, "long_lat", "cols_key_meta")

        # Coerce loc_id to string here, once, at the source - every downstream
        # consumer (loc_id_all, dict_marker_map, df_coordinate, the PCA/PaCMAP
        # output columns, and plotting.py's df.groupby(col_loc_id)) derives
        # from this column, so a single cast here keeps the dtype consistent
        # through the whole pipeline instead of drifting after a JSON round-
        # trip (JSON object keys are always strings, but JSON array/column
        # values preserve numeric dtype - without this, a numeric loc_id used
        # to desync dict_marker_map's string keys from the dataframe's numeric
        # values after a dcc.Store round-trip).
        self.df_master[loc_id] = self.df_master[loc_id].astype(str)

        self.df_master = self.df_master.sort_values(by=[*plotting_groups, loc_id]).reset_index(
            drop=True
        )

        self.df_coordinate = extract_coordinate_dataframe(
            self.df_master,
            plotting_groups,
            loc_id,
            long_lat[0],
            long_lat[1],
            col_marker_size=_require(self.cols_key_meta, "map_marker_size", "cols_key_meta"),
        )

        self.loc_id_all = self.df_master[loc_id].unique().tolist()

        # dict_marker_map is keyed by loc_id, which is now always string (see
        # the astype(str) cast above), so its keys stay consistent with
        # plotting.py's df.groupby(col_loc_id) after a JSON round-trip.
        # dict_generic_colors, in contrast, is keyed by plotting-group values,
        # which are NOT coerced to string - a numeric plotting-group column
        # could still hit the same JSON-round-trip key-type mismatch;
        # plotting.py's fallback-on-miss (default color + logged warning)
        # covers that remaining case, since coercing arbitrary group values
        # (not just the one loc_id column) is a larger, unrequested change.
        marker_symbol = _require(self.cols_key_meta, "marker_symbol", "cols_key_meta")
        if marker_symbol:
            self.dict_marker_map = df_col_group_to_dict(
                self.df_master,
                loc_id,
                marker_symbol,
            )
        else:
            # No marker-symbol role mapped - fill every location with a
            # constant default so plotting.py's direct dict indexing
            # (name_marker_map[loc_code]) never KeyErrors.
            self.dict_marker_map = {loc: DEFAULT_MARKER_SYMBOL for loc in self.loc_id_all}

        self.dict_generic_colors = make_plotting_group_color_dicts(
            self.df_master,
            plotting_groups,
            group_colors=mapping.group_colors,
        )

        self.cols_numeric_all = _require(self.cols_key_plot, "numeric_all", "cols_key_plot")

    def get_session_dict(self) -> Dict[str, Any]:
        """Package this preprocessor's state into the JSON-serializable dict
        shape every dcc.Store/Redis session blob uses."""
        date_col = _require(self.cols_key_meta, "date", "cols_key_meta")
        plotting_groups = _require(self.cols_key_meta, "plotting_groups", "cols_key_meta")
        numeric_all = _require(self.cols_key_plot, "numeric_all", "cols_key_plot")
        return {
            "df_master": pandas_to_json(self.df_master, date_col),
            "meta_data": {
                "cols_key_plot": self.cols_key_plot,
                "cols_key_meta": self.cols_key_meta,
                "dict_marker_map": self.dict_marker_map,
                "dict_generic_colors": self.dict_generic_colors,
                "loc_id_all": self.loc_id_all,
                "cols_numeric_all": self.cols_numeric_all,
                "df_coordinate": self.df_coordinate.to_json(),
                "custom_group_columns": [],  # user-created group columns, see add_custom_group
            },
            "data_hash": {
                "data_hash": self.content_hash,
            },
            "working_data": None,  # Placeholder for working data
            "custom_color_overrides": {},  # {group_col: {value: hex}}, see SessionManager.add_custom_group
            "plotting_data": {
                "feature_selection_dropdown_options": numeric_all,
                "feature_selection_dropdown_value": numeric_all,
                "loc_id_dropdown_options": self.loc_id_all,
                "loc_id_dropdown_value": self.loc_id_all,
                "date_filter_range_dropdown_value": None,  # upstream date Filter, see subset_df_dateRange
                "map_group_dropdown_options": plotting_groups,
                "map_group_dropdown_value": plotting_groups[0],
                "plot_group_dropdown_1_options": plotting_groups,
                "plot_group_dropdown_1_value": plotting_groups[0],
                "plot_group_dropdown_2_options": plotting_groups,
                "plot_group_dropdown_2_value": plotting_groups[0],
                "pmap_neighbors": 15,  # Default value for neighbors in pmap
            },
            "version": 1,
        }


class DataPlotter:
    """Deserializes a session's `working_data`/`meta_data` dcc.Store payloads
    and renders the PCA/PaCMAP biplot figures from them."""

    def __init__(
        self,
        working_data: str,
        meta_data: str,
        selected_loc_ids: Optional[dict],
        plot_groups: List[str],
        date_range: List[int],
    ) -> None:
        self.initialize_data(
            working_data,
            meta_data,
            selected_loc_ids,
            plot_groups,
            date_range,
        )

    def initialize_data(
        self,
        working_data: str,
        meta_data: str,
        selected_loc_ids: Optional[dict],
        plot_groups: List[str],
        date_range: List[int],
    ) -> None:
        """Parse the JSON store payloads and build df_plot_pca/df_plot_pmap.
        Logs and re-raises the original exception (preserving its type/
        traceback) on any failure, rather than masking it behind a generic
        ValueError."""
        try:
            self.working_data = json.loads(working_data)
            self.meta_data = json.loads(meta_data)
            self.cols_key_plot = _require(self.meta_data, "cols_key_plot", "meta_data")
            self.cols_key_meta = _require(self.meta_data, "cols_key_meta", "meta_data")
            self.dict_marker_map = _require(self.meta_data, "dict_marker_map", "meta_data")
            self.load_dataframes(selected_loc_ids)
            self.df_between_dates(date_range)
            self.ldg_df = pd.read_json(io.StringIO(self.working_data["ldg_df"]))
            self.expl_var = self.working_data["expl_var"]
            self.plot_groups = plot_groups
        except Exception:
            logger.exception("Error initializing DataPlotter")
            raise

    def load_dataframes(self, selected_loc_ids: Optional[dict]) -> None:
        """Build df_plot_pca/df_plot_pmap, optionally subset to the map's
        current selection (selected_loc_ids, a Plotly selectedData dict)."""
        date_col = _require(self.cols_key_meta, "date", "cols_key_meta")
        self.df_plot_pca = json_to_pandas(self.working_data, "df_plot_pca", date_col)
        self.df_plot_pmap = json_to_pandas(self.working_data, "df_plot_pmap", date_col)
        if selected_loc_ids is not None:
            self.selected_loc_ids = [point["customdata"][0] for point in selected_loc_ids["points"]]
            self.df_plot_pca = self._subset_df_locIds(self.df_plot_pca)
            self.df_plot_pmap = self._subset_df_locIds(self.df_plot_pmap)
        else:
            self.selected_loc_ids = _require(self.meta_data, "loc_id_all", "meta_data")

    def df_between_dates(self, date_range: List[int]) -> None:
        """Filter df_plot_pca/df_plot_pmap to rows within `date_range` (years),
        a no-op when no date column is mapped."""
        if not self.df_plot_pca.index.equals(self.df_plot_pmap.index):
            # Asserts are stripped under `python -O`; this invariant must hold
            # regardless of optimization flags, so raise explicitly instead.
            raise ValueError(
                "PCA and PaCMAP dataframe indices are out of sync "
                f"({len(self.df_plot_pca)} vs {len(self.df_plot_pmap)} rows) - "
                "cannot align them for date-range filtering."
            )
        col_date = _require(self.cols_key_meta, "date", "cols_key_meta")
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

    def _subset_df_locIds(self, df: pd.DataFrame) -> pd.DataFrame:
        return subset_df_locIds(
            df,
            _require(self.cols_key_meta, "loc_id", "cols_key_meta"),
            self.selected_loc_ids,
        ).reset_index(drop=True)

    @staticmethod
    def empty_figs() -> Tuple[Any, Any]:
        """Placeholder (pca_fig, pmap_fig) pair shown before any data is loaded."""
        return empty_fig(), empty_fig()

    def _color_maps_for_plot_groups(self) -> Tuple[Dict[Any, str], Dict[Any, str]]:
        """dict_generic_colors[plot_groups[0]]/[1] - a stale/mismatched plot
        group selection (e.g. dropdown options built before a re-upload) means
        the group column itself isn't a key here, not just a group value
        within it (plotting.py's own fallback-on-miss only covers the latter),
        so this is checked explicitly with a clear error rather than a bare
        KeyError two frames down inside plotting.py."""
        dict_generic_colors = _require(self.meta_data, "dict_generic_colors", "meta_data")
        colors = []
        for group_col in self.plot_groups:
            if group_col not in dict_generic_colors:
                logger.error(
                    "Plot group '%s' not found in dict_generic_colors (have: %s)",
                    group_col,
                    list(dict_generic_colors),
                )
                raise KeyError(
                    f"Plot group '{group_col}' not found in this session's color "
                    "mapping - the group dropdown selection may be stale."
                )
            colors.append(dict_generic_colors[group_col])
        return colors[0], colors[1]

    def _build_plot_context(self) -> PlotContext:
        """PlotContext for the current plot groups/selection - bundles the
        cluster of args make_fig_pca/make_fig_pmap need but never vary
        between the two calls."""
        color_primary, color_secondary = self._color_maps_for_plot_groups()
        return PlotContext(
            col_loc_id=_require(self.cols_key_meta, "loc_id", "cols_key_meta"),
            col_primary_domain=self.plot_groups[0],
            col_secondary_domain=self.plot_groups[1],
            col_date=_require(self.cols_key_meta, "date", "cols_key_meta"),
            dict_color_map_primary=color_primary,
            dict_color_map_secondary=color_secondary,
            name_marker_map=self.dict_marker_map,
            col_entity_id=self.cols_key_meta.get("entity_id"),
        )

    def plot_pmap(self, n_neighbors: int) -> Any:
        """Render the PaCMAP biplot figure for the current plot groups/selection."""
        return make_fig_pmap(
            self.df_plot_pmap,
            self._build_plot_context(),
            n_neighbors,
        )

    def pca_component_options(self) -> List[str]:
        """Sorted list of computed PC column names (e.g. ["PC1", "PC2", "PC3"])
        available to plot, driven by however many components
        `process_dimension_reduction` actually computed - used to populate the
        pca-x-component/pca-y-component dropdown options."""
        cols = [c for c in self.ldg_df.columns if c != "metals"]
        return sorted(cols, key=lambda c: int(c[2:]))

    def plot_pca(self, x_col: str = "PC1", y_col: str = "PC2") -> Any:
        """Render the PCA biplot figure for the current plot groups/selection.
        x_col/y_col select which computed components to plot."""
        return make_fig_pca(
            self.df_plot_pca,
            self.ldg_df,
            self.expl_var,
            self._build_plot_context(),
            x_col=x_col,
            y_col=y_col,
        )


class SessionManager:
    """Packaging helpers for building the `working_data` session payload."""

    # Column names/roles that always mean something else to plotting.py/the
    # mapping layer - a user-created group column can never collide with
    # these regardless of what's currently mapped.
    _RESERVED_GROUP_NAMES = {
        "ENTITY_ID",
        "LATITUDE",
        "LONGITUDE",
        "MAP-MARKER-SIZE",
        *(f"PC{i}" for i in range(1, MAX_PCA_COMPONENTS + 1)),
        "PMAP1",
        "PMAP2",
        ".",
    }

    @staticmethod
    def add_custom_group(
        session: Dict[str, Any], new_col_name: str, assignments: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """Create a new user-defined categorical plotting-group column,
        assigning rows per `assignments` (`{category_value: [entity_id, ...]}`),
        and thread it through every downstream structure that needs to know
        about it (dropdown options, color dict, map coordinate table).

        Parameters
        ----------
        session : dict
            The *loaded* (not JSON-string) session dict, as produced by
            `store_utils.load_store(session_json)`.
        new_col_name : str
            Name of the new group column. Must not collide with a reserved
            name, an existing plotting-group/meta column, or a numeric
            analyte column.
        assignments : dict
            `{category_value: [entity_id, ...]}` - see `assign_custom_group_column`.

        Returns
        -------
        dict
            The updated session dict (same object, mutated in place and
            returned for convenience).

        Raises
        ------
        ValueError
            On an empty/collision name, or if `assignments` references an
            unknown entity_id (propagated from `assign_custom_group_column`).
        """
        meta_data = _require(session, "meta_data", "session")
        cols_key_meta = _require(meta_data, "cols_key_meta", "meta_data")
        cols_key_plot = _require(meta_data, "cols_key_plot", "meta_data")

        if not new_col_name or not new_col_name.strip():
            raise ValueError("Custom group name cannot be empty.")
        loc_id_col = _require(cols_key_meta, "loc_id", "cols_key_meta")
        existing_names = (
            SessionManager._RESERVED_GROUP_NAMES
            | {loc_id_col}
            | set(cols_key_plot.get("meta", []))
            | set(cols_key_plot.get("numeric_all", []))
        )
        if new_col_name in existing_names:
            raise ValueError(f"'{new_col_name}' is already in use - choose a different name.")

        date_col = cols_key_meta.get("date")
        entity_id_col = _require(cols_key_meta, "entity_id", "cols_key_meta")

        df_master = json_to_pandas(session, "df_master", date_col)
        df_master = assign_custom_group_column(df_master, entity_id_col, new_col_name, assignments)

        plotting_groups = list(cols_key_meta["plotting_groups"]) + [new_col_name]
        cols_key_meta["plotting_groups"] = plotting_groups
        cols_key_plot["meta"] = list(cols_key_plot.get("meta", [])) + [new_col_name]
        meta_data["custom_group_columns"] = list(meta_data.get("custom_group_columns", [])) + [
            new_col_name
        ]

        dict_generic_colors = meta_data.get("dict_generic_colors", {})
        dict_generic_colors[new_col_name] = make_color_dict(df_master, new_col_name)
        meta_data["dict_generic_colors"] = dict_generic_colors

        long_lat = _require(cols_key_meta, "long_lat", "cols_key_meta")
        df_coordinate = extract_coordinate_dataframe(
            df_master,
            plotting_groups,
            loc_id_col,
            long_lat[0],
            long_lat[1],
            col_marker_size=cols_key_meta.get("map_marker_size"),
        )
        meta_data["df_coordinate"] = df_coordinate.to_json()

        plotting_data = _require(session, "plotting_data", "session")
        for key in (
            "map_group_dropdown_options",
            "plot_group_dropdown_1_options",
            "plot_group_dropdown_2_options",
        ):
            options = list(plotting_data.get(key, []))
            if new_col_name not in options:
                options.append(new_col_name)
            plotting_data[key] = options

        session["df_master"] = pandas_to_json(df_master, date_col)
        session["meta_data"] = meta_data
        session["plotting_data"] = plotting_data
        logger.info(
            "Created custom group column '%s' with %d categor%s.",
            new_col_name,
            len(assignments),
            "y" if len(assignments) == 1 else "ies",
        )
        return session

    @staticmethod
    def package_plotting_data(
        plot_components_pca: tuple, plot_components_pmap: pd.DataFrame, meta_data: dict
    ) -> Dict[str, Any]:
        """Bundle PCA/PaCMAP dimension-reduction outputs into the JSON-serializable
        `working_data` shape DataPlotter expects."""
        date_col = _require(
            _require(meta_data, "cols_key_meta", "meta_data"), "date", "cols_key_meta"
        )
        dict_working_data = {
            "df_plot_pca": pandas_to_json(plot_components_pca[0], date_col),
            "ldg_df": plot_components_pca[1].to_json(),
            "expl_var": plot_components_pca[2],
            "df_plot_pmap": pandas_to_json(plot_components_pmap, date_col),
        }
        return dict_working_data

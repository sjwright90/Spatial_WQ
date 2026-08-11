# Declarative data model for mapping arbitrary uploaded CSV columns to the
# semantic roles the app needs. Replaces the old regex/column-name-prefix
# convention (NUMERIC-ANALYTE_, CLR-ANALYTE_, LOCATION-ID_, DATETIME, LABELS_*,
# COLORS_*, MARKERS-PLOT-DOMAIN, MAP-MARKER-SIZE, literal LONGITUDE/LATITUDE).
#
# This module is pure schema/dataclasses - no pandas/dataframe logic lives here.
# See data_mapping.py for the validation + dataframe-building logic that
# consumes a ColumnMapping.
#
# Classes
# -------
# ColumnRole
# RoleSpec
# ColumnMapping
#
# Module-level
# ------------
# ROLE_REGISTRY

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ColumnRole(str, Enum):
    """Semantic roles a raw CSV column can be mapped to."""

    LOCATION_ID = "location_id"
    LATITUDE = "latitude"
    LONGITUDE = "longitude"
    NUMERIC_SIMPLE = "numeric_simple"
    NUMERIC_CLR = "numeric_clr"
    DATE = "date"
    PLOTTING_GROUP = "plotting_group"
    MARKER_SYMBOL = "marker_symbol"
    MAP_MARKER_SIZE = "map_marker_size"
    GROUP_COLOR = "group_color"


@dataclass(frozen=True)
class RoleSpec:
    """Declarative metadata describing one column role.

    Parameters
    ----------
    role : ColumnRole
        The role this spec describes.
    label : str
        Human-readable label for the mapping UI.
    required : bool
        Whether at least `min_count` column(s) must be mapped to this role
        for the dataset to be usable.
    multi : bool
        Whether more than one raw column can be mapped to this role
        (e.g. numeric analytes, plotting groups).
    dtype_hint : str
        One of "numeric", "string", "date", "float_lat", "float_lon",
        "hex_color" - used by the mapping/validation layer to decide how to
        coerce/validate values.
    min_count : int
        Minimum number of mapped columns required when `required` is True.
    """

    role: ColumnRole
    label: str
    required: bool
    multi: bool
    dtype_hint: str
    min_count: int = 0


# Single source of truth for what roles exist and how the mapping UI should
# present them. Iterate this list to build the mapping UI rather than
# hand-authoring one component per role.
ROLE_REGISTRY: List[RoleSpec] = [
    RoleSpec(
        role=ColumnRole.LOCATION_ID,
        label="Location ID",
        required=True,
        multi=False,
        dtype_hint="string",
        min_count=1,
    ),
    RoleSpec(
        role=ColumnRole.LATITUDE,
        label="Latitude",
        required=True,
        multi=False,
        dtype_hint="float_lat",
        min_count=1,
    ),
    RoleSpec(
        role=ColumnRole.LONGITUDE,
        label="Longitude",
        required=True,
        multi=False,
        dtype_hint="float_lon",
        min_count=1,
    ),
    RoleSpec(
        role=ColumnRole.NUMERIC_SIMPLE,
        label="Numeric analytes (simple)",
        required=False,
        multi=True,
        dtype_hint="numeric",
    ),
    RoleSpec(
        role=ColumnRole.NUMERIC_CLR,
        label="Numeric analytes (compositional / CLR)",
        required=False,
        multi=True,
        dtype_hint="numeric",
    ),
    RoleSpec(
        role=ColumnRole.DATE,
        label="Date",
        required=False,
        multi=False,
        dtype_hint="date",
    ),
    RoleSpec(
        role=ColumnRole.PLOTTING_GROUP,
        label="Plotting group(s)",
        required=True,
        multi=True,
        dtype_hint="string",
        min_count=1,
    ),
    RoleSpec(
        role=ColumnRole.MARKER_SYMBOL,
        label="Marker symbol",
        required=False,
        multi=False,
        dtype_hint="string",
    ),
    RoleSpec(
        role=ColumnRole.MAP_MARKER_SIZE,
        label="Map marker size",
        required=False,
        multi=False,
        dtype_hint="numeric",
    ),
    RoleSpec(
        role=ColumnRole.GROUP_COLOR,
        label="Plotting group color column(s)",
        required=False,
        multi=True,
        dtype_hint="hex_color",
    ),
]

# NOTE: at least one of NUMERIC_SIMPLE / NUMERIC_CLR must be mapped - this
# "at least one of a pair" constraint can't be expressed by a single
# RoleSpec.required flag and is enforced in data_mapping.py's validation.


@dataclass
class ColumnMapping:
    """User-supplied mapping from raw CSV column names to semantic roles.

    `group_colors` pairs a plotting-group column name to the color column
    that supplies its predefined hex colors (optional - unmapped groups fall
    back to an auto-generated palette).
    """

    location_id: str
    latitude: str
    longitude: str
    plotting_groups: List[str] = field(default_factory=list)
    numeric_simple: List[str] = field(default_factory=list)
    numeric_clr: List[str] = field(default_factory=list)
    date: Optional[str] = None
    marker_symbol: Optional[str] = None
    map_marker_size: Optional[str] = None
    group_colors: Dict[str, str] = field(default_factory=dict)

    def all_mapped_columns(self) -> List[str]:
        """Every raw column name referenced anywhere in this mapping."""
        cols = [self.location_id, self.latitude, self.longitude]
        cols += self.plotting_groups
        cols += self.numeric_simple
        cols += self.numeric_clr
        if self.date:
            cols.append(self.date)
        if self.marker_symbol:
            cols.append(self.marker_symbol)
        if self.map_marker_size:
            cols.append(self.map_marker_size)
        cols += list(self.group_colors.values())
        return cols

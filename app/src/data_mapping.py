# Mapping + validation logic: turns a raw uploaded dataframe plus a
# user-supplied ColumnMapping (see data_model.py) into the internal canonical
# structures the rest of the app consumes (cols_key_plot / cols_key_meta,
# matching the shape DataPreprocessor.get_session_dict() has always emitted),
# collecting structured warnings/errors along the way instead of silently
# corrupting data or failing with a single opaque boolean.
#
# Classes
# -------
# ValidationIssue
# ValidationResult
# MappedDataset
#
# Functions
# ---------
# build_mapped_dataset

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .data_model import ColumnMapping

_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MAX_SAMPLE_VALUES = 10


@dataclass
class ValidationIssue:
    """One validation finding.

    Parameters
    ----------
    field : str
        Role name (e.g. "latitude", "numeric_clr") or "general".
    severity : str
        "error" (blocks upload) or "warning" (upload proceeds, feature may degrade).
    message : str
        Human-readable description.
    offending_values : list, optional
        A capped sample of the values that triggered this issue.
    """

    field: str
    severity: str
    message: str
    offending_values: Optional[list] = None


@dataclass
class ValidationResult:
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]


@dataclass
class MappedDataset:
    """Result of `build_mapped_dataset`.

    `df_master`/`cols_key_plot`/`cols_key_meta` are None when `validation.has_errors`
    is True - the mapping could not be safely applied.
    """

    df_master: Optional[pd.DataFrame]
    cols_key_plot: Optional[Dict]
    cols_key_meta: Optional[Dict]
    validation: ValidationResult


def _add_issue(issues, field_name, severity, message, offending_values=None):
    if offending_values is not None:
        offending_values = [str(v) for v in list(offending_values)[:_MAX_SAMPLE_VALUES]]
    issues.append(ValidationIssue(field_name, severity, message, offending_values))


def _flatten_role_columns(mapping: ColumnMapping):
    """Yield (role_name, raw_column_name) for every mapped slot."""
    yield "location_id", mapping.location_id
    yield "latitude", mapping.latitude
    yield "longitude", mapping.longitude
    for col in mapping.plotting_groups:
        yield "plotting_group", col
    for col in mapping.numeric_simple:
        yield "numeric_simple", col
    for col in mapping.numeric_clr:
        yield "numeric_clr", col
    if mapping.date:
        yield "date", mapping.date
    if mapping.marker_symbol:
        yield "marker_symbol", mapping.marker_symbol
    if mapping.map_marker_size:
        yield "map_marker_size", mapping.map_marker_size
    for group_col, color_col in mapping.group_colors.items():
        yield "group_color", color_col


def _check_duplicate_columns(mapping: ColumnMapping, issues):
    seen: Dict[str, List[str]] = {}
    for role_name, col in _flatten_role_columns(mapping):
        if col is None:
            continue
        seen.setdefault(col, []).append(role_name)
    for col, roles in seen.items():
        if len(roles) > 1:
            _add_issue(
                issues,
                "general",
                "error",
                f"Column '{col}' is mapped to more than one role: {', '.join(roles)}.",
            )


def _check_required_roles(mapping: ColumnMapping, issues):
    if not mapping.location_id:
        _add_issue(issues, "location_id", "error", "A location ID column must be mapped.")
    if not mapping.latitude:
        _add_issue(issues, "latitude", "error", "A latitude column must be mapped.")
    if not mapping.longitude:
        _add_issue(issues, "longitude", "error", "A longitude column must be mapped.")
    if not (mapping.numeric_simple or mapping.numeric_clr):
        _add_issue(
            issues,
            "numeric_simple",
            "error",
            "At least one numeric analyte column must be mapped (simple or compositional/CLR).",
        )
    if not mapping.plotting_groups:
        _add_issue(
            issues,
            "plotting_group",
            "error",
            "At least one plotting-group column must be mapped.",
        )


def _check_group_color_references(mapping: ColumnMapping, issues):
    for group_col in mapping.group_colors:
        if group_col not in mapping.plotting_groups:
            _add_issue(
                issues,
                "group_color",
                "warning",
                f"A color column was mapped for '{group_col}', which is not one of the "
                "mapped plotting-group columns; ignoring.",
            )


def _check_columns_exist(df_raw: pd.DataFrame, mapping: ColumnMapping, issues) -> bool:
    missing = sorted(
        {
            col
            for _, col in _flatten_role_columns(mapping)
            if col is not None and col not in df_raw.columns
        }
    )
    for col in missing:
        _add_issue(
            issues, "general", "error", f"Mapped column '{col}' was not found in the uploaded file."
        )
    return len(missing) == 0


def _coerce_lat_lon(df: pd.DataFrame, col: str, bound: float, field_name: str, issues) -> pd.Series:
    coerced = pd.to_numeric(df[col], errors="coerce")
    bad_mask = coerced.isna() | coerced.abs().gt(bound)
    if bad_mask.any():
        _add_issue(
            issues,
            field_name,
            "error",
            f"Column '{col}': {int(bad_mask.sum())} row(s) have missing or out-of-range "
            f"{field_name} values (must be within +/-{bound}).",
            offending_values=df.loc[bad_mask, col],
        )
    return coerced


def _coerce_numeric_column(df: pd.DataFrame, col: str, field_name: str, issues) -> pd.Series:
    original_na = df[col].isna()
    coerced = pd.to_numeric(df[col], errors="coerce")
    newly_bad = coerced.isna() & ~original_na
    if newly_bad.any():
        _add_issue(
            issues,
            field_name,
            "warning",
            f"Column '{col}': {int(newly_bad.sum())} value(s) could not be parsed as "
            "numeric and were treated as missing.",
            offending_values=df.loc[newly_bad, col],
        )
    if coerced.isna().any():
        _add_issue(
            issues,
            field_name,
            "warning",
            f"Column '{col}' has {int(coerced.isna().sum())} missing numeric value(s).",
        )
    return coerced


def _check_clr_positive(coerced: pd.Series, col: str, issues):
    bad_mask = coerced.isna() | coerced.le(0)
    if bad_mask.any():
        _add_issue(
            issues,
            "numeric_clr",
            "error",
            f"Column '{col}' (compositional/CLR) has {int(bad_mask.sum())} value(s) that "
            "are missing or <= 0; CLR requires strictly positive values.",
            offending_values=coerced[bad_mask],
        )


def _coerce_date(df: pd.DataFrame, col: str, issues):
    """Coerce a date column per-row instead of the old whole-column
    substitute-with-now() fallback. Returns (coerced_series_or_None, unusable)."""
    original_present = df[col].notna()
    coerced = pd.to_datetime(df[col], errors="coerce")
    bad_mask = coerced.isna() & original_present
    if len(df) > 0 and bad_mask.sum() == original_present.sum() and original_present.any():
        _add_issue(
            issues,
            "date",
            "warning",
            f"Column '{col}' could not be parsed as dates for any row; date-range "
            "filtering will be disabled.",
            offending_values=df.loc[bad_mask, col],
        )
        return None, True
    if bad_mask.any():
        _add_issue(
            issues,
            "date",
            "warning",
            f"Column '{col}': {int(bad_mask.sum())} value(s) could not be parsed as dates "
            "and were treated as missing.",
            offending_values=df.loc[bad_mask, col],
        )
    return coerced, False


def _check_hex_colors(df: pd.DataFrame, col: str, issues):
    str_vals = df[col].astype(str)
    invalid_mask = ~str_vals.map(lambda v: bool(_HEX_COLOR_PATTERN.fullmatch(v)))
    if invalid_mask.any():
        invalid_uniques = df.loc[invalid_mask, col].unique()
        _add_issue(
            issues,
            "group_color",
            "warning",
            f"Color column '{col}' has {len(invalid_uniques)} invalid hex value(s) (must "
            "match '#RRGGBB'); affected groups will fall back to an auto-generated palette.",
            offending_values=invalid_uniques,
        )


def build_mapped_dataset(df_raw: pd.DataFrame, mapping: ColumnMapping) -> MappedDataset:
    """Validate `mapping` against `df_raw` and, if there are no blocking errors,
    build the canonical (df_master, cols_key_plot, cols_key_meta) structures the
    rest of the app expects - the same shape `DataPreprocessor` has always produced.

    Always returns a `MappedDataset`; check `.validation.has_errors` before using
    `.df_master`/`.cols_key_plot`/`.cols_key_meta`, which are None when blocked.
    """
    issues: List[ValidationIssue] = []

    _check_duplicate_columns(mapping, issues)
    _check_required_roles(mapping, issues)
    _check_group_color_references(mapping, issues)
    columns_ok = _check_columns_exist(df_raw, mapping, issues)

    core_ok = columns_ok and mapping.location_id and mapping.latitude and mapping.longitude
    if not core_ok:
        # Can't safely proceed without the columns row identity/plotting depend on.
        return MappedDataset(None, None, None, ValidationResult(issues))

    df = df_raw.copy()

    df[mapping.latitude] = _coerce_lat_lon(df, mapping.latitude, 90, "latitude", issues)
    df[mapping.longitude] = _coerce_lat_lon(df, mapping.longitude, 180, "longitude", issues)

    for col in mapping.numeric_simple:
        df[col] = _coerce_numeric_column(df, col, "numeric_simple", issues)

    for col in mapping.numeric_clr:
        coerced = _coerce_numeric_column(df, col, "numeric_clr", issues)
        _check_clr_positive(coerced, col, issues)
        df[col] = coerced

    if mapping.map_marker_size:
        df[mapping.map_marker_size] = _coerce_numeric_column(
            df, mapping.map_marker_size, "map_marker_size", issues
        )

    date_col = mapping.date
    if date_col:
        coerced_date, unusable = _coerce_date(df, date_col, issues)
        if unusable:
            date_col = None
        else:
            df[date_col] = coerced_date

    for color_col in mapping.group_colors.values():
        if color_col in df.columns:
            _check_hex_colors(df, color_col, issues)

    validation = ValidationResult(issues)
    if validation.has_errors:
        return MappedDataset(None, None, None, validation)

    # Canonical renames required downstream: plotting.make_map hardcodes
    # df["LATITUDE"]/df["LONGITUDE"] with no override kwarg.
    df = df.rename(columns={mapping.longitude: "LONGITUDE", mapping.latitude: "LATITUDE"})

    numeric_all = list(mapping.numeric_simple) + list(mapping.numeric_clr)
    meta_cols = list(mapping.plotting_groups) + [mapping.location_id, "LONGITUDE", "LATITUDE"]
    if date_col:
        meta_cols.append(date_col)
    if mapping.marker_symbol:
        meta_cols.append(mapping.marker_symbol)
    if mapping.map_marker_size:
        meta_cols.append(mapping.map_marker_size)
    meta_cols = list(dict.fromkeys(meta_cols))  # de-dupe, preserve order

    df_master = df[meta_cols + numeric_all].copy()

    cols_key_plot = {
        "meta": meta_cols,
        "numeric_all": numeric_all,
        "numeric_simple": list(mapping.numeric_simple),
        "numeric_clr": list(mapping.numeric_clr),
    }
    cols_key_meta = {
        "loc_id": mapping.location_id,
        "date": date_col,
        "plotting_groups": list(mapping.plotting_groups),
        "long_lat": ["LONGITUDE", "LATITUDE"],
        "marker_symbol": mapping.marker_symbol,
        "map_marker_size": mapping.map_marker_size,
    }

    return MappedDataset(df_master, cols_key_plot, cols_key_meta, validation)

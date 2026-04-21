import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


STANDARD_COLUMNS = [
    "obs_date",
    "timestamp",
    "arm",
    "recipe",
    "metric",
    "value",
    "unit",
    "source_file",
]


def _empty_qc_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=STANDARD_COLUMNS)


def infer_arm_from_sof_name(sof_name: str) -> str | None:
    """
    Infer instrument arm from sof_name.
    """
    name = sof_name.upper()

    if "_NIR_" in name:
        return "NIR"

    if "_VIS_" in name:
        return "VIS"

    return None


def parse_qc_value(raw_value: object) -> float | None:
    """
    Convert qc_value to float.

    Current assumption:
    - values are numeric strings (or already numeric)
    - invalid / non-finite values are discarded
    """
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(value):
        return None

    return value


def load_qc_from_session_db(
    session_db_path: Path,
    obs_date: str,
    cfg: dict,
) -> pd.DataFrame:
    """
    Load QC metrics from one soxspipe session database.

    Parameters
    ----------
    session_db_path : Path
        Full path to the session database file.
    obs_date : str
        Observing date (YYYY-MM-DD), taken from the session directory name.
    cfg : dict
        Full configuration dictionary.

    Returns
    -------
    pd.DataFrame
        Standardized QC dataframe with columns:
        obs_date, timestamp, arm, recipe, metric, value, unit, source_file
    """
    acquisition_cfg = cfg.get("acquisition", {})
    allowed_recipes: list[str] = list(acquisition_cfg.get("recipes", []))
    allowed_metrics: list[str] = list(acquisition_cfg.get("metrics", []))

    if not session_db_path.is_file():
        log.warning(
            "Session database not found for %s: %s",
            obs_date,
            session_db_path,
        )
        return _empty_qc_dataframe()

    if not allowed_recipes:
        log.warning("No acquisition recipes configured")
        return _empty_qc_dataframe()

    placeholders_recipes = ",".join("?" for _ in allowed_recipes)

    query = f"""
    SELECT
        soxspipe_recipe,
        qc_name,
        qc_value,
        qc_unit,
        obs_date_utc,
        reduction_date_utc,
        sof_name
    FROM quality_control
    WHERE soxspipe_recipe IN ({placeholders_recipes})
    """

    params: list[object] = list(allowed_recipes)

    try:
        with sqlite3.connect(session_db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)
    except Exception as exc:
        log.error(
            "Failed to read quality_control from %s: %s",
            session_db_path,
            exc,
        )
        return _empty_qc_dataframe()

    if df.empty:
        log.info("No QC rows found in session database for %s", obs_date)
        return _empty_qc_dataframe()

    # Filter metrics only if explicitly configured
    if allowed_metrics:
        df = df[df["qc_name"].isin(allowed_metrics)].copy()

    if df.empty:
        log.info(
            "No configured QC metrics found in session database for %s",
            obs_date,
        )
        return _empty_qc_dataframe()

    # Standardize fields
    df["arm"] = df["sof_name"].apply(infer_arm_from_sof_name)
    df["value"] = df["qc_value"].apply(parse_qc_value)

    # Prefer obs_date_utc as timestamp; fallback to reduction_date_utc
    df["timestamp"] = df["obs_date_utc"].fillna(df["reduction_date_utc"])

    # Use observing date from session folder, not from the DB contents
    df["obs_date"] = obs_date

    df["recipe"] = df["soxspipe_recipe"]
    df["metric"] = df["qc_name"]
    df["unit"] = df["qc_unit"].fillna("")
    df["source_file"] = df["sof_name"]

    invalid_arm = int(df["arm"].isna().sum())
    invalid_value = int(df["value"].isna().sum())
    invalid_timestamp = int(df["timestamp"].isna().sum())

    if invalid_arm:
        log.warning(
            "Dropping %d rows with unknown arm in %s",
            invalid_arm,
            session_db_path.name,
        )

    if invalid_value:
        log.warning(
            "Dropping %d rows with non-numeric qc_value in %s",
            invalid_value,
            session_db_path.name,
        )

    if invalid_timestamp:
        log.warning(
            "Dropping %d rows with missing timestamp in %s",
            invalid_timestamp,
            session_db_path.name,
        )

    df = df.dropna(subset=["arm", "value", "timestamp"]).copy()

    if df.empty:
        log.info("No valid QC datapoints left after cleaning for %s", obs_date)
        return _empty_qc_dataframe()

    df = df[STANDARD_COLUMNS].reset_index(drop=True)

    log.info(
        "Loaded %d QC datapoints from session database for %s",
        len(df),
        obs_date,
    )

    return df
import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from qc_monitor.schema import TABLE_SCHEMA

log = logging.getLogger(__name__)

TABLE_COLUMNS = list(TABLE_SCHEMA.keys())


def find_session_databases(qc_root: Path, database_name: str) -> list[Path]:
    """
    Find all upstream SOXS pipeline session databases under qc_root.
    """
    return sorted(qc_root.rglob(database_name))


def _empty_qc_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=TABLE_COLUMNS)


def parse_qc_value(raw_value: object) -> float | None:
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(value):
        return None

    return value


def parse_optional_float(raw_value: object) -> float | None:
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(value):
        return None

    return value


def normalize_arm(raw_arm: object) -> str | None:
    if raw_arm is None:
        return None

    arm = str(raw_arm).upper().strip()

    if arm in {"VIS", "NIR"}:
        return arm

    return None


def _table_or_view_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (name,),
    )
    return cur.fetchone() is not None


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """
    Return column names for a SQLite table or view.
    """
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {row[1] for row in rows}


def _build_select_query(upstream_table: str) -> str:
    columns_sql = ",\n                ".join(
        f'`{col}`'
        for col in TABLE_COLUMNS
    )

    return f"""
            SELECT
                {columns_sql}
            FROM `{upstream_table}`
            """


def load_qc_from_session_db(
    session_db_path: Path,
    cfg: dict,
) -> pd.DataFrame:
    """
    Load all QC metrics from one upstream SOXS pipeline session database.

    The upstream database is expected to contain the configured upstream QC view.
    The returned DataFrame uses the original upstream column names.
    """
    if not session_db_path.is_file():
        log.warning("Session database not found: %s", session_db_path)
        return _empty_qc_dataframe()

    try:
        upstream_table = cfg["acquisition"]["upstream_table"]

        with sqlite3.connect(session_db_path) as conn:
            if not _table_or_view_exists(conn, upstream_table):
                log.error(
                    "Required upstream view/table %s not found in %s",
                    upstream_table,
                    session_db_path,
                )
                return _empty_qc_dataframe()

            available_columns = _get_table_columns(conn, upstream_table)
            required_columns = set(TABLE_COLUMNS)
            missing_columns = required_columns - available_columns

            if missing_columns:
                log.error(
                    "Missing required columns in %s (%s): %s",
                    upstream_table,
                    session_db_path,
                    ", ".join(sorted(missing_columns)),
                )
                return _empty_qc_dataframe()

            query = _build_select_query(upstream_table)
            df = pd.read_sql_query(query, conn)

    except KeyError as exc:
        log.error("Missing configuration key: %s", exc)
        return _empty_qc_dataframe()

    except Exception as exc:
        log.error("Failed to read QC data from %s: %s", session_db_path, exc)
        return _empty_qc_dataframe()

    if df.empty:
        log.info("No QC rows found in session database %s", session_db_path)
        return _empty_qc_dataframe()

    # Normalize / validate values, keeping upstream column names
    df["eso seq arm"] = df["eso seq arm"].apply(normalize_arm)
    df["qc_value"] = df["qc_value"].apply(parse_qc_value)
    df["qc_value_min"] = df["qc_value_min"].apply(parse_optional_float)
    df["qc_value_max"] = df["qc_value_max"].apply(parse_optional_float)
    df["qc_unit"] = df["qc_unit"].fillna("")
    df["qc_order"] = (
        df["qc_order"]
        .fillna("-1")
        .astype(str)
        .str.strip()
    )

    invalid_obs_day = int(df["night start date"].isna().sum())
    invalid_obs_date_utc = int(df["obs_date_utc"].isna().sum())
    invalid_arm = int(df["eso seq arm"].isna().sum())
    invalid_value = int(df["qc_value"].isna().sum())

    if invalid_obs_day:
        log.warning(
            "Dropping %d rows with missing night start date in %s",
            invalid_obs_day,
            session_db_path.name,
        )

    if invalid_obs_date_utc:
        log.warning(
            "Dropping %d rows with missing obs_date_utc in %s",
            invalid_obs_date_utc,
            session_db_path.name,
        )

    if invalid_arm:
        log.warning(
            "Dropping %d rows with invalid arm in %s",
            invalid_arm,
            session_db_path.name,
        )

    if invalid_value:
        log.warning(
            "Dropping %d rows with non-numeric qc_value in %s",
            invalid_value,
            session_db_path.name,
        )

    df = df.dropna(
        subset=[
            "night start date",
            "obs_date_utc",
            "eso seq arm",
            "qc_value",
        ]
    ).copy()

    if df.empty:
        log.info(
            "No valid QC datapoints left after cleaning in %s",
            session_db_path,
        )
        return _empty_qc_dataframe()

    df = df[TABLE_COLUMNS].reset_index(drop=True)

    log.info(
        "Loaded %d QC datapoints from session database %s",
        len(df),
        session_db_path,
    )

    return df
import re
import logging
import sqlite3

import numpy as np
import pandas as pd

from pathlib import Path
from astropy.io import fits
from astropy.table import Table

from qc_monitor.schema import TABLE_SCHEMA

log = logging.getLogger(__name__)

TABLE_COLUMNS = list(TABLE_SCHEMA.keys())

DISPERSION_SOLUTION_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "soxspipe_recipe",
    "source_file",
    "filepath",
    "wavelength",
    "order",
    "slit_index",
    "slit_position",
    "detector_x",
    "detector_y",
    "observed_x",
    "observed_y",
    "x_diff",
    "y_diff",
    "fit_x",
    "fit_y",
    "residuals_x",
    "residuals_y",
    "residuals_xy",
    "sigma_clipped",
    "sharpness",
    "roundness1",
    "roundness2",
    "npix",
    "sky",
    "peak",
    "flux",
    "fwhm_pin_px",
    "R_pin",
    "pixelScaleNm",
    "detector_x_shifted",
    "detector_y_shifted",
    "R_slit",
    "fwhm_slit_px",
]

DISPERSION_RESOLUTION_STATS_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "soxspipe_recipe",
    "source_file",
    "filepath",
    "order",
    "mean_R_pin",
    "std_R_pin",
    "n_points",
]

ORDER_LOCATION_META_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "soxspipe_recipe",
    "source_file",
    "filepath",
    "slit",
    "slitmask",
    "lamp",
    "binning",
    "rospeed",
    "order",
    "xmin",
    "xmax",
    "ymin",
    "ymax",
    "maxThreshold",
    "minThreshold",
    "maxvalue",
]

ORDER_LOCATION_COEFF_COLUMNS = [
    "degorder_cent",
    "degy_cent",
    "degx_cent",
    *[f"cent_{i}{j}" for i in range(7) for j in range(6)],

    "degorder_std",
    "degy_std",
    "degx_std",
    *[f"std_{i}{j}" for i in range(7) for j in range(6)],

    "degorder_edgelow",
    "degorder_edgeup",
    "degy_edgelow",
    "degy_edgeup",
    "degx_edgelow",
    "degx_edgeup",
    *[f"edgelow_c{i}{j}" for i in range(7) for j in range(6)],
    *[f"edgeup_c{i}{j}" for i in range(7) for j in range(6)],
]

ORDER_LOCATION_MODEL_COLUMNS = (
    ORDER_LOCATION_META_COLUMNS
    + ORDER_LOCATION_COEFF_COLUMNS
)

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


def find_dispersion_solution_fits_files(qc_root: Path) -> list[Path]:
    """
    Find SOXS dispersion-solution fitted-lines FITS files.

    Only DSOL PINHOLE products are selected.
    SSOL / spatial-solution products are intentionally ignored.
    """
    candidates = qc_root.rglob("*DSOL_PINHOLE*SOXS_FITTED_LINES.fits")

    files = []
    for path in candidates:
        name = path.name.upper()

        if "_VIS_" not in name and "_NIR_" not in name:
            continue

        if "_DSOL_PINHOLE_" not in name:
            continue

        files.append(path)

    return sorted(files)


def parse_dispersion_solution_filename(path: Path) -> tuple[str, str, str]:
    """
    Extract obs_day, obs_date_utc and arm from a DSOL fitted-lines filename.

    Example:
    20251129T093102_VIS_1X1_1_DSOL_PINHOLE_30_0S_SOXS_FITTED_LINES.fits

    Returns
    -------
    obs_day : str
        YYYY-MM-DD
    obs_date_utc : str
        YYYY-MM-DDThh:mm:ss
    arm : str
        VIS or NIR
    """
    name = path.name

    match = re.match(
        r"(?P<stamp>\d{8}T\d{6})_(?P<arm>VIS|NIR)_.*_DSOL_PINHOLE_.*SOXS_FITTED_LINES\.fits$",
        name,
        re.IGNORECASE,
    )

    if match is None:
        raise ValueError(f"Invalid dispersion-solution FITS filename: {name}")

    stamp = match.group("stamp")
    arm = match.group("arm").upper()

    obs_day = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
    obs_date_utc = (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        f"T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"
    )

    return obs_day, obs_date_utc, arm


def load_dispersion_solution_fits_table(fits_path: Path) -> pd.DataFrame:
    """
    Load one DSOL fitted-lines FITS table and add QC-monitor metadata.
    """
    obs_day, obs_date_utc, arm = parse_dispersion_solution_filename(fits_path)

    with fits.open(fits_path) as hdul:
        if len(hdul) < 2:
            raise ValueError(f"No table HDU found in {fits_path}")

        table = Table(hdul[1].data)

    df = table.to_pandas()

    df["obs_day"] = obs_day
    df["obs_date_utc"] = obs_date_utc
    df["eso seq arm"] = arm
    df["soxspipe_recipe"] = "soxs-disp-solution"
    df["source_file"] = fits_path.name
    df["filepath"] = str(fits_path)

    for col in DISPERSION_SOLUTION_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[DISPERSION_SOLUTION_COLUMNS].reset_index(drop=True)


def load_dispersion_solution_tables(
    fits_files: list[Path],
) -> pd.DataFrame:
    """
    Load multiple DSOL fitted-lines FITS tables into one dataframe.
    """
    frames = []

    for fits_path in fits_files:
        try:
            df = load_dispersion_solution_fits_table(fits_path)
        except Exception as exc:
            log.error(
                "Failed to load dispersion-solution FITS table %s: %s",
                fits_path,
                exc,
            )
            continue

        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=DISPERSION_SOLUTION_COLUMNS)

    out = pd.concat(frames, ignore_index=True)

    log.info(
        "Loaded %d dispersion-solution rows from %d FITS files",
        len(out),
        len(frames),
    )

    return out


def compute_dispersion_resolution_stats(
    df_lines: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute mean and standard deviation of R_pin per order.

    Input dataframe is the line-by-line dispersion solution table.
    Output dataframe has one row per obs_date_utc / arm / order / source_file.
    """
    if df_lines.empty:
        return pd.DataFrame(columns=DISPERSION_RESOLUTION_STATS_COLUMNS)

    required_columns = {
        "obs_day",
        "obs_date_utc",
        "eso seq arm",
        "soxspipe_recipe",
        "source_file",
        "filepath",
        "order",
        "R_pin",
    }

    missing = required_columns - set(df_lines.columns)
    if missing:
        raise ValueError(
            "Missing required columns for dispersion resolution stats: "
            f"{sorted(missing)}"
        )

    df = df_lines.copy()
    df["R_pin"] = pd.to_numeric(df["R_pin"], errors="coerce")
    df = df.dropna(subset=["R_pin", "order"])

    if df.empty:
        return pd.DataFrame(columns=DISPERSION_RESOLUTION_STATS_COLUMNS)

    grouped = (
        df
        .groupby(
            [
                "obs_day",
                "obs_date_utc",
                "eso seq arm",
                "soxspipe_recipe",
                "source_file",
                "filepath",
                "order",
            ],
            dropna=False,
        )["R_pin"]
        .agg(
            mean_R_pin="mean",
            std_R_pin="std",
            n_points="count",
        )
        .reset_index()
    )

    return grouped[DISPERSION_RESOLUTION_STATS_COLUMNS]


def load_order_location_meta_fits_table(fits_path: Path) -> pd.DataFrame:
    """
    Load HDU 2 of one OLOC FITS file.

    HDU 2 contains one row per order, with the order number and detector
    coordinate ranges used by the pipeline to evaluate the OLOC polynomials.
    """
    metadata = parse_order_location_filename(fits_path)

    with fits.open(fits_path) as hdul:
        if len(hdul) < 3:
            raise ValueError(f"No order-location meta HDU found in {fits_path}")

        table = Table(hdul[2].data)

    df = table.to_pandas()

    for key, value in metadata.items():
        df[key] = value

    missing_cols = [
        col for col in ORDER_LOCATION_META_COLUMNS
        if col not in df.columns
    ]

    if missing_cols:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    {col: None for col in missing_cols},
                    index=df.index,
                ),
            ],
            axis=1,
        )

    return df[ORDER_LOCATION_META_COLUMNS].copy().reset_index(drop=True)


def load_order_location_meta(
    fits_files: list[Path],
) -> pd.DataFrame:
    """
    Load HDU 2 metadata tables from multiple OLOC FITS files.
    """
    frames = []

    for fits_path in fits_files:
        try:
            df = load_order_location_meta_fits_table(fits_path)
        except Exception as exc:
            log.error(
                "Failed to load order-location meta table %s: %s",
                fits_path,
                exc,
            )
            continue

        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=ORDER_LOCATION_META_COLUMNS)

    out = pd.concat(frames, ignore_index=True, sort=False)

    log.info(
        "Loaded %d order-location meta rows from %d FITS files",
        len(out),
        len(frames),
    )

    return out


def _infer_order_location_recipe(path: Path) -> str:
    """
    Infer the upstream recipe from the directory path.
    """
    parts = {p.lower() for p in path.parts}

    if "soxs-mflat" in parts:
        return "soxs-mflat"

    if "soxs-order-centres" in parts:
        return "soxs-order-centres"

    return "unknown"

def find_order_location_fits_files(qc_root: Path) -> list[Path]:
    """
    Find SOXS order-location FITS products.

    Selects OLOC products and ignores unrelated FITS files.
    """
    candidates = qc_root.rglob("*_OLOC_*_SOXS.fits")

    files = []
    for path in candidates:
        name = path.name.upper()

        if "_OLOC_" not in name:
            continue

        if "_VIS_" not in name and "_NIR_" not in name:
            continue

        files.append(path)

    return sorted(files)

def parse_order_location_filename(path: Path) -> dict[str, str | None]:
    """
    Parse metadata from an OLOC filename.

    Examples:
    20251129T083501_VIS_1X1_1_OLOC_QTH_SLIT0_5_20_0S_SOXS.fits
    20251129T083459_NIR_3_OLOC_QTH_SLIT0_5_7_5S_SOXS.fits
    20251129T092633_VIS_1X1_1_OLOC_QTH_PINHOLE_10_0S_SOXS.fits
    """
    name = path.name

    match = re.match(
        r"(?P<stamp>\d{8}T\d{6})_"
        r"(?P<arm>VIS|NIR)_"
        r"(?P<setup>.*?)_"
        r"OLOC_"
        r"(?P<lamp>[^_]+)_"
        r"(?P<mask_part>SLIT\d+_\d+|PINHOLE)_"
        r"(?P<exptime>[\d_]+S)_"
        r"SOXS\.fits$",
        name,
        re.IGNORECASE,
    )

    if match is None:
        raise ValueError(f"Invalid order-location FITS filename: {name}")

    stamp = match.group("stamp")
    arm = match.group("arm").upper()
    setup = match.group("setup")
    lamp = match.group("lamp").upper()
    mask_part = match.group("mask_part").upper()

    obs_day = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
    obs_date_utc = (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        f"T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"
    )

    if arm == "VIS":
        setup_parts = setup.split("_")
        binning = setup_parts[0].lower() if len(setup_parts) >= 1 else None
        rospeed = setup_parts[-1] if len(setup_parts) >= 2 else None
    else:
        binning = None
        rospeed = setup

    if mask_part.startswith("SLIT"):
        slitmask = "SLIT"
        slit_value = mask_part.replace("SLIT", "", 1).replace("_", ".")
        slit = f"SLIT{slit_value}"
    elif mask_part == "PINHOLE":
        slitmask = "PINHOLE"
        slit = "PINHOLE"
    else:
        slitmask = mask_part
        slit = mask_part

    return {
        "obs_day": obs_day,
        "obs_date_utc": obs_date_utc,
        "eso seq arm": arm,
        "soxspipe_recipe": _infer_order_location_recipe(path),
        "source_file": path.name,
        "filepath": str(path),
        "slit": slit,
        "slitmask": slitmask,
        "lamp": lamp,
        "binning": binning,
        "rospeed": rospeed,
    }

def load_order_location_model_fits_table(fits_path: Path) -> pd.DataFrame:
    """
    Load one OLOC FITS polynomial-coefficient table.

    The FITS table contains order-centre, order-edge and related polynomial
    coefficients. Metadata parsed from filename/path are added as columns.
    """
    metadata = parse_order_location_filename(fits_path)

    with fits.open(fits_path) as hdul:
        if len(hdul) < 2:
            raise ValueError(f"No table HDU found in {fits_path}")

        table = Table(hdul[1].data)

    df = table.to_pandas()

    for key, value in metadata.items():
        df[key] = value

    missing_cols = [
        col for col in ORDER_LOCATION_MODEL_COLUMNS
        if col not in df.columns
    ]

    if missing_cols:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    {col: None for col in missing_cols},
                    index=df.index,
                ),
            ],
            axis=1,
        )

    return df[ORDER_LOCATION_MODEL_COLUMNS].copy().reset_index(drop=True)

def load_order_location_models(
    fits_files: list[Path],
) -> pd.DataFrame:
    """
    Load multiple OLOC FITS coefficient tables into one dataframe.
    """
    frames = []

    for fits_path in fits_files:
        try:
            df = load_order_location_model_fits_table(fits_path)
        except Exception as exc:
            log.error(
                "Failed to load order-location FITS table %s: %s",
                fits_path,
                exc,
            )
            continue

        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=ORDER_LOCATION_MODEL_COLUMNS)

    out = pd.concat(frames, ignore_index=True, sort=False)

    log.info(
        "Loaded %d order-location model rows from %d FITS files",
        len(out),
        len(frames),
    )

    return out
import re
import numpy as np
import pandas as pd
import logging
from astropy.io import fits
from astropy.table import Table
from pathlib import Path

log = logging.getLogger(__name__)

def list_observing_dates(qc_root: Path) -> list[Path]:
    return sorted(
        p for p in qc_root.iterdir()
        if p.is_dir() and p.name[:4].isdigit()
    )

def find_qc_csv_files(date_dir: Path, pattern: str):
    return list(date_dir.rglob(pattern))

def find_disp_solution_fits_files(date_dir: Path, pattern: str) -> list[Path]:
    """
    Find dispersion-solution FITS products inside an observing-date folder.

    We look for files matching the configured pattern (e.g. '*_SOXS_FITTED_LINES.fits').
    """
    disp_dir = date_dir / "soxs-disp-solution"

    if not disp_dir.is_dir():
        return []

    return sorted(disp_dir.rglob(pattern))

def infer_arm_from_filename(filename: str) -> str | None:
        """
        Infer instrument arm (VIS/NIR) from QC filename.
        Returns 'VIS', 'NIR', or None if not identifiable.
        """
        name = filename.upper()
        if "_NIR_" in name:
            return "NIR"
        if "_VIS_" in name:
            return "VIS"
        return None

_TS_RE = re.compile(r"^(?P<ts>\d{8}T\d{6})_")

def parse_timestamp_from_filename(name: str) -> str | None:
    """
    Extract ISO timestamp from filenames like '20251129T093102_VIS_...fits'
    Returns a timestamp like '2025-11-29T09:31:02' or None if not parsable.
    """
    m = _TS_RE.match(name)
    if not m:
        return None

    ts = m.group("ts")  # YYYYMMDDThhmmss
    yyyy = ts[0:4]
    mm = ts[4:6]
    dd = ts[6:8]
    hh = ts[9:11]
    mi = ts[11:13]
    ss = ts[13:15]
    return f"{yyyy}-{mm}-{dd}T{hh}:{mi}:{ss}"


def extract_qc_metrics(
    csv_file: Path,
    obs_date: str,
    allowed_metrics: list[str],
    allowed_recipes: list[str],
):
    df = pd.read_csv(csv_file)

    df = df[
        df["qc_name"].isin(allowed_metrics)
        & df["soxspipe_recipe"].isin(allowed_recipes)
    ].copy()

    if df.empty:
        return None
    
    arm = infer_arm_from_filename(csv_file.name)

    if arm is None:
        log.warning(
            "Cannot infer arm from filename %s, skipping file",
            csv_file.name,
        )
        return None

    df["timestamp"] = df["reduction_date_utc"].fillna(df["obs_date_utc"])
    df["obs_date"] = obs_date # YYYY-MM-DD
    df["metric"] = df["qc_name"]
    df["value"] = pd.to_numeric(df["qc_value"], errors="coerce")
    df["unit"] = df["qc_unit"]
    df["arm"] = arm
    df["recipe"] = df["soxspipe_recipe"]
    df["source_file"] = csv_file.name

    return df[
        [
            "timestamp",
            "obs_date",
            "metric",
            "value",
            "unit",
            "arm",
            "recipe",
            "source_file",
        ]
    ]

def extract_disp_solution_metrics_df(
    fits_file: Path,
    obs_date: str,
    hdu_index: int = 1,
) -> pd.DataFrame | None:
    """
    Extract dispersion solution QC metrics from a fitted-lines FITS product.

    Produces a DataFrame with the standard schema:
    obs_date, timestamp, arm, recipe, metric, value, unit, source_file
    """
    arm = infer_arm_from_filename(fits_file.name)
    if arm is None:
        log.warning("Cannot infer arm from filename %s, skipping", fits_file.name)
        return None

    timestamp = parse_timestamp_from_filename(fits_file.name)
    if timestamp is None:
        log.warning("Cannot parse timestamp from filename %s, skipping", fits_file.name)
        return None

    recipe = "soxs-disp-solution"
    source_file = fits_file.name

    # Load FITS table into DataFrame
    with fits.open(fits_file) as hdul:
        hdu = hdul[hdu_index]
        if not isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            raise TypeError(f"HDU #{hdu_index} is not a table HDU in {fits_file}")
        table = Table(hdu.data)

    df = table.to_pandas()

    # Mask
    if "sigma_clipped" in df.columns:
        dfp = df[~df["sigma_clipped"]]
    else:
        dfp = df

    # Defensive checks (fail fast but readable logs)
    required_cols = {"residuals_xy", "order", "R_pin", "fwhm_pin_px", "wavelength"}
    missing = required_cols - set(dfp.columns)
    if missing:
        log.warning("Missing columns %s in %s, skipping", sorted(missing), fits_file.name)
        return None

    # Compute metrics
    residuals_mean = float(np.mean(dfp["residuals_xy"].values))
    residuals_std = float(np.std(dfp["residuals_xy"].values))

    rows: list[dict] = []

    # 1. residuals mean and std
    rows.append(
        {
            "obs_date": obs_date,
            "timestamp": timestamp,
            "arm": arm,
            "recipe": recipe,
            "metric": "DISP_RESIDUALS_MEAN",
            "value": residuals_mean,
            "unit": "px",
            "source_file": source_file,
        }
    )

    rows.append(
        {
            "obs_date": obs_date,
            "timestamp": timestamp,
            "arm": arm,
            "recipe": recipe,
            "metric": "DISP_RESIDUALS_STD",
            "value": residuals_std,
            "unit": "",
            "source_file": source_file,
        }
    )

    # 2. per-order means
    for order, group in dfp.groupby("order"):
        # normalize order to int if possible
        try:
            order_int = int(order)
        except Exception:
            order_int = order  # fallback

        rows.extend(
            [
                {
                    "obs_date": obs_date,
                    "timestamp": timestamp,
                    "arm": arm,
                    "recipe": recipe,
                    "metric": f"DISP_R_MEAN_ORDER_{order_int}",
                    "value": float(group["R_pin"].mean()),
                    "unit": "",  # dimensionless
                    "source_file": source_file,
                },
                {
                    "obs_date": obs_date,
                    "timestamp": timestamp,
                    "arm": arm,
                    "recipe": recipe,
                    "metric": f"DISP_FWHM_MEAN_ORDER_{order_int}",
                    "value": float(group["fwhm_pin_px"].mean()),
                    "unit": "",
                    "source_file": source_file,
                },
                {
                    "obs_date": obs_date,
                    "timestamp": timestamp,
                    "arm": arm,
                    "recipe": recipe,
                    "metric": f"DISP_WAVELENGTH_MEAN_ORDER_{order_int}",
                    "value": float(group["wavelength"].mean()),
                    "unit": "nm",
                    "source_file": source_file,
                },
            ]
        )

    return pd.DataFrame(rows)


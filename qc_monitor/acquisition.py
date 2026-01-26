from pathlib import Path
import pandas as pd
import logging

log = logging.getLogger(__name__)

def list_observing_dates(qc_root: Path) -> list[Path]:
    return sorted(
        p for p in qc_root.iterdir()
        if p.is_dir() and p.name[:4].isdigit()
    )

def find_qc_csv_files(date_dir: Path, pattern: str):
    return list(date_dir.rglob(pattern))

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

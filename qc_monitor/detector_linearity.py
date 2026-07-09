import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.io import fits

log = logging.getLogger(__name__)

VIS_MODE_ORDER = ["SHG", "FLG", "SLG", "FHG"]
DEFAULT_DETLIN_TOKEN = "DETLIN"
DEFAULT_SATURATION_LEVEL = 2**16

DETECTOR_LINEARITY_MEASUREMENT_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "detector_mode",
    "frame_type",
    "exptime",
    "source_file",
    "filepath",
    "roi_name",
    "roi_y1",
    "roi_y2",
    "roi_x1",
    "roi_x2",
    "statistic",
    "signal_raw",
]

DETECTOR_LINEARITY_RESULT_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "detector_mode",
    "exptime",
    "pair_index",
    "file1",
    "file2",
    "signal",
    "fit_signal",
    "residual",
    "residual_percent",
    "fit_used",
    "saturation_limit",
    "slope",
    "intercept",
    "mean_bias_roi",
    "rms_bias_adu",
    "cf",
    "rms_bias_e",
    "dark_file",
    "flat_files",
    "n_flat_frames",
]


def detector_linearity_enabled(cfg: dict) -> bool:
    return bool(cfg.get("detector_linearity", {}).get("enabled", False))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default

    if not np.isfinite(out):
        return default

    return out


def _header_value(header, *names: str):
    for name in names:
        if name in header:
            return header[name]
    return None


def _parse_vis_detlin_filename(path: Path) -> dict[str, object] | None:
    match = re.search(
        r"_VIS_DETLIN_(?P<mode>SHG|FLG|SLG|FHG)_(?P<kind>BIAS|UIT(?P<uit>\d+))_",
        path.name,
        re.IGNORECASE,
    )

    if match is None:
        return None

    kind = match.group("kind").upper()

    return {
        "arm": "VIS",
        "mode": match.group("mode").upper(),
        "frame_type": "Bias" if kind == "BIAS" else "Normal",
        "filename_exptime": 0.0 if kind == "BIAS" else float(match.group("uit")),
    }


def _parse_nir_detlin_filename(path: Path) -> dict[str, object] | None:
    match = re.search(
        r"_NIR_DETLIN_(?:(?P<dark>DARK)_)?DIT(?P<dit>\d+(?:_\d+)?)_",
        path.name,
        re.IGNORECASE,
    )

    if match is None:
        return None

    filename_exptime = float(match.group("dit").replace("_", "."))

    return {
        "arm": "NIR",
        "mode": "NIR",
        "frame_type": "Dark" if match.group("dark") else "Normal",
        "filename_exptime": filename_exptime,
    }


def _parse_detlin_filename(path: Path) -> dict[str, object] | None:
    return _parse_vis_detlin_filename(path) or _parse_nir_detlin_filename(path)


def _validate_roi(roi: list[int] | tuple[int, int, int, int], shape: tuple[int, int]):
    x1, x2, y1, y2 = map(int, roi)
    ny, nx = shape

    if not (0 <= y1 < y2 <= ny and 0 <= x1 < x2 <= nx):
        raise ValueError(f"ROI x=({x1}, {x2}) y=({y1}, {y2}) outside image shape {shape}")

    return x1, x2, y1, y2


def find_detector_linearity_fits_files(root: Path, token: str = DEFAULT_DETLIN_TOKEN) -> list[Path]:
    root = Path(root).expanduser().resolve()

    if not root.is_dir():
        return []

    token = token.upper()
    files = [
        path
        for path in root.rglob("*.fits")
        if token in path.name.upper()
        and "ignored" not in {part.lower() for part in path.parts}
    ]

    return sorted(files)


def _read_roi(path: Path, roi: tuple[int, int, int, int]) -> tuple[np.ndarray, dict]:
    with fits.open(path, memmap=False) as hdul:
        data = hdul[0].data
        if data is None:
            raise ValueError(f"No image data in HDU0: {path}")

        array = np.asarray(data, dtype=np.float64)
        x1, x2, y1, y2 = _validate_roi(roi, array.shape)
        return array[y1:y2, x1:x2].copy(), dict(hdul[0].header)


def _obs_day_from_date(obs_date_utc: str) -> str:
    return str(obs_date_utc)[:10]


def _measure_frame(
    path: Path,
    roi_name: str,
    roi: tuple[int, int, int, int],
    statistic: str,
) -> tuple[dict, np.ndarray] | None:
    parsed = _parse_detlin_filename(path)

    if parsed is None:
        log.debug("Skipping DETLIN candidate with unsupported filename: %s", path)
        return None

    roi_data, header = _read_roi(path, roi)

    obs_date_utc = _header_value(header, "DATE-OBS")
    if obs_date_utc is None:
        raise ValueError(f"Missing DATE-OBS in {path}")

    arm = str(
        _header_value(header, "ESO SEQ ARM", "HIERARCH ESO SEQ ARM")
        or parsed["arm"]
    ).upper()

    if arm == "NIR":
        exptime = _safe_float(
            _header_value(header, "ESO DET SEQ1 DIT", "HIERARCH ESO DET SEQ1 DIT"),
            default=float(parsed["filename_exptime"]),
        )
        frame_type = str(parsed["frame_type"])
    else:
        exptime = _safe_float(
            _header_value(header, "ESO DET UIT1", "HIERARCH ESO DET UIT1"),
            default=float(parsed["filename_exptime"]),
        )
        frame_type = str(
            _header_value(header, "ESO DET EXP TYPE", "HIERARCH ESO DET EXP TYPE")
            or parsed["frame_type"]
        )

    if statistic == "mean":
        signal_raw = float(np.mean(roi_data))
    elif statistic == "median":
        signal_raw = float(np.median(roi_data))
    else:
        raise ValueError(f"Unsupported detector linearity statistic: {statistic}")

    x1, x2, y1, y2 = roi

    row = {
        "obs_day": _obs_day_from_date(obs_date_utc),
        "obs_date_utc": str(obs_date_utc),
        "eso seq arm": arm,
        "detector_mode": str(parsed["mode"]),
        "frame_type": frame_type,
        "exptime": exptime,
        "source_file": path.name,
        "filepath": str(path),
        "roi_name": roi_name,
        "roi_x1": x1,
        "roi_x2": x2,
        "roi_y1": y1,
        "roi_y2": y2,
        "statistic": statistic,
        "signal_raw": signal_raw,
    }

    return row, roi_data


def load_detector_linearity_data(
    cfg: dict,
    processed_obs_days: set[tuple[str, str]] | None = None,
    force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detlin_cfg = cfg.get("detector_linearity", {})

    if not bool(detlin_cfg.get("enabled", False)):
        return (
            pd.DataFrame(columns=DETECTOR_LINEARITY_MEASUREMENT_COLUMNS),
            pd.DataFrame(columns=DETECTOR_LINEARITY_RESULT_COLUMNS),
        )

    arms_cfg = detlin_cfg.get("arms", {})

    if not arms_cfg:
        log.info("No detector-linearity arms are configured")
        return (
            pd.DataFrame(columns=DETECTOR_LINEARITY_MEASUREMENT_COLUMNS),
            pd.DataFrame(columns=DETECTOR_LINEARITY_RESULT_COLUMNS),
        )

    token = str(detlin_cfg.get("filename_token", DEFAULT_DETLIN_TOKEN))
    statistic = str(detlin_cfg.get("statistic", "mean")).lower()
    saturation_limit = (
        float(detlin_cfg.get("saturation_fraction", 0.80))
        * float(detlin_cfg.get("saturation_level", DEFAULT_SATURATION_LEVEL))
    )

    processed_obs_days = processed_obs_days or set()
    measurements = []
    roi_cache = {}

    for configured_arm, arm_cfg in arms_cfg.items():
        if not arm_cfg or not arm_cfg.get("root"):
            continue

        configured_arm = str(configured_arm).upper()
        root = Path(arm_cfg["root"]).expanduser()
        roi_name = str(arm_cfg.get("roi_name", configured_arm))
        roi_default = [512, 537, 2000, 2100] if configured_arm == "VIS" else [0, 0, 0, 0]
        roi = tuple(int(v) for v in arm_cfg.get("roi", roi_default))
        files = find_detector_linearity_fits_files(root, token=token)

        if not files:
            log.info("No detector-linearity FITS files found under %s", root)
            continue

        for path in files:
            try:
                measured = _measure_frame(
                    path=path,
                    roi_name=roi_name,
                    roi=roi,
                    statistic=statistic,
                )
            except Exception as exc:
                log.error("Failed to measure detector-linearity FITS %s: %s", path, exc)
                continue

            if measured is None:
                continue

            row, roi_data = measured

            if row["eso seq arm"] != configured_arm:
                continue

            if not force and (row["obs_day"], row["eso seq arm"]) in processed_obs_days:
                continue

            measurements.append(row)
            roi_cache[row["source_file"]] = roi_data

    if not measurements:
        return (
            pd.DataFrame(columns=DETECTOR_LINEARITY_MEASUREMENT_COLUMNS),
            pd.DataFrame(columns=DETECTOR_LINEARITY_RESULT_COLUMNS),
        )

    df_measurements = pd.DataFrame(measurements)
    df_measurements = df_measurements[DETECTOR_LINEARITY_MEASUREMENT_COLUMNS]

    df_results = compute_detector_linearity_results(
        df_measurements=df_measurements,
        roi_cache=roi_cache,
        saturation_limit=saturation_limit,
    )

    log.info(
        "Loaded %d detector-linearity measurements and %d result rows",
        len(df_measurements),
        len(df_results),
    )

    return df_measurements, df_results


def compute_detector_linearity_results(
    df_measurements: pd.DataFrame,
    roi_cache: dict[str, np.ndarray],
    saturation_limit: float,
) -> pd.DataFrame:
    rows = []

    group_cols = ["obs_day", "eso seq arm", "detector_mode"]

    for (obs_day, arm, mode), group in df_measurements.groupby(group_cols):
        if arm == "NIR":
            pair_rows = _compute_nir_detector_linearity_rows(
                obs_day=obs_day,
                arm=arm,
                mode=mode,
                group=group,
                roi_cache=roi_cache,
                saturation_limit=saturation_limit,
            )
        else:
            pair_rows = _compute_vis_detector_linearity_rows(
                obs_day=obs_day,
                arm=arm,
                mode=mode,
                group=group,
                roi_cache=roi_cache,
                saturation_limit=saturation_limit,
            )

        pair_rows = sorted(pair_rows, key=lambda row: row["exptime"])

        if not pair_rows:
            continue

        if arm == "NIR":
            _warn_if_nir_not_monotonic(pair_rows, saturation_limit=saturation_limit)

        _fit_detector_linearity_rows(pair_rows, saturation_limit=saturation_limit)
        rows.extend(pair_rows)

    if not rows:
        return pd.DataFrame(columns=DETECTOR_LINEARITY_RESULT_COLUMNS)

    return pd.DataFrame(rows)[DETECTOR_LINEARITY_RESULT_COLUMNS]


def _base_result_row(
    obs_day: str,
    obs_date_utc: str,
    arm: str,
    mode: str,
    exptime: float,
    pair_index: int,
    file1: str,
    file2: str,
    signal: float,
    saturation_limit: float,
    mean_bias_roi: float,
    rms_bias_adu: float,
    cf: float,
    rms_bias_e: float,
    dark_file: str = "",
    flat_files: str = "",
    n_flat_frames: int = 0,
) -> dict:
    return {
        "obs_day": obs_day,
        "obs_date_utc": obs_date_utc,
        "eso seq arm": arm,
        "detector_mode": mode,
        "exptime": _safe_float(exptime),
        "pair_index": int(pair_index),
        "file1": file1,
        "file2": file2,
        "signal": signal,
        "fit_signal": 0.0,
        "residual": 0.0,
        "residual_percent": 0.0,
        "fit_used": int(signal <= saturation_limit),
        "saturation_limit": saturation_limit,
        "slope": 0.0,
        "intercept": 0.0,
        "mean_bias_roi": mean_bias_roi,
        "rms_bias_adu": rms_bias_adu,
        "cf": cf,
        "rms_bias_e": rms_bias_e,
        "dark_file": dark_file,
        "flat_files": flat_files,
        "n_flat_frames": int(n_flat_frames),
    }


def _compute_vis_detector_linearity_rows(
    obs_day: str,
    arm: str,
    mode: str,
    group: pd.DataFrame,
    roi_cache: dict[str, np.ndarray],
    saturation_limit: float,
) -> list[dict]:
    bias = group[group["frame_type"].str.lower() == "bias"].copy()
    flats = group[group["frame_type"].str.lower() != "bias"].copy()

    if len(bias) != 2:
        log.warning(
            "Skipping detector-linearity %s %s %s: expected 2 bias frames, got %d",
            obs_day,
            arm,
            mode,
            len(bias),
        )
        return []

    if flats.empty:
        log.warning("Skipping detector-linearity %s %s %s: no flat frames", obs_day, arm, mode)
        return []

    bias_arrays = [
        roi_cache[row["source_file"]]
        for _, row in bias.sort_values("obs_date_utc").iterrows()
    ]
    master_bias = 0.5 * (bias_arrays[0] + bias_arrays[1])
    mean_bias_roi = _safe_float(np.mean(master_bias))
    rms_bias_adu = _safe_float(np.sqrt(np.var(bias_arrays[0] - bias_arrays[1]) / 2.0))

    rows = []

    for exptime, flat_group in flats.groupby("exptime"):
        flat_group = flat_group.sort_values("obs_date_utc")

        if len(flat_group) != 2:
            log.warning(
                "Skipping detector-linearity %s %s %s exptime %.6g: expected 2 flat frames, got %d",
                obs_day,
                arm,
                mode,
                exptime,
                len(flat_group),
            )
            continue

        first, second = [row for _, row in flat_group.iterrows()]
        image1 = roi_cache[first["source_file"]] - master_bias
        image2 = roi_cache[second["source_file"]] - master_bias

        signal = 0.5 * (_safe_float(np.mean(image1)) + _safe_float(np.mean(image2)))
        diff = image1 - image2
        var_single = _safe_float(np.var(diff) / 2.0)
        cf = _safe_float(signal / var_single) if var_single > 0 else 0.0
        rms_bias_e = _safe_float(rms_bias_adu * cf)

        rows.append(_base_result_row(
            obs_day=obs_day,
            obs_date_utc=first["obs_date_utc"],
            arm=arm,
            mode=mode,
            exptime=exptime,
            pair_index=1,
            file1=first["source_file"],
            file2=second["source_file"],
            signal=signal,
            saturation_limit=saturation_limit,
            mean_bias_roi=mean_bias_roi,
            rms_bias_adu=rms_bias_adu,
            cf=cf,
            rms_bias_e=rms_bias_e,
            flat_files=",".join([first["source_file"], second["source_file"]]),
            n_flat_frames=2,
        ))

    return rows


def _compute_nir_detector_linearity_rows(
    obs_day: str,
    arm: str,
    mode: str,
    group: pd.DataFrame,
    roi_cache: dict[str, np.ndarray],
    saturation_limit: float,
) -> list[dict]:
    darks = group[group["frame_type"].str.lower() == "dark"].copy()
    flats = group[group["frame_type"].str.lower() != "dark"].copy()

    if darks.empty:
        log.warning("Skipping detector-linearity %s %s %s: no dark frames", obs_day, arm, mode)
        return []

    if flats.empty:
        log.warning("Skipping detector-linearity %s %s %s: no flat frames", obs_day, arm, mode)
        return []

    rows = []

    for exptime, flat_group in flats.groupby("exptime"):
        flat_group = flat_group.sort_values("obs_date_utc")
        dark_group = darks[darks["exptime"] == exptime].sort_values("obs_date_utc")

        if dark_group.empty:
            log.warning(
                "Skipping detector-linearity %s %s %s exptime %.6g: no matching dark frame",
                obs_day,
                arm,
                mode,
                exptime,
            )
            continue

        if len(dark_group) > 1:
            log.warning(
                "Detector-linearity %s %s %s exptime %.6g has %d dark frames; using the first",
                obs_day,
                arm,
                mode,
                exptime,
                len(dark_group),
            )

        dark = dark_group.iloc[0]
        dark_image = roi_cache[dark["source_file"]]
        corrected_images = [
            roi_cache[row["source_file"]] - dark_image
            for _, row in flat_group.iterrows()
        ]
        flat_files = [row["source_file"] for _, row in flat_group.iterrows()]

        signal = _safe_float(np.mean([np.mean(image) for image in corrected_images]))
        mean_bias_roi = _safe_float(np.mean(dark_image))

        if len(corrected_images) >= 2:
            diff = corrected_images[0] - corrected_images[1]
            rms_bias_adu = _safe_float(np.sqrt(np.var(diff) / 2.0))
            var_single = _safe_float(np.var(diff) / 2.0)
            cf = _safe_float(signal / var_single) if var_single > 0 else 0.0
            rms_bias_e = _safe_float(rms_bias_adu * cf)
        else:
            rms_bias_adu = 0.0
            cf = 0.0
            rms_bias_e = 0.0

        first_flat = flat_group.iloc[0]
        rows.append(_base_result_row(
            obs_day=obs_day,
            obs_date_utc=first_flat["obs_date_utc"],
            arm=arm,
            mode=mode,
            exptime=exptime,
            pair_index=1,
            file1=flat_files[0],
            file2=flat_files[1] if len(flat_files) > 1 else "",
            signal=signal,
            saturation_limit=saturation_limit,
            mean_bias_roi=mean_bias_roi,
            rms_bias_adu=rms_bias_adu,
            cf=cf,
            rms_bias_e=rms_bias_e,
            dark_file=dark["source_file"],
            flat_files=",".join(flat_files),
            n_flat_frames=len(flat_files),
        ))

    return rows


def _fit_detector_linearity_rows(rows: list[dict], saturation_limit: float):
    x = np.array([_safe_float(row["exptime"]) for row in rows], dtype=float)
    y = np.array([_safe_float(row["signal"]) for row in rows], dtype=float)
    good = (
        np.isfinite(x)
        & np.isfinite(y)
        & (x > 0)
        & (y > 0)
        & (y <= saturation_limit)
    )

    if np.count_nonzero(good) < 2:
        log.warning("Cannot fit detector linearity: fewer than 2 unsaturated points")
        return

    slope, intercept = np.polyfit(x[good], y[good], 1)
    y_fit = slope * x + intercept

    for index, row in enumerate(rows):
        residual = y[index] - y_fit[index]
        residual_percent = residual / y_fit[index] * 100.0 if y_fit[index] != 0 else 0.0

        row["fit_signal"] = _safe_float(y_fit[index])
        row["residual"] = _safe_float(residual)
        row["residual_percent"] = _safe_float(residual_percent)
        row["fit_used"] = int(bool(good[index]))
        row["slope"] = _safe_float(slope)
        row["intercept"] = _safe_float(intercept)


def _warn_if_nir_not_monotonic(rows: list[dict], saturation_limit: float):
    fit_rows = [
        row
        for row in sorted(rows, key=lambda item: _safe_float(item["exptime"]))
        if _safe_float(row["signal"]) <= saturation_limit
    ]

    if len(fit_rows) < 2:
        return

    signals = np.array([_safe_float(row["signal"]) for row in fit_rows], dtype=float)
    exptimes = np.array([_safe_float(row["exptime"]) for row in fit_rows], dtype=float)
    diffs = np.diff(signals)

    if np.any(diffs < 0):
        log.warning(
            "NIR detector-linearity signals are not monotonic before saturation: "
            "exptimes=%s signals=%s",
            [float(v) for v in exptimes],
            [float(v) for v in signals],
        )

import logging
from itertools import combinations
import re
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.io import fits
from qc_monitor._outcomes import AcquisitionBatch, InputOutcome

log = logging.getLogger(__name__)

VIS_MODE_ORDER = ["SHG", "FLG", "SLG", "FHG"]
DEFAULT_DETLIN_TOKEN = "DETLIN"
DEFAULT_SATURATION_LEVEL = 2**16
DEFAULT_SATURATION_FRACTION = 0.60

DETECTOR_LINEARITY_MEASUREMENT_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "detector_mode",
    "frame_type",
    "exptime",
    "source_file",
    "sequence_image_name",
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


def _parse_vis_detlin_name(name: str) -> dict[str, object] | None:
    match = re.search(
        r"_VIS_DETLIN_(?P<mode>SHG|FLG|SLG|FHG)_(?P<kind>BIAS|UIT(?P<uit>\d+))_",
        name,
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


def _parse_nir_detlin_name(name: str) -> dict[str, object] | None:
    match = re.search(
        r"_NIR_DETLIN_(?:(?P<dark>DARK)_)?DIT(?P<dit>\d+(?:_\d+)?)_",
        name,
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


def _parse_detlin_name(name: str) -> dict[str, object] | None:
    return _parse_vis_detlin_name(name) or _parse_nir_detlin_name(name)


def _validate_roi(roi: list[int] | tuple[int, int, int, int], shape: tuple[int, int]):
    x1, x2, y1, y2 = map(int, roi)
    ny, nx = shape

    if not (0 <= y1 < y2 <= ny and 0 <= x1 < x2 <= nx):
        raise ValueError(f"ROI x=({x1}, {x2}) y=({y1}, {y2}) outside image shape {shape}")

    return x1, x2, y1, y2


def _sequence_image_name_from_header(header, arm: str) -> str:
    arm = str(arm).upper()

    if arm == "NIR":
        value = _header_value(
            header,
            "ESO OCS DET1 IMGNAME",
            "HIERARCH ESO OCS DET1 IMGNAME",
        )
    elif arm == "VIS":
        value = _header_value(
            header,
            "ESO OCS DET2 IMGNAME",
            "HIERARCH ESO OCS DET2 IMGNAME",
        )
    else:
        value = None

    return "" if value is None else str(value).strip()


def _scan_detector_linearity_candidates(
    root: Path,
    arm: str,
    token: str = DEFAULT_DETLIN_TOKEN,
    allow_filename_fallback: bool = False,
    outcomes: list[InputOutcome] | None = None,
) -> list[tuple[Path, dict, str]]:
    root = Path(root).expanduser().resolve()

    if not root.is_dir():
        return []

    token = token.upper()
    files = sorted(
        path
        for path in root.rglob("*.fits")
        if "ignored" not in {part.lower() for part in path.parts}
    )
    candidates = []
    outcomes = outcomes if outcomes is not None else []
    scanned = 0
    header_matches = 0
    fallback_matches = 0

    for path in files:
        scanned += 1

        try:
            header = fits.getheader(path, 0)
        except Exception as exc:
            log.warning("Cannot read FITS header for detector-linearity candidate %s: %s", path, exc)
            named = _parse_detlin_name(path.name)
            if (named and named["arm"] == arm) or (token in path.name.upper() and named is None):
                outcomes.append(InputOutcome(str(path), "failed", reason=str(exc), arm=arm))
            else:
                outcomes.append(InputOutcome(str(path), "foreign", arm=arm))
            continue

        sequence_image_name = _sequence_image_name_from_header(header, arm)
        parsed = None

        if token in sequence_image_name.upper():
            parsed = _parse_detlin_name(sequence_image_name)
            if parsed is not None:
                header_matches += 1

        if parsed is None and allow_filename_fallback and token in path.name.upper():
            sequence_image_name = path.name
            parsed = _parse_detlin_name(path.name)
            if parsed is not None:
                fallback_matches += 1

        if parsed is None:
            state = "failed" if token in sequence_image_name.upper() else "foreign"
            outcomes.append(InputOutcome(str(path), state, reason="Unrecognized sequence name", arm=arm))
            continue

        if str(parsed["arm"]).upper() != str(arm).upper():
            continue

        candidates.append((path, parsed, sequence_image_name))

    log.info(
        "Scanned %d FITS headers under %s for %s detector-linearity; "
        "matched %d via header and %d via filename fallback",
        scanned,
        root,
        arm,
        header_matches,
        fallback_matches,
    )

    if scanned and not candidates:
        log.warning(
            "No %s detector-linearity FITS recognized under %s from sequence IMGNAME headers",
            arm,
            root,
        )

    return candidates


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


def validate_frame_classification(header, arm, kind):
    """Check name-derived classification; return a warning for legacy DPR."""
    expected = "LAMP,OFF" if kind.lower() in {"bias", "dark"} else "LAMP,ON"
    raw = header.get("ESO DPR TYPE", header.get("HIERARCH ESO DPR TYPE"))
    dpr = "" if raw is None else ",".join(part.strip().upper() for part in str(raw).split(","))
    if dpr not in {"", "LAMP,FLAT", expected}:
        raise ValueError(f"ESO DPR TYPE={raw!r}; expected {expected} from sequence name")
    if arm.upper() == "VIS":
        exp_type = header.get("ESO DET EXP TYPE", header.get("HIERARCH ESO DET EXP TYPE"))
        expected_type = "Bias" if kind.lower() == "bias" else "Normal"
        if exp_type is not None and str(exp_type).strip().lower() != expected_type.lower():
            raise ValueError(
                f"ESO DET EXP TYPE={exp_type!r}; expected {expected_type} from sequence name"
            )
    if dpr in {"", "LAMP,FLAT"}:
        return (f"Legacy ESO DPR TYPE={raw!r}; classification cannot be verified "
                f"against expected {expected}; using sequence name")
    return None


def _measure_frame(
    path: Path,
    parsed: dict[str, object],
    sequence_image_name: str,
    roi_name: str,
    roi: tuple[int, int, int, int],
    statistic: str,
) -> tuple[dict, np.ndarray] | None:
    header = fits.getheader(path, 0)
    warning = validate_frame_classification(header, str(parsed["arm"]), str(parsed["frame_type"]))
    if warning:
        log.warning("%s: %s", path, warning)
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
        frame_type = str(parsed["frame_type"])

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
        "sequence_image_name": sequence_image_name,
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
    cfg: dict, processed_obs_days: set[tuple[str, str]] | None = None, force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    batch = _load_detector_linearity_batch(cfg, processed_obs_days, force)
    return batch.frames["measurements"], batch.frames["results"]


def _load_detector_linearity_batch(
    cfg: dict,
    processed_obs_days: set[tuple[str, str]] | None = None,
    force: bool = False,
) -> AcquisitionBatch:
    detlin_cfg = cfg.get("detector_linearity", {})

    if not bool(detlin_cfg.get("enabled", False)):
        return AcquisitionBatch({"measurements": pd.DataFrame(columns=DETECTOR_LINEARITY_MEASUREMENT_COLUMNS),
                                 "results": pd.DataFrame(columns=DETECTOR_LINEARITY_RESULT_COLUMNS)})

    arms_cfg = detlin_cfg.get("arms", {})

    if not arms_cfg:
        log.info("No detector-linearity arms are configured")
        return AcquisitionBatch({"measurements": pd.DataFrame(columns=DETECTOR_LINEARITY_MEASUREMENT_COLUMNS),
                                 "results": pd.DataFrame(columns=DETECTOR_LINEARITY_RESULT_COLUMNS)})

    token = str(detlin_cfg.get("filename_token", DEFAULT_DETLIN_TOKEN))
    statistic = str(detlin_cfg.get("statistic", "mean")).lower()
    saturation_level = float(detlin_cfg.get("saturation_level", DEFAULT_SATURATION_LEVEL))
    saturation_fraction = float(detlin_cfg.get("saturation_fraction", DEFAULT_SATURATION_FRACTION))
    if not np.isfinite(saturation_level) or saturation_level <= 0 or not 0 < saturation_fraction <= 1:
        raise ValueError("Invalid detector-linearity saturation_level or saturation_fraction")
    saturation_limit = saturation_fraction * saturation_level

    processed_obs_days = processed_obs_days or set()
    measurements = []
    roi_cache = {}
    outcomes = []
    inventory = []

    for configured_arm, arm_cfg in arms_cfg.items():
        if not arm_cfg or not arm_cfg.get("root"):
            continue

        configured_arm = str(configured_arm).upper()
        root = Path(arm_cfg["root"]).expanduser()
        roi_name = str(arm_cfg.get("roi_name", configured_arm))
        roi_default = [512, 537, 2000, 2100] if configured_arm == "VIS" else [0, 0, 0, 0]
        roi = tuple(int(v) for v in arm_cfg.get("roi", roi_default))
        allow_filename_fallback = bool(arm_cfg.get("allow_filename_fallback", False))
        candidates = _scan_detector_linearity_candidates(
            root=root,
            arm=configured_arm,
            token=token,
            allow_filename_fallback=allow_filename_fallback,
            outcomes=outcomes,
        )

        if not candidates:
            log.info("No detector-linearity FITS files found under %s", root)
            continue

        for path, parsed, sequence_image_name in candidates:
            unit = None
            try:
                header = fits.getheader(path, 0)
                date = str(_header_value(header, "DATE-OBS") or "")
                if date:
                    unit = (_obs_day_from_date(date), configured_arm)
                if not force and unit in processed_obs_days:
                    outcomes.append(InputOutcome(str(path), "skipped", unit))
                    continue
                entry = {"unit": unit, "path": str(path), "start": header.get("ESO TPL START"),
                         "id": header.get("ESO TPL ID"), "nexp": header.get("ESO TPL NEXP"),
                         "expno": header.get("ESO TPL EXPNO")}
                inventory.append(entry)
                if unit is None:
                    raise ValueError("Missing DATE-OBS")
                measured = _measure_frame(
                    path=path,
                    parsed=parsed,
                    sequence_image_name=sequence_image_name,
                    roi_name=roi_name,
                    roi=roi,
                    statistic=statistic,
                )
            except Exception as exc:
                log.error("Failed to measure detector-linearity FITS %s: %s", path, exc)
                outcomes.append(InputOutcome(str(path), "failed", unit, str(exc), configured_arm))
                continue

            if measured is None:
                continue

            row, roi_data = measured

            if row["eso seq arm"] != configured_arm:
                outcomes.append(InputOutcome(str(path), "failed", unit, "Arm/header mismatch", configured_arm))
                continue
            if not np.isfinite(row["signal_raw"]) or not np.isfinite(roi_data).all():
                outcomes.append(InputOutcome(str(path), "failed", unit, "Nonfinite measurement", configured_arm))
                continue
            outcomes.append(InputOutcome(str(path), "acquired", unit))

            if not force and (row["obs_day"], row["eso seq arm"]) in processed_obs_days:
                continue

            measurements.append(row)
            roi_cache[row["source_file"]] = roi_data

    ambiguous = _validate_detlin_inventory(inventory, outcomes)
    if not measurements:
        return AcquisitionBatch({"measurements": pd.DataFrame(columns=DETECTOR_LINEARITY_MEASUREMENT_COLUMNS),
                                 "results": pd.DataFrame(columns=DETECTOR_LINEARITY_RESULT_COLUMNS)}, outcomes)

    df_measurements = pd.DataFrame(measurements)
    df_measurements = df_measurements[DETECTOR_LINEARITY_MEASUREMENT_COLUMNS]

    df_results = compute_detector_linearity_results(
        df_measurements=df_measurements.loc[[
            (str(row["obs_day"]), str(row["eso seq arm"])) not in ambiguous
            for _, row in df_measurements.iterrows()]],
        roi_cache=roi_cache,
        saturation_limit=saturation_limit,
    )

    log.info(
        "Loaded %d detector-linearity measurements and %d result rows",
        len(df_measurements),
        len(df_results),
    )

    for unit, group in df_measurements.groupby(["obs_day", "eso seq arm"]):
        unit = tuple(str(value) for value in unit)
        required_modes = set(VIS_MODE_ORDER) if unit[1] == "VIS" else {"NIR"}
        if set(group["detector_mode"]) != required_modes:
            outcomes.append(InputOutcome("sequence", "failed", unit, "Missing detector modes"))
        for mode, mode_group in group.groupby("detector_mode"):
            flats = mode_group[~mode_group["frame_type"].str.lower().isin(["bias", "dark"])]
            if unit[1] == "VIS" and len(mode_group[mode_group["frame_type"].str.lower() == "bias"]) != 3:
                outcomes.append(InputOutcome(mode, "failed", unit, "Expected three VIS bias frames"))
            times = set(flats["exptime"])
            if unit[1] == "NIR":
                times.update(mode_group.loc[mode_group["frame_type"].str.lower() == "dark", "exptime"])
            for time in sorted(times):
                pair = flats[flats["exptime"] == time]
                darks = mode_group[(mode_group["frame_type"].str.lower() == "dark") & (mode_group["exptime"] == time)]
                if len(pair) != 2 or (unit[1] == "NIR" and len(darks) != 1):
                    outcomes.append(InputOutcome(mode, "failed", unit, f"Incomplete exposure at time {time}"))
            fitted = df_results[(df_results["obs_day"] == unit[0]) &
                                (df_results["eso seq arm"] == unit[1]) &
                                (df_results["detector_mode"] == mode)]
            if fitted.empty or fitted.loc[fitted["fit_used"] == 1, "exptime"].nunique() < 2 or not np.isfinite(fitted[["slope", "intercept"]].to_numpy(dtype=float)).all():
                outcomes.append(InputOutcome(mode, "failed", unit, "Required fit unavailable"))
    return AcquisitionBatch({"measurements": df_measurements, "results": df_results}, outcomes)


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

    if len(bias) != 3:
        log.warning(
            "Skipping detector-linearity %s %s %s: expected 3 bias frames, got %d",
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
    master_bias = np.mean(bias_arrays, axis=0)
    mean_bias_roi = _safe_float(np.mean(master_bias))
    # Estimate single-frame read noise from all pairs, not the noise of the master.
    pair_variances = [np.var(a - b, ddof=0) for a, b in combinations(bias_arrays, 2)]
    rms_bias_adu = _safe_float(np.sqrt(np.mean(pair_variances) / 2.0))

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

    for row in rows:
        row["fit_used"] = 0

    if len(np.unique(x[good])) < 2:
        log.warning(
            "Cannot fit detector linearity: fewer than 2 distinct usable times "
            "at signal <= %.6g ADU",
            saturation_limit,
        )
        return

    slope, intercept = np.polyfit(x[good], y[good], 1)
    log.info(
        "Detector-linearity fit: %d/%d points, signal <= %.6g ADU",
        np.count_nonzero(good), len(rows), saturation_limit,
    )
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


def _validate_detlin_inventory(inventory: list[dict], outcomes: list[InputOutcome]) -> set[tuple]:
    ambiguous = set()
    sequences = {}
    by_unit = {}
    names = {}
    for entry in inventory:
        unit = entry["unit"]
        if unit is None:
            continue
        try:
            if not str(entry["start"] or "").strip() or not str(entry["id"] or "").strip():
                raise ValueError("Missing TPL START/ID")
            n, index = int(entry["nexp"]), int(entry["expno"])
            if n <= 0 or index < 1 or index > n or n != float(entry["nexp"]) or index != float(entry["expno"]):
                raise ValueError("Invalid TPL NEXP/EXPNO")
            sequence = (unit[1], str(entry["id"]), str(entry["start"]))
            sequences.setdefault(sequence, []).append(entry)
            by_unit.setdefault(unit, set()).add(sequence)
            name = Path(entry["path"]).name
            names.setdefault(name, []).append(unit)
        except (TypeError, ValueError, OverflowError) as exc:
            outcomes.append(InputOutcome(entry["path"], "failed", unit, str(exc)))
            ambiguous.add(unit)
    for sequence, entries in sequences.items():
        units = {entry["unit"] for entry in entries}
        counts = {int(entry["nexp"]) for entry in entries}
        indices = [int(entry["expno"]) for entry in entries]
        if len(units) != 1:
            ambiguous.update(units)
            reason = "Sequence crosses observing days"
        elif len(counts) != 1 or len(indices) != next(iter(counts)) or len(indices) != len(set(indices)):
            reason = "Incomplete/inconsistent sequence exposure inventory"
        else:
            continue
        for unit in units:
            outcomes.append(InputOutcome(str(sequence), "failed", unit, reason))
    for unit, sequences_for_unit in by_unit.items():
        if len(sequences_for_unit) > 1:
            ambiguous.add(unit)
            outcomes.append(InputOutcome("sequence", "failed", unit, "Multiple sequences for day/arm"))
    for name, units in names.items():
        if len(units) > 1:
            ambiguous.update(units)
            for unit in set(units):
                outcomes.append(InputOutcome(name, "failed", unit, "Ambiguous source filename"))
    return ambiguous

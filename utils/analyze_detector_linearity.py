#!/usr/bin/env python3
"""Standalone SOXS detector-linearity analysis; no qc_monitor imports or output files.

Run in an environment with NumPy, Astropy, Matplotlib and PyYAML:
    python utils/analyze_detector_linearity.py --config configs/qc_monitor_SSA.yaml

ROI bounds are half-open frame coordinates at binning 1x1. Signals and ADU
thresholds are divided by BINX*BINY. Like qc-monitor, corrected signals and fits use
means; the configured mean/median statistic applies to raw frame diagnostics.
"""

import argparse
from itertools import combinations
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import math
from pathlib import Path
import re
import sys


VIS_MODES = ["SHG", "FLG", "SLG", "FHG"]


def load_libraries():
    global np, fits, plt, yaml
    import numpy as np
    from astropy.io import fits
    import matplotlib.pyplot as plt
    import yaml


@dataclass
class Frame:
    path: Path
    time: str
    kind: str
    exptime: float
    image: object
    shape: tuple
    raw_statistic: float


@dataclass
class Group:
    arm: str
    mode: str
    acquisition: str
    day: str
    binning: tuple
    frames: list = field(default_factory=list)
    found: int = 0
    used: set = field(default_factory=set)
    discarded: list = field(default_factory=list)
    notes: set = field(default_factory=set)
    points: list = field(default_factory=list)
    curves: dict = field(default_factory=dict)


def parse_name(name):
    match = re.search(
        r"_VIS_DETLIN_(SHG|FLG|SLG|FHG)_(BIAS|UIT(\d+))_", name, re.I
    )
    if match:
        return "VIS", match[1].upper(), "bias" if match[2].upper() == "BIAS" else "flat", float(match[3] or 0)
    match = re.search(r"_NIR_DETLIN_(?:(DARK)_)?DIT(\d+(?:_\d+)?)_", name, re.I)
    if match:
        return "NIR", "NIR", "dark" if match[1] else "flat", float(match[2].replace("_", "."))
    return None


def positive_integer(value):
    number = float(value)
    if not math.isfinite(number) or number < 1 or not number.is_integer():
        raise ValueError(f"invalid positive integer: {value}")
    return int(number)


def valid_time(value):
    value = str(value).strip()
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def mapped_roi(roi, binning, shape):
    x1, x2, y1, y2 = roi
    bx, by = binning
    result = (math.floor(x1 / bx), math.ceil(x2 / bx),
              math.floor(y1 / by), math.ceil(y2 / by))
    ax1, ax2, ay1, ay2 = result
    ny, nx = shape
    if not (0 <= ax1 < ax2 <= nx and 0 <= ay1 < ay2 <= ny):
        raise ValueError(f"ROI {result} outside image shape {shape}")
    return result


def load_config(path):
    with path.open() as stream:
        cfg = yaml.safe_load(stream)
    if not isinstance(cfg, dict):
        raise ValueError("configuration must be a YAML mapping")
    det = cfg.get("detector_linearity", {})
    if not isinstance(det, dict) or not isinstance(det.get("arms"), dict) or not det["arms"]:
        raise ValueError("detector_linearity.arms must contain at least one arm")
    if str(det.get("statistic", "mean")).lower() not in ("mean", "median"):
        raise ValueError("statistic must be mean or median")
    level = float(det.get("saturation_level", 65536))
    fraction = float(det.get("saturation_fraction", 0.60))
    if not math.isfinite(level) or level <= 0 or not 0 < fraction <= 1:
        raise ValueError("invalid saturation_level or saturation_fraction")
    for arm, settings in det["arms"].items():
        if arm.upper() not in ("VIS", "NIR") or not isinstance(settings, dict) or not settings.get("root"):
            raise ValueError(f"invalid arm configuration: {arm}")
        roi = settings.get("roi", [512, 537, 2000, 2100] if arm.upper() == "VIS" else None)
        if not isinstance(roi, (list, tuple)) or len(roi) != 4:
            raise ValueError(f"{arm}: roi must contain [x1,x2,y1,y2]")
        if any(not math.isfinite(float(v)) or float(v) != int(v) for v in roi):
            raise ValueError(f"{arm}: roi must contain integer coordinates")
        if not (0 <= roi[0] < roi[1] and 0 <= roi[2] < roi[3]):
            raise ValueError(f"{arm}: invalid ROI bounds")
    plots = cfg.get("plots", {})
    if not isinstance(plots, dict):
        raise ValueError("plots must be a YAML mapping")
    if not isinstance(plots.get("figures", []), list) or not isinstance(plots.get("include", []), list):
        raise ValueError("plots.figures and plots.include must be lists")
    figures = list(plots.get("figures", []))
    for include in plots.get("include", []):
        with (path.parent / include).open() as stream:
            included = yaml.safe_load(stream) or {}
        if not isinstance(included, dict) or not isinstance(included.get("figures", []), list):
            raise ValueError(f"invalid plot include: {include}")
        figures.extend(included.get("figures", []))
    if any(not isinstance(f, dict) for f in figures):
        raise ValueError("plot figures must be YAML mappings")
    figures = [f for f in figures if f.get("type") == "detector_linearity"]
    if not figures:
        figures = [{"arm": arm.upper(), "type": "detector_linearity"}
                   for arm in det["arms"]]
    for figure in figures:
        if figure.get("selection", "latest") not in ("latest", "all"):
            raise ValueError("plot selection must be latest or all")
        arm = figure.get("arm", "VIS").upper()
        modes = figure.get("mode_order", VIS_MODES if arm == "VIS" else ["NIR"])
        if arm not in ("VIS", "NIR") or not isinstance(modes, list) or not modes or len(set(modes)) != len(modes):
            raise ValueError("invalid plot arm or mode_order")
        if any(mode not in (VIS_MODES if arm == "VIS" else ["NIR"]) for mode in modes):
            raise ValueError("mode_order contains an unknown detector mode")
        if len(modes) > (4 if arm == "VIS" else 1):
            raise ValueError("plots support up to four VIS modes or one NIR mode")
    return det, figures, level, level * fraction


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


def scan_frames(det, project_root):
    groups = {}
    acquisitions = defaultdict(lambda: {"numbers": set(), "expected": set()})
    messages = []
    token = str(det.get("filename_token", "DETLIN")).upper()
    for configured_arm, settings in det["arms"].items():
        arm = configured_arm.upper()
        root = Path(settings["root"]).expanduser()
        if not root.is_absolute():
            root = project_root / root
        root = root.resolve()
        if not root.is_dir():
            messages.append(f"{arm}: root unavailable: {root}")
            continue
        files = sorted(p for p in root.rglob("*.fits")
                       if "ignored" not in {part.lower() for part in p.parts})
        recognized = 0
        for path in files:
            try:
                header = fits.getheader(path, 0)
            except Exception as exc:
                messages.append(f"Discarded {path}: cannot read header: {exc}")
                continue
            name = str(header.get(f"ESO OCS DET{2 if arm == 'VIS' else 1} IMGNAME", ""))
            parsed = parse_name(name) if token in name.upper() else None
            fallback = False
            if parsed is None and settings.get("allow_filename_fallback", False) and token in path.name.upper():
                parsed = parse_name(path.name)
                fallback = parsed is not None
            if parsed is None or parsed[0] != arm:
                continue
            recognized += 1
            group = None
            try:
                _, mode, kind, filename_time = parsed
                if str(header.get("ESO SEQ ARM", arm)).upper() != arm:
                    raise ValueError("header arm differs from configured arm")
                obs_time = valid_time(header.get("DATE-OBS", ""))
                acquisition = str(header.get("ESO TPL START", "")).strip() or obs_time[:10]
                binning = tuple(positive_integer(header.get(f"ESO DET BIN{axis}", 1)) for axis in "XY")
                key = (acquisition, arm, mode, binning)
                group = groups.setdefault(key, Group(arm, mode, acquisition, obs_time[:10], binning))
                group.found += 1
                group.day = max(group.day, obs_time[:10])
                if not header.get("ESO TPL START"):
                    group.notes.add("TPL START missing: grouped by observing day")
                if any(f"ESO DET BIN{axis}" not in header for axis in "XY"):
                    group.notes.add("Missing binning header axis/axes assumed to be 1")
                if fallback:
                    group.notes.add("Used filename fallback for frame recognition")
                audit = acquisitions[(acquisition, arm)]
                for keyword, target in (("ESO TPL EXPNO", "numbers"), ("ESO TPL NEXP", "expected")):
                    if keyword in header:
                        try:
                            audit[target].add(positive_integer(header[keyword]))
                        except ValueError:
                            group.notes.add(f"Invalid {keyword}: missing-exposure audit incomplete")
                    else:
                        group.notes.add(f"Missing {keyword}: missing-exposure audit incomplete")
                exptime = float(header.get("ESO DET UIT1" if arm == "VIS" else "ESO DET SEQ1 DIT", filename_time))
                if not math.isfinite(exptime) or exptime < 0:
                    raise ValueError("invalid exposure time")
                warning = validate_frame_classification(header, arm, kind)
                if warning:
                    group.notes.add(f"{path}: {warning}")
                with fits.open(path, memmap=False) as hdul:
                    if hdul[0].data is None or hdul[0].data.ndim != 2:
                        raise ValueError("HDU0 must contain a 2D image")
                    shape = hdul[0].data.shape
                    roi = tuple(settings.get("roi", [512, 537, 2000, 2100]))
                    applied = mapped_roi(roi, binning, shape)
                    x1, x2, y1, y2 = applied
                    image = np.array(hdul[0].data[y1:y2, x1:x2], dtype=float, copy=True)
                if not np.isfinite(image).all():
                    raise ValueError("ROI contains non-finite pixels")
                image /= binning[0] * binning[1]
                group.notes.add(f"ROI {settings.get('roi_name', arm)}: {roi} -> {applied}; binning {binning[0]}x{binning[1]}"
                                + (" (adapted)" if binning != (1, 1) else ""))
                raw = float(np.median(image) if det.get("statistic", "mean").lower() == "median" else np.mean(image))
                group.frames.append(Frame(path, obs_time, kind, exptime, image, shape, raw))
            except Exception as exc:
                if group is None:
                    messages.append(f"Discarded {path}: {exc}")
                else:
                    group.discarded.append(f"{path}: {exc}")
        messages.append(f"{arm}: scanned {len(files)} FITS; recognized {recognized}; root={root}")
    for (acquisition, arm), audit in sorted(acquisitions.items()):
        if len(audit["expected"]) == 1 and audit["numbers"]:
            expected = next(iter(audit["expected"]))
            missing = sorted(set(range(1, expected + 1)) - audit["numbers"])
            messages.append(f"{arm} acquisition {acquisition}: missing exposure numbers {missing or 'none'} / {expected}")
            if max(audit["numbers"]) > expected:
                messages.append(f"{arm} {acquisition}: EXPNO exceeds NEXP")
        elif len(audit["expected"]) > 1:
            messages.append(f"{arm} {acquisition}: inconsistent TPL NEXP {sorted(audit['expected'])}")
    return list(groups.values()), messages


def compute_group(group, threshold, level):
    area = group.binning[0] * group.binning[1]
    threshold /= area
    level /= area
    group.notes.add(f"Signals normalized to 1x1-equivalent ADU: divided by {area}; "
                    f"fit threshold={threshold:g}, nominal saturation={level:g} normalized ADU")
    frames = sorted(group.frames, key=lambda f: (f.time, str(f.path)))
    # Exact frame geometry is required for pixelwise subtraction and pair noise.
    # Keep the geometry of the earliest flat; do not silently mix windows.
    flats = [f for f in frames if f.kind == "flat"]
    if not flats:
        group.notes.add("No usable flat frames; fit unavailable")
        return
    shape = flats[0].shape
    compatible = []
    for frame in frames:
        if frame.shape != shape:
            group.discarded.append(f"{frame.path}: image shape {frame.shape} differs from {shape}")
        else:
            compatible.append(frame)
    refs = [f for f in compatible if f.kind != "flat"]
    flats = [f for f in compatible if f.kind == "flat"]
    master = None
    bias_noise = None
    if group.arm == "VIS":
        if len(refs) != 3:
            group.notes.add(f"Expected 3 biases; found {len(refs)}; "
                            + ("using available biases" if refs else "using raw signals"))
        if refs:
            master = np.mean([f.image for f in refs], axis=0)
            if len(refs) >= 2:
                # Same single-frame estimator as qc-monitor, generalized to N biases.
                pair_variances = [np.var(a.image - b.image, ddof=0)
                                  for a, b in combinations(refs, 2)]
                bias_noise = float(np.sqrt(np.mean(pair_variances) / 2))
    by_time = defaultdict(list)
    for frame in flats:
        by_time[frame.exptime].append(frame)
    for exptime, flat_frames in sorted(by_time.items()):
        if len(flat_frames) != 2:
            group.notes.add(f"t={exptime:g}s: expected 2 flats; found {len(flat_frames)}; using available flats")
        selected_refs = refs if group.arm == "VIS" else [f for f in refs if f.exptime == exptime][:1]
        reference = master if group.arm == "VIS" else (selected_refs[0].image if selected_refs else None)
        if group.arm == "NIR":
            matching = [f for f in refs if f.exptime == exptime]
            if not matching:
                group.notes.add(f"DIT={exptime:g}s: missing matching dark; using raw signal")
            elif len(matching) > 1:
                group.notes.add(f"DIT={exptime:g}s: {len(matching)} darks; using first")
        images = [f.image - reference if reference is not None else f.image for f in flat_frames]
        signal = float(np.mean([np.mean(im) for im in images]))
        calibration = "corrected" if reference is not None else "raw"
        var_single = float(np.var(images[0] - images[1]) / 2) if len(images) >= 2 else None
        gain = signal / var_single if var_single is not None and var_single > 0 else None
        noise = bias_noise if group.arm == "VIS" else (math.sqrt(var_single) if var_single is not None else None)
        group.points.append({"exptime": exptime, "signal": signal, "calibration": calibration,
                             "cf": gain, "rms_bias_adu": noise,
                             "rms_bias_e": noise * gain if noise is not None and gain is not None else None,
                             "fit_signal": None, "residual": None, "residual_percent": None, "fit_used": False})
        group.used.update(f.path for f in flat_frames + selected_refs)
    for calibration in ("corrected", "raw"):
        points = [p for p in group.points if p["calibration"] == calibration]
        if not points:
            continue
        group.curves[calibration] = fit_points(points, threshold, level)
        if group.arm == "NIR":
            signals = [p["signal"] for p in points if p["signal"] <= threshold]
            if any(b < a for a, b in zip(signals, signals[1:])):
                group.notes.add(f"NIR {calibration}: non-monotonic signal below fit threshold")


def fit_points(points, threshold, level):
    good = [p for p in points if math.isfinite(p["exptime"]) and math.isfinite(p["signal"])
            and p["exptime"] > 0 and 0 < p["signal"] <= threshold]
    result = {"points": points, "nfit": len(good), "slope": None, "intercept": None, "tmax": None}
    if len({p["exptime"] for p in good}) < 2:
        result["reason"] = "fewer than two distinct usable exposure times"
        return result
    try:
        slope, intercept = np.polyfit([p["exptime"] for p in good], [p["signal"] for p in good], 1)
        if not np.isfinite([slope, intercept]).all():
            raise ValueError("non-finite fit coefficients")
    except (ValueError, np.linalg.LinAlgError) as exc:
        result["reason"] = str(exc)
        return result
    result.update(slope=float(slope), intercept=float(intercept))
    good_ids = {id(p) for p in good}
    for point in points:
        predicted = float(slope * point["exptime"] + intercept)
        point.update(fit_signal=predicted, residual=point["signal"] - predicted,
                     residual_percent=(point["signal"] - predicted) / predicted * 100 if predicted else 0.0,
                     fit_used=id(point) in good_ids)
    if slope > 0:
        maximum = float((level - intercept) / slope)
        if math.isfinite(maximum) and maximum > 0:
            result["tmax"] = maximum
            result["extrapolated"] = maximum > max(p["exptime"] for p in points)
        else:
            result["reason"] = "non-positive or non-finite saturation time"
    else:
        result["reason"] = "non-positive slope"
    return result


def print_summary(groups, messages, threshold, level):
    print("\nSOXS detector linearity summary")
    print(f"Native fit threshold: {threshold:g} ADU; native nominal saturation: {level:g} ADU")
    print("Signals and thresholds are normalized by BINX*BINY; maximum times refer to the acquired binning.")
    print("t_max=(nominal saturation-intercept)/slope, in the fit signal system;")
    print("this is an extrapolated saturation estimate, not a measured linearity or safe operating limit.")
    for message in messages:
        print(message)
    for group in sorted(groups, key=lambda g: (g.acquisition, g.arm, g.mode, g.binning)):
        print(f"\n{group.arm} {group.mode} | {group.acquisition} | binning {group.binning[0]}x{group.binning[1]}")
        print(f"  Files: found={group.found}, read={len(group.frames)}, used={len(group.used)}, "
              f"discarded={len(group.discarded)}, unused={group.found - len(group.used) - len(group.discarded)}")
        for note in sorted(group.notes):
            print(f"  {note}")
        for discarded in group.discarded:
            print(f"  Discarded: {discarded}")
        if not group.curves:
            print("  Fit / maximum exposure: unavailable")
        for calibration, curve in group.curves.items():
            print(f"  {calibration}: {len(curve['points'])} points; {curve['nfit']} fit points")
            if curve["slope"] is not None:
                print(f"    S(t)={curve['slope']:.8g}*t + {curve['intercept']:.8g} ADU")
            if curve["tmax"] is None:
                print(f"    Maximum exposure estimate unavailable: {curve.get('reason', 'invalid fit')}")
            else:
                label = "maximum DIT" if group.arm == "NIR" else "maximum exposure"
                print(f"    Estimated {label}: {curve['tmax']:.6g} s at nominal saturation"
                      + ("; beyond measured times" if curve["extrapolated"] else "")
                      + ("; NO calibration" if calibration == "raw" else ""))


def selected_groups(groups, plot_cfg):
    arm = plot_cfg.get("arm", "VIS").upper()
    selected = [g for g in groups if g.arm == arm]
    if selected and plot_cfg.get("selection", "latest") == "latest":
        latest_day = max(g.day for g in selected)
        selected = [g for g in selected if g.day == latest_day]
    return sorted(selected, key=lambda g: (g.acquisition, g.binning))


def plot_groups(groups, figures, threshold):
    for cfg in figures:
        arm = cfg.get("arm", "VIS").upper()
        selected = selected_groups(groups, cfg)
        identities = {(g.acquisition, g.binning) for g in selected}
        modes = cfg.get("mode_order", VIS_MODES if arm == "VIS" else ["NIR"])
        if arm == "VIS":
            fig, axes = plt.subplots(2, 2, figsize=cfg.get("figsize", [11, 8]), sharey=True)
        else:
            fig, axes = plt.subplots(1, 1, figsize=cfg.get("figsize", [8, 5]))
        axes = np.atleast_1d(axes).ravel()
        for ax, mode in zip(axes, modes):
            has_data = False
            for group in selected:
                if group.mode != mode:
                    continue
                for calibration, curve in group.curves.items():
                    points = curve["points"]
                    has_data = True
                    suffix = " (raw)" if calibration == "raw" else ""
                    if len(identities) > 1:
                        suffix += f" {group.acquisition} {group.binning[0]}x{group.binning[1]}"
                    line, = ax.plot([p["exptime"] for p in points], [p["signal"] for p in points],
                                    marker="o", label=f"Measured{suffix}")
                    color = line.get_color()
                    for used, marker, name in ((True, "o", "Fit points"), (False, "x", "Excluded")):
                        subset = [p for p in points if p["fit_used"] == used]
                        if subset:
                            ax.scatter([p["exptime"] for p in subset], [p["signal"] for p in subset],
                                       marker=marker, color=color, label=name)
                    if curve["slope"] is not None:
                        ax.plot([p["exptime"] for p in points], [p["fit_signal"] for p in points],
                                linestyle="--", color=color, label=f"Linear fit{suffix}")
            areas = {g.binning[0] * g.binning[1] for g in selected if g.mode == mode} or {1}
            for area in sorted(areas):
                label = "Fit threshold" + (f" / {area}" if len(areas) > 1 else "")
                ax.axhline(threshold / area, linestyle=":", linewidth=1, label=label)
            ax.set_title(mode if has_data else f"{mode} - no data")
            ax.set_xlabel(cfg.get("x_label", "Exposure time [s]"))
            ax.grid(True)
        for ax in axes[len(modes):]:
            ax.set_visible(False)
        for index in ([0, 2] if arm == "VIS" else [0]):
            label = cfg.get("y_label", "Signal [ADU]")
            axes[index].set_ylabel(label + " (1x1-equivalent)")
        legend = {}
        for ax in axes[:len(modes)]:
            handles, labels = ax.get_legend_handles_labels()
            for handle, label in zip(handles, labels):
                legend.setdefault(label, handle)
        if legend:
            fig.legend(list(legend.values()), list(legend), loc=cfg.get("legend_loc", "lower center"),
                       ncol=cfg.get("legend_ncol", 4))
        fig.suptitle(cfg.get("title", cfg.get("name", f"{arm} Detector Linearity")), y=0.98)
        fig.tight_layout(rect=[0, 0.12, 1, 0.95])
    plt.show()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True, help="qc-monitor YAML configuration")
    args = parser.parse_args(argv)
    try:
        load_libraries()
    except ImportError as exc:
        print(f"Missing library: {exc}. Use an environment with NumPy, Astropy, Matplotlib and PyYAML.", file=sys.stderr)
        return 1
    try:
        path = args.config.expanduser().resolve()
        det, figures, level, threshold = load_config(path)
        if not det.get("enabled", False):
            print("detector_linearity.enabled is false: no analysis requested.")
            return 0
        groups, messages = scan_frames(det, path.parent.parent)
        for group in groups:
            compute_group(group, threshold, level)
        print_summary(groups, messages, threshold, level)
        plot_groups(groups, figures, threshold)
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        print(f"Configuration or analysis error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

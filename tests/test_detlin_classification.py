"""DPR/name consistency and independent three-bias numerical regressions."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from conftest import DAY, rows
from qc_monitor.detector_linearity import (
    validate_frame_classification, load_detector_linearity_data,
    compute_detector_linearity_results,
)
from qc_monitor.main import consolidate_detector_linearity
from qc_monitor.storage import SQLiteStore


@pytest.fixture(scope="module")
def standalone():
    path = Path(__file__).resolve().parents[1] / "utils/analyze_detector_linearity.py"
    spec = importlib.util.spec_from_file_location("standalone_detlin", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.load_libraries()
    return module


@pytest.mark.parametrize("arm,kind", [("VIS", "Bias"), ("VIS", "Normal"), ("NIR", "Dark"), ("NIR", "Normal")])
@pytest.mark.parametrize("value", [None, "", "  ", "LAMP,FLAT", " lamp , flat ", "LAMP,ON", " lamp , off ", "BIAS", "LAMP,ON,OFF"])
def test_dpr_policy(standalone, arm, kind, value):
    header = fits.Header()
    if value is not None:
        header["HIERARCH ESO DPR TYPE"] = value
    normalized = "" if value is None else ",".join(x.strip().upper() for x in value.split(","))
    legacy = normalized in {"", "LAMP,FLAT"}
    expected = "LAMP,OFF" if kind in {"Bias", "Dark"} else "LAMP,ON"
    for validate in [validate_frame_classification, standalone.validate_frame_classification]:
        if legacy or normalized == expected:
            warning = validate(header, arm, kind)
            assert bool(warning) == legacy
        else:
            with pytest.raises(ValueError, match="ESO DPR TYPE=.*expected"):
                validate(header, arm, kind)


@pytest.mark.parametrize("kind,exp_type,valid", [("Bias", " Bias ", True), ("Normal", "normal", True),
    ("Bias", "Normal", False), ("Normal", "Bias", False), ("Bias", "", False), ("Bias", None, True)])
def test_detector_type_consistency(standalone, kind, exp_type, valid):
    header = {"ESO DPR TYPE": "LAMP,OFF" if kind == "Bias" else "LAMP,ON"}
    if exp_type is not None:
        header["ESO DET EXP TYPE"] = exp_type
    for validate in [validate_frame_classification, standalone.validate_frame_classification]:
        if valid:
            assert validate(header, "VIS", kind) is None
        else:
            with pytest.raises(ValueError, match="ESO DET EXP TYPE"):
                validate(header, "VIS", kind)


def edit(path, key, value):
    with fits.open(path, mode="update") as hdul:
        if value is None:
            del hdul[0].header[key]
        else:
            hdul[0].header["HIERARCH " + key if key.startswith("ESO ") else key] = value


@pytest.mark.parametrize("arm", ["VIS", "NIR"])
@pytest.mark.parametrize("fallback", [False, True])
def test_mismatch_blocks_commit_and_script_discards(lab, standalone, arm, fallback):
    lab.detlin(arm=arm)
    target = next(lab.raw.glob("*BIAS*" if arm == "VIS" else "*DARK*"))
    edit(target, "ESO DPR TYPE", "LAMP,ON")
    if fallback:
        edit(target, f"ESO OCS DET{2 if arm == 'VIS' else 1} IMGNAME", None)
        lab.cfg["detector_linearity"]["arms"][arm]["allow_filename_fallback"] = True
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, "SELECT * FROM processed_detector_linearity_obs_days") == []
    assert rows(lab.db, "SELECT * FROM detector_linearity_results") == []
    groups, _ = standalone.scan_frames(lab.cfg["detector_linearity"], lab.raw)
    discarded = [msg for group in groups for msg in group.discarded]
    assert any(str(target) in msg and "expected LAMP,OFF" in msg for msg in discarded)
    assert all(frame.path != target for group in groups for frame in group.frames)


@pytest.mark.parametrize("count", [2, 3, 4])
def test_monitor_requires_exactly_three(lab, count):
    lab.detlin()
    if count == 2:
        next(lab.raw.glob("*SHG_BIAS*0003.fits")).unlink()
    elif count == 4:
        path = lab.detlin_frame("VIS", "SHG", "bias", 0, 4, 10.)
        edit(path, "ESO TPL START", DAY + "T08:00:00")
    _, results = load_detector_linearity_data(lab.cfg)
    assert ("SHG" in set(results.detector_mode)) == (count == 3)
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert bool(rows(lab.db, "SELECT * FROM processed_detector_linearity_obs_days")) == (count == 3)


def test_three_bias_numerics_and_script_parity(lab, standalone):
    lab.detlin(times=(1, 2, 3))
    # Third bias differs in DC level: excluding it would give an incorrect signal.
    lab.detlin_frame("VIS", "SHG", "bias", 0, 3, 40.)
    measurements, results = load_detector_linearity_data(lab.cfg)
    selected = results[results.detector_mode == "SHG"].sort_values("exptime")
    assert selected.mean_bias_roi.to_numpy() == pytest.approx([20.] * 3)
    # Pair pattern variances are 1,4,1: sqrt((1+4+1)/6) = 1 ADU.
    assert selected.rms_bias_adu.to_numpy() == pytest.approx([1.] * 3)
    assert selected.signal.to_numpy() == pytest.approx([90., 190., 290.])
    assert selected.cf.to_numpy() == pytest.approx([180., 380., 580.])
    assert selected.slope.to_numpy() == pytest.approx([100.] * 3)
    assert selected.intercept.to_numpy() == pytest.approx([-10.] * 3)
    cache = {p.name: fits.getdata(p).astype(float) for p in lab.raw.glob("*.fits")}
    reversed_data = measurements.copy()
    bias_indices = reversed_data.index[reversed_data.frame_type == "Bias"]
    reversed_data.loc[bias_indices, "obs_date_utc"] = list(reversed(reversed_data.loc[bias_indices, "obs_date_utc"].tolist()))
    reordered = compute_detector_linearity_results(reversed_data, cache, 0.6 * 65536)
    assert reordered.signal.to_numpy() == pytest.approx(results.signal.to_numpy())
    assert reordered.rms_bias_adu.to_numpy() == pytest.approx(results.rms_bias_adu.to_numpy())
    bias = [v for k, v in cache.items() if "SHG_BIAS" in k]
    flats = [v for k, v in sorted(cache.items()) if "SHG_UIT1_" in k]
    master = np.mean(bias, axis=0)
    assert (flats[0] - master) - (flats[1] - master) == pytest.approx(flats[0] - flats[1])
    groups, _ = standalone.scan_frames(lab.cfg["detector_linearity"], lab.raw)
    for group in groups:
        standalone.compute_group(group, 0.6 * 65536, 65536)
        expected = results[results.detector_mode == group.mode].sort_values("exptime")
        for key in ["signal", "cf", "rms_bias_adu", "rms_bias_e"]:
            assert [p[key] for p in group.points] == pytest.approx(expected[key].tolist())
        assert group.curves["corrected"]["slope"] == pytest.approx(expected.slope.iloc[0])
        assert group.curves["corrected"]["intercept"] == pytest.approx(expected.intercept.iloc[0], abs=1e-9)


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
def test_script_permissive_bias_counts(lab, standalone, count):
    lab.detlin()
    for path in lab.raw.glob("*SHG_BIAS*"):
        path.unlink()
    for index in range(1, count + 1):
        path = lab.detlin_frame("VIS", "SHG", "bias", 0, index, 10.)
        edit(path, "ESO TPL START", DAY + "T08:00:00")
    groups, _ = standalone.scan_frames(lab.cfg["detector_linearity"], lab.raw)
    group = next(g for g in groups if g.mode == "SHG")
    standalone.compute_group(group, 0.6 * 65536, 65536)
    assert len(group.points) == 2
    assert group.points[0]["signal"] == pytest.approx(100. if count else 110.)
    assert group.points[0]["calibration"] == ("corrected" if count else "raw")
    if count < 2:
        assert group.points[0]["rms_bias_adu"] is None
    else:
        # Mean squared pair spacing / 2 for the synthetic +/-index patterns.
        expected = np.sqrt(np.mean([(i-j)**2 for i in range(1,count+1) for j in range(i+1,count+1)]) / 2)
        assert group.points[0]["rms_bias_adu"] == pytest.approx(expected)
    assert any("Expected 3 biases" in note for note in group.notes) == (count != 3)


@pytest.mark.parametrize("arm", ["VIS", "NIR"])
@pytest.mark.parametrize("legacy", [None, "", "LAMP,FLAT"])
def test_legacy_frames_remain_usable(lab, standalone, caplog, arm, legacy):
    lab.detlin(arm=arm)
    for path in lab.raw.glob("*.fits"):
        edit(path, "ESO DPR TYPE", legacy)
    measurements, results = load_detector_linearity_data(lab.cfg)
    assert len(results) == (8 if arm == "VIS" else 2)
    assert "classification cannot be verified" in caplog.text
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, "SELECT status FROM processed_detector_linearity_obs_days") == [("PROCESSED",)]
    groups, _ = standalone.scan_frames(lab.cfg["detector_linearity"], lab.raw)
    for group in groups:
        assert not group.discarded
        assert any("classification cannot be verified" in note for note in group.notes)
        standalone.compute_group(group, 0.6 * 65536, 65536)
        expected = results[results.detector_mode == group.mode].sort_values("exptime")
        assert [p["signal"] for p in group.points] == pytest.approx(expected.signal.tolist())


def test_standalone_imports_without_project(tmp_path, standalone):
    import shutil
    import subprocess
    copied = tmp_path / "analyze.py"
    shutil.copyfile(standalone.__file__, copied)
    # An isolated interpreter can import and show help without the package/project.
    result = subprocess.run([sys.executable, "-I", str(copied), "--help"],
                            cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "--config" in result.stdout


def test_vis_detector_mismatch_blocks_day(lab, standalone):
    lab.detlin()
    target = next(lab.raw.glob("*BIAS*"))
    edit(target, "ESO DET EXP TYPE", "Normal")
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, "SELECT * FROM processed_detector_linearity_obs_days") == []
    groups, _ = standalone.scan_frames(lab.cfg["detector_linearity"], lab.raw)
    assert any("ESO DET EXP TYPE='Normal'; expected Bias" in msg
               for group in groups for msg in group.discarded)


def test_validation_precedes_pixel_use(lab, monkeypatch):
    import qc_monitor.detector_linearity as detlin
    lab.detlin()
    target = next(lab.raw.glob("*BIAS*"))
    edit(target, "ESO DPR TYPE", "LAMP,ON")
    def forbidden(*args, **kwargs):
        pytest.fail("Pixels read before rejecting contradictory classification")
    monkeypatch.setattr(detlin, "_read_roi", forbidden)
    with pytest.raises(ValueError, match="expected LAMP,OFF"):
        detlin._measure_frame(target, detlin._parse_detlin_name(target.name),
                              target.name, "test", (0, 2, 0, 2), "mean")

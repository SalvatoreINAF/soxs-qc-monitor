"""P0-B: selected inputs must succeed before a family/day can be closed."""
import math
import sqlite3
from contextlib import closing

import numpy as np
import pytest

from qc_monitor.acquisition import (
    TABLE_COLUMNS, load_qc_from_session_db, load_dispersion_solution_tables,
    load_order_location_models, load_order_location_meta,
)
from qc_monitor.detector_linearity import load_detector_linearity_data
from qc_monitor.main import (
    consolidate, consolidate_dispersion_solution, consolidate_order_location_models,
    consolidate_detector_linearity,
)
from qc_monitor.storage import SQLiteStore
from conftest import DAY, REGISTERS, database_snapshot, require, rows


def dsol_run(lab, store):
    return consolidate_dispersion_solution(lab.reduced, store)


def oloc_run(lab, store):
    return consolidate_order_location_models(lab.reduced, store)


def detlin_run(lab, store):
    return consolidate_detector_linearity(lab.cfg, store)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: corrupt selected DSOL product closes the day")
def test_dsol_corrupt_required_product_keeps_day_open(lab):
    valid = lab.dsol()
    lab.dsol("090000", broken=True)
    require(len(load_dispersion_solution_tables([valid])) == 2, "Invalid nominal DSOL fixture")
    store = SQLiteStore(lab.db)
    dsol_run(lab, store)
    assert rows(lab.db, 'SELECT * FROM processed_dispersion_obs_days') == [], "P0-B: corrupt DSOL closed day"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: premature DSOL closure skips repaired input")
def test_dsol_retry_repairs_day_without_duplicates(lab):
    lab.dsol()
    lab.dsol("090000", broken=True)
    store = SQLiteStore(lab.db)
    dsol_run(lab, store)
    lab.dsol("090000")
    dsol_run(lab, store)
    assert rows(lab.db, 'SELECT count(*) FROM dispersion_solution_lines') == [(4,)]
    assert rows(lab.db, 'SELECT count(*) FROM dispersion_resolution_stats') == [(2,)]
    assert rows(lab.db, 'SELECT obs_day, status FROM processed_dispersion_obs_days') == [(DAY, "PROCESSED")]
    before = database_snapshot(lab.db)
    assert dsol_run(lab, store) == 0
    assert database_snapshot(lab.db) == before


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: DSOL closes without required resolution statistics")
def test_dsol_missing_required_statistics_keeps_day_open(lab):
    path = lab.dsol(stats=False)
    require(len(load_dispersion_solution_tables([path])) == 2, "DSOL must remain readable")
    store = SQLiteStore(lab.db)
    dsol_run(lab, store)
    assert rows(lab.db, 'SELECT * FROM processed_dispersion_obs_days') == [], "P0-B: DSOL without usable R_pin closed day"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: OLOC closes without the required metadata HDU")
def test_oloc_missing_metadata_keeps_day_open(lab):
    path = lab.oloc(meta=False)
    require(len(load_order_location_models([path])) == 1, "Invalid nominal OLOC model fixture")
    require(load_order_location_meta([path]).empty, "Missing OLOC HDU should return empty metadata")
    store = SQLiteStore(lab.db)
    oloc_run(lab, store)
    assert rows(lab.db, 'SELECT * FROM processed_order_location_obs_days') == [], "P0-B: missing OLOC HDU closed day"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: premature OLOC closure skips repaired metadata")
def test_oloc_retry_repairs_day_without_duplicates(lab):
    lab.oloc(meta=False)
    store = SQLiteStore(lab.db)
    oloc_run(lab, store)
    lab.oloc(meta=True)
    oloc_run(lab, store)
    assert rows(lab.db, 'SELECT count(*), cent_00 FROM order_location_models') == [(1, 2.0)]
    assert rows(lab.db, 'SELECT count(*), "order" FROM order_location_meta') == [(1, 10)]
    assert rows(lab.db, 'SELECT obs_day, status FROM processed_order_location_obs_days') == [(DAY, "PROCESSED")]
    before = database_snapshot(lab.db)
    assert oloc_run(lab, store) == 0
    assert database_snapshot(lab.db) == before


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: present modes conceal a failed DETLIN pair")
def test_detlin_present_modes_with_failed_pair_keep_day_open(lab, failure):
    lab.detlin(times=(1, 2, 3))
    path = lab.raw / "SOXS_GEN_FLAT_VIS_DETLIN_SHG_UIT3_278_0002.fits"
    if failure == "missing":
        path.unlink()
    else:
        path.write_bytes(b"not a FITS file")
    _, results = load_detector_linearity_data(lab.cfg)
    require(set(results.detector_mode) == {"SHG", "FLG", "SLG", "FHG"}, "All VIS modes must be present")
    require(len(results[results.detector_mode == "SHG"]) == 2, "SHG partial pair fixture is invalid")
    store = SQLiteStore(lab.db)
    detlin_run(lab, store)
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == [], "P0-B: modes concealed a failed exposure pair"


@pytest.mark.parametrize("arm", ["VIS", "NIR"])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: DETLIN closes with an unavailable fit")
def test_detlin_unavailable_fit_keeps_day_open(lab, arm):
    lab.detlin(arm=arm, times=(1,))
    _, results = load_detector_linearity_data(lab.cfg)
    require(not results.empty and (results.fit_used == 0).all(), "Fixture must have results but no fit")
    store = SQLiteStore(lab.db)
    detlin_run(lab, store)
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == [], "P0-B: unavailable fit closed day"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: premature DETLIN closure skips repaired input and refreshed fit")
def test_detlin_retry_replaces_all_coefficients(lab):
    lab.detlin(times=(1, 2, 3))
    # SHG third time is selected but one of its two required FITS is corrupt.
    broken = lab.raw / "SOXS_GEN_FLAT_VIS_DETLIN_SHG_UIT3_278_0002.fits"
    broken.write_bytes(b"not a FITS file")
    # Keep the first surviving flat at a signal that changes the repaired fit.
    lab.detlin_frame("VIS", "SHG", "flat", 3, 1, 370.0)
    store = SQLiteStore(lab.db)
    detlin_run(lab, store)
    lab.detlin_frame("VIS", "SHG", "flat", 3, 2, 370.0)
    _, expected = load_detector_linearity_data(lab.cfg, force=True)
    require(len(expected) == 12, "Repaired sequence must have three results per VIS mode")
    expected_shg = expected[expected.detector_mode == "SHG"]
    require(not np.isclose(expected_shg.slope.iloc[0], 100.0), "Repaired fit must change")
    detlin_run(lab, store)
    actual = rows(lab.db, 'SELECT detector_mode, exptime, slope, intercept FROM detector_linearity_results ORDER BY detector_mode, exptime')
    for mode, time, slope, intercept in actual:
        target = expected[(expected.detector_mode == mode) & (expected.exptime == time)].iloc[0]
        assert slope == pytest.approx(target.slope, rel=1e-10, abs=1e-8), "P0-B: retry retained the previous fit slope"
        assert intercept == pytest.approx(target.intercept, rel=1e-10, abs=1e-8), "P0-B: retry retained the previous fit intercept"
    assert len(actual) == 12, "P0-B: retry skipped the repaired exposure"
    assert rows(lab.db, 'SELECT count(*) FROM detector_linearity_measurements') == [(32,)]
    assert rows(lab.db, 'SELECT obs_day, arm, status FROM processed_detector_linearity_obs_days') == [(DAY, "VIS", "PROCESSED")]
    before = database_snapshot(lab.db)
    assert detlin_run(lab, store) == 0
    assert database_snapshot(lab.db) == before


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-B: first upstream DB closes the day before the second source")
def test_qc_multiple_sources_same_day_are_all_ingested(lab):
    lab.upstream.unlink()
    lab.make_upstream(lab.upstream.parent / "a" / "soxspipe.db", "metric_a")
    lab.make_upstream(lab.upstream.parent / "b" / "soxspipe.db", "metric_b")
    lab.cfg["acquisition"].update(upstream_database_search="recursive", allow_multiple_upstream_databases=True)
    lab.save_config()
    lab.cli("--no-plots")
    assert rows(lab.db, 'SELECT qc_name FROM qc_metrics ORDER BY qc_name') == [("metric_a",), ("metric_b",)], "P0-B: first source closed day before second source"
    assert rows(lab.db, 'SELECT obs_day, status FROM processed_obs_days') == [(DAY, "PROCESSED")]
    before = database_snapshot(lab.db)
    lab.cli("--no-plots")
    assert database_snapshot(lab.db) == before


def test_upstream_read_error_returns_schema_without_closing_day(lab):
    with closing(sqlite3.connect(lab.upstream)) as conn:
        conn.execute('DROP TABLE quality_control_plus_lite')
        conn.commit()
    frame = load_qc_from_session_db(lab.upstream, lab.cfg)
    assert frame.empty
    assert list(frame.columns) == TABLE_COLUMNS
    assert consolidate(lab.upstream, lab.config) == 0
    assert rows(lab.db, 'SELECT * FROM processed_obs_days') == []
    # A failed QC read must not certify or prevent an independent family.
    lab.dsol()
    lab.cli("--no-plots")
    assert rows(lab.db, 'SELECT * FROM processed_obs_days') == []
    assert rows(lab.db, 'SELECT obs_day FROM processed_dispersion_obs_days') == [(DAY,)]


@pytest.mark.parametrize("family", ["qc", "dsol", "oloc", "vis", "nir"])
def test_valid_family_closes_only_its_register_and_skips_second_run(lab, family):
    # Malformed FITS outside selection must not affect completion.
    (lab.products / "unrelated.fits").write_bytes(b"unrelated corrupt file")
    (lab.raw / "unrelated.fits").write_bytes(b"unrelated corrupt file")
    store = SQLiteStore(lab.db)
    if family == "qc":
        run = lambda: consolidate(lab.upstream, lab.config)
        register, table, count = REGISTERS[0], "qc_metrics", 1
    elif family == "dsol":
        lab.dsol()
        run = lambda: dsol_run(lab, store)
        register, table, count = REGISTERS[1], "dispersion_solution_lines", 2
    elif family == "oloc":
        lab.oloc()
        run = lambda: oloc_run(lab, store)
        register, table, count = REGISTERS[2], "order_location_models", 1
    else:
        lab.detlin(arm=family.upper())
        run = lambda: detlin_run(lab, store)
        register, table, count = REGISTERS[3], "detector_linearity_results", 8 if family == "vis" else 2
    assert run() > 0
    assert rows(lab.db, f'SELECT count(*) FROM {table}') == [(count,)]
    assert rows(lab.db, f'SELECT obs_day, status FROM {register}') == [(DAY, "PROCESSED")]
    for other in REGISTERS:
        if other != register:
            assert rows(lab.db, f'SELECT * FROM {other}') == []
    if family == "dsol":
        assert rows(lab.db, 'SELECT mean_R_pin, std_R_pin, n_points FROM dispersion_resolution_stats')[0] == pytest.approx((1100.0, math.sqrt(20000), 2), rel=1e-10, abs=1e-8)
    if family in ("vis", "nir"):
        assert rows(lab.db, 'SELECT DISTINCT slope, intercept FROM detector_linearity_results')[0] == pytest.approx((100.0, 0.0), rel=1e-10, abs=1e-8)
        assert rows(lab.db, 'SELECT DISTINCT arm FROM processed_detector_linearity_obs_days') == [(family.upper(),)]
    before = database_snapshot(lab.db)
    assert run() == 0
    assert database_snapshot(lab.db) == before

"""H2: complete units, truthful acquisition evidence and transactional recovery."""
from contextlib import closing
import shutil
import sqlite3

from astropy.io import fits
from astropy.table import Table
import numpy as np
import pytest

from qc_monitor.acquisition import _load_qc_batch, load_qc_from_session_db
from qc_monitor.main import (
    ConfigurationError, consolidate, consolidate_dispersion_solution,
    consolidate_order_location_models, consolidate_detector_linearity,
)
from qc_monitor.storage import SQLiteStore
from conftest import DAY, REGISTERS, database_snapshot, rows, tree_snapshot


def execute(path, sql, args=()):
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(sql, args)
        conn.commit()


def edit_header(path, **values):
    with fits.open(path, mode="update") as hdus:
        for key, value in values.items():
            if value is None:
                del hdus[0].header[key]
            else:
                hdus[0].header[key] = value


def setup_family(lab, family):
    store = SQLiteStore(lab.db)
    if family == "qc":
        return store, lambda force=False, dry=False: consolidate(lab.upstream, lab.config, force=force, dry_run=dry), REGISTERS[0]
    if family == "dsol":
        lab.dsol()
        return store, lambda force=False, dry=False: consolidate_dispersion_solution(lab.reduced, store, force=force, dry_run=dry), REGISTERS[1]
    if family == "oloc":
        lab.oloc()
        return store, lambda force=False, dry=False: consolidate_order_location_models(lab.reduced, store, force=force, dry_run=dry), REGISTERS[2]
    lab.detlin()
    return store, lambda force=False, dry=False: consolidate_detector_linearity(lab.cfg, store, force=force, dry_run=dry), REGISTERS[3]


@pytest.mark.parametrize("column, value", [
    ("qc_value", "bad"), ("qc_value", float("inf")),
    ("eso seq arm", "unknown"), ("qc_name", ""), ("obs_date_utc", ""),
])
def test_invalid_qc_row_keeps_valid_day_open_and_recovers(lab, column, value):
    execute(lab.upstream, 'INSERT INTO quality_control_plus_lite SELECT * FROM quality_control_plus_lite')
    execute(lab.upstream, f'UPDATE quality_control_plus_lite SET "{column}" = ? WHERE rowid = 2', (value,))
    assert len(load_qc_from_session_db(lab.upstream, lab.cfg)) == 1
    assert consolidate(lab.upstream, lab.config) == 1
    assert rows(lab.db, 'SELECT * FROM qc_metrics') == []
    assert rows(lab.db, 'SELECT * FROM processed_obs_days') == []
    execute(lab.upstream, 'DELETE FROM quality_control_plus_lite WHERE rowid = 2')
    assert consolidate(lab.upstream, lab.config) == 1
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(1,)]
    assert rows(lab.db, 'SELECT obs_day FROM processed_obs_days') == [(DAY,)]


@pytest.mark.parametrize("conflict", [False, True])
def test_nullable_qc_identity_duplicates_are_explicit(lab, conflict):
    execute(lab.upstream, 'UPDATE quality_control_plus_lite SET file = NULL')
    execute(lab.upstream, 'INSERT INTO quality_control_plus_lite SELECT * FROM quality_control_plus_lite')
    if conflict:
        execute(lab.upstream, 'UPDATE quality_control_plus_lite SET qc_value = 200 WHERE rowid = 2')
    assert consolidate(lab.upstream, lab.config) == 2  # selected, not persisted
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(0 if conflict else 1,)]
    assert rows(lab.db, 'SELECT count(*) FROM processed_obs_days') == [(0 if conflict else 1,)]


def configure_multiple(lab):
    lab.upstream.unlink()
    a = lab.make_upstream(lab.upstream.parent / "a" / "soxspipe.db", "a")
    b = lab.make_upstream(lab.upstream.parent / "b" / "soxspipe.db", "b")
    lab.cfg["acquisition"].update(upstream_database_search="recursive", allow_multiple_upstream_databases=True)
    lab.save_config()
    return a, b


@pytest.mark.parametrize("source_state", ["empty", "failed"])
def test_empty_source_differs_from_failed_source_and_other_family_proceeds(lab, source_state):
    a, b = configure_multiple(lab)
    if source_state == "empty":
        execute(b, 'DELETE FROM quality_control_plus_lite')
    else:
        execute(b, 'DROP TABLE quality_control_plus_lite')
    batch = _load_qc_batch(b, lab.cfg)
    assert batch.frames["metrics"].empty
    assert batch.outcomes[0].state == ("acquired" if source_state == "empty" else "failed")
    lab.dsol()
    lab.cli("--no-plots", expected=1 if source_state == "failed" else 0)
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(1 if source_state == "empty" else 0,)]
    assert rows(lab.db, 'SELECT count(*) FROM processed_obs_days') == [(1 if source_state == "empty" else 0,)]
    assert rows(lab.db, 'SELECT obs_day FROM processed_dispersion_obs_days') == [(DAY,)]


def test_api_acquires_configured_sources_once_and_checks_membership(lab):
    a, b = configure_multiple(lab)
    outside = lab.make_upstream(lab.root / "outside.db", "outside")
    before = tree_snapshot(lab.root)
    with pytest.raises(ConfigurationError, match="outside configured sources"):
        consolidate(outside, lab.config)
    assert tree_snapshot(lab.root) == before
    assert consolidate(a, lab.config) == 2
    assert rows(lab.db, 'SELECT qc_name FROM qc_metrics ORDER BY qc_name') == [("a",), ("b",)]
    before = database_snapshot(lab.db)
    assert consolidate(b, lab.config) == 0
    assert database_snapshot(lab.db) == before


def test_api_multisource_dry_run_checks_all_wal_headers_before_store(lab):
    a, b = configure_multiple(lab)
    with closing(sqlite3.connect(b)) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
    before = tree_snapshot(lab.root)
    from qc_monitor.storage import ReadOnlyStorageError
    with pytest.raises(ReadOnlyStorageError, match="WAL"):
        consolidate(a, lab.config, dry_run=True)
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize("usable_second_order", [False, True])
def test_dsol_every_order_needs_statistics_but_individual_samples_can_be_discarded(lab, usable_second_order):
    path = lab.dsol()
    table = Table({"order": [10, 10, 11, 11], "wavelength": [500., 501., 502., 503.],
                   "detector_x": [1., 2., 3., 4.], "detector_y": [3., 4., 5., 6.],
                   "R_pin": [1000., np.inf, 1200. if usable_second_order else np.nan, np.nan]})
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU(table)]).writeto(path, overwrite=True)
    store = SQLiteStore(lab.db)
    consolidate_dispersion_solution(lab.reduced, store)
    assert rows(lab.db, 'SELECT count(*) FROM processed_dispersion_obs_days') == [(int(usable_second_order),)]
    if usable_second_order:
        assert rows(lab.db, 'SELECT mean_R_pin, n_points FROM dispersion_resolution_stats ORDER BY "order"') == [(1000., 1), (1200., 1)]
    else:
        assert rows(lab.db, 'SELECT * FROM dispersion_solution_lines') == []


@pytest.mark.parametrize("damage", ["coefficient", "geometry", "empty-meta", "missing-degree"])
def test_oloc_invalid_required_data_keeps_unit_open(lab, damage):
    path = lab.oloc()
    with fits.open(path, mode="update") as hdus:
        if damage == "coefficient":
            hdus[1].data["cent_00"][0] = np.nan
        elif damage == "geometry":
            hdus[2].data["xmin"][0] = 99.
        elif damage == "missing-degree":
            hdus[1] = fits.BinTableHDU(Table({"cent_00": [2.]}))
        else:
            hdus[2] = fits.BinTableHDU(Table({"order": np.array([], dtype=int)}))
    store = SQLiteStore(lab.db)
    consolidate_order_location_models(lab.reduced, store)
    assert rows(lab.db, 'SELECT * FROM processed_order_location_obs_days') == []
    assert rows(lab.db, 'SELECT * FROM order_location_models') == []


@pytest.mark.parametrize("damage", ["missing-start", "blank-start", "missing-id", "missing-nexp", "missing-expno", "duplicate-index", "wrong-nexp", "bad-nexp", "cross-day", "nonfinite"])
def test_detlin_invalid_metadata_or_measurement_keeps_day_open(lab, damage):
    lab.detlin()
    path = sorted(lab.raw.glob("*.fits"))[0]
    key = {"missing-start": "ESO TPL START", "missing-id": "ESO TPL ID",
           "missing-nexp": "ESO TPL NEXP", "missing-expno": "ESO TPL EXPNO"}.get(damage)
    if damage == "blank-start":
        edit_header(path, **{"ESO TPL START": " "})
    elif key:
        edit_header(path, **{key: None})
    elif damage == "duplicate-index":
        other = sorted(lab.raw.glob("*.fits"))[1]
        edit_header(path, **{"ESO TPL EXPNO": fits.getheader(other)["ESO TPL EXPNO"]})
    elif damage == "wrong-nexp":
        edit_header(path, **{"ESO TPL NEXP": 999})
    elif damage == "bad-nexp":
        edit_header(path, **{"ESO TPL NEXP": "bad"})
    elif damage == "cross-day":
        edit_header(path, **{"DATE-OBS": "2026-10-06T00:00:01"})
    else:
        with fits.open(path, mode="update") as hdus:
            hdus[0].data[0, 0] = np.nan
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == []
    assert rows(lab.db, 'SELECT * FROM detector_linearity_results') == []


def test_detlin_multiple_sequences_are_rejected_without_mixing(lab):
    lab.detlin()
    other_root = lab.raw / "second"
    other_root.mkdir()
    for original in lab.raw.glob("*.fits"):
        copy = other_root / original.name
        shutil.copyfile(original, copy)
        edit_header(copy, **{"ESO TPL START": DAY + "T10:00:00"})
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == []
    assert rows(lab.db, 'SELECT * FROM detector_linearity_results') == []


def test_nir_missing_pair_blocks_closure_even_with_a_fit(lab):
    lab.detlin(arm="NIR", times=(1, 2, 3))
    (lab.raw / 'SOXS_GEN_FLAT_NIR_DETLIN_DIT3_278_0002.fits').unlink()
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == []


def test_detlin_saturated_exposure_is_retained_when_fit_available(lab):
    lab.detlin(times=(1, 2, 3))
    for index in (1, 2):
        lab.detlin_frame("VIS", "SHG", "flat", 3, index, 50010.)
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT signal, fit_used FROM detector_linearity_results WHERE detector_mode = "SHG" AND exptime = 3') == [(50000., 0)]
    assert rows(lab.db, 'SELECT obs_day FROM processed_detector_linearity_obs_days') == [(DAY,)]


def corrupt_family(lab, family):
    if family == "qc":
        execute(lab.upstream, 'UPDATE quality_control_plus_lite SET qc_value = "bad"')
    elif family == "dsol":
        lab.dsol("090000", broken=True)
    elif family == "oloc":
        lab.oloc(meta=False)
    else:
        (lab.raw / "SOXS_GEN_FLAT_VIS_DETLIN_SHG_UIT2_278_0002.fits").write_bytes(b"not FITS")


@pytest.mark.parametrize("family", ["qc", "dsol", "oloc", "detlin"])
def test_forced_incomplete_attempt_preserves_previously_closed_unit(lab, family):
    store, run, register = setup_family(lab, family)
    run()
    assert rows(lab.db, f'SELECT obs_day FROM {register}') == [(DAY,)]
    before = database_snapshot(lab.db)
    corrupt_family(lab, family)
    run(force=True)
    assert database_snapshot(lab.db) == before


@pytest.mark.parametrize("family", ["qc", "dsol", "oloc", "detlin"])
def test_incomplete_attempt_preserves_legacy_partial_data_then_replaces_it(lab, family):
    store, run, register = setup_family(lab, family)
    run()
    execute(lab.db, f'DELETE FROM {register}')
    before = database_snapshot(lab.db)
    corrupt_family(lab, family)
    run()
    assert database_snapshot(lab.db) == before
    if family == "qc":
        execute(lab.upstream, 'UPDATE quality_control_plus_lite SET qc_value = 200')
    elif family == "dsol":
        lab.dsol("090000")
    elif family == "oloc":
        lab.oloc()
    else:
        lab.detlin_frame("VIS", "SHG", "flat", 2, 2, 210.)
    run()
    assert rows(lab.db, f'SELECT obs_day FROM {register}') == [(DAY,)]
    if family == "qc":
        assert rows(lab.db, 'SELECT count(*), qc_value FROM qc_metrics') == [(1, 200.)]
    before = database_snapshot(lab.db)
    assert run() == 0
    assert database_snapshot(lab.db) == before


@pytest.mark.parametrize("family", ["qc", "dsol", "oloc", "detlin"])
def test_sql_failure_at_registration_rolls_back_the_whole_unit(lab, family):
    store, run, register = setup_family(lab, family)
    run()
    execute(lab.db, f'CREATE TRIGGER fail_registration BEFORE INSERT ON {register} BEGIN SELECT RAISE(ABORT, "controlled registration failure"); END')
    before = database_snapshot(lab.db)
    with pytest.raises(sqlite3.IntegrityError, match="controlled registration failure"):
        run(force=True)
    assert database_snapshot(lab.db) == before
    execute(lab.db, 'DROP TRIGGER fail_registration')
    run(force=True)
    assert rows(lab.db, f'SELECT obs_day FROM {register}') == [(DAY,)]


def test_invalid_qc_day_does_not_block_other_known_day(lab):
    execute(lab.upstream, 'INSERT INTO quality_control_plus_lite SELECT * FROM quality_control_plus_lite')
    execute(lab.upstream, 'UPDATE quality_control_plus_lite SET "night start date" = "2026-10-06", obs_date_utc = "2026-10-06T08:00:00", qc_value = "bad" WHERE rowid = 2')
    assert consolidate(lab.upstream, lab.config) == 1
    assert rows(lab.db, 'SELECT obs_day FROM processed_obs_days') == [(DAY,)]


def test_malformed_selected_dsol_filename_is_failure_not_crash(lab):
    lab.dsol()
    (lab.products / 'broken_VIS_DSOL_PINHOLE_SOXS_FITTED_LINES.fits').write_bytes(b"not FITS")
    store = SQLiteStore(lab.db)
    consolidate_dispersion_solution(lab.reduced, store)
    assert rows(lab.db, 'SELECT * FROM processed_dispersion_obs_days') == []


def test_incomplete_dry_run_applies_validation_without_writes(lab, caplog):
    lab.dsol()
    lab.dsol("090000", broken=True)
    store = SQLiteStore(lab.db, read_only=True)
    before = tree_snapshot(lab.root)
    consolidate_dispersion_solution(lab.reduced, store, dry_run=True)
    assert "remains open" in caplog.text
    assert tree_snapshot(lab.root) == before


def test_nir_orphan_dark_is_incomplete_even_with_consistent_exposure_count(lab):
    lab.detlin(arm="NIR", times=(1, 2, 3))
    for index in (1, 2):
        (lab.raw / f"SOXS_GEN_FLAT_NIR_DETLIN_DIT3_278_{index:04d}.fits").unlink()
    paths = sorted(lab.raw.glob("*.fits"))
    for number, path in enumerate(paths, 1):
        edit_header(path, **{"ESO TPL NEXP": len(paths), "ESO TPL EXPNO": number})
    consolidate_detector_linearity(lab.cfg, SQLiteStore(lab.db))
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == []


@pytest.mark.parametrize("failed", [False, True])
def test_empty_qc_does_not_require_unused_registers(lab, failed):
    lab.seed()
    execute(lab.db, 'DROP TABLE processed_obs_days')
    execute(lab.upstream, 'DROP TABLE quality_control_plus_lite' if failed else 'DELETE FROM quality_control_plus_lite')
    before = tree_snapshot(lab.root)
    assert consolidate(lab.upstream, lab.config, dry_run=True) == 0
    assert tree_snapshot(lab.root) == before


def test_oloc_numeric_text_geometry_is_compared_numerically(lab):
    path = lab.oloc()
    with fits.open(path, mode="update") as hdus:
        hdus[2] = fits.BinTableHDU(Table({"order": ["10"], "xmin": ["10"], "xmax": ["2"], "ymin": ["0"], "ymax": ["3"]}))
    consolidate_order_location_models(lab.reduced, SQLiteStore(lab.db))
    assert rows(lab.db, 'SELECT * FROM processed_order_location_obs_days') == []


def test_declared_huge_exposure_count_does_not_allocate_an_inventory(lab):
    lab.detlin()
    for path in lab.raw.glob("*.fits"):
        edit_header(path, **{"ESO TPL NEXP": 10**12})
    consolidate_detector_linearity(lab.cfg, SQLiteStore(lab.db))
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == []

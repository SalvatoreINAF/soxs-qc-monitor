"""H1: read-only selection, explicit failures and dry-run preflight."""
from contextlib import closing
import os
import sqlite3

import pytest

from qc_monitor.acquisition import load_qc_from_session_db
from qc_monitor.main import consolidate, run_preflight
from qc_monitor.storage import ReadOnlyStorageError, SQLiteStore
from conftest import DAY, database_snapshot, tree_snapshot


@pytest.mark.parametrize("interface", ["cli", "api"])
def test_closed_day_is_skipped_without_writes(lab, interface):
    store = SQLiteStore(lab.db)
    store.register_processed_obs_day(DAY)
    before = tree_snapshot(lab.root)
    if interface == "cli":
        result = lab.cli("--dry-run")
        assert "Total consolidated QC datapoints: 0" in result.stderr
    else:
        assert consolidate(lab.upstream, lab.config, dry_run=True) == 0
    assert tree_snapshot(lab.root) == before


def test_api_force_selects_closed_day_without_writes(lab):
    SQLiteStore(lab.db).register_processed_obs_day(DAY)
    before = tree_snapshot(lab.root)
    assert consolidate(lab.upstream, lab.config, force=True, dry_run=True) == 1
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize("interface", ["cli", "api"])
@pytest.mark.parametrize("damage", ["missing-register", "missing-column", "corrupt"])
def test_invalid_qc_archive_is_explicit_and_unchanged(lab, interface, damage):
    lab.seed()
    if damage == "corrupt":
        lab.db.write_bytes(b"not a SQLite database")
        reason = "not a database"
    else:
        with closing(sqlite3.connect(lab.db)) as conn:
            if damage == "missing-register":
                conn.execute('DROP TABLE processed_obs_days')
                reason = "processed_obs_days"
            else:
                conn.execute('ALTER TABLE processed_obs_days DROP COLUMN status')
                reason = "status"
            conn.commit()
    before = tree_snapshot(lab.root)
    if interface == "cli":
        result = lab.cli("--dry-run", expected=2)
        assert str(lab.db) in result.stderr
        assert reason in result.stderr
        assert "Dry-run storage error" in result.stderr
    else:
        with pytest.raises(ReadOnlyStorageError, match=reason) as caught:
            consolidate(lab.upstream, lab.config, dry_run=True)
        assert str(lab.db) in str(caught.value)
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize("interface", ["cli", "api"])
def test_sqlite_uri_handles_special_characters(lab, interface):
    lab.db = lab.root / "archive ? # %" / "qc ?.sqlite"
    lab.upstream = lab.make_upstream(lab.root / "input ? # %" / "soxspipe.db")
    lab.cfg["paths"].update(qc_database=str(lab.db), upstream_root=str(lab.upstream.parent))
    lab.save_config()
    lab.seed()
    before = tree_snapshot(lab.root)
    if interface == "cli":
        result = lab.cli("--dry-run")
        assert "Total consolidated QC datapoints: 1" in result.stderr
    else:
        assert consolidate(lab.upstream, lab.config, dry_run=True) == 1
    assert tree_snapshot(lab.root) == before


def test_read_only_store_rejects_real_write(lab):
    lab.seed()
    before_sql = database_snapshot(lab.db)
    before = tree_snapshot(lab.root)
    store = SQLiteStore(lab.db, read_only=True)
    # Real SQL through a public writer, not a mocked connection.
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        store.write_metrics(load_qc_from_session_db(lab.upstream, lab.cfg))
    assert database_snapshot(lab.db) == before_sql
    assert tree_snapshot(lab.root) == before


def test_absent_store_returns_all_empty_registers(lab):
    before = tree_snapshot(lab.root)
    store = SQLiteStore(lab.db, read_only=True)
    assert store.get_processed_obs_days() == set()
    assert store.get_processed_dispersion_obs_days() == set()
    assert store.get_processed_order_location_obs_days() == set()
    assert store.get_processed_detector_linearity_obs_days() == set()
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize("getter, register, columns", [
    ("get_processed_obs_days", "processed_obs_days", "obs_day TEXT"),
    ("get_processed_dispersion_obs_days", "processed_dispersion_obs_days", "obs_day TEXT"),
    ("get_processed_order_location_obs_days", "processed_order_location_obs_days", "obs_day TEXT"),
    ("get_processed_detector_linearity_obs_days", "processed_detector_linearity_obs_days", "obs_day TEXT, status TEXT"),
])
def test_each_incompatible_register_fails_without_migration(lab, getter, register, columns):
    lab.seed()
    with closing(sqlite3.connect(lab.db)) as conn:
        conn.execute(f'DROP TABLE {register}')
        conn.execute(f'CREATE TABLE {register} ({columns})')
        conn.commit()
    before = tree_snapshot(lab.root)
    with pytest.raises(ReadOnlyStorageError, match="no such column"):
        getattr(SQLiteStore(lab.db, read_only=True), getter)()
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize("source", ["qc", "upstream"])
@pytest.mark.parametrize("sidecars", [False, True], ids=["no-sidecars", "existing-sidecars"])
@pytest.mark.parametrize("interface", ["cli", "api"])
def test_wal_is_rejected_before_sqlite_creates_or_changes_sidecars(lab, source, sidecars, interface):
    lab.seed()
    path = lab.db if source == "qc" else lab.upstream
    writer = sqlite3.connect(path)
    try:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone() == ("wal",)
        if sidecars:
            # Retain a committed WAL and its index while exercising the reader.
            writer.execute('CREATE TABLE wal_sentinel (value INTEGER)')
            writer.execute('INSERT INTO wal_sentinel VALUES (1)')
            writer.commit()
            assert path.with_name(path.name + "-wal").exists()
            assert path.with_name(path.name + "-shm").exists()
        else:
            writer.close()
            assert not path.with_name(path.name + "-wal").exists()
            assert not path.with_name(path.name + "-shm").exists()
        before = tree_snapshot(lab.root)
        if interface == "cli":
            result = lab.cli("--dry-run", expected=2)
            assert "WAL" in result.stderr and str(path) in result.stderr
        else:
            with pytest.raises(ReadOnlyStorageError, match="WAL") as caught:
                consolidate(lab.upstream, lab.config, dry_run=True)
            assert str(path) in str(caught.value)
        assert tree_snapshot(lab.root) == before
    finally:
        writer.close()


def test_wal_in_later_source_is_checked_before_qc_initialization(lab):
    lab.upstream.unlink()
    lab.make_upstream(lab.upstream.parent / "a" / "soxspipe.db", "a")
    later = lab.make_upstream(lab.upstream.parent / "b" / "soxspipe.db", "b")
    with closing(sqlite3.connect(later)) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
    lab.cfg["acquisition"].update(upstream_database_search="recursive", allow_multiple_upstream_databases=True)
    lab.save_config()
    before = tree_snapshot(lab.root)
    result = lab.cli("--dry-run", expected=2)
    assert str(later) in result.stderr
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize("output_kind", ["missing-template", "invalid-output-types"])
def test_dry_run_preflight_skips_unused_output_resources(lab, output_kind):
    if output_kind == "missing-template":
        lab.cfg["plots"]["template"] = str(lab.root / "missing-template.html")
    else:
        # These are incompatible with publication but irrelevant to acquisition.
        lab.cfg["plots"].update(output_dir=str(lab.upstream), html_output=str(lab.reduced))
    lab.save_config()
    before = tree_snapshot(lab.root)
    assert run_preflight(lab.cfg, lab.root, dry_run=True)
    assert not run_preflight(lab.cfg, lab.root)
    lab.cli("--dry-run")
    assert tree_snapshot(lab.root) == before


def test_dry_run_accepts_readable_inputs_and_unwritable_destinations(lab):
    lab.seed()
    lab.publish_sentinels()
    targets = (lab.db, lab.db.parent, lab.output, lab.output / "plots")
    try:
        for target in targets:
            target.chmod(0o444 if target.is_file() else 0o555)
        if any(os.access(target, os.W_OK) for target in targets):
            pytest.skip("Current privileges bypass filesystem permission restrictions")
        before = tree_snapshot(lab.root)
        assert run_preflight(lab.cfg, lab.root, dry_run=True)
        assert not run_preflight(lab.cfg, lab.root)
        lab.cli("--dry-run")
        assert tree_snapshot(lab.root) == before
    finally:
        for target in targets:
            target.chmod(0o644 if target.is_file() else 0o755)


def test_dry_run_still_rejects_invalid_acquisition_input(lab):
    lab.cfg["paths"]["reduced_root"] = str(lab.root / "missing-reduced")
    lab.save_config()
    before = tree_snapshot(lab.root)
    assert not run_preflight(lab.cfg, lab.root, dry_run=True)
    result = lab.cli("--dry-run", expected=2)
    assert "reduced_root is not an existing directory" in result.stderr
    assert tree_snapshot(lab.root) == before


def test_incompatible_flags_are_rejected_before_config_loading(lab):
    lab.config.unlink()
    before = tree_snapshot(lab.root)
    result = lab.cli("--dry-run", "--rebuild-db", expected=2)
    assert "cannot be used together" in result.stderr
    assert "Configuration error" not in result.stderr
    assert tree_snapshot(lab.root) == before

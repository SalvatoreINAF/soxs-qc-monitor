"""Real SQLite identities, schema compatibility, rebuild recovery and writer leases."""
from contextlib import closing, contextmanager
from pathlib import Path
import os
import sqlite3
import subprocess
import sys

import pytest

from conftest import DAY, database_snapshot, rows, tree_snapshot
from qc_monitor.main import consolidate, consolidate_dispersion_solution, consolidate_order_location_models
from qc_monitor.rebuild import acquisition_store, validate_archive, validate_coverage, RebuildError
from qc_monitor.schema import SCHEMA_VERSION
from qc_monitor.storage import SQLiteStore, SchemaError
from qc_monitor.locking import WriterBusyError, writer_lease
from qc_monitor.acquisition import load_qc_from_session_db


def execute(path, sql, values=()):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(sql, values)


@contextmanager
def external_writer(path):
    program = '''
import sys
from qc_monitor.locking import writer_lease
with writer_lease(sys.argv[1]):
    print('ready', flush=True)
    sys.stdin.read()
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', program, str(path)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'ready'
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=10)


def test_schema_version_and_structural_rejection(lab):
    SQLiteStore(lab.db)
    assert rows(lab.db, 'PRAGMA user_version') == [(SCHEMA_VERSION,)]
    validate_archive(lab.db)
    execute(lab.db, 'DROP INDEX qc_metric_identity')
    before = database_snapshot(lab.db)
    with pytest.raises(SchemaError, match='structure'):
        SQLiteStore(lab.db)
    assert database_snapshot(lab.db) == before


@pytest.mark.parametrize('version', [0, 2])
def test_old_or_unknown_schema_never_auto_migrates(lab, version):
    lab.seed()
    execute(lab.db, f'PRAGMA user_version={version}')
    before = tree_snapshot(lab.root)
    with pytest.raises(SchemaError, match='rebuild'):
        SQLiteStore(lab.db)
    lab.cli('--no-plots', expected=2)
    assert tree_snapshot(lab.root) == before
    if version == 0:
        lab.cli('--dry-run')
        assert tree_snapshot(lab.root) == before


def test_qc_null_identity_is_enforced_in_sql_and_empty_file_is_distinct(lab):
    store = SQLiteStore(lab.db)
    frame = load_qc_from_session_db(lab.upstream, lab.cfg)
    frame['file'] = None
    store.write_metrics(frame)
    before = database_snapshot(lab.db)
    with pytest.raises(sqlite3.IntegrityError):
        store.write_metrics(frame)
    assert database_snapshot(lab.db) == before
    frame['file'] = ''
    store.write_metrics(frame)
    assert rows(lab.db, 'SELECT file FROM qc_metrics ORDER BY id') == [(None,), ('',)]


def test_multisource_qc_deduplication_records_all_origins(lab):
    nested = lab.make_upstream(lab.upstream.parent / 'nested' / 'soxspipe.db')
    lab.cfg['acquisition'].update(upstream_database_search='recursive', allow_multiple_upstream_databases=True)
    lab.save_config()
    assert consolidate(lab.upstream, lab.config) == 2
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(1,)]
    assert {row[0] for row in rows(lab.db, 'SELECT source_path FROM qc_metric_sources')} == {str(lab.upstream), str(nested)}
    before = database_snapshot(lab.db)
    assert consolidate(lab.upstream, lab.config) == 0
    assert database_snapshot(lab.db) == before


@pytest.mark.parametrize('family', ['dsol', 'oloc'])
def test_identical_basenames_in_distinct_directories_are_distinct_products(lab, family):
    import shutil
    file = lab.dsol() if family == 'dsol' else lab.oloc()
    other = file.parent / 'another'
    other.mkdir()
    shutil.copyfile(file, other / file.name)
    store = SQLiteStore(lab.db)
    if family == 'dsol':
        consolidate_dispersion_solution(lab.reduced, store)
        table = 'dispersion_resolution_stats'
    else:
        consolidate_order_location_models(lab.reduced, store)
        table = 'order_location_models'
    assert rows(lab.db, f'SELECT count(DISTINCT filepath) FROM {table}') == [(2,)]


@pytest.mark.parametrize('interface', ['cli', 'api', 'writer'])
def test_competing_writers_rejected_without_writes(lab, interface):
    store = SQLiteStore(lab.db)
    before = tree_snapshot(lab.root)
    with external_writer(lab.db):
        if interface == 'cli':
            assert 'BusyError' in lab.cli('--no-plots', expected=2).stderr
        elif interface == 'api':
            with pytest.raises(WriterBusyError):
                consolidate(lab.upstream, lab.config)
        else:
            with pytest.raises(WriterBusyError):
                store.write_metrics(load_qc_from_session_db(lab.upstream, lab.cfg))
        lab.cli('--dry-run')
        assert tree_snapshot(lab.root) == before
    assert consolidate(lab.upstream, lab.config) == 1  # terminated holder releases lease


def test_reentrant_lease_uses_canonical_path(lab):
    alias = lab.root / 'monitor-alias'
    alias.symlink_to(lab.db.parent, target_is_directory=True)
    with writer_lease(lab.db), writer_lease(alias / lab.db.name):
        store = SQLiteStore(lab.db)
        assert consolidate(lab.upstream, lab.config) == 1
        assert store.get_processed_obs_days() == {DAY}


def test_rebuild_preserves_previous_database_when_historical_source_is_absent(lab):
    lab.seed()
    lab.publish_sentinels()
    before_sql = database_snapshot(lab.db)
    before_artifacts = tree_snapshot(lab.output)
    result = lab.cli('--rebuild-db', expected=2)
    assert 'coverage' in result.stderr
    assert database_snapshot(lab.db) == before_sql
    assert tree_snapshot(lab.output) == before_artifacts
    backups = list(lab.db.parent.glob(lab.db.name + '.backup-*.sqlite'))
    assert len(backups) == 1
    assert database_snapshot(backups[0]) == before_sql
    assert not list(lab.db.parent.glob('.*rebuild-*'))


def restore_seed_source(lab):
    with closing(sqlite3.connect(lab.upstream)) as conn, conn:
        conn.execute('ATTACH DATABASE ? AS seed', (str(lab.root / 'seed.db'),))
        conn.execute('INSERT INTO quality_control_plus_lite SELECT * FROM seed.quality_control_plus_lite')


def test_successful_rebuild_covers_history_and_recovers_legacy_version(lab):
    lab.seed()
    restore_seed_source(lab)
    execute(lab.db, 'PRAGMA user_version=0')
    before_sql = database_snapshot(lab.db)
    lab.cli('--rebuild-db', '--no-plots')
    assert rows(lab.db, 'PRAGMA user_version') == [(SCHEMA_VERSION,)]
    assert rows(lab.db, 'SELECT qc_name FROM qc_metrics ORDER BY qc_name') == [('bias_level',), ('sentinel',)]
    backups = list(lab.db.parent.glob(lab.db.name + '.backup-*.sqlite'))
    assert database_snapshot(backups[0]) == before_sql
    validate_archive(lab.db)


@pytest.mark.parametrize('failure', ['acquisition', 'backup', 'replace'])
def test_rebuild_failures_never_publish_candidate(lab, failure, monkeypatch):
    lab.seed()
    restore_seed_source(lab)
    previous = database_snapshot(lab.db)
    if failure == 'acquisition':
        lab.dsol(broken=True)
        lab.cli('--rebuild-db', '--no-plots', expected=2)
    else:
        import qc_monitor.rebuild as rebuild
        def fail(*args):
            raise OSError('deliberate failure')
        if failure == 'backup':
            monkeypatch.setattr(rebuild, 'backup_archive', fail)
        else:
            monkeypatch.setattr(rebuild.os, 'replace', fail)
        with pytest.raises(OSError):
            with acquisition_store(lab.db, rebuild=True) as store:
                # Full current content ensures replacement is the failing operation.
                from qc_monitor.main import _consolidate_qc_sources
                _consolidate_qc_sources([lab.upstream], lab.cfg, store)
    assert database_snapshot(lab.db) == previous
    assert not list(lab.db.parent.glob('.*rebuild-*'))


def test_candidate_integrity_and_coverage_fail_before_replacement(lab):
    lab.seed()
    previous = database_snapshot(lab.db)
    with pytest.raises(SchemaError):
        with acquisition_store(lab.db, rebuild=True) as candidate:
            execute(candidate.db_path, 'DROP INDEX qc_metric_identity')
    assert database_snapshot(lab.db) == previous
    with pytest.raises(RebuildError, match='coverage'):
        with acquisition_store(lab.db, rebuild=True):
            pass
    assert database_snapshot(lab.db) == previous


def test_rebuild_refuses_unknown_previous_schema_and_products(lab):
    lab.seed()
    restore_seed_source(lab)
    execute(lab.db, 'CREATE TABLE experimental (value REAL)')
    previous = database_snapshot(lab.db)
    lab.cli('--rebuild-db', '--no-plots', expected=2)
    assert database_snapshot(lab.db) == previous


def test_rebuild_backup_includes_committed_wal_but_live_sidecars_block_replace(lab):
    lab.seed()
    restore_seed_source(lab)
    with closing(sqlite3.connect(lab.db)) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
        writer.execute('UPDATE qc_metrics SET qc_value=123')
        writer.commit()
        before = database_snapshot(lab.db)
        result = lab.cli('--rebuild-db', '--no-plots', expected=2)
        assert 'sidecars' in result.stderr
        assert database_snapshot(lab.db) == before
        backup = next(lab.db.parent.glob('qc.sqlite.backup-*.sqlite'))
        assert rows(backup, 'SELECT qc_value FROM qc_metrics') == [(123.,)]
        assert rows(backup, 'PRAGMA integrity_check') == [('ok',)]


def test_closed_unit_coverage_alone_cannot_hide_missing_product(lab):
    lab.seed()
    restore_seed_source(lab)
    # Two independently identified metrics in the same historical unit.
    execute(lab.db, '''INSERT INTO qc_metrics("night start date",obs_date_utc,"eso seq arm",soxspipe_recipe,qc_name,qc_value,qc_order,file)
                       VALUES ('2026-10-01','2026-10-01T09:00:00','VIS','soxs-mbias','lost',99,'-1','lost.fits')''')
    before = database_snapshot(lab.db)
    assert 'missing products' in lab.cli('--rebuild-db', '--no-plots', expected=2).stderr
    assert database_snapshot(lab.db) == before


def test_rebuild_reads_failures_without_touching_new_archive(lab):
    lab.dsol(broken=True)
    lab.cli('--rebuild-db', '--no-plots', expected=2)
    assert not lab.db.exists()
    assert not list(lab.db.parent.glob('.*rebuild-*'))


def test_failed_rebuild_summary_never_claims_candidate_rows_are_published(lab):
    import json
    lab.seed()
    restore_seed_source(lab)
    lab.dsol(broken=True)
    result = lab.cli('--rebuild-db', '--no-plots', expected=2)
    value = json.loads(next(line.split('RUN_SUMMARY ', 1)[1] for line in result.stderr.splitlines() if 'RUN_SUMMARY ' in line))
    assert value['storage']['rebuild_state'] == 'failed'
    qc = value['families']['qc']
    assert qc['completed_units'] == []
    assert qc['tables']['qc_metrics']['persisted'] == 0
    assert qc['tables']['qc_metrics']['staged'] == 2
    assert qc['latest_data_utc'] is None
    assert qc['staged_units']


def test_preflight_rejects_legacy_write_schema_but_rebuild_inspection_is_allowed(lab):
    lab.seed()
    execute(lab.db, 'PRAGMA user_version=0')
    before = tree_snapshot(lab.root)
    lab.cli('--preflight', expected=2)
    lab.cli('--preflight', '--rebuild-db')
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize('damaged_reference', [False, True])
def test_legacy_detector_fit_coverage_requires_original_input_pair(lab, damaged_reference):
    from qc_monitor.main import consolidate_detector_linearity
    lab.detlin()
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    columns = [r[1] for r in rows(lab.db, 'PRAGMA table_info(detector_linearity_results)') if r[1] != 'sequence_id']
    with closing(sqlite3.connect(lab.db)) as conn, conn:
        conn.execute('CREATE TABLE legacy_results AS SELECT ' + ','.join('"'+c+'"' for c in columns) + ' FROM detector_linearity_results')
        conn.execute('DROP TABLE detector_linearity_results')
        conn.execute('ALTER TABLE legacy_results RENAME TO detector_linearity_results')
        conn.execute('PRAGMA user_version=0')
        for number, first, second in conn.execute('SELECT id,file1,file2 FROM detector_linearity_results').fetchall():
            conn.execute('UPDATE detector_linearity_results SET file1=?,file2=? WHERE id=?',
                         ('unknown.fits' if damaged_reference else Path(first).name, Path(second).name, number))
    before = database_snapshot(lab.db)
    lab.cli('--rebuild-db', '--no-plots', expected=2 if damaged_reference else 0)
    if damaged_reference:
        assert database_snapshot(lab.db) == before
    else:
        validate_archive(lab.db)
        assert rows(lab.db, 'SELECT count(*) FROM detector_linearity_results') == [(8,)]

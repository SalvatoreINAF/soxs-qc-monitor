"""D3-A: sequence failures, real SQLite contention and committed counters."""
from contextlib import closing, contextmanager
import json
import logging
import shutil
import sqlite3
import subprocess
import sys
import time

from astropy.io import fits
import pandas as pd
import pytest

from conftest import DAY, database_snapshot, rows, tree_snapshot
import qc_monitor.acquisition as acquisition
import qc_monitor.detector_linearity as detlin
import qc_monitor.main as cli
import qc_monitor.storage as storage
import qc_monitor.rebuild as rebuild
from qc_monitor import _sqlite_retry as retry
from qc_monitor.locking import WriterBusyError
from qc_monitor.run_result import RunResult
from qc_monitor.storage import SQLiteStore, ReadOnlyStorageError


def in_process(lab, monkeypatch, caplog, *flags):
    monkeypatch.setattr(sys, 'argv', ['qc-monitor', '--config', str(lab.config), *flags])
    caplog.set_level(logging.INFO)
    code = cli.main()
    values = [json.loads(record.getMessage().split('RUN_SUMMARY ', 1)[1])
              for record in caplog.records if record.getMessage().startswith('RUN_SUMMARY ')]
    assert values[-1]['exit_code'] == code
    return code, values[-1]


def copy_sequence(lab, other_day=False):
    directory = lab.raw / 'second'
    directory.mkdir()
    day = '2026-10-06' if other_day else DAY
    for original in lab.raw.glob('*.fits'):
        destination = directory / original.name
        shutil.copyfile(original, destination)
        with fits.open(destination, mode='update') as hdus:
            hdus[0].header['ESO TPL START'] = day + 'T10:00:00'
            hdus[0].header['DATE-OBS'] = hdus[0].header['DATE-OBS'].replace(DAY, day).replace('T08:', 'T10:')
    return day


@pytest.mark.parametrize('arm', ['VIS', 'NIR'])
@pytest.mark.parametrize('other_day', [False, True])
def test_fit_failure_isolated_and_repaired_without_duplicates(lab, monkeypatch, caplog, arm, other_day):
    lab.detlin(arm=arm)
    failed_day = copy_sequence(lab, other_day)
    lab.dsol()
    original = detlin.compute_detector_linearity_results
    computed = []

    def fail_late(**kwargs):
        frame = kwargs['df_measurements']
        result = original(**kwargs)
        computed.append(frame.tpl_start.iloc[0])
        if pd.Timestamp(frame.tpl_start.iloc[0]).hour == 10:
            raise ArithmeticError('Induced sequence fit failure')
        return result

    monkeypatch.setattr(detlin, 'compute_detector_linearity_results', fail_late)
    batch = detlin._load_detector_linearity_batch(lab.cfg)
    assert len(computed) == 2
    assert batch.frames['results'].sequence_id.nunique() == 1
    failures = [outcome for outcome in batch.outcomes if outcome.state == 'failed']
    assert len(failures) == 1
    assert failures[0].unit == (failed_day, arm)
    assert failures[0].details['phase'] == 'fit'
    assert failures[0].details['type'] == 'ArithmeticError'
    assert failures[0].details['sequence_id'] == failures[0].source
    code, value = in_process(lab, monkeypatch, caplog, '--no-plots')
    assert code == 1
    family = value['families']['detlin']
    assert family['open_units'] == [[failed_day, arm]]
    assert family['errors'][0]['sequence_id'] == failures[0].source
    assert value['families']['dsol']['completed_units'] == [[DAY]]
    assert rows(lab.db, 'SELECT obs_day,arm FROM processed_detector_linearity_obs_days') == (
        [(DAY, arm)] if other_day else [])
    monkeypatch.setattr(detlin, 'compute_detector_linearity_results', original)
    store = SQLiteStore(lab.db)
    cli.consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT count(*) FROM detlin_sequences') == [(2,)]
    before = database_snapshot(lab.db)
    assert cli.consolidate_detector_linearity(lab.cfg, store) == 0
    assert database_snapshot(lab.db) == before


def test_failed_forced_fit_preserves_closed_unit_and_public_compute_raises(lab, monkeypatch):
    lab.detlin()
    store = SQLiteStore(lab.db)
    cli.consolidate_detector_linearity(lab.cfg, store)
    before = database_snapshot(lab.db)

    def fail(*args, **kwargs):
        raise ArithmeticError('Fit failed')

    monkeypatch.setattr(detlin, '_fit_detector_linearity_rows', fail)
    batch = detlin._load_detector_linearity_batch(lab.cfg, force=True)
    assert batch.frames['results'].empty
    cache = {path: fits.getdata(path) for path in batch.frames['measurements'].filepath}
    with pytest.raises(ArithmeticError):
        detlin.compute_detector_linearity_results(batch.frames['measurements'], cache, 39321.6)
    counts = {}
    cli.consolidate_detector_linearity(lab.cfg, store, force=True, _result=counts)
    assert counts['persisted'] == 0
    assert counts['completed_units'] == []
    assert database_snapshot(lab.db) == before


@pytest.mark.parametrize('family', ['dsol', 'oloc'])
def test_malformed_filename_blocks_own_family_but_others_proceed(lab, family):
    lab.dsol()
    lab.oloc()
    name = ('broken_VIS_DSOL_PINHOLE_SOXS_FITTED_LINES.fits' if family == 'dsol'
            else 'broken_VIS_OLOC_QTH_PINHOLE_10_0S_SOXS.fits')
    (lab.products / name).write_bytes(b'not FITS')
    result = lab.cli('--no-plots', expected=1)
    value = json.loads(result.stderr.split('RUN_SUMMARY ')[-1])
    assert value['families'][family]['errors']
    assert value['families'][family]['completed_units'] == []
    other = 'oloc' if family == 'dsol' else 'dsol'
    assert value['families'][other]['completed_units'] == [[DAY]]
    assert value['families']['qc']['completed_units'] == [[DAY]]


@contextmanager
def database_lock(path, kind='EXCLUSIVE'):
    """An external SQL process does not cooperate with the monitor's writer lease."""
    program = '''
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute('BEGIN ' + sys.argv[2])
if sys.argv[2] == '':
    conn.execute('SELECT * FROM qc_metrics').fetchall()
print('locked', flush=True)
sys.stdin.readline()
conn.rollback()
conn.close()
'''
    process = subprocess.Popen([sys.executable, '-I', '-c', program, str(path), kind],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'locked'

        def release():
            if process.poll() is None:
                process.stdin.write('\n')
                process.stdin.flush()
                assert process.wait(timeout=5) == 0
        yield release
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


@pytest.fixture
def short_sqlite_timeout(monkeypatch):
    # Keep broad integration coverage fast; a separate test exercises the real 5s policy.
    from qc_monitor import _preflight
    for module in (storage, acquisition, cli, rebuild, _preflight):
        monkeypatch.setattr(module, 'SQLITE_TIMEOUT_SECONDS', 0.05)


@pytest.mark.parametrize('access', ['upstream', 'registry', 'dataframe', 'init',
                                   'preflight_upstream', 'preflight_archive',
                                   'rebuild_archive', 'rebuild_coverage'])
@pytest.mark.parametrize('released', [False, True])
def test_real_read_contention_is_bounded_and_diagnosed(
        lab, monkeypatch, short_sqlite_timeout, access, released):
    store = SQLiteStore(lab.db)
    source = lab.upstream if 'upstream' in access else lab.db
    events = []
    delays = []
    with database_lock(source) as release:
        def pause(seconds):
            delays.append(seconds)
            if released:
                release()
        monkeypatch.setattr(retry, 'sleep', pause)
        with retry.collect_sqlite_events(events):
            if access == 'upstream':
                batch = acquisition._load_qc_batch(source, lab.cfg)
                assert bool(batch.frames['metrics'].empty) != released
                if not released:
                    assert batch.outcomes[0].details['sqlite_code'] == sqlite3.SQLITE_BUSY
                assert batch.sqlite_operations == events
            else:
                action = {
                    'registry': store.get_processed_obs_days,
                    'dataframe': store.load_all_metrics,
                    'init': lambda: SQLiteStore(lab.db),
                    'rebuild_archive': lambda: rebuild.validate_archive(lab.db),
                    'rebuild_coverage': lambda: rebuild.validate_coverage(lab.db, lab.db),
                    'preflight_upstream': lambda: retry.retry_sqlite(
                        lambda: cli._inspect_upstream_schema(source, 'quality_control_plus_lite'),
                        operation='preflight_upstream', source=source),
                    'preflight_archive': lambda: retry.retry_sqlite(
                        lambda: cli._inspect_qc_schema(source, False),
                        operation='preflight_archive', source=source),
                }[access]
                if released:
                    action()
                else:
                    with pytest.raises(Exception) as raised:
                        action()
                    assert retry.is_transient_sqlite_error(raised.value)
    assert len(events) == 1
    assert events[0]['state'] == ('recovered' if released else 'exhausted')
    assert events[0]['attempts'] == (2 if released else 3)
    assert delays == ([0.25] if released else [0.25, 0.5])


def test_default_timeout_and_retry_budget_with_real_persistent_lock(lab):
    store = SQLiteStore(lab.db)
    assert retry.SQLITE_TIMEOUT_SECONDS == storage.SQLITE_TIMEOUT_SECONDS == 5
    assert retry.RETRY_DELAYS_SECONDS == (0.25, 0.5)
    with database_lock(lab.db):
        start = time.monotonic()
        with pytest.raises(sqlite3.OperationalError):
            store.get_processed_obs_days()
        elapsed = time.monotonic() - start
    assert 15.7 <= elapsed < 25
    assert store.sqlite_operations[-1]['attempts'] == 3


@pytest.mark.parametrize('released', [False, True])
@pytest.mark.parametrize('kind', ['IMMEDIATE', ''])
def test_write_and_commit_contention_roll_back_whole_unit(
        lab, monkeypatch, short_sqlite_timeout, released, kind):
    store = SQLiteStore(lab.db)
    frame = acquisition.load_qc_from_session_db(lab.upstream, lab.cfg)
    before = database_snapshot(lab.db)
    with database_lock(lab.db, kind) as release:
        monkeypatch.setattr(retry, 'sleep', lambda _: release() if released else None)
        if released:
            store.replace_qc_day(DAY, frame)
        else:
            with pytest.raises(sqlite3.OperationalError):
                store.replace_qc_day(DAY, frame)
    if released:
        assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(1,)]
        assert rows(lab.db, 'SELECT obs_day FROM processed_obs_days') == [(DAY,)]
        assert rows(lab.db, 'SELECT count(*) FROM qc_metric_sources') == [(1,)]
    else:
        assert database_snapshot(lab.db) == before
    assert len(store.sqlite_operations) == 1
    assert store.sqlite_operations[0]['attempts'] == (2 if released else 3)


@pytest.mark.parametrize('read', ['counts', 'latest'])
def test_readonly_exhaustion_is_not_swallowed_as_legacy_no_data(lab, monkeypatch, short_sqlite_timeout, read):
    SQLiteStore(lab.db)
    with closing(sqlite3.connect(lab.db)) as conn:
        conn.execute('PRAGMA user_version=0')
    store = SQLiteStore(lab.db, read_only=True)
    before = tree_snapshot(lab.root)
    monkeypatch.setattr(retry, 'sleep', lambda _: None)
    with database_lock(lab.db):
        with pytest.raises(ReadOnlyStorageError):
            store.unit_row_counts('qc', (DAY,)) if read == 'counts' else store.latest_data_utc('qc')
    assert tree_snapshot(lab.root) == before
    assert len(store.sqlite_operations) == 1


@pytest.mark.parametrize('code', [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_BUSY_SNAPSHOT])
def test_numeric_codes_and_pandas_wrappers_are_used_for_retry(monkeypatch, code):
    events, calls = [], []
    monkeypatch.setattr(retry, 'sleep', lambda _: None)

    def action():
        calls.append(1)
        if len(calls) == 1:
            try:
                error = sqlite3.OperationalError('An arbitrary message without lock keywords')
                error.sqlite_errorcode = code
                error.sqlite_errorname = 'numeric-test'
                raise error
            except sqlite3.Error as error:
                raise pd.errors.DatabaseError('pandas wrapped query') from error
        return 42

    assert retry.retry_sqlite(action, operation='wrapped', source='temporary', events=events) == 42
    assert len(calls) == 2
    assert events[0]['failures'][0]['sqlite_code'] == code
    assert events[0]['state'] == 'recovered'


@pytest.mark.parametrize('failure', [ValueError('busy locked'), WriterBusyError('busy'),
    sqlite3.OperationalError('database is locked without a numeric SQLite code')])
def test_non_sqlite_errors_and_messages_are_never_retried(failure, monkeypatch):
    calls = []
    def action():
        calls.append(1)
        raise failure
    monkeypatch.setattr(retry, 'sleep', lambda _: pytest.fail('Unexpected retry'))
    with pytest.raises(type(failure)):
        retry.retry_sqlite(action, operation='permanent', source='temporary')
    assert len(calls) == 1


def test_real_schema_and_integrity_failures_are_not_retried(lab, monkeypatch):
    store = SQLiteStore(lab.db)
    frame = acquisition.load_qc_from_session_db(lab.upstream, lab.cfg)
    store.write_metrics(frame)
    monkeypatch.setattr(retry, 'sleep', lambda _: pytest.fail('Unexpected retry'))
    with pytest.raises(sqlite3.IntegrityError):
        store.write_metrics(frame)
    with closing(sqlite3.connect(lab.db)) as conn:
        conn.execute('PRAGMA user_version=2')
    with pytest.raises(storage.SchemaError):
        SQLiteStore(lab.db)
    assert store.sqlite_operations == []


def test_counters_keep_previous_commits_after_later_storage_failure(lab, monkeypatch, caplog):
    second_day = '2026-10-06'
    with closing(sqlite3.connect(lab.upstream)) as conn:
        conn.execute('INSERT INTO quality_control_plus_lite SELECT * FROM quality_control_plus_lite')
        conn.execute('UPDATE quality_control_plus_lite SET "night start date"=?, obs_date_utc=? WHERE rowid=2',
                     (second_day, second_day + 'T08:00:00'))
        conn.commit()
    SQLiteStore(lab.db)
    with closing(sqlite3.connect(lab.db)) as conn:
        conn.execute(f"""CREATE TRIGGER fail_second BEFORE INSERT ON processed_obs_days
            WHEN NEW.obs_day='{second_day}' BEGIN
            SELECT RAISE(ABORT, 'Induced registry failure'); END""")
        conn.commit()
    code, value = in_process(lab, monkeypatch, caplog, '--no-plots')
    assert code == 2
    family = value['families']['qc']
    assert family['selected'] == 2
    assert family['persisted'] == family['tables']['qc_metrics']['persisted'] == 1
    assert family['completed_units'] == [[DAY]]
    assert rows(lab.db, 'SELECT obs_day FROM processed_obs_days') == [(DAY,)]
    assert rows(lab.db, 'SELECT "night start date" FROM qc_metrics') == [(DAY,)]
    assert rows(lab.db, 'SELECT count(*) FROM qc_metric_sources') == [(1,)]
    assert 'dsol' not in value['families']


def test_recovered_preflight_is_success_and_summary_contains_retry(lab, monkeypatch, caplog, short_sqlite_timeout):
    before = tree_snapshot(lab.root)
    with database_lock(lab.upstream) as release:
        monkeypatch.setattr(retry, 'sleep', lambda _: release())
        code, value = in_process(lab, monkeypatch, caplog, '--preflight')
    assert code == 0
    assert value['sqlite_operations'][0]['operation'] == 'preflight_upstream'
    assert value['sqlite_operations'][0]['state'] == 'recovered'
    assert tree_snapshot(lab.root) == before


def test_exhausted_preflight_is_error_before_writes(lab, monkeypatch, caplog, short_sqlite_timeout):
    before = tree_snapshot(lab.root)
    with database_lock(lab.upstream):
        monkeypatch.setattr(retry, 'sleep', lambda _: None)
        code, value = in_process(lab, monkeypatch, caplog, '--no-plots')
    assert code == 2
    assert value['families'] == {}
    assert value['sqlite_operations'][0]['state'] == 'exhausted'
    assert tree_snapshot(lab.root) == before


def test_json_additions_and_collector_do_not_leak_between_runs():
    run = RunResult('run')
    with retry.collect_sqlite_events(run.sqlite_operations):
        assert retry.retry_sqlite(lambda: 1, operation='ok', source='temporary') == 1
    assert run.as_dict()['format_version'] == 1
    assert run.as_dict()['sqlite_operations'] == []
    assert RunResult('run').sqlite_operations is not run.sqlite_operations


@pytest.mark.parametrize('code', [sqlite3.SQLITE_FULL, sqlite3.SQLITE_READONLY,
                                 sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_IOERR,
                                 sqlite3.SQLITE_CONSTRAINT])
def test_permanent_numeric_sqlite_codes_are_not_retried(monkeypatch, code):
    error = sqlite3.OperationalError('busy locked wording does not control retry')
    error.sqlite_errorcode = code
    error.sqlite_errorname = 'permanent-test'
    calls = []
    def action():
        calls.append(1)
        raise error
    monkeypatch.setattr(retry, 'sleep', lambda _: pytest.fail('Unexpected retry'))
    with pytest.raises(sqlite3.OperationalError):
        retry.retry_sqlite(action, operation='permanent', source='temporary')
    assert len(calls) == 1


def test_runtime_upstream_exhaustion_is_partial_and_other_family_proceeds(
        lab, monkeypatch, caplog, short_sqlite_timeout):
    lab.dsol()
    original = cli._load_qc_batch
    def contended(path, cfg):
        with database_lock(path):
            return original(path, cfg)
    from qc_monitor import _consolidation
    monkeypatch.setattr(_consolidation, '_load_qc_batch', contended)
    monkeypatch.setattr(retry, 'sleep', lambda _: None)
    code, value = in_process(lab, monkeypatch, caplog, '--no-plots')
    assert code == 1
    assert value['families']['qc']['state'] == 'partial'
    assert value['families']['qc']['errors'][0]['sqlite_retry']['attempts'] == 3
    assert value['families']['dsol']['completed_units'] == [[DAY]]
    assert value['sqlite_operations'][0]['state'] == 'exhausted'
    assert rows(lab.db, 'SELECT * FROM processed_obs_days') == []


def test_archive_write_exhaustion_is_blocking_and_does_not_advance_counters(
        lab, monkeypatch, caplog, short_sqlite_timeout):
    lab.dsol()
    original = SQLiteStore.replace_qc_day
    def contended(self, day, frame):
        with database_lock(self.db_path, 'IMMEDIATE'):
            return original(self, day, frame)
    monkeypatch.setattr(SQLiteStore, 'replace_qc_day', contended)
    monkeypatch.setattr(retry, 'sleep', lambda _: None)
    code, value = in_process(lab, monkeypatch, caplog, '--no-plots')
    assert code == 2
    family = value['families']['qc']
    assert family['selected'] == 1
    assert family['persisted'] == family['tables']['qc_metrics']['persisted'] == 0
    assert family['completed_units'] == []
    assert 'dsol' not in value['families']
    assert value['sqlite_operations'][0]['operation'] == '_replace_complete_unit'
    assert value['sqlite_operations'][0]['attempts'] == 3
    assert rows(lab.db, 'SELECT * FROM processed_obs_days') == []

"""Build, verify and replace an archive while retaining a consistent backup."""
from contextlib import closing, contextmanager
from pathlib import Path
import os
import sqlite3
import tempfile

from qc_monitor.locking import writer_lease
from qc_monitor.schema import UNIT_TABLES, REGISTERS, SCHEMA_VERSION, quote
from qc_monitor.storage import SQLiteStore, SchemaError, validate_schema
from qc_monitor._sqlite_retry import SQLITE_TIMEOUT_SECONDS, retry_path_read


class RebuildError(RuntimeError):
    pass


def _readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True,
                           timeout=SQLITE_TIMEOUT_SECONDS)


@retry_path_read
def validate_archive(path):
    with closing(_readonly(path)) as conn:
        validate_schema(conn)
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RebuildError('Rebuilt archive failed integrity_check')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise RebuildError('Rebuilt archive failed foreign_key_check')


def backup_archive(path):
    """SQLite backup includes committed WAL content without copying live sidecars."""
    fd, name = tempfile.mkstemp(prefix=path.name + '.backup-', suffix='.sqlite', dir=path.parent)
    os.close(fd)
    backup = Path(name)
    try:
        with closing(_readonly(path)) as source, closing(sqlite3.connect(
                backup, timeout=SQLITE_TIMEOUT_SECONDS)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise RebuildError('Previous archive failed backup integrity_check')
        with backup.open('rb') as stream:
            os.fsync(stream.fileno())
    except Exception as exc:
        raise RebuildError(f'Cannot verify backup {backup}: {exc}') from exc
    return backup


@retry_path_read
def validate_coverage(previous, candidate):
    """Check old product identities, not old numeric values or exact row counts."""
    with closing(_readonly(previous)) as old, closing(_readonly(candidate)) as new:
        version = old.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise RebuildError(f'Cannot establish coverage for schema version {version}')
        known = {table[0] for tables in UNIT_TABLES.values() for table in tables} | set(REGISTERS.values())
        known |= {'detlin_sequences', 'qc_metric_sources', 'sqlite_sequence'}
        existing = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if existing - known:
            raise RebuildError(f'Cannot establish coverage for unknown tables: {sorted(existing - known)}')
        for family, register in REGISTERS.items():
            if register not in existing:
                continue
            columns = ['obs_day', 'arm'] if family == 'detlin' else ['obs_day']
            query = f'SELECT {",".join(map(quote, columns))} FROM {quote(register)}'
            try:
                old_units = set(old.execute(query))
                new_units = set(new.execute(query))
            except sqlite3.Error as exc:
                raise RebuildError(f'Cannot establish coverage of {register}: {exc}') from exc
            if not old_units <= new_units:
                raise RebuildError(f'Rebuild coverage missing closed units in {register}: {sorted(old_units-new_units)}')
        for family, tables in UNIT_TABLES.items():
            for table, _, keys in tables:
                if table not in existing:
                    continue
                available = {r[1] for r in old.execute(f'PRAGMA table_info({quote(table)})')}
                coverage_keys = keys
                if table == 'detector_linearity_results' and 'sequence_id' not in available:
                    coverage_keys = ['obs_day', 'eso seq arm', 'detector_mode', 'exptime', 'pair_index']
                if not set(coverage_keys) <= available:
                    raise RebuildError(f'Cannot establish coverage of {table}: identity columns absent')
                query = f'SELECT {",".join(map(quote, coverage_keys))} FROM {quote(table)}'
                old_rows, new_rows = set(old.execute(query)), set(new.execute(query))
                if not old_rows <= new_rows:
                    raise RebuildError(f'Rebuild coverage missing products in {table}: {len(old_rows-new_rows)} identities')
                if table == 'detector_linearity_results' and 'sequence_id' not in available:
                    _validate_legacy_detlin_references(old, new, available, coverage_keys)
        # QC origins describe the selected databases of this acquisition. Coverage
        # uses scientific metric identities, independent of where those DBs live.


def _validate_legacy_detlin_references(old, new, available, keys):
    """A day/mode match alone cannot identify an old unversioned detector fit."""
    references = [column for column in ('file1', 'file2', 'dark_file') if column in available]
    if not {'file1', 'file2'} <= set(references):
        raise RebuildError('Cannot establish legacy DETLIN input identities: pair columns absent')
    try:
        source_paths = dict(old.execute('SELECT source_file,filepath FROM detector_linearity_measurements'))
    except sqlite3.Error as exc:
        raise RebuildError(f'Cannot establish legacy DETLIN input identities: {exc}') from exc
    query = 'SELECT ' + ','.join(map(quote, [*keys, *references])) + ' FROM detector_linearity_results'
    where = ' AND '.join(f'{quote(key)} IS ?' for key in keys)
    for row in old.execute(query):
        matches = new.execute('SELECT ' + ','.join(map(quote, references))
                              + ' FROM detector_linearity_results WHERE ' + where, row[:len(keys)]).fetchall()
        expected = []
        for reference in row[len(keys):]:
            if not reference:
                expected.append(None)
                continue
            path = reference if Path(reference).is_absolute() else source_paths.get(reference)
            if not path or not Path(path).is_absolute():
                raise RebuildError('Cannot establish legacy DETLIN input identities from basenames')
            expected.append(str(Path(path).resolve()))
        if not any(all(previous is None or previous == current for previous, current in zip(expected, match))
                   for match in matches):
            raise RebuildError('Rebuild coverage missing legacy DETLIN input pair')


@contextmanager
def acquisition_store(path, *, dry_run=False, rebuild=False, run=None):
    path = Path(path).resolve()
    if dry_run:
        store = SQLiteStore(path, read_only=True)
        if run is not None:
            run.storage = {'schema_version': store.schema_version}
        yield store
        return
    with writer_lease(path):
        if not rebuild:
            store = SQLiteStore(path)
            if run is not None:
                run.storage = {'schema_version': store.schema_version}
            yield store
            return
        backup = backup_archive(path) if path.exists() else None
        fd, name = tempfile.mkstemp(prefix='.' + path.name + '.rebuild-', suffix='.sqlite', dir=path.parent)
        os.close(fd)
        candidate = Path(name)
        try:
            store = SQLiteStore(candidate)
            if run is not None:
                run.storage = {'schema_version': SCHEMA_VERSION, 'backup': str(backup) if backup else None,
                               'rebuild_state': 'building', 'active_database': str(path),
                               'candidate': str(candidate)}
            yield store
            if run is not None and (run.errors or any(f.get('state') == 'partial' for f in run.families.values())):
                raise RebuildError('Rebuild acquisition incomplete; previous archive retained')
            validate_archive(candidate)
            if backup is not None:
                validate_coverage(backup, candidate)
            # A pre-existing WAL archive cannot be atomically replaced with unrelated
            # sidecars still attached. Do not checkpoint or delete another writer's WAL.
            if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
                raise RebuildError('Active SQLite sidecars prevent safe replacement; close external connections first')
            with candidate.open('rb') as stream:
                os.fsync(stream.fileno())
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            # All fallible validation/synchronization precedes the commit point.
            # Atomic rename protects readers; power-loss durability is filesystem dependent.
            os.replace(candidate, path)
            store.db_path = path
            if run is not None:
                run.storage['rebuild_state'] = 'published'
        except BaseException:
            if run is not None and hasattr(run, 'storage'):
                run.storage['rebuild_state'] = 'failed'
                for family in run.families.values():
                    staged_units = family.get('completed_units', [])
                    family['staged_units'] = staged_units
                    if staged_units:
                        family['state'] = 'partial'
                    family['completed_units'] = []
                    if 'persisted' in family:
                        family['persisted'] = 0
                    family['latest_data_utc'] = None
                    for counts in family.get('tables', {}).values():
                        counts['staged'] = counts['persisted']
                        counts['persisted'] = 0
            raise
        finally:
            # Only owned staging files; backups deliberately survive failures.
            candidate.unlink(missing_ok=True)
            for suffix in ('-journal', '-wal', '-shm', '.lock'):
                Path(str(candidate) + suffix).unlink(missing_ok=True)

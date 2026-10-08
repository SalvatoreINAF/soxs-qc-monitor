import logging
import sqlite3
from contextlib import closing, nullcontext
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from qc_monitor.schema import (
    TABLE_SCHEMA, UNIQUE_COLUMNS, SCHEMA_VERSION, UNIT_TABLES as _UNIT_TABLES,
    REGISTERS as _REGISTERS, schema_statements, quote,
    DISPERSION_SOLUTION_COLUMNS, DISPERSION_RESOLUTION_STATS_COLUMNS,
    ORDER_LOCATION_MODEL_COLUMNS, ORDER_LOCATION_META_COLUMNS,
    DETECTOR_LINEARITY_MEASUREMENT_COLUMNS, DETECTOR_LINEARITY_RESULT_COLUMNS,
)
from qc_monitor.locking import locked_store_read, writer_lease, locked_store_method
from qc_monitor._sqlite_retry import (SQLITE_TIMEOUT_SECONDS, retry_store_method,
                                      is_transient_sqlite_error)
import json

log = logging.getLogger(__name__)
TABLE_COLUMNS = list(TABLE_SCHEMA)


def qc_identity(row):
    return json.dumps([None if pd.isna(row[key]) else str(row[key]) for key in UNIQUE_COLUMNS],
                      ensure_ascii=True, separators=(',', ':'))


class SchemaError(RuntimeError):
    pass


def validate_schema(conn):
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    if conn.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
        raise SchemaError(f'{path}: Incompatible schema; use an explicit backed-up --rebuild-db')
    # Compare the full structural contract, including unique/check/foreign keys.
    with closing(sqlite3.connect(':memory:')) as expected:
        for sql in schema_statements():
            expected.execute(sql)
        contract = expected.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        actual = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type != 'trigger'").fetchall()
        if sorted(contract) != sorted(actual):
            raise SchemaError(f'{path}: Incompatible schema structure; use an explicit backed-up --rebuild-db')



def _prepare_unit_frames(family: str, frames: list[pd.DataFrame]) -> list[pd.DataFrame]:
    prepared = []
    for (_, columns, keys), frame in zip(_UNIT_TABLES[family], frames, strict=True):
        normalized = frame[columns].astype(object).where(pd.notna(frame[columns]), None)
        required = [key for key in keys if not (family == "qc" and key == "file")]
        if normalized[required].isna().any().any():
            raise ValueError(f"Missing {family} identity fields: {required}")
        normalized = normalized.drop_duplicates().reset_index(drop=True)
        normalized.attrs = frame.attrs.copy()
        if normalized.duplicated(subset=keys).any():
            raise ValueError(f"Conflicting {family} rows for existing identity {keys}")
        prepared.append(normalized)
    return prepared


class ReadOnlyStorageError(RuntimeError):
    """An archive cannot be safely inspected without filesystem writes."""


def validate_readonly_sqlite_path(path: Path) -> bool:
    """Inspect the header without opening SQLite; absent files are allowed.

    WAL reads may create sidecars even with mode=ro. Do not use immutable=1
    for archives that another process could change.
    """
    path = Path(path).expanduser().resolve()
    try:
        with path.open("rb") as source:
            header = source.read(20)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ReadOnlyStorageError(f"Cannot read SQLite archive {path}: {exc}") from exc
    if header[:16] == b"SQLite format 3\x00" and 2 in header[18:20]:
        raise ReadOnlyStorageError(f"WAL archive is unsupported in dry-run: {path}")
    return True


class SQLiteStore:
    def __init__(self, db_path: Path, *, read_only: bool = False):
        self.db_path = Path(db_path).expanduser().resolve()
        self.read_only = read_only
        self._missing_database = False
        self.schema_version = None
        self.sqlite_operations = []
        if read_only:
            self._missing_database = not validate_readonly_sqlite_path(self.db_path)
            if not self._missing_database:
                self._read_registry("SELECT name FROM sqlite_master")
                version = self._read_registry('PRAGMA user_version')[0][0]
                self.schema_version = version
                if version not in (0, SCHEMA_VERSION):
                    raise ReadOnlyStorageError(f'Unsupported schema version {version}: {self.db_path}')
        else:
            self._init_db()
            self.schema_version = SCHEMA_VERSION

    def _connect(self):
        if not self.read_only:
            conn = sqlite3.connect(self.db_path, timeout=SQLITE_TIMEOUT_SECONDS)
            try:
                conn.execute('PRAGMA foreign_keys = ON')
            except BaseException:
                conn.close()
                raise
            return conn
        validate_readonly_sqlite_path(self.db_path)
        try:
            return sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=SQLITE_TIMEOUT_SECONDS)
        except sqlite3.Error as exc:
            raise ReadOnlyStorageError(f"Cannot open SQLite archive {self.db_path}: {exc}") from exc

    @locked_store_read
    @retry_store_method
    def _read_registry(self, query: str, parameters=()) -> list[tuple]:
        if self.read_only and self._missing_database:
            return []
        try:
            with closing(self._connect()) as conn:
                return conn.execute(query, parameters).fetchall()
        except sqlite3.Error as exc:
            if not self.read_only:
                raise
            raise ReadOnlyStorageError(
                f"Cannot read SQLite archive {self.db_path}: {exc}"
            ) from exc

    def _quote(self, name: str) -> str:
        return quote(name)

    def write_session(self):
        if self.read_only:
            return nullcontext()
        return writer_lease(self.db_path)

    @locked_store_method
    @retry_store_method
    def _init_db(self):
        # Existing archives are inspected before any writable connection is opened.
        if self.db_path.exists() and self.db_path.stat().st_size:
            with closing(sqlite3.connect(self.db_path.as_uri() + '?mode=ro', uri=True, timeout=SQLITE_TIMEOUT_SECONDS)) as conn:
                validate_schema(conn)
            return
        with closing(self._connect()) as conn, conn:
            conn.execute('BEGIN')
            for statement in schema_statements():
                conn.execute(statement)
            conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

    # Registry API

    def get_processed_obs_days(self) -> set[str]:
        query = """
        SELECT obs_day
        FROM processed_obs_days
        WHERE status = 'PROCESSED'
        """

        rows = self._read_registry(query)

        return {r[0] for r in rows}

    @locked_store_method
    @retry_store_method
    def register_processed_obs_day(
        self,
        obs_day: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_obs_days
                (obs_day, processed_at, status)
                VALUES (?, ?, ?)
                """,
                (obs_day, processed_at, status),
            )
            conn.commit()

    def get_processed_dispersion_obs_days(self) -> set[str]:
        query = """
        SELECT obs_day
        FROM processed_dispersion_obs_days
        WHERE status = 'PROCESSED'
        """

        rows = self._read_registry(query)

        return {r[0] for r in rows}

    @locked_store_method
    @retry_store_method
    def register_processed_dispersion_obs_day(
        self,
        obs_day: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_dispersion_obs_days
                (obs_day, processed_at, status)
                VALUES (?, ?, ?)
                """,
                (obs_day, processed_at, status),
            )
            conn.commit()


    def get_processed_order_location_obs_days(self) -> set[str]:
        query = """
        SELECT obs_day
        FROM processed_order_location_obs_days
        WHERE status = 'PROCESSED'
        """

        rows = self._read_registry(query)

        return {r[0] for r in rows}

    @locked_store_method
    @retry_store_method
    def register_processed_order_location_obs_day(
        self,
        obs_day: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_order_location_obs_days
                (obs_day, processed_at, status)
                VALUES (?, ?, ?)
                """,
                (obs_day, processed_at, status),
            )
            conn.commit()

    def get_processed_detector_linearity_obs_days(self) -> set[tuple[str, str]]:
        query = """
        SELECT obs_day, arm
        FROM processed_detector_linearity_obs_days
        WHERE status = 'PROCESSED'
        """

        rows = self._read_registry(query)

        return {(r[0], r[1]) for r in rows}

    @locked_store_method
    @retry_store_method
    def register_processed_detector_linearity_obs_day(
        self,
        obs_day: str,
        arm: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_detector_linearity_obs_days
                (obs_day, arm, processed_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (obs_day, arm, processed_at, status),
            )
            conn.commit()

    @locked_store_method
    @retry_store_method
    def _replace_complete_unit(self, family: str, unit: tuple[str, ...], frames: list[pd.DataFrame]):
        frames = _prepare_unit_frames(family, frames)
        day_column = "night start date" if family == "qc" else "obs_day"
        for frame in frames:
            if not frame[day_column].astype(str).eq(unit[0]).all():
                raise ValueError('Rows do not belong to the declared unit')
            if family == 'detlin' and not frame['eso seq arm'].eq(unit[1]).all():
                raise ValueError('Rows do not belong to the declared arm')
        if family == 'detlin':
            if set(frames[0].sequence_id) != set(frames[1].sequence_id) or not frames[1].fit_state.eq('available').all():
                raise ValueError('Incomplete detector-linearity sequence results')
        condition = self._quote(day_column) + " = ?"
        if family == "detlin":
            condition += ' AND "eso seq arm" = ?'
        with closing(self._connect()) as conn:
            with conn:
                if family == "detlin":
                    for table, _, _ in _UNIT_TABLES[family]:
                        conn.execute(f'DELETE FROM {quote(table)} WHERE {condition}', unit)
                    conn.execute('DELETE FROM detlin_sequences WHERE obs_day=? AND arm=?', unit)
                    sequences = frames[0][["sequence_id", "eso seq arm", "tpl_start", "tpl_id", "obs_day"]].drop_duplicates()
                    conn.executemany('INSERT INTO detlin_sequences VALUES (?,?,?,?,?)',
                                     sequences.itertuples(index=False, name=None))
                for (table, columns, _), frame in zip(_UNIT_TABLES[family], frames, strict=True):
                    conn.execute(f'DELETE FROM {self._quote(table)} WHERE {condition}', unit)
                    columns_sql = ", ".join(self._quote(column) for column in columns)
                    placeholders = ", ".join("?" for _ in columns)
                    values = [tuple(value.item() if hasattr(value, "item") else value for value in row)
                              for row in frame.itertuples(index=False, name=None)]
                    conn.executemany(f'INSERT INTO {self._quote(table)} ({columns_sql}) VALUES ({placeholders})', values)
                if family == "qc":
                    self._save_qc_provenance(conn, frames[0])
                register = _REGISTERS[family]
                timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if family == "detlin":
                    conn.execute(f'INSERT OR REPLACE INTO {register} (obs_day, arm, processed_at, status) VALUES (?, ?, ?, ?)',
                                 (*unit, timestamp, "PROCESSED"))
                else:
                    conn.execute(f'INSERT OR REPLACE INTO {register} (obs_day, processed_at, status) VALUES (?, ?, ?)',
                                 (*unit, timestamp, "PROCESSED"))

    def replace_qc_day(self, day: str, metrics: pd.DataFrame):
        self._replace_complete_unit("qc", (day,), [metrics])

    def replace_dispersion_day(self, day: str, lines: pd.DataFrame, stats: pd.DataFrame):
        self._replace_complete_unit("dsol", (day,), [lines, stats])

    def replace_order_location_day(self, day: str, models: pd.DataFrame, meta: pd.DataFrame):
        self._replace_complete_unit("oloc", (day,), [models, meta])

    def replace_detector_linearity_day(self, day: str, arm: str, measurements: pd.DataFrame, results: pd.DataFrame):
        self._replace_complete_unit("detlin", (day, arm), [measurements, results])

    def _insert_sequences(self, conn, frame):
        for row in frame[['sequence_id', 'eso seq arm', 'tpl_start', 'tpl_id', 'obs_day']].drop_duplicates().itertuples(index=False, name=None):
            present = conn.execute('SELECT sequence_id,arm,tpl_start,tpl_id,obs_day FROM detlin_sequences WHERE sequence_id=?', (row[0],)).fetchone()
            if present is None:
                conn.execute('INSERT INTO detlin_sequences VALUES (?,?,?,?,?)', row)
            elif present != row:
                raise ValueError('Conflicting sequence metadata')

    def _save_qc_provenance(self, conn, frame):
        provenance = frame.attrs.get('provenance', {})
        direct_source = frame.attrs.get('source_database')
        lookup = 'SELECT id FROM qc_metrics WHERE ' + ' AND '.join(f'{quote(key)} IS ?' for key in UNIQUE_COLUMNS)
        links = []
        for _, row in frame.iterrows():
            sources = set(provenance.get(qc_identity(row), set()))
            if direct_source:
                sources.add(direct_source)
            if not sources:
                continue
            values = tuple(None if pd.isna(row[key]) else str(row[key]) for key in UNIQUE_COLUMNS)
            metric_id = conn.execute(lookup, values).fetchone()[0]
            links.extend((metric_id, source) for source in sorted(sources))
        conn.executemany('INSERT INTO qc_metric_sources VALUES (?,?)', links)

    # Metrics storage

    @locked_store_method
    @retry_store_method
    def write_metrics(self, df: pd.DataFrame):
        if df.empty:
            return

        missing_columns = set(TABLE_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(
                f"Missing required columns in QC dataframe: {sorted(missing_columns)}"
            )

        columns_sql = ", ".join(self._quote(c) for c in TABLE_COLUMNS)
        placeholders = ", ".join("?" for _ in TABLE_COLUMNS)

        query = f"""
        INSERT INTO qc_metrics (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in TABLE_COLUMNS)
            for _, row in df.iterrows()
        ]

        with closing(self._connect()) as conn, conn:
            conn.executemany(query, rows)
            self._save_qc_provenance(conn, df)
            conn.commit()


    @locked_store_method
    @retry_store_method
    def write_dispersion_solution_lines(self, df: pd.DataFrame):
        if df.empty:
            return

        missing_columns = set(DISPERSION_SOLUTION_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(
                "Missing required columns in dispersion solution dataframe: "
                f"{sorted(missing_columns)}"
            )

        columns_sql = ", ".join(self._quote(c) for c in DISPERSION_SOLUTION_COLUMNS)
        placeholders = ", ".join("?" for _ in DISPERSION_SOLUTION_COLUMNS)

        query = f"""
        INSERT INTO dispersion_solution_lines (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DISPERSION_SOLUTION_COLUMNS)
            for _, row in df.iterrows()
        ]

        with closing(self._connect()) as conn, conn:
            conn.executemany(query, rows)
            conn.commit()

    @locked_store_method
    @retry_store_method
    def write_dispersion_resolution_stats(self, df: pd.DataFrame):
        if df.empty:
            return

        missing_columns = set(DISPERSION_RESOLUTION_STATS_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(
                "Missing required columns in dispersion resolution stats dataframe: "
                f"{sorted(missing_columns)}"
            )

        columns_sql = ", ".join(
            self._quote(c) for c in DISPERSION_RESOLUTION_STATS_COLUMNS
        )
        placeholders = ", ".join("?" for _ in DISPERSION_RESOLUTION_STATS_COLUMNS)

        query = f"""
        INSERT INTO dispersion_resolution_stats (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DISPERSION_RESOLUTION_STATS_COLUMNS)
            for _, row in df.iterrows()
        ]

        with closing(self._connect()) as conn, conn:
            conn.executemany(query, rows)
            conn.commit()

    @locked_store_method
    @retry_store_method
    def write_order_location_models(self, df: pd.DataFrame):
        if df.empty:
            return

        missing_columns = set(ORDER_LOCATION_MODEL_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(
                "Missing required columns in order-location dataframe: "
                f"{sorted(missing_columns)}"
            )

        columns_sql = ", ".join(self._quote(c) for c in ORDER_LOCATION_MODEL_COLUMNS)
        placeholders = ", ".join("?" for _ in ORDER_LOCATION_MODEL_COLUMNS)

        query = f"""
        INSERT INTO order_location_models (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in ORDER_LOCATION_MODEL_COLUMNS)
            for _, row in df.iterrows()
        ]

        with closing(self._connect()) as conn, conn:
            conn.executemany(query, rows)
            conn.commit()

    @locked_store_method
    @retry_store_method
    def write_order_location_meta(self, df: pd.DataFrame):
        if df.empty:
            return

        missing_columns = set(ORDER_LOCATION_META_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(
                "Missing required columns in order-location meta dataframe: "
                f"{sorted(missing_columns)}"
            )

        columns_sql = ", ".join(self._quote(c) for c in ORDER_LOCATION_META_COLUMNS)
        placeholders = ", ".join("?" for _ in ORDER_LOCATION_META_COLUMNS)

        query = f"""
        INSERT INTO order_location_meta (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in ORDER_LOCATION_META_COLUMNS)
            for _, row in df.iterrows()
        ]

        with closing(self._connect()) as conn, conn:
            conn.executemany(query, rows)
            conn.commit()

    @locked_store_method
    @retry_store_method
    def write_detector_linearity_measurements(self, df: pd.DataFrame):
        if df.empty:
            return

        missing_columns = set(DETECTOR_LINEARITY_MEASUREMENT_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(
                "Missing required columns in detector-linearity measurements: "
                f"{sorted(missing_columns)}"
            )

        columns_sql = ", ".join(
            self._quote(c) for c in DETECTOR_LINEARITY_MEASUREMENT_COLUMNS
        )
        placeholders = ", ".join("?" for _ in DETECTOR_LINEARITY_MEASUREMENT_COLUMNS)

        query = f"""
        INSERT INTO detector_linearity_measurements (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DETECTOR_LINEARITY_MEASUREMENT_COLUMNS)
            for _, row in df.iterrows()
        ]

        with closing(self._connect()) as conn, conn:
            self._insert_sequences(conn, df)
            conn.executemany(query, rows)
            conn.commit()

    @locked_store_method
    @retry_store_method
    def write_detector_linearity_results(self, df: pd.DataFrame):
        if df.empty:
            return

        missing_columns = set(DETECTOR_LINEARITY_RESULT_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(
                "Missing required columns in detector-linearity results: "
                f"{sorted(missing_columns)}"
            )

        columns_sql = ", ".join(
            self._quote(c) for c in DETECTOR_LINEARITY_RESULT_COLUMNS
        )
        placeholders = ", ".join("?" for _ in DETECTOR_LINEARITY_RESULT_COLUMNS)

        query = f"""
        INSERT INTO detector_linearity_results (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DETECTOR_LINEARITY_RESULT_COLUMNS)
            for _, row in df.iterrows()
        ]

        with closing(self._connect()) as conn, conn:
            self._insert_sequences(conn, df)
            conn.executemany(query, rows)
            conn.commit()

    def unit_row_counts(self, family: str, unit: tuple) -> dict:
        """Count historical rows preserved by a closed-unit skip; no input comparison."""
        counts = {}
        day_column = "night start date" if family == "qc" else "obs_day"
        for table, _, _ in _UNIT_TABLES[family]:
            where = f'"{day_column}" = ?'
            if family == "detlin":
                where += ' AND "eso seq arm" = ?'
            try:
                result = self._read_registry(f'SELECT count(*) FROM "{table}" WHERE {where}', unit)
                counts[table] = result[0][0] if result else 0
            except ReadOnlyStorageError as exc:
                if is_transient_sqlite_error(exc) or self.schema_version != 0 or self._read_registry(
                        'SELECT name FROM sqlite_master WHERE name=?', (table,)):
                    raise
                # Legacy read-only archives need not expose every data table.
                counts[table] = None
        return counts

    def latest_data_utc(self, family: str) -> str | None:
        """Timestamp of latest persisted data, distinct from the batch execution time."""
        table = _UNIT_TABLES[family][0][0]
        try:
            result = self._read_registry(f'SELECT MAX("obs_date_utc") FROM "{table}"')
        except ReadOnlyStorageError as exc:
            if is_transient_sqlite_error(exc) or self.schema_version != 0 or self._read_registry(
                    'SELECT name FROM sqlite_master WHERE name=?', (table,)):
                raise
            return None
        return result[0][0] if result else None

    # Metrics load

    @locked_store_read
    @retry_store_method
    def load_all_metrics(self) -> pd.DataFrame:
        order_cols = [
            "night start date",
            "obs_date_utc",
            "eso seq arm",
            "soxspipe_recipe",
            "qc_name",
            "qc_order",
        ]

        order_sql = ", ".join(self._quote(c) for c in order_cols)

        query = f"""
        SELECT *
        FROM qc_metrics
        ORDER BY {order_sql}
        """

        with closing(self._connect()) as conn, conn:
            return pd.read_sql(query, conn)
        

    @locked_store_read
    @retry_store_method
    def load_dispersion_solution_lines(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM dispersion_solution_lines
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "order", "wavelength"
        """

        with closing(self._connect()) as conn, conn:
            return pd.read_sql(query, conn)
        
    @locked_store_read
    @retry_store_method
    def load_order_location_models(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM order_location_models
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "soxspipe_recipe", "source_file"
        """

        with closing(self._connect()) as conn, conn:
            return pd.read_sql(query, conn)


    @locked_store_read
    @retry_store_method
    def load_dispersion_resolution_stats(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM dispersion_resolution_stats
        ORDER BY "obs_date_utc", "eso seq arm", "order"
        """

        with closing(self._connect()) as conn, conn:
            return pd.read_sql(query, conn)


    @locked_store_read
    @retry_store_method
    def load_order_location_meta(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM order_location_meta
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "soxspipe_recipe", "source_file", "order"
        """

        with closing(self._connect()) as conn, conn:
            return pd.read_sql(query, conn)

    @locked_store_read
    @retry_store_method
    def load_detector_linearity_measurements(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM detector_linearity_measurements
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "detector_mode", "exptime"
        """

        with closing(self._connect()) as conn, conn:
            return pd.read_sql(query, conn)

    @locked_store_read
    @retry_store_method
    def load_detector_linearity_results(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM detector_linearity_results
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "detector_mode", "exptime"
        """

        with closing(self._connect()) as conn, conn:
            return pd.read_sql(query, conn)


    # Wipe database

    @locked_store_method
    def drop_all(self):
        """Explicit low-level maintenance; the CLI uses protected_rebuild instead."""
        with closing(self._connect()) as conn, conn:
            tables = [table[0] for tables in _UNIT_TABLES.values() for table in tables]
            for table in ['qc_metric_sources', *tables, 'detlin_sequences', *_REGISTERS.values()]:
                conn.execute(f'DROP TABLE IF EXISTS {quote(table)}')
        # File still exists: create the declared fresh schema without opening legacy.
        with closing(self._connect()) as conn, conn:
            for statement in schema_statements():
                conn.execute(statement)
            conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

import sqlite3
from pathlib import Path
import pandas as pd
import logging

log = logging.getLogger(__name__)

class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """
        Initialize the SQLite database schema.

        This method is idempotent and safe to call multiple times.
        It defines the QC metrics table with a UNIQUE constraint
        enforcing datapoint uniqueness.
        """
        with self._connect() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                obs_date TEXT NOT NULL,          -- YYYY-MM-DD
                timestamp TEXT NOT NULL,         -- ISO timestamp
                arm TEXT NOT NULL,               -- VIS/NIR
                recipe TEXT NOT NULL,            -- soxs-mdark, etc.
                metric TEXT NOT NULL,            -- QC metric name
                value REAL,
                unit TEXT,
                source_file TEXT,                -- filename only

                UNIQUE (timestamp, metric, arm, recipe)
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_registry (
                obs_date TEXT NOT NULL,
                arm TEXT NOT NULL,
                recipe TEXT NOT NULL,
                status TEXT NOT NULL,             -- COMPLETE / INCOMPLETE

                UNIQUE (obs_date, arm, recipe)
            );
            """)

            conn.commit()

    # Registry API

    def get_processed_dates(self) -> set[str]:
        query = """
        SELECT DISTINCT obs_date
        FROM qc_registry
        """
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return {r[0] for r in rows}

    def register_recipe_status(
        self,
        obs_date: str,
        arm: str,
        recipe: str,
        status: str,
    ):
        """
        Register the completeness status of a recipe for a given date and arm.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qc_registry
                (obs_date, arm, recipe, status)
                VALUES (?, ?, ?, ?)
                """,
                (obs_date, arm, recipe, status),
            )
            conn.commit()

    # Metrics storage

    def write_metrics(self, df: pd.DataFrame):
        """
        Insert QC metrics into the database.

        Datapoint uniqueness is enforced by the UNIQUE constraint
        (timestamp, metric, arm, recipe). Duplicate datapoints
        are silently ignored.
        """
        if df.empty:
            return

        query = """
        INSERT OR IGNORE INTO qc_metrics (
            obs_date,
            timestamp,
            arm,
            recipe,
            metric,
            value,
            unit,
            source_file
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

        rows = [
            (
                row.obs_date,
                row.timestamp,
                row.arm,
                row.recipe,
                row.metric,
                row.value,
                row.unit,
                row.source_file,
            )
            for row in df.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(query, rows)
            conn.commit()

    # Metrics load

    def load_all_metrics(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM qc_metrics
        ORDER BY obs_date
        """
        with self._connect() as conn:
            return pd.read_sql(query, conn)

    # Wipe database

    def drop_all(self):
        with self._connect() as conn:
            conn.execute("DROP TABLE IF EXISTS qc_metrics")
            conn.execute("DROP TABLE IF EXISTS qc_registry")
            conn.commit()

        # Recreate empty schema
        self._init_db()

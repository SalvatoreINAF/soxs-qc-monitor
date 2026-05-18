import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from qc_monitor.schema import TABLE_SCHEMA, UNIQUE_COLUMNS

log = logging.getLogger(__name__)

TABLE_COLUMNS = list(TABLE_SCHEMA.keys())

class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _quote(self, name: str) -> str:
        return f'"{name}"'

    def _init_db(self):
        columns_sql = """
                id INTEGER PRIMARY KEY AUTOINCREMENT,
        """

        for col in TABLE_COLUMNS:
            col_type = TABLE_SCHEMA[col]
            columns_sql += f"""
                {self._quote(col)} {col_type},
            """

        unique_sql = ", ".join(self._quote(c) for c in UNIQUE_COLUMNS)

        with self._connect() as conn:
            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS qc_metrics (
                {columns_sql}

                UNIQUE ({unique_sql})
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_obs_days (
                obs_day TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """)

            conn.commit()

    # Registry API

    def get_processed_obs_days(self) -> set[str]:
        query = """
        SELECT obs_day
        FROM processed_obs_days
        WHERE status = 'PROCESSED'
        """

        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        return {r[0] for r in rows}

    def register_processed_obs_day(
        self,
        obs_day: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_obs_days
                (obs_day, processed_at, status)
                VALUES (?, ?, ?)
                """,
                (obs_day, processed_at, status),
            )
            conn.commit()

    # Metrics storage

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
        INSERT OR IGNORE INTO qc_metrics (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in TABLE_COLUMNS)
            for _, row in df.iterrows()
        ]

        with self._connect() as conn:
            conn.executemany(query, rows)
            conn.commit()

    # Metrics load

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

        with self._connect() as conn:
            return pd.read_sql(query, conn)

    # Wipe database

    def drop_all(self):
        with self._connect() as conn:
            conn.execute("DROP TABLE IF EXISTS qc_metrics")
            conn.execute("DROP TABLE IF EXISTS processed_obs_days")
            conn.commit()

        self._init_db()
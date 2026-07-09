import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from qc_monitor.schema import TABLE_SCHEMA, UNIQUE_COLUMNS
from qc_monitor.acquisition import DISPERSION_SOLUTION_COLUMNS
from qc_monitor.acquisition import DISPERSION_RESOLUTION_STATS_COLUMNS
from qc_monitor.acquisition import ORDER_LOCATION_MODEL_COLUMNS
from qc_monitor.acquisition import ORDER_LOCATION_META_COLUMNS
from qc_monitor.detector_linearity import DETECTOR_LINEARITY_MEASUREMENT_COLUMNS
from qc_monitor.detector_linearity import DETECTOR_LINEARITY_RESULT_COLUMNS

log = logging.getLogger(__name__)

TABLE_COLUMNS = list(TABLE_SCHEMA.keys())

class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _quote(self, name: str) -> str:
        return f'"{name}"'

    def _init_db(self):

        # QC table columns
        columns_sql = """
                id INTEGER PRIMARY KEY AUTOINCREMENT,
        """

        for col in TABLE_COLUMNS:
            col_type = TABLE_SCHEMA[col]
            columns_sql += f"""
                {self._quote(col)} {col_type},
            """

        unique_sql = ", ".join(self._quote(c) for c in UNIQUE_COLUMNS)

        # Dispersion solution columns
        dsol_columns_sql = """
                id INTEGER PRIMARY KEY AUTOINCREMENT,
        """

        dsol_type_map = {
            "obs_day": "TEXT NOT NULL",
            "obs_date_utc": "TEXT NOT NULL",
            "eso seq arm": "TEXT NOT NULL",
            "soxspipe_recipe": "TEXT NOT NULL",
            "source_file": "TEXT NOT NULL",
            "filepath": "TEXT",
            "wavelength": "REAL",
            "order": "TEXT",
            "slit_index": "INTEGER",
            "slit_position": "REAL",
            "detector_x": "REAL",
            "detector_y": "REAL",
            "observed_x": "REAL",
            "observed_y": "REAL",
            "x_diff": "REAL",
            "y_diff": "REAL",
            "fit_x": "REAL",
            "fit_y": "REAL",
            "residuals_x": "REAL",
            "residuals_y": "REAL",
            "residuals_xy": "REAL",
            "sigma_clipped": "TEXT",
            "sharpness": "REAL",
            "roundness1": "REAL",
            "roundness2": "REAL",
            "npix": "REAL",
            "sky": "REAL",
            "peak": "REAL",
            "flux": "REAL",
            "fwhm_pin_px": "REAL",
            "R_pin": "REAL",
            "pixelScaleNm": "REAL",
            "detector_x_shifted": "REAL",
            "detector_y_shifted": "REAL",
            "R_slit": "REAL",
            "fwhm_slit_px": "REAL",
        }

        for col in DISPERSION_SOLUTION_COLUMNS:
            col_type = dsol_type_map.get(col, "TEXT")
            dsol_columns_sql += f"""
            {self._quote(col)} {col_type},
            """

        # Dispersion resolution stats columns
        resolution_stats_columns_sql = """
                id INTEGER PRIMARY KEY AUTOINCREMENT,
            """
        
        resolution_stats_type_map = {
                "obs_day": "TEXT NOT NULL",
                "obs_date_utc": "TEXT NOT NULL",
                "eso seq arm": "TEXT NOT NULL",
                "soxspipe_recipe": "TEXT NOT NULL",
                "source_file": "TEXT NOT NULL",
                "filepath": "TEXT",
                "order": "TEXT NOT NULL",
                "mean_R_pin": "REAL",
                "std_R_pin": "REAL",
                "n_points": "INTEGER",
            }
        
        for col in DISPERSION_RESOLUTION_STATS_COLUMNS:
                col_type = resolution_stats_type_map.get(col, "TEXT")
                resolution_stats_columns_sql += f"""
                {self._quote(col)} {col_type},
                """

        # Order localization columns
        order_location_columns_sql = """
                id INTEGER PRIMARY KEY AUTOINCREMENT,
            """
        
        order_location_type_map = {
                "obs_day": "TEXT NOT NULL",
                "obs_date_utc": "TEXT NOT NULL",
                "eso seq arm": "TEXT NOT NULL",
                "soxspipe_recipe": "TEXT NOT NULL",
                "source_file": "TEXT NOT NULL",
                "filepath": "TEXT",
                "slit": "TEXT",
                "slitmask": "TEXT",
                "lamp": "TEXT",
                "binning": "TEXT",
                "rospeed": "TEXT",
            }
        
        for col in ORDER_LOCATION_MODEL_COLUMNS:
                col_type = order_location_type_map.get(col, "REAL")
                order_location_columns_sql += f"""
                {self._quote(col)} {col_type},
                """

        # Order location meta columns
        order_location_meta_columns_sql = """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
        """

        order_location_meta_type_map = {
            "obs_day": "TEXT NOT NULL",
            "obs_date_utc": "TEXT NOT NULL",
            "eso seq arm": "TEXT NOT NULL",
            "soxspipe_recipe": "TEXT NOT NULL",
            "source_file": "TEXT NOT NULL",
            "filepath": "TEXT",
            "slit": "TEXT",
            "slitmask": "TEXT",
            "lamp": "TEXT",
            "binning": "TEXT",
            "rospeed": "TEXT",
            "order": "REAL NOT NULL",
            "xmin": "REAL",
            "xmax": "REAL",
            "ymin": "REAL",
            "ymax": "REAL",
            "maxThreshold": "REAL",
            "minThreshold": "REAL",
            "maxvalue": "REAL",
        }

        for col in ORDER_LOCATION_META_COLUMNS:
            col_type = order_location_meta_type_map.get(col, "REAL")
            order_location_meta_columns_sql += f"""
            {self._quote(col)} {col_type},
            """

        # Detector linearity columns
        detlin_measurement_columns_sql = """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
        """

        detlin_measurement_type_map = {
            "obs_day": "TEXT NOT NULL",
            "obs_date_utc": "TEXT NOT NULL",
            "eso seq arm": "TEXT NOT NULL",
            "detector_mode": "TEXT NOT NULL",
            "frame_type": "TEXT NOT NULL",
            "exptime": "REAL NOT NULL",
            "source_file": "TEXT NOT NULL",
            "filepath": "TEXT",
            "roi_name": "TEXT",
            "roi_y1": "INTEGER",
            "roi_y2": "INTEGER",
            "roi_x1": "INTEGER",
            "roi_x2": "INTEGER",
            "statistic": "TEXT",
            "signal_raw": "REAL",
        }

        for col in DETECTOR_LINEARITY_MEASUREMENT_COLUMNS:
            col_type = detlin_measurement_type_map.get(col, "TEXT")
            detlin_measurement_columns_sql += f"""
            {self._quote(col)} {col_type},
            """

        detlin_result_columns_sql = """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
        """

        detlin_result_type_map = {
            "obs_day": "TEXT NOT NULL",
            "obs_date_utc": "TEXT NOT NULL",
            "eso seq arm": "TEXT NOT NULL",
            "detector_mode": "TEXT NOT NULL",
            "exptime": "REAL NOT NULL",
            "pair_index": "INTEGER NOT NULL",
            "file1": "TEXT NOT NULL",
            "file2": "TEXT NOT NULL",
            "signal": "REAL",
            "fit_signal": "REAL",
            "residual": "REAL",
            "residual_percent": "REAL",
            "fit_used": "INTEGER",
            "saturation_limit": "REAL",
            "slope": "REAL",
            "intercept": "REAL",
            "mean_bias_roi": "REAL",
            "rms_bias_adu": "REAL",
            "cf": "REAL",
            "rms_bias_e": "REAL",
            "dark_file": "TEXT",
            "flat_files": "TEXT",
            "n_flat_frames": "INTEGER",
        }

        for col in DETECTOR_LINEARITY_RESULT_COLUMNS:
            col_type = detlin_result_type_map.get(col, "TEXT")
            detlin_result_columns_sql += f"""
            {self._quote(col)} {col_type},
            """

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

            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS dispersion_solution_lines (
                {dsol_columns_sql}
                UNIQUE (
                    "source_file",
                    "order",
                    "wavelength",
                    "detector_x",
                    "detector_y"
                )
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_dispersion_obs_days (
                obs_day TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """)

            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS dispersion_resolution_stats (
                {resolution_stats_columns_sql}

                UNIQUE (
                    "source_file",
                    "order"
                )
            );
            """)

            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS order_location_models (
                {order_location_columns_sql}

                UNIQUE (
                    "source_file"
                )
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_order_location_obs_days (
                obs_day TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """)

            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS order_location_meta (
                {order_location_meta_columns_sql}

                UNIQUE (
                    "source_file",
                    "order"
                )
            );
            """)

            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS detector_linearity_measurements (
                {detlin_measurement_columns_sql}

                UNIQUE (
                    "source_file"
                )
            );
            """)

            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS detector_linearity_results (
                {detlin_result_columns_sql}

                UNIQUE (
                    "obs_day",
                    "eso seq arm",
                    "detector_mode",
                    "exptime",
                    "pair_index"
                )
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_detector_linearity_obs_days (
                obs_day TEXT NOT NULL,
                arm TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY (obs_day, arm)
            );
            """)

            self._ensure_columns(
                conn=conn,
                table="detector_linearity_results",
                columns=DETECTOR_LINEARITY_RESULT_COLUMNS,
                type_map=detlin_result_type_map,
            )
            self._ensure_detector_linearity_registry_schema(conn)

            conn.commit()

    def _ensure_columns(
        self,
        conn: sqlite3.Connection,
        table: str,
        columns: list[str],
        type_map: dict[str, str],
    ):
        existing = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({self._quote(table)})").fetchall()
        }

        for column in columns:
            if column in existing:
                continue

            col_type = type_map.get(column, "TEXT")
            conn.execute(
                f"ALTER TABLE {self._quote(table)} "
                f"ADD COLUMN {self._quote(column)} {col_type}"
            )

    def _ensure_detector_linearity_registry_schema(self, conn: sqlite3.Connection):
        table = "processed_detector_linearity_obs_days"
        columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({self._quote(table)})").fetchall()
        }

        if "arm" in columns:
            return

        conn.execute(f"ALTER TABLE {self._quote(table)} RENAME TO {self._quote(table + '_legacy')}")
        conn.execute("""
        CREATE TABLE processed_detector_linearity_obs_days (
            obs_day TEXT NOT NULL,
            arm TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (obs_day, arm)
        );
        """)
        conn.execute("""
        INSERT OR IGNORE INTO processed_detector_linearity_obs_days
        (obs_day, arm, processed_at, status)
        SELECT obs_day, 'VIS', processed_at, status
        FROM processed_detector_linearity_obs_days_legacy
        """)
        conn.execute("DROP TABLE processed_detector_linearity_obs_days_legacy")

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

    def get_processed_dispersion_obs_days(self) -> set[str]:
        query = """
        SELECT obs_day
        FROM processed_dispersion_obs_days
        WHERE status = 'PROCESSED'
        """

        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        return {r[0] for r in rows}

    def register_processed_dispersion_obs_day(
        self,
        obs_day: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._connect() as conn:
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

        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        return {r[0] for r in rows}

    def register_processed_order_location_obs_day(
        self,
        obs_day: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._connect() as conn:
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

        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        return {(r[0], r[1]) for r in rows}

    def register_processed_detector_linearity_obs_day(
        self,
        obs_day: str,
        arm: str,
        status: str = "PROCESSED",
    ):
        processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_detector_linearity_obs_days
                (obs_day, arm, processed_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (obs_day, arm, processed_at, status),
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
        INSERT OR IGNORE INTO dispersion_solution_lines (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DISPERSION_SOLUTION_COLUMNS)
            for _, row in df.iterrows()
        ]

        with self._connect() as conn:
            conn.executemany(query, rows)
            conn.commit()

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
        INSERT OR IGNORE INTO dispersion_resolution_stats (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DISPERSION_RESOLUTION_STATS_COLUMNS)
            for _, row in df.iterrows()
        ]

        with self._connect() as conn:
            conn.executemany(query, rows)
            conn.commit()

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
        INSERT OR IGNORE INTO order_location_models (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in ORDER_LOCATION_MODEL_COLUMNS)
            for _, row in df.iterrows()
        ]

        with self._connect() as conn:
            conn.executemany(query, rows)
            conn.commit()

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
        INSERT OR IGNORE INTO order_location_meta (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in ORDER_LOCATION_META_COLUMNS)
            for _, row in df.iterrows()
        ]

        with self._connect() as conn:
            conn.executemany(query, rows)
            conn.commit()

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
        INSERT OR IGNORE INTO detector_linearity_measurements (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DETECTOR_LINEARITY_MEASUREMENT_COLUMNS)
            for _, row in df.iterrows()
        ]

        with self._connect() as conn:
            conn.executemany(query, rows)
            conn.commit()

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
        INSERT OR IGNORE INTO detector_linearity_results (
            {columns_sql}
        )
        VALUES ({placeholders})
        """

        rows = [
            tuple(row[col] for col in DETECTOR_LINEARITY_RESULT_COLUMNS)
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
        

    def load_dispersion_solution_lines(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM dispersion_solution_lines
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "order", "wavelength"
        """

        with self._connect() as conn:
            return pd.read_sql(query, conn)
        
    def load_order_location_models(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM order_location_models
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "soxspipe_recipe", "source_file"
        """

        with self._connect() as conn:
            return pd.read_sql(query, conn)


    def load_dispersion_resolution_stats(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM dispersion_resolution_stats
        ORDER BY "obs_date_utc", "eso seq arm", "order"
        """

        with self._connect() as conn:
            return pd.read_sql(query, conn)


    def load_order_location_meta(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM order_location_meta
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "soxspipe_recipe", "source_file", "order"
        """

        with self._connect() as conn:
            return pd.read_sql(query, conn)

    def load_detector_linearity_measurements(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM detector_linearity_measurements
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "detector_mode", "exptime"
        """

        with self._connect() as conn:
            return pd.read_sql(query, conn)

    def load_detector_linearity_results(self) -> pd.DataFrame:
        query = """
        SELECT *
        FROM detector_linearity_results
        ORDER BY "obs_day", "obs_date_utc", "eso seq arm", "detector_mode", "exptime"
        """

        with self._connect() as conn:
            return pd.read_sql(query, conn)


    # Wipe database

    def drop_all(self):
        with self._connect() as conn:
            conn.execute("DROP TABLE IF EXISTS qc_metrics")
            conn.execute("DROP TABLE IF EXISTS processed_obs_days")
            conn.execute("DROP TABLE IF EXISTS dispersion_solution_lines")
            conn.execute("DROP TABLE IF EXISTS processed_dispersion_obs_days")
            conn.execute("DROP TABLE IF EXISTS dispersion_resolution_stats")
            conn.execute("DROP TABLE IF EXISTS order_location_models")
            conn.execute("DROP TABLE IF EXISTS processed_order_location_obs_days")
            conn.execute("DROP TABLE IF EXISTS order_location_meta")
            conn.execute("DROP TABLE IF EXISTS detector_linearity_measurements")
            conn.execute("DROP TABLE IF EXISTS detector_linearity_results")
            conn.execute("DROP TABLE IF EXISTS processed_detector_linearity_obs_days")
            conn.commit()

        self._init_db()

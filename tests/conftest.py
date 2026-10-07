"""Synthetic H0 inputs: every configured path belongs to a temporary project."""
import atexit
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

# Set these before importing anything that imports pyplot. Collection also stays
# independent of the user's font cache and of any interactive plotting backend.
_collection_cache = tempfile.TemporaryDirectory(prefix="qc-h0-mpl-")
atexit.register(_collection_cache.cleanup)
os.environ["MPLBACKEND"] = "Agg"
os.environ["MPLCONFIGDIR"] = _collection_cache.name

import numpy as np
from astropy.io import fits
from astropy.table import Table
import pytest
import yaml

from qc_monitor.acquisition import load_qc_from_session_db
from qc_monitor.schema import TABLE_SCHEMA
from qc_monitor.storage import SQLiteStore

DAY = "2026-10-05"
REGISTERS = (
    "processed_obs_days",
    "processed_dispersion_obs_days",
    "processed_order_location_obs_days",
    "processed_detector_linearity_obs_days",
)


def rows(path, sql, parameters=()):
    """Inspection must never initialize, migrate, or create a database."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        return conn.execute(sql, parameters).fetchall()


def database_snapshot(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        return tuple(conn.iterdump())


def tree_snapshot(root):
    if not root.exists():
        return None
    result = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_dir():
            result[relative] = ("directory",)
        else:
            result[relative] = (
                "file", hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mtime_ns,
            )
    return result


def require(condition, message):
    """Preconditions/harness failures must not be swallowed by an XFAIL."""
    if not condition:
        raise RuntimeError(message)


class Lab:
    def __init__(self, tmp_path):
        self.root = tmp_path / "project"
        self.root.mkdir()
        self.cache = tmp_path / "cli-mpl-cache"
        self.cache.mkdir()
        self.upstream = self.root / "upstream" / "soxspipe.db"
        self.reduced = self.root / "reduced"
        self.products = self.reduced / DAY / "soxs-order-centres"
        self.products.mkdir(parents=True)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.db = self.root / "monitor" / "qc.sqlite"
        self.output = self.root / "published"
        self.config = self.root / "configs" / "h0.yaml"
        self.config.parent.mkdir()
        self.cfg = {
            "paths": {"upstream_root": str(self.upstream.parent),
                      "reduced_root": str(self.reduced), "qc_database": str(self.db)},
            "acquisition": {
                "upstream_database_name": "soxspipe.db",
                "upstream_table": "quality_control_plus_lite",
                "upstream_database_search": "direct",
                "allow_multiple_upstream_databases": False,
                "reduced_products_search": "observing_day_dirs",
                "allow_suspicious_paths": True,
            },
            "detector_linearity": {"enabled": False},
            "plots": {"output_dir": str(self.output / "plots"),
                      "html_output": str(self.output / "index.html"),
                      "show": False, "figures": []},
        }
        self.make_upstream(self.upstream)
        self.save_config()

    def save_config(self):
        self.config.write_text(yaml.safe_dump(self.cfg), encoding="utf-8")

    def make_upstream(self, path, metric="bias_level", day=DAY):
        path.parent.mkdir(parents=True, exist_ok=True)
        values = {key: None for key in TABLE_SCHEMA}
        values.update({"night start date": day, "obs_date_utc": day + "T08:00:00",
                       "eso seq arm": "VIS", "soxspipe_recipe": "soxs-mbias",
                       "qc_name": metric, "qc_value": 100.0, "qc_order": "-1",
                       "qc_unit": "adu", "file": metric + ".fits"})
        definitions = ", ".join(f'"{key}" {kind}' for key, kind in TABLE_SCHEMA.items())
        columns = ", ".join(f'"{key}"' for key in TABLE_SCHEMA)
        placeholders = ", ".join("?" for _ in TABLE_SCHEMA)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute(f'CREATE TABLE quality_control_plus_lite ({definitions})')
            conn.execute(f'INSERT INTO quality_control_plus_lite ({columns}) '
                         f'VALUES ({placeholders})', tuple(values.values()))
            conn.commit()
        return path

    def seed(self, legacy=False):
        store = SQLiteStore(self.db)
        sentinel = self.make_upstream(self.root / "seed.db", "sentinel", "2026-10-01")
        store.write_metrics(load_qc_from_session_db(sentinel, self.cfg))
        store.register_processed_obs_day("2026-10-01")
        if legacy:
            with closing(sqlite3.connect(self.db)) as conn:
                conn.execute('ALTER TABLE detector_linearity_results DROP COLUMN n_flat_frames')
                conn.commit()
        return store

    def publish_sentinels(self):
        (self.output / "plots").mkdir(parents=True)
        (self.output / "plots" / "existing.png").write_bytes(b"existing image sentinel")
        (self.output / "index.html").write_text("existing report sentinel", encoding="utf-8")

    def cli(self, *flags, expected=0):
        env = os.environ.copy()
        env.update(MPLBACKEND="Agg", MPLCONFIGDIR=str(self.cache),
                   PYTHONDONTWRITEBYTECODE="1")
        # Exercise this checkout, even when cwd is the temporary project.
        repo = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [repo, env.get("PYTHONPATH")]))
        result = subprocess.run(
            [sys.executable, "-m", "qc_monitor.main", "--config", str(self.config), *flags],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=60,
        )
        if expected is not None:
            require(result.returncode == expected,
                    f"CLI exit {result.returncode}; stdout={result.stdout}; stderr={result.stderr}")
        return result

    def dsol(self, stamp="080000", broken=False, stats=True):
        path = self.products / f"20261005T{stamp}_VIS_1X1_1_DSOL_PINHOLE_30_0S_SOXS_FITTED_LINES.fits"
        if broken:
            path.write_bytes(b"not a FITS file")
        else:
            table = Table({"order": [10, 10], "wavelength": [500.0, 501.0],
                           "detector_x": [1.0, 2.0], "detector_y": [3.0, 4.0],
                           "R_pin": [1000.0, 1200.0] if stats else [np.nan, np.nan]})
            fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU(table)]).writeto(path, overwrite=True)
        return path

    def oloc(self, meta=True):
        path = self.products / "20261005T080000_VIS_1X1_1_OLOC_QTH_PINHOLE_10_0S_SOXS.fits"
        model = Table({"degorder_cent": [0], "degy_cent": [0], "cent_00": [2.0]})
        hdus = [fits.PrimaryHDU(), fits.BinTableHDU(model)]
        if meta:
            hdus.append(fits.BinTableHDU(Table({"order": [10], "xmin": [0.0],
                                               "xmax": [3.0], "ymin": [0.0], "ymax": [3.0]})))
        fits.HDUList(hdus).writeto(path, overwrite=True)
        return path

    def detlin_frame(self, arm, mode, kind, time, index, signal):
        token = ("BIAS" if kind == "bias" else f"UIT{time}") if arm == "VIS" else (
            ("DARK_" if kind == "dark" else "") + f"DIT{time}")
        mode_part = mode + "_" if arm == "VIS" else ""
        name = f"SOXS_GEN_FLAT_{arm}_DETLIN_{mode_part}{token}_278_{index:04d}.fits"
        path = self.raw / name
        header = fits.Header()
        metadata = getattr(self, "detlin_headers", {}).get(name)
        if metadata:
            header["HIERARCH ESO TPL START"] = DAY + "T08:00:00"
            header["HIERARCH ESO TPL ID"] = "SOXS_gen_tec_" + arm + "DetLin"
            header["HIERARCH ESO TPL NEXP"] = metadata[0]
            header["HIERARCH ESO TPL EXPNO"] = metadata[1]
        header["DATE-OBS"] = DAY + f"T08:{time:02d}:{index:02d}"
        header["HIERARCH ESO SEQ ARM"] = arm
        # Keep the HIERARCH card within FITS' 80-character limit, including
        # the longer NIR DARK token. The parser needs the arm/DETLIN tokens.
        header[f"HIERARCH ESO OCS DET{2 if arm == 'VIS' else 1} IMGNAME"] = name.replace(
            "SOXS_GEN_FLAT", "SOXS"
        )
        header["HIERARCH ESO DET UIT1" if arm == "VIS" else "HIERARCH ESO DET SEQ1 DIT"] = time
        header["HIERARCH ESO DPR TYPE"] = "LAMP,OFF" if kind in {"bias", "dark"} else "LAMP,ON"
        header["HIERARCH ESO DET EXP TYPE"] = "Bias" if kind == "bias" else "Normal"
        # Small zero-mean patterns give nonzero pair variance without changing signal.
        pattern = np.array([[-1.0, 1.0], [1.0, -1.0]]) * index
        fits.PrimaryHDU(signal + pattern, header).writeto(path, overwrite=True)
        return path

    def detlin(self, arm="VIS", times=(1, 2)):
        self.cfg["detector_linearity"] = {
            "enabled": True, "statistic": "mean", "saturation_level": 65536,
            "saturation_fraction": 0.60,
            "arms": {arm: {"root": str(self.raw), "roi": [0, 2, 0, 2],
                           "roi_name": "synthetic", "allow_filename_fallback": False}},
        }
        modes = ("SHG", "FLG", "SLG", "FHG") if arm == "VIS" else ("NIR",)
        self.detlin_headers = {}
        planned = []
        for mode in modes:
            if arm == "VIS":
                planned.extend((mode, "bias", 0, index) for index in (1, 2, 3))
            for time in times:
                if arm == "NIR":
                    planned.append((mode, "dark", time, 1))
                planned.extend((mode, "flat", time, index) for index in (1, 2))
        for number, (mode, kind, time, index) in enumerate(planned, 1):
            token = ("BIAS" if kind == "bias" else f"UIT{time}") if arm == "VIS" else (("DARK_" if kind == "dark" else "") + f"DIT{time}")
            mode_part = mode + "_" if arm == "VIS" else ""
            name = f"SOXS_GEN_FLAT_{arm}_DETLIN_{mode_part}{token}_278_{index:04d}.fits"
            self.detlin_headers[name] = (len(planned), number)
        for mode in modes:
            if arm == "VIS":
                for index in (1, 2, 3):
                    self.detlin_frame(arm, mode, "bias", 0, index, 10.0)
            for time in times:
                if arm == "NIR":
                    self.detlin_frame(arm, mode, "dark", time, 1, 10.0)
                for index in (1, 2):
                    self.detlin_frame(arm, mode, "flat", time, index, 10.0 + 100 * time)
        self.save_config()


@pytest.fixture
def lab(tmp_path):
    return Lab(tmp_path)

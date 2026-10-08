#!/usr/bin/env python3
"""Verify an installed wheel from a temporary working directory, without source imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    repository = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["MPLBACKEND"] = "Agg"
    with tempfile.TemporaryDirectory(prefix="qc-installed-") as temporary:
        root = Path(temporary)
        env["MPLCONFIGDIR"] = str(root / "cache")
        env["XDG_CACHE_HOME"] = str(root / "cache")
        env["QC_MONITOR_ROOT"] = str(root)
        setup = '''
import json, sqlite3
from pathlib import Path
from importlib import resources
import qc_monitor
from qc_monitor.schema import TABLE_SCHEMA
root = Path.cwd()
assert not Path(qc_monitor.__file__).resolve().is_relative_to(Path(REPOSITORY))
assert resources.files("qc_monitor").joinpath("resources/template.html").read_text()
(root / "configs").mkdir()
(root / "upstream").mkdir()
(root / "reduced/2026-10-05").mkdir(parents=True)
with sqlite3.connect(root / "upstream/soxspipe.db") as conn:
    definitions = ",".join('"' + key + '" ' + kind for key, kind in TABLE_SCHEMA.items())
    conn.execute("CREATE TABLE quality_control_plus_lite (" + definitions + ")")
    values = {key: None for key in TABLE_SCHEMA}
    values.update({"night start date": "2026-10-05", "obs_date_utc": "2026-10-05T08:00:00", "eso seq arm": "VIS", "soxspipe_recipe": "soxs-mbias", "qc_name": "bias", "qc_value": 100, "qc_order": "-1"})
    columns = ",".join('"' + key + '"' for key in values)
    conn.execute("INSERT INTO quality_control_plus_lite (" + columns + ") VALUES (" + ",".join("?" for _ in values) + ")", tuple(values.values()))
cfg = {"paths": {"upstream_root": str(root / "upstream"), "reduced_root": str(root / "reduced"), "qc_database": str(root / "qc.sqlite")}, "acquisition": {"upstream_database_name": "soxspipe.db", "upstream_table": "quality_control_plus_lite", "allow_suspicious_paths": True}, "detector_linearity": {"enabled": False}, "plots": {"output_dir": str(root / "plots"), "html_output": str(root / "index.html"), "figures": []}}
(root / "configs/qc_monitor.yaml").write_text(json.dumps(cfg))
'''
        subprocess.run([sys.executable, "-I", "-c", "REPOSITORY=" + repr(str(repository)) + "\n" + setup],
                       cwd=root, env=env, check=True)
        entry = Path(sys.executable).parent / "qc-monitor"
        commands = ([str(entry), "--preflight"],
                    [sys.executable, "-I", "-m", "qc_monitor.main", "--config", str(root / "configs/qc_monitor.yaml"), "--no-plots"],
                    [str(entry), "--no-plots"])
        summaries = []
        for command in commands:
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError(result.stderr)
            lines = [line.split("RUN_SUMMARY ", 1)[1] for line in result.stderr.splitlines() if "RUN_SUMMARY " in line]
            assert len(lines) == 1, result.stderr
            summaries.append(json.loads(lines[0]))
        assert summaries[1]["families"]["qc"]["tables"]["qc_metrics"]["persisted"] == 1
        assert summaries[2]["families"]["qc"]["tables"]["qc_metrics"]["preserved"] == 1
    print("Installed wheel: entry point, isolated imports, bundled template, config and idempotent acquisition verified")


if __name__ == "__main__":
    main()

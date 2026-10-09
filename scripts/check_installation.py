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
        before = (root / 'qc.sqlite').read_bytes()
        inspect = subprocess.run([str(entry), '--dry-run'], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=60)
        assert inspect.returncode == 0, inspect.stderr
        assert (root / 'qc.sqlite').read_bytes() == before
        original = json.loads((root / 'configs/qc_monitor.yaml').read_text())
        invalid = dict(original, plots=dict(original['plots'], show='false'))
        (root / 'configs/invalid.yaml').write_text(json.dumps(invalid))
        rejected = subprocess.run([str(entry), '--config', str(root / 'configs/invalid.yaml')],
                                  cwd=root, env=env, capture_output=True, text=True, timeout=60)
        assert rejected.returncode == 2, rejected.stderr
        assert (root / 'qc.sqlite').read_bytes() == before
        rebuilt = subprocess.run([str(entry), '--rebuild-db', '--no-plots'], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=60)
        assert rebuilt.returncode == 0, rebuilt.stderr
        backups = list(root.glob('qc.sqlite.backup-*.sqlite'))
        assert len(backups) == 1
        checked = subprocess.run([sys.executable, '-I', '-c', '''
import sqlite3
from contextlib import closing
from pathlib import Path
with closing(sqlite3.connect('qc.sqlite')) as connection:
    assert connection.execute('PRAGMA user_version').fetchone() == (1,)
    assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert connection.execute('SELECT count(*) FROM qc_metrics').fetchone() == (1,)
with closing(sqlite3.connect(str(next(Path('.').glob('qc.sqlite.backup-*.sqlite'))))) as backup:
    assert backup.execute('SELECT count(*) FROM qc_metrics').fetchone() == (1,)
'''], cwd=root, env=env, capture_output=True, text=True, timeout=60)
        assert checked.returncode == 0, checked.stderr
        # D3-C: exercise the installed renderer/result module and the CLI backend
        # without inheriting the workflow's Agg setting.
        rendering = json.loads((root / 'configs/qc_monitor.yaml').read_text())
        rendering['plots']['datapoint_queries'] = {'sample': {'filters': {}}}
        rendering['plots']['figures'] = [
            {'name': 'vis_good', 'type': 'histogram', 'filename': 'good.png',
             'arm': 'VIS', 'datapoint_query': 'sample'},
            {'name': 'vis_bad', 'type': 'histogram', 'filename': 'bad.png',
             'arm': 'VIS', 'datapoint_query': 'sample'},
        ]
        (root / 'plots/bad.png').mkdir(parents=True)
        (root / 'configs/qc_monitor.yaml').write_text(json.dumps(rendering))
        env.pop('MPLBACKEND', None)
        partial = subprocess.run([str(entry)], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=60)
        assert partial.returncode == 2, partial.stderr
        diagnostic = json.loads(partial.stderr.split('RUN_SUMMARY ')[-1])
        assert diagnostic['versions']['qc-monitor'] == '1.5.0'
        assert diagnostic['plots']['counts'] == {'produced': 1, 'failed': 1, 'no_data': 0}
        assert diagnostic['report']['state'] == 'published'
        assert (root / 'plots/good.png').is_file()
        report = (root / 'index.html').read_text()
        assert 'src="plots/good.png"' in report and 'src="plots/bad.png"' not in report
        backend = subprocess.run([sys.executable, '-I', '-c', '''
import sys
from qc_monitor import main as app
from qc_monitor.figure_result import FigureResult
assert 'matplotlib.pyplot' not in sys.modules
assert app.main() == 2
import matplotlib
assert matplotlib.get_backend().lower() == 'agg'
'''], cwd=root, env=dict(env, MPLBACKEND='TkAgg'),
            capture_output=True, text=True, timeout=60)
        assert backend.returncode == 0, backend.stderr
    print("Installed wheel: isolated imports, entry point, template, validated config, idempotence, immutable dry-run, protected rebuild, partial rendering and autonomous Agg verified")


if __name__ == "__main__":
    main()

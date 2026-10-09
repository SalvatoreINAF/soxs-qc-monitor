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
        # D4: imported facades and every family implementation must be in the wheel.
        signatures = json.loads((repository / 'tests/fixtures/d4-api-signatures.json').read_text())
        verify_api = "EXPECTED=" + repr(signatures) + "\nREPOSITORY=" + repr(str(repository)) + "\n" + """
import importlib, inspect, sys
from pathlib import Path
from qc_monitor._renderers import RENDERERS
import qc_monitor.main
assert 'matplotlib.pyplot' not in sys.modules
assert len(RENDERERS) == 10
for module, expected in EXPECTED.items():
    target = (importlib.import_module('qc_monitor.storage').SQLiteStore if module == 'SQLiteStore'
              else importlib.import_module('qc_monitor.' + module))
    for name, signature in expected.items():
        assert str(inspect.signature(getattr(target, name))).replace('pathlib._local.', 'pathlib.') == signature, (module, name)
for name in ('processing', '_preflight', '_runtime', '_consolidation', '_plots_common',
             '_plots_qc', '_plots_dsol', '_plots_oloc', '_plots_detlin'):
    module = importlib.import_module('qc_monitor.' + name)
    assert not Path(module.__file__).resolve().is_relative_to(Path(REPOSITORY))
"""
        subprocess.run([sys.executable, '-I', '-W', 'error', '-c', verify_api],
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
        (root / 'configs/qc_monitor.yaml').write_text(json.dumps(rendering))
        env.pop('MPLBACKEND', None)
        partial_program = """
from pathlib import Path
from qc_monitor import main as app
original = app.generate_plots_from_config
def fail_save(frame, plots, *args, **kwargs):
    (Path(plots['output_dir']) / 'bad.png').mkdir(exist_ok=True)
    return original(frame, plots, *args, **kwargs)
app.generate_plots_from_config = fail_save
"""
        partial = subprocess.run([sys.executable, '-I', '-c', partial_program + '\nimport sys; sys.exit(app.main())'], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=60)
        assert partial.returncode == 2, partial.stderr
        diagnostic = json.loads(partial.stderr.split('RUN_SUMMARY ')[-1])
        assert diagnostic['versions']['qc-monitor'] == '1.9.0'
        assert diagnostic['plots']['counts'] == {'produced': 1, 'failed': 1, 'no_data': 0, 'reused': 0}
        assert diagnostic['report']['state'] == 'published'
        good_path = Path(diagnostic['plots']['figures'][0]['path'])
        assert good_path.is_file() and '.qc-publication' in good_path.parts
        assert not (root / 'plots/good.png').exists()
        report = (root / 'index.html').read_text()
        import re
        sources = re.findall(r'<img[^>]* src="([^"]+)"', report)
        assert len(sources) == 1 and sources[0].endswith('/plots/good.png')
        backend = subprocess.run([sys.executable, '-I', '-c', partial_program + '''
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
        assert diagnostic['publication']['state'] == 'published'
        assert diagnostic['publication']['cleanup']['retention']['limits_guaranteed'] is True
        assert len(list((root / 'plots/.qc-publication').glob('*/generations/*/manifest.json'))) == 2
        publication = subprocess.run([sys.executable, '-I', '-c', '''
import json, uuid
from pathlib import Path
import pandas as pd
from qc_monitor.config import normalize_runtime_config
from qc_monitor.plotting import generate_plots_from_config
from qc_monitor.publication import publish_report, PublicationError
from qc_monitor.run_result import RunResult
root = Path.cwd()
cfg = normalize_runtime_config(json.loads((root / 'configs/qc_monitor.yaml').read_text()), root)
cfg['plots']['output_dir'] = str(root / 'generation images')
cfg['plots']['html_output'] = str(root / 'web/current.html')
cfg['plots']['figures'] = cfg['plots']['figures'][:1]
frame = pd.DataFrame({'qc_value': [1., 2., 3.], 'eso seq arm': ['VIS'] * 3})
def publish(render):
    return publish_report(cfg, project_root=root, config_path=root / 'configs/qc_monitor.yaml',
                          run_id=str(uuid.uuid4()), render=render)
good = publish(lambda plots: generate_plots_from_config(frame, plots, continue_on_error=True))
assert good.state == 'published' and good.durability == 'confirmed'
manifest = json.loads(Path(good.manifest_path).read_text())
assert manifest['package_version'] == '1.9.0'
assert (Path(good.manifest_path).parent / 'report.html').is_file()
def failed_image(plots):
    (Path(plots['output_dir']) / plots['figures'][0]['filename']).mkdir(parents=True)
    return generate_plots_from_config(frame, plots, continue_on_error=True)
reused = publish(failed_image)
assert reused.figures[0].state == 'reused'
assert reused.figures[0].generated_utc == good.figures[0].generated_utc
assert reused.figures[0].origin_generation_id == good.generation_id
assert Path(reused.figures[0].path).read_bytes() == Path(good.figures[0].path).read_bytes()
run = RunResult('run')
reused.apply_to(run)
run.finish()
assert run.exit_code == 2 and run.plots['counts']['reused'] == 1
assert 'Original image produced (UTC)' in Path(reused.report_path).read_text()
before = Path(good.report_path).read_bytes()
def broken(plots):
    raise OSError('installed failure injection')
try:
    publish(broken)
except PublicationError as exc:
    assert exc.result.state == 'failed' and exc.result.staging_cleanup == 'removed'
    run = RunResult('run')
    exc.result.apply_to(run)
    run.finish()
    assert run.exit_code == 2
else:
    raise AssertionError('failure incorrectly published')
assert Path(good.report_path).read_bytes() == before
for _ in range(4):
    result = publish(lambda plots: generate_plots_from_config(frame, plots, continue_on_error=True))
assert result.cleanup['retention']['remaining'] == {'generations': 2, 'staging': 0}
assert not Path(good.manifest_path).exists()
'''], cwd=root, env=dict(env, MPLBACKEND='Agg'),
            capture_output=True, text=True, timeout=60)
        assert publication.returncode == 0, publication.stderr
    print("Installed wheel: isolated imports, entry point, template, config, idempotence, dry-run, rebuild, partial rendering, Agg, atomic publication/retention and compatible image reuse verified")


if __name__ == "__main__":
    main()

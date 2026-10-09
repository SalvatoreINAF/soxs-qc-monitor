"""Compare baseline/current real CLI and normalized SQLite contents on synthetic inputs.

Usage: python scripts/check_d4_equivalence.py BASELINE_CHECKOUT OUTPUT_DIRECTORY
Only supplied temporary output directories are used; no operational inputs.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

repository = Path(__file__).resolve().parents[1]
baseline = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(repository), str(repository / 'tests')]
from conftest import Lab


def snapshot(lab):
    tables = {}
    with closing(sqlite3.connect(lab.db.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        for table, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            columns = [record[1] for record in conn.execute(f'PRAGMA table_info("{table}")')
                       if record[1] != 'processed_at']
            fields = ','.join('"' + name + '"' for name in columns)
            values = conn.execute(f'SELECT {fields} FROM "{table}"').fetchall()
            tables[table] = {'columns': columns, 'rows': sorted(values, key=repr)}
    # Absolute provenance paths differ only because the projects are isolated.
    return json.loads(json.dumps(tables).replace(str(lab.root), '<PROJECT>'))


def invoke(root, lab, flags=(), fail=False):
    env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE='1',
               MPLBACKEND='Agg', MPLCONFIGDIR=str(lab.cache), XDG_CACHE_HOME=str(lab.cache))
    if fail:
        code = '''import sys
from matplotlib.figure import Figure
original = Figure.savefig
def failed(self, path, *args, **kwargs):
    if str(path).endswith('dsol.png'):
        raise OSError('D4 controlled real save failure')
    return original(self, path, *args, **kwargs)
Figure.savefig = failed
from qc_monitor.main import main
sys.exit(main())
'''
        command = [sys.executable, '-c', code]
    else:
        command = [sys.executable, '-m', 'qc_monitor.main']
    result = subprocess.run([*command, '--config', str(lab.config), *flags], cwd=lab.root,
                            env=env, capture_output=True, text=True, timeout=90)
    summaries = [json.loads(line.split('RUN_SUMMARY ', 1)[1])
                 for line in result.stderr.splitlines() if 'RUN_SUMMARY ' in line]
    assert len(summaries) == 1, result.stderr
    value = summaries[0]
    return result.returncode, value


all_results = {}
for label, root in [('baseline', baseline), ('refactored', repository)]:
    parent = output / label
    parent.mkdir()
    lab = Lab(parent)
    lab.dsol()
    lab.oloc()
    lab.detlin()
    lab.cfg['plots'].update(datapoint_queries={'sample': {'filters': {}}}, figures=[
        {'name': 'vis_qc', 'type': 'histogram', 'filename': 'qc.png', 'arm': 'VIS',
         'datapoint_query': 'sample'},
        {'name': 'vis_dsol', 'type': 'dispersion_resolution', 'filename': 'dsol.png',
         'arm': 'VIS', 'selection': 'all'},
        {'name': 'vis_detlin', 'type': 'detector_linearity', 'filename': 'detlin.png',
         'arm': 'VIS', 'selection': 'all'},
    ])
    lab.save_config()
    steps = {}
    def step(name, expected, flags=(), fail=False):
        code, value = invoke(root, lab, flags, fail)
        assert code == expected, (name, code, value)
        steps[name] = {'exit_code': code, 'tables': snapshot(lab),
                       'states': {family: data['state'] for family, data in value['families'].items()},
                       'counts': {family: data.get('tables', {}) for family, data in value['families'].items()},
                       'plots': value['plots'].get('counts', {})}
    step('nominal', 0)
    broken = lab.dsol(stamp='090000', broken=True)
    later = lab.reduced / '2026-10-06' / 'soxs-order-centres' / broken.name.replace('20261005', '20261006')
    later.parent.mkdir(parents=True)
    broken.rename(later)
    step('incomplete', 1)
    step('save_failure_reuse', 2, fail=True)
    repaired = lab.dsol(stamp='090000')
    later.write_bytes(repaired.read_bytes())
    repaired.unlink()
    step('repair_retry', 0)
    step('idempotent', 0)
    step('dry_run', 0, ('--dry-run',))
    step('rebuild', 0, ('--rebuild-db',))
    all_results[label] = steps
assert all_results['baseline'] == all_results['refactored']
result = {'baseline_sha': 'ddf67a85793e8dd64bbac19fe29e7a84634b89f0',
          'equivalent': True, 'steps': list(all_results['baseline']),
          'comparisons': all_results}
(output / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
print('D4 baseline/current CLI and SQL equivalent:', ', '.join(result['steps']))

"""D3-B: actual process barriers and isolated operational resources."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from conftest import Lab, tree_snapshot, database_snapshot
from qc_monitor.coordination import (leases, runtime_requests, resource_requests,
                                    config_resources, CoordinationBusyError)
from qc_monitor.locking import writer_lease
from qc_monitor.config import load_config, normalize_runtime_config
from qc_monitor.storage import SQLiteStore


@contextmanager
def holder(requests):
    program = '''
import json, sys
from qc_monitor.coordination import leases
with leases(json.loads(sys.argv[1])):
    print('ready', flush=True)
    sys.stdin.read()
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', program, json.dumps(requests)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'ready'
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=10)


@pytest.mark.parametrize('flags', [(), ('--rebuild-db',)])
def test_project_contention_preserves_summary_and_all_data(lab, flags):
    summary = lab.root / 'summary.json'
    summary.write_text('previous summary')
    before = tree_snapshot(lab.root)
    with holder([('project', str(lab.root), True)]):
        started = time.monotonic()
        result = lab.cli('--summary-json', str(summary), *flags, expected=2)
        assert time.monotonic() - started < 5
    assert tree_snapshot(lab.root) == before
    diagnostic = json.loads(result.stderr.split('RUN_SUMMARY ')[-1])
    assert diagnostic['coordination']['conflict_resource'].startswith('project:')


@pytest.mark.parametrize('kind', ['environment', 'source'])
def test_update_exclusive_rejects_cli_and_api_before_writes(lab, kind):
    request = next(item for item in runtime_requests(update=True) if item[0] == kind)
    before = tree_snapshot(lab.root)
    with holder([request]):
        lab.cli('--no-plots', expected=2)
        with pytest.raises(CoordinationBusyError):
            SQLiteStore(lab.db)
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize('target', ['database', 'html', 'png', 'directory', 'nested', 'alias'])
def test_shared_destinations_rejected_across_projects(lab, tmp_path, target):
    cfg = normalize_runtime_config(load_config(lab.config), lab.root, validated=True)
    if target == 'database':
        requests = resource_requests(files=[lab.db])
    elif target == 'html':
        requests = resource_requests(files=[cfg['plots']['html_output']])
    elif target == 'png':
        requests = resource_requests(files=[Path(cfg['plots']['output_dir']) / 'sample.png'])
    elif target == 'directory':
        requests = resource_requests(directories=[cfg['plots']['output_dir']])
    elif target == 'nested':
        requests = resource_requests(directories=[Path(cfg['plots']['output_dir']) / 'child'])
    else:
        alias = tmp_path / 'alias'
        alias.symlink_to(lab.root, target_is_directory=True)
        requests = resource_requests(files=[alias / 'monitor/qc.sqlite'])
    before = tree_snapshot(lab.root)
    with holder(requests):
        lab.cli(expected=2)
    assert tree_snapshot(lab.root) == before


def test_independent_projects_share_runtime(lab, tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    independent = Lab(other)
    cfg = normalize_runtime_config(load_config(lab.config), lab.root, validated=True)
    with holder(runtime_requests() + [('project', str(lab.root), True)] + config_resources(cfg)):
        independent.cli('--no-plots')
    assert independent.db.exists()


@pytest.mark.parametrize('flags', [('--preflight',), ('--dry-run',)])
def test_inspections_ignore_operational_update_leases(lab, flags):
    before = tree_snapshot(lab.root)
    with holder(runtime_requests(update=True) + [('project', str(lab.root), True)]):
        lab.cli(*flags)
    assert tree_snapshot(lab.root) == before


def test_partial_acquisition_released_and_killed_owner_released(tmp_path):
    first, second = tmp_path / 'a', tmp_path / 'b'
    with holder(resource_requests(files=[second])) as process:
        with pytest.raises(CoordinationBusyError):
            with leases(resource_requests(files=[first, second])):
                pytest.fail('must contend')
        with holder(resource_requests(files=[first])):
            pass
        process.kill()
        process.wait(timeout=10)
        with leases(resource_requests(files=[second])):
            pass


def test_reentrancy_and_forbidden_promotion(tmp_path):
    path = str(tmp_path / 'resource')
    with leases([('resource', path, True)]):
        with leases([('resource', path, False)]), leases([('resource', path, True)]):
            pass
    with leases([('resource', path, False)]):
        with pytest.raises(CoordinationBusyError):
            with leases([('resource', path, True)]):
                pass
    with writer_lease(tmp_path / 'db'):
        with writer_lease(tmp_path / 'db'):
            pass


@pytest.mark.parametrize('phase', ['plots', 'html', 'summary'])
def test_run_keeps_protection_through_publication(lab, phase):
    # D3-C skips rendering/publication when there are no figures. Exercise real
    # configured work instead of relying on an empty generator call.
    lab.cfg['plots'].update(datapoint_queries={'sample': {'filters': {}}}, figures=[{
        'name': 'vis_protection', 'type': 'histogram', 'filename': 'sample.png',
        'arm': 'VIS', 'datapoint_query': 'sample'}])
    lab.save_config()
    # Run the real application, pausing only the selected boundary via stdin.
    program = '''
import sys
import qc_monitor.main as app
from qc_monitor import publication as pub
phase = sys.argv[2]
def pause(*args, **kwargs):
    print('ready', flush=True)
    sys.stdin.read(1)
if phase == 'plots': app.generate_plots_from_config = pause
elif phase == 'html': pub._render_html_report = pause
else: app.write_summary = pause
sys.argv = ['qc-monitor', '--config', sys.argv[1], '--summary-json', sys.argv[3]]
sys.exit(app.main())
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', program, str(lab.config), phase, str(lab.root / 'summary.json')],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'ready'
        before = tree_snapshot(lab.root)
        lab.cli('--no-plots', expected=2)
        with pytest.raises(CoordinationBusyError):
            SQLiteStore(lab.db)
        assert tree_snapshot(lab.root) == before
    finally:
        process.terminate()
        process.communicate(timeout=10)
    lab.cli('--no-plots')


def test_inherited_descriptor_keeps_protection_after_parent_dies(tmp_path):
    resource = str(tmp_path / 'resource')
    program = '''
import subprocess, sys
from qc_monitor.coordination import leases
with leases([('resource', sys.argv[1], True)]) as fds:
    subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'], pass_fds=fds,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('ready', flush=True)
    sys.stdin.read()
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', program, resource],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'ready'
        process.kill()
        process.wait(timeout=10)
        with pytest.raises(CoordinationBusyError):
            with leases([('resource', resource, True)]):
                pass
        # Closing the pipe lets the surviving child finish and release its fd.
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 10
        while True:
            try:
                with leases([('resource', resource, True)]):
                    break
            except CoordinationBusyError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(.01)
    finally:
        process.communicate(timeout=10)

@pytest.mark.parametrize('failure', ['none', 'style', 'paths', 'pull', 'install', 'preflight', 'dry-run', 'backup'])
def test_update_real_checks_and_backup(lab, monkeypatch, failure):
    import importlib.util
    import shutil
    import yaml
    spec = importlib.util.spec_from_file_location('d3b_batch', Path(__file__).resolve().parents[1] / 'scripts/batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    if failure == 'none':
        lab.seed()
    # A synthetic repository supplies actual backup provenance without network.
    for command in (["git", "init", "-q"], ["git", "add", "configs"],
                    ["git", "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(command, cwd=lab.root, check=True, capture_output=True)
    shutil.copyfile(lab.config, lab.config.parent / 'qc_monitor.yaml')
    monkeypatch.setenv('QC_MONITOR_ROOT', str(lab.root))
    monkeypatch.setenv('MPLBACKEND', 'Agg')
    repo = str(Path(__file__).resolve().parents[1])
    monkeypatch.setenv('PYTHONPATH', repo)
    real_execute = batch.execute
    calls = []
    def execute(command, root, stream, deadline, **kwargs):
        calls.append(command)
        assert kwargs.get('pass_fds')
        if command[0] == 'git':
            if failure == 'paths':
                cfg = yaml.safe_load((lab.config.parent / 'qc_monitor.yaml').read_text())
                cfg['plots']['html_output'] = str(lab.root / 'different.html')
                (lab.config.parent / 'qc_monitor.yaml').write_text(yaml.safe_dump(cfg))
            if failure == 'style':
                cfg = yaml.safe_load((lab.config.parent / 'qc_monitor.yaml').read_text())
                cfg['plots']['datapoint_queries'] = {'updated': {'filters': {'qc_name': 'bias_level'}}}
                (lab.config.parent / 'qc_monitor.yaml').write_text(yaml.safe_dump(cfg))
            return 1 if failure == 'pull' else 0
        if command[1:3] == ['-m', 'pip']:
            return 1 if failure == 'install' else 0
        if (failure == 'preflight' and '--preflight' in command) or (failure == 'dry-run' and '--dry-run' in command):
            # A genuine missing-input error in the real child, not a fake exit.
            lab.upstream.unlink()
        return real_execute(command, root, stream, deadline, **kwargs)
    monkeypatch.setattr(batch, 'execute', execute)
    if failure == 'backup':
        def fail_backup(*args):
            raise OSError('induced backup failure')
        monkeypatch.setattr(batch, 'backup', fail_backup)
    before = tree_snapshot(lab.db.parent)
    assert batch.main(['update', '--root', str(lab.root)]) == (0 if failure in ('none', 'style') else 2)
    if failure == 'none':
        assert tree_snapshot(lab.db.parent) == before
    else:
        assert not lab.db.exists()
        assert set((tree_snapshot(lab.db.parent) or {})) <= {'qc.sqlite.lock'}
    if failure != 'backup':
        backups = list((lab.root / 'logs').glob('backup_*'))
        assert len(backups) == 1
        manifest = json.loads((backups[0] / 'configuration-provenance.json').read_text())
        assert manifest[0]['source'] == str(lab.config.parent / 'qc_monitor.yaml')
        if failure == 'none':
            assert database_snapshot(backups[0] / 'qc.sqlite') == database_snapshot(lab.db)
    if failure in ('paths', 'pull', 'backup'):
        assert not any(command[1:3] == ['-m', 'pip'] for command in calls)
    with leases(runtime_requests(update=True) + [('project', str(lab.root), True)]):
        pass


def test_update_update_and_run_update_contention(lab, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location('d3b_contending_batch', Path(__file__).resolve().parents[1] / 'scripts/batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    monkeypatch.setenv('QC_MONITOR_ROOT', str(lab.root))
    monkeypatch.setenv('MPLBACKEND', 'Agg')
    for update in (False, True):
        before = tree_snapshot(lab.config.parent)
        with holder(runtime_requests(update=update) + [('project', str(lab.root), True)]):
            assert batch.main(['update', '--root', str(lab.root)]) == 2
        assert tree_snapshot(lab.config.parent) == before
    assert not list((lab.root / 'logs').glob('backup_*'))


def test_lock_symlinks_rejected_without_touching_target(tmp_path, monkeypatch):
    import hashlib
    import qc_monitor.coordination as coordination
    registry = tmp_path / 'registry'
    registry.mkdir(mode=0o700)
    monkeypatch.setattr(coordination, '_registry', lambda: registry)
    path = str(tmp_path / 'resource')
    name = hashlib.sha256(('resource\0' + path).encode()).hexdigest() + '.lock'
    target = tmp_path / 'sentinel'
    target.write_text('untouched')
    (registry / name).symlink_to(target)
    with pytest.raises(OSError):
        with leases([('resource', path, True)]):
            pass
    assert target.read_text() == 'untouched'


def test_timeout_kills_descendant_after_leader_exits(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('timeout_batch', Path(__file__).resolve().parents[1] / 'scripts/batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    resource = str(tmp_path / 'timeout-resource')
    # Child ignores TERM; its parent uses the normal TERM handler.
    child = "import signal, sys; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('child-ready', flush=True); __import__('time').sleep(30)"
    program = "from qc_monitor.coordination import leases; import subprocess,sys,time\nwith leases([('resource', sys.argv[1], True)]) as fds:\n subprocess.Popen([sys.executable,'-c',sys.argv[2]], pass_fds=fds, stdin=subprocess.PIPE)\n time.sleep(30)\n"
    with (tmp_path / 'timeout.log').open('w') as stream:
        with pytest.raises(subprocess.TimeoutExpired):
            batch.execute([sys.executable, '-c', program, resource, child], tmp_path, stream, time.monotonic() + 1)
    assert 'child-ready' in (tmp_path / 'timeout.log').read_text()
    with leases([('resource', resource, True)]):
        pass


def test_direct_api_reads_obey_update_guard(lab):
    store = SQLiteStore(lab.db)
    with holder(runtime_requests(update=True)):
        with pytest.raises(CoordinationBusyError):
            store.load_all_metrics()
        # Explicit read-only inspection retains its no-lock contract.
        assert SQLiteStore(lab.db, read_only=True).load_all_metrics().empty


@pytest.mark.parametrize('suffix', ['.lock', '-wal', '-shm', '-journal'])
def test_archive_sidecars_protected(lab, suffix):
    before = tree_snapshot(lab.root)
    with holder(resource_requests(files=[str(lab.db) + suffix])):
        lab.cli('--no-plots', expected=2)
    assert tree_snapshot(lab.root) == before


def test_external_include_conflicts_with_publication(lab, tmp_path):
    include = tmp_path / 'external.yaml'
    include.write_text('datapoint_queries: {external: {filters: {}}}')
    lab.cfg['plots']['include'] = [str(include)]
    lab.save_config()
    with holder(resource_requests(files=[include])):
        lab.cli('--no-plots', expected=2)
    assert not lab.db.exists()


def test_parent_project_excludes_nested_operational_project(lab):
    before = tree_snapshot(lab.root)
    with holder([('project', str(lab.root.parent), True)]):
        lab.cli('--no-plots', expected=2)
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize('state', ['Z', 'Z+', 'X'])
def test_group_wait_ignores_dead_processes(monkeypatch, state):
    import importlib.util
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('group_wait', Path(__file__).resolve().parents[1] / 'scripts/batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    monkeypatch.setattr(batch.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=f'123 {state}\n456 S\n'))
    batch.wait_process_group(123)


def test_group_wait_is_bounded(monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('group_bound', Path(__file__).resolve().parents[1] / 'scripts/batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    monkeypatch.setattr(batch.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='123 S\n'))
    with pytest.raises(TimeoutError, match='did not terminate'):
        batch.wait_process_group(123, timeout=.03)


def test_timeout_waits_for_deferred_child_termination(tmp_path, monkeypatch):
    import importlib.util
    import signal
    import threading
    spec = importlib.util.spec_from_file_location('deferred_batch', Path(__file__).resolve().parents[1] / 'scripts/batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    resource = str(tmp_path / 'deferred-resource')
    child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(30)"
    program = "from qc_monitor.coordination import leases; import subprocess,sys,time\nwith leases([('resource',sys.argv[1],True)]) as fds:\n subprocess.Popen([sys.executable,'-c',sys.argv[2]],pass_fds=fds)\n time.sleep(30)\n"
    real_killpg = os.killpg
    timers = []
    def defer(group, sig):
        if sig == signal.SIGKILL:
            timer = threading.Timer(.15, real_killpg, args=(group, sig))
            timers.append(timer)
            timer.start()
        else:
            real_killpg(group, sig)
    monkeypatch.setattr(os, 'killpg', defer)
    try:
        with (tmp_path / 'deferred.log').open('w') as stream:
            with pytest.raises(subprocess.TimeoutExpired):
                batch.execute([sys.executable, '-c', program, resource, child], tmp_path, stream, time.monotonic()+1)
        assert timers and not timers[0].is_alive()
        assert 'ready' in (tmp_path / 'deferred.log').read_text()
        with leases([('resource', resource, True)]):
            pass
    finally:
        for timer in timers:
            timer.join(timeout=2)

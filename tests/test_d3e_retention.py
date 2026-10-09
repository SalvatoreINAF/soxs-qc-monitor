"""D3-E: safe retention, startup recovery and CLI activation on temporary data."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import uuid

import pytest

from qc_monitor import publication as pub
from qc_monitor.config import normalize_runtime_config, ConfigurationError
from qc_monitor.run_result import RunResult
from conftest import tree_snapshot, database_snapshot
from test_d3d_publication import configuration, publish, render, root_of, references, CHILD, legacy_manifest
from test_d3c_rendering import configure_cli, summary


@pytest.fixture
def setup(tmp_path):
    return configuration(tmp_path / 'project')


def orphan(setup, kind='staging', *, age=0, identifier=None):
    cfg, _ = setup
    root = root_of(cfg)
    identifier = identifier or str(uuid.uuid4())
    path = root / kind / identifier
    path.mkdir()
    marker = {'owner': pub.OWNER, 'format_version': 1, 'kind': 'generation',
              'report_id': root.name, 'report_path': cfg['plots']['html_output'],
              'generation_id': identifier,
              'prepared_utc': (datetime.now(timezone.utc) - timedelta(hours=age)).isoformat()}
    (path / '.owner.json').write_text(json.dumps(marker))
    (path / 'payload').write_text('orphan payload')
    return path


@pytest.mark.parametrize('policy', [
    {'retained_generations': 1}, {'retained_generations': 2.0}, {'retained_generations': True},
    {'retained_generations': '2'}, {'max_orphan_staging': -1}, {'max_orphan_staging': 1.5},
    {'max_orphan_staging': False}, {'orphan_max_age_hours': 0}, {'orphan_max_age_hours': -1},
    {'orphan_max_age_hours': float('inf')}, {'orphan_max_age_hours': float('nan')},
    {'orphan_max_age_hours': True}, {'unknown': 1}, None, [], 'invalid'])
def test_policy_rejected_before_writes(setup, policy):
    cfg, config = setup
    cfg['plots']['publication'] = policy
    before = tree_snapshot(config.parent.parent)
    with pytest.raises(ConfigurationError):
        normalize_runtime_config(cfg, config.parent.parent)
    assert tree_snapshot(config.parent.parent) == before


def test_partial_policy_defaults_are_independent(setup):
    cfg, config = setup
    cfg['plots']['publication'] = {'max_orphan_staging': 0, 'orphan_max_age_hours': .5}
    normal = normalize_runtime_config(cfg, config.parent.parent)
    assert normal['plots']['publication'] == {'retained_generations': 2,
        'max_orphan_staging': 0, 'orphan_max_age_hours': .5}
    cfg['plots'].pop('publication')
    assert normalize_runtime_config(cfg, config.parent.parent)['plots']['publication']['max_orphan_staging'] == 2


@pytest.mark.parametrize('count', [2, 4])
def test_many_publications_keep_published_prefix_and_all_html_images(setup, count):
    cfg, _ = setup
    cfg['plots']['publication']['retained_generations'] = count
    results = [publish(setup) for _ in range(8)]
    surviving = set(path.name for path in (root_of(cfg) / 'generations').iterdir() if path.is_dir())
    assert surviving == {result.generation_id for result in results[-count:]}
    assert results[-1].cleanup['retention']['remaining'] == {'generations': count, 'staging': 0}
    for result in results[-count:]:
        archive = Path(result.manifest_path).parent / 'report.html'
        assert all(path.is_file() for path in references(archive))
    assert all(path.is_file() for path in references(Path(cfg['plots']['html_output'])))
    # Oldest retained manifest deliberately still refers to a deleted predecessor.
    pub.validate_publication(cfg, config_path=setup[1])


@pytest.mark.parametrize('limit', [0, 1, 2, 5])
def test_orphan_age_then_count_and_uuid_tie_break_ignores_mtime(setup, limit, monkeypatch):
    publish(setup)
    cfg, _ = setup
    cfg['plots']['publication']['max_orphan_staging'] = limit
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    monkeypatch.setattr(pub, 'utc_now', lambda: now.isoformat())
    paths = []
    for index, age in enumerate([24, 25, 1, 1, 1]):
        path = orphan(setup, identifier=str(uuid.UUID(int=index + 1)))
        marker = json.loads((path / '.owner.json').read_text())
        marker['prepared_utc'] = (now - timedelta(hours=age)).isoformat()
        (path / '.owner.json').write_text(json.dumps(marker))
        os.utime(path, (index, index))
        paths.append(path)
    result = publish(setup)
    expected = paths[2:][-limit:] if limit else []
    assert [path for path in paths if path.exists()] == expected
    assert result.cleanup['startup']['removed']['staging'] == 5 - len(expected)
    assert result.cleanup['startup']['limits_guaranteed'] is True


def test_finalized_and_partially_cleaned_orphans_removed_without_manifest(setup):
    publish(setup)
    path = orphan(setup, 'generations')
    result = publish(setup)
    assert not path.exists()
    assert result.cleanup['startup']['removed']['generations'] == 1


@pytest.mark.parametrize('point', ['staging', 'finalised', 'committed'])
def test_sigkill_recovery_protects_published_history(setup, point):
    cfg, config = setup
    first = publish(setup)
    cfg['plots']['publication']['max_orphan_staging'] = 0
    config.write_text(json.dumps(cfg))
    program = CHILD
    if point == 'committed':
        program = program.replace("pub.publish_report(cfg,", """original_cleanup = pub._cleanup

def pause_cleanup(root, identity, current, policy, run_id, diagnostic):
    if current == run_id: wait()
    return original_cleanup(root, identity, current, policy, run_id, diagnostic)
pub._cleanup = pause_cleanup
pub.publish_report(cfg,""")
    child = subprocess.Popen([sys.executable, '-u', '-c', program, str(config), point],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([child.stdout], [], [], 30)
        assert ready and child.stdout.readline().strip() == 'READY'
        committed = pub._marker(Path(cfg['plots']['html_output']).read_text())['generation_id']
        child.kill()
        child.communicate(timeout=10)
        next_result = publish(setup)
        assert next_result.previous_generation_id == committed
        assert next_result.cleanup['startup']['remaining']['staging'] == 0
        generations = list((root_of(cfg) / 'generations').glob('*/manifest.json'))
        assert len(generations) == 2
        if point == 'committed':
            assert not Path(first.manifest_path).exists()
        else:
            assert Path(first.manifest_path).is_file()
    finally:
        if child.poll() is None: child.kill()
        child.communicate(timeout=10)


@pytest.mark.parametrize('corruption', ['report', 'uuid', 'time', 'extra', 'boolean', 'json', 'symlink', 'hardlink'])
def test_unsafe_owned_candidate_preserved_and_blocks_cleanup(setup, corruption):
    cfg, _ = setup
    publish(setup)
    html = Path(cfg['plots']['html_output'])
    before = html.read_bytes()
    path = orphan(setup, age=30)
    owner = path / '.owner.json'
    marker = json.loads(owner.read_text())
    if corruption == 'report': marker['report_id'] = 'other'
    elif corruption == 'uuid': marker['generation_id'] = str(uuid.uuid4())
    elif corruption == 'time': marker['prepared_utc'] = '2026-10-09T00:00:00'
    elif corruption == 'extra': marker['extra'] = 1
    elif corruption == 'boolean': marker['format_version'] = True
    owner.write_text(json.dumps(marker))
    if corruption == 'json': owner.write_text('broken JSON')
    if corruption in ('symlink', 'hardlink'):
        target = path.parent / 'external-marker'
        target.write_bytes(owner.read_bytes())
        owner.unlink()
        if corruption == 'symlink': owner.symlink_to(target)
        else: os.link(target, owner)
    with pytest.raises(pub.PublicationError) as caught:
        publish(setup)
    result = caught.value.result
    assert result.phase == 'startup_cleanup'
    assert result.cleanup['startup']['limits_guaranteed'] is False
    assert (path / 'payload').read_text() == 'orphan payload'
    assert html.read_bytes() == before


def test_foreign_files_legacy_backups_other_report_and_symlink_targets_untouched(setup):
    cfg, config = setup
    first = publish(setup)
    root = root_of(cfg)
    foreign = root / 'staging' / str(uuid.uuid4())
    foreign.mkdir()
    (foreign / 'sentinel').write_text('foreign')
    similar = root / 'generations' / 'similar-name'
    similar.mkdir()
    (similar / '.owner.json').write_text('invalid but foreign name')
    legacy = Path(cfg['plots']['output_dir']) / 'legacy.png'
    legacy.write_bytes(b'legacy')
    backup = config.parent.parent / 'archive-backup.sqlite'
    backup.write_bytes(b'backup')
    external = config.parent.parent / 'external'
    external.mkdir()
    (external / 'sentinel').write_text('external')
    owned = orphan(setup, age=30)
    (owned / 'link').symlink_to(external, target_is_directory=True)
    other = deepcopy(cfg)
    other['plots']['html_output'] = str(Path(cfg['plots']['html_output']).with_name('other.html'))
    other_result = publish((other, config))
    snapshots = {path: tree_snapshot(path) for path in (foreign, similar, external, Path(other_result.manifest_path).parent)}
    result = publish(setup)
    assert not owned.exists()
    assert snapshots == {path: tree_snapshot(path) for path in snapshots}
    assert legacy.read_bytes() == b'legacy' and backup.read_bytes() == b'backup'
    assert Path(first.manifest_path).is_file()
    assert result.cleanup['startup']['ignored'] == {'generations': 1, 'staging': 1}


@pytest.mark.parametrize('phase', ['startup', 'retention'])
def test_cleanup_failure_preserves_report_boundary_and_is_recoverable(setup, monkeypatch, phase):
    cfg, _ = setup
    results = [publish(setup), publish(setup)]
    extra = orphan(setup, 'generations') if phase == 'startup' else None
    html = Path(cfg['plots']['html_output'])
    before = html.read_bytes()
    original = pub._remove_owned
    target = extra or Path(results[0].manifest_path).parent
    def blocked(path, identity):
        if path == target: raise PermissionError('cleanup denied')
        return original(path, identity)
    monkeypatch.setattr(pub, '_remove_owned', blocked)
    with pytest.raises(pub.PublicationError) as caught:
        publish(setup)
    result = caught.value.result
    assert result.cleanup[phase]['state'] == 'failed'
    assert result.cleanup[phase]['limits_guaranteed'] is False
    assert result.state == ('failed' if phase == 'startup' else 'published')
    assert (html.read_bytes() == before) == (phase == 'startup')
    assert all(path.is_file() for path in references(html))
    run = RunResult('run'); result.apply_to(run); run.finish()
    assert run.exit_code == 2 and run.publication['state'] == result.state
    monkeypatch.setattr(pub, '_remove_owned', original)
    assert publish(setup).cleanup['retention']['limits_guaranteed'] is True


@pytest.mark.parametrize('kind', ['staging', 'generations'])
def test_run_collision_never_cleaned(setup, kind):
    publish(setup)
    path = orphan(setup, kind, age=30)
    before = tree_snapshot(root_of(setup[0]))
    with pytest.raises(pub.PublicationError):
        publish(setup, run_id=path.name)
    assert tree_snapshot(root_of(setup[0])) == before


@pytest.mark.parametrize('damage', ['archive', 'png', 'missing', 'cycle'])
def test_retained_history_damage_stops_before_deletions(setup, damage):
    first = publish(setup)
    legacy_manifest(first)
    second = publish(setup)
    path = Path(first.manifest_path).parent
    if damage == 'archive': (path / 'report.html').write_text('<img src="outside.png">')
    elif damage == 'png': next((path / 'plots').rglob('*.png')).write_bytes(b'broken')
    elif damage == 'missing': (path / 'manifest.json').unlink()
    else:
        manifest = json.loads((path / 'manifest.json').read_text())
        manifest['previous_generation_id'] = second.generation_id
        (path / 'manifest.json').write_text(json.dumps(manifest))
    extra = orphan(setup, age=30)
    before = tree_snapshot(root_of(setup[0]))
    with pytest.raises(pub.PublicationError): publish(setup)
    assert extra.exists() and tree_snapshot(root_of(setup[0])) == before


@pytest.mark.parametrize('flag', ['--no-plots', '--dry-run', '--preflight'])
def test_cli_inspection_preserves_existing_orphans(lab, flag):
    configure_cli(lab)
    lab.cli()
    cfg = normalize_runtime_config(lab.cfg, lab.root)
    path = orphan((cfg, lab.config), age=30)
    before = tree_snapshot(lab.output)
    data = summary(lab.cli(flag))
    assert tree_snapshot(lab.output) == before and path.exists()
    assert data['publication']['state'] == 'skipped'


@pytest.mark.parametrize('target', ['summary', 'database', 'input', 'owner', 'current'])
def test_cli_unsafe_publication_rejected_before_archive_writes(lab, target):
    configure_cli(lab)
    lab.seed()
    if target in ('owner', 'current'):
        lab.cli()
        cfg = normalize_runtime_config(lab.cfg, lab.root)
        if target == 'owner': (root_of(cfg) / '.owner.json').write_text('invalid')
        else: Path(cfg['plots']['html_output']).write_text('<!-- qc-publication-v1:invalid -->')
    elif target == 'database':
        lab.cfg['plots']['output_dir'] = str(lab.db.parent)
        lab.cfg['plots']['html_output'] = str(lab.db)
        lab.save_config()
    elif target == 'input':
        lab.cfg['plots']['output_dir'] = str(lab.upstream.parent)
        lab.save_config()
    before = database_snapshot(lab.db)
    flags = ['--summary-json', str(Path(lab.cfg['plots']['output_dir']) / '.qc-publication/summary.json')] if target == 'summary' else []
    result = lab.cli(*flags, expected=2)
    assert database_snapshot(lab.db) == before
    assert summary(result)['exit_code'] == 2


def test_cli_cleanup_failure_keeps_committed_acquisition(lab):
    configure_cli(lab)
    lab.cli()
    cfg = normalize_runtime_config(lab.cfg, lab.root)
    path = orphan((cfg, lab.config), 'generations')
    lab.upstream.unlink()
    lab.make_upstream(lab.upstream, 'new_metric', '2026-10-06')
    program = '''
import sys
from qc_monitor import main as app, publication as pub
original = pub._remove_owned
def fail(path, identity):
    raise PermissionError('cleanup denied')
pub._remove_owned = fail
sys.exit(app.main())
'''
    result = subprocess.run([sys.executable, '-c', program, '--config', str(lab.config)],
        cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(), capture_output=True, text=True, timeout=60)
    assert result.returncode == 2, result.stderr
    data = summary(result)
    assert data['families']['qc']['tables']['qc_metrics']['persisted'] == 1
    assert data['publication']['state'] == 'failed' and path.exists()
    assert data['publication']['cleanup']['startup']['state'] == 'failed'


def test_increasing_retention_grows_available_history_without_requiring_deleted_images(setup):
    cfg, _ = setup
    results = [publish(setup) for _ in range(4)]
    cfg['plots']['publication']['retained_generations'] = 4
    result = publish(setup)
    assert result.cleanup['retention']['remaining']['generations'] == 3
    result = publish(setup)
    assert result.cleanup['retention']['remaining']['generations'] == 4
    cfg['plots']['publication']['retained_generations'] = 2
    result = publish(setup)
    assert result.cleanup['retention']['remaining']['generations'] == 2
    cfg['plots']['publication']['retained_generations'] = 4
    assert publish(setup).cleanup['retention']['remaining']['generations'] == 3
    assert not Path(results[0].manifest_path).exists()


@pytest.mark.parametrize('phase', ['startup', 'retention'])
def test_cleanup_directory_sync_failure_reports_actual_remaining_count(setup, monkeypatch, phase):
    cfg, _ = setup
    first, second = publish(setup), publish(setup)
    target = orphan(setup, 'generations') if phase == 'startup' else Path(first.manifest_path).parent
    remove = pub._remove_owned
    def sync_failure(path, identity):
        if path != target: return remove(path, identity)
        original = pub.os.fsync
        parent = path.parent.stat()
        def fail_parent(fd):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == (parent.st_dev, parent.st_ino):
                raise OSError('cleanup parent sync failed')
            original(fd)
        with monkeypatch.context() as patch:
            patch.setattr(pub.os, 'fsync', fail_parent)
            return remove(path, identity)
    monkeypatch.setattr(pub, '_remove_owned', sync_failure)
    with pytest.raises(pub.PublicationError) as caught: publish(setup)
    diagnostic = caught.value.result.cleanup[phase]
    assert diagnostic['limits_guaranteed'] is False and diagnostic['removed']['generations'] == 1
    assert diagnostic['remaining']['generations'] == 2
    assert not target.exists()
    assert all(path.is_file() for path in references(Path(cfg['plots']['html_output'])))


@pytest.mark.parametrize('point', ['startup', 'retention'])
def test_real_contender_rejected_while_cleanup_holds_leases(setup, point):
    cfg, config = setup
    publish(setup)
    config.write_text(json.dumps(cfg))
    child_code = CHILD.replace("pub.publish_report(cfg,", """original_cleanup = pub._cleanup

def pause_cleanup(root, identity, current, policy, run_id, diagnostic):
    if (current == run_id) == (point == 'retention'): wait()
    return original_cleanup(root, identity, current, policy, run_id, diagnostic)
pub._cleanup = pause_cleanup
pub.publish_report(cfg,""")
    child = subprocess.Popen([sys.executable, '-u', '-c', child_code, str(config), point],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([child.stdout], [], [], 30)
        assert ready and child.stdout.readline().strip() == 'READY'
        with pytest.raises(pub.PublicationError) as caught: publish(setup)
        assert caught.value.result.errors[0]['type'] == 'CoordinationBusyError'
        _, errors = child.communicate(input='go\n', timeout=30)
        assert child.returncode == 0, errors
        assert publish(setup).state == 'published'
    finally:
        if child.poll() is None: child.kill()
        child.communicate(timeout=10)


def test_real_permission_failure_preserves_marker_and_current_report(setup):
    if os.geteuid() == 0: pytest.skip('root bypasses directory permissions')
    cfg, _ = setup
    publish(setup)
    path = orphan(setup, 'generations')
    before = Path(cfg['plots']['html_output']).read_bytes()
    path.chmod(0o500)
    try:
        with pytest.raises(pub.PublicationError) as caught: publish(setup)
        assert caught.value.result.cleanup['startup']['state'] == 'failed'
        assert (path / '.owner.json').exists()
        assert Path(cfg['plots']['html_output']).read_bytes() == before
    finally:
        path.chmod(0o700)
    assert publish(setup).state == 'published'


def test_summary_lexically_inside_namespace_cannot_escape_through_symlink(lab):
    configure_cli(lab)
    lab.cli()
    cfg = normalize_runtime_config(lab.cfg, lab.root)
    target = root_of(cfg) / 'diagnostic.json'
    outside = lab.root / 'outside.json'
    outside.write_text('outside sentinel')
    target.symlink_to(outside)
    before = database_snapshot(lab.db)
    lab.cli('--summary-json', str(target), expected=2)
    assert outside.read_text() == 'outside sentinel'
    assert database_snapshot(lab.db) == before

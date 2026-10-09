"""Publication invariants using real PNGs, real child processes, and temporary I/O."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
from urllib.parse import unquote
import uuid

from PIL import Image
import pandas as pd
import pytest

from qc_monitor.config import normalize_runtime_config
from qc_monitor.coordination import (leases, runtime_requests, project_requests,
                                    config_resources, configuration_requests)
from qc_monitor.figure_result import FigureResult
from qc_monitor.generate_html import generate_html_report
from qc_monitor import publication as pub
from qc_monitor.run_result import RunResult
from test_scientific_rendering import Images


def configuration(root):
    root.mkdir(parents=True, exist_ok=True)
    config = root / 'configs' / 'monitor.yaml'
    config.parent.mkdir(exist_ok=True)
    config.write_text('configuration sentinel')
    cfg = normalize_runtime_config({
        'paths': {'upstream_root': str(root / 'inputs/upstream'),
                  'reduced_root': str(root / 'inputs/reduced'),
                  'qc_database': str(root / 'archive/qc.sqlite')},
        'detector_linearity': {'enabled': False},
        'plots': {'output_dir': str(root / 'images à # &'),
                  'html_output': str(root / 'web reports/index.html'),
                  'datapoint_queries': {'sample': {'filters': {}}},
                  'figures': [{'name': 'vis_sample', 'arm': 'VIS', 'type': 'histogram',
                               'filename': 'nested à # &/image ?%.png',
                               'datapoint_query': 'sample'}]}}, root)
    return cfg, config


def render(plots):
    outcomes = []
    for figure in plots['figures']:
        path = Path(plots['output_dir']) / figure['filename']
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (4, 4), color='blue').save(path)
        outcomes.append(FigureResult(figure['name'], figure['type'], figure['filename'],
                                     'produced', 'rendered', 'Synthetic PNG', str(path)))
    return outcomes


@pytest.fixture
def setup(tmp_path):
    cfg, config = configuration(tmp_path / 'project')
    return cfg, config


def publish(setup, **kwargs):
    cfg, config = setup
    return pub.publish_report(cfg, project_root=config.parent.parent,
                              config_path=config, run_id=kwargs.pop('run_id', str(uuid.uuid4())),
                              render=kwargs.pop('render', render), **kwargs)


def root_of(cfg):
    html = Path(cfg['plots']['html_output'])
    return Path(cfg['plots']['output_dir']) / '.qc-publication' / hashlib.sha256(str(html).encode()).hexdigest()


def references(html):
    parser = Images()
    parser.feed(html.read_text())
    return [html.parent / unquote(value) for value in parser.sources]


def test_successive_generations_are_independent_and_manifest_is_not_a_pointer(setup):
    cfg, _ = setup
    before = deepcopy(cfg)
    first = publish(setup)
    second = publish(setup)
    assert cfg == before
    assert first.state == second.state == 'published'
    assert second.previous_generation_id == first.generation_id
    assert second.durability == 'confirmed' and not second.errors
    live = Path(cfg['plots']['html_output'])
    for result in (first, second):
        manifest = json.loads(Path(result.manifest_path).read_text())
        archived = Path(result.manifest_path).parent / 'report.html'
        assert manifest['figures'][0]['data_utc'] is None
        assert manifest['figures'][0]['path'].startswith('plots/')
        assert 'staging/' not in Path(result.manifest_path).read_text()
        assert 'current' not in manifest
        for image in references(archived):
            assert image.resolve().is_relative_to(archived.parent)
            pub._png(image)
    assert all(image.resolve().is_relative_to(Path(second.manifest_path).parent) for image in references(live))
    assert '%23' in live.read_text() and '%3F' in live.read_text() and '%25' in live.read_text()
    assert pub._current(live, root_of(cfg), pub._marker(live.read_text())['report_id']) == second.generation_id
    assert not list((root_of(cfg) / 'staging').glob('*/manifest.json'))


@pytest.mark.parametrize('state', ['no_data', 'failed'])
def test_absence_and_partial_failure_never_link_legacy_images(setup, state):
    cfg, _ = setup
    first = publish(setup)
    cfg['plots']['figures'].append(dict(cfg['plots']['figures'][0], name='nir_empty',
                                      arm='NIR', filename='unused.png'))
    def partial(plots):
        good = render(dict(plots, figures=plots['figures'][:1]))
        figure = plots['figures'][1]
        return good + [FigureResult(figure['name'], figure['type'], figure['filename'],
                                    state, 'synthetic', '<failure & reason>')]
    result = publish(setup, render=partial)
    assert result.state == 'published'
    assert len(references(Path(cfg['plots']['html_output']))) == 1
    assert 'unused.png' not in Path(cfg['plots']['html_output']).read_text()
    run = RunResult('run')
    result.apply_to(run)
    run.finish()
    assert run.exit_code == (2 if state == 'failed' else 0)
    assert run.report['state'] == 'published'
    assert run.publication['generation_id'] == result.generation_id
    assert run.storage == {}
    # Archived predecessor still resolves its own images.
    assert all(image.is_file() for image in references(Path(first.manifest_path).parent / 'report.html'))


def test_no_figures_is_read_only(setup):
    cfg, config = setup
    cfg['plots']['figures'] = []
    before = list(config.parent.parent.rglob('*'))
    assert publish(setup).as_dict() == RunResult('run').publication
    assert list(config.parent.parent.rglob('*')) == before


@pytest.mark.parametrize('fault', ['render', 'missing', 'corrupt', 'wrong_path', 'duplicate',
                                  'manifest', 'archive', 'sync_tree', 'rename', 'live', 'replace'])
def test_precommit_failures_preserve_previous_publication(setup, monkeypatch, fault):
    cfg, _ = setup
    old = publish(setup)
    html = Path(cfg['plots']['html_output'])
    old_bytes = html.read_bytes()
    old_images = {path: path.read_bytes() for path in references(html)}
    callback = render
    def fail(*args, **kwargs):
        raise OSError('injected ' + fault)
    if fault == 'render':
        callback = fail
    elif fault in ('missing', 'corrupt', 'wrong_path', 'duplicate'):
        def callback(plots):
            results = render(plots)
            path = Path(results[0].path)
            if fault == 'missing':
                path.unlink()
            elif fault == 'corrupt':
                path.write_bytes(b'not a PNG')
            elif fault == 'wrong_path':
                results[0].path = str(next(iter(old_images)))
            else:
                results.append(results[0])
            return results
    elif fault in ('manifest', 'archive'):
        original = pub._write
        def write(path, content):
            if path.name == ('manifest.json' if fault == 'manifest' else 'report.html'):
                fail()
            return original(path, content)
        monkeypatch.setattr(pub, '_write', write)
    elif fault == 'sync_tree':
        monkeypatch.setattr(pub, '_sync_tree', fail)
    elif fault in ('rename', 'replace'):
        monkeypatch.setattr(pub.os, fault, fail)
    elif fault == 'live':
        original = pub._render_html_report
        def html_render(plots, path, *args, **kwargs):
            if path.name.startswith('.qc-report-'):
                fail()
            return original(plots, path, *args, **kwargs)
        monkeypatch.setattr(pub, '_render_html_report', html_render)
    with pytest.raises(pub.PublicationError) as caught:
        publish(setup, render=callback)
    result = caught.value.result
    assert result.state == 'failed' and result.report_path is None
    assert html.read_bytes() == old_bytes
    assert {path: path.read_bytes() for path in old_images} == old_images
    assert not list(html.parent.glob('.qc-report-*'))
    assert not list((root_of(cfg) / 'staging').glob('*/manifest.json'))
    assert result.errors
    if fault in ('live', 'replace'):
        assert Path(result.manifest_path).is_file()  # Recognisable finalised orphan.
    assert Path(old.manifest_path).is_file()


def test_every_fsync_failure_respects_commit_boundary(tmp_path, monkeypatch):
    original = pub.os.fsync
    count = 0
    def counting(fd):
        nonlocal count
        count += 1
        original(fd)
    monkeypatch.setattr(pub.os, 'fsync', counting)
    successful = configuration(tmp_path / 'count')
    measured_html = Path(successful[0]['plots']['html_output'])
    measured_html.parent.mkdir()
    measured_html.write_bytes(b'legacy report sentinel')
    publish(successful)
    total = count
    assert total > 15
    # Exercise each real sync position, failing only that call so cleanup can run.
    for position in range(1, total + 1):
        setup = configuration(tmp_path / str(position))
        html = Path(setup[0]['plots']['html_output'])
        html.parent.mkdir()
        html.write_bytes(b'legacy report sentinel')
        calls = 0
        committed = False
        replace = pub.os.replace
        def record_replace(*args, **kwargs):
            nonlocal committed
            replace(*args, **kwargs)
            committed = True
        def failing(fd):
            nonlocal calls
            calls += 1
            if calls == position:
                raise OSError('sync failed')
            original(fd)
        monkeypatch.setattr(pub.os, 'fsync', failing)
        monkeypatch.setattr(pub.os, 'replace', record_replace)
        try:
            result = publish(setup)
        except pub.PublicationError as exc:
            result = exc.result
            if committed:
                assert result.state == 'published' and result.durability == 'unconfirmed'
                assert references(html)[0].is_file()
                run = RunResult('run')
                result.apply_to(run)
                run.finish()
                assert run.exit_code == 2 and run.report['state'] == 'published'
            else:
                assert result.state == 'failed' and html.read_bytes() == b'legacy report sentinel'
        else:
            pytest.fail(f'Failed to exercise fsync position {position} of {total}')
        monkeypatch.setattr(pub.os, 'replace', replace)
    assert total >= calls


@pytest.mark.parametrize('location', ['namespace', 'report_root', 'stage', 'png', 'archive', 'live', 'ancestor'])
def test_symlinks_never_modify_external_files(setup, tmp_path, location):
    cfg, _ = setup
    sentinel = tmp_path / 'outside'
    sentinel.mkdir()
    victim = sentinel / 'victim.png'
    Image.new('RGB', (4, 4), color='red').save(victim)
    before = victim.read_bytes()
    root = root_of(cfg)
    run_id = str(uuid.uuid4())
    callback = render
    if location in ('namespace', 'report_root'):
        target = root.parent if location == 'namespace' else root
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(sentinel, target_is_directory=True)
    elif location == 'live':
        target = Path(cfg['plots']['html_output'])
        target.parent.mkdir()
        target.symlink_to(victim)
    elif location == 'ancestor':
        output = Path(cfg['plots']['output_dir'])
        output.symlink_to(sentinel, target_is_directory=True)
    elif location == 'stage':
        publish(setup)
        (root / 'staging' / run_id).symlink_to(sentinel, target_is_directory=True)
    else:
        def callback(plots):
            results = render(plots)
            if location == 'png':
                image = Path(results[0].path)
                image.unlink()
                image.symlink_to(victim)
            else:
                (Path(plots['output_dir']).parent / 'report.html').symlink_to(victim)
            return results
    with pytest.raises(pub.PublicationError):
        publish(setup, run_id=run_id, render=callback)
    assert victim.read_bytes() == before
    assert sorted(path.name for path in sentinel.iterdir()) == ['victim.png']


@pytest.mark.parametrize('collision', ['config', 'template', 'database', 'summary', 'input'])
def test_protected_destinations_rejected_before_writes(setup, collision):
    cfg, config = setup
    if collision == 'input':
        cfg['plots']['output_dir'] = cfg['paths']['reduced_root']
    elif collision == 'summary':
        pass
    elif collision == 'template':
        cfg['plots']['template'] = cfg['plots']['html_output']
    else:
        cfg['plots']['html_output'] = str(config) if collision == 'config' else cfg['paths']['qc_database']
    options = {'summary_path': cfg['plots']['html_output']} if collision == 'summary' else {}
    with pytest.raises(pub.PublicationError):
        publish(setup, **options)
    assert not Path(cfg['plots']['output_dir']).exists()
    assert config.read_text() == 'configuration sentinel'


@pytest.mark.parametrize('corruption', ['marker', 'duplicate', 'manifest', 'png', 'owner'])
def test_invalid_existing_publication_is_not_adopted(setup, corruption):
    cfg, _ = setup
    previous = publish(setup)
    html = Path(cfg['plots']['html_output'])
    if corruption == 'marker':
        html.write_text('<!-- qc-publication-v1:invalid -->')
    elif corruption == 'duplicate':
        html.write_text(html.read_text() + html.read_text())
    elif corruption == 'manifest':
        Path(previous.manifest_path).write_text('{}')
    elif corruption == 'png':
        references(html)[0].write_bytes(b'corrupt PNG')
    else:
        (root_of(cfg) / '.owner.json').write_text('{}')
    before = html.read_bytes()
    with pytest.raises(pub.PublicationError):
        publish(setup)
    assert html.read_bytes() == before


def test_run_id_collisions_and_staging_cleanup_failures_are_visible(setup, monkeypatch):
    cfg, _ = setup
    first = publish(setup)
    with pytest.raises(pub.PublicationError):
        publish(setup, run_id=first.generation_id)
    def fail(*args, **kwargs):
        raise OSError('cleanup forbidden')
    monkeypatch.setattr(pub, '_remove_owned', fail)
    with pytest.raises(pub.PublicationError) as caught:
        publish(setup, render=fail)
    assert caught.value.result.staging_cleanup == 'failed'
    assert len(caught.value.result.errors) == 2
    assert list((root_of(cfg) / 'staging').glob('*/.owner.json'))


def test_engine_reenters_existing_operation_leases(setup):
    cfg, config = setup
    requests = (runtime_requests() + project_requests(config.parent.parent)
                + configuration_requests(config, cfg) + config_resources(cfg))
    with leases(requests):
        assert publish(setup).state == 'published'


CHILD = '''
import json, sys, uuid
from pathlib import Path
from PIL import Image
from qc_monitor.figure_result import FigureResult
from qc_monitor import publication as pub
cfg = json.loads(Path(sys.argv[1]).read_text())
point = sys.argv[2]
def wait():
    print('READY', flush=True)
    sys.stdin.readline()
def render(plots):
    if point == 'staging': wait()
    results = []
    for f in plots['figures']:
        p = Path(plots['output_dir']) / f['filename']
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (4,4)).save(p)
        results.append(FigureResult(f['name'], f['type'], f['filename'], 'produced', 'ok', 'ok', str(p)))
    return results
if point == 'finalised':
    original = pub._render_html_report
    def html(*args, **kwargs):
        if args[1].name.startswith('.qc-report-'): wait()
        return original(*args, **kwargs)
    pub._render_html_report = html
pub.publish_report(cfg, project_root=Path(sys.argv[1]).parent,
                   config_path=Path(sys.argv[1]), run_id=str(uuid.uuid4()), render=render)
'''


@pytest.mark.parametrize('point', ['staging', 'finalised'])
def test_killed_publisher_preserves_report_leaves_owned_orphan_and_releases_leases(setup, point):
    cfg, config = setup
    previous = publish(setup)
    html = Path(cfg['plots']['html_output'])
    before = html.read_bytes()
    config.write_text(json.dumps(cfg))
    child = subprocess.Popen([sys.executable, '-c', CHILD, str(config), point],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        ready, _, _ = select.select([child.stdout], [], [], 30)
        assert ready, 'child did not signal readiness'
        assert child.stdout.readline().strip() == 'READY'
        with pytest.raises(pub.PublicationError) as conflict:
            publish(setup)
        assert conflict.value.result.errors[0]['type'] == 'CoordinationBusyError'
        assert html.read_bytes() == before
        child.kill()
        child.communicate(timeout=10)
        assert html.read_bytes() == before
        root = root_of(cfg)
        if point == 'staging':
            assert len(list((root / 'staging').glob('*/.owner.json'))) == 1
        else:
            assert len(list((root / 'generations').glob('*/manifest.json'))) == 2
        assert publish(setup).state == 'published'
        assert Path(previous.manifest_path).is_file()
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)


def test_real_renderer_custom_template_and_legacy_api(setup):
    cfg, config = setup
    from qc_monitor.plotting import generate_plots_from_config
    frame = pd.DataFrame({'qc_value': [1., 2., 3.], 'eso seq arm': ['VIS'] * 3})
    template = config.parent / 'custom.html'
    template.write_text('<html><title>{{ page_title }}</title><body>{{ sections }}</body></html>')
    cfg['plots']['template'] = str(template)
    result = publish(setup, render=lambda plots: generate_plots_from_config(frame, plots, continue_on_error=True))
    assert result.figures[0].state == 'produced'
    html = Path(cfg['plots']['html_output'])
    assert len(references(html)) == 1
    legacy = html.parent / 'legacy.html'
    generate_html_report(cfg['plots'], legacy)
    assert 'src="plots/' in legacy.read_text() and pub.MARKER not in legacy.read_text()


def test_cli_activates_atomic_publication(lab):
    lab.cfg['plots']['datapoint_queries'] = {'sample': {'filters': {}}}
    lab.cfg['plots']['figures'] = [{'name': 'vis_hist', 'type': 'histogram',
                                   'filename': 'hist.png', 'datapoint_query': 'sample', 'arm': 'VIS'}]
    lab.save_config()
    completed = lab.cli()
    summary = json.loads(completed.stderr.split('RUN_SUMMARY ')[-1])
    assert summary['report']['state'] == 'published'
    assert summary['publication']['state'] == 'published'
    assert summary['publication']['cleanup']['retention']['limits_guaranteed'] is True
    assert list(lab.output.rglob('.qc-publication'))
    assert not (lab.output / 'plots/hist.png').exists()
    assert references(Path(summary['report']['path']))[0].is_file()


def test_renames_are_local_to_each_filesystem(setup, monkeypatch):
    calls = []
    rename, replace = pub.os.rename, pub.os.replace
    def record(function, src, dst, *, src_dir_fd, dst_dir_fd):
        calls.append((os.fstat(src_dir_fd).st_dev, os.fstat(dst_dir_fd).st_dev))
        return function(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
    monkeypatch.setattr(pub.os, 'rename', lambda *a, **k: record(rename, *a, **k))
    monkeypatch.setattr(pub.os, 'replace', lambda *a, **k: record(replace, *a, **k))
    assert publish(setup).state == 'published'
    assert len(calls) == 2 and all(src == dst for src, dst in calls)


def test_distinct_real_filesystems_when_available(setup):
    cfg, _ = setup
    candidates = [Path('/dev/shm'), Path('/tmp'), Path('/private/tmp')]
    base = Path(cfg['plots']['output_dir']).parent.stat().st_dev
    for candidate in candidates:
        if candidate.is_dir() and os.access(candidate, os.W_OK) and candidate.stat().st_dev != base:
            with tempfile.TemporaryDirectory(prefix='qc-d3d-', dir=candidate) as temporary:
                cfg['plots']['html_output'] = str(Path(temporary).resolve() / 'index.html')
                result = publish(setup)
                assert result.state == 'published'
                assert references(Path(cfg['plots']['html_output']))[0].is_file()
            return
    pytest.skip('Runner has no second writable filesystem; local rename invariant tested separately')


@pytest.mark.parametrize('body', ['<base href="https://example.invalid/">{{ sections }}',
                                 '<img src="old.png">{{ sections }}',
                                 '<a href="old.png">obsolete</a>{{ sections }}',
                                 '<!-- qc-publication-v1:invalid -->{{ sections }}'])
def test_custom_templates_cannot_introduce_unvalidated_artifacts(setup, body):
    cfg, config = setup
    old = publish(setup)
    template = config.parent / 'bad.html'
    template.write_text(body)
    cfg['plots']['template'] = str(template)
    before = Path(old.report_path).read_bytes()
    with pytest.raises(pub.PublicationError):
        publish(setup)
    assert Path(old.report_path).read_bytes() == before


@pytest.mark.parametrize('artifact', ['hardlink', 'fifo', 'directory'])
def test_non_regular_and_shared_artifacts_are_rejected(setup, tmp_path, artifact):
    outside = tmp_path / 'foreign.png'
    Image.new('RGB', (3, 3), 'red').save(outside)
    before = outside.read_bytes()
    def callback(plots):
        outcomes = render(plots)
        path = Path(outcomes[0].path)
        path.unlink()
        if artifact == 'hardlink':
            os.link(outside, path)
        elif artifact == 'fifo':
            os.mkfifo(path)
        else:
            path.mkdir()
        return outcomes
    with pytest.raises(pub.PublicationError):
        publish(setup, render=callback)
    assert outside.read_bytes() == before


@pytest.mark.parametrize('state', ['no_data', 'failed'])
def test_report_without_any_produced_image_is_publishable(setup, state):
    def callback(plots):
        return [FigureResult(f['name'], f['type'], f['filename'], state,
                             'empty_or_failed', 'Synthetic reason') for f in plots['figures']]
    result = publish(setup, render=callback)
    assert result.state == 'published' and not references(Path(result.report_path))
    run = RunResult('run')
    result.apply_to(run)
    run.finish()
    assert run.exit_code == (2 if state == 'failed' else 0)


def test_preexisting_unowned_namespace_fails_without_creating_html_directory(setup):
    cfg, _ = setup
    root_of(cfg).parent.mkdir(parents=True)
    sentinel = root_of(cfg).parent / 'foreign'
    sentinel.write_bytes(b'foreign directory content')
    with pytest.raises(pub.PublicationError):
        publish(setup)
    assert not Path(cfg['plots']['html_output']).parent.exists()
    assert sentinel.read_bytes() == b'foreign directory content'


def test_preexisting_temporary_name_is_never_cleaned(setup):
    cfg, _ = setup
    old = publish(setup)
    run_id = str(uuid.uuid4())
    temporary = Path(old.report_path).parent / ('.qc-report-' + run_id + '.html')
    temporary.write_bytes(b'foreign temporary sentinel')
    before = Path(old.report_path).read_bytes()
    with pytest.raises(pub.PublicationError):
        publish(setup, run_id=run_id)
    assert temporary.read_bytes() == b'foreign temporary sentinel'
    assert Path(old.report_path).read_bytes() == before


def test_changed_staging_ownership_blocks_cleanup(setup):
    cfg, _ = setup
    def callback(plots):
        owner = Path(plots['output_dir']).parent / '.owner.json'
        owner.write_text('{}')
        raise OSError('renderer failed after ownership change')
    with pytest.raises(pub.PublicationError) as caught:
        publish(setup, render=callback)
    assert caught.value.result.staging_cleanup == 'failed'
    assert list((root_of(cfg) / 'staging').glob('*/.owner.json'))


@pytest.mark.parametrize('run_id', ['../escape', 'not-an-id', str(uuid.uuid4()).upper()])
def test_invalid_identifiers_have_no_output_effects(setup, run_id):
    cfg, _ = setup
    with pytest.raises(pub.PublicationError):
        publish(setup, run_id=run_id)
    assert not Path(cfg['plots']['output_dir']).exists()


@pytest.mark.parametrize('boundary', ['unlink', 'rmdir'])
def test_cleanup_failure_preserves_ownership_for_handover(setup, monkeypatch, boundary):
    cfg, _ = setup
    original = getattr(pub.os, boundary)
    run_id = str(uuid.uuid4())
    def fail_entry(name, *args, **kwargs):
        if name == ('leftover' if boundary == 'unlink' else run_id):
            raise PermissionError('real cleanup boundary refused')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(pub.os, boundary, fail_entry)
    def callback(plots):
        (Path(plots['output_dir']) / 'leftover').write_bytes(b'owned artifact')
        raise OSError('render failed')
    with pytest.raises(pub.PublicationError) as caught:
        publish(setup, run_id=run_id, render=callback)
    assert caught.value.result.staging_cleanup == 'failed'
    marker = root_of(cfg) / 'staging' / run_id / '.owner.json'
    assert json.loads(marker.read_text())['generation_id'] == run_id


def test_renderer_cannot_publish_changed_generation_ownership(setup):
    cfg, _ = setup
    previous = publish(setup)
    before = Path(previous.report_path).read_bytes()
    def callback(plots):
        outcomes = render(plots)
        (Path(plots['output_dir']).parent / '.owner.json').write_text('{}')
        return outcomes
    with pytest.raises(pub.PublicationError):
        publish(setup, render=callback)
    assert Path(previous.report_path).read_bytes() == before

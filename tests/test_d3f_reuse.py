"""D3-F fallback, immutable provenance and integrated CLI recovery on synthetic data."""
from copy import deepcopy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from qc_monitor import publication as pub
from qc_monitor.figure_result import FigureResult, validate_figure_results
from qc_monitor.run_result import RunResult
from conftest import DAY, rows, database_snapshot
from test_d3d_publication import (configuration, publish, render, references, root_of,
                                  legacy_manifest)
from test_d3c_rendering import configure_cli, summary, save_failure_cli


@pytest.fixture
def setup(tmp_path):
    return configuration(tmp_path / 'project')


def failed(plots):
    return [FigureResult.failed(fig, OSError('<current & failure>')) for fig in plots['figures']]


def edit_manifest(result, change):
    path = Path(result.manifest_path)
    data = json.loads(path.read_text())
    change(data)
    path.write_text(pub._json(data))
    html = Path(result.report_path)
    content = html.read_text()
    marker = pub._marker(content)
    marker['manifest_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    html.write_text(pub._marked(content.split('\n', 1)[1], marker))


def test_repeat_reuse_is_autonomous_after_origin_removed(setup):
    first = publish(setup)
    original = first.figures[0]
    data = Path(original.path).read_bytes()
    for _ in range(4):
        result = publish(setup, render=failed)
        item = result.figures[0]
        assert item.state == 'reused' and item.reason == '<current & failure>'
        assert item.generated_utc == original.generated_utc
        assert item.origin_generation_id == first.generation_id
        assert item.reused_from_generation_id == result.previous_generation_id
        assert Path(item.path).read_bytes() == data
        manifest = json.loads(Path(result.manifest_path).read_text())
        assert manifest['figures'][0]['data_utc'] is None
        assert manifest['figures'][0]['path'].startswith('plots/')
        run = RunResult('run')
        result.apply_to(run)
        run.finish()
        assert run.exit_code == 2 and run.plots['state'] == 'failed'
        assert run.plots['counts'] == {'produced': 0, 'reused': 1, 'failed': 0, 'no_data': 0}
        assert run.errors[0]['reason'] == '<current & failure>'
        assert run.errors[0]['type'] == 'OSError'
        for html in (Path(result.report_path), Path(result.manifest_path).parent / 'report.html'):
            content = html.read_text()
            assert 'Reused after failure' in content and original.generated_utc in content
            assert '&lt;current &amp; failure&gt;' in content
            assert all(image.resolve().is_relative_to(Path(result.manifest_path).parent)
                       for image in references(html))
    assert not Path(first.manifest_path).exists()
    assert result.cleanup['retention']['remaining'] == {'generations': 2, 'staging': 0}
    pub.validate_publication(setup[0], config_path=setup[1])


@pytest.mark.parametrize('change', ['title', 'bins', 'filename', 'arm', 'type', 'query',
                                   'database', 'contract_version', 'section', 'wide',
                                   'page_title', 'template', 'unrelated_query', 'other_figure'])
def test_compatibility_is_per_figure(setup, change):
    cfg, _ = setup
    first = publish(setup)
    fig = cfg['plots']['figures'][0]
    compatible = change in {'section', 'wide', 'page_title', 'template', 'unrelated_query', 'other_figure'}
    if change == 'title': fig['title'] = 'Changed pixels'
    elif change == 'bins': fig['bins'] = 17
    elif change == 'filename': fig['filename'] = 'other.png'
    elif change == 'arm': fig['arm'] = 'NIR'
    elif change == 'type': fig['type'] = 'time_series'
    elif change == 'query': cfg['plots']['datapoint_queries']['sample']['filters']['qc_name'] = 'other'
    elif change == 'database': cfg['paths']['qc_database'] += '.other'
    elif change == 'contract_version':
        edit_manifest(first, lambda data: data['figures'][0]['compatibility'].update(version=2))
    elif change == 'section': fig['section'] = 'New section'
    elif change == 'wide': fig['wide'] = True
    elif change == 'page_title': cfg['plots']['page_title'] = 'New page'
    elif change == 'template':
        path = setup[1].parent / 'custom.html'
        path.write_text('<html><title>{{ page_title }}</title>{{ sections }}</html>')
        cfg['plots']['template'] = str(path)
    elif change == 'unrelated_query': cfg['plots']['datapoint_queries']['unused'] = {'filters': {'qc_name': 'unused'}}
    elif change == 'other_figure':
        cfg['plots']['figures'].append(dict(fig, name='nir_other', arm='NIR', filename='other.png'))
    result = publish(setup, render=failed)
    assert result.figures[0].state == ('reused' if compatible else 'failed')
    assert result.figures[0].fallback['reason_code'] == ('compatible_current_image' if compatible else 'incompatible')
    if change == 'other_figure': assert result.figures[1].fallback['reason_code'] == 'no_current_image'


def test_database_updates_and_package_version_do_not_invalidate(setup):
    cfg, _ = setup
    first = publish(setup)
    db = Path(cfg['paths']['qc_database'])
    db.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute('CREATE TABLE synthetic (value INTEGER)')
        connection.execute('INSERT INTO synthetic VALUES (1)')
    edit_manifest(first, lambda data: data.update(package_version='future-compatible'))
    assert publish(setup, render=failed).figures[0].state == 'reused'


@pytest.mark.parametrize('change', ['statistic', 'own_arm', 'other_arm'])
def test_detlin_contract_only_uses_selected_arm(setup, change):
    cfg, _ = setup
    fig = cfg['plots']['figures'][0]
    fig.update(type='detector_linearity', arm='VIS')
    fig.pop('datapoint_query')
    cfg['detector_linearity']['arms'] = {
        'VIS': {'root': str(setup[1].parent.parent / 'detlin-vis'), 'option': 1},
        'NIR': {'root': str(setup[1].parent.parent / 'detlin-nir'), 'option': 1}}
    publish(setup)
    if change == 'statistic': cfg['detector_linearity']['statistic'] = 'median'
    else: cfg['detector_linearity']['arms']['NIR' if change == 'other_arm' else 'VIS']['option'] = 2
    result = publish(setup, render=failed)
    assert result.figures[0].state == ('reused' if change == 'other_arm' else 'failed')


@pytest.mark.parametrize('damage', ['legacy', 'timestamp', 'origin', 'naive_time', 'unknown_state',
                                   'missing', 'corrupt', 'symlink', 'hardlink'])
def test_unavailable_candidate_publishes_failure_without_image(setup, damage, tmp_path):
    first = publish(setup)
    source = Path(first.figures[0].path)
    if damage == 'legacy': legacy_manifest(first)
    elif damage in ('timestamp', 'origin', 'naive_time', 'unknown_state'):
        def modify(data):
            figure = data['figures'][0]
            if damage == 'timestamp': figure.pop('generated_utc')
            elif damage == 'origin': figure['origin_generation_id'] = 'invalid'
            elif damage == 'naive_time': figure['generated_utc'] = '2026-10-09T01:00:00'
            else: figure['state'] = 'no_data'; figure['path'] = None
        if damage == 'unknown_state':
            # Keep structural HTML consistent with a no_data current manifest.
            # This case is covered by a real no_data publication below instead.
            result = publish(setup, render=lambda plots: [FigureResult(
                f['name'], f['type'], f['filename'], 'no_data', 'empty', 'Empty')
                for f in plots['figures']])
            first = result
        else: edit_manifest(first, modify)
    elif damage == 'missing': source.unlink()
    elif damage == 'corrupt': source.write_bytes(b'not a PNG')
    else:
        sentinel = tmp_path / 'external.png'
        sentinel.write_bytes(source.read_bytes())
        before = sentinel.read_bytes()
        source.unlink()
        if damage == 'symlink': source.symlink_to(sentinel)
        else: os.link(sentinel, source)
    result = publish(setup, render=failed)
    assert result.state == 'published' and result.figures[0].state == 'failed'
    assert references(Path(result.report_path)) == []
    assert result.figures[0].fallback['state'] == 'unavailable'
    if damage in ('symlink', 'hardlink'): assert sentinel.read_bytes() == before


def test_no_data_never_reuses_and_does_not_search_older_generation(setup):
    publish(setup)
    empty = publish(setup, render=lambda plots: [FigureResult(
        f['name'], f['type'], f['filename'], 'no_data', 'empty', 'Empty') for f in plots['figures']])
    assert empty.figures[0].fallback is None and empty.figures[0].path is None
    failure = publish(setup, render=failed)
    assert failure.figures[0].state == 'failed'
    assert failure.figures[0].fallback['reason_code'] == 'no_current_image'


@pytest.mark.parametrize('partial', [False, True])
def test_copy_failure_discards_partial_and_still_publishes(setup, monkeypatch, partial):
    publish(setup)
    def broken(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if partial: destination.write_bytes(b'partial PNG')
        raise OSError('copy failed')
    monkeypatch.setattr(pub, '_copy_png', broken)
    result = publish(setup, render=failed)
    assert result.state == 'published' and result.figures[0].state == 'failed'
    assert result.figures[0].fallback['reason_code'] == 'copy_failed'
    assert not list((Path(result.manifest_path).parent / 'plots').rglob('*.png'))
    run = RunResult('run'); result.apply_to(run); run.finish()
    assert run.exit_code == 2


def test_failed_save_directory_is_removed_before_reuse(setup):
    publish(setup)
    def broken(plots):
        path = Path(plots['output_dir']) / plots['figures'][0]['filename']
        path.mkdir(parents=True)
        (path / 'partial').write_bytes(b'partial')
        return failed(plots)
    result = publish(setup, render=broken)
    assert result.figures[0].state == 'reused'
    pub._png(Path(result.figures[0].path))


def test_copy_cleanup_failure_protects_previous_report(setup, monkeypatch):
    first = publish(setup)
    before = Path(first.report_path).read_bytes()
    def broken(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'partial')
        raise OSError('copy failed')
    discard = pub._discard_artifact
    def failed_cleanup(path):
        if path.is_file(): raise PermissionError('cannot remove partial copy')
        discard(path)
    monkeypatch.setattr(pub, '_copy_png', broken)
    monkeypatch.setattr(pub, '_discard_artifact', failed_cleanup)
    with pytest.raises(pub.PublicationError) as caught:
        publish(setup, render=failed)
    assert caught.value.result.phase == 'fallback'
    assert Path(first.report_path).read_bytes() == before
    assert caught.value.result.staging_cleanup == 'removed'


@pytest.mark.parametrize('fault', ['manifest', 'archive', 'live', 'sync', 'cleanup'])
def test_failure_after_reuse_preserves_commit_contract(setup, monkeypatch, fault):
    first = publish(setup)
    before = Path(first.report_path).read_bytes()
    if fault in ('manifest', 'archive'):
        original = pub._write
        def broken(path, content):
            if path.name == ('manifest.json' if fault == 'manifest' else 'report.html'):
                raise OSError('write failed after reuse')
            return original(path, content)
        monkeypatch.setattr(pub, '_write', broken)
    elif fault == 'live':
        original = pub._render_html_report
        def broken(plots, path, *args, **kwargs):
            if path.name.startswith('.qc-report-'): raise OSError('live failed')
            return original(plots, path, *args, **kwargs)
        monkeypatch.setattr(pub, '_render_html_report', broken)
    elif fault == 'sync':
        monkeypatch.setattr(pub, '_sync_tree', lambda path: (_ for _ in ()).throw(OSError('sync failed')))
    else:
        original = pub._cleanup
        calls = []
        def broken(*args):
            calls.append(1)
            if len(calls) == 2: raise OSError('retention failed')
            return original(*args)
        monkeypatch.setattr(pub, '_cleanup', broken)
    with pytest.raises(pub.PublicationError) as caught: publish(setup, render=failed)
    result = caught.value.result
    run = RunResult('run'); result.apply_to(run); run.finish()
    assert run.exit_code == 2 and result.figures[0].state == 'reused'
    if fault == 'cleanup':
        assert result.state == 'published' and Path(first.report_path).read_bytes() != before
        assert all(path.is_file() for path in references(Path(first.report_path)))
    else:
        assert result.state == 'failed' and Path(first.report_path).read_bytes() == before


@pytest.mark.parametrize('field', ['generated_utc', 'origin_generation_id', 'reused_from_generation_id',
                                   'compatibility', 'fallback'])
def test_reused_result_requires_provenance(setup, field):
    publish(setup)
    result = publish(setup, render=failed)
    item = deepcopy(result.figures[0]); setattr(item, field, None)
    with pytest.raises((ValueError, TypeError)):
        validate_figure_results(setup[0]['plots']['figures'], [item])


def test_cli_integrated_recovery_and_reuse(lab):
    configure_cli(lab)
    nominal = summary(lab.cli())
    assert nominal['plots']['figures'][0]['state'] == 'produced'
    original_data = database_snapshot(lab.db)
    # A new, incomplete independent DSOL unit must not erase valid QC history.
    lab.dsol(broken=True)
    incomplete = summary(lab.cli(expected=1))
    assert incomplete['families']['dsol']['state'] == 'partial'
    assert rows(lab.db, 'SELECT * FROM processed_dispersion_obs_days') == []
    assert database_snapshot(lab.db) == original_data
    # Actual renderer save failure, with the same config and existing image.
    error = summary(save_failure_cli(lab, 'time_series.png', 2))
    figure = error['plots']['figures'][0]
    assert figure['state'] == 'reused' and Path(figure['path']).is_file()
    assert error['report']['state'] == 'published' and error['errors']
    assert database_snapshot(lab.db) == original_data
    lab.dsol()  # Repair the real FITS input, then retry acquisition and rendering.
    repaired = summary(lab.cli())
    assert repaired['families']['dsol']['state'] == 'completed'
    assert repaired['plots']['figures'][0]['state'] == 'produced'
    assert rows(lab.db, 'SELECT obs_day FROM processed_dispersion_obs_days') == [(DAY,)]
    closed = database_snapshot(lab.db)
    again = summary(lab.cli())
    assert again['exit_code'] == 0 and database_snapshot(lab.db) == closed
    assert again['families']['qc']['tables']['qc_metrics']['preserved'] == 1
    assert again['publication']['cleanup']['retention']['remaining'] == {'generations': 2, 'staging': 0}
    rebuilt = summary(lab.cli('--rebuild-db'))
    assert rebuilt['exit_code'] == 0
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(1,)]
    assert list(lab.db.parent.glob(lab.db.name + '.backup-*.sqlite'))


@pytest.mark.parametrize('point', ['fallback', 'finalised'])
def test_interrupted_reuse_releases_leases_and_retry_recovers(setup, point):
    import select
    from test_d3d_publication import CHILD
    cfg, config = setup
    previous = publish(setup)
    before = Path(previous.report_path).read_bytes()
    config.write_text(json.dumps(cfg))
    program = CHILD.replace("results.append(FigureResult(f['name'], f['type'], f['filename'], 'produced', 'ok', 'ok', str(p)))",
                            "results.append(FigureResult.failed(f, OSError('child render failed')))")
    program = program.replace('pub.publish_report(cfg,', '''
if point == 'fallback':
    original_copy = pub._copy_png
    def copy(source, destination):
        wait()
        return original_copy(source, destination)
    pub._copy_png = copy
pub.publish_report(cfg,''')
    child = subprocess.Popen([sys.executable, '-c', program, str(config), point],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([child.stdout], [], [], 30)
        assert ready, 'reusing child did not signal readiness'
        assert child.stdout.readline().strip() == 'READY'
        with pytest.raises(pub.PublicationError) as caught: publish(setup, render=failed)
        assert caught.value.result.errors[0]['type'] == 'CoordinationBusyError'
        assert Path(previous.report_path).read_bytes() == before
        child.kill(); child.communicate(timeout=10)
        recovered = publish(setup, render=failed)
        assert recovered.figures[0].state == 'reused'
        assert recovered.cleanup['retention']['remaining'] == {'generations': 2, 'staging': 1 if point == 'fallback' else 0}
        assert recovered.figures[0].origin_generation_id == previous.generation_id
    finally:
        if child.poll() is None: child.kill()
        child.communicate(timeout=10)

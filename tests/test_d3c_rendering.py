"""D3-C: explicit outcomes, real artifacts and isolated failure recovery."""
from copy import deepcopy
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from conftest import DAY, tree_snapshot
from qc_monitor.figure_result import FigureResult, summarize_figures
from qc_monitor.generate_html import generate_html_report
from qc_monitor import plotting
from qc_monitor.plotting import (generate_plots_from_config,
    generate_order_location_plots_from_config, InvalidPlotData)
from test_scientific_rendering import Images

KINDS = ('time_series', 'xy_scatter', 'histogram', 'latest_by_order_bar',
         'dispersion_resolution', 'dispersion_resolution_timeseries',
         'dispersion_residual_xy', 'dispersion_residual_histogram',
         'order_location_fit', 'detector_linearity')


def example(kind, output):
    fig = {'name': 'vis_' + kind, 'type': kind, 'filename': kind + '.png',
           'title': 'VIS ' + kind, 'arm': 'VIS', 'selection': 'all',
           'datapoint_query': 'sample', 'axis_b_step': 1,
           'series': [{'datapoint_query': 'sample', 'label': 'Sample'}],
           'x': {'datapoint_query': 'sample'}, 'y': {'datapoint_query': 'sample'}}
    if kind == 'order_location_fit':
        fig['selection'] = 'latest'
    cfg = {'output_dir': str(output / 'plots'), 'figures': [fig],
           'datapoint_queries': {'sample': {'filters': {}}}, 'show': False}
    df = pd.DataFrame({'eso seq arm': ['VIS'] * 2,
        'obs_date_utc': [DAY + 'T08:00:00', DAY + 'T09:00:00'],
        'night start date': ['2026-10-04', DAY], 'qc_value': [1., 2.], 'qc_order': [10, 11],
        'wavelength': [500., 600.], 'R_pin': [1000., 1200.], 'order': [10, 11],
        'mean_R_pin': [1000., 1200.], 'std_R_pin': [2., 3.], 'n_points': [2, 2],
        'residuals_x': [.1, .2], 'residuals_y': [.2, .3], 'residuals_xy': [.3, .4],
        'exptime': [1., 2.], 'signal': [100., 200.], 'fit_signal': [100., 200.],
        'fit_used': [1, 1], 'saturation_limit': [600., 600.], 'detector_mode': ['SHG'] * 2,
        'sequence_id': ['seq'] * 2, 'tpl_start': [DAY + 'T08:00:00'] * 2,
        'tpl_id': ['detlin'] * 2, 'fit_state': ['available'] * 2})
    meta = pd.DataFrame({'source_file': ['model'] * 2, 'order': [10., 11.],
                         'ymin': [0., 0.], 'ymax': [4., 4.]})
    if kind == 'order_location_fit':
        df = pd.DataFrame([{'eso seq arm': 'VIS', 'obs_date_utc': DAY,
            'source_file': 'model', 'degorder_cent': 0, 'degy_cent': 0, 'cent_00': 2.,
            'degorder_edgelow': 0, 'degy_edgelow': 0, 'edgelow_c00': 1.,
            'degorder_edgeup': 0, 'degy_edgeup': 0, 'edgeup_c00': 3.}])
    return cfg, df, meta


def render(kind, cfg, df, meta, **kwargs):
    if kind == 'order_location_fit':
        return generate_order_location_plots_from_config(df, meta, cfg, **kwargs)
    return generate_plots_from_config(df, cfg, **kwargs)


def primary(kind):
    return {'dispersion_resolution': 'wavelength', 'dispersion_resolution_timeseries': 'mean_R_pin',
            'dispersion_residual_xy': 'residuals_x', 'dispersion_residual_histogram': 'residuals_xy',
            'detector_linearity': 'signal', 'order_location_fit': 'cent_00'}.get(kind, 'qc_value')


@pytest.mark.parametrize('kind', KINDS)
def test_all_renderers_produce_explicit_results_and_empty_history(kind, tmp_path):
    cfg, df, meta = example(kind, tmp_path)
    result, = render(kind, cfg, df, meta)
    assert result.state == 'produced'
    assert Path(result.path).is_file()
    assert result.name == cfg['figures'][0]['name']
    assert result.filename == cfg['figures'][0]['filename']
    assert plt.get_fignums() == []
    empty, = render(kind, cfg, df.iloc[:0], meta)
    assert empty.state == 'no_data' and empty.path is None
    assert empty.reason_code == 'empty_history'


@pytest.mark.parametrize('kind', KINDS)
def test_partial_invalid_samples_produce_and_report_discards(kind, tmp_path):
    cfg, df, meta = example(kind, tmp_path)
    if kind == 'order_location_fit':
        bad = meta.iloc[:1].copy()
        bad['order'] = np.inf
        meta = pd.concat([meta, bad], ignore_index=True)
    else:
        bad = df.iloc[:1].copy()
        bad[primary(kind)] = np.inf
        # Keep latest-by-order's invalid row in the selected latest group.
        if kind == 'latest_by_order_bar':
            bad['obs_date_utc'] = df['obs_date_utc'].iloc[-1]
        df = pd.concat([df, bad], ignore_index=True)
    result, = render(kind, cfg, df, meta)
    assert result.state == 'produced'
    assert sum(item['count'] for item in result.discarded) >= 1
    generate_html_report(cfg, tmp_path / 'index.html', figure_results=[result])
    assert 'Discarded ' in (tmp_path / 'index.html').read_text()
    assert summarize_figures([result])['counts']['failed'] == 0


@pytest.mark.parametrize('kind', KINDS)
def test_all_invalid_samples_fail_without_stale_path(kind, tmp_path):
    cfg, df, meta = example(kind, tmp_path)
    df[primary(kind)] = np.inf
    with pytest.raises((InvalidPlotData, ValueError)):
        render(kind, cfg, df, meta)
    result, = render(kind, cfg, df, meta, continue_on_error=True)
    assert result.state == 'failed' and result.path is None
    assert plt.get_fignums() == []


@pytest.mark.parametrize('kind', KINDS)
def test_missing_required_column_is_failure(kind, tmp_path):
    cfg, df, meta = example(kind, tmp_path)
    df = df.drop(columns=[primary(kind)])
    result, = render(kind, cfg, df, meta, continue_on_error=True)
    assert result.state == 'failed'
    assert result.error_type in ('InvalidPlotData', 'KeyError')


@pytest.mark.parametrize('kind', KINDS)
def test_save_failure_closes_owned_figures_preserves_callers(kind, tmp_path):
    cfg, df, meta = example(kind, tmp_path)
    blocked = tmp_path / 'blocked'
    blocked.write_text('not a directory')
    cfg['output_dir'] = str(blocked)
    owned = plt.figure()
    try:
        with pytest.raises(OSError):
            render(kind, cfg, df, meta)
        assert plt.get_fignums() == [owned.number]
        result, = render(kind, cfg, df, meta, continue_on_error=True)
        assert result.state == 'failed' and result.path is None
        assert plt.get_fignums() == [owned.number]
    finally:
        plt.close(owned)


def test_broken_series_fails_whole_figure_but_independent_ones_continue(tmp_path):
    cfg, df, meta = example('time_series', tmp_path)
    cfg['datapoint_queries']['bad'] = {'filters': {'nonexistent': 'anything'}}
    cfg['figures'][0]['series'].append({'datapoint_query': 'bad', 'label': 'Broken'})
    good = deepcopy(cfg['figures'][0])
    good.update(name='vis_good', filename='good.png', series=good['series'][:1])
    cfg['figures'] = [good, cfg['figures'][0], dict(good, name='vis_later', filename='later.png')]
    results = generate_plots_from_config(df, cfg, continue_on_error=True)
    assert [r.state for r in results] == ['produced', 'failed', 'produced']
    assert plt.get_fignums() == []
    with pytest.raises(InvalidPlotData):
        generate_plots_from_config(df, cfg)


@pytest.mark.parametrize('stage', ['draw', 'save', 'show'])
def test_exception_after_creation_closes_figures(stage, tmp_path, monkeypatch):
    cfg, df, _ = example('histogram', tmp_path)
    cfg['show'] = stage == 'show'
    def fail(*args, **kwargs):
        raise RuntimeError(stage + ' failure')
    monkeypatch.setattr(plt, {'draw': 'hist', 'show': 'show'}.get(stage, 'savefig'), fail)
    if stage == 'save':
        from qc_monitor import _plots_common
        monkeypatch.setattr(_plots_common, '_save_figure', fail)
    with pytest.raises(RuntimeError, match=stage):
        generate_plots_from_config(df, cfg)
    assert plt.get_fignums() == []


def test_legitimate_empty_series_and_xy_insufficient_are_no_data(tmp_path):
    cfg, df, _ = example('time_series', tmp_path)
    cfg['datapoint_queries']['sample']['filters'] = {'eso seq arm': 'NIR'}
    result, = generate_plots_from_config(df, cfg)
    assert result.state == 'no_data'
    cfg, df, _ = example('xy_scatter', tmp_path)
    result, = generate_plots_from_config(df.iloc[:1], cfg)
    assert result.state == 'no_data'


@pytest.mark.parametrize('state', ['no_data', 'failed'])
def test_html_omits_stale_images_and_escapes_custom_template(state, tmp_path):
    cfg, _, _ = example('histogram', tmp_path)
    image = tmp_path / 'plots/histogram.png'
    image.parent.mkdir()
    image.write_bytes(b'previous image')
    cfg['figures'][0]['title'] = '<script>title</script>'
    result = FigureResult('vis_histogram', 'histogram', 'histogram.png', state, 'test', '<bad & reason>')
    template = tmp_path / 'template.html'
    template.write_text('<h1>{{ page_title }}</h1>{{ sections }}')
    generate_html_report(cfg, tmp_path / 'index.html', template, [result])
    report = (tmp_path / 'index.html').read_text()
    assert '<img' not in report and 'histogram.png' not in report
    assert '&lt;bad &amp; reason&gt;' in report
    assert '&lt;script&gt;title&lt;/script&gt;' in report
    assert image.read_bytes() == b'previous image'
    # Direct legacy HTML remains usable without the new argument.
    generate_html_report(cfg, tmp_path / 'legacy.html', template)
    assert '<img' in (tmp_path / 'legacy.html').read_text()


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'mismatch', 'bad_path', 'bad_state'])
def test_html_rejects_incoherent_outcomes_before_write(case, tmp_path):
    cfg, _, _ = example('histogram', tmp_path)
    result = FigureResult('vis_histogram', 'histogram', 'histogram.png', 'no_data', 'empty', 'Empty')
    results = [result]
    if case == 'missing': results = []
    if case == 'duplicate': results = [result, result]
    if case == 'mismatch': result.filename = 'other.png'
    if case == 'bad_path': result.path = 'old.png'
    if case == 'bad_state': result.state = 'unknown'
    with pytest.raises(ValueError):
        generate_html_report(cfg, tmp_path / 'index.html', figure_results=results)
    assert not (tmp_path / 'index.html').exists()


def summary(process):
    return json.loads(process.stderr.split('RUN_SUMMARY ')[-1])


def configure_cli(lab):
    cfg, _, _ = example('time_series', lab.output)
    cfg['figures'][0] = {key: value for key, value in cfg['figures'][0].items()
                         if key in ('name', 'type', 'filename', 'title', 'arm', 'series')}
    cfg['datapoint_queries']['sample']['filters'] = {'qc_name': 'bias_level'}
    lab.cfg['plots'] = dict(cfg, html_output=str(lab.output / 'index.html'))
    lab.save_config()



# Inject actual save failures inside the new staging, rather than legacy PNG paths.
SAVE_FAILURE = """
from pathlib import Path
original_plots = app.generate_plots_from_config
def failed_save(frame, plots, *args, **kwargs):
    for figure in plots['figures']:
        if figure['filename'] == FAILED_FILENAME:
            (Path(plots['output_dir']) / figure['filename']).mkdir(parents=True, exist_ok=True)
    return original_plots(frame, plots, *args, **kwargs)
app.generate_plots_from_config = failed_save
"""


def save_failure_cli(lab, filename, expected):
    program = 'import sys\nfrom qc_monitor import main as app\nFAILED_FILENAME=' + repr(filename) + '\n' + SAVE_FAILURE + '\nsys.exit(app.main())'
    result = subprocess.run([sys.executable, '-c', program, '--config', str(lab.config)],
        cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(), capture_output=True, text=True, timeout=60)
    assert result.returncode == expected, result.stderr
    return result

@pytest.mark.parametrize('backend', [None, 'TkAgg'])
def test_cli_batch_backend_selected_without_pytest_environment(lab, backend):
    configure_cli(lab)
    env = os.environ.copy()
    env['MPLCONFIGDIR'] = str(lab.cache)
    env['XDG_CACHE_HOME'] = str(lab.cache)
    if backend is None: env.pop('MPLBACKEND', None)
    else: env['MPLBACKEND'] = backend
    program = '''
import sys
from qc_monitor import main as app
assert 'matplotlib.pyplot' not in sys.modules
code = app.main()
import matplotlib
assert matplotlib.get_backend().lower() == 'agg'
sys.exit(code)
'''
    result = subprocess.run([sys.executable, '-c', program, '--config', str(lab.config)],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    result_json = summary(result)
    assert result_json['plots']['counts']['produced'] == 1
    assert result_json['report']['state'] == 'published'


@pytest.mark.parametrize('failure', ['read', 'render', 'html'])
def test_cli_independent_figures_summary_and_real_failure(lab, failure):
    configure_cli(lab)
    lab.dsol()
    independent = {'name': 'vis_dsol', 'type': 'dispersion_resolution', 'filename': 'dsol.png',
                   'arm': 'VIS', 'selection': 'all'}
    lab.cfg['plots']['figures'].append(independent)
    lab.save_config()
    program = '''
import sys
from qc_monitor import main as app
from qc_monitor.storage import SQLiteStore
from qc_monitor import publication as pub
if FAILURE == 'read':
    def bad_read(self): raise OSError('history read failure')
    SQLiteStore.load_all_metrics = bad_read
elif FAILURE == 'html':
    def bad_html(*args, **kwargs): raise OSError('HTML write failure')
    pub._render_html_report = bad_html
sys.exit(app.main())
'''
    result = subprocess.run([sys.executable, '-c', 'FAILURE=' + repr(failure) + '\n' + (('from qc_monitor import main as app\nFAILED_FILENAME=\"time_series.png\"\n' + SAVE_FAILURE) if failure == 'render' else '') + program,
        '--config', str(lab.config), '--summary-json', str(lab.root / 'summary.json')],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 2, result.stderr
    data = summary(result)
    assert json.loads((lab.root / 'summary.json').read_text()) == data
    assert data['format_version'] == 1
    assert data['plots']['figures'][1]['state'] == 'produced'
    if failure == 'html':
        assert data['report'] == {'state': 'failed', 'path': None}
    else:
        assert data['plots']['figures'][0]['state'] == 'failed'
        assert data['report']['state'] == 'published'
        report = (lab.output / 'index.html').read_text()
        parser = Images()
        parser.feed(report)
        from urllib.parse import unquote
        assert len(parser.sources) == 1
        assert (lab.output / unquote(parser.sources[0])).is_file()
        assert parser.sources[0].endswith('/plots/dsol.png')
        assert 'Traceback' in result.stderr


@pytest.mark.parametrize('flag', ['--no-plots', '--dry-run', '--preflight'])
def test_inspection_and_no_plots_are_explicitly_skipped(lab, flag):
    configure_cli(lab)
    before = tree_snapshot(lab.output)
    result = lab.cli(flag)
    data = summary(result)
    assert data['plots']['state'] == 'skipped' and data['plots']['figures'] == []
    assert data['report']['state'] == 'skipped'
    assert tree_snapshot(lab.output) == before


def test_interactive_api_keeps_explicit_backend(tmp_path):
    env = os.environ.copy()
    env['MPLCONFIGDIR'] = str(tmp_path)
    program = '''
import matplotlib
matplotlib.use('svg')
import qc_monitor.plotting
assert matplotlib.get_backend().lower() == 'svg'
'''
    process = subprocess.run([sys.executable, '-c', program], env=env,
                             capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stderr


@pytest.mark.parametrize('invalid', ['metadata', 'degree', 'coefficient', 'timestamp'])
def test_oloc_invalid_model_is_failure_and_later_model_proceeds(tmp_path, invalid):
    cfg, df, meta = example('order_location_fit', tmp_path)
    bad_cfg = deepcopy(cfg['figures'][0])
    bad_cfg.update(name='nir_bad', filename='bad.png', arm='NIR')
    cfg['figures'].insert(0, bad_cfg)
    bad = df.copy()
    bad['eso seq arm'] = 'NIR'
    bad['source_file'] = 'bad'
    bad_meta = meta.copy()
    bad_meta['source_file'] = 'bad'
    if invalid == 'degree': bad['degy_cent'] = .5
    if invalid == 'coefficient': bad['cent_00'] = np.nan
    if invalid == 'timestamp': bad['obs_date_utc'] = 'invalid'
    if invalid != 'metadata': meta = pd.concat([meta, bad_meta], ignore_index=True)
    results = generate_order_location_plots_from_config(pd.concat([df, bad], ignore_index=True),
        meta, cfg, continue_on_error=True)
    assert [r.state for r in results] == ['failed', 'produced']


@pytest.mark.parametrize('state', ['empty', 'partial_acquisition', 'partial_with_render_failure'])
def test_cli_empty_report_and_exit_precedence(lab, state):
    import sqlite3
    configure_cli(lab)
    if state == 'empty':
        lab.cfg['plots']['datapoint_queries']['sample']['filters'] = {'qc_name': 'absent'}
    else:
        with closing(sqlite3.connect(lab.upstream)) as conn, conn:
            conn.execute('UPDATE quality_control_plus_lite SET qc_value=?', ('invalid',))
    if state == 'partial_with_render_failure':
        lab.dsol()
        lab.cfg['plots']['figures'].append({'name': 'vis_dsol', 'type': 'dispersion_resolution',
            'filename': 'dsol.png', 'arm': 'VIS', 'selection': 'all'})
    lab.save_config()
    code = {'empty': 0, 'partial_acquisition': 1, 'partial_with_render_failure': 2}[state]
    data = summary(save_failure_cli(lab, 'dsol.png', code) if code == 2 else lab.cli(expected=code))
    assert data['report']['state'] == 'published'
    assert data['plots']['figures'][0]['state'] == 'no_data'
    assert '<img' not in (lab.output / 'index.html').read_text()
    if code == 2:
        assert data['plots']['state'] == 'partial'


def test_cli_all_failed_publishes_error_report(lab):
    configure_cli(lab)
    data = summary(save_failure_cli(lab, 'time_series.png', 2))
    assert data['plots']['state'] == 'failed'
    assert data['report']['state'] == 'published'
    report = (lab.output / 'index.html').read_text()
    assert '<img' not in report and 'Failed:' in report


def test_partial_report_retains_coordination_until_summary(lab):
    from qc_monitor.storage import SQLiteStore
    from qc_monitor.coordination import CoordinationBusyError
    configure_cli(lab)
    program = 'import qc_monitor.main as app\nFAILED_FILENAME=\"time_series.png\"\n' + SAVE_FAILURE + '''
import sys
from qc_monitor import publication as pub
original = pub._render_html_report
def pause(plots, path, template, figure_results, **kwargs):
    assert figure_results[0].state == 'failed'
    pub._render_html_report = original
    print('ready', flush=True)
    sys.stdin.read(1)
    return original(plots, path, template, figure_results, **kwargs)
pub._render_html_report = pause
sys.exit(app.main())
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', program,
        '--config', str(lab.config), '--summary-json', str(lab.root / 'summary.json')],
        cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'ready'
        before = tree_snapshot(lab.root)
        lab.cli('--no-plots', expected=2)
        with pytest.raises(CoordinationBusyError):
            SQLiteStore(lab.db)
        assert tree_snapshot(lab.root) == before
        _, errors = process.communicate(input='x', timeout=60)
        assert process.returncode == 2, errors
        assert json.loads((lab.root / 'summary.json').read_text())['report']['state'] == 'published'
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10)


def test_optional_detlin_values_and_insufficient_stats_are_not_invalid(tmp_path):
    cfg, df, meta = example('detector_linearity', tmp_path)
    df['fit_signal'] = np.nan
    df['saturation_limit'] = np.nan
    df['fit_used'] = 0
    result, = render('detector_linearity', cfg, df, meta)
    assert result.state == 'produced' and not result.discarded
    df['fit_state'] = 'unavailable'
    result, = render('detector_linearity', cfg, df, meta)
    assert result.state == 'no_data'
    cfg, df, meta = example('dispersion_resolution_timeseries', tmp_path)
    df['n_points'] = 1
    result, = render('dispersion_resolution_timeseries', cfg, df, meta)
    assert result.state == 'no_data' and not result.discarded


@pytest.mark.parametrize('kind', ['dispersion_resolution', 'dispersion_resolution_timeseries',
                                  'detector_linearity', 'order_location_fit'])
def test_known_series_with_all_invalid_samples_fails_whole_figure(kind, tmp_path):
    cfg, df, meta = example(kind, tmp_path)
    if kind == 'order_location_fit':
        meta.loc[0, 'ymax'] = np.nan
    elif kind == 'detector_linearity':
        df.loc[0, 'detector_mode'] = 'FLG'
        df.loc[0, 'signal'] = np.nan
    else:
        df.loc[0, primary(kind)] = np.nan
    result, = render(kind, cfg, df, meta, continue_on_error=True)
    assert result.state == 'failed' and result.path is None
    assert plt.get_fignums() == []

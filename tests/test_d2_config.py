"""D2: reject bad contracts before opening writable resources."""
from copy import deepcopy
from pathlib import Path

import pytest

from conftest import tree_snapshot, rows
from qc_monitor.config import ConfigurationError, load_config, load_plot_includes, normalize_runtime_config
from qc_monitor.acquisition import find_session_databases


@pytest.mark.parametrize('section,key,value', [
    ('acquisition', 'allow_multiple_upstream_databases', 'false'),
    ('acquisition', 'upstream_database_search', 'typo'),
    ('acquisition', 'reduced_products_search', 'all'),
    ('acquisition', 'upstream_database_name', '../soxspipe.db'),
    ('acquisition', 'unknown', True),
    ('acquisition', 'suspicious_path_tokens', 'test'),
    ('plots', 'show', 'false'),
    ('plots', 'figures', {}),
    ('detector_linearity', 'enabled', 1),
    ('detector_linearity', 'statistic', 'maximum'),
    ('detector_linearity', 'saturation_level', float('inf')),
    ('detector_linearity', 'saturation_fraction', 0),
    ('detector_linearity', 'saturation_fraction', 1.1),
])
def test_invalid_configuration_is_write_free(lab, section, key, value):
    lab.cfg[section][key] = value
    lab.save_config()
    before = tree_snapshot(lab.root)
    result = lab.cli('--no-plots', expected=2)
    assert key in result.stderr
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize('override', [
    {'type': 'misspelled'}, {'filename': '../escape.png'}, {'filename': '/absolute.png'},
    {'filename': 'not-an-image.html'}, {'bins': 0}, {'bins': 2.5},
    {'time_range': 'recent'}, {'time_column': 'typo'}, {'datapoint_query': 'absent'},
])
def test_invalid_figure_contracts(lab, override):
    lab.cfg['plots'].update(datapoint_queries={'sample': {'filters': {}}}, figures=[{
        'name': 'vis_sample', 'type': 'histogram', 'filename': 'sample.png',
        'datapoint_query': 'sample', **override}])
    lab.save_config()
    before = tree_snapshot(lab.root)
    lab.cli(expected=2)
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize('roi', [[0, 0, 0, 2], [0, 2, 2, 1], [-1, 2, 0, 2], [0, 2.5, 0, 2], [0, 2, 0], 'roi'])
def test_invalid_roi_before_pixels_or_database(lab, roi):
    lab.detlin()
    lab.cfg['detector_linearity']['arms']['VIS']['roi'] = roi
    lab.save_config()
    before = tree_snapshot(lab.root)
    assert '.roi' in lab.cli('--no-plots', expected=2).stderr
    assert tree_snapshot(lab.root) == before


def test_duplicate_yaml_rejected_but_anchor_override_allowed(lab):
    lab.config.write_text('plots: {}\nplots: {}\n')
    with pytest.raises(ConfigurationError, match='Duplicate YAML key'):
        load_config(lab.config)
    included = lab.config.parent / 'queries.yaml'
    included.write_text('anchors: {base: &base {qc_name: old}}\ndatapoint_queries:\n  q:\n    filters: {<<: *base, qc_name: new}\n')
    lab.cfg['plots']['include'] = ['queries.yaml']
    lab.save_config()
    assert load_config(lab.config)['plots']['datapoint_queries']['q']['filters']['qc_name'] == 'new'
    included.write_text('datapoint_queries: {q: {filters: {qc_name: old, qc_name: new}}}\n')
    with pytest.raises(ConfigurationError, match='queries.yaml'):
        load_config(lab.config)


@pytest.mark.parametrize('kind', ['query-column', 'figure-name', 'figure-filename', 'series-style', 'figure-field'])
def test_query_and_figure_cross_validation(lab, kind):
    figure = {'name': 'vis_time', 'type': 'time_series', 'filename': 'time.png',
              'series': [{'label': 'sample', 'datapoint_query': 'q'}]}
    lab.cfg['plots'].update(figures=[figure], datapoint_queries={'q': {'filters': {}}})
    if kind == 'query-column':
        lab.cfg['plots']['datapoint_queries']['q']['filters'] = {'misspelled': 1}
    elif kind == 'series-style':
        figure['series'][0]['style'] = 'bars'
    elif kind == 'figure-field':
        figure['misspelled'] = True
    else:
        duplicate = deepcopy(figure)
        duplicate['name' if kind == 'figure-filename' else 'filename'] = 'different.png'
        lab.cfg['plots']['figures'].append(duplicate)
    lab.save_config()
    before = tree_snapshot(lab.root)
    lab.cli(expected=2)
    assert tree_snapshot(lab.root) == before


def test_relative_paths_use_parent_of_config_directory(lab):
    lab.cfg['paths'] = {'upstream_root': 'upstream', 'reduced_root': 'reduced', 'qc_database': 'monitor/qc.sqlite'}
    lab.save_config()
    cfg = normalize_runtime_config(load_config(lab.config), lab.config.parent.parent)
    assert cfg['paths']['upstream_root'] == str(lab.upstream.parent)
    lab.cli('--no-plots')
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(1,)]


def test_recursive_discovery_includes_direct_and_nested_databases(lab):
    nested = lab.make_upstream(lab.upstream.parent / 'nested' / 'soxspipe.db', 'nested')
    assert find_session_databases(lab.upstream.parent, 'soxspipe.db', 'direct') == [lab.upstream]
    assert set(find_session_databases(lab.upstream.parent, 'soxspipe.db', 'recursive')) == {lab.upstream, nested}
    lab.cfg['acquisition']['upstream_database_search'] = 'recursive'
    lab.save_config()
    before = tree_snapshot(lab.root)
    lab.cli('--preflight', expected=2)
    assert tree_snapshot(lab.root) == before
    lab.cfg['acquisition']['allow_multiple_upstream_databases'] = True
    lab.save_config()
    lab.cli('--no-plots')
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(2,)]


@pytest.mark.parametrize('destination', ['upstream', 'config', 'fits', 'html-db', 'symlink'])
def test_output_collisions_are_rejected_before_database_creation(lab, destination):
    if destination == 'upstream':
        lab.cfg['paths']['qc_database'] = str(lab.upstream)
    elif destination == 'config':
        lab.cfg['plots']['html_output'] = str(lab.config)
    elif destination == 'fits':
        lab.cfg['plots']['html_output'] = str(lab.dsol())
    elif destination == 'html-db':
        lab.cfg['plots']['html_output'] = str(lab.db)
    else:
        outside = lab.root / 'outside'
        outside.mkdir()
        output = lab.output / 'plots'
        output.mkdir(parents=True)
        (output / 'escape').symlink_to(outside, target_is_directory=True)
        lab.cfg['plots'].update(datapoint_queries={'q': {}}, figures=[{
            'name': 'vis_escape', 'type': 'histogram', 'filename': 'escape/plot.png', 'datapoint_query': 'q'}])
    lab.save_config()
    before = tree_snapshot(lab.root)
    lab.cli('--preflight', expected=2)
    assert tree_snapshot(lab.root) == before


def test_no_plots_ignores_unused_publication_resources(lab):
    lab.cfg['plots'].update(output_dir=str(lab.upstream), html_output=str(lab.reduced), template='missing.html')
    lab.save_config()
    lab.cli('--no-plots')
    assert rows(lab.db, 'SELECT count(*) FROM qc_metrics') == [(1,)]


def test_operational_yaml_preserves_report_groups_and_default_queries():
    cfg = load_config(Path(__file__).resolve().parents[1] / 'configs/qc_monitor.yaml')
    assert len(cfg['plots']['figures']) == 22
    assert len(cfg['plots']['datapoint_queries']) == 49
    assert all('arm' in f and 'section' in f for f in cfg['plots']['figures'])
    assert all('processing' not in q for q in cfg['plots']['datapoint_queries'].values())


@pytest.mark.parametrize('field,value', [('bins', 10**9), ('filename', '..\\escape.png')])
def test_resource_and_portable_filename_limits(lab, field, value):
    lab.cfg['plots'].update(datapoint_queries={'q': {}}, figures=[{
        'type': 'histogram', 'name': 'vis_large', 'filename': 'large.png', 'datapoint_query': 'q', field: value}])
    lab.save_config()
    with pytest.raises(ConfigurationError, match=field):
        load_config(lab.config)


def test_filename_case_collisions_are_portably_rejected(lab):
    lab.cfg['plots'].update(datapoint_queries={'q': {}}, figures=[
        {'type': 'histogram', 'name': 'vis_a', 'filename': 'a.png', 'datapoint_query': 'q'},
        {'type': 'histogram', 'name': 'vis_b', 'filename': 'A.png', 'datapoint_query': 'q'}])
    lab.save_config()
    with pytest.raises(ConfigurationError, match='Duplicate'):
        load_config(lab.config)


@pytest.mark.parametrize('artifact', ['.lock', '-wal', '-shm', '-journal'])
def test_summary_cannot_replace_storage_control_files(lab, artifact):
    lab.seed()
    before = tree_snapshot(lab.root)
    lab.cli('--no-plots', '--summary-json', str(lab.db) + artifact, expected=2)
    assert tree_snapshot(lab.root) == before


def test_configuration_collision_does_not_write_even_diagnostic_json(lab):
    lab.cfg['plots']['html_output'] = str(lab.config)
    lab.save_config()
    before = tree_snapshot(lab.root)
    lab.cli('--summary-json', str(lab.root / 'summary.json'), expected=2)
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize('filters', [{'exptime': '2.0'}, {'qc_order': 10}, {'qc_value': True}])
def test_filter_types_follow_upstream_column_contract(lab, filters):
    lab.cfg['plots']['datapoint_queries'] = {'bad': {'filters': filters}}
    lab.save_config()
    with pytest.raises(ConfigurationError, match='filters'):
        load_config(lab.config)


def test_null_filter_distinguishes_missing_value_from_zero():
    import pandas as pd
    from qc_monitor.plotting import resolve_datapoint_query
    data = pd.DataFrame({'qc_value_min': [None, 0., 1.]})
    selected = resolve_datapoint_query(data, 'missing', {'missing': {'filters': {'qc_value_min': None}}})
    assert list(selected.index) == [0]


def test_last_three_months_is_calendar_window_anchored_to_selected_data():
    import pandas as pd
    from qc_monitor.plotting import _apply_time_range
    data = pd.DataFrame({'obs_date_utc': ['2026-02-27', '2026-02-28', '2026-03-01', '2026-05-31']})
    assert _apply_time_range(data, 'obs_date_utc', 'last_3_months').obs_date_utc.tolist() == [
        '2026-02-28', '2026-03-01', '2026-05-31']


def test_unknown_report_tab_cannot_silently_drop_configured_figure(lab):
    lab.cfg['plots'].update(datapoint_queries={'q': {}}, figures=[{
        'name': 'unclassified', 'type': 'histogram', 'filename': 'unclassified.png', 'datapoint_query': 'q'}])
    lab.save_config()
    with pytest.raises(ConfigurationError, match='report tab'):
        load_config(lab.config)
    lab.cfg['plots']['figures'][0]['arm'] = 'VIS'
    lab.save_config()
    assert load_config(lab.config)['plots']['figures'][0]['arm'] == 'VIS'

"""D4 compatibility and independent pre-refactor rendering/storage contracts."""
from contextlib import closing
import importlib
import inspect
import json
from pathlib import Path
import pickle
import sqlite3
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from conftest import DAY, database_snapshot, rows
from qc_monitor.acquisition import (_load_dsol_batch, _load_oloc_batch,
                                    load_qc_from_session_db, parse_optional_float, parse_qc_value)
from qc_monitor.detector_linearity import load_detector_linearity_data
from qc_monitor.storage import SQLiteStore
from qc_monitor import _plots_common
from test_d3c_rendering import example, render, KINDS

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.mark.parametrize('module', ['main', 'plotting', 'acquisition', 'storage', 'SQLiteStore'])
def test_pre_d4_imports_and_signatures_remain_usable(module):
    expected = json.loads((FIXTURES / 'd4-api-signatures.json').read_text())[module]
    target = SQLiteStore if module == 'SQLiteStore' else importlib.import_module('qc_monitor.' + module)
    for name, signature in expected.items():
        actual = str(inspect.signature(getattr(target, name)))
        # Python 3.13 relocated the implementation of the same public pathlib types.
        assert actual.replace("pathlib._local.", "pathlib.") == signature, name
    importlib.import_module('qc_monitor.processing')


def test_registry_and_main_do_not_import_pyplot_before_backend_selection():
    root = Path(__file__).resolve().parents[1]
    code = f'''import sys
sys.path.insert(0, {str(root)!r})
from qc_monitor._renderers import RENDERERS
from qc_monitor.config import FIGURE_FIELDS
import qc_monitor.main
assert set(RENDERERS) == set(FIGURE_FIELDS)
assert len(RENDERERS) == 10
assert 'matplotlib.pyplot' not in sys.modules
assert 'qc_monitor.plotting' not in sys.modules
assert RENDERERS['order_location_fit'].dataset == 'oloc'
'''
    subprocess.run([sys.executable, '-I', '-W', 'error', '-c', code], check=True,
                   capture_output=True, text=True, timeout=20)


@pytest.mark.parametrize('name,args', [('PlotSeries', ('sample', 'Sample')),
                                      ('InvalidPlotData', ('bad sample',))])
def test_public_plot_types_keep_serializable_identity(name, args):
    from qc_monitor import plotting
    cls = getattr(plotting, name)
    value = cls(*args)
    assert cls.__module__ == 'qc_monitor.plotting'
    assert type(pickle.loads(pickle.dumps(value))) is cls


@pytest.mark.parametrize('value,expected', [(None, None), (pd.NA, None), ('invalid', None),
    ('nan', None), (np.inf, None), (-np.inf, None), ('0', 0.), ('-2.5', -2.5),
    (np.float64(3.25), 3.25)])
def test_public_numeric_converters_preserve_finite_values(value, expected):
    assert parse_qc_value(value) == expected
    assert parse_optional_float(value) == expected


WRITERS = [
    ('write_metrics', 'qc_metrics'),
    ('write_dispersion_solution_lines', 'dispersion_solution_lines'),
    ('write_dispersion_resolution_stats', 'dispersion_resolution_stats'),
    ('write_order_location_models', 'order_location_models'),
    ('write_order_location_meta', 'order_location_meta'),
    ('write_detector_linearity_measurements', 'detector_linearity_measurements'),
    ('write_detector_linearity_results', 'detector_linearity_results'),
]


def writer_frame(lab, table):
    if table == 'qc_metrics':
        return load_qc_from_session_db(lab.upstream, lab.cfg)
    if table.startswith('dispersion'):
        batch = _load_dsol_batch([lab.dsol()])
        return batch.frames['lines' if table.endswith('lines') else 'stats']
    if table.startswith('order_location'):
        batch = _load_oloc_batch([lab.oloc()])
        return batch.frames['models' if table.endswith('models') else 'meta']
    lab.detlin()
    measurements, results = load_detector_linearity_data(lab.cfg)
    return measurements if table.endswith('measurements') else results


@pytest.mark.parametrize('writer,table', WRITERS)
def test_domain_writers_keep_column_order_and_real_sql_types(lab, writer, table):
    frame = writer_frame(lab, table)
    assert not frame.empty
    # Object dtype forces the SQL boundary to adapt NumPy scalars, not pandas.
    store = SQLiteStore(lab.db)
    sql_types = {record[1]: record[2] for record in rows(lab.db, f"PRAGMA table_info({table})")}
    numeric = next(col for col in frame if pd.api.types.is_numeric_dtype(frame[col])
                   and sql_types[col] in ("REAL", "INTEGER"))
    frame[numeric] = pd.Series([np.float64(value) for value in frame[numeric]], dtype=object)
    frame['unrelated'] = 'ignored'
    frame = frame[list(reversed(frame.columns))]
    store = SQLiteStore(lab.db)
    getattr(store, writer)(frame)
    assert rows(lab.db, f'SELECT count(*) FROM {table}') == [(len(frame),)]
    assert all(kind in ('integer', 'real', 'null')
               for kind, in rows(lab.db, f'SELECT typeof("{numeric}") FROM {table}'))
    assert rows(lab.db, 'PRAGMA foreign_key_check') == []


@pytest.mark.parametrize('missing', [pd.NA, np.nan, None])
def test_optional_sql_nulls_and_provenance_survive_public_writer(lab, missing):
    store = SQLiteStore(lab.db)
    frame = load_qc_from_session_db(lab.upstream, lab.cfg)
    frame['qc_value_min'] = pd.Series([missing], dtype=object)
    frame['qc_value_max'] = pd.Series([np.float64(101.5)], dtype=object)
    store.write_metrics(frame)
    assert rows(lab.db, 'SELECT qc_value_min,qc_value_max,typeof(qc_value_max) FROM qc_metrics') == [(None, 101.5, 'real')]
    assert rows(lab.db, 'SELECT source_path FROM qc_metric_sources') == [(str(lab.upstream.resolve()),)]


def test_public_writer_rolls_back_when_later_row_conflicts(lab):
    store = SQLiteStore(lab.db)
    frame = load_qc_from_session_db(lab.upstream, lab.cfg)
    store.write_metrics(frame)
    before = database_snapshot(lab.db)
    new = frame.copy()
    new['obs_date_utc'] = DAY + 'T12:00:00'
    batch = pd.concat([new, frame], ignore_index=True)
    with pytest.raises(sqlite3.IntegrityError):
        store.write_metrics(batch)
    assert database_snapshot(lab.db) == before


@pytest.mark.parametrize('domain,args,getter', [
    ('obs', (DAY,), 'get_processed_obs_days'),
    ('dispersion_obs', (DAY,), 'get_processed_dispersion_obs_days'),
    ('order_location_obs', (DAY,), 'get_processed_order_location_obs_days'),
    ('detector_linearity_obs', (DAY, 'VIS'), 'get_processed_detector_linearity_obs_days'),
])
def test_registry_status_and_domain_keys_are_preserved(lab, domain, args, getter):
    store = SQLiteStore(lab.db)
    register = getattr(store, 'register_processed_' + domain + '_day')
    # Public spelling uses days for the getter and day for registration.
    register(*args, status='FAILED')
    assert getattr(store, getter)() == set()
    register(*args)
    expected = {args} if len(args) == 2 else {DAY}
    assert getattr(store, getter)() == expected


@pytest.mark.parametrize('kind', KINDS)
def test_renderer_data_matches_independent_pre_d4_capture(kind, tmp_path, monkeypatch):
    expected = json.loads((FIXTURES / 'd4-renderer-data.json').read_text())[kind]
    captured = {}
    original = _plots_common._save_figure
    def save(path, fig=None):
        axes = []
        for ax in fig.axes:
            axes.append({'title': ax.get_title(), 'xlabel': ax.get_xlabel(), 'ylabel': ax.get_ylabel(),
                'lines': [{'x': line.get_xdata(orig=False).tolist(), 'y': line.get_ydata(orig=False).tolist(),
                           'label': line.get_label()} for line in ax.lines],
                'offsets': [collection.get_offsets().tolist() for collection in ax.collections],
                'bars': [[p.get_x(), p.get_y(), p.get_width(), p.get_height()]
                         for p in ax.patches if hasattr(p, 'get_height')]})
        captured['axes'] = axes
        original(path, fig)
    monkeypatch.setattr(_plots_common, '_save_figure', save)
    cfg, df, meta = example(kind, tmp_path)
    result, = render(kind, cfg, df, meta)
    captured.update(state=result.state, discarded=result.discarded)
    # JSON NaN encoding also handles Matplotlib's masked empty collection offsets.
    assert json.dumps(captured, sort_keys=True, default=lambda value: value.item()) == json.dumps(expected, sort_keys=True)


def test_runtime_rechecks_configuration_under_resource_protection(lab, monkeypatch):
    from contextlib import ExitStack
    from types import SimpleNamespace
    from qc_monitor import _runtime
    from qc_monitor.config import ConfigurationError
    from qc_monitor.run_result import RunResult
    original = _runtime.load_config
    reads = []
    def changed(path):
        cfg = original(path)
        reads.append(path)
        if len(reads) == 2:
            cfg['plots']['page_title'] = 'Changed while acquiring resources'
        return cfg
    monkeypatch.setattr(_runtime, 'load_config', changed)
    with ExitStack() as stack:
        args = SimpleNamespace(config=lab.config, summary_json=None, dry_run=False,
                               preflight=False, no_plots=True, _operation_stack=stack)
        with pytest.raises(ConfigurationError, match='changed during operational coordination'):
            _runtime.prepare_runtime(args, RunResult('run'))
    assert len(reads) == 2
    assert not lab.db.exists()


@pytest.mark.parametrize('kind', ['unknown', None, ['invalid'], 'order_location_fit'])
def test_single_frame_dispatch_preserves_unsupported_type_error(kind, tmp_path):
    from qc_monitor.plotting import plot_from_config
    with pytest.raises(ValueError, match='Unsupported plot type'):
        plot_from_config(pd.DataFrame(), {'type': kind}, {}, tmp_path)


@pytest.mark.parametrize('missing', [pd.NA, np.nan])
def test_required_sql_values_are_rejected_without_partial_insert(lab, missing):
    store = SQLiteStore(lab.db)
    before = database_snapshot(lab.db)
    frame = load_qc_from_session_db(lab.upstream, lab.cfg)
    frame['qc_value'] = pd.Series([missing], dtype=object)
    with pytest.raises(sqlite3.IntegrityError):
        store.write_metrics(frame)
    assert database_snapshot(lab.db) == before

"""YAML loading, defaults and validation, independent of storage and plotting."""
from copy import deepcopy
from pathlib import Path
import math
import yaml

from qc_monitor.schema import TABLE_SCHEMA
from qc_monitor._renderers import RENDERERS


class ConfigurationError(RuntimeError, ValueError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        # Check explicit keys BEFORE flattening merges: local anchor overrides are valid.
        explicit = set()
        for key_node, _ in node.value:
            if key_node.tag == 'tag:yaml.org,2002:merge':
                continue
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in explicit:
                    raise ConfigurationError(f'{key_node.start_mark}: Duplicate YAML key {key!r}')
                explicit.add(key)
            except TypeError as exc:
                raise ConfigurationError(f'{key_node.start_mark}: YAML keys must be scalar') from exc
        self.flatten_mapping(node)
        return super().construct_mapping(node, deep=deep)


def _mapping(value, field):
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ConfigurationError(f'{field}: expected a mapping with string keys')
    return value


def _keys(value, allowed, field):
    _mapping(value, field)
    unknown = set(value) - set(allowed)
    if unknown:
        raise ConfigurationError(f'{field}: unknown fields {sorted(unknown)}')


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ConfigurationError(f'{field}: expected nonempty text')


def _boolean(value, field):
    if type(value) is not bool:
        raise ConfigurationError(f'{field}: expected a boolean')


def _number(value, field, *, positive=True, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigurationError(f'{field}: expected a finite number')
    if integer and type(value) is not int:
        raise ConfigurationError(f'{field}: expected an integer')
    if positive and value <= 0:
        raise ConfigurationError(f'{field}: expected a positive number')


def _choice(value, choices, field):
    if not isinstance(value, str) or value not in choices:
        raise ConfigurationError(f'{field}: expected one of {sorted(choices)}')


def _list(value, field):
    if not isinstance(value, list):
        raise ConfigurationError(f'{field}: expected a list')
    return value


def _read_yaml(path):
    try:
        with Path(path).open(encoding='utf-8') as source:
            result = yaml.load(source, Loader=UniqueKeyLoader)
        return _mapping(result, str(path))
    except (yaml.YAMLError, OSError) as exc:
        raise ConfigurationError(f'{path}: {exc}') from exc


def load_plot_includes(cfg, config_dir):
    cfg = deepcopy(_mapping(cfg, 'configuration'))
    plots = _mapping(cfg.setdefault('plots', {}), 'plots')
    files = _list(plots.get('include', []), 'plots.include')
    figures = list(_list(plots.get('figures', []), 'plots.figures'))
    queries = dict(_mapping(plots.get('datapoint_queries', {}), 'plots.datapoint_queries'))
    origins = ['main YAML'] * len(figures)
    query_origins = {name: 'main YAML' for name in queries}
    includes = []
    for file in files:
        _text(file, 'plots.include')
        path = (Path(config_dir) / file).expanduser().resolve()
        included = _read_yaml(path)
        _keys(included, {'figures', 'datapoint_queries', 'anchors'}, str(path))
        additions = _list(included.get('figures', []), f'{path}: figures')
        figures.extend(additions)
        origins.extend([str(path)] * len(additions))
        incoming = _mapping(included.get('datapoint_queries', {}), f'{path}: datapoint_queries')
        duplicate = set(queries) & set(incoming)
        if duplicate:
            raise ConfigurationError(f'Duplicate datapoint query names in {path}: {sorted(duplicate)}')
        queries.update(incoming)
        query_origins.update({name: str(path) for name in incoming})
        includes.append(str(path))
    plots.update(figures=figures, datapoint_queries=queries)
    cfg['_origins'] = {'figures': origins, 'queries': query_origins, 'includes': includes}
    return cfg


ACQUISITION_DEFAULTS = {
    'upstream_database_name': 'soxspipe.db', 'upstream_table': 'quality_control_plus_lite',
    'upstream_database_search': 'direct', 'allow_multiple_upstream_databases': False,
    'reduced_products_search': 'observing_day_dirs', 'allow_suspicious_paths': False,
    'suspicious_path_tokens': ['test', 'tmp', 'temporary', 'sandbox'],
}
DETLIN_DEFAULTS = {'enabled': False, 'filename_token': 'DETLIN', 'statistic': 'mean',
                   'saturation_level': 65536, 'saturation_fraction': .60, 'arms': {}}
PUBLICATION_DEFAULTS = {'retained_generations': 2, 'orphan_max_age_hours': 24,
                        'max_orphan_staging': 2}
PLOT_DEFAULTS = {'output_dir': 'plots', 'html_output': 'index.html', 'show': False,
                 'figures': [], 'datapoint_queries': {}, 'publication': PUBLICATION_DEFAULTS}
COMMON_FIGURE = {'name', 'type', 'filename', 'arm', 'section', 'title', 'wide',
                 'x_label', 'y_label'}
LEGEND = {'figsize', 'legend_fontsize', 'legend_ncol', 'legend_loc'}
FIGURE_FIELDS = {
    'time_series': {'series', 'time_range', 'x_column', 'y_column'},
    'xy_scatter': {'x', 'y', 'time_range', 'time_column', 'value_column', 'join_on'},
    'histogram': {'datapoint_query', 'time_range', 'time_column', 'value_column', 'bins'},
    'latest_by_order_bar': {'datapoint_query', 'order_sequence'},
    'dispersion_resolution': {'selection', 'aspect'},
    'dispersion_resolution_timeseries': LEGEND | {'min_n_points'},
    'dispersion_residual_xy': {'selection', 'aspect'},
    'dispersion_residual_histogram': {'selection', 'bins', 'figsize'},
    'order_location_fit': LEGEND | {'recipe', 'slit', 'axis_b_step', 'aspect', 'invert_yaxis'},
    'detector_linearity': LEGEND | {'selection', 'mode_order'},
}


assert set(FIGURE_FIELDS) == set(RENDERERS), "Renderer/configuration type contracts differ"

def validate_detector_linearity_config(options):
    _keys(options, DETLIN_DEFAULTS, 'detector_linearity')
    detlin = {**deepcopy(DETLIN_DEFAULTS), **deepcopy(options)}
    _boolean(detlin['enabled'], 'detector_linearity.enabled')
    _text(detlin['filename_token'], 'detector_linearity.filename_token')
    _choice(detlin['statistic'], {'mean', 'median'}, 'detector_linearity.statistic')
    for key in ('saturation_level', 'saturation_fraction'):
        _number(detlin[key], 'detector_linearity.' + key)
    if detlin['saturation_fraction'] > 1:
        raise ConfigurationError('detector_linearity.saturation_fraction: expected 0 < fraction <= 1')
    arms = _mapping(detlin['arms'], 'detector_linearity.arms')
    if detlin['enabled'] and not arms:
        raise ConfigurationError('detector_linearity.enabled requires configured arms')
    for arm, options in arms.items():
        field = f'detector_linearity.arms.{arm}'
        _choice(arm, {'VIS', 'NIR'}, field)
        _keys(options, {'root', 'roi', 'roi_name', 'allow_filename_fallback'}, field)
        _text(options.get('root'), field + '.root')
        options.setdefault('roi', [512, 537, 2000, 2100] if arm == 'VIS' else [0, 0, 0, 0])
        options.setdefault('roi_name', arm)
        options.setdefault('allow_filename_fallback', False)
        _text(options['roi_name'], field + '.roi_name')
        _boolean(options['allow_filename_fallback'], field + '.allow_filename_fallback')
        roi = _list(options['roi'], field + '.roi')
        if len(roi) != 4 or any(type(v) is not int or v < 0 for v in roi) or roi[0] >= roi[1] or roi[2] >= roi[3]:
            raise ConfigurationError(field + '.roi: expected four nonnegative integers with ordered bounds')
    return detlin


def validate_config(cfg):
    _keys(cfg, {'paths', 'acquisition', 'detector_linearity', 'plots', 'anchors', '_origins'}, 'configuration')
    paths = _mapping(cfg.get('paths'), 'paths')
    _keys(paths, {'upstream_root', 'reduced_root', 'qc_database'}, 'paths')
    for key in ('upstream_root', 'reduced_root', 'qc_database'):
        _text(paths.get(key), 'paths.' + key)
    for name, defaults in (('acquisition', ACQUISITION_DEFAULTS), ('detector_linearity', DETLIN_DEFAULTS), ('plots', PLOT_DEFAULTS)):
        section = _mapping(cfg.get(name, {}), name)
        _keys(section, set(defaults) | ({'template', 'include', 'page_title'} if name == 'plots' else set()), name)
        cfg[name] = {**deepcopy(defaults), **section}
    acq = cfg['acquisition']
    for field in ('upstream_database_name', 'upstream_table'):
        _text(acq[field], 'acquisition.' + field)
    if Path(acq['upstream_database_name']).name != acq['upstream_database_name']:
        raise ConfigurationError('acquisition.upstream_database_name: expected a filename')
    _choice(acq['upstream_database_search'], {'direct', 'recursive'}, 'acquisition.upstream_database_search')
    _choice(acq['reduced_products_search'], {'observing_day_dirs', 'recursive'}, 'acquisition.reduced_products_search')
    for key in ('allow_multiple_upstream_databases', 'allow_suspicious_paths'):
        _boolean(acq[key], 'acquisition.' + key)
    for token in _list(acq['suspicious_path_tokens'], 'acquisition.suspicious_path_tokens'):
        _text(token, 'acquisition.suspicious_path_tokens')
    detlin = cfg['detector_linearity']
    cfg['detector_linearity'] = validate_detector_linearity_config(detlin)
    plots = cfg['plots']
    for key in ('output_dir', 'html_output'):
        _text(plots[key], 'plots.' + key)
    if 'template' in plots:
        _text(plots['template'], 'plots.template')
    if 'page_title' in plots:
        _text(plots['page_title'], 'plots.page_title')
    _boolean(plots['show'], 'plots.show')
    policy = _mapping(plots['publication'], 'plots.publication')
    _keys(policy, PUBLICATION_DEFAULTS, 'plots.publication')
    policy = plots['publication'] = {**PUBLICATION_DEFAULTS, **policy}
    for key in ('retained_generations', 'max_orphan_staging'):
        _number(policy[key], 'plots.publication.' + key, integer=True, positive=False)
    if policy['retained_generations'] < 2 or policy['max_orphan_staging'] < 0:
        raise ConfigurationError('plots.publication: retained_generations >= 2 and max_orphan_staging >= 0 required')
    _number(policy['orphan_max_age_hours'], 'plots.publication.orphan_max_age_hours')
    queries = _mapping(plots['datapoint_queries'], 'plots.datapoint_queries')
    for name, query in queries.items():
        field = f"{cfg.get('_origins', {}).get('queries', {}).get(name, 'YAML')}: datapoint_queries.{name}"
        _text(name, field)
        _keys(query, {'filters', 'processing'}, field)
        filters = _mapping(query.get('filters', {}), field + '.filters')
        for column, value in filters.items():
            if column not in TABLE_SCHEMA:
                raise ConfigurationError(f'{field}.filters: unknown QC column {column}')
            if isinstance(value, (list, dict)) or (isinstance(value, float) and not math.isfinite(value)):
                raise ConfigurationError(f'{field}.filters.{column}: expected a finite scalar')
            if value is not None:
                if TABLE_SCHEMA[column].startswith('REAL'):
                    _number(value, field + '.filters.' + column, positive=False)
                elif not isinstance(value, str):
                    raise ConfigurationError(f'{field}.filters.{column}: expected text for a TEXT column')
        processing = query.get('processing', {})
        _keys(processing, {'function', 'params'}, field + '.processing')
        _choice(processing.get('function', 'none'), {'none'}, field + '.processing.function')
        _keys(processing.get('params', {}), set(), field + '.processing.params')
    figures = _list(plots['figures'], 'plots.figures')
    names, filenames = set(), set()
    for index, figure in enumerate(figures):
        origins = cfg.get('_origins', {}).get('figures', [])
        field = f'{origins[index] if index < len(origins) else "YAML"}: plots.figures[{index}]'
        _mapping(figure, field)
        kind = figure.get('type')
        _choice(kind, set(FIGURE_FIELDS), field + '.type')
        _keys(figure, COMMON_FIGURE | FIGURE_FIELDS[kind], field)
        for key in ('name', 'filename'):
            _text(figure.get(key), field + '.' + key)
        filename = Path(figure['filename'])
        if filename.is_absolute() or '..' in filename.parts or '\\' in figure['filename'] or filename.suffix.lower() != '.png':
            raise ConfigurationError(field + '.filename: expected a confined relative PNG filename')
        canonical = str(filename).casefold()
        if figure['name'] in names or canonical in filenames:
            raise ConfigurationError(field + ': Duplicate figure name or filename')
        names.add(figure['name']); filenames.add(canonical)
        if 'arm' in figure:
            _choice(figure['arm'], {'VIS', 'NIR'}, field + '.arm')
        elif kind.startswith('dispersion_') or kind in {'order_location_fit', 'detector_linearity'}:
            raise ConfigurationError(field + '.arm: required')
        else:
            name, title = figure['name'].lower(), figure.get('title', '')
            if name.startswith('vis_') or (isinstance(title, str) and title.startswith('VIS')):
                figure['arm'] = 'VIS'
            elif name.startswith('nir_') or (isinstance(title, str) and title.startswith('NIR')):
                figure['arm'] = 'NIR'
            else:
                raise ConfigurationError(field + '.arm: cannot infer report tab; specify VIS or NIR')
        if 'section' in figure:
            _text(figure['section'], field + '.section')
        for key in ('title', 'x_label', 'y_label', 'recipe', 'slit'):
            if key in figure:
                _text(figure[key], field + '.' + key)
        for key in ('wide', 'invert_yaxis'):
            if key in figure:
                _boolean(figure[key], field + '.' + key)
        for key in ('bins', 'axis_b_step', 'legend_ncol', 'min_n_points'):
            if key in figure:
                _number(figure[key], field + '.' + key, integer=True)
        if figure.get('bins', 1) > 10000:
            raise ConfigurationError(field + '.bins: maximum 10000')
        if 'legend_fontsize' in figure:
            _number(figure['legend_fontsize'], field + '.legend_fontsize')
        if 'figsize' in figure:
            size = _list(figure['figsize'], field + '.figsize')
            if len(size) != 2:
                raise ConfigurationError(field + '.figsize: expected width and height')
            for value in size:
                _number(value, field + '.figsize')
                if value > 32:
                    raise ConfigurationError(field + '.figsize: maximum 32 inches per dimension')
        if 'aspect' in figure:
            aspect = figure['aspect']
            if isinstance(aspect, str):
                _choice(aspect, {'equal', 'auto'} if kind == 'order_location_fit' else set(), field + '.aspect')
            else:
                _number(aspect, field + '.aspect')
        if 'selection' in figure:
            _choice(figure['selection'], {'latest', 'all'}, field + '.selection')
        if 'time_range' in figure:
            _choice(figure['time_range'], {'all', 'last_3_months'}, field + '.time_range')
        if 'legend_loc' in figure:
            _choice(figure['legend_loc'], {'best', 'upper right', 'upper left', 'lower left', 'lower right',
                                         'right', 'center left', 'center right', 'lower center', 'upper center', 'center'}, field + '.legend_loc')
            if kind == 'detector_linearity' and figure['legend_loc'] == 'best':
                raise ConfigurationError(field + '.legend_loc: best is unsupported by figure legends')
        for key in ('x_column', 'y_column', 'time_column', 'value_column', 'join_on'):
            if key in figure and figure[key] not in TABLE_SCHEMA:
                raise ConfigurationError(f'{field}.{key}: unknown QC column {figure[key]}')
        references = []
        if kind == 'time_series':
            series = _list(figure.get('series'), field + '.series')
            if not series:
                raise ConfigurationError(field + '.series: at least one series required')
            for item in series:
                _keys(item, {'datapoint_query', 'label', 'style'}, field + '.series')
                _text(item.get('label'), field + '.series.label')
                _choice(item.get('style', 'line+markers'), {'markers', 'line', 'line+markers'}, field + '.series.style')
                references.append(item.get('datapoint_query'))
        elif kind == 'xy_scatter':
            for axis in ('x', 'y'):
                item = figure.get(axis)
                _keys(item, {'datapoint_query', 'label'}, field + '.' + axis)
                if 'label' in item:
                    _text(item['label'], field + '.' + axis + '.label')
                references.append(item.get('datapoint_query'))
        elif kind in {'histogram', 'latest_by_order_bar'}:
            references.append(figure.get('datapoint_query'))
        for reference in references:
            _text(reference, field + '.datapoint_query')
            if reference not in queries:
                raise ConfigurationError(f'{field}: Datapoint query not found: {reference}')
        if 'order_sequence' in figure:
            order = _list(figure['order_sequence'], field + '.order_sequence')
            if any(isinstance(v, (list, dict)) for v in order) or len({str(v) for v in order}) != len(order):
                raise ConfigurationError(field + '.order_sequence: expected unique scalar labels')
        if kind == 'detector_linearity':
            modes = figure.get('mode_order', ['NIR'] if figure['arm'] == 'NIR' else ['SHG', 'FLG', 'SLG', 'FHG'])
            _list(modes, field + '.mode_order')
            allowed = {'NIR'} if figure['arm'] == 'NIR' else {'SHG', 'FLG', 'SLG', 'FHG'}
            if len(modes) not in (1, 4) or len(set(modes)) != len(modes) or not set(modes) <= allowed:
                raise ConfigurationError(field + '.mode_order: expected one or four distinct supported modes')
            figure['mode_order'] = modes
    return cfg


def load_config(config_path=Path('configs/qc_monitor.yaml')):
    path = Path(config_path).expanduser().resolve()
    try:
        return validate_config(load_plot_includes(_read_yaml(path), path.parent))
    except ConfigurationError as exc:
        raise ConfigurationError(f'{path}: {exc}') from exc


def resolve_project_path(path, project_root):
    path = Path(path).expanduser()
    return (path if path.is_absolute() else Path(project_root) / path).resolve()


def normalize_runtime_config(cfg, project_root, *, validated=False):
    cfg = deepcopy(cfg)
    if not validated:
        cfg = validate_config(cfg)
    for key in ('upstream_root', 'reduced_root', 'qc_database'):
        cfg['paths'][key] = str(resolve_project_path(cfg['paths'][key], project_root))
    for key in ('output_dir', 'html_output', 'template'):
        if key in cfg['plots']:
            cfg['plots'][key] = str(resolve_project_path(cfg['plots'][key], project_root))
    for arm in cfg['detector_linearity']['arms'].values():
        arm['root'] = str(resolve_project_path(arm['root'], project_root))
    return cfg

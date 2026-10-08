"""Declarative scientific columns, identities and SQLite schema version."""

# Upstream columns remain independent of historical storage metadata.
TABLE_SCHEMA = {
    "night start date": "TEXT NOT NULL",
    "obs_date_utc": "TEXT NOT NULL",
    "eso seq arm": "TEXT NOT NULL",
    "soxspipe_recipe": "TEXT NOT NULL",
    "qc_name": "TEXT NOT NULL",
    "qc_value": "REAL NOT NULL",
    "qc_order": "TEXT NOT NULL DEFAULT '-1'",
    "qc_unit": "TEXT",
    "qc_flag": "TEXT",
    "qc_value_min": "REAL",
    "qc_value_max": "REAL",
    "sof_name": "TEXT",
    "file": "TEXT",
    "status": "TEXT",
    "binning": "TEXT",
    "rospeed": "TEXT",
    "slit": "TEXT",
    "slitmask": "TEXT",
    "lamp": "TEXT",
    "exptime": "REAL",
    "template": "TEXT",
    "object": "TEXT",
    "filepath": "TEXT",
}


# Columns that uniquely identify a QC metric in the upstream database
UNIQUE_COLUMNS = [
    "obs_date_utc",
    "soxspipe_recipe",
    "qc_name",
    "eso seq arm",
    "qc_order",
    "file",
]

# Domain contracts shared by loaders, storage and configuration validation.
SCHEMA_VERSION = 1

DISPERSION_SOLUTION_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "soxspipe_recipe",
    "source_file",
    "filepath",
    "wavelength",
    "order",
    "slit_index",
    "slit_position",
    "detector_x",
    "detector_y",
    "observed_x",
    "observed_y",
    "x_diff",
    "y_diff",
    "fit_x",
    "fit_y",
    "residuals_x",
    "residuals_y",
    "residuals_xy",
    "sigma_clipped",
    "sharpness",
    "roundness1",
    "roundness2",
    "npix",
    "sky",
    "peak",
    "flux",
    "fwhm_pin_px",
    "R_pin",
    "pixelScaleNm",
    "detector_x_shifted",
    "detector_y_shifted",
    "R_slit",
    "fwhm_slit_px",
]

DISPERSION_RESOLUTION_STATS_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "soxspipe_recipe",
    "source_file",
    "filepath",
    "order",
    "mean_R_pin",
    "std_R_pin",
    "n_points",
]

ORDER_LOCATION_META_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "soxspipe_recipe",
    "source_file",
    "filepath",
    "slit",
    "slitmask",
    "lamp",
    "binning",
    "rospeed",
    "order",
    "xmin",
    "xmax",
    "ymin",
    "ymax",
    "maxThreshold",
    "minThreshold",
    "maxvalue",
]

ORDER_LOCATION_COEFF_COLUMNS = [
    "degorder_cent",
    "degy_cent",
    "degx_cent",
    *[f"cent_{i}{j}" for i in range(7) for j in range(6)],

    "degorder_std",
    "degy_std",
    "degx_std",
    *[f"std_{i}{j}" for i in range(7) for j in range(6)],

    "degorder_edgelow",
    "degorder_edgeup",
    "degy_edgelow",
    "degy_edgeup",
    "degx_edgelow",
    "degx_edgeup",
    *[f"edgelow_c{i}{j}" for i in range(7) for j in range(6)],
    *[f"edgeup_c{i}{j}" for i in range(7) for j in range(6)],
]

ORDER_LOCATION_MODEL_COLUMNS = (
    ORDER_LOCATION_META_COLUMNS
    + ORDER_LOCATION_COEFF_COLUMNS
)


DETECTOR_LINEARITY_MEASUREMENT_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "detector_mode",
    "frame_type",
    "exptime",
    "source_file",
    "sequence_image_name",
    "filepath",
    "roi_name",
    "roi_y1",
    "roi_y2",
    "roi_x1",
    "roi_x2",
    "statistic",
    "signal_raw",
]

DETECTOR_LINEARITY_RESULT_COLUMNS = [
    "obs_day",
    "obs_date_utc",
    "eso seq arm",
    "detector_mode",
    "exptime",
    "pair_index",
    "file1",
    "file2",
    "signal",
    "fit_signal",
    "residual",
    "residual_percent",
    "fit_used",
    "saturation_limit",
    "slope",
    "intercept",
    "mean_bias_roi",
    "rms_bias_adu",
    "cf",
    "rms_bias_e",
    "dark_file",
    "flat_files",
    "n_flat_frames",
]


DSOL_TYPE_MAP = {
    'obs_day': 'TEXT NOT NULL',
    'obs_date_utc': 'TEXT NOT NULL',
    'eso seq arm': 'TEXT NOT NULL',
    'soxspipe_recipe': 'TEXT NOT NULL',
    'source_file': 'TEXT NOT NULL',
    'filepath': 'TEXT',
    'wavelength': 'REAL',
    'order': 'TEXT',
    'slit_index': 'INTEGER',
    'slit_position': 'REAL',
    'detector_x': 'REAL',
    'detector_y': 'REAL',
    'observed_x': 'REAL',
    'observed_y': 'REAL',
    'x_diff': 'REAL',
    'y_diff': 'REAL',
    'fit_x': 'REAL',
    'fit_y': 'REAL',
    'residuals_x': 'REAL',
    'residuals_y': 'REAL',
    'residuals_xy': 'REAL',
    'sigma_clipped': 'TEXT',
    'sharpness': 'REAL',
    'roundness1': 'REAL',
    'roundness2': 'REAL',
    'npix': 'REAL',
    'sky': 'REAL',
    'peak': 'REAL',
    'flux': 'REAL',
    'fwhm_pin_px': 'REAL',
    'R_pin': 'REAL',
    'pixelScaleNm': 'REAL',
    'detector_x_shifted': 'REAL',
    'detector_y_shifted': 'REAL',
    'R_slit': 'REAL',
    'fwhm_slit_px': 'REAL',
}

RESOLUTION_STATS_TYPE_MAP = {
    'obs_day': 'TEXT NOT NULL',
    'obs_date_utc': 'TEXT NOT NULL',
    'eso seq arm': 'TEXT NOT NULL',
    'soxspipe_recipe': 'TEXT NOT NULL',
    'source_file': 'TEXT NOT NULL',
    'filepath': 'TEXT',
    'order': 'TEXT NOT NULL',
    'mean_R_pin': 'REAL',
    'std_R_pin': 'REAL',
    'n_points': 'INTEGER',
}

ORDER_LOCATION_TYPE_MAP = {
    'obs_day': 'TEXT NOT NULL',
    'obs_date_utc': 'TEXT NOT NULL',
    'eso seq arm': 'TEXT NOT NULL',
    'soxspipe_recipe': 'TEXT NOT NULL',
    'source_file': 'TEXT NOT NULL',
    'filepath': 'TEXT',
    'slit': 'TEXT',
    'slitmask': 'TEXT',
    'lamp': 'TEXT',
    'binning': 'TEXT',
    'rospeed': 'TEXT',
}

ORDER_LOCATION_META_TYPE_MAP = {
    'obs_day': 'TEXT NOT NULL',
    'obs_date_utc': 'TEXT NOT NULL',
    'eso seq arm': 'TEXT NOT NULL',
    'soxspipe_recipe': 'TEXT NOT NULL',
    'source_file': 'TEXT NOT NULL',
    'filepath': 'TEXT',
    'slit': 'TEXT',
    'slitmask': 'TEXT',
    'lamp': 'TEXT',
    'binning': 'TEXT',
    'rospeed': 'TEXT',
    'order': 'REAL NOT NULL',
    'xmin': 'REAL',
    'xmax': 'REAL',
    'ymin': 'REAL',
    'ymax': 'REAL',
    'maxThreshold': 'REAL',
    'minThreshold': 'REAL',
    'maxvalue': 'REAL',
}

DETLIN_MEASUREMENT_TYPE_MAP = {
    'obs_day': 'TEXT NOT NULL',
    'obs_date_utc': 'TEXT NOT NULL',
    'eso seq arm': 'TEXT NOT NULL',
    'detector_mode': 'TEXT NOT NULL',
    'frame_type': 'TEXT NOT NULL',
    'exptime': 'REAL NOT NULL',
    'source_file': 'TEXT NOT NULL',
    'sequence_image_name': 'TEXT',
    'filepath': 'TEXT',
    'roi_name': 'TEXT',
    'roi_y1': 'INTEGER',
    'roi_y2': 'INTEGER',
    'roi_x1': 'INTEGER',
    'roi_x2': 'INTEGER',
    'statistic': 'TEXT',
    'signal_raw': 'REAL',
}

DETLIN_RESULT_TYPE_MAP = {
    'obs_day': 'TEXT NOT NULL',
    'obs_date_utc': 'TEXT NOT NULL',
    'eso seq arm': 'TEXT NOT NULL',
    'detector_mode': 'TEXT NOT NULL',
    'exptime': 'REAL NOT NULL',
    'pair_index': 'INTEGER NOT NULL',
    'file1': 'TEXT NOT NULL',
    'file2': 'TEXT NOT NULL',
    'signal': 'REAL',
    'fit_signal': 'REAL',
    'residual': 'REAL',
    'residual_percent': 'REAL',
    'fit_used': 'INTEGER',
    'saturation_limit': 'REAL',
    'slope': 'REAL',
    'intercept': 'REAL',
    'mean_bias_roi': 'REAL',
    'rms_bias_adu': 'REAL',
    'cf': 'REAL',
    'rms_bias_e': 'REAL',
    'dark_file': 'TEXT',
    'flat_files': 'TEXT',
    'n_flat_frames': 'INTEGER',
}

SEQUENCE_COLUMNS = ['sequence_id', 'tpl_start', 'tpl_id', 'bin_x', 'bin_y',
                    'image_width', 'image_height']
DETECTOR_LINEARITY_MEASUREMENT_COLUMNS += SEQUENCE_COLUMNS + ['tpl_nexp', 'tpl_expno', 'binning_assumed']
DETECTOR_LINEARITY_RESULT_COLUMNS += SEQUENCE_COLUMNS + ['fit_state', 'fit_reason']
for column in ('roi_name', 'roi_x1', 'roi_x2', 'roi_y1', 'roi_y2', 'statistic', 'signal_raw'):
    DETLIN_MEASUREMENT_TYPE_MAP[column] += ' NOT NULL'
for column in SEQUENCE_COLUMNS + ['tpl_nexp', 'tpl_expno', 'binning_assumed']:
    DETLIN_MEASUREMENT_TYPE_MAP[column] = ('INTEGER' if column in {
        'bin_x', 'bin_y', 'image_width', 'image_height', 'tpl_nexp', 'tpl_expno', 'binning_assumed'
    } else 'TEXT') + ' NOT NULL'
for column in SEQUENCE_COLUMNS + ['fit_state', 'fit_reason']:
    DETLIN_RESULT_TYPE_MAP[column] = ('INTEGER' if column in {
        'bin_x', 'bin_y', 'image_width', 'image_height'
    } else 'TEXT') + ' NOT NULL'

UNIT_TABLES = {
    'qc': [('qc_metrics', list(TABLE_SCHEMA), UNIQUE_COLUMNS)],
    'dsol': [('dispersion_solution_lines', DISPERSION_SOLUTION_COLUMNS,
              ['filepath', 'order', 'wavelength', 'detector_x', 'detector_y']),
             ('dispersion_resolution_stats', DISPERSION_RESOLUTION_STATS_COLUMNS, ['filepath', 'order'])],
    'oloc': [('order_location_models', ORDER_LOCATION_MODEL_COLUMNS, ['filepath']),
             ('order_location_meta', ORDER_LOCATION_META_COLUMNS, ['filepath', 'order'])],
    'detlin': [('detector_linearity_measurements', DETECTOR_LINEARITY_MEASUREMENT_COLUMNS, ['filepath']),
               ('detector_linearity_results', DETECTOR_LINEARITY_RESULT_COLUMNS,
                ['sequence_id', 'detector_mode', 'exptime', 'pair_index'])],
}
REGISTERS = {'qc': 'processed_obs_days', 'dsol': 'processed_dispersion_obs_days',
             'oloc': 'processed_order_location_obs_days', 'detlin': 'processed_detector_linearity_obs_days'}
TYPE_MAPS = {'qc_metrics': TABLE_SCHEMA, 'dispersion_solution_lines': DSOL_TYPE_MAP,
             'dispersion_resolution_stats': RESOLUTION_STATS_TYPE_MAP,
             'order_location_models': ORDER_LOCATION_TYPE_MAP,
             'order_location_meta': ORDER_LOCATION_META_TYPE_MAP,
             'detector_linearity_measurements': DETLIN_MEASUREMENT_TYPE_MAP,
             'detector_linearity_results': DETLIN_RESULT_TYPE_MAP}


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def schema_statements():
    """Generate only mechanical SQL; scientific keys are declared above."""
    statements = []
    statements.append('''CREATE TABLE detlin_sequences (
        sequence_id TEXT PRIMARY KEY NOT NULL, arm TEXT NOT NULL,
        tpl_start TEXT NOT NULL, tpl_id TEXT NOT NULL, obs_day TEXT NOT NULL,
        UNIQUE(arm, tpl_start, tpl_id))''')
    for family, tables in UNIT_TABLES.items():
        for table, columns, keys in tables:
            types = TYPE_MAPS[table]
            definitions = ['id INTEGER PRIMARY KEY AUTOINCREMENT']
            for column in columns:
                kind = types.get(column, 'REAL' if family == 'oloc' else 'TEXT')
                if column in keys and not (family == 'qc' and column == 'file') and 'NOT NULL' not in kind:
                    kind += ' NOT NULL'
                if column == 'sequence_id':
                    kind += ' REFERENCES detlin_sequences(sequence_id)'
                definitions.append(f'{quote(column)} {kind}')
            if family != 'qc':
                definitions.append('UNIQUE (' + ', '.join(map(quote, keys)) + ')')
            if family == 'detlin':
                definitions += ['CHECK(bin_x > 0 AND bin_y > 0 AND image_width > 0 AND image_height > 0)']
                if table.endswith('measurements'):
                    definitions += ['CHECK(tpl_nexp > 0 AND tpl_expno BETWEEN 1 AND tpl_nexp)',
                                    'CHECK(binning_assumed IN (0,1))',
                                    'CHECK(roi_x1 >= 0 AND roi_y1 >= 0 AND roi_x2 > roi_x1 AND roi_y2 > roi_y1 '
                                    'AND roi_x2 <= image_width AND roi_y2 <= image_height)']
                else:
                    definitions += ["CHECK(fit_state IN ('available','unavailable'))", 'CHECK(fit_used IN (0,1))',
                                    "CHECK((fit_state='available' AND slope IS NOT NULL AND intercept IS NOT NULL "
                                    "AND fit_signal IS NOT NULL AND fit_reason='') OR (fit_state='unavailable' "
                                    "AND slope IS NULL AND intercept IS NULL AND fit_signal IS NULL "
                                    "AND fit_used=0 AND length(fit_reason)>0))"]
            statements.append(f'CREATE TABLE {quote(table)} (' + ', '.join(definitions) + ')')
        register = REGISTERS[family]
        statements.append(f'CREATE TABLE {register} (obs_day TEXT NOT NULL, '
                          + ('arm TEXT NOT NULL, ' if family == 'detlin' else '')
                          + 'processed_at TEXT NOT NULL, status TEXT NOT NULL, PRIMARY KEY(obs_day'
                          + (', arm' if family == 'detlin' else '') + '))')
    # A NULL file is a missing identifier, distinct from a physical empty string.
    statements.append('CREATE UNIQUE INDEX qc_metric_identity ON qc_metrics ('
                      + ', '.join(map(quote, UNIQUE_COLUMNS[:-1]))
                      + ', (file IS NULL), COALESCE(file,\'\'))')
    statements.append('''CREATE TABLE qc_metric_sources (
        metric_id INTEGER NOT NULL REFERENCES qc_metrics(id) ON DELETE CASCADE,
        source_path TEXT NOT NULL, PRIMARY KEY(metric_id, source_path))''')
    return statements

# The module invocation must guard startup before loading application modules.
if __name__ == "__main__":
    import sys
    from qc_monitor.bootstrap import main as guarded_main
    sys.exit(guarded_main())

import qc_monitor
import logging
import argparse
import os
import sys
import sqlite3
from contextlib import closing, ExitStack
from pathlib import Path
import pandas as pd

from qc_monitor.acquisition import (
    find_session_databases,
    _load_qc_batch, _load_dsol_batch, _load_oloc_batch,
    find_observing_day_directories,
    load_qc_from_session_db,
    find_dispersion_solution_fits_files,
    parse_dispersion_solution_filename,
    load_dispersion_solution_tables,
    compute_dispersion_resolution_stats,
    find_order_location_fits_files,
    parse_order_location_filename,
    load_order_location_models,
    load_order_location_meta,
)
from qc_monitor.storage import SQLiteStore, ReadOnlyStorageError, validate_readonly_sqlite_path, _prepare_unit_frames
from qc_monitor.schema import TABLE_SCHEMA, SCHEMA_VERSION
from qc_monitor._outcomes import AcquisitionBatch, InputOutcome
from qc_monitor.run_result import RunResult, write_summary
from qc_monitor.plotting import generate_order_location_plots_from_config, generate_plots_from_config
from qc_monitor.generate_html import generate_html_report, _load_template
from qc_monitor.detector_linearity import (
    VIS_MODE_ORDER,
    _load_detector_linearity_batch,
    detector_linearity_enabled,
    load_detector_linearity_data,
)


from qc_monitor.config import (
    ConfigurationError, load_config, load_plot_includes, normalize_runtime_config, resolve_project_path,
)
from qc_monitor.locking import locked_coordinator, _archive_lease
from qc_monitor.coordination import leases, runtime_requests, project_requests, config_resources, configuration_requests, CoordinationBusyError
from qc_monitor.rebuild import acquisition_store
from qc_monitor.storage import qc_identity
from qc_monitor.storage import validate_schema, SchemaError
from qc_monitor._sqlite_retry import SQLITE_TIMEOUT_SECONDS, retry_sqlite, collect_sqlite_events


def _inspect_upstream_schema(database, table):
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True,
                                timeout=SQLITE_TIMEOUT_SECONDS)) as conn:
        table = table.replace('"', '""')
        return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _inspect_qc_schema(database, rebuild):
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True,
                                timeout=SQLITE_TIMEOUT_SECONDS)) as conn:
        if rebuild:
            if conn.execute('PRAGMA user_version').fetchone()[0] not in (0, SCHEMA_VERSION):
                raise SchemaError(f'{database}: unsupported schema for rebuild')
        else:
            validate_schema(conn)


def validate_path_collisions(cfg, config_path, databases, *, no_plots=False):
    """Protect selected input files while permitting QC below reduced_root."""
    protected = {Path(config_path).resolve(), *[Path(path).resolve() for path in databases]}
    protected.update(Path(path) for path in cfg.get('_origins', {}).get('includes', []))
    roots = [Path(cfg['paths']['reduced_root'])]
    roots.extend(Path(arm['root']) for arm in cfg['detector_linearity']['arms'].values())
    for root in roots:
        if root.is_dir():
            protected.update(path.resolve() for path in root.rglob('*.fits'))
    targets = [Path(cfg['paths']['qc_database']).resolve()]
    protected.update(Path(str(targets[0]) + suffix) for suffix in ('.lock', '-wal', '-shm', '-journal'))
    protected.update(targets[0].parent.glob(targets[0].name + '.backup-*.sqlite'))
    if not no_plots:
        output = Path(cfg['plots']['output_dir']).resolve()
        targets.append(Path(cfg['plots']['html_output']).resolve())
        for figure in cfg['plots']['figures']:
            target = (output / figure['filename']).resolve()
            if not target.is_relative_to(output):
                raise ConfigurationError(f"Figure filename escapes output directory: {target}")
            targets.append(target)
        if output in targets or output in protected:
            raise ConfigurationError(f'Output directory collides with a file: {output}')
    if len(targets) != len(set(targets)) or protected & set(targets):
        raise ConfigurationError('Output paths collide with each other or protected input/configuration files')


def parse_args():
    parser = argparse.ArgumentParser(
        description="SOXS QC monitoring pipeline"
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate configuration, paths, and scan policy, then exit",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect acquisition without changing databases or generating plots/report (WAL unsupported)",
    )

    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip plot generation",
    )

    parser.add_argument(
        "--rebuild-db",
        action="store_true",
        help="Build a verified replacement database, retaining historical coverage and a backup",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    parser.add_argument("--summary-json", type=Path, help="Save the run summary (ignored in dry-run/preflight)")

    args = parser.parse_args()
    if args.dry_run and args.rebuild_db:
        parser.error("--dry-run and --rebuild-db cannot be used together")
    return args


def default_config_path() -> Path:
    """
    Resolve the default config without using the installed package location.

    After pip installation, __file__ points inside site-packages. That path is
    intentionally never used as the project root.
    """
    env_root = os.environ.get("QC_MONITOR_ROOT")

    if env_root:
        config_path = Path(env_root).expanduser().resolve() / "configs" / "qc_monitor.yaml"
        if config_path.is_file():
            return config_path
        raise ConfigurationError(
            "QC_MONITOR_ROOT is set but configs/qc_monitor.yaml was not found: "
            f"{config_path}"
        )

    cwd = Path.cwd().resolve()

    for candidate_root in (cwd, *cwd.parents):
        config_path = candidate_root / "configs" / "qc_monitor.yaml"
        if (
            config_path.is_file()
            and (candidate_root / "pyproject.toml").is_file()
            and (candidate_root / "qc_monitor").is_dir()
        ):
            return config_path

    raise ConfigurationError(
        "No default configuration file could be resolved safely. "
        "Run qc-monitor from the cloned repository root, set QC_MONITOR_ROOT "
        "to the clone path, or pass --config /path/to/configs/qc_monitor.yaml. "
    )


def resolve_config_path(config_arg: Path | None) -> Path:
    if config_arg is not None:
        return config_arg.expanduser().resolve()

    return default_config_path()


def _nearest_existing_parent(path: Path) -> Path | None:
    for candidate in (Path(path), *Path(path).parents):
        if candidate.exists():
            return candidate

    return None


def _is_writable_path(path: Path) -> bool:
    existing = _nearest_existing_parent(path)
    return existing is not None and os.access(existing, os.W_OK)


def _path_contains_suspicious_token(path: Path, tokens: list[str]) -> str | None:
    lowered_parts = [part.lower() for part in path.parts]

    for token in tokens:
        token_l = str(token).lower()
        if any(token_l in part for part in lowered_parts):
            return token

    return None


def run_preflight(cfg: dict, project_root: Path, *, dry_run: bool = False, no_plots: bool = False,
                  inspection: bool = False, config_validated: bool = False, rebuild: bool = False) -> bool:
    log = logging.getLogger("qc-monitor")
    if not config_validated:
        try:
            cfg = normalize_runtime_config(cfg, project_root)
        except ConfigurationError as exc:
            log.error('Preflight failed: %s', exc)
            return False
    errors = []
    warnings = []

    paths_cfg = cfg.get("paths", {})
    acquisition_cfg = cfg.get("acquisition", {})
    plots_cfg = cfg.get("plots", {})

    upstream_root = Path(paths_cfg.get("upstream_root", "")).expanduser()
    reduced_root = Path(paths_cfg.get("reduced_root", "")).expanduser()
    qc_database_path = Path(paths_cfg.get("qc_database", "")).expanduser()
    output_dir = Path(plots_cfg.get("output_dir", "")).expanduser()
    html_output = Path(plots_cfg.get("html_output", "")).expanduser()
    template_path = plots_cfg.get("template")
    detlin_cfg = cfg.get("detector_linearity", {})

    upstream_database_name = acquisition_cfg.get("upstream_database_name", "soxspipe.db")
    upstream_search_mode = acquisition_cfg.get("upstream_database_search", "direct")
    reduced_search_mode = acquisition_cfg.get("reduced_products_search", "observing_day_dirs")
    allow_multiple_upstream = bool(acquisition_cfg.get("allow_multiple_upstream_databases", False))
    allow_suspicious_paths = bool(acquisition_cfg.get("allow_suspicious_paths", False))
    suspicious_tokens = acquisition_cfg.get(
        "suspicious_path_tokens",
        ["test", "tmp", "temporary", "sandbox"],
    )

    log.info("Preflight project root: %s", project_root)
    log.info("Preflight upstream root: %s", upstream_root)
    log.info("Preflight reduced root: %s", reduced_root)

    for label, path in (
        ("upstream_root", upstream_root),
        ("reduced_root", reduced_root),
    ):
        if not path.is_dir():
            errors.append(f"{label} is not an existing directory: {path}")
        elif not os.access(path, os.R_OK | os.X_OK):
            errors.append(f"{label} is not readable/searchable: {path}")

    for label, path in (
        ("qc_database", qc_database_path),
        ("plots.output_dir", output_dir),
        ("plots.html_output", html_output),
    ):
        if (dry_run or no_plots) and label != "qc_database":
            continue

        if label == "qc_database" and path.exists() and not path.is_file():
            errors.append(f"{label} exists but is not a file: {path}")
            continue

        if label == "plots.output_dir" and path.exists() and not path.is_dir():
            errors.append(f"{label} exists but is not a directory: {path}")
            continue

        if label == "plots.html_output" and path.exists() and path.is_dir():
            errors.append(f"{label} exists but is a directory: {path}")
            continue

        if dry_run:
            continue

        target = path if label == "plots.output_dir" else path.parent
        if not _is_writable_path(target):
            errors.append(f"{label} parent is not writable or cannot be reached: {path}")

    if template_path and not (dry_run or no_plots):
        template_path = Path(template_path).expanduser()
        if not template_path.is_file():
            errors.append(f"plots.template is not an existing file: {template_path}")
    if not (dry_run or no_plots) and plots_cfg.get('figures'):
        try:
            template = _load_template(Path(template_path) if template_path else None)
            if '{{ sections }}' not in template:
                errors.append('HTML template is missing {{ sections }}')
        except OSError as exc:
            errors.append(str(exc))

    if bool(detlin_cfg.get("enabled", False)):
        arms_cfg = detlin_cfg.get("arms", {})
        if not arms_cfg:
            errors.append("detector_linearity.enabled is true but no arms are configured")

        detlin_figures = [
            fig
            for fig in plots_cfg.get("figures", [])
            if fig.get("type") == "detector_linearity"
        ]
        if not detlin_figures and not (dry_run or no_plots):
            warnings.append(
                "detector_linearity enabled but no detector_linearity plots configured"
            )

        for arm, arm_cfg in arms_cfg.items():
            if not arm_cfg or not arm_cfg.get("root"):
                errors.append(f"detector_linearity.enabled is true but arms.{arm}.root is not configured")
                continue

            arm_root = Path(arm_cfg["root"]).expanduser()
            if not arm_root.is_dir():
                errors.append(f"detector_linearity.arms.{arm}.root is not an existing directory: {arm_root}")
            elif not os.access(arm_root, os.R_OK | os.X_OK):
                errors.append(f"detector_linearity.arms.{arm}.root is not readable/searchable: {arm_root}")

    if upstream_search_mode not in {"direct", "recursive"}:
        errors.append(
            "acquisition.upstream_database_search must be 'direct' or 'recursive'"
        )

    if reduced_search_mode not in {"observing_day_dirs", "recursive"}:
        errors.append(
            "acquisition.reduced_products_search must be 'observing_day_dirs' or 'recursive'"
        )

    if upstream_root.is_dir():
        databases = find_session_databases(upstream_root, upstream_database_name, upstream_search_mode)
        if not databases:
            errors.append(f'Upstream database not found: {upstream_root / upstream_database_name}')
        elif len(databases) > 1 and not allow_multiple_upstream:
            errors.append(f'Found {len(databases)} upstream databases; set allow_multiple_upstream_databases only if intentional')


    if dry_run or inspection:
        # Inspect every selected header before any acquisition opens SQLite.
        databases = find_session_databases(
            upstream_root, upstream_database_name, search_mode=upstream_search_mode
        ) if upstream_root.is_dir() and upstream_search_mode in {"direct", "recursive"} else []
        for database in [qc_database_path, *databases]:
            try:
                validate_readonly_sqlite_path(database)
            except ReadOnlyStorageError as exc:
                errors.append(str(exc))

    if not errors:
        databases = find_session_databases(upstream_root, upstream_database_name, upstream_search_mode)
        for database in databases:
            try:
                table = acquisition_cfg['upstream_table']
                columns = retry_sqlite(lambda: _inspect_upstream_schema(database, table),
                                       operation="preflight_upstream", source=database)
                missing = set(TABLE_SCHEMA) - columns
                if missing:
                    errors.append(f'{database}: upstream {table} missing required columns: {sorted(missing)}')
            except sqlite3.Error as exc:
                errors.append(f'{database}: cannot inspect upstream schema: {exc}')
    if not errors and qc_database_path.is_file() and not dry_run:
        retry_sqlite(lambda: _inspect_qc_schema(qc_database_path, rebuild),
                     operation="preflight_archive", source=qc_database_path)

    if reduced_root.is_dir():
        day_dirs = find_observing_day_directories(reduced_root)

        if reduced_search_mode == "observing_day_dirs" and not day_dirs:
            errors.append(
                f"No observing-day directories named YYYY-MM-DD found directly under {reduced_root}"
            )

        if not allow_suspicious_paths:
            token = _path_contains_suspicious_token(reduced_root, suspicious_tokens)
            if token is not None:
                errors.append(
                    f"reduced_root contains suspicious token '{token}': {reduced_root}"
                )

            for child in reduced_root.iterdir():
                token = _path_contains_suspicious_token(child, suspicious_tokens)
                if token is not None:
                    errors.append(
                        f"Suspicious directory/file under reduced_root contains "
                        f"'{token}': {child}"
                    )

    for warning in warnings:
        log.warning("Preflight warning: %s", warning)

    if errors:
        for error in errors:
            log.error("Preflight failed: %s", error)
        return False

    log.info("Preflight completed successfully")
    return True


def _consolidate_impl(
    upstream_db_path: Path,
    config_path: Path = Path("configs/qc_monitor.yaml"),
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Consolidate selected QC metrics into the independent historical database.
    With multiple sources enabled, acquire the whole configured source set.

    Can be called either from the main QC script or directly within the pipeline.

    Parameters
    ----------
    upstream_db_path : Path
        Path to an upstream SOXS pipeline SQLite database. With multiple
        sources enabled, it must belong to the configured discovery set.
    config_path : Path
        Path to the qc_monitor YAML configuration file.
    force : bool
        If True, ingest all observing days contained in the upstream DB,
        even if they were already marked as processed.
    dry_run : bool
        If True, load and filter data but do not write anything to the
        historical QC database.

    Returns
    -------
    int
        Number of valid QC datapoints selected, including rows of units
        that remain incomplete and are therefore not persisted.
    """
    log = logging.getLogger("qc-monitor")

    # Load configuration

    config_path = config_path.resolve()
    cfg = load_config(config_path)

    project_root = config_path.parent.parent
    cfg = normalize_runtime_config(cfg, project_root, validated=True)

    qc_database_path = resolve_project_path(
        cfg["paths"]["qc_database"],
        project_root,
    )

    paths = [upstream_db_path]
    if cfg.get("acquisition", {}).get("allow_multiple_upstream_databases", False):
        paths = find_session_databases(Path(cfg["paths"]["upstream_root"]),
                                       cfg["acquisition"]["upstream_database_name"],
                                       cfg["acquisition"].get("upstream_database_search", "direct"))
        if upstream_db_path.resolve() not in {path.resolve() for path in paths}:
            raise ConfigurationError(f"Upstream path is outside configured sources: {upstream_db_path}")
    if dry_run:
        for path in paths:
            validate_readonly_sqlite_path(path)
    validate_path_collisions(cfg, config_path, paths, no_plots=True)
    with acquisition_store(qc_database_path, dry_run=dry_run) as qc_database:
        return _consolidate_qc_sources(paths, cfg, qc_database, force, dry_run)


def consolidate(upstream_db_path: Path, config_path: Path = Path("configs/qc_monitor.yaml"),
                force: bool = False, dry_run: bool = False) -> int:
    if dry_run:
        return _consolidate_impl(upstream_db_path, config_path, force, dry_run)
    path = Path(config_path).expanduser().resolve()
    with leases(runtime_requests() + project_requests(path.parent.parent)):
        return _consolidate_impl(upstream_db_path, path, force, dry_run)


def _commit_batch(batch, family, qc_database, dry_run, already_closed, force, counts=None):
    log = logging.getLogger("qc-monitor")
    from qc_monitor.storage import _UNIT_TABLES
    frames = list(batch.frames.values())
    names = [table[0] for table in _UNIT_TABLES[family]]
    day_column = "night start date" if family == "qc" else "obs_day"
    units = set()
    for frame in frames:
        if not frame.empty:
            columns = [day_column, "eso seq arm"] if family == "detlin" else [day_column]
            units.update(tuple(str(value) for value in row) for row in frame[columns].itertuples(index=False, name=None))
    units.update(outcome.unit for outcome in batch.outcomes if outcome.unit is not None)
    report = counts if counts is not None else {}
    report.update(state="no_data", tables={name: {"selected": 0, "persisted": 0,
                  "discarded": batch.discarded_rows.get(key), "duplicates": 0,
                  "not_persisted_incomplete": 0, "preserved": 0}
                  for name, key in zip(names, batch.frames)},
                  completed_units=[], open_units=[], skipped_units=[], validated_units=[],
                  errors=[], input_states={}, latest_data_utc=None, selected=0, persisted=0,
                  sqlite_operations=batch.sqlite_operations)
    for outcome in batch.outcomes:
        report["input_states"][outcome.state] = report["input_states"].get(outcome.state, 0) + 1
        if outcome.state == "failed" and (force or outcome.unit is None or
                (outcome.unit if family == "detlin" else outcome.unit[0]) not in already_closed):
            report["errors"].append({"source": outcome.source, "unit": outcome.unit,
                                     "reason": outcome.reason, **outcome.details})
    selected, persisted = 0, 0
    writers = {"qc": qc_database.replace_qc_day, "dsol": qc_database.replace_dispersion_day,
               "oloc": qc_database.replace_order_location_day, "detlin": qc_database.replace_detector_linearity_day}
    for unit in sorted(units):
        closed_key = unit if family == "detlin" else unit[0]
        if not force and closed_key in already_closed:
            report["skipped_units"].append(unit)
            preserved = qc_database.unit_row_counts(family, unit)
            for name in names:
                previous = report["tables"][name]["preserved"]
                value = preserved[name]
                report["tables"][name]["preserved"] = None if previous is None or value is None else previous + value
            continue
        subset = []
        for name, frame in zip(names, frames):
            mask = frame[day_column].astype(str).eq(unit[0])
            if family == "detlin":
                mask &= frame["eso seq arm"].astype(str).eq(unit[1])
            subset.append(frame.loc[mask].copy())
            report["tables"][name]["selected"] += len(subset[-1])
        selected += sum(len(frame) for frame in subset)
        report["selected"] = selected
        failures = batch.failures(unit)
        reason = None
        if failures:
            reason = "; ".join(failure.reason for failure in failures)
        else:
            try:
                prepared = _prepare_unit_frames(family, subset)
                for name, before, after in zip(names, subset, prepared):
                    report["tables"][name]["duplicates"] += len(before) - len(after)
                subset = prepared
                if family == 'qc':
                    subset[0].attrs['provenance'] = frames[0].attrs.get('provenance', {})
            except ValueError as exc:
                reason = str(exc)
            if reason is None and not all(not frame.empty for frame in subset):
                reason = "Missing required data"
        if reason is not None:
            log.error("%s unit %s remains open: %s", family, unit, reason)
            report["open_units"].append(unit)
            if not failures:
                report["errors"].append({"source": family, "unit": unit, "reason": reason})
            for name, frame in zip(names, subset):
                report["tables"][name]["not_persisted_incomplete"] += len(frame)
            continue
        report["validated_units"].append(unit)
        if dry_run:
            for frame in subset:
                print(frame)
            log.info("Dry-run: %s unit %s is complete; no writes", family, unit)
        else:
            # Counters advance only after the whole transaction has committed.
            writers[family](*unit, *subset)
            report["completed_units"].append(unit)
            for name, frame in zip(names, subset):
                report["tables"][name]["persisted"] += len(frame)
            persisted += sum(len(frame) for frame in subset)
            report["persisted"] = persisted
    report.update(selected=selected, persisted=persisted)
    report["state"] = "partial" if report["errors"] or report["open_units"] else (
        "completed" if units else "no_data")
    if family == 'detlin':
        metadata = frames[0][['sequence_id', 'tpl_start', 'tpl_id', 'obs_day', 'eso seq arm']].drop_duplicates()
        report['sequences'] = metadata.to_dict(orient='records')
    for error in report["errors"]:
        log.error("%s acquisition: %s: %s", family, error["source"], error["reason"])
    log.info("%s selected %d rows; persisted %d rows", family, selected, persisted)
    return selected


def _consolidate_qc_sources(paths, cfg, qc_database, force=False, dry_run=False, counts=None):
    if dry_run:
        for path in paths:
            validate_readonly_sqlite_path(path)
    batches = [_load_qc_batch(path, cfg) for path in paths]
    frames = [batch.frames["metrics"] for batch in batches if not batch.frames["metrics"].empty]
    metrics = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(TABLE_SCHEMA))
    batch = AcquisitionBatch({"metrics": metrics}, [outcome for item in batches for outcome in item.outcomes],
                             {"metrics": sum(item.discarded_rows["metrics"] for item in batches)}
                             if all("metrics" in item.discarded_rows for item in batches) else {},
                             [event for item in batches for event in item.sqlite_operations])
    provenance = {}
    for path, item in zip(paths, batches):
        for _, row in item.frames['metrics'].iterrows():
            provenance.setdefault(qc_identity(row), set()).add(str(Path(path).resolve()))
    metrics.attrs['provenance'] = provenance
    has_units = not metrics.empty or any(outcome.unit is not None for outcome in batch.outcomes)
    closed = qc_database.get_processed_obs_days() if has_units else set()
    return _commit_batch(batch, "qc", qc_database, dry_run, closed, force, counts)


def _selected_product_files(paths, parser, closed, force, skipped=None):
    # Malformed selected filenames must become failures, not abort discovery.
    selected = []
    for path in paths:
        try:
            day = parser(path)
        except (ValueError, KeyError):
            selected.append(path)
            continue
        if force or day not in closed:
            selected.append(path)
        elif skipped is not None:
            skipped.append(InputOutcome(str(path), "skipped", (str(day),)))
    return selected


@locked_coordinator
def consolidate_dispersion_solution(reduced_root: Path, qc_database: SQLiteStore,
                                    dry_run: bool = False, force: bool = False,
                                    search_mode: str = "observing_day_dirs", *, _result=None) -> int:
    discovered = find_dispersion_solution_fits_files(reduced_root, search_mode)
    closed = qc_database.get_processed_dispersion_obs_days() if discovered else set()
    skipped = []
    paths = _selected_product_files(discovered,
                                    lambda path: parse_dispersion_solution_filename(path)[0], closed, force, skipped)
    batch = _load_dsol_batch(paths)
    batch.outcomes.extend(skipped)
    return _commit_batch(batch, "dsol", qc_database, dry_run, closed, force, _result)


@locked_coordinator
def consolidate_order_location_models(reduced_root: Path, qc_database: SQLiteStore,
                                      dry_run: bool = False, force: bool = False,
                                      search_mode: str = "observing_day_dirs", *, _result=None) -> int:
    discovered = find_order_location_fits_files(reduced_root, search_mode)
    closed = qc_database.get_processed_order_location_obs_days() if discovered else set()
    skipped = []
    paths = _selected_product_files(discovered,
                                    lambda path: parse_order_location_filename(path)["obs_day"], closed, force, skipped)
    batch = _load_oloc_batch(paths)
    batch.outcomes.extend(skipped)
    return _commit_batch(batch, "oloc", qc_database, dry_run, closed, force, _result)


@locked_coordinator
def consolidate_detector_linearity(cfg: dict, qc_database: SQLiteStore,
                                   dry_run: bool = False, force: bool = False, *, _result=None) -> int:
    if not detector_linearity_enabled(cfg):
        if _result is not None:
            _result.update(state="disabled", tables={}, latest_data_utc=None)
        return 0
    closed = qc_database.get_processed_detector_linearity_obs_days()
    batch = _load_detector_linearity_batch(cfg, closed, force)
    return _commit_batch(batch, "detlin", qc_database, dry_run, closed, force, _result)


def _run_main(args, run):

    ####################################################
    ############ Load configuration ####################
    ####################################################

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    if args.verbose:
        logging.getLogger("qc-monitor").setLevel(logging.DEBUG)
        logging.getLogger("qc_monitor").setLevel(logging.DEBUG)
        logging.getLogger("matplotlib").setLevel(logging.WARNING)
    log = logging.getLogger("qc-monitor")
    log.info("qc-monitor version %s", qc_monitor.__version__)

    try:
        config_path = resolve_config_path(args.config)
        if args.summary_json and not (args.dry_run or args.preflight):
            target = args.summary_json.expanduser().resolve()
            if target.is_relative_to(config_path.parent):
                args.summary_json = None
                raise ConfigurationError(f"Summary destination overlaps protected configuration: {target}")
        cfg = load_config(config_path)
    except Exception as exc:
        raise ConfigurationError(str(exc)) from exc

    config_dir = config_path.parent
    project_root = config_dir.parent

    cfg = normalize_runtime_config(cfg, project_root, validated=True)

    if args.summary_json and not (args.dry_run or args.preflight):
        target = args.summary_json.expanduser().resolve()
        input_roots = [Path(cfg["paths"][key]).resolve() for key in ("upstream_root", "reduced_root")]
        input_roots.append(config_dir.resolve())
        input_roots.extend(Path(arm["root"]).resolve() for arm in cfg.get("detector_linearity", {}).get("arms", {}).values() if arm.get("root"))
        protected = {Path(cfg["paths"]["qc_database"]).resolve(),
                     Path(cfg["plots"]["html_output"]).resolve()}
        database = Path(cfg['paths']['qc_database']).resolve()
        protected.update(Path(str(database) + suffix) for suffix in ('.lock', '-wal', '-shm', '-journal'))
        protected.update(database.parent.glob(database.name + '.backup-*.sqlite'))
        protected.update((Path(cfg["plots"]["output_dir"]) / figure["filename"]).resolve()
                         for figure in cfg["plots"].get("figures", []) if figure.get("filename"))
        if target in protected or any(target.is_relative_to(root) for root in input_roots):
            # Do not attempt this destination even while reporting the failure.
            args.summary_json = None
            raise ConfigurationError(f"Summary destination overlaps protected data/config/artifacts: {target}")

    if not (args.dry_run or args.preflight):
        args._operation_stack.enter_context(leases(config_resources(
            cfg, no_plots=args.no_plots, summary=args.summary_json) + configuration_requests(config_path, cfg), run.coordination))
        checked = normalize_runtime_config(load_config(config_path), project_root, validated=True)
        if checked != cfg:
            raise ConfigurationError("Configuration changed during operational coordination")

    upstream_root = Path(cfg["paths"]["upstream_root"])
    reduced_root = Path(cfg["paths"]["reduced_root"])
    qc_database_path = Path(cfg["paths"]["qc_database"])
    acquisition_cfg = cfg.get("acquisition", {})
    upstream_database_name = acquisition_cfg["upstream_database_name"]
    upstream_search_mode = acquisition_cfg.get("upstream_database_search", "direct")
    reduced_search_mode = acquisition_cfg.get("reduced_products_search", "observing_day_dirs")

    with run.phase("preflight"):
        if not run_preflight(cfg, project_root, dry_run=args.dry_run, no_plots=args.no_plots,
                             inspection=args.preflight, config_validated=True, rebuild=args.rebuild_db):
            raise ConfigurationError("Preflight failed; see preceding diagnostics")

    sources = find_session_databases(upstream_root, upstream_database_name, upstream_search_mode)
    validate_path_collisions(cfg, config_path, sources, no_plots=args.dry_run or args.no_plots)
    if args.preflight:
        return
    if not args.dry_run:
        args._operation_stack.enter_context(_archive_lease(qc_database_path))
    if args.summary_json and not args.dry_run:
        args._summary_allowed = True
    with acquisition_store(qc_database_path, dry_run=args.dry_run, rebuild=args.rebuild_db, run=run) as qc_database:

        plots_cfg = cfg.get("plots", {})

        ####################################################
        ############### Scanning step ######################
        ####################################################

        # assumes more than one pipeline database can be present in the path
        session_databases = find_session_databases(
            upstream_root=upstream_root,
            database_name=upstream_database_name,
            search_mode=upstream_search_mode,
        )

        log.info("Found %d upstream session databases", len(session_databases))

        qc_counts = run.families.setdefault("qc", {})
        with run.phase("qc"):
            total_points = _consolidate_qc_sources(session_databases, cfg, qc_database,
                                                  force=args.rebuild_db, dry_run=args.dry_run, counts=qc_counts)

        log.info("Total consolidated QC datapoints: %d%s",
                 total_points if args.dry_run else qc_counts["persisted"],
                 " (dry-run selection; no writes)" if args.dry_run else "")

        with run.phase("dsol"):
            dsol_points = consolidate_dispersion_solution(
                reduced_root=reduced_root,
                qc_database=qc_database,
                dry_run=args.dry_run,
                force=args.rebuild_db,
                search_mode=reduced_search_mode,
                _result=run.families.setdefault("dsol", {}),
            )


        log.info("Total selected dispersion-solution rows: %d", dsol_points)

        with run.phase("oloc"):
            oloc_points = consolidate_order_location_models(
                reduced_root=reduced_root,
                qc_database=qc_database,
                dry_run=args.dry_run,
                force=args.rebuild_db,
                search_mode=reduced_search_mode,
                _result=run.families.setdefault("oloc", {}),
            )


        log.info("Total selected order-location model rows: %d", oloc_points)

        with run.phase("detlin"):
            detlin_points = consolidate_detector_linearity(
                cfg=cfg,
                qc_database=qc_database,
                dry_run=args.dry_run,
                force=args.rebuild_db,
                _result=run.families.setdefault("detlin", {}),
            )


        log.info("Total selected detector-linearity rows: %d", detlin_points)

        for family, result in run.families.items():
            if result["state"] != "disabled":
                result["latest_data_utc"] = qc_database.latest_data_utc(family)

    if args.dry_run:
        log.info("Dry-run enabled, skipping plot generation")
        return

    ####################################################
    ############### Plotting step ######################
    ####################################################

    if args.no_plots:
        log.info("Skipping plot generation (--no-plots)")
        return

    with run.phase("plots"):
        # Plots are defined in configuration
        plots_cfg = cfg.get("plots", {})

        # Load the newly consolidated QC metrics for plotting
        df_plot = qc_database.load_all_metrics()

        if df_plot.empty:
            log.info("No historical QC metrics available for plotting")
        else:
            generate_plots_from_config(
                df=df_plot,
                plots_cfg=plots_cfg,
                plot_types={"time_series", "xy_scatter", "histogram", "latest_by_order_bar"}
            )

        # Load dispersion solution lines for plotting
        df_dsol = qc_database.load_dispersion_solution_lines()

        if df_dsol.empty:
            log.info("No historical dispersion-solution data available for plotting")
        else:
            generate_plots_from_config(
                df=df_dsol,
                plots_cfg=plots_cfg,
                plot_types={"dispersion_resolution", "dispersion_residual_xy", "dispersion_residual_histogram"},
            )

        # Load dispersion resolution stats for plotting
        df_resolution_stats = qc_database.load_dispersion_resolution_stats()

        generate_plots_from_config(
            df=df_resolution_stats,
            plots_cfg=plots_cfg,
            plot_types={"dispersion_resolution_timeseries"},
        )

        # Load order location models for plotting
        df_oloc_models = qc_database.load_order_location_models()
        df_oloc_meta = qc_database.load_order_location_meta()

        generate_order_location_plots_from_config(
            df_models=df_oloc_models,
            df_meta=df_oloc_meta,
            plots_cfg=plots_cfg,
        )

        # Load detector linearity results for plotting
        df_detlin = qc_database.load_detector_linearity_results()

        generate_plots_from_config(
            df=df_detlin,
            plots_cfg=plots_cfg,
            plot_types={"detector_linearity"},
        )

        ####################################################
        ############### HTML Report Generation #############
        ####################################################

        html_output = resolve_project_path(
            plots_cfg.get("html_output", "index.html"),
            project_root,
        )

    with run.phase("html"):
        generate_html_report(
            plots_cfg=plots_cfg,
            output_html=html_output,
            template_path=(
                Path(plots_cfg["template"])
                if plots_cfg.get("template")
                else None
            ),
        )



def main():
    with ExitStack() as operation:
        return _main(operation)


def _main(operation):
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    log = logging.getLogger("qc-monitor")
    mode = "preflight" if args.preflight else "dry-run" if args.dry_run else "run"
    run = RunResult(mode)
    args._summary_allowed = False
    args._operation_stack = operation
    run.coordination = {"operation": "rebuild" if args.rebuild_db else mode, "resources": [], "conflict_resource": None}
    if args.summary_json and (args.dry_run or args.preflight):
        log.warning("--summary-json ignored in dry-run/preflight; summary is log-only")
    try:
        if not (args.dry_run or args.preflight):
            config_path = resolve_config_path(args.config)
            args._operation_stack.enter_context(leases(runtime_requests() + project_requests(config_path.parent.parent), run.coordination))
        with collect_sqlite_events(run.sqlite_operations), run.phase("execution"):
            _run_main(args, run)
    except Exception as exc:
        log.exception("Dry-run storage error: %s" if isinstance(exc, ReadOnlyStorageError) else "Run failed: %s", exc)
        if isinstance(exc, CoordinationBusyError):
            args._summary_allowed = False
            run.coordination['conflict_resource'] = exc.resource
        failed = [phase["name"] for phase in run.phases if phase["state"] == "failed"]
        error = {"type": type(exc).__name__, "reason": str(exc), "phase": failed[-1] if failed else "execution"}
        run.errors.append(error)
        for name in failed:
            if name in run.families:
                run.families[name]["state"] = "failed"
    run.finish()
    if args.summary_json and args._summary_allowed:
        try:
            write_summary(args.summary_json, run)
        except Exception as exc:
            log.exception("Summary save failed")
            run.errors.append({"type": type(exc).__name__, "reason": str(exc), "source": str(args.summary_json)})
            run.finish()
    log.info("RUN_SUMMARY %s", run.to_json())
    return run.exit_code


if __name__ == "__main__":
    sys.exit(main())

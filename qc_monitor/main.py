# The module invocation must guard startup before loading application modules.
if __name__ == "__main__":
    import sys
    from qc_monitor.bootstrap import main as guarded_main
    sys.exit(guarded_main())

import qc_monitor
import logging
import argparse
import sys
from contextlib import ExitStack
from pathlib import Path

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
from qc_monitor.figure_result import FigureResult, summarize_figures, validate_figure_results

from qc_monitor.generate_html import _load_template
from qc_monitor.publication import publish_report, PublicationError, validate_publication
from qc_monitor.detector_linearity import (
    VIS_MODE_ORDER,
    _load_detector_linearity_batch,
    detector_linearity_enabled,
    load_detector_linearity_data,
)


from qc_monitor.config import (
    ConfigurationError,
    load_config,
    load_plot_includes,
    normalize_runtime_config,
    resolve_project_path,
)
from qc_monitor.locking import locked_coordinator, _archive_lease
from qc_monitor.coordination import leases, runtime_requests, project_requests, config_resources, configuration_requests, CoordinationBusyError
from qc_monitor.rebuild import acquisition_store
from qc_monitor.storage import qc_identity
from qc_monitor.storage import validate_schema, SchemaError
from qc_monitor._sqlite_retry import SQLITE_TIMEOUT_SECONDS, retry_sqlite, collect_sqlite_events


# Compatibility exports: existing pipeline and inspection imports remain valid.
from ._preflight import (
    _inspect_qc_schema,
    _inspect_upstream_schema,
    _is_writable_path,
    _nearest_existing_parent,
    _path_contains_suspicious_token,
    run_preflight,
    validate_path_collisions,
)
from ._consolidation import (
    _commit_batch,
    _consolidate_impl,
    _consolidate_qc_sources,
    _selected_product_files,
    consolidate,
    consolidate_detector_linearity,
    consolidate_dispersion_solution,
    consolidate_order_location_models,
)
from ._runtime import (
    default_config_path,
    prepare_runtime,
    resolve_config_path,
)
from ._renderers import types_for_dataset


def generate_plots_from_config(*args, **kwargs):
    # Lazy import preserves both interactive APIs and the CLI startup guards.
    from qc_monitor.plotting import generate_plots_from_config as generate
    return generate(*args, **kwargs)


def generate_order_location_plots_from_config(*args, **kwargs):
    from qc_monitor.plotting import generate_order_location_plots_from_config as generate
    return generate(*args, **kwargs)


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

    cfg, config_path, project_root = prepare_runtime(args, run)

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
    if not (args.dry_run or args.no_plots) and cfg['plots']['figures']:
        validate_publication(cfg, config_path=config_path, summary_path=args.summary_json)
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

    plots_cfg = cfg.get('plots', {})
    if not plots_cfg.get('figures'):
        return
    # Batch selection must happen before pyplot is imported. Direct APIs retain
    # the caller's backend, and explicit interactive requests are respected.
    if not plots_cfg.get('show', False):
        import matplotlib
        matplotlib.use('Agg')

    def render(staging_plots_cfg):
        plots_cfg = staging_plots_cfg
        figure_results = []
        groups = [
            ('qc', types_for_dataset('qc'),
             lambda: (qc_database.load_all_metrics(),)),
            ('dsol_lines', types_for_dataset('dsol_lines'),
             lambda: (qc_database.load_dispersion_solution_lines(),)),
            ('dsol_stats', types_for_dataset('dsol_stats'),
             lambda: (qc_database.load_dispersion_resolution_stats(),)),
            ('oloc', types_for_dataset('oloc'),
             lambda: (qc_database.load_order_location_models(), qc_database.load_order_location_meta())),
            ('detlin', types_for_dataset('detlin'),
             lambda: (qc_database.load_detector_linearity_results(),)),
        ]
        for dataset, types, load in groups:
            figures = [fig for fig in plots_cfg['figures'] if fig['type'] in types]
            if not figures:
                continue
            try:
                frames = load()
            except Exception as exc:
                log.exception('Plot dataset %s could not be loaded', dataset)
                results = [FigureResult.failed(fig, exc, 'history_read_error') for fig in figures]
            else:
                if dataset == 'oloc':
                    results = generate_order_location_plots_from_config(
                        *frames, plots_cfg, continue_on_error=True)
                else:
                    results = generate_plots_from_config(
                        frames[0], plots_cfg, types, continue_on_error=True)
            figure_results.extend(results)
            # Retain already completed work if a later global failure occurs.
            run.plots = summarize_figures(figure_results)
        by_name = validate_figure_results(plots_cfg['figures'], figure_results)
        figure_results = [by_name[fig['name']] for fig in plots_cfg['figures']]
        run.plots = summarize_figures(figure_results)

        return figure_results

    with run.phase('publication'):
        try:
            result = publish_report(cfg, project_root=project_root, config_path=config_path,
                                    run_id=run.run_id, render=render, summary_path=args.summary_json)
        except PublicationError as exc:
            exc.result.apply_to(run)
            raise
        else:
            result.apply_to(run)


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
        if not isinstance(exc, PublicationError):
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

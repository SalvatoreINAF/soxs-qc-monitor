import qc_monitor
import logging
import yaml
import argparse
from pathlib import Path
import pandas as pd

from qc_monitor.acquisition import (
    find_session_databases,
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
from qc_monitor.storage import SQLiteStore
from qc_monitor.plotting import generate_order_location_plots_from_config, generate_plots_from_config
from qc_monitor.generate_html import generate_html_report


def parse_args():
    parser = argparse.ArgumentParser(
        description="SOXS QC monitoring pipeline"
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run acquisition but do not write anything to the database",
    )

    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip plot generation",
    )

    parser.add_argument(
        "--rebuild-db",
        action="store_true",
        help="Rebuild the QC database from scratch",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    return parser.parse_args()

def default_config_path() -> Path:
    package_dir = Path(__file__).resolve().parent
    project_root = package_dir.parent
    return project_root / "configs" / "qc_monitor.yaml"


def resolve_project_path(path: str | Path, project_root: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return project_root / path


def load_plot_includes(cfg: dict, config_dir: Path) -> dict:
    plots_cfg = cfg.get("plots", {})
    include_files = plots_cfg.get("include", [])

    figures = list(plots_cfg.get("figures", []))
    datapoint_queries = dict(plots_cfg.get("datapoint_queries", {}))

    for include_file in include_files:
        include_path = config_dir / include_file

        with open(include_path) as f:
            included_cfg = yaml.safe_load(f) or {}

        figures.extend(included_cfg.get("figures", []))

        included_queries = included_cfg.get("datapoint_queries", {})
        duplicate_queries = set(datapoint_queries) & set(included_queries)

        if duplicate_queries:
            raise ValueError(
                f"Duplicate datapoint query names in {include_path}: "
                f"{sorted(duplicate_queries)}"
            )

        datapoint_queries.update(included_queries)

    plots_cfg["figures"] = figures
    plots_cfg["datapoint_queries"] = datapoint_queries
    cfg["plots"] = plots_cfg

    return cfg


def load_config(config_path: Path = Path("configs/qc_monitor.yaml")):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    return load_plot_includes(cfg, config_path.parent)


def consolidate(
    upstream_db_path: Path,
    config_path: Path = Path("configs/qc_monitor.yaml"),
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Consolidate new QC metrics from one upstream SOXS pipeline database
    into the independent historical QC database.

    Can be called either from the main QC script or directly within the pipeline.

    Parameters
    ----------
    upstream_db_path : Path
        Path to the upstream SOXS pipeline SQLite database.
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
        Number of QC datapoints selected for consolidation.
    """
    log = logging.getLogger("qc-monitor")

    # Load configuration

    config_path = config_path.resolve()
    cfg = load_config(config_path)

    project_root = config_path.parent.parent

    qc_database_path = resolve_project_path(
        cfg["paths"]["qc_database"],
        project_root,
    )

    qc_database = SQLiteStore(qc_database_path)

    # Load QC datapoints from the upstream database

    df = load_qc_from_session_db(
        session_db_path=upstream_db_path,
        cfg=cfg,
    )

    if df.empty:
        log.info("No QC datapoints found in upstream database: %s", upstream_db_path)
        return 0
    
    # Filter out already processed observing days, unless --force is used

    processed_obs_days = qc_database.get_processed_obs_days()

    if not force:
        df = df[~df["night start date"].isin(processed_obs_days)].copy()

    if df.empty:
        log.info(
            "No new QC datapoints to consolidate from upstream database: %s",
            upstream_db_path,
        )
        return 0

    log.info(
        "Selected %d QC datapoints from %s",
        len(df),
        upstream_db_path,
    )

    # Write new QC datapoints to the historical QC database and mark observing days as processed

    if dry_run:
        log.info("Dry-run enabled, not writing to historical QC database")
        print(df)
        return len(df)

    qc_database.write_metrics(df)

    for obs_day in sorted(df["night start date"].unique()):
        qc_database.register_processed_obs_day(str(obs_day))

    log.info(
        "Consolidated %d QC datapoints from %s",
        len(df),
        upstream_db_path,
    )

    return len(df)


def consolidate_dispersion_solution(
    reduced_root: Path,
    qc_database: SQLiteStore,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    log = logging.getLogger("qc-monitor")

    fits_files = find_dispersion_solution_fits_files(reduced_root)

    if not fits_files:
        log.info("No dispersion-solution FITS files found")
        return 0

    processed_days = qc_database.get_processed_dispersion_obs_days()

    new_files = []

    for fits_file in fits_files:
        obs_day, _, _ = parse_dispersion_solution_filename(fits_file)

        if force or obs_day not in processed_days:
            new_files.append(fits_file)

    if not new_files:
        log.info("No new dispersion-solution FITS files to consolidate")
        return 0

    log.info(
        "Found %d new dispersion-solution FITS files",
        len(new_files),
    )

    df = load_dispersion_solution_tables(new_files)

    df_stats = compute_dispersion_resolution_stats(df)

    if df.empty and df_stats.empty:
        log.info("No dispersion-solution rows loaded")
        return 0

    if dry_run:
        log.info("Dry-run enabled, not writing dispersion-solution data")

        if not df.empty:
            print("DISPERSION SOLUTION LINES")
            print(df)

        if not df_stats.empty:
            print("DISPERSION RESOLUTION STATS")
            print(df_stats)

        return len(df) + len(df_stats)

    if not df.empty:
        qc_database.write_dispersion_solution_lines(df)

    if not df_stats.empty:
        qc_database.write_dispersion_resolution_stats(df_stats)

    obs_days = set()

    if not df.empty:
        obs_days.update(str(v) for v in df["obs_day"].unique())

    if not df_stats.empty:
        obs_days.update(str(v) for v in df_stats["obs_day"].unique())

    for obs_day in sorted(obs_days):
        qc_database.register_processed_dispersion_obs_day(obs_day)

    log.info(
        "Consolidated %d dispersion-solution rows and %d resolution-stat rows",
        len(df),
        len(df_stats),
    )

    return len(df) + len(df_stats)


def consolidate_order_location_models(
    reduced_root: Path,
    qc_database: SQLiteStore,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    log = logging.getLogger("qc-monitor")

    fits_files = find_order_location_fits_files(reduced_root)

    if not fits_files:
        log.info("No order-location FITS files found")
        return 0

    processed_days = qc_database.get_processed_order_location_obs_days()

    new_files = []

    for fits_file in fits_files:
        obs_day = parse_order_location_filename(fits_file)["obs_day"]

        if force or obs_day not in processed_days:
            new_files.append(fits_file)

    if not new_files:
        log.info("No new order-location FITS files to consolidate")
        return 0

    log.info(
        "Found %d new order-location FITS files",
        len(new_files),
    )

    df_models = load_order_location_models(new_files)
    df_meta = load_order_location_meta(new_files)

    if df_models.empty and df_meta.empty:
        log.info("No order-location rows loaded")
        return 0

    if dry_run:
        log.info("Dry-run enabled, not writing order-location data")
        if not df_models.empty:
            print("ORDER LOCATION MODELS")
            print(df_models)
        if not df_meta.empty:
            print("ORDER LOCATION META")
            print(df_meta)
        return len(df_models) + len(df_meta)

    if not df_models.empty:
        qc_database.write_order_location_models(df_models)

    if not df_meta.empty:
        qc_database.write_order_location_meta(df_meta)

    obs_days = set()

    if not df_models.empty:
        obs_days.update(str(v) for v in df_models["obs_day"].unique())

    if not df_meta.empty:
        obs_days.update(str(v) for v in df_meta["obs_day"].unique())

    for obs_day in sorted(obs_days):
        qc_database.register_processed_order_location_obs_day(obs_day)

    log.info(
        "Consolidated %d order-location model rows and %d order-location meta rows",
        len(df_models),
        len(df_meta),
    )

    return len(df_models) + len(df_meta)


def main():

    ####################################################
    ############ Load configuration ####################
    ####################################################

    args = parse_args()

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

    config_path = args.config.resolve()
    cfg = load_config(config_path)

    config_dir = config_path.parent
    project_root = config_dir.parent

    upstream_root = resolve_project_path(cfg["paths"]["upstream_root"], project_root)
    reduced_root = resolve_project_path(cfg["paths"]["reduced_root"], project_root)
    qc_database_path = resolve_project_path(cfg["paths"]["qc_database"], project_root)

    qc_database = SQLiteStore(qc_database_path)
    upstream_database_name = cfg["acquisition"]["upstream_database_name"]

    if args.rebuild_db:
        log.warning("Rebuilding QC database from scratch")
        qc_database.drop_all()

    # Normalize and resolve all paths in the "plots" section of the configuration
    plots_cfg = cfg.get("plots", {})

    plots_cfg["output_dir"] = str(
        resolve_project_path(
            plots_cfg.get("output_dir", "plots"),
            project_root,
        )
    )

    plots_cfg["html_output"] = str(
        resolve_project_path(
            plots_cfg.get("html_output", "index.html"),
            project_root,
        )
    )

    plots_cfg["template"] = str(
        resolve_project_path(
            plots_cfg.get("template", "qc_monitor/template.html"),
            project_root,
        )
    )

    cfg["plots"] = plots_cfg

    ####################################################
    ############### Scanning step ######################
    ####################################################

    # assumes more than one pipeline database can be present in the path
    session_databases = find_session_databases(
        upstream_root=upstream_root,
        database_name=upstream_database_name,
    )

    log.info("Found %d upstream session databases", len(session_databases))

    total_points = 0

    # consolidate new QC datapoints into the historical QC database
    for upstream_db_path in session_databases:
        total_points += consolidate(
            upstream_db_path=upstream_db_path,
            config_path=config_path,
            force=args.rebuild_db,
            dry_run=args.dry_run,
        )

    log.info("Total consolidated QC datapoints: %d", total_points)

    dsol_points = consolidate_dispersion_solution(
        reduced_root=reduced_root,
        qc_database=qc_database,
        dry_run=args.dry_run,
        force=args.rebuild_db,
    )

    log.info("Total consolidated dispersion-solution rows: %d", dsol_points)

    oloc_points = consolidate_order_location_models(
        reduced_root=reduced_root,
        qc_database=qc_database,
        dry_run=args.dry_run,
        force=args.rebuild_db,
    )

    log.info("Total consolidated order-location model rows: %d", oloc_points)

    if args.dry_run:
        log.info("Dry-run enabled, skipping plot generation")
        return

    ####################################################
    ############### Plotting step ######################
    ####################################################

    if args.no_plots:
        log.info("Skipping plot generation (--no-plots)")
        return

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

    ####################################################
    ############### HTML Report Generation #############
    ####################################################

    html_output = resolve_project_path(
        plots_cfg.get("html_output", "index.html"),
        project_root,
    )

    generate_html_report(
        plots_cfg=plots_cfg,
        output_html=html_output,
    )


if __name__ == "__main__":
    main()
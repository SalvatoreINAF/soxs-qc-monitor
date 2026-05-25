import qc_monitor
import logging
import yaml
import argparse
from pathlib import Path
import pandas as pd

from qc_monitor.acquisition import find_session_databases
from qc_monitor.acquisition import load_qc_from_session_db
from qc_monitor.storage import SQLiteStore
from qc_monitor.plotting import generate_plots_from_config
from qc_monitor.generate_html import generate_html_report


def parse_args():
    parser = argparse.ArgumentParser(
        description="SOXS QC monitoring pipeline"
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

    cfg = load_config(config_path)

    qc_database = SQLiteStore(Path(cfg["paths"]["qc_database"]))

    df = load_qc_from_session_db(
        session_db_path=upstream_db_path,
        cfg=cfg,
    )

    if df.empty:
        log.info("No QC datapoints found in upstream database: %s", upstream_db_path)
        return 0

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

    config_path = Path("configs/qc_monitor.yaml")
    cfg = load_config(config_path)

    qc_root = Path(cfg["paths"]["qc_root"])
    qc_database = SQLiteStore(Path(cfg["paths"]["qc_database"]))
    upstream_database_name = cfg["acquisition"]["upstream_database_name"]

    if args.rebuild_db:
        log.warning("Rebuilding QC database from scratch")
        qc_database.drop_all()

    ####################################################
    ############### Scanning step ######################
    ####################################################

    # assumes more than one pipeline database can be present in the path
    session_databases = find_session_databases(
        qc_root=qc_root,
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
        return

    generate_plots_from_config(
        df=df_plot,
        plots_cfg=plots_cfg,
    )

    ####################################################
    ############### HTML Report Generation #############
    ####################################################

    html_output = Path(plots_cfg.get("html_output", "index.html"))

    generate_html_report(
        plots_cfg=plots_cfg,
        output_html=html_output,
    )


if __name__ == "__main__":
    main()
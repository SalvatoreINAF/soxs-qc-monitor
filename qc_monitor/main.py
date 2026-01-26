import qc_monitor
import logging
import yaml
import argparse
from pathlib import Path
import pandas as pd

from qc_monitor.acquisition import (
    find_disp_solution_fits_files,
    list_observing_dates,
    find_qc_csv_files,
    extract_qc_metrics,
    extract_disp_solution_metrics_df,
)
from qc_monitor.storage import SQLiteStore
from qc_monitor.processing import filter_complete_recipes_by_arm
from qc_monitor.plotting import plot_time_series

def parse_args():
    parser = argparse.ArgumentParser(
        description="SOXS QC monitoring pipeline"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run acquisition and processing but do not write anything to the database",
    )

    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip plot generation (if enabled)",
    )

    parser.add_argument(
        "--force-date",
        type=str,
        metavar="YYYY-MM-DD",
        help="Force processing of a specific observing date",
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

def load_config():
    cfg_path = Path("configs/qc_monitor.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)

def main():

    # Parse arguments, setup logging and load config

    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)
    log = logging.getLogger("qc-monitor")
    log.info("qc-monitor version %s", qc_monitor.__version__)

    cfg = load_config()

    qc_root = Path(cfg["paths"]["qc_root"])
    store = SQLiteStore(Path(cfg["paths"]["database"]))

    if args.rebuild_db:
        log.warning("Rebuilding QC database from scratch")
        store.drop_all()

    ####################################################
    ############### Acquisition step ###################
    ####################################################

    # First, load all dates based on qc_root subdirectories names
    all_dates = list_observing_dates(qc_root)

    # Get already processed dates from the registry
    processed_dates = store.get_processed_dates()

    # Unless forced, process only new dates
    if args.force_date:
        dates_to_scan = [
            d for d in all_dates if d.name == args.force_date
        ]
        if not dates_to_scan:
            log.error("Forced date %s not found in qc_root", args.force_date)
            return
        log.info("Forcing processing of date %s", args.force_date)
    else:
        dates_to_scan = [
            d for d in all_dates if d.name not in processed_dates
        ]

    log.info(
        "Found %d observing dates, %d already processed, %d to scan",
        len(all_dates),
        len(processed_dates),
        len(dates_to_scan),
    )

    collected = []

    # Scan valid (new) dates for QC metrics in CSV files
    for date_dir in dates_to_scan:
        csv_files = find_qc_csv_files(
            date_dir,
            cfg["acquisition"]["file_pattern_csv"],
        )

        log.info(
            "Scanning %s (%d QC files)",
            date_dir.name,
            len(csv_files),
        )

        for csv_file in csv_files:
            df = extract_qc_metrics(
                csv_file,
                obs_date=date_dir.name,
                allowed_metrics=cfg["acquisition"]["metrics"],
                allowed_recipes=cfg["acquisition"]["recipes"],
            )
            if df is not None:
                collected.append(df)

        # Dispersion solution FITS products
        fits_files = find_disp_solution_fits_files(
            date_dir,
            cfg["acquisition"]["file_pattern_disp_solution_fits"],
        )

        # Optional: only if recipe enabled in config
        if "soxs-disp-solution" in cfg["acquisition"]["recipes"]:
            log.info(
                "Scanning %s (%d dispersion-solution FITS files)",
                date_dir.name,
                len(fits_files),
            )

            for fits_file in fits_files:
                df = extract_disp_solution_metrics_df(
                    fits_file,
                    obs_date=date_dir.name,
                    hdu_index=1,
                )
                if df is not None and not df.empty:
                    collected.append(df)

    if not collected:
        log.info("No QC metrics found")
        return

    df_all = pd.concat(collected, ignore_index=True)

    # Check if the recipes found are complete
    # (complete means there are all the metrics defined in the config)
    df_complete = filter_complete_recipes_by_arm(
        df_all,
        cfg=cfg,
        log=log,
    )

    if df_complete.empty:
        log.info("No complete recipes found")
        return
    
    # Register COMPLETE recipes in the registry
    for (obs_date, arm, recipe), _ in (
        df_complete
        .groupby(["obs_date", "arm", "recipe"])
    ):
        store.register_recipe_status(
            obs_date=obs_date,
            arm=str(arm),
            recipe=recipe,
            status="COMPLETE",
        )

    if args.dry_run:
        log.info("Dry-run enabled, not writing to database")
        print(df_complete)
        return

    # Write data and update registry
    store.write_metrics(df_complete)

    log.info("Database updated successfully")

    ####################################################
    ############### Plotting step #####################
    ####################################################

    if args.no_plots:
        log.info("Skipping plot generation (--no-plots)")
        return

    # Configure plots
    plots_cfg = cfg.get("plots", {})
    metrics_to_plot = plots_cfg.get("metrics", [])
    output_dir = Path(plots_cfg.get("output_dir", "plots"))

    # Load data from the (now updated) database
    df_plot = store.load_all_metrics()

    # Generate plots per arm/metric
    for arm, df_arm in df_plot.groupby("arm"):
        arm = str(arm)

        for metric in metrics_to_plot:
            plot_time_series(
                df_arm,
                metric=metric,
                arm=arm,
                output_dir=output_dir / arm,
            )



if __name__ == "__main__":
    main()

import qc_monitor
import logging
import yaml
import argparse
import os
import sys
from pathlib import Path
import pandas as pd

from qc_monitor.acquisition import (
    find_session_databases,
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
from qc_monitor.storage import SQLiteStore
from qc_monitor.plotting import generate_order_location_plots_from_config, generate_plots_from_config
from qc_monitor.generate_html import generate_html_report
from qc_monitor.detector_linearity import (
    VIS_MODE_ORDER,
    detector_linearity_enabled,
    load_detector_linearity_data,
)


class ConfigurationError(RuntimeError):
    pass


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


def normalize_runtime_config(cfg: dict, project_root: Path) -> dict:
    cfg = dict(cfg)
    paths_cfg = dict(cfg.get("paths", {}))

    for key in ("upstream_root", "reduced_root", "qc_database"):
        if key in paths_cfg:
            paths_cfg[key] = str(resolve_project_path(paths_cfg[key], project_root))

    cfg["paths"] = paths_cfg

    plots_cfg = dict(cfg.get("plots", {}))

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

    if plots_cfg.get("template"):
        plots_cfg["template"] = str(
            resolve_project_path(
                plots_cfg["template"],
                project_root,
            )
        )

    cfg["plots"] = plots_cfg

    detlin_cfg = dict(cfg.get("detector_linearity", {}))
    arms_cfg = dict(detlin_cfg.get("arms", {}))

    for arm, arm_cfg in arms_cfg.items():
        arm_cfg = dict(arm_cfg)
        if arm_cfg.get("root"):
            arm_cfg["root"] = str(resolve_project_path(arm_cfg["root"], project_root))
        arms_cfg[arm] = arm_cfg

    detlin_cfg["arms"] = arms_cfg
    cfg["detector_linearity"] = detlin_cfg

    return cfg


def run_preflight(cfg: dict, project_root: Path) -> bool:
    log = logging.getLogger("qc-monitor")
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
        if label == "qc_database" and path.exists() and not path.is_file():
            errors.append(f"{label} exists but is not a file: {path}")
            continue

        if label == "plots.output_dir" and path.exists() and not path.is_dir():
            errors.append(f"{label} exists but is not a directory: {path}")
            continue

        if label == "plots.html_output" and path.exists() and path.is_dir():
            errors.append(f"{label} exists but is a directory: {path}")
            continue

        target = path if label == "plots.output_dir" else path.parent
        if not _is_writable_path(target):
            errors.append(f"{label} parent is not writable or cannot be reached: {path}")

    if template_path:
        template_path = Path(template_path).expanduser()
        if not template_path.is_file():
            errors.append(f"plots.template is not an existing file: {template_path}")

    if bool(detlin_cfg.get("enabled", False)):
        arms_cfg = detlin_cfg.get("arms", {})
        if not arms_cfg:
            errors.append("detector_linearity.enabled is true but no arms are configured")

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
        direct_db = upstream_root / upstream_database_name
        recursive_dbs = sorted(upstream_root.rglob(upstream_database_name))

        if upstream_search_mode == "direct":
            if not direct_db.is_file():
                if recursive_dbs:
                    errors.append(
                        f"{upstream_database_name} was not found directly under "
                        f"{upstream_root}, but {len(recursive_dbs)} nested database(s) "
                        "exist. Refusing to guess the production database."
                    )
                else:
                    errors.append(f"Upstream database not found: {direct_db}")
            elif len(recursive_dbs) > 1:
                warnings.append(
                    f"Nested {upstream_database_name} files were found but ignored "
                    "because upstream_database_search is 'direct'."
                )
        elif recursive_dbs:
            if len(recursive_dbs) > 1 and not allow_multiple_upstream:
                errors.append(
                    f"Found {len(recursive_dbs)} upstream databases under "
                    f"{upstream_root}; set allow_multiple_upstream_databases only "
                    "if this is intentional."
                )
        else:
            errors.append(f"No upstream database named {upstream_database_name} found")

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
    search_mode: str = "observing_day_dirs",
) -> int:
    log = logging.getLogger("qc-monitor")

    fits_files = find_dispersion_solution_fits_files(
        reduced_root,
        search_mode=search_mode,
    )

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
    search_mode: str = "observing_day_dirs",
) -> int:
    log = logging.getLogger("qc-monitor")

    fits_files = find_order_location_fits_files(
        reduced_root,
        search_mode=search_mode,
    )

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


def consolidate_detector_linearity(
    cfg: dict,
    qc_database: SQLiteStore,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    log = logging.getLogger("qc-monitor")

    if not detector_linearity_enabled(cfg):
        log.info("Detector-linearity acquisition disabled")
        return 0

    processed_days = qc_database.get_processed_detector_linearity_obs_days()

    df_measurements, df_results = load_detector_linearity_data(
        cfg=cfg,
        processed_obs_days=processed_days,
        force=force,
    )

    if df_measurements.empty and df_results.empty:
        log.info("No new detector-linearity rows to consolidate")
        return 0

    if dry_run:
        log.info("Dry-run enabled, not writing detector-linearity data")

        if not df_measurements.empty:
            print("DETECTOR LINEARITY MEASUREMENTS")
            print(df_measurements)

        if not df_results.empty:
            print("DETECTOR LINEARITY RESULTS")
            print(df_results)

        return len(df_measurements) + len(df_results)

    if not df_measurements.empty:
        qc_database.write_detector_linearity_measurements(df_measurements)

    if not df_results.empty:
        qc_database.write_detector_linearity_results(df_results)

    processed_arm_days = set()

    if not df_results.empty:
        expected_modes_by_arm = {}
        for arm in cfg.get("detector_linearity", {}).get("arms", {}):
            arm = str(arm).upper()
            if arm == "VIS":
                expected_modes_by_arm[arm] = set(VIS_MODE_ORDER)
            elif arm == "NIR":
                expected_modes_by_arm[arm] = {"NIR"}

        for (obs_day, arm), group in df_results.groupby(["obs_day", "eso seq arm"]):
            arm = str(arm).upper()
            expected_modes = expected_modes_by_arm.get(arm)

            if expected_modes is None:
                log.warning(
                    "Detector-linearity day %s arm %s is not configured; "
                    "not marking it as processed",
                    obs_day,
                    arm,
                )
                continue

            modes = {str(v) for v in group["detector_mode"].unique()}
            missing_modes = expected_modes - modes

            if not missing_modes:
                processed_arm_days.add((str(obs_day), arm))
            else:
                log.warning(
                    "Detector-linearity day %s arm %s has partial results; missing modes %s; "
                    "not marking it as processed",
                    obs_day,
                    arm,
                    sorted(missing_modes),
                )

    for obs_day, arm in sorted(processed_arm_days):
        qc_database.register_processed_detector_linearity_obs_day(obs_day, arm)

    log.info(
        "Consolidated %d detector-linearity measurements and %d result rows",
        len(df_measurements),
        len(df_results),
    )

    return len(df_measurements) + len(df_results)


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

    try:
        config_path = resolve_config_path(args.config)
        cfg = load_config(config_path)
    except Exception as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(2)

    config_dir = config_path.parent
    project_root = config_dir.parent

    cfg = normalize_runtime_config(cfg, project_root)

    upstream_root = Path(cfg["paths"]["upstream_root"])
    reduced_root = Path(cfg["paths"]["reduced_root"])
    qc_database_path = Path(cfg["paths"]["qc_database"])
    acquisition_cfg = cfg.get("acquisition", {})
    upstream_database_name = acquisition_cfg["upstream_database_name"]
    upstream_search_mode = acquisition_cfg.get("upstream_database_search", "direct")
    reduced_search_mode = acquisition_cfg.get("reduced_products_search", "observing_day_dirs")

    if not run_preflight(cfg, project_root):
        sys.exit(2)

    if args.preflight:
        return

    qc_database = SQLiteStore(qc_database_path)

    if args.rebuild_db:
        log.warning("Rebuilding QC database from scratch")
        qc_database.drop_all()

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
        search_mode=reduced_search_mode,
    )

    log.info("Total consolidated dispersion-solution rows: %d", dsol_points)

    oloc_points = consolidate_order_location_models(
        reduced_root=reduced_root,
        qc_database=qc_database,
        dry_run=args.dry_run,
        force=args.rebuild_db,
        search_mode=reduced_search_mode,
    )

    log.info("Total consolidated order-location model rows: %d", oloc_points)

    detlin_points = consolidate_detector_linearity(
        cfg=cfg,
        qc_database=qc_database,
        dry_run=args.dry_run,
        force=args.rebuild_db,
    )

    log.info("Total consolidated detector-linearity rows: %d", detlin_points)

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

    generate_html_report(
        plots_cfg=plots_cfg,
        output_html=html_output,
        template_path=(
            Path(plots_cfg["template"])
            if plots_cfg.get("template")
            else None
        ),
    )


if __name__ == "__main__":
    main()

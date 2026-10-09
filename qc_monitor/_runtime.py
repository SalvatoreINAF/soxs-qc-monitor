"""Configuration resolution and protected operational setup."""
import os
from pathlib import Path
from qc_monitor.config import (
    ConfigurationError,
    load_config,
    normalize_runtime_config,
)
from qc_monitor.coordination import (
    leases,
    config_resources,
    configuration_requests,
)

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


def prepare_runtime(args, run):
    """Resolve destinations and recheck configuration under operation leases."""
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
        publication_namespace = Path(cfg['plots']['output_dir']).resolve() / '.qc-publication'
        lexical_target = Path(os.path.abspath(args.summary_json.expanduser()))
        if (target == publication_namespace or target.is_relative_to(publication_namespace)
                or lexical_target == publication_namespace
                or lexical_target.is_relative_to(publication_namespace)):
            args.summary_json = None
            raise ConfigurationError(f'Summary destination overlaps managed publication: {target}')
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

    return cfg, config_path, project_root

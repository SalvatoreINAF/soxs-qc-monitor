"""Read-only preflight and path validation."""
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from qc_monitor.acquisition import find_session_databases, find_observing_day_directories
from qc_monitor.storage import ReadOnlyStorageError, validate_readonly_sqlite_path
from qc_monitor.schema import TABLE_SCHEMA, SCHEMA_VERSION
from qc_monitor.generate_html import _load_template
from qc_monitor.config import ConfigurationError, normalize_runtime_config
from qc_monitor.storage import validate_schema, SchemaError
from qc_monitor._sqlite_retry import SQLITE_TIMEOUT_SECONDS, retry_sqlite

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

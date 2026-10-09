"""Domain consolidation on one configured store; unit commits stay explicit."""
import logging
from pathlib import Path
import pandas as pd
from qc_monitor.acquisition import (
    find_session_databases,
    _load_qc_batch,
    _load_dsol_batch,
    _load_oloc_batch,
    find_dispersion_solution_fits_files,
    parse_dispersion_solution_filename,
    find_order_location_fits_files,
    parse_order_location_filename,
)
from qc_monitor.storage import (
    SQLiteStore,
    validate_readonly_sqlite_path,
    _prepare_unit_frames,
)
from qc_monitor.schema import TABLE_SCHEMA
from qc_monitor._outcomes import AcquisitionBatch, InputOutcome
from qc_monitor.detector_linearity import _load_detector_linearity_batch, detector_linearity_enabled
from qc_monitor.config import (
    ConfigurationError,
    load_config,
    normalize_runtime_config,
    resolve_project_path,
)
from qc_monitor.locking import locked_coordinator
from qc_monitor.coordination import (
    leases,
    runtime_requests,
    project_requests,
)
from qc_monitor.rebuild import acquisition_store
from qc_monitor.storage import qc_identity

from ._preflight import validate_path_collisions

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

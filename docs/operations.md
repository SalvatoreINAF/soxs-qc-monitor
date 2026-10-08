# Batch operation and recovery — D2

Run only after the pipeline has finished reduction. An inventory of present FITS
files does not certify producer completion. Closed observing days are normally
skipped; incomplete units are retried atomically at the next invocation.

## Interpreter and verified environment

Python 3.12 is the reference environment. Use the same absolute interpreter for
installation, preflight, execution and updates. The supported range remains
Python 3.11–3.13; the workflow checks Linux on all three and macOS on 3.12.

```sh
python3.12 -m venv /path/to/qc-env
/path/to/qc-env/bin/python -m pip install -c requirements/reference-py312.txt setuptools wheel build '.[test]'
/path/to/qc-env/bin/python -m pip check
/path/to/qc-env/bin/python -m pytest -ra --tb=short
/path/to/qc-env/bin/python -m build --wheel --no-isolation --outdir /tmp/qc-wheel
```

`reference-py312.txt` fixes direct, transitive, test and build dependencies. It is
a constraints file, not an installation list. Python 3.11/3.13 compatibility jobs
resolve the declared package requirements separately. Record their exact versions
when investigating a failure. The standalone permits NumPy, Astropy, Matplotlib
and PyYAML, but must not import `qc_monitor`.

For an independent installation check, install the wheel into a second clean
virtual environment and run its interpreter with `scripts/check_installation.py`.
The check uses an isolated interpreter, a temporary working directory, synthetic
SQLite data and the installed console entry point; no source `PYTHONPATH` is used.
Configuration, wrappers and standalone remain in the checkout, outside the wheel.

## Exit codes and summary

| Code | Meaning | Operator action |
|---|---|---|
| 0 | Completed; valid empty sources and no new data are normal | Check freshness separately |
| 1 | Partial acquisition; failed input or an open unit | Inspect family errors, repair source, retry |
| 2 | Blocking error | Inspect traceback and failed phase before retrying |

Each parsed CLI invocation logs one `RUN_SUMMARY <JSON>` line. Argument parser
errors retain argparse output and code 2. JSON format version 1 includes UUID,
mode, UTC start/end, monotonic durations, installed versions, phases, family
states and errors. Disabled families are explicit. Fatal exceptions dominate
partial acquisition. Rendering errors remain blocking. D2 adds storage/schema and sequence metadata
without changing JSON format version 1; see [D2 contracts](d2-contracts.md).

Per-table counters mean:

- `selected`: valid loader rows belonging to units considered for this attempt,
  before deduplication; it is not necessarily the number of persisted rows.
- `persisted`: rows written after a successful whole-unit commit.
- `discarded`: rows rejected by the loader where measurable; otherwise `null`.
- `duplicates`: identical rows eliminated during validation.
- `not_persisted_incomplete`: available rows withheld because the unit is incomplete.
- `preserved`: historical rows belonging to encountered closed units that were
  skipped. This is not a comparison with new source content.

`input_states` counts diagnostic events; it is not a unique-file counter. FITS
failures may not expose a row count. `completed_units` records actual commits;
`validated_units` also reports complete units in dry-run. `latest_data_utc` is
read from persisted data and is independent of `ended_utc`; unavailable history
is `null`. No age threshold changes the acquisition status.

```sh
/path/to/qc-env/bin/python -m qc_monitor.main --config /path/to/clone/configs/qc_monitor.yaml --summary-json /path/to/clone/logs/latest.json
```

The optional summary is replaced atomically on its own filesystem. Its destination
cannot overlap configured inputs, configuration, the QC database or configured
report artifacts. A failed save gives code 2 and an updated log summary. Dry-run
and preflight ignore this flag with a warning and never write the summary file.
If configuration loading fails before the destination can be checked, the
summary is log-only. Summary atomicity does not imply atomic HTML/PNG publication.

## Scheduler, timeout, logs and missing jobs

The tcsh wrappers dispatch `scripts/batch.py` through `QC_PYTHON`; that interpreter
also invokes the monitor and pip. Set `QC_PYTHON` to an absolute executable before
starting the wrapper. `python` in the active environment is the fallback.

| Environment variable | Default | Meaning |
|---|---:|---|
| `QC_JOB_TIMEOUT_SECONDS` | 7200 | Maximum supervised job duration |
| `QC_LOG_RETENTION_DAYS` | 30 | Age beyond which recognized log files are removed |
| `QC_FRESHNESS_HOURS` | 48 | Maximum age of a normal batch summary |

```sh
QC_PYTHON=/path/to/qc-env/bin/python ./run_SOXS_QC_Monitor.sh
/path/to/qc-env/bin/python scripts/batch.py freshness --root /path/to/clone
```

The run wrapper uses the monitor's own preflight, avoiding a second acquisition
run. It forces backend `Agg`. Timeout terminates the subprocess group and returns
2; abrupt termination can leave no monitor summary. The external freshness check
examines the newest recognized run log: missing/malformed summary or age beyond
48 hours gives 2; a recent summary propagates its 0/1/2. An older success does not
hide a more recent failed attempt; a supervisor error dominates a successful
monitor summary. Update and inspection runs do not refresh it.
Run this check through an independent scheduler, including when the normal job
never starts. No scheduler entries or notifications are installed automatically.

Retention deletes only regular, non-symlink files with recognized monitor log
names, protects the current log, and leaves foreign files and backup directories
alone. Backups need an explicit operator retention policy. Defaults are initial
operational limits, not measured production performance guarantees.

## Update and rollback

Stop scheduled jobs and ensure no CLI/API acquisition is running. D2 leases
coordinate CLI/API storage writers; update and report publication are not yet
coordinated by that lease. Keep the previous environment intact; prepare a candidate
virtual environment or clone of the Conda environment. Save the last known good
wheel/revision and verify source data availability before any DB maintenance.

The update wrapper uses the selected candidate interpreter. It saves the entire
`configs/` directory, current Git revision, installed requirements and a consistent
SQLite backup under `logs/backup_<UTC>_<id>/` before `git pull --ff-only` and
`python -m pip install .`. It then runs preflight and read-only dry-run. Any nonzero
result prevents an update success report; partial dry-run returns 1.

The helper does not switch environments or automatically restore a failed update.
If any check fails, leave the scheduler stopped. Restore the saved configurations
and use the preserved environment and revision/wheel. If restoring SQLite is
necessary, first save the failed archive, close all connections and restore the
backup while the scheduler is stopped. Validate preflight, dry-run and the test
suite before re-enabling execution. Never run rebuild as an automatic recovery.

## Schema transition and protected rebuild

Version 1.2.0 requires SQLite schema version 1 for ordinary writes. An old
unversioned archive causes ordinary preflight to fail, preventing the update
helper from reporting a usable deployment prematurely. Dry-run can still inspect
recognized legacy registers. Verify source availability and stop all jobs before
explicit maintenance:

```sh
/path/to/qc-env/bin/python -m qc_monitor.main --config /path/to/clone/configs/qc_monitor.yaml --preflight --rebuild-db
/path/to/qc-env/bin/python -m qc_monitor.main --config /path/to/clone/configs/qc_monitor.yaml --rebuild-db --no-plots
```

The first command does not create a backup or replacement. The second preserves
a verified `<db>.backup-<unique>.sqlite`, builds separately, checks completeness
and coverage of previous units/products, and replaces only a valid candidate.
Missing historical inputs, unknown schema or active sidecars block replacement.
Do not delete the persistent `<db>.lock` to release a writer; OS process exit
releases the lease. Backups are retained for explicit operator recovery/retention.
See [full D2 contracts](d2-contracts.md) for failure counters and restore semantics.

## Limits retained for D3 and operational acceptance

Multiple DETLIN sequences now have independent fits and one atomic day/arm
commit; cross-date sequences remain unsupported. D1/D2 fixtures provide an
analytical baseline, not scientific acceptance on real instrument data.

HTML still references configured figures in `plots/` relative to the page. A
skipped figure may be missing or stale; other layouts are not reliable. There is
no artifact manifest, atomic report generation, image retention or figure-level
error isolation yet. Use the standard layout and inspect representative outputs.
`--no-plots` skips both PNG and HTML generation.

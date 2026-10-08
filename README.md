# SOXS QC Monitor

The SOXS QC Monitor is a lightweight monitoring tool that extracts Quality Control (QC) information from SOXS Pipeline products and generates a static HTML report with trend plots and diagnostic visualizations.

The monitor is designed to run periodically in batch mode and maintain an independent SQLite database containing historical QC information. It combines:

- QC metrics extracted from the SOXS Pipeline upstream database (`soxspipe.db`)
- Dispersion solution products
- Order localization products
- Detector linearity raw sequences

and produces:

- Historical trend plots
- Diagnostic plots
- A static HTML report referencing PNG images suitable for publication on the web

## Example HTML Report

An example report is available at:

https://salvatoreinaf.github.io/soxs-qc-monitor/

---

# Installation

The package is typically installed into the same Python/Conda environment used by the SOXS Pipeline.
The expected environment name is `soxspipe`.
Use the following commands to clone the repo in a suitable folder, activate the environment, and install the package:

```bash
mkdir -p ~/git_repos

cd ~/git_repos

git clone https://github.com/SalvatoreINAF/soxs-qc-monitor.git

cd ~/git_repos/soxs-qc-monitor/

conda activate soxspipe

python -m pip install .
```

The installation creates the command-line executable in the environment bin folder:

```bash
qc-monitor
```

This serves as the entry point to run the QC Monitor.

The cloned repository must remain available on the pipeline machine after
installation. Configuration files, wrapper scripts and update scripts are read
from the clone, not from the installed Python package directory.

---

# Initial Configuration

The monitor is configured through:

```text
configs/qc_monitor.yaml
```

The only mandatory configuration is the definition of the input and output paths.

Example:

```yaml
paths:
  upstream_root: /diska/home/pipeline/soxspipe_reductions/
  reduced_root: /diska/home/pipeline/soxspipe_reductions/reduced/
  qc_database: /diska/home/pipeline/soxspipe_reductions/reduced/QC/qc.sqlite

plots:
  output_dir: /diska/home/pipeline/soxspipe_reductions/reduced/QC/plots
  html_output: /diska/home/pipeline/soxspipe_reductions/reduced/QC/index.html
```

By default the monitor uses a production-safe acquisition policy:

```yaml
acquisition:
  upstream_database_search: direct
  reduced_products_search: observing_day_dirs
  allow_multiple_upstream_databases: false
  allow_suspicious_paths: false
```

This means that the upstream database must be found directly as:

```text
upstream_root/soxspipe.db
```

and reduced products are scanned only below observing-day directories named:

```text
reduced_root/YYYY-MM-DD/
```

Legacy recursive scanning is still available by setting the corresponding
search option to `recursive`, but it should not be used in production unless the
directory tree has been checked carefully.

## Detector Linearity Fit

The linear fit uses only positive signals at or below
`detector_linearity.saturation_level * saturation_fraction`. The default
`saturation_fraction` is `0.60`, selecting the low-signal part of the response
before departures from linearity near saturation. Higher-signal measurements
remain in the plots and residuals but do not influence the fit. There is no
exposure-time cutoff. At least two distinct exposure times must survive the
signal threshold; the threshold is never widened automatically.

Frame recognition uses the sequence IMGNAME header (or the configured filename
fallback). Both tools check `ESO DPR TYPE` against that name: bias/dark frames
require `LAMP,OFF`, illuminated frames require `LAMP,ON`. Missing/blank values
and historical `LAMP,FLAT` remain accepted with a warning; other mismatches are
rejected. VIS `ESO DET EXP TYPE`, when present, must also agree with the name.
DPR CATG and TECH are not constrained. Invalid frames prevent monitor day closure.

VIS processing requires exactly three biases per mode. Their pixelwise mean is
the master bias; single-frame read noise is the square root of half the mean
spatial variance of all three pair differences (`ddof=0`). This is not the noise
of the averaged master. The common master cancels in each flat-pair difference.
The standalone tool remains permissive: it averages all available biases and,
with at least two, uses all pair differences for noise. With one bias noise is
unavailable; with none it shows raw signals. Counts other than three are reported.

The standalone `utils/analyze_detector_linearity.py --config <config.yaml>`
uses the same default signal threshold (`saturation_fraction: 0.60`); explicit YAML values override it. It divides signals and ADU thresholds by
`BINX * BINY` to compare different binning factors in equivalent 1x1 ADU.
Its extrapolated maximum exposure uses the normalized nominal saturation, so
the reported time refers to the binning actually acquired, not a hypothetical
1x1 acquisition.

Existing processed days in the monitor database are not refitted automatically
when this setting changes. Recalculate from the original FITS in a separate
database if historical fits need the new threshold; the protected rebuild option
recreates the entire QC database.

## Default Configuration Resolution

When `qc-monitor` is executed without `--config`, it never uses the installed
package location under `site-packages` as the configuration root.

The default configuration is resolved in this order:

1. `QC_MONITOR_ROOT/configs/qc_monitor.yaml`, if `QC_MONITOR_ROOT` is set.
2. `configs/qc_monitor.yaml` in the current directory or one of its parents,
   only if that directory looks like the cloned QC Monitor repository.

If neither rule succeeds, the program exits with an explicit configuration
error and does not acquire data.

## Path Definitions

### `upstream_root`

Root directory containing the SOXS Pipeline upstream database:

```text
soxspipe.db
```

Example:

```text
/diska/home/pipeline/soxspipe_reductions/
```

### `reduced_root`

Directory containing the reduced products organised by observing day.

Example:

```text
/diska/home/pipeline/soxspipe_reductions/reduced/
```

### `qc_database`

SQLite database maintained by the QC Monitor.

The database is created automatically if it does not already exist.

Example:

```text
/diska/home/pipeline/soxspipe_reductions/reduced/QC/qc.sqlite
```

---

# Production Directory Layout

The typical production installation is assumed to look like:

```text
soxspipe_reductions/
├── soxspipe.db
├── SOXS.2025-03-15T00:39:10.639.fits
├── SOXS.2025-03-15T00:42:08.122.fits
├── ...
└── reduced/
    ├── 2025-03-15/
    ├── 2025-03-16/
    ├── ...
    └── QC/
        ├── qc.sqlite
        ├── index.html
        └── plots/
```

QC information is extracted from:

- the upstream SOXS Pipeline database (`soxspipe.db`)
- selected reduced FITS products contained in the reduction directories

---

# Running the Monitor

The monitor can be executed manually from the Command line (under the soxspipe environment):

```bash
qc-monitor --config configs/qc_monitor.yaml --verbose
```

Common options:

```bash
qc-monitor --help
```

```bash
qc-monitor --verbose
```

```bash
qc-monitor --preflight --config configs/qc_monitor.yaml --verbose
```

```bash
qc-monitor --preflight --rebuild-db
qc-monitor --rebuild-db --no-plots
```

```bash
qc-monitor --no-plots
qc-monitor --summary-json logs/latest.json
```

There is no `--force-date` CLI option. See [batch operation and recovery](docs/operations.md)
for exit codes 0/1/2, JSON diagnostics, exact reference dependencies and scheduler checks.


## Dry-run

```bash
qc-monitor --dry-run --config configs/qc_monitor.yaml
```

Dry-run loads and selects acquisition data without creating or changing the QC
archive, running schema migrations, generating plots or publishing HTML. An
absent QC archive is treated as having empty processed-day registers; existing
registers still filter out closed days. The dry-run preflight checks acquisition
inputs, without requiring writable output destinations or an HTML template.

`--dry-run --rebuild-db` is rejected with exit code `2` before configuration or
database access. A corrupt/unreadable QC archive or a required missing or
incompatible register also produces a diagnostic and exit code `2`, without
migration. Schema differences unrelated to the registers being read are left
untouched.

WAL-mode QC and upstream databases are explicitly rejected during dry-run,
even when their `-wal`/`-shm` files already exist. SQLite can create auxiliary
files during a read-only WAL open; H1 checks the header before opening SQLite
and does not checkpoint, convert, or copy the original archive. Ordinary runs
retain their existing WAL behavior. Run the monitor after reduction completes;
H1 does not introduce concurrency protection or WAL snapshot support.

The API has the same storage contract:

```python
from qc_monitor.main import consolidate
from pathlib import Path

selected = consolidate(
    Path("/path/to/soxspipe.db"),
    config_path=Path("/path/to/configs/qc_monitor.yaml"),
    dry_run=True,
)
```

It returns the number of selected QC rows and prints them as before.
`force=True, dry_run=True` selects closed days without writing. Storage failures
raise `qc_monitor.storage.ReadOnlyStorageError` (`RuntimeError`); the upstream
loader retains its existing empty-DataFrame behavior for read/schema errors.
`SQLiteStore(path, read_only=True)` also exposes read-only register access,
without initializing an absent archive.


## Complete observing-day acquisition

Run the monitor **after reduction completes**. H2 has no operational pipeline
completion marker: it checks selected inputs and their declared metadata, not
the age of a directory or a fixed number of products.

QC, dispersion solutions, order-location products and detector linearity have
separate processed-day registers (DETLIN also distinguishes the arm). A complete
unit replaces its data and writes its `PROCESSED` register in one transaction.
An incomplete attempt leaves the existing archive unchanged and can be retried;
no partial measurements or fits from that attempt are published. A failed SQL
write rolls back the data and register together and raises an explicit error.
Closed units are skipped normally. Forced acquisition replaces an older closed
unit only after full validation; failure preserves the previous data and register.
Consequently a failed forced attempt must be retried explicitly with force.

QC reads all selected session databases before closing any day. Preflight now
rejects incompatible upstream schemas before any family writes (CLI 2). Runtime
read failures still block new QC units when their affected days cannot be
identified; valid empty sources do not. Invalid required QC identifiers, arms or
numeric values block their day. Independent family API calls remain available. Equivalent duplicate rows, including nullable identities,
are deduplicated; conflicting rows sharing an existing identity keep the unit open.
Logs and JSON summaries distinguish selected rows from persisted rows; CLI
codes are 0 completed, 1 partial acquisition and 2 blocking failure.

A DSOL product requires usable line identifiers and resolution statistics for
every order actually present. Nonfinite individual `R_pin` samples are excluded
from statistics if usable samples remain for that order; an order with no usable
sample blocks closure. OLOC requires both the model HDU and order-metadata HDU,
finite coordinate ranges, and the coefficients required by its declared polynomial
degrees. Optional undeclared polynomials are not required.

DETLIN requires `ESO TPL START`, `ESO TPL ID`, `ESO TPL NEXP` and `ESO TPL EXPNO`.
The exposure indices must uniquely cover the declared `1..NEXP`; no universal
exposure count is assumed. VIS requires the four existing modes, three bias frames
per mode, and two flats per selected exposure time. NIR requires one dark and two
flats per selected exposure time. Each mode must have a finite fit using at least
two distinct usable times under the existing saturation selection. Saturated
exposures remain in the results when a fit is available from other exposures.

D2 introduces schema version 1 and separate DETLIN sequence identities and fits.
Multiple sequences per day/arm are supported, but all must be complete before
the day/arm is committed. Missing metadata or sequences spanning dates remain
open with a diagnosis. Binning and geometry are explicit; missing binning assumes
1 per axis, and ROI/signal conventions remain those of the acquired image.
The latest plot selects one complete sequence by TPL START. Recognizable DETLIN files with unreadable headers block their
arm's open units when no day can be established. Foreign files do not block
acquisition. `DATE-OBS` still supplies the DETLIN day; H2 introduces no new
observing-night definition.

When `allow_multiple_upstream_databases` is enabled, the public
`consolidate(upstream_db_path, ...)` API acquires the full set returned by the
configured discovery policy, verifies membership of the supplied path, and
returns the aggregate number of valid selected QC rows. This count is not a
promise that an incomplete unit was persisted. Single-source behavior and the
read-only dry-run contract remain unchanged.

H2 does not automatically reopen experimental days already registered by earlier
versions. Explicit archive maintenance requires a backup and verification of
available source data. It does not alter the standalone detector-linearity tool.

---

# Batch Execution

The monitor is intended to run periodically through cron or another scheduler.
An example tcsh wrapper is provided in the file `run_SOXS_QC_Monitor.sh`.

The wrapper resolves the repository root from its own location, exports
`QC_MONITOR_ROOT` and starts the monitor, which performs its own preflight.
Set `QC_PYTHON` to the desired interpreter. The supervisor applies configurable
timeout and log retention; see [operations](docs/operations.md).

---

# Updating

An update helper is provided:

```bash
./update_QC_Monitor.sh
```

The helper preserves configuration, revision, environment requirements and a
consistent SQLite backup, runs `git pull --ff-only`, installs with the selected
interpreter and checks preflight/dry-run. Prepare a candidate environment and
stop the scheduler first; see [update and rollback](docs/operations.md#update-and-rollback).

---

# Project Structure

```text
.
├── configs
│   ├── plots
│   └── qc_monitor.yaml
├── data
│   ├── qc.sqlite
│   └── upstream
├── logs
├── plots
├── qc_monitor
│   ├── acquisition.py
│   ├── config.py
│   ├── locking.py
│   ├── rebuild.py
│   ├── generate_html.py
│   ├── main.py
│   ├── plotting.py
│   ├── processing.py
│   ├── resources
│   │   └── template.html
│   ├── schema.py
│   ├── storage.py
│   └── run_result.py
├── README.md
├── pyproject.toml
└── run_SOXS_QC_Monitor.sh
```

## Main Components

### `main.py`

Application entry point.

Responsibilities:

- validated configuration and acquisition orchestration
- acquisition orchestration
- database consolidation
- plot generation
- HTML report generation

### `acquisition.py`

Acquires data from:

- upstream SOXS Pipeline database
- dispersion solution FITS products
- order localization FITS products

### `processing.py`

Placeholder containing only a docstring; it is not an operational processing layer.

### `storage.py`

Manages the QC Monitor SQLite database, schema checks and atomic family units.
`locking.py` coordinates storage writers; `rebuild.py` validates and publishes
replacement databases while retaining backups. `config.py` owns declarative
loading, defaults, validation and path normalization.

### `plotting.py`

Generates all PNG plots used by the report.

### `generate_html.py`

Generates the final HTML report.

### `schema.py`

Database schema definitions.

### `run_result.py`

Versioned run diagnostics, phase timing and optional atomic JSON summary.
Upstream access is implemented in `acquisition.py`; there is no `upstream.py` module.

---

# Notes

The QC Monitor maintains its own SQLite database and does not modify any SOXS Pipeline products or databases.

The monitor is designed to be re-run safely and incrementally as new reduction sessions become available.


# Development verification and handover

The Python 3.12 reference dependencies are fixed in
`requirements/reference-py312.txt`. The verification workflow tests `dev` pushes and pull
requests on Linux Python 3.11–3.13 and macOS Python 3.12, builds the wheel and
checks its isolated installation. See [test instructions](tests/README.md),
[operations](docs/operations.md) and [session handover](docs/handover.md).

The report currently requires the standard HTML/`plots/` layout. Missing/stale
figure handling and coherent publication remain D3 work. No P0 dry-run or
whole-unit transaction guarantees are relaxed by these limitations.


D1 è formalmente chiuso l’8 ottobre 2026: [matrice hosted verde](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37772436524)
sul commit `fb37d9e`, con 216 PASS per job (Linux 3.11/3.12/3.13 e macOS 3.12),
build della wheel e installazione isolata verificate. La chiusura documentale
successiva conserva i limiti D2/D3 e non avvia automaticamente nuove fasi.


## D2 — Configuration and storage

**D2 formalmente chiuso l’8 ottobre 2026**: [CI hosted verde](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37793731551)
su `9f666b0`, 315 PASS in ciascuno dei quattro job Linux/macOS; build e
installazione isolata della wheel riuscite. D3 non avviato.

Version **1.2.0** validates YAML, includes, query references, renderer parameters,
ROIs and path collisions before acquisition. Relative operational paths retain
`config_path.parent.parent`; includes remain relative to the YAML directory.
Recursive discovery now includes both direct and nested session databases,
subject to the configured multisource consent.

Writable archives require SQLite **schema version 1**. Unversioned experimental
archives require an explicit backed-up rebuild; no automatic migrations occur.
Dry-run retains legacy-register inspection and its no-write/WAL contract. The
rebuild verifies source completeness and coverage of previous product identities,
then atomically replaces the archive; a failure keeps the previous database.
CLI/API writers share a per-archive lease. Update and publication coordination
remain D3, so scheduled jobs must still be stopped for updates.

See [D2 contracts and recovery](docs/d2-contracts.md),
[verification evidence](tests/results/d2-validation.md) and
[handover and delivery](docs/handover.md) for status. No next development step
is started automatically.

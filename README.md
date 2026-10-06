# SOXS QC Monitor

The SOXS QC Monitor is a lightweight monitoring tool that extracts Quality Control (QC) information from SOXS Pipeline products and generates a static HTML report with trend plots and diagnostic visualizations.

The monitor is designed to run periodically in batch mode and maintain an independent SQLite database containing historical QC information. It combines:

- QC metrics extracted from the SOXS Pipeline upstream database (`soxspipe.db`)
- Dispersion solution products
- Order localization products

and produces:

- Historical trend plots
- Diagnostic plots
- A self-contained HTML report suitable for publication on the web

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

pip install .
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

The standalone `utils/analyze_detector_linearity.py --config <config.yaml>`
uses the same signal threshold. It divides signals and ADU thresholds by
`BINX * BINY` to compare different binning factors in equivalent 1x1 ADU.
Its extrapolated maximum exposure uses the normalized nominal saturation, so
the reported time refers to the binning actually acquired, not a hypothetical
1x1 acquisition.

Existing processed days in the monitor database are not refitted automatically
when this setting changes. Recalculate from the original FITS in a separate
database if historical fits need the new threshold; the database rebuild option
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
qc-monitor --rebuild-db
```

```bash
qc-monitor --force-date YYYY-MM-DD
```


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

---

# Batch Execution

The monitor is intended to run periodically through cron or another scheduler.
An example tcsh wrapper is provided in the file `run_SOXS_QC_Monitor.sh`.

The wrapper resolves the repository root from its own location, exports
`QC_MONITOR_ROOT`, runs a preflight check, and only then starts the normal QC
Monitor execution.

---

# Updating

An update helper is provided:

```bash
./update_QC_Monitor.sh
```

The script backs up `configs/qc_monitor.yaml`, runs `git pull --ff-only`,
reinstalls the package with `pip install .`, then runs preflight and dry-run
checks. It does not rebuild or delete the historical QC database.

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
│   ├── generate_html.py
│   ├── main.py
│   ├── plotting.py
│   ├── processing.py
│   ├── resources
│   │   └── template.html
│   ├── schema.py
│   ├── storage.py
│   └── upstream.py
├── README.md
├── pyproject.toml
└── run_SOXS_QC_Monitor.sh
```

## Main Components

### `main.py`

Application entry point.

Responsibilities:

- configuration loading
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

Performs transformations and aggregation of acquired data.

### `storage.py`

Manages the QC Monitor SQLite database.

### `plotting.py`

Generates all PNG plots used by the report.

### `generate_html.py`

Generates the final HTML report.

### `schema.py`

Database schema definitions.

### `upstream.py`

Utilities used to access the SOXS Pipeline upstream database.

---

# Notes

The QC Monitor maintains its own SQLite database and does not modify any SOXS Pipeline products or databases.

The monitor is designed to be re-run safely and incrementally as new reduction sessions become available.

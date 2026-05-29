# SOXS QC Monitor

SOXS QC Monitor is a Python module used to collect, consolidate, and visualize quality-control data produced by the SOXS pipeline.

The module reads QC information from upstream SOXS pipeline products, stores selected quantities into an independent SQLite database, generates monitoring plots, and produces a static HTML report.

An example HTML report is available here:

https://salvatoreinaf.github.io/soxs-qc-monitor/

## Installation

Create and activate a dedicated Python environment (or use the same as the SOXS Pipeline), then install the package from the project root:

```bash
pip install -e .
```

The required Python dependencies are listed in `pyproject.toml`.

## Initial configuration

Edit:

```text
configs/qc_monitor.yaml
```

For a basic installation, the user only needs to configure the input QC root and the output SQLite database path:

```yaml
paths:
  qc_root: data/upstream/long_term_reduction/
  qc_database: data/qc.sqlite
```

`qc_root` must point to the directory containing the upstream SOXS pipeline reduction products and databases.

`qc_database` is the independent SQLite database created and maintained by SOXS QC Monitor.

## Running manually

From the project root:

```bash
python -m qc_monitor.main --config configs/qc_monitor.yaml --verbose
```

This will:

1. scan the upstream QC products;
2. consolidate new QC data into the local SQLite database;
3. generate PNG plots;
4. update the static `index.html` report.

## Batch execution

The project includes a batch execution script:

```text
run_SOXS_QC_Monitor.sh
```

Before using it, check and adapt the configuration section near the top of the script:

```tcsh
set CONFIG=${ROOT}/configs/qc_monitor.yaml
set LOG_DIR=${ROOT}/logs
set PYTHON=python
```

`PYTHON` should point to the Python executable from the environment where the package and its dependencies are installed.

The script can be executed manually:

```bash
./run_SOXS_QC_Monitor.sh
```

or periodically through a cron job.

The script writes logs into:

```text
logs/
```

A placeholder section for web publication is included in the script, but the actual publication mechanism must be configured by the deployment team.

## Project structure

```text
configs/
```

Configuration files. The main configuration is `qc_monitor.yaml`; plot-specific YAML files are stored under `configs/plots/`.

```text
data/
```

Local data area. It contains the independent QC SQLite database and, in development setups, example upstream data.

```text
plots/
```

Generated PNG monitoring plots.

```text
index.html
```

Generated static HTML QC report.

```text
qc_monitor/acquisition.py
```

Reads upstream SOXS pipeline databases and FITS products.

```text
qc_monitor/storage.py
```

Manages the independent SQLite QC database.

```text
qc_monitor/plotting.py
```

Generates monitoring plots from the consolidated QC database.

```text
qc_monitor/generate_html.py
```

Builds the static HTML report from the generated plots.

```text
qc_monitor/template.html
```

HTML template used by the report generator.

```text
qc_monitor/main.py
```

Main orchestration script.

```text
qc_monitor/processing.py
```

Optional processing hooks for datapoints before plotting.

```text
qc_monitor/schema.py
```

Shared schema definitions.

```text
qc_monitor/upstream.py
```

Utilities related to upstream SOXS pipeline inputs.

## Notes

SOXS QC Monitor does not modify the upstream SOXS pipeline database or products. It builds and maintains a separate SQLite database for long-term monitoring.
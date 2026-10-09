# SOXS QC Monitor

**Current: 1.7.0/schema 1; D3-E formally closed after hosted verification.**
See [handover](docs/handover.md) for the current resume point.

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
            └── .qc-publication/<report-id>/generations/<uuid>/
                ├── plots/
                ├── manifest.json
                └── report.html
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

The CLI publishes self-contained generations atomically and retains two by default.
Missing/failed figures have explicit cards without stale images. HTML and image
destinations may be separate; see the D3-E operational contract below. Dry-run
and whole-unit transaction guarantees are preserved.


D1 è formalmente chiuso l’8 ottobre 2026: [matrice hosted verde](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37772436524)
sul commit `fb37d9e`, con 216 PASS per job (Linux 3.11/3.12/3.13 e macOS 3.12),
build della wheel e installazione isolata verificate. La chiusura documentale
successiva conserva i limiti D2/D3 e non avvia automaticamente nuove fasi.


## D2 — Configuration and storage

**D2 formalmente chiuso l’8 ottobre 2026**: [CI hosted verde](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37793731551)
su `9f666b0`, 315 PASS in ciascuno dei quattro job Linux/macOS; build e
installazione isolata della wheel riuscite. Le funzionalità successive sono descritte sotto.

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


## D3 — Roadmap e handover per milestone

**D3-0 documentale consegnato l’8 ottobre 2026** su `dev`: consultare
[l’indice D3](docs/d3-roadmap.md) per ordine, dipendenze, decisioni e stime,
e le sei schede collegate per pianificare una milestone alla volta.
D3-A è **completata e formalmente chiusa**, pacchetto **1.3.0**, schema SQLite **1**
invariato. D3-B formalmente chiusa nel pacchetto **1.4.0**; D3-C…F non avviate.
[Verifiche D3-0](tests/results/d3-0-validation.md) e
[handover](docs/handover.md) identificano la baseline e il punto di ripresa:
**verifica e chiusura hosted D3-B**, senza avanzamento automatico.

### D3-A — Acquisizione resiliente

Un calcolo DETLIN fallito è isolato alla sua sequenza: le altre vengono calcolate,
ma il giorno/braccio si salva solo quando tutte le sue sequenze sono complete.
Un nuovo tentativo dopo la riparazione conserva l'idempotenza; un tentativo
forzato fallito conserva i dati precedenti. I nomi malformati senza giorno
riconoscibile impediscono la chiusura delle unità potenzialmente coinvolte della
famiglia, senza fermare le altre famiglie.

Letture SQLite, preflight e transazioni di acquisizione hanno timeout esplicito
di 5 secondi e due retry aggiuntivi, con attese di 0,25 e 0,5 secondi, soltanto
per codici busy/locked. Prima di riprovare si annulla l'intera transazione e si
chiude la connessione. La politica è fissa, senza nuove opzioni YAML/CLI.
Il JSON v1 espone diagnosi di sequenza e `sqlite_operations`, compresi i retry
risolti. Errori input/fit danno 1; errori bloccanti dell'archivio danno 2.

Vedere [scheda D3-A](docs/d3/d3-a.md), [procedure](docs/operations.md) e
[verifiche D3-A](tests/results/d3-a-validation.md).
[CI D3-A verde](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37807882167), attempt 1, sul commit `be8b3d5`:
363 PASS per job Linux 3.11/3.12/3.13 e macOS 3.12, build wheel e installazione
isolata riuscite. Update/pubblicazione, grafici, generazioni e retention restano
negli step successivi; D3-B consegnata localmente con CI pendente.


## D3-B — Coordinamento operativo (1.4.0, schema 1)

Una sola operazione per cartella operativa; conflitto immediato con uscita 2.
Progetti separati procedono se non condividono archivio o report incompatibili.
Run e API usano ambiente Python e sorgenti con lease condivise, update esclusive.
Le protezioni comprendono directory annidate e percorsi risolti tramite symlink,
e durano fino a HTML/riepilogo, oppure al termine del log di update.
Il JSON v1 aggiunge `coordination`; il supervisore registra `COORDINATION` JSON.

Il registro privato `/tmp/soxs-qc-monitor-locks-<uid>` e `<db>.lock` mantengono
file persistenti: non cancellarli per risolvere una contesa. Verificare il
processo proprietario e riprovare quando è terminato. Sono protezioni
cooperative sullo stesso host/account Linux/macOS; prima di introdurre 1.4.0
terminare i processi operativi delle versioni precedenti.

Update salva configurazioni/include/provenienza e usa i percorsi normalizzati.
Se dopo pull cambiano archivio o destinazioni dei report si ferma prima di
installare: conservare backup/log, rivedere la configurazione e riprovare.
Non viene eseguito alcun rollback automatico. I controlli preflight/dry-run
figli restano senza lock; anche quelli autonomi non garantiscono una fotografia
atomica durante update. Il wrapper run lascia le lease al monitor figlio.

Per verificare in un ambiente di test, senza operare sui dati dell’utente:

```sh
python -m pytest tests/test_d3b_coordination.py -ra --tb=short -W error
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-d3b-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
/path/to/installed-env/bin/python -m pip check
```

Eseguire le suite in sequenza: le prove di update prendono lease esclusive
sull’ambiente e sui sorgenti usati dai processi di test. Pull/installazione sono
simulati, backup e controlli figli eseguiti su fixture temporanee reali.
Vedere [scheda D3-B](docs/d3/d3-b.md).
Implementazione locale e chiusura formale sono distinte: CI D3-B pendente,
D3-C non avviata. Questa nota aggiorna le precedenti indicazioni di ripresa.


## Correzione timeout dopo CI — 9 ottobre 2026

CI 37818741442 sul candidato `0df371c`: Linux 3.11/3.12/3.13, 399 PASS
più lo stesso fallimento nel rilascio della lease dopo timeout; macOS 3.12 verde.
Il supervisore attendeva soltanto il processo principale dopo SIGKILL.
Riproduzione Linux del vecchio codice: **20 contese immediate su 20 prove**.

Correzione applicativa **`179f3ecaa7cb1fce0faa2ffe79931650bf359cb4`**:
attesa verificabile della fine dei processi attivi del gruppo, limite **5 s**,
scansioni `ps` ogni massimo 20 ms. Processi zombie/dead, che hanno già chiuso
le risorse, non impediscono il completamento. Mancata terminazione o errore
nell’ispezione resta bloccante; nessuna pausa fissa usata come prova di rilascio.
Richiesto `ps` di sistema (macOS; pacchetto `procps` su Linux minimale).
Pacchetto 1.4.0/schema 1 conservati, moduli della wheel invariati.

Suite aggiornata: **405 casi**, cinque nuovi rispetto alla consegna iniziale.
macOS Python 3.12.15: **405 PASS / 207,52 s**, `-W error`.
Docker Linux ARM64 Python 3.12.15: **404 PASS, 1 SKIP / 174,76 s** sotto root;
il caso sui permessi è poi passato con utente normale (**1 PASS / 1,04 s**).
Sei casi mirati del timeout, tutti PASS: Linux utente normale (2,57 s),
macOS Python 3.11.17 (2,33 s) e 3.13.16 (2,31 s).
Il test aggiunto ritarda la consegna di SIGKILL al figlio e pretende la lease
libera al ritorno del supervisore; verifica anche gruppi con zombie e limite
massimo dell’attesa. Formule, tolleranze, schema e retry invariati.

Questa correzione aggiorna la consegna locale precedente. **Nuova CI pendente**
sul nuovo candidato: Linux x86_64 3.11/3.12/3.13 e macOS 3.12. Le prove locali
Docker ARM64 non equivalgono alla matrice hosted. D3-B non formalmente chiusa;
nessun push/merge/deploy, nessun D3-C.
Dettagli: tests/results/d3-b-timeout-correction.md e
 docs/qa/d3-b-environments.json. Le verifiche wheel precedenti restano valide
per i moduli Python/template invariati; il supervisore corretto vive nel checkout.


## D3-B — Chiusura formale, 9 ottobre 2026

**D3-B completata e formalmente chiusa.** [CI 37933559550](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37933559550),
attempt 1, sul candidato corretto **`7a952c5972dfa7f00a0ccfefc5968e40f7e05d8a`**.
**405 PASS per ciascun job**, nessuno skip/XFAIL: Linux Python 3.11
(178,99 s), 3.12 (182,66 s), 3.13 (181,69 s), macOS 3.12 (240,88 s).
Build wheel e checker di installazione isolata PASS in tutti e quattro i job.
`pip check` è verificato localmente; il workflow hosted non lo esegue separatamente.
La correzione timeout `179f3ec` è dunque verificata anche dalla matrice hosted.
Il precedente run fallito resta evidenza storica, superata da questa esecuzione.

Pacchetto **1.4.0**, schema **1**; nessuna verifica D3-B pendente.
Questa nota aggiorna le precedenti indicazioni di CI pendente.
Ripresa: pianificazione D3-C **soltanto su nuova richiesta**.
**D3-C non avviata.** Nessun push/merge/deploy o rebuild operativo in questa
chiusura; aggiornamenti solo documentali, sorgenti/test/workflow invariati.

## D3-C — Piano dettagliato consegnato, 9 ottobre 2026

Su `dev` è disponibile il [piano D3-C](docs/d3/d3-c.md), verificato sul codice
1.4.0/schema 1 dopo la chiusura D3-B. **Sviluppo non avviato.**
Prevede esiti per figura, isolamento dei guasti, cleanup Matplotlib, Agg batch,
HTML parziale e diagnostica JSON v1 additiva; la pubblicazione resta diretta.
[Audit della baseline](tests/results/d3-c-planning.md): 82 PASS mirati;
[handover corrente](docs/handover.md). Stima sviluppo completo **10–14 ore**,
incluse verifiche e documentazione, escluse attese CI. Ripresa su nuova richiesta:
sviluppo della sola C, senza avanzare a D. Questa nota aggiorna le precedenti
indicazioni di ripresa; le funzionalità pianificate non sono ancora disponibili.

## D3-C — Esiti delle figure (1.5.0, schema 1)

**D3-C consegnata e verificata localmente su `dev` il 9 ottobre 2026.**
Pacchetto **1.5.0**, SQLite **schema 1**. Commit applicativo **`45a7e3e5a2c8133120e185a42ded9e6f4256049f`**.
D3-A/B restano formalmente chiuse; **CI hosted D3-C pendente, D3-D…F non avviate**.

Ogni figura del batch ha un esito produced/no_data/failed. I renderer indipendenti
proseguono dopo un errore; il report mostra schede senza immagini per assenza o
fallimento, e segnala gli scarti quando può produrre una figura valida. Una
serie interamente guasta rende fallita la figura. Gli errori danno codice 2
anche con report pubblicato; l'assenza legittima non è un errore.

I generatori ritornano liste di FigureResult e conservano le eccezioni per
default; `continue_on_error=True` abilita la raccolta tollerante usata dal batch.
HTML accetta `figure_results`; senza parametro resta legacy. JSON v1 aggiunge
`plots` e `report`, distinguendo grafici e HTML pubblicato. Batch non interattivo
usa Agg, le API conservano il backend esplicito. No-plots/dry-run/preflight
rimangono senza rendering/pubblicazione.

[Contratti](docs/d2-contracts.md), [procedure](docs/operations.md),
[evidenze](tests/results/d3-c-validation.md) e [handover](docs/handover.md).
490 PASS per Python 3.11/3.12/3.13 locale e wheel verificata nei tre venv;
CI hosted pendente. Pubblicazione ancora diretta nel layout standard:
nessuna atomicità, retention o immagine riusata in C. Fermarsi prima di D.

## D3-C — Chiusura formale, 9 ottobre 2026

**D3-C completata e formalmente chiusa.** [CI 37951987536](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37951987536), attempt 1,
sul candidato **`45257ccc71d62ba6fa8174256bca15964da3ac9d`**. **490 PASS per ciascun job**, nessuno skip/XFAIL,
warning come errori: Linux Python 3.11 (193,96 s), 3.12 (229,21 s),
3.13 (233,03 s), macOS 3.12 (221,36 s). Build wheel e checker di installazione
isolata PASS in tutti i quattro job. `pip check` verificato localmente;
il workflow hosted non lo esegue separatamente.

Pacchetto **1.5.0**, SQLite **schema 1**. Commit applicativo `45a7e3e`,
candidato hosted `45257cc`, differenze solo documentali. Nessuna verifica C
pendente. Questa nota supera le precedenti indicazioni di CI pendente.
L'utente ha pubblicato il candidato; questa registrazione modifica soltanto
documenti, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
Ripresa: pianificazione D3-D soltanto su nuova richiesta, dopo controllo del
checkout e lettura di scheda/indice/handover. **D3-D…F non avviate.**


## D3-E atomic publication and retention (1.7.0)

The ordinary CLI now uses the D3-D atomic engine. Images live under
`plots.output_dir/.qc-publication/<report-id>/generations/<uuid>/plots/`;
the configured HTML is the only commit point. Existing PNGs are preserved.

```yaml
plots:
  publication:
    retained_generations: 2
    orphan_max_age_hours: 24
    max_orphan_staging: 2
```

Settings are optional and validated. At least two generations are retained;
zero orphan staging is allowed. Owned finalised orphans are removed at the next
publication attempt; staging is limited by age and count. Cleanup failure yields
exit 2 and does not roll back a published report or committed data. `--no-plots`,
dry-run and preflight do not clean output. These are artifact counts, not a byte
quota; foreign files, legacy PNGs and SQLite backups require operator management.
Old browser pages may lose pruned images. The HTTP server must expose both
configured destinations with matching relative URLs; no hosting change is automatic.

See [D3-E contract](docs/d3/d3-e.md), [operations](docs/operations.md) and
[handover](docs/handover.md). No image reuse; D3-F remains unstarted.
The following D3-D closure is historical evidence for version 1.6.0.


## D3-D — Chiusura formale, 9 ottobre 2026

**D3-D completata e formalmente chiusa.** [CI 37966108485](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37966108485), attempt **1**,
sul candidato **`dc3b736c6b62219c5f4e2fdae078fd5a03449e02`**. Suite con warning come errori:

| Job hosted | Esito suite | Durata | Wheel / checker isolato |
|---|---|---|---|
| Linux Python 3.11 | 549 PASS, 0 SKIP | 150,62 s | PASS |
| Linux Python 3.12 | 549 PASS, 0 SKIP | 232,58 s | PASS |
| Linux Python 3.13 | 549 PASS, 0 SKIP | 253,03 s | PASS |
| macOS Python 3.12 | 548 PASS, 1 SKIP | 274,41 s | PASS |

Nessun FAIL/XFAIL/XPASS. Lo skip macOS riguarda esclusivamente l'assenza di
un secondo filesystem scrivibile; la stessa prova reale passa nei tre job
Linux. Build wheel e checker di installazione isolata PASS in tutti i job.
`pip check` verificato localmente, non separatamente dal workflow hosted.

Pacchetto **1.6.0**, SQLite **schema 1**. Commit applicativo **`a7a2ebb`**,
candidato hosted **`dc3b736`**: differenze soltanto documentali. Nessuna verifica
D3-D pendente. Questa nota supera le precedenti indicazioni di CI pendente;
le evidenze locali e i relativi skip restano conservati come storia distinta.

L'utente ha pubblicato il candidato. Questa chiusura modifica soltanto
documenti/evidenze, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
CLI ordinaria ancora diretta; nessuna retention o riuso introdotti. Ripresa:
**pianificazione D3-E soltanto su nuova richiesta**, dopo controllo del checkout
e lettura di indice/scheda/handover. **D3-E/F non avviate.**


## D3-E — Chiusura formale, 9 ottobre 2026

**D3-E completata e formalmente chiusa.** [CI 37981677957](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37981677957), attempt **1**,
sul candidato **`9e5cdd0310b7314b859457ee82a94d8a6648ba45`**. Suite con warning come errori:

| Job hosted | Esito suite | Durata | Wheel / checker isolato |
|---|---|---|---|
| Linux Python 3.11 | 609 PASS, 0 SKIP | 192,33 s | PASS |
| Linux Python 3.12 | 609 PASS, 0 SKIP | 232,66 s | PASS |
| Linux Python 3.13 | 609 PASS, 0 SKIP | 242,13 s | PASS |
| macOS Python 3.12 | 608 PASS, 1 SKIP | 336,86 s | PASS |

Nessun FAIL/XFAIL/XPASS. Lo skip macOS riguarda esclusivamente il secondo
filesystem scrivibile assente; la stessa prova reale passa nei tre job Linux.
Build wheel 1.7.0 e checker di installazione isolata PASS nei quattro job.
`pip check` verificato localmente, non separatamente dal workflow hosted.

Pacchetto **1.7.0**, SQLite **schema 1**. Commit applicativo **`c48380d`**,
candidato hosted **`9e5cdd0`**: differenze soltanto documentali, verificate.
**Nessuna verifica D3-E pendente.** Questa nota supera le indicazioni precedenti
di CI pendente; le prove locali restano evidenze storiche distinte.

L'utente ha pubblicato il candidato. Questa chiusura modifica soltanto documenti
ed evidenze, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
Ripresa: **pianificazione D3-F soltanto su nuova richiesta**, dopo controllo di
checkout, indice, scheda F e handover. **D3-F non avviata; D3 non ancora chiusa.**

# Batch operation and recovery — D3-B

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

## Acquisition failures and bounded SQLite retries — D3-A

Package 1.3.0 retains schema 1, loader DataFrame returns and coordinator integer
returns. A failed DETLIN calculation records `sequence_id`, `phase=fit`, exception
`type` and `reason` in the family's `errors`; its partial results are discarded.
Other sequences are calculated, but every sequence in a day/arm must be complete
before that entire unit is replaced. A failed forced attempt preserves the prior
unit. Repair the source/cause and rerun normally for open units; no automatic fit
retry or new scientific normalization is introduced.

A selected DSOL/OLOC filename with no recognizable day conservatively prevents
closure of all potentially affected units in its family. Other families continue.
No day is guessed from a directory or header. Preflight still rejects incompatible
source/archive schemas before acquisition; a source failure arising later is
partial acquisition, whereas a failed QC archive operation blocks dependent phases.

SQLite operations use an explicit connection timeout of **5 seconds** and at most
**three attempts**, with **0.25 and 0.5 seconds** between attempts. Only numeric
`SQLITE_BUSY`/`SQLITE_LOCKED` codes (including extended variants and wrapped causes)
are retried. Each failed connection is closed and each transaction is rolled back
before the complete operation is repeated, while retaining the writer lease.
Schema, integrity, permission, I/O and full-disk failures are not retried. The
monitor's own `WriterBusyError` is still rejected immediately.

This policy covers source reads, preflight, archive initialization, registry and
historical reads, acquisition writers, and read-only rebuild validation/coverage.
Backup, archive replacement and explicit low-level `drop_all()` maintenance are
not replayed. There are no YAML/CLI retry settings. A single persistent lock at
one SQL statement normally costs about **15.75 seconds** of waiting; the policy
is a per-operation attempt limit, not an overall batch deadline. Multiple SQL
statements or separate operations can each wait. Keep the supervisor timeout.

The additive JSON v1 `sqlite_operations` list records contended operations across
preflight, acquisition and historical reads: `operation`, `source`, `attempts`,
`state` (`recovered`, `exhausted`, or `failed` after a retry followed by a permanent
error), and `failures` with numeric SQLite code/name, exception type/reason and
scheduled wait. Uncontended operations are omitted. QC families also carry their
source-read records; exhausted source errors include `sqlite_retry`. Direct store
callers can inspect `SQLiteStore.sqlite_operations`; an internal acquisition batch
retains source-read diagnostics. Logs are explanatory, not the source of state.

A recovered contention does not change a successful exit code. Exhausted runtime
source reads give partial acquisition (1), exhausted preflight or QC archive reads/
writes give blocking error (2). Legacy tables that are absent may still yield
unknown counts, but an exhausted read never becomes a false empty/unknown result.
Family and table `persisted` counters reflect only completed commits, even if a
later unit fails. Earlier commits remain available; failed rebuild candidates are
still reported as staged according to D2.

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

Versions 1.2.0, 1.3.0 and 1.4.0 require SQLite schema version 1 for ordinary writes. An old
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
Vedere [scheda D3-B](d3/d3-b.md).
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

# Batch operation and recovery — D3-F

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
| 2 | Error, including a failed figure in a published partial report | Inspect errors, figure states and traceback before retrying |

Each parsed CLI invocation logs one `RUN_SUMMARY <JSON>` line. Argument parser
errors retain argparse output and code 2. JSON format version 1 includes UUID,
mode, UTC start/end, monotonic durations, installed versions, phases, family
states and errors. Disabled families are explicit. Fatal exceptions dominate
partial acquisition. Rendering errors cause code 2 while independent figures and partial HTML can complete. D2 adds storage/schema and sequence metadata
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

Versions 1.2.0 through 1.7.0 require SQLite schema version 1 for ordinary writes. An old
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

The CLI uses atomic, self-contained image generations with bounded retention
(1.7.0, D3-E). Produced figures alone have image references; no_data/failed have
explicit cards. Direct legacy HTML calls keep their original semantics.
`--no-plots` skips PNG, HTML and publication cleanup. See the D3-E section below.


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

## D3-C — Contratto operativo pianificato, 9 ottobre 2026

**Non ancora implementato**, pacchetto corrente 1.4.0/schema 1. Il
[piano dettagliato](d3/d3-c.md) fissa: batch non interattivo Agg; errore di una
figura/lettura isolato, altre figure proseguono; report parziale con codice 2;
assenza legittima distinta da errore; nessun riferimento alle vecchie immagini
per esiti failed/no_data. JSON v1 aggiungerà `plots` e `report`; published indica
soltanto HTML scritto con successo. API senza esiti espliciti conservano il
comportamento legacy. Nessuna nuova opzione YAML/CLI, riuso o retention.
La pubblicazione resterà diretta nel layout standard fino a D3-E: il piano non
fornisce già la garanzia di aggiornamento atomico. Gli attuali limiti sopra
restano operativi. [Audit](../tests/results/d3-c-planning.md),
[handover](handover.md): prossima attività sviluppo C su nuova richiesta.

## D3-C — Esiti di rendering e report (1.5.0)

Implementato e formalmente chiuso dopo CI hosted verde. `RUN_SUMMARY` v1 aggiunge:

- `plots.state`: completed senza errori (anche tutto no_data), partial con
  failed e altri esiti, failed se tutte fallite, skipped senza rendering.
- `plots.counts`: produced/no_data/failed; `plots.figures` in ordine YAML con
  name/type/filename/state/reason_code/reason/path/error_type/discarded.
- `report.state`: published solo dopo scrittura HTML riuscita, failed dopo
  errore HTML, skipped quando non richiesto; path valorizzato solo su published.

Per ogni scarto: context/count/reason della serie/fase di preparazione;
non sommare come righe uniche fra query diverse. Produced con scarti leciti
non provoca codice 2. Una serie interamente inutilizzabile, lettura fallita,
errore di disegno/save/HTML comporta codice 2; no_data da solo non lo comporta.
L'acquisizione parziale conserva codice 1 in assenza di questi errori.
Controllare `plots`/`errors`, non soltanto il completamento della fase plots.

Il report viene scritto anche con tutte le figure vuote/fallite. Nessun link
alle vecchie immagini di tali figure e nessuna cancellazione dei PNG legacy.
Errori HTML lasciano report.failed; non assumere che il vecchio HTML sia fresco.
Le protezioni B restano attive fino al riepilogo. Batch show=false impone Agg;
show=true resta richiesta interattiva. Dry-run/preflight/no-plots e configurazioni
senza figure registrano skipped e non importano plotting nel percorso CLI.

Le API HTML senza esiti restano legacy. Pubblicazione diretta e layout standard
rimangono obbligatori; interruzioni possono ancora lasciare artefatti incoerenti.
Atomicità, layout separati, retention e riuso restano D/E/F.
[Evidenze C](../tests/results/d3-c-validation.md), [handover](handover.md).

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


## D3-E — Pubblicazione atomica e retention (1.7.0)

Il batch usa ora il motore D. Nessun nuovo comando, job di pulizia, migrazione,
rebuild o cambio scheduler richiesto. Le impostazioni opzionali `plots.publication`
sono: retained_generations=2 (intero >=2), orphan_max_age_hours=24 (finito >0),
max_orphan_staging=2 (intero >=0). Valori booleani numerici e campi ignoti rifiutati.

Il report HTML configurato è l'unico commit; PNG/manifesti/HTML archiviato sono
nella generazione autosufficiente sotto `.qc-publication/<report-id>/generations`.
Preflight verifica percorsi, proprietà e storia prima delle scritture DB, senza
modificare output. No-plots e dry-run ignorano le risorse grafiche inutilizzate.

All'avvio della pubblicazione, sotto lease: elimina generazioni possedute fuori
dalla storia conservata e staging scaduti/eccedenti. Dopo commit e fsync HTML:
retention delle ultime N pubblicazioni. Ordinamento staging per preparazione
UTC e UUID, non mtime. N può aumentare: la storia eliminata non ritorna, quella
disponibile cresce ai run successivi. Report correnti/archiviati conservati
vengono verificati prima della cancellazione.

`publication.cleanup.startup/retention` distingue stato, conteggi removed/remaining,
ignored e limits_guaranteed. Null indica fase/inventario non verificato; false
indica errore. Se cleanup iniziale fallisce, il report corrente resta e non si
pubblica altro. Se fallisce dopo commit, il report nuovo resta disponibile.
Entrambi danno codice 2; DB già committato indipendente dal cleanup.
`published/unconfirmed` dopo fsync HTML fallito non è rollback e non avvia retention.

Limiti di quantità/età, non byte, applicati ai run operativi. File estranei, PNG
legacy, backup SQLite e temporanei HTML senza proprietà verificabile non sono
cancellati. Ispezionare manualmente questi residui quando necessario; non adottare
directory riservate senza marker, modificare marker o cancellare lock per forzare
un run. Un browser con HTML molto vecchio può perdere le immagini già eliminate.
Il server web deve esporre HTML e immagini con URL relativi coerenti anche su
filesystem separati. Nessun riuso su errore fino a D3-F.

[Contratto completo](d3/d3-e.md). Le sezioni di chiusura precedenti sono evidenze
storiche; stato attuale e ripresa sono nell'handover.


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


Commit applicativo D3-E **`c48380dddaa33d48d2b66db4380bd454f0f7782b`**; consegna locale verificata,
CI E pendente sul candidato esatto. [Evidenze](../tests/results/d3-e-validation.md).


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


## D3-F — Riuso compatibile e stato corrente (1.8.0/schema 1)

D3-F e D3 formalmente chiuse dopo verifica hosted. A–E restano chiuse.
Il publisher cerca solo nel manifesto corrente e copia un PNG compatibile
solo quando una figura fallisce; no_data non riusa. I vecchi manifesti E
restano leggibili, ma serve una prima produzione F per disporre del fallback.

La compatibilità confronta figura (esclusi section/wide), query utilizzate,
percorso canonico QC/schema e parametri DETLIN generali/del braccio pertinente.
Il database può acquisire nuove righe senza invalidare il fallback. Percorso
uguale non certifica che il database non sia stato sostituito. Nessuna nuova
configurazione, migrazione o modifica scientifica. Contratto di compatibilità
versione 1: incrementarlo se un futuro renderer cambia significato.

JSON/manifesto v1 aggiungono generated_utc, origin_generation_id,
reused_from_generation_id, compatibility, fallback e conteggio reused.
Generated UTC è la prima produzione dell'immagine, non la data osservativa;
data_utc resta null. Riuso ripetuto conserva l'origine senza seguirne i percorsi.
Nessun limite massimo di età dell'immagine; leggere la data mostrata nel report.

Errore originale conservato, uscita 2 anche se il report viene pubblicato.
Copia fallita degrada a figura failed senza PNG solo se la copia incompleta
è rimossa; rimozione fallita blocca la pubblicazione. PNG F mancanti/danneggiati
sono candidati indisponibili; la verifica dei report esistenti resta strutturale
per questi artefatti, mentre legacy e tutti i nuovi PNG sono verificati.
Gli archivi precedenti danneggiati non vengono riparati. Le protezioni su
marker/manifesto/proprietà/percorsi e le lease restano obbligatorie.

Ogni generazione è autosufficiente, retention E e codici 0/1/2 conservati.
[Contratto F](d3/d3-f.md), [handover](handover.md),
[evidenze](../tests/results/d3-f-validation.md). Nessun D4, push/merge/deploy,
scheduler o rebuild operativo implicito. Le note precedenti restano storiche.


## D3-F e D3 — Chiusura formale, 9 ottobre 2026

**D3-F completata e formalmente chiusa; D3 complessivamente chiusa.**
CI [37986639107](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37986639107),
attempt **1**, sul candidato **`fa9abac024f2f596d482e6385a564801dd1240fe`**.
Pacchetto **1.8.0**, SQLite **schema 1**; D3-A/B/C/D/E restano chiuse.

| Job hosted | Suite con warning come errori | Durata | Wheel / checker isolato |
|---|---|---|---|
| Linux Python 3.11 | 655 PASS, 0 SKIP | 263,35 s | PASS |
| Linux Python 3.12 | 655 PASS, 0 SKIP | 198,40 s | PASS |
| Linux Python 3.13 | 655 PASS, 0 SKIP | 249,40 s | PASS |
| macOS Python 3.12 | 654 PASS, 1 SKIP | 246,71 s | PASS |

Nessun FAIL/XFAIL/XPASS. Skip macOS soltanto per secondo filesystem scrivibile
assente; la stessa prova passa nei tre job Linux. Build wheel 1.8.0 e checker
isolato, incluso riuso/provenienza/uscita 2, verdi nei quattro job. Pip check
verificato localmente; il workflow non lo esegue separatamente.

Commit applicativo **`f416da6be0b50ef50d1c6640be7152610a1210e3`**;
candidato hosted **`fa9abac024f2f596d482e6385a564801dd1240fe`**: differenze
soltanto documentazione/evidenze/QA, verificate. Il successivo commit di
chiusura è documentale e non ha una propria CI attribuita.
**Nessuna verifica D3-F pendente.** Questa nota supera le precedenti indicazioni
di CI F/D3 pendente; le prove locali restano evidenze storiche distinte.

L'utente ha pubblicato il candidato. Questa chiusura modifica soltanto documenti
ed evidenze, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
Ripresa: leggere handover/indice e verificare dev/HEAD/working tree. D3 è chiusa;
**D4 non avviata: pianificazione soltanto su nuova richiesta**, dopo verifica
dello stato effettivo e chiarimento delle decisioni della prossima milestone.

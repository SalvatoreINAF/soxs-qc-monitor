# D2 — Configuration and storage contracts

D2 package 1.2.0; current D3-A package 1.3.0; SQLite schema version 1. D2 is developed on `dev`. D1 remains
formally closed on its previously verified candidate. D2 delivery and current
verification evidence are recorded in [handover](handover.md) and
[test results](../tests/results/d2-validation.md).

## Configuration and discovery

`qc_monitor.config` owns YAML loading, includes, defaults, validation and path
normalization. The functions formerly imported from `qc_monitor.main` remain
available there. `load_config()` returns a validated dictionary with defaults;
`normalize_runtime_config()` resolves paths and validates dictionaries supplied
directly unless its internal `validated=True` option is used. No resource is
created by these functions.

The root for relative operational paths remains `config_path.parent.parent`.
Includes are relative to the main YAML directory, including when `--config`
points outside the checkout. Tilde expansion and canonical path resolution are
applied; environment-variable interpolation inside YAML is not introduced.

Explicit duplicate YAML keys are errors. Local YAML anchors and intentional
`<<` overrides remain valid; anchors do not cross include files. Query names,
figure names and normalized filenames must be unique. Filenames are relative
PNG paths, without parent traversal, backslashes or escape through symlinks.
Filename uniqueness ignores case so configurations work consistently on Linux
and macOS. Types, unknown fields, query references, dataset columns, renderer
parameters, processing (`none`) and series styles are checked before acquisition.
Numeric filters require finite numbers; TEXT filters require strings. A `null`
filter selects missing values, distinct from zero.

Figure parameters are checked by renderer. Bins are positive integers no larger
than 10000; figure dimensions are positive finite numbers no larger than 32 inches
per dimension. DETLIN supports one or four panels for VIS and one for NIR.
Unsupported figure categories cannot silently disappear from the HTML: `arm`
must be VIS/NIR, explicitly or through the retained name/title inference for QC
figures. The shipped 22 figures now declare `arm` and `section`; their ordering
and existing sections are preserved. The 49 redundant `processing: none` blocks
are removed, with identical query behavior.

`last_3_months` is a calendar window ending at the latest timestamp in the
selected dataset, with an inclusive cutoff three calendar months earlier. It is
not a run-age or producer-completion policy. The separate 48-hour supervisor
freshness setting remains unchanged.

Discovery uses the same function in preflight and acquisition. `direct` reads
only `upstream_root/upstream_database_name`; `recursive` selects every matching
DB, including the direct one, sorted and deduplicated by canonical path. Multiple
selected DBs require `allow_multiple_upstream_databases: true`.

Preflight checks upstream columns in read-only connections. An incompatible
upstream schema gives CLI code 2 before creating QC storage or persisting an
independent family. Valid empty sources remain normal; runtime acquisition
failures still leave units open, and public loaders retain their empty DataFrame
contracts. Non-dry-run preflight also verifies the current QC schema. A legacy
archive therefore fails ordinary preflight, while `--preflight --rebuild-db`
allows recognized versions 0/1 without performing a rebuild or backup.

Output files cannot overwrite configuration, includes, selected inputs, storage
sidecars, writer locks or retained backups. QC output may still live below
`reduced_root`. Dry-run and `--no-plots` skip unused publication resources;
structural YAML validation still applies. Configuration/preflight failures do
not save a requested JSON diagnostic file; the log summary remains available.

## SQLite identity and compatibility

Column lists, types, scientific keys and generated DDL live in `schema.py`.
Storage no longer imports acquisition or detector-analysis modules. Existing
column-list imports from those modules remain valid aliases. Writable opening
verifies both `PRAGMA user_version` and the declared tables, indices and
constraints; incidental column migrations are removed. Connection lifetimes are
explicit, and correlated data plus `PROCESSED` advance in one transaction.

| Data | Identity |
|---|---|
| QC | UTC observation, recipe, metric, arm, order, file; missing file is distinct from an empty string |
| DSOL lines | Canonical filepath, order, wavelength, detector x/y |
| DSOL statistics | Canonical filepath and order |
| OLOC model / metadata | Canonical filepath / canonical filepath and order |
| DETLIN measurement | Canonical filepath |
| DETLIN result | Sequence ID, detector mode, exposure time and pair index |
| DETLIN sequence | Arm, UTC-normalized TPL START and TPL ID |

The QC uniqueness index also covers SQL NULL. Equivalent QC rows across sources
are deduplicated; conflicting values for one identity keep the whole day open.
`qc_metric_sources` records all contributing database paths, linked to the
metric ID with deletion cascade. Public QC loaders carry known source provenance
in DataFrame attributes, which the corresponding writer preserves. Rebuild
reconstructs QC provenance from the databases selected for that acquisition;
coverage compares scientific identities independently of the upstream DB location.

`source_file` remains a display basename; file identities use canonical paths.
Moving FITS source trees is not an automatic identity migration. A rebuild whose
prior identities cannot be recovered is refused rather than discarding history.

An unversioned experimental archive is version 0. Ordinary writable opening
refuses it unchanged and requests an explicit rebuild. Dry-run can inspect
legacy/current registers needed for the selected acquisition without upgrading
other tables. Unknown versions are rejected. The pre-existing dry-run WAL
restriction remains: no snapshots, checkpoints or conversion are introduced.

Low-level data writers now use strict INSERT; conflicts raise instead of silently
ignoring rows. They do not certify input completeness or mark a day closed.
Use the family coordinators for scientific acquisition. Public loader return
values and coordinator integer returns remain unchanged.

## DETLIN sequence and geometry contract

Each sequence is identified by a deterministic JSON tuple of arm, normalized
TPL START and TPL ID. Measurements retain NEXP/EXPNO, image dimensions, ROI,
binning and whether binning was assumed. Frame references and the ROI cache use
canonical paths, so equal basenames in different directories do not overwrite
one another. The public compute helper accepts an old basename cache only when
its mapping is unambiguous.

Fits and reference-frame subtraction are independent for each sequence/mode.
Each mode must have consistent image dimensions, binning and ROI. Missing BINX
or BINY assumes 1 for that axis and logs a diagnosis; invalid declared binning
blocks the sequence. ROI bounds remain half-open coordinates in the acquired
image. No binning-dependent ROI conversion, signal normalization or change to
saturation thresholds is introduced. Present invalid exposure times are failures;
an absent time header retains the existing filename fallback.

VIS still requires all four modes, three biases per mode and two flats per time.
NIR requires one dark and two flats per time. Exposure indices must cover the
actual declared NEXP uniquely; no universal total is invented. A required fit
needs at least two usable distinct times. Saturated exposures remain available
when other points provide the fit. Sequences crossing DATE-OBS dates remain
open; the monitor does not introduce an observing-night boundary.

The persistence unit remains day/arm. Every pertinent sequence must be complete
before measurements, results, sequence metadata and registry are replaced in
one transaction. Incomplete acquisition, failed force or SQL error preserves the
previous unit. Missing fits have `fit_state=unavailable`, a reason and null
coefficients/derived values; they never close a unit. Zero pair variance gives
missing conversion factor and electron noise, not artificial zero gain.

`latest` selects one complete sequence per arm by TPL START, with deterministic
sequence-ID tie breaking. `all` draws separate curves and labels per sequence.
OLOC plotting now joins models and metadata by filepath instead of basename.
The standalone remains independent and retains its intentional binning/ROI
normalization differences.

## Writer lease, rebuild and recovery

CLI acquisition, public family coordinators and store writers use a common
canonical-path lease. Nested calls in the same thread are reentrant; another
writer is refused immediately with `WriterBusyError` (CLI 2). The persistent
`<db>.lock` inode uses OS `flock`, also released after process termination.
Do not unlink the lock file to release a lease. Inspection creates no lock.
This is an advisory Linux/macOS mechanism; external SQL tools must be stopped
before maintenance. Update and publication coordination remain D3.

`--rebuild-db` acquires the active archive lease and:

1. Creates and integrity-checks a consistent SQLite backup at
   `<db>.backup-<unique>.sqlite`, including committed WAL content.
2. Acquires all configured inputs into a separate `.<db>.rebuild-<unique>.sqlite`
   on the same filesystem, retaining the ordinary whole-unit transactions.
3. Rejects incomplete acquisition; verifies schema, integrity and foreign keys.
4. Verifies coverage of prior registered units and stored product identities,
   including open experimental data. Numerical values may legitimately change
   during recomputation. Legacy DETLIN fits also require identifiable original
   input pairs; a matching day/mode alone is insufficient.
5. Refuses replacement while active SQLite sidecars remain, closes connections,
   synchronizes the candidate and atomically replaces the active pathname.

Checks and synchronization occur before the atomic rename commit point.
Power-loss durability still depends on the filesystem. A failed rebuild leaves
the prior archive available, retains its backup, removes owned staging on normal
exception paths and does not render from the rejected candidate. Backup retention
is explicitly managed by the operator. Abrupt OS termination can leave an owned
staging file; it is never reused or published automatically.

JSON format remains v1, with additive `storage` metadata and DETLIN sequence
identities. Failed rebuild counters report candidate commits as `staged`, reset
`persisted` and `completed_units`, and retain `staged_units`; they do not claim
the discarded candidate updated the active archive. Successful rebuild counts
refer to the newly published archive.

Restore only with schedulers stopped and all writers/readers closed: preserve
the failed archive, verify the chosen backup, restore it with the matching
software/schema version and rerun inspection. Never rebuild automatically after
an update failure. D2 does not perform production migration, push, merge or D3.

## D3-A additive acquisition contract — 8 October 2026

The D2 scientific identities, day/arm atomicity, public function signatures and
DataFrame/integer return contracts remain unchanged. Batch-only DETLIN calculation
now catches an exception per sequence, discards its computed results and records
sequence/unit/phase/type/reason. The public compute helper still raises calculation
errors. A failed sequence leaves the entire day/arm open; independent units proceed.

SQLite reads and whole acquisition transactions have explicit 5-second connection
timeouts and two additional attempts after 0.25/0.5 seconds for numeric busy/locked
codes only. Rollback and connection closure precede replay; the writer lease stays
held. Wrapped pandas/storage causes are recognized. Rebuild validation/coverage
reads use the same policy; backup/replacement and drop_all are not replayed.

JSON v1 has additive sequence error fields, family source-read retry records and
run-wide `sqlite_operations`; direct stores retain these records on the instance.
Counts advance only after commit, including family totals when a later unit fails.
Exhausted archive reads are not hidden by legacy missing-table fallbacks. See
[operations](operations.md) for the exact diagnostic fields and exit-code behavior,
[D3-A](d3/d3-a.md) and [evidence](../tests/results/d3-a-validation.md) for delivery.
D2 historical results remain unchanged; D3-A is formally closed with its own
hosted evidence, recorded in the linked D3-A results.


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

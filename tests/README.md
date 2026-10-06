# H0 — Regressioni minime delle P0

Suite su `main`, baseline applicativa `96f18e3`. H0 aggiunge test e fixture,
senza correggere il monitor. Le correzioni appartengono a H1 (P0-A) e H2
(P0-B); CI e suite estesa appartengono a D1.

## Esecuzione

Usare Python 3.11–3.13 con le dipendenze scientifiche del progetto e installare
l'extra di test con lo stesso interprete:

```sh
python -m pip install -e '.[test]'
python -m pytest -ra
python -m pytest --runxfail
```

La prima esecuzione deve avere **15 PASS e 17 XFAIL**, senza FAIL o XPASS.
La seconda deve mostrare **17 FAIL e 15 PASS**, con uscita pytest `1`: rende
visibili le violazioni delle P0. Questi conteggi valgono per la baseline H0;
un successo inatteso di una regressione è un errore della suite, perché tutti
i marker sono `xfail(strict=True, raises=AssertionError)`.

Ogni marker indica la P0 e l'invariante violata. In H1/H2, dopo la correzione,
rimuovere soltanto i marker dei casi risolti e verificare nuovamente entrambe
le famiglie. Non aggiornare le aspettative per accettare il difetto attuale.

## Isolamento e contratti delle fixture

`conftest.py` genera un progetto sotto `tmp_path`: YAML autonomo, DB upstream,
DB QC, prodotti ridotti e raw. Nessun test legge il YAML operativo o usa
`data/`, `plots/` o percorsi di produzione. Le configurazioni contengono solo
percorsi assoluti della fixture e consentono esplicitamente i percorsi temporanei
nel preflight. Non si sostituiscono loader, discovery, consolidatori o writer
con mock.

La CLI usa `sys.executable -m qc_monitor.main`, lavora nel progetto temporaneo
e carica il checkout mediante `PYTHONPATH`. Timeout: 60 secondi. `Agg` e una
cache Matplotlib esterna all'albero monitorato sono impostati prima degli import
scientifici; ogni fixture CLI dispone di una cache temporanea separata.
La cache pytest è disabilitata nella configurazione del runner.

I controlli SQL aprono connessioni indipendenti in sola lettura con `mode=ro`,
chiuse esplicitamente. Le istantanee comprendono schema e dati (`iterdump`),
inventario di file/directory, SHA-256 e `mtime_ns` dei file. Non si confronta
`atime`, che può cambiare leggendo un file. Le directory sono confrontate per
presenza, senza dipendere dalla risoluzione dei loro timestamp.

Il caso di migrazione usa uno schema QC esistente con `n_flat_frames` rimossa:
la reinizializzazione attuale la aggiunge anche in dry-run. Le sentinelle
includono una metrica storica e una giornata registrata. I test nominali
preservano il valore di stato attuale `PROCESSED`.

DSOL: due righe nello stesso ordine, coordinate/identità complete e `R_pin`
1000/1200; media attesa 1100 e deviazione standard campionaria `sqrt(20000)`.
OLOC: modello costante `cent_00=2`, HDU 1 dei coefficienti e HDU 2 dei metadati.
DETLIN: ROI 2×2, pattern a media nulla con varianza nonzero, nomi e header IMGNAME
riconosciuti; bias/dark medio 10 e segnale corretto `100 × tempo`. VIS usa due
bias e due flat per tempo per ciascuna delle quattro modalità; NIR usa un dark
e due flat per tempo. Due tempi distinti consentono il fit nominale, mentre
un solo tempo deve lasciare l'unità aperta. Il retry VIS ripara il terzo tempo
SHG con segnale corretto 360, rendendo il nuovo fit diverso dal precedente.
Le tolleranze per fit e statistiche sono `rel=1e-10`, `abs=1e-8`.

Queste cardinalità descrivono esclusivamente i dati sintetici e i requisiti
delle coppie già presenti nel codice. Non stabiliscono un numero universale
di esposizioni di una sequenza reale. La suite non certifica la fine della
riduzione: ordine operativo «riduzione completata → monitor» e indicatore di
fine pipeline restano da verificare in H2. Non si testa l'arrivo di dati nuovi
dopo una chiusura valida.

## Matrice dei casi

| Gruppo | Casi parametrizzati | Attesa H0 |
|---|---:|---|
| Dry-run CLI/API, DB e directory assenti | 2 | XFAIL: creazione DB |
| Dry-run CLI/API, DB esistente con sentinelle e schema attuale | 2 | PASS: dati, schema e file invariati |
| Dry-run CLI/API, schema da aggiornare | 2 | XFAIL: migrazione incidentale |
| CLI dry-run + rebuild, DB assente/presente | 2 | XFAIL: flag accettati ed effetti collaterali; contratto finale uscita 2 |
| Dry-run CLI/API, output assente/presente e figura configurata | 4 | PASS: input e artefatti invariati |
| Consolidamento ordinario CLI/API | 2 | PASS: metrica e registro persistiti |
| Rebuild ordinario CLI | 1 | PASS: sentinelle sostituite dagli input |
| DSOL valido + selezionato corrotto | 1 | XFAIL: chiusura anticipata |
| DSOL retry dopo riparazione | 1 | XFAIL: file riparato saltato |
| DSOL leggibile con R_pin non utilizzabile | 1 | XFAIL: chiusura senza statistiche richieste |
| OLOC senza HDU dei metadati | 1 | XFAIL: chiusura anticipata |
| OLOC retry dopo riparazione HDU | 1 | XFAIL: metadati riparati saltati |
| DETLIN VIS, tutte le modalità ma coppia mancante/illeggibile | 2 | XFAIL: chiusura per sola presenza modalità |
| DETLIN VIS/NIR con fit indisponibile | 2 | XFAIL: chiusura senza fit |
| DETLIN retry con fit diverso | 1 | XFAIL: coefficienti precedenti; anche controllo righe e duplicati |
| QC con due sorgenti dello stesso giorno, discovery ricorsiva senza DB diretto | 1 | XFAIL: seconda sorgente saltata |
| Errore upstream: vista assente e DSOL indipendente valido | 1 | PASS: DataFrame vuoto con schema, QC aperto e DSOL acquisito |
| Nominali QC/DSOL/OLOC/VIS/NIR, secondo avvio e prodotto estraneo | 5 | PASS: solo registro pertinente chiuso, secondo avvio invariato |

Mancata chiusura e recupero sono test separati. Le precondizioni delle fixture
e gli errori CLI inattesi sollevano `RuntimeError`, quindi non possono essere
assorbiti dai marker che ammettono soltanto `AssertionError`. Il caso dei flag
incompatibili ammette come risultato intermedio soltanto 0 (difetto attuale) o
2 (rifiuto richiesto); qualunque altra uscita è un errore dell'harness.

## Evidenze locali del 6 ottobre 2026

Interprete: `/opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python`, Python
3.12.12; NumPy 2.1.0, pandas 2.3.3, PyYAML 6.0.2, Astropy 6.1.2, Matplotlib
3.10.8, pytest 8.4.2. Pytest è stato installato con `--target` in
`/private/tmp/qc-monitor-h0-test-deps`, senza alterare l'ambiente scientifico.
I comandi di verifica effettivi, dalla radice del checkout, sono:

```sh
PYTHONPATH=/private/tmp/qc-monitor-h0-test-deps PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python -m pytest -ra --tb=short
PYTHONPATH=/private/tmp/qc-monitor-h0-test-deps PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python -m pytest --runxfail --tb=short
```

Le directory temporanee non sono risorse necessarie a un clone: l'installazione
ordinaria dell'extra `test` rende disponibili gli stessi comandi senza il
`PYTHONPATH` locale. Nessuna prova riguarda i dati sperimentali dell'utente,
lo standalone, il rendering completo del report o le prestazioni operative.

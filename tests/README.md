# D1 — Verifica batch, scientifica e di installazione

Suite corrente su `dev`: 216 casi (177 di baseline e 39 nuovi D1).
I risultati storici H0/H1/H2 sotto riportati restano evidenze delle rispettive
revisioni; non descrivono il conteggio corrente. La correzione DETLIN `8d44c9d`
aveva già introdotto tre bias VIS e i confronti standalone.

Vedere [handover](../docs/handover.md) per gli esiti D1 e
[guida operativa](../docs/operations.md) per il contratto JSON e i codici 0/1/2.

## Evidenze storiche H0–H2

Suite su `main`: H0 (`314441f`) introduce le fixture e le regressioni sulla
baseline applicativa `96f18e3`; H1 corregge P0-A e aggiunge i casi read-only.
H2 corregge P0-B con unità complete e transazioni; CI e suite estesa appartengono a D1.

## Esecuzione

Usare Python 3.11–3.13 con le dipendenze scientifiche del progetto e installare
l'extra di test con lo stesso interprete:

```sh
python -m pip install -e '.[test]'
python -m pytest -ra
python -m pytest --runxfail
```

La verifica storica dopo H2 aveva **113 PASS**, senza FAIL, XFAIL o
XPASS. I 63 casi H0/H1 rimangono verdi; H2 aggiunge 50 casi di completezza e
recupero. Soltanto la prova H1 dei permessi può essere saltata quando i privilegi
del processo rendono non significativo il controllo.

La baseline H0 aveva 15 PASS e 17 XFAIL; H1 aveva 52 PASS e 11 XFAIL P0-B.
La verifica mirata delle 17 prove di completezza con `--runxfail` ha dato 17
PASS prima della rimozione dei nove marker che coprivano gli 11 casi P0-B.
La suite corrente non ha marker XFAIL: non cambiare le aspettative per accettare
un difetto.

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
la reinizializzazione della baseline H0 la aggiungeva anche in dry-run; H1
ora legge i registri senza migrare il resto dello schema. Le sentinelle
includono una metrica storica e una giornata registrata. I test nominali
preservano il valore di stato attuale `PROCESSED`.

DSOL: due righe nello stesso ordine, coordinate/identità complete e `R_pin`
1000/1200; media attesa 1100 e deviazione standard campionaria `sqrt(20000)`.
OLOC: modello costante `cent_00=2`, HDU 1 dei coefficienti e HDU 2 dei metadati.
DETLIN: ROI 2×2, pattern a media nulla con varianza nonzero, nomi e header IMGNAME
riconosciuti; bias/dark medio 10 e segnale corretto `100 × tempo`. VIS usa ora tre
bias (due nella baseline H2) e due flat per tempo per ciascuna delle quattro modalità; NIR usa un dark
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

## Matrice dei casi H0 dopo H2

| Gruppo | Casi parametrizzati | Attesa dopo H2 |
|---|---:|---|
| Dry-run CLI/API, DB e directory assenti | 2 | PASS: DB e directory non creati |
| Dry-run CLI/API, DB esistente con sentinelle e schema attuale | 2 | PASS: dati, schema e file invariati |
| Dry-run CLI/API, schema da aggiornare | 2 | PASS: nessuna migrazione |
| CLI dry-run + rebuild, DB assente/presente | 2 | PASS: flag rifiutati con uscita 2, senza effetti collaterali |
| Dry-run CLI/API, output assente/presente e figura configurata | 4 | PASS: input e artefatti invariati |
| Consolidamento ordinario CLI/API | 2 | PASS: metrica e registro persistiti |
| Rebuild ordinario CLI | 1 | PASS: sentinelle sostituite dagli input |
| DSOL valido + selezionato corrotto | 1 | PASS: unità aperta senza salvataggio parziale |
| DSOL retry dopo riparazione | 1 | PASS: file riparato acquisito, nessun duplicato |
| DSOL leggibile con R_pin non utilizzabile | 1 | PASS: ordine senza statistiche mantiene aperta l’unità |
| OLOC senza HDU dei metadati | 1 | PASS: unità aperta senza salvataggio parziale |
| OLOC retry dopo riparazione HDU | 1 | PASS: modello e metadati salvati insieme al retry |
| DETLIN VIS, tutte le modalità ma coppia mancante/illeggibile | 2 | PASS: coppia incompleta impedisce la chiusura |
| DETLIN VIS/NIR con fit indisponibile | 2 | PASS: fit indisponibile impedisce la chiusura |
| DETLIN retry con fit diverso | 1 | PASS: intero fit sostituito, righe coerenti e nessun duplicato |
| QC con due sorgenti dello stesso giorno, discovery ricorsiva senza DB diretto | 1 | PASS: sorgenti aggregate prima della chiusura |
| Errore upstream: vista assente e DSOL indipendente valido | 1 | PASS: DataFrame vuoto con schema, QC aperto e DSOL acquisito |
| Nominali QC/DSOL/OLOC/VIS/NIR, secondo avvio e prodotto estraneo | 5 | PASS: solo registro pertinente chiuso, secondo avvio invariato |

Mancata chiusura e recupero sono test separati. Le precondizioni delle fixture
e gli errori CLI inattesi sollevano `RuntimeError`; nella baseline non potevano
essere assorbiti dai marker che ammettevano soltanto `AssertionError`. Il caso dei flag
incompatibili ammette come risultato intermedio soltanto 0 (difetto della baseline H0) o
2 (rifiuto richiesto); qualunque altra uscita è un errore dell'harness.

## Casi aggiuntivi H1

| Contratto | Casi | Attesa |
|---|---:|---|
| CLI/API saltano la giornata già chiusa | 2 | PASS: registro rispettato e file invariati |
| API force + dry-run seleziona la giornata chiusa | 1 | PASS: una riga selezionata senza scritture |
| CLI/API con registro mancante, colonna mancante o QC corrotto | 6 | PASS: diagnosi esplicita con percorso; CLI 2/API ReadOnlyStorageError |
| URI SQLite con spazi, ?, # e % nei percorsi QC/upstream | 2 | PASS: selezione corretta, file invariati |
| Scrittura reale su store read-only | 1 | PASS: SQLite rifiuta il writer, DB invariato |
| Store assente, tutti e quattro i registri | 1 | PASS: insiemi vuoti senza inizializzazione |
| Schema incompatibile per ciascuno dei quattro registri | 4 | PASS: errore esplicito senza migrazione |
| WAL QC/upstream, CLI/API, con/senza sidecar | 8 | PASS: rifiuto prima delle operazioni SQLite, file invariati |
| WAL nella seconda sorgente CLI | 1 | PASS: tutte le sorgenti controllate prima dello store QC |
| Template assente o destinazioni di tipo errato in dry-run | 2 | PASS: output ignorati, preflight ordinario ancora rifiuta |
| DB leggibile e destinazioni non scrivibili | 1 | PASS: dry-run possibile, preflight ordinario rifiuta |
| Input di acquisizione assente | 1 | PASS: preflight dry-run e CLI rifiutano senza scritture |
| Flag incompatibili e configurazione assente | 1 | PASS: errore argparse prima del caricamento config |

La modalità `SQLiteStore(..., read_only=True)` non crea directory o database.
Soltanto l'assenza del DB equivale a un registro vuoto; DB presenti con registri
richiesti incompatibili generano `ReadOnlyStorageError`. I DB WAL sono rifiutati
nel dry-run tramite ispezione del solo header: non si usa `immutable=1`, non si
eseguono checkpoint o conversioni e non si aprono copie temporanee. Nei test
WAL con sidecar un writer controllato resta aperto durante il confronto;
quando i sidecar sono assenti, il writer viene chiuso prima della prova.

## Casi aggiuntivi H2

| Contratto | Casi | Attesa |
|---|---:|---|
| QC invalido: valore non numerico/non finito, braccio o identificativi vuoti | 5 | Nessuna chiusura; dopo riparazione una riga e registro corretto |
| Duplicati QC con identità nullable, equivalenti o conflittuali | 2 | Una riga deduplicata oppure unità aperta |
| Sorgente QC vuota valida versus vista fallita, DSOL indipendente | 2 | Esiti interni distinti; solo il fallimento blocca QC |
| API multisorgente: membership, aggregazione e secondo avvio | 1 | Percorso estraneo respinto prima delle scritture; entrambe le sorgenti salvate |
| API multisorgente dry-run con seconda sorgente WAL | 1 | Rifiuto prima dello store QC, file invariati |
| DSOL: ordine inutilizzabile oppure campioni individuali scartati | 2 | Tutti gli ordini presenti devono avere statistiche; n_points=1 ammesso |
| OLOC: coefficienti, geometria, metadati vuoti o gradi mancanti | 4 | Unità aperta senza salvataggio parziale |
| DETLIN: header mancanti/vuoti, indice duplicato, conteggio incoerente/non numerico, più date o pixel non finiti | 10 | Unità aperta senza risultati persistiti |
| Più sequenze DETLIN nella stessa giornata | 1 | Ambiguità respinta senza mescolare misure/fit |
| NIR con flat mancante | 1 | Coppia incompleta impedisce la chiusura |
| Esposizione satura con altri tempi utilizzabili | 1 | Esposizione conservata con fit_used=0, fit complessivo valido |
| Acquisizione forzata incompleta delle quattro famiglie | 4 | Dati e registro precedenti invariati |
| Dati parziali sperimentali delle quattro famiglie e retry | 4 | Tentativo incompleto non modifica; completo sostituisce e chiude |
| Trigger SQL fallisce durante la registrazione, quattro famiglie | 4 | Rollback di dati, registro e sqlite_sequence; retry successivo possibile |
| QC con una giornata valida e un’altra invalida | 1 | Chiusura indipendente della giornata valida |
| Nome DSOL selezionato malformato | 1 | Fallimento esplicito senza crash di parsing o chiusura |
| Dry-run su unità incompleta | 1 | Stessa validazione, nessuna scrittura |
| Dark NIR senza flat con conteggio header coerente | 1 | Conteggio da solo insufficiente, unità aperta |
| Sorgente QC vuota/fallita e registro non utilizzato assente | 2 | API ritorna zero senza errore artificiale o migrazione |
| Geometria OLOC numerica rappresentata come testo | 1 | Confronto numerico dei limiti, range invalido respinto |
| NEXP dichiarato enorme | 1 | Diagnosi di incompletezza senza allocare un intervallo enorme |

H2 salva solo unità complete. `test_unit_recovery.py` usa trigger SQLite reali
per i guasti SQL; non sostituisce writer, connessioni o loader con mock. I test
di force verificano anche la conservazione del vecchio registro chiuso; quelli
di retry eliminano deliberatamente il registro per simulare dati sperimentali
rimasti aperti. I nuovi casi esercitano la stessa acquisizione e le stesse
transazioni utilizzate dai coordinatori.

Le fixture DETLIN H2 avevano TPL START/ID coerenti e NEXP/EXPNO assegnati
all'inventario sintetico. La riparazione di un frame mantiene i suoi identificativi;
le cardinalità descrivono la fixture, non un conteggio universale del produttore.

## Ambiente ed evidenze H0/H1 del 6 ottobre 2026

Interprete: `/opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python`, Python
3.12.12; NumPy 2.1.0, pandas 2.3.3, PyYAML 6.0.2, Astropy 6.1.2, Matplotlib
3.10.8, pytest 8.4.2. Pytest è stato installato con `--target` in
`/private/tmp/qc-monitor-h0-test-deps`, senza alterare l'ambiente scientifico.
I comandi di verifica effettivi, dalla radice del checkout, sono:

```sh
PYTHONPATH=/private/tmp/qc-monitor-h0-test-deps PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python -m pytest -ra --tb=short
PYTHONPATH=/private/tmp/qc-monitor-h0-test-deps PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python -m pytest --runxfail --tb=short
```

H1 usa gli stessi due comandi e lo stesso ambiente di H0. La verifica mirata
`python -m pytest tests/test_dry_run.py --runxfail -q --tb=short` ha confermato
15 PASS prima della rimozione dei marker P0-A.

Verifica finale H1: **52 PASS, 11 XFAIL**, uscita 0, in 294,08 secondi;
con `--runxfail`: **11 FAIL P0-B, 52 PASS**, uscita 1, in 289,41 secondi.
I 31 casi aggiuntivi H1 sono passati anche nell'esecuzione mirata (172,65
secondi), senza skip. Queste durate misurano la suite sintetica, non il batch
operativo. Nessun errore di fixture, import o subprocess.

Le directory temporanee non sono risorse necessarie a un clone: l'installazione
ordinaria dell'extra `test` rende disponibili gli stessi comandi senza il
`PYTHONPATH` locale. Nessuna prova riguarda i dati sperimentali dell'utente,
lo standalone, il rendering completo del report o le prestazioni operative.


## Evidenze H2

Verifica iniziale delle regressioni: `python -m pytest tests/test_completeness.py
--runxfail -q --tb=short`, **17 PASS** in 35,31 secondi prima della rimozione
dei marker P0-B. Verifica mirata finale di `test_unit_recovery.py`: **50 PASS**
in 75,07 secondi. La matrice sopra descrive tutti i nuovi casi.

Le verifiche complete finali, con gli stessi prefissi di ambiente documentati
per H0/H1, sono:

```sh
PYTHONPATH=/private/tmp/qc-monitor-h0-test-deps PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python -m pytest -ra --tb=short
PYTHONPATH=/private/tmp/qc-monitor-h0-test-deps PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/Caskroom/miniforge/base/envs/qc/bin/python -m pytest --runxfail --tb=short
```

Entrambe: **113 PASS**, uscita 0, 591,30 secondi, senza FAIL, XFAIL, XPASS,
warning o skip. Le esecuzioni sono indipendenti e hanno usato directory
temporanee separate. Le durate riflettono la suite e i subprocess scientifici
concorrenti; non sono un benchmark del monitor operativo.

Nessun dato operativo è stato usato come destinazione dei test. Nessuna
ricostruzione degli archivi sperimentali o modifica al codice standalone.


## D1 — Matrice aggiuntiva

| Gruppo | Casi | Verifica |
|---|---:|---|
| Riepilogo e acquisizione | 17 | JSON/file identici, UUID, UTC, conteggi, retry, deduplicazione, esiti 0/1/2, dry-run/preflight invariati, SQL lock reale, rollback, collisioni e configurazione malformata |
| Scientificità, configurazione e rendering | 8 | Polinomio analitico, media/std DSOL, soglia esatta e fit, include duplicati, query assente, tutti i renderer, 12 riferimenti HTML, dati vuoti ed errore di salvataggio reale, standalone default/override |
| Wrapper e supervisione | 14 | tcsh reale, interprete richiesto, percorsi con spazi, codici, timeout di un processo reale, retention sicura, ultimo tentativo e freschezza, errore supervisore dominante |

Nessun nuovo XFAIL. I due test CLI legacy di sorgente QC fallita attendono ora 1;
i test API conservano gli interi precedenti e gli invarianti di storage.
Le simulazioni dello script update riguardano solo il dispatch del wrapper:
nessun pull o aggiornamento reale viene eseguito durante la suite.

### Ambiente pulito

```sh
python3.12 -m venv /tmp/qc-reference
/tmp/qc-reference/bin/python -m pip install -c requirements/reference-py312.txt '.[test]' build setuptools wheel
PYTHONDONTWRITEBYTECODE=1 /tmp/qc-reference/bin/python -m pytest -ra --tb=short
/tmp/qc-reference/bin/python -m build --wheel --no-isolation --outdir /tmp/qc-wheel
```

Usare un secondo ambiente per installare la wheel e verificare:

```sh
/path/to/installed-env/bin/python scripts/check_installation.py
```

La CI esegue questi controlli su Linux 3.11/3.12/3.13 e macOS 3.12. `tcsh` è
necessario anche localmente. `Agg`, cache Matplotlib e cache Fontconfig/XDG
sono impostate in directory temporanee prima degli import scientifici.
I test non dipendono dal vecchio percorso `/private/tmp/qc-monitor-h0-test-deps`.

La [tavola di controllo visivo](../docs/qa/d1-reference.png) mostra i dodici
grafici sintetici ispezionati; non è una golden image pixel per pixel.
Lo smoke HTML usa il layout standard. Il difetto sui riferimenti fuori da
`plots/` e sulle immagini mancanti/stale rimane esplicitamente rinviato a D3.

La baseline scientifica è analitica: polinomio `1+2y+3o+4oy`, fit `10t+5`,
media DSOL 1100 e deviazione campionaria `sqrt(20000)`. Tolleranze dove
pertinente `rel=1e-10`, `abs=1e-8`; nessuna certificazione di dati operativi.


### Esito finale D1 — 8 ottobre 2026

Sul codice candidato `7732ddb`: **216 PASS in 483,91 s**, Python 3.12.15
e ambiente fissato. Nessun FAIL/XFAIL/XPASS, warning o skip. Wheel e compatibilità
macOS 3.11/3.13 verificate come descritto nei
[risultati completi](results/d1-validation.md). La matrice hosted sul successivo
candidato `fb37d9e` è verde: **216 PASS in ciascuno dei quattro job**, wheel e
installazione isolata verificate. [Run 37772436524](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37772436524).
**D1 completato e formalmente chiuso.** Non avviare D2 senza una nuova richiesta.

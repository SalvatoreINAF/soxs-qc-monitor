# Verifica batch, scientifica e di installazione

Suite corrente su `dev`: **655 casi**, D3-F implementata localmente (1.8.0/schema 1),
chiusura hosted F/D3 pendente. D3-E resta formalmente chiusa sul suo candidato. D3-D formalmente chiusa.
D3-A/B/C restano formalmente chiuse. Il caso su due filesystem può essere
saltato quando il runner non dispone di un secondo dispositivo scrivibile.
La consegna D1 storica aveva 216 casi (177 di baseline e 39 nuovi D1).
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


## D2 — Contratti aggiuntivi

`test_d2_config.py` verifica YAML/ancore/duplicati, tipi dei filtri, query e
renderer, ROI, limiti delle figure, percorsi relativi e collisioni, output non
utilizzati, discovery diretta/ricorsiva e invarianza prima delle scritture.
`test_d2_storage.py` verifica identità SQL nullable, provenienza QC, omonimie
DSOL/OLOC, schema/versioni, lock fra processi e rilascio dopo terminazione,
rebuild/backup/coverage/sidecar WAL e contatori di candidati scartati.
`test_d2_detlin.py` verifica sequenze VIS/NIR separate, retry/force atomici,
geometria e binning, fit mancanti, gain indefinito, selezione latest/all e
rollback dei metadati di sequenza.

Aspettative intenzionalmente aggiornate: schema upstream incompatibile bloccato
in preflight con codice 2, più sequenze accettate senza mescolare i fit, rebuild
incapace di eliminare storico non recuperabile. I loader e le API delle famiglie
indipendenti conservano il comportamento tollerante ai guasti; nessun XFAIL
aggiunto e nessuna tolleranza scientifica allargata.

Ogni cache CLI rimane temporanea e separata dal progetto monitorato. La fixture
copia l’inventario font creato nella cache temporanea di collection, evitando una
nuova scansione dei font di sistema per ogni caso. Nessuna cache dell’utente o
cache generata su altre macchine viene riutilizzata. Le durate della suite non
sono benchmark del batch operativo.

Eseguire la suite con warning trattati come errori:

```sh
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
```

Il checker della wheel comprende ora validazione anticipata, dry-run immutabile
e rebuild protetto, oltre a entry point, risorsa template e idempotenza.
La [tavola D2](../docs/qa/d2-reference.png) documenta i grafici VIS latest/all
con due pendenze distinte; non è una golden image. Evidenze e stato di chiusura
sono in [risultati D2](results/d2-validation.md) e [handover](../docs/handover.md).
La CI rimane Linux 3.11/3.12/3.13 e macOS 3.12; un risultato locale non prova
un’esecuzione hosted né Linux.

**D2 completato e formalmente chiuso l’8 ottobre 2026.**
[Matrice hosted](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37793731551), attempt 1, sul commit `9f666b0`:
315 PASS per ciascuno dei quattro job, wheel e installazione isolata riuscite.
Nessuna verifica D2 pendente; non avviare D3 senza nuova richiesta.


## D3-0 — Documentazione per le prossime verifiche

D3-0 è una consegna solo documentale: [risultati](results/d3-0-validation.md).
L’[indice D3](../docs/d3-roadmap.md) collega le sei schede con test e criteri
previsti per ciascuna milestone applicativa. Questi test sono pianificati,
non già implementati o eseguiti. Le evidenze storiche D1/D2 restano distinte.
Ripresa corrente: D3-A chiusa; D3-B locale, verifica hosted pendente,
secondo l’[handover](../docs/handover.md).

## D3-A — Acquisizione resiliente

Suite alla consegna D3-A: **363 casi**, i 315 D2 più 48 di `test_d3a_resilience.py`.
I conteggi nelle sezioni storiche restano riferiti alle rispettive consegne.
Le nuove prove verificano isolamento fit VIS/NIR per sequenza, atomicità
giorno/braccio, force/recovery/idempotenza, nomi malformati e prosecuzione
famiglie; contesa SQLite di un processo esterno con rilascio sincronizzato,
letture/preflight/init/rebuild, rollback di scrittura e di commit, cause numeriche
avvolte da pandas, errori permanenti, contatori dopo trigger SQL su una seconda
unità, JSON e codici CLI 0/1/2. Nessun input/output operativo è usato.

Un test usa timeout/attese reali (5 s, 0,25/0,5 s, circa 15,75 s per blocco
persistente). Gli altri casi di contesa riducono solo il timeout nelle fixture,
registrando le attese programmate: nessuna impostazione produttiva modificata.
Il processo esterno usa stdin/stdout per segnalare il lock e il rilascio;
non dipende da un ritardo presunto per acquisire il lock. Le prove numeriche
mantengono le tolleranze D2, senza XFAIL o confronti pixel introdotti.

```sh
python -m pytest tests/test_d3a_resilience.py -ra --tb=short -W error
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-d3a-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
/path/to/installed-env/bin/python -m pip check
```

Installare la wheel 1.3.0 in un ambiente separato; il checker usa processi -I
fuori checkout e verifica entry point, template, idempotenza, dry-run, config e
rebuild. Il nuovo modulo interno deve essere incluso nella wheel. Riferimento
Python 3.12 fissato; compatibilità 3.11/3.13, matrice hosted Linux/macOS invariata.

[Evidenze D3-A](results/d3-a-validation.md): chiusura formale completata con
[CI 37807882167](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37807882167), attempt 1, sullo SHA
`be8b3d5202716679de7f46cf73ea984127e3aa8e`. Linux 3.11/3.12/3.13 e macOS 3.12:
363 PASS ciascuno, build/installazione isolata verdi. Nessuna verifica D3-A
pendente; D3-B consegnata localmente, CI pendente.


## D3-B — Coordinamento operativo (1.4.0, schema 1)

Suite alla consegna iniziale: **400 casi**, inclusi 37 nuovi test D3-B. **400 PASS** per
macOS Python 3.11.17/3.12.15/3.13.16 con `-W error`; wheel/checker/pip check
verificati in tre nuovi venv. [Evidenze](results/d3-b-validation.md).

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
Vedere [scheda D3-B](../docs/d3/d3-b.md).
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

## D3-C — Verifiche pianificate, 9 ottobre 2026

**Sviluppo e test D3-C non ancora implementati.** Il
[piano](../docs/d3/d3-c.md) contiene matrice di accettazione e comandi previsti;
creare `test_d3c_rendering.py`, verificare tutti i dieci renderer, dati vuoti
versus invalidi, errori lettura/save, cleanup e figure del chiamante, immagini
legacy, API compatibili, HTML/template/JSON e codici 0/1/2. La prova Agg va
eseguita in subprocess senza ereditare MPLBACKEND da pytest/CI. Verificare
le lease durante report parziale e l'assenza di scritture nelle modalità ispettive.

Audit della pianificazione sul codice corrente: **82 PASS / 81,80 s**, macOS
Python 3.12.15, `-W error`; [evidenze](results/d3-c-planning.md). Non sostituisce
suite completa, wheel o CI del futuro codice C. Prevedere regressioni locali
3.11/3.12/3.13 in sequenza, wheel in nuovi ambienti, checker/pip check e QA
nominale/parziale; formalmente chiudere con CI Linux 3.11/3.12/3.13 e macOS 3.12
sul candidato esatto. Salvare risultati effettivi in `results/d3-c-validation.md`
e ambiente/QA in docs/qa alla consegna. D3-B resta chiusa, 405 casi storici;
le sezioni precedenti di CI pendente sono superate dalla chiusura registrata.

## D3-C — Suite e consegna locale (1.5.0, schema 1)

**490 casi**, 405 precedenti più 85 C. Tutti PASS su Python 3.11/3.12/3.13
macOS, warning come errori, nessuno skip/XFAIL. [Evidenze](results/d3-c-validation.md),
[ambiente](../docs/qa/d3-c-environments.json), [handover](../docs/handover.md).
CI hosted ancora pendente: non attribuire le prove D3-B al codice C.

```sh
python -m pytest tests/test_d3c_rendering.py -ra --tb=short -W error
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-d3c-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
/path/to/installed-env/bin/python -m pip check
python scripts/render_d3c_qa.py /tmp/qc-d3c-visual
```

Suite in sequenza per le lease D3-B; il sandbox deve consentire ps ai test dei
timeout reali. Non trasformare una restrizione del runner in skip o modificare
il supervisore per nasconderla. Backend provato in subprocess senza Agg
preimpostato; salvataggi falliti su filesystem reale; cleanup preserva figure
preesistenti. I test D3-B di pubblicazione configurano ora vere figure.

Checker wheel esteso per il modulo degli esiti, report parziale e Agg autonomo;
installazioni nuove e isolate per i tre interpreti. QA ripetibile con i dati dei
test, non con archivi operativi. [Tavola](../docs/qa/d3-c-reference.png) e
[screenshot NIR](../docs/qa/d3-c-report-nir.png) ispezionati; nessuna golden image.
Fermarsi a C: dopo pubblicazione autorizzata, verificare solo la chiusura hosted.

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


## D3-D — Atomic publisher (1.6.0, schema 1)

`test_d3d_publication.py` exercises generations/manifest/HTML, each sync boundary,
real readable PNGs, absent/failed images, precommit faults, postcommit sync errors,
owned cleanup, path/URL escaping, symlinks/hardlinks/FIFO, template contamination,
collisions and invalid ownership. Real child processes verify operation contention,
SIGKILL orphans and lease release. The ordinary CLI must keep direct publication
and summary publication.state=skipped. No scientific tolerance changes.

```sh
python -m pytest tests/test_d3d_publication.py -ra --tb=short -W error
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-d3d-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
/path/to/installed-env/bin/python -m pip check
python scripts/render_d3d_qa.py /tmp/qc-d3d-visual
```

Run source suites sequentially for B's exclusive environment/source tests.
The runner must allow ps for real timeout checks; environmental denial is a
failed attempt to record, not grounds to skip or relax the existing tests.
The real two-filesystem case uses a second writable device (e.g. /dev/shm on
Linux); it explicitly skips if absent, alongside an always-run invariant check
that both rename endpoints use the same device. Record this skip separately.
The isolated wheel checker verifies the installed publisher with a real
renderer and a failed callback preserving the previous publication.

Visual QA uses real scientific rendering and a real save failure in synthetic
staging. Inspect nominal, partial/current and archived reports; no pixel golden
images. Results/versions/limits in [D3-D validation](results/d3-d-validation.md)
and [environment manifest](../docs/qa/d3-d-environments.json). Hosted Linux
3.11/3.12/3.13 and macOS 3.12 passed on the exact D candidate; see the closure below.
**Stop at D3-D: D3-E/F are not started.**


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


## D3-E — Retention e CLI atomica

60 nuovi casi in test_d3e_retention.py, con dati temporanei: conservazione N=2/4,
variazione di N, storia/HTML/PNG, orfani per età/numero/spareggio/zero, SIGKILL
in tre fasi, contese reali durante cleanup, permessi reali, marker/link/estranei,
collisioni UUID e destinazioni, summary anche attraverso symlink, fsync cleanup,
DB acquisito prima del fallimento cleanup, modalità senza effetti grafici.
I casi C/D mantengono gli stessi contratti funzionali ma usano lo staging nuovo
per provocare save failure; non creare ostacoli nei percorsi PNG legacy.

```sh
python -m pytest tests/test_d3e_retention.py tests/test_d3d_publication.py tests/test_d3c_rendering.py -ra --tb=short -W error
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-d3e-wheel
/path/to/isolated-env/bin/python scripts/check_installation.py
/path/to/isolated-env/bin/python -m pip check
python scripts/render_d3e_qa.py /tmp/qc-d3e-qa
```

Per la suite completa il runner deve consentire ps e gestione dei gruppi di
processi: il sandbox Codex può bloccare ps e richiedere esecuzione autorizzata
fuori sandbox. Non cambiare test/aspettative per mascherare tale limite.
Linux non privilegiato per verificare i permessi; due filesystem reali quando
disponibili, altrimenti skip motivato. Il checker wheel usa import isolati,
CLI senza figure e con rendering parziale, Agg e pubblicazioni ripetute/retention.

Chiusura formale soltanto con matrice hosted verde sul candidato E esatto;
non attribuire CI D3-D al nuovo codice. Evidenze: tests/results/d3-e-validation.md,
ambiente/hash/QA: docs/qa/d3-e-environments.json. D3-F non avviata.


Commit applicativo D3-E **`c48380dddaa33d48d2b66db4380bd454f0f7782b`**; consegna locale verificata,
CI E pendente sul candidato esatto. [Evidenze](results/d3-e-validation.md).


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


## D3-F — Riuso e collaudo integrato

46 nuovi casi in `test_d3f_reuse.py`: contratto per figura, query/database/DETLIN,
metadati mancanti/legacy, PNG mancanti/corrotti/symlink/hardlink, no_data,
provenienza immutata dopo retention, guasti copia/rimozione/manifesto/HTML/sync,
cleanup finale, interruzione e contesa durante copia/finalizzazione. CLI reale
verifica il ciclo incompleto/errore/riparazione/retry/chiusura/idempotenza e rebuild
sintetico; le regressioni B verificano update fallito e rilascio dei processi.

I casi legacy di D/E ora costruiscono esplicitamente un manifesto pre-F,
aggiornando correttamente il marker: mantengono il rifiuto dei PNG legacy
danneggiati. F può invece pubblicare senza immagine se un candidato F è
illeggibile, preservando i controlli di struttura/proprietà e dei nuovi PNG.

```sh
python -m pytest tests/test_d3f_reuse.py -ra --tb=short -W error
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /private/tmp/qc-d3f-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
/path/to/installed-env/bin/python -m pip check
python scripts/render_d3f_qa.py /private/tmp/qc-d3f-qa
```

Checker isolato esteso con reale errore di save, riuso/provenienza e uscita 2.
Evidenze/ambienti in `tests/results/d3-f-validation.md` e
`docs/qa/d3-f-environments.json`. Non attribuire la CI E al nuovo F.
La chiusura richiede Linux 3.11/3.12/3.13 e macOS 3.12 sul candidato esatto.

# D4 — Validazione e consegna locale, 9 ottobre 2026

**D4 consegnata e verificata localmente, 1.9.0/schema 1; CI D4 pendente.**
Baseline `ddf67a85793e8dd64bbac19fe29e7a84634b89f0`, dev pulito inizialmente.
[Piano e audit](d4-planning.md), [contratto](../../docs/d4.md).

## Cambiamenti

Helper privati per INSERT/registri senza commit autonomi; conversione a float finito
con wrapper equivalenti; traversal comune DSOL/OLOC. Preflight, runtime e
consolidamento estratti con import compatibili. Plotting diviso per famiglia,
registro statico con adattatori lazy, finalizzazione condivisa e selezione DSOL
latest/all comune. OLOC/DETLIN mantengono le proprie selezioni. Tipi pubblici
PlotSeries/InvalidPlotData conservano identità serializzabile. Processing vuoto
conservato; calcolo HTML inutilizzato eliminato. Nessuna opzione o schema nuovo.

49 nuovi test D4. Solo punti di iniezione guasti/timeout adattati nei test D2/C/A;
fixture scientifiche e tolleranze numeriche invariate.

## Verifiche intermedie

- Storage/completa-ripara-retry: 92 PASS / 29,91 s, Python 3.12.15, -W error.
- Rendering/read-only/DETLIN: 140 PASS, 1 FAIL / 61,44 s. Il helper registri quotava
  una colonna SELECT mancante che SQLite accettava come stringa; corretta la
  selezione dei nomi fissi. Ripetizione casi coinvolti: 8 PASS / 11,86 s.
- D4 mirato finale: 49 PASS / 14,35 s, -W error. Firme originali importabili e
  dati degli artisti equivalenti ai dieci renderer della baseline; i dieci PNG
  prodotti nello stesso ambiente sono identici byte per byte.
- D3-A: 48 PASS nell’esecuzione intermedia, insieme a 39 casi D4 allora verdi.
  Tre fixture nuove avevano una query di provenienza con nome colonna errato,
  corretta a source_path. Altri tentativi intermedi avevano catture mancanti,
  selezione di una colonna SQL TEXT come numerica e formattazione import non valida;
  corretti prima della suite finale, senza cambiare aspettative scientifiche.
- Prima cattura QA baseline intercettava un modulo editable del checkout nuovo:
  scelta esplicita del helper soltanto se presente nel checkout di origine; gli
  scalari NumPy degli artisti sono serializzati con item(). Catture ricreate dalla
  baseline originale, non dal codice D4.
- Tre suite complete lanciate contemporaneamente interferivano nelle lease di
  aggiornamento del medesimo sorgente. Interrotte; non sono evidenza finale verde.
  Le esecuzioni finali vengono svolte sequenzialmente, senza modificare i test.

Esiti finali, installazione, ambienti e QA sono registrati sotto.
Nessun D5, push/merge/deploy, scheduler o rebuild operativo.

## Equivalenza, packaging e QA

Confronto reale CLI/SQL con sorgenti baseline separati, stesso interprete 3.12:
nominale → nuovo giorno DSOL incompleto → reale save fallito con riuso → riparazione
→ retry → run idempotente → dry-run → rebuild. Tutti e sette i passaggi equivalenti:
contenuti delle tabelle ordinati, path di provenienza normalizzati per progetto,
processed_at escluso perché orario di esecuzione, contatori/stati/esiti identici;
integrity_check e foreign_key_check indipendenti. Tutti gli input/output sono
sintetici e temporanei. [Sintesi confronto](../../docs/qa/d4-equivalence.json).
La prima fixture aggiungeva un FITS allo stesso giorno già chiuso: corretto il
nuovo input a un giorno distinto, conservando la politica di skip delle unità chiuse.

[Audit del codice](../../docs/qa/d4-code-audit.json): schema, intero modulo DETLIN,
bootstrap, lock/coordinamento, retry, rebuild, pubblicazione, esiti/riepilogo e
HTML template invariati byte per byte; loader/formule di acquisizione e helper
scientifici/di selezione OLOC/DETLIN invariati nell’AST. Tutti i moduli/risorse
nella wheel corrispondono al checkout byte per byte. Versione 1.9.0/schema 1.

Checker installato esteso a import/firme e presenza di tutti i moduli privati,
con import -I fuori checkout. Due vecchie aspettative 1.8.0 aggiornate a 1.9.0.
Python 3.13 sposta l’implementazione delle stesse classi pubbliche pathlib in
pathlib._local: normalizzato soltanto questo prefisso nei confronti delle firme.
La cattura API della baseline originale su 3.13 conferma che è l’unica differenza;
nessun parametro, default o annotazione di dominio cambia.

QA generata con scripts/render_d4_qa.py: tavola dei dieci renderer e report
nominale/parziale/riusato/archiviato. Screenshot headless con profili temporanei;
prima acquisizione incompleta/timeout, ripetuta con attesa del compositor.
Nessun dato operativo modificato. La verifica PNG byte-identici è aggiuntiva,
mentre accettazione scientifica usa valori numerici e dati rappresentati.

QA finale verificata dopo decode delle immagini e due frame del compositor,
tramite DevTools localhost e profilo headless temporaneo. Tutti i quattro
screenshot RGB 1440×1500 sono completi; corrente riusato e archivio riusato
identici byte per byte. Tavola dei dieci renderer e report nominale/parziale/
riusato/archiviato ispezionati; percorsi relativi con Unicode/spazi/caratteri speciali
validi. Failed/no_data privi di immagini, riuso con data UTC originale ed errore.

Un ulteriore test mirato 3.12 sovrapposto alla prima suite sequenziale 3.11 ha
causato contese sul sorgente (12 casi mirati falliti e una prova B nella suite).
Quella suite è stata interrotta e ripetuta da zero, insieme a 3.13, senza altre
verifiche applicative concorrenti. Nessuna modifica al codice di coordinamento
né alle aspettative dei test; registrare soltanto le ultime suite complete verdi.

## Riproduzione delle prove finali

```sh
PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d4-final312.xml
PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d4-isolated311.xml
PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d4-isolated313.xml
/private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d4-wheel
/private/tmp/qc-d3d-installed312/bin/python scripts/check_installation.py
/private/tmp/qc-d3d-installed312/bin/python -m pip check
/private/tmp/qc-d1-reference/bin/python scripts/render_d4_qa.py /private/tmp/qc-d4-qa
python3 scripts/capture_d4_reports.py /private/tmp/qc-d4-qa docs/qa
```

Eseguire suite/API sul checkout una per volta. Per confrontare la baseline,
esportare lo SHA con git archive in una nuova directory temporanea e usare
scripts/check_d4_equivalence.py e scripts/capture_d4_rendering.py con output
nuovi: le fixture API/artisti sono riferimenti pre-D4 e non vanno rigenerate
per far passare il codice corrente. Checker/pip check ripetuti anche negli
ambienti installati isolati 3.11 e 3.13. Cache/font/config/input/output di prova
sono temporanei; QA esportata sotto docs/qa. Chrome richiesto solo dalla cattura
visiva macOS, non dal pacchetto o dalla suite.

## Limiti e chiusura

Nessuna accettazione su strumenti reali o misura di prestazioni operative.
Filesystem/permessi Linux e matrice hosted restano da verificare sul candidato
esatto. Conservare i limiti D3 su hosting/browser, sorgenti incomplete, sequenze
su più date e completamento della riduzione. Nessuna modifica scheduler/deploy,
nessuna rielaborazione dei dati dell’utente. D4 non introduce ottimizzazioni D5.
Stima approvata 28–40 ore incluse verifiche/handover, attese CI escluse; non
consuntivo. Fermata a D4. Pubblicazione del candidato soltanto su richiesta.

## Esiti finali e scheda sintetica D4

**Consegna locale completata; CI hosted D4 pendente.**
49 nuovi casi, 704 complessivi, versione 1.9.0/schema 1.

| macOS 15.8 ARM64 | Suite con -W error | Durata pytest | Wheel/checker/pip check |
|---|---|---|---|
| Python 3.12.15 | 703 PASS, 1 SKIP | 232,65 s | PASS |
| Python 3.11.17 | 703 PASS, 1 SKIP | 202,88 s | PASS |
| Python 3.13.16 | 703 PASS, 1 SKIP | 225,95 s | PASS |

Nessun FAIL/XFAIL/XPASS finale. Skip solo secondo filesystem scrivibile assente
sul Mac; non sostituisce le future prove Linux. Tempi/ambienti/hash e differenze
fra durata JUnit/pytest in [manifesto](../../docs/qa/d4-environments.json).
Suite 3.12 prima della sola normalizzazione pathlib nel confronto di firme;
moduli applicativi finali identici, D4 mirato 3.12 ripetuto sul test finale.
Suite 3.11/3.13 comprendono tale normalizzazione, confermata sulla baseline 3.13.
Wheel finale contiene tutti i moduli estratti, identici a checkout e installazioni
isolate. Checker esteso e pip check PASS nei tre ambienti, fuori checkout con -I.

[Nominale](../../docs/qa/d4-report-nominal.png),
[parziale](../../docs/qa/d4-report-partial.png),
[riusata](../../docs/qa/d4-report-reused.png),
[archiviata](../../docs/qa/d4-report-archive.png),
[tavola renderer](../../docs/qa/d4-reference.png) ispezionati.
Equivalenza di sette scenari CLI/SQL e di dati/PNG dei dieci renderer PASS.
Parsing sorgenti, link documentali, diff check e audit confini modifiche PASS.

Scheda, README, contratti/procedure, indice, test/evidenze/ambienti e handover
aggiornati; entrambi i reference_docs aggiornati localmente e ignorati da Git.
Commit applicativo locale registrato nel manifesto e nell’handover; successivo
commit documentale registra la consegna. Nessun candidato D4 pubblicato/verificato
hosted e nessuna CI D3 attribuita a D4.

Ripresa: controllare dev/HEAD/working tree e leggere handover/scheda/evidenze.
Pubblicare soltanto su richiesta; verificare matrice sullo SHA esatto prima
della chiusura formale. **Fermata a D4; nessun D5 o intervento operativo.**

Commit applicativo locale **`2cbbdb93500898730e4f32e1c3c21ceafa88602a`**.
Il commit documentale successivo registra evidenze/handover; candidato hosted
non ancora pubblicato. D4 mirato finale sul test aggiornato: **49 PASS / 13,85 s**.
Wheel ricostruita con README finale, moduli Python/template identici alla prima
wheel verificata; installazioni e checker finali ripetuti sui tre interpreti.

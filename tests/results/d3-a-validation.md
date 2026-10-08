# D3-A — Verifica e chiusura formale, 8 ottobre 2026

**D3-A completata e formalmente chiusa su `dev` l’8 ottobre 2026.** Pacchetto **1.3.0**, SQLite **schema 1**. D2 rimane formalmente chiuso;
D3-B…F non implementate. Riferimenti: [scheda A](../../docs/d3/d3-a.md),
[indice](../../docs/d3-roadmap.md), [handover](../../docs/handover.md).

## Baseline e candidato

Baseline `957aa968578613612477e00f34998f72ea2977a3`, dev inizialmente un commit
oltre origin/dev. Modifiche documentali D3-0 locali preservate. Prima dello
sviluppo: **315 PASS in 127,38 s**, Python 3.12.15, pytest 8.4.2, -W error,
uscita 0. Pacchetto iniziale 1.2.0/schema 1. git diff --check verde.

Commit applicativo e candidato verificato:
**`64d787d035b134f4eaed9f7f8935964ec156c73e`**. Suite e wheel corrispondono al
codice di questo commit; i successivi aggiornamenti sono esclusivamente
documentali. L'utente ha pubblicato `dev`; la CI ha verificato il candidato
**`be8b3d5202716679de7f46cf73ea984127e3aa8e`**, commit documentale `be8b3d5`.
Confronto Git tra `64d787d` e `be8b3d5`: codice, test Python, packaging, script e
workflow identici; le differenze sono esclusivamente documentali.

## Verifiche locali effettive

| Sistema | Python | Suite completa | Durata | Exit |
|---|---|---:|---:|---:|
| macOS 15.8 arm64 | 3.12.15, riferimento | 363 PASS | 183,28 s | 0 |
| macOS 15.8 arm64 | 3.11.17, compatibilità | 363 PASS | 165,56 s | 0 |
| macOS 15.8 arm64 | 3.13.16, compatibilità | 363 PASS | 168,85 s | 0 |

Nessun FAIL/XFAIL/XPASS, skip o warning pytest; warning trattati come errori.
I 315 casi D2 e i 48 nuovi casi D3-A sono verdi in ogni ambiente. Le tre suite
sono state avviate indipendentemente, contemporaneamente, su input/output/cache
temporanei separati. Le durate non sono benchmark operativi.

Verifiche intermedie: 123 regressioni storage/DETLIN/recovery/read-only PASS in
51,35 s; matrice mirata finale D3-A **48 PASS in 37,23 s**, Python 3.12.15.
Le evidenze finali sul candidato sono le suite complete sopra.

Comandi effettivi dalla radice del repository:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error
```

Log: `/private/tmp/qc-d3a-final312.log`, `qc-d3a-final311.log`,
`qc-d3a-final313.log`; test mirati in `qc-d3a-targeted312.log`. I percorsi
sono artefatti temporanei di questa sessione, non dipendenze del progetto.
Seguire [istruzioni test](../README.md) per riprodurre in un clone.
Versioni osservate in [manifesto D3-A](../../docs/qa/d3-a-environments.json).

## Copertura dei guasti e compatibilità

- Fit VIS/NIR con eccezione dopo il calcolo di una sequenza: altra sequenza
  calcolata, risultati falliti scartati, diagnosi sequence_id/unit/phase/type/reason.
  Stesso giorno/braccio non committato; un altro giorno può esserlo.
  Famiglia DSOL indipendente prosegue; riparazione/idempotenza e force che
  conserva lo storico verificati. Compute helper pubblico continua a sollevare.
- File DSOL/OLOC malformati insieme a file validi: diagnosi e prudente mancata
  chiusura della famiglia; acquisizioni indipendenti proseguono con codice 1.
- Processo SQL esterno sincronizzato che prende lock reali: upstream,
  registri/storico, init, preflight, validation/coverage rebuild; rilascio su
  retry oppure persistenza con tre tentativi. Un test usa timeout reale 5 s
  con attese 0,25/0,5 s e circa 15,75 s di blocco; gli altri riducono solo il
  timeout delle fixture e verificano le attese programmate.
- Lock IMMEDIATE ferma la scrittura prima dei dati; lettore con transazione
  aperta ferma il commit dopo INSERT/metadati/registro. Rollback totale prima
  del replay, nessun duplicato/provenienza fantasma, nessun commit su esaurimento.
- Cause numeriche LOCKED/BUSY/varianti estese attraverso wrapper pandas;
  messaggi senza codici non usati; FULL/READONLY/CORRUPT/IOERR/CONSTRAINT e
  schema/integrità reali non riprovati, WriterBusyError subito rifiutato.
- Legacy read-only non nasconde busy esaurito come conteggio sconosciuto;
  trigger SQL reale su seconda unità lascia la prima committata, annulla
  dati/provenienza/registro della seconda e conserva tutti i contatori.
- CLI/preflight: contesa risolta codice 0; sorgente runtime esaurita codice 1
  e famiglia indipendente salvata; archivio/preflight bloccante codice 2,
  senza anticipare persistiti o avviare fasi dipendenti. JSON v1 additivo;
  preflight/read-only immutabili e nessuna contaminazione tra run.
- Regresso D2 completo: dry-run/WAL, lease CLI/API reali, schema/rebuild,
  identità, completezza, fit multisequenza e tolleranze scientifiche invariati.

## Wheel e installazione isolata

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d3a-wheel
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d3a-installed312/bin/python scripts/check_installation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d3a-installed311/bin/python scripts/check_installation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d3a-installed313/bin/python scripts/check_installation.py
```

Wheel `qc_monitor-1.3.0-py3-none-any.whl`, SHA-256:
`2d22729d9b58a01e6d3bd3f584442a068b1cd65cd496558b767858a99903dc39`.
I **16 file Python/template** inclusi corrispondono byte per byte ai sorgenti
verificati, incluso `_sqlite_retry.py`. Build riuscita con ambiente riferimento.

Installata in **tre ambienti venv puliti separati** (Python 3.11/3.12/3.13),
con le stesse versioni scientifiche delle rispettive suite. Checker isolato
**PASS, uscita 0** in tutti e tre: import -I fuori checkout, entry point/template,
config validata, idempotenza, dry-run immutabile e rebuild con backup verificato.
`pip check` **PASS** sia nei tre ambienti sorgenti sia nei tre installati.
Gli import installati provengono dai rispettivi site-packages, non dall'editable.
Per 3.12 usati i vincoli reference-py312.txt; per 3.11/3.13 vincoli temporanei
ricavati con pip freeze --exclude qc-monitor dai rispettivi ambienti già testati.
Installazione da PyPI senza allentare vincoli o modificare gli ambienti/dati
dell'utente.

Log locali: `/private/tmp/qc-d3a-build.log`, `qc-d3a-install<versione>.log`,
`qc-d3a-check<versione>.log`, `qc-d3a-pipcheck<versione>.log`
e `qc-d3a-source-pipcheck<versione>.log`. Per 3.12 il pip check installato è
registrato nel log del checker. Versioni/runtime osservati nel manifesto D3-A.
Non modificati workflow o tolleranze; lo smoke grafico/HTML scientifico rimane
nella suite completa. Nessun cambiamento ai renderer richiede nuova QA pixel.

## Matrice hosted verificata — chiusura D3-A

[GitHub Actions run 37807882167](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37807882167), **attempt 1**, conclusione **success**,
SHA esatto **`be8b3d5202716679de7f46cf73ea984127e3aa8e`**. API e log verificati direttamente
l'8 ottobre 2026. Quattro job completati con successo:

| Runner | Python | Suite | Durata pytest | Wheel 1.3.0 | Checker isolato |
|---|---|---:|---:|---|---|
| ubuntu-latest | 3.11 | 363 PASS | 203,39 s | PASS | PASS |
| ubuntu-latest | 3.12 | 363 PASS | 190,85 s | PASS | PASS |
| ubuntu-latest | 3.13 | 363 PASS | 181,58 s | PASS | PASS |
| macos-latest | 3.12 | 363 PASS | 256,35 s | PASS | PASS |

Nessuno skip nella suite; warning come errori. Lo step di installazione tcsh
è correttamente escluso su macOS, non è uno skip di test. Build wheel e verifica
installazione isolata sono riuscite in ogni job. Il `pip check` è provato negli
ambienti locali sopra; non è attribuito come step separato a questa CI.
Log scaricato in `/private/tmp/qc-d3a-hosted-37807882167.log`; durate dal
riepilogo pytest, non dai tempi complessivi dei job. Il log temporaneo non è una
dipendenza del progetto: il link hosted e questa tabella conservano l'evidenza.

La chiusura è esclusivamente documentale; nessuna nuova suite locale richiesta
per codice invariato. Verifiche di chiusura **PASS**: git diff --check,
**75 collegamenti locali** nei documenti aggiornati, manifesto CI coerente con
SHA/quattro job, nessuna modifica a codice, configurazione, test o schema.

## Consegna e limiti

Documentazione: scheda/indice D3, handover, README, contratti/operazioni,
istruzioni test, queste evidenze e manifesto ambiente. Roadmap/valutazione
locali aggiornate e ancora ignorate; documentazione D3-0 preservata. Evidenze
D1/D2 e codice/schema scientifico non modificati oltre allo scopo D3-A.
Verifiche documentali **PASS**: git diff --check, whitespace dei nuovi file,
**108 collegamenti locali** senza target mancanti; sorgenti/test/versione identici
al candidato applicativo. Documenti storici D1/D2 e schema identici alla baseline.

La matrice hosted seguente completa la chiusura D3-A. Le prove locali e la CI
D2 restano evidenze distinte. Il successivo commit di chiusura modifica soltanto
la documentazione e non ha una propria esecuzione CI attribuita.

Limiti: retry per operazione e timeout per attesa SQLite, non deadline globale;
backup/replace/drop_all non riprovati; lease di update/pubblicazione, figure,
generazioni/retention/riuso rimangono B–F. Le fixture sintetiche non certificano
l'accettazione scientifica operativa né il completamento del produttore.
Stima concordata 6–8 ore inclusi test/documentazione; non è consuntivo.

Nessun push, merge, deploy, modifica scheduler, archivio operativo o rebuild
dell'utente. Nessuna verifica D3-A pendente. Punto di ripresa: leggere stato,
evidenze e [scheda D3-B](../../docs/d3/d3-b.md), poi pianificare D3-B soltanto
su una nuova richiesta. D3-B non avviata; nessun avanzamento automatico.

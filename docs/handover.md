# Handover D3-A — 8 ottobre 2026

**D3-A implementata e consegnata localmente su `dev`; chiusura formale hosted
pendente.** Pacchetto **1.3.0**, SQLite **schema 1**. **D3-B…F non avviate**.
Questa apertura prevale sulle precedenti istruzioni di ripresa, conservate sotto
come storia di D3-0/D2. D2 rimane formalmente chiuso.

## Scheda sintetica di consegna D3-A

- Baseline `957aa968578613612477e00f34998f72ea2977a3`, dev un commit oltre
  origin/dev; modifiche documentali locali D3-0 preservate. Prima dello sviluppo:
  315 PASS in 127,38 s, Python 3.12.15, warning come errori, uscita 0.
- Commit applicativo/candidato locale **`64d787d035b134f4eaed9f7f8935964ec156c73e`**.
  La registrazione successiva delle evidenze è documentale: identificarne SHA
  con git log, senza attribuirle una CI non eseguita.
- Consegnati: isolamento del calcolo DETLIN per sequenza, diagnosi strutturate,
  retry SQLite limitati nelle letture e transazioni, contatori corretti dopo
  errori successivi. Schema/scienza/firme e ritorni pubblici invariati.
- Decisioni confermate: timeout 5 s, due retry con attese 0,25/0,5 s, politica
  fissa senza YAML/CLI; filename senza giorno blocca prudentemente la famiglia.
  Giorno/braccio resta atomico, force fallito preserva storico.
- Suite completa locale: **363 PASS su ciascuno di Python 3.11/3.12/3.13**,
  warning come errori, nessuno skip; verifiche e durate: [evidenze D3-A](../tests/results/d3-a-validation.md);
  [manifesto ambiente](qa/d3-a-environments.json). Nuovi casi D3-A: 48.
  Wheel 1.3.0 installata in tre venv puliti: checker isolato e pip check
  PASS su 3.11/3.12/3.13. Tutti gli input/output sono sintetici e temporanei.
- Documentazione aggiornata: [indice](d3-roadmap.md), [scheda A](d3/d3-a.md),
  contratti/operazioni, README/test, risultati/ambiente; roadmap/valutazione in
  reference_docs restano locali e ignorate. D3-0 conservata, evidenze D1/D2 invariate.
- Limiti: retry per operazione, non deadline dell'intero batch; backup, rename
  e drop_all non sono rilanciati. Renderer, update/pubblicazione, generazioni,
  retention/riuso restano da sviluppare nelle rispettive milestone.
- **Hosted pendente:** matrice Linux 3.11/3.12/3.13 e macOS 3.12 sul candidato
  esatto. Non attribuire a D3-A la CI D2 o verifiche locali come prove Linux.
  Nessun push, merge, deploy, modifica scheduler o rebuild dei dati dell'utente.
- Stima concordata 6–8 ore inclusi test/documentazione; attese CI escluse.
  È una stima di sviluppo, non un tempo misurato o un benchmark del batch.

## Punto di ripresa vincolante

Verificare branch/HEAD/working tree e leggere scheda A, evidenze e istruzioni test.
La prossima attività è **completare soltanto la verifica hosted D3-A** dopo che
l'utente autorizza/pubblica il candidato. Il commit documentale successivo non
cambia il codice: distinguere SHA applicativo, SHA effettivamente eseguito dalla
CI e documentazione di chiusura. Se CI fallisce, correggere e riverificare D3-A.
Solo dopo esiti verdi registrarne la chiusura formale.
**Non iniziare D3-B o qualsiasi step successivo senza una nuova richiesta.**

## Handover storico D3-0 — 8 ottobre 2026

**D2 completato e formalmente chiuso l’8 ottobre 2026** su `dev`, pacchetto **1.2.0**, SQLite
**schema 1**. **315 PASS su ciascuno di Python 3.11/3.12/3.13**, wheel isolata e
`pip check` verdi su tutti e tre. Verifiche e stato di chiusura sono registrati nei [risultati D2](../tests/results/d2-validation.md);
La [matrice hosted D2](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37793731551), attempt 1, è verde sul commit
`9f666b0e3382468ad7caf167d8437acabbe897c7`: 315 PASS in ciascuno dei quattro
job, build e installazione isolata riuscite. Nessuna funzionalità D3 implementata.

## Stato corrente e scheda di consegna D3-0

**D3-0 completato: solo roadmap e documentazione per l’handover.** D3-A…F
sono pianificate, non implementate. Il riferimento per ogni nuova sessione è
[l’indice D3](d3-roadmap.md), con schede [A](d3/d3-a.md), [B](d3/d3-b.md),
[C](d3/d3-c.md), [D](d3/d3-d.md), [E](d3/d3-e.md), [F](d3/d3-f.md).

- Baseline verificata: `dev`, HEAD `957aa968578613612477e00f34998f72ea2977a3`,
  working tree inizialmente pulito; un commit oltre `origin/dev` (`9f666b0`).
- Consegnati: indice versionato, sei schede, roadmap/valutazione locali,
  collegamento README e questo handover. `reference_docs/` resta ignorata.
- Decisioni registrate: report parziale con errore visibile e uscita 2;
  riuso solo su errore con data originale; due generazioni, orfani 24 ore,
  massimo due staging orfani. Dettagli comuni e questioni aperte nelle schede.
- Verifiche documentali: confronto con sorgenti D2, coerenza e link locali,
  confini di modifica e `git diff --check`; [evidenze D3-0](../tests/results/d3-0-validation.md).
- La suite della pianificazione, precedente alle modifiche documentali, ha dato
  **315 PASS in 128,22 s**, Python 3.12.15, `-W error`. Non è una nuova CI D3.
- Codice, config, pacchetto 1.2.0, schema 1 e dati invariati. Nessun commit/push,
  merge, deploy o rebuild operativo eseguito nella consegna D3-0.
- Stima pianificata D3-0: 2–4 ore; D3 completa 36–56 ore (5–7 giornate),
  incluse verifiche/documentazione, escluse attese CI; non è consuntivo.

**Prossima attività: pianificazione dettagliata di D3-A**, soltanto su nuova
richiesta. Leggere indice/scheda A, verificare branch/HEAD/working tree e risultati
D2, poi chiarire le questioni di A senza iniziare B o D4. Le dipendenze e la
procedura di consegna sono nell’indice; non richiedono il contesto della chat.
I documenti D3-0 sono modifiche locali da identificare tramite `git status`;
un futuro commit di consegna va registrato senza inventarne preventivamente lo SHA.

## Baseline e scheda di consegna D2 (storia conservata)

Commit applicativo **`7f0f657`** (`7f0f657c3727aed5221fa9fb3ab5a3ca5c4d04ed`),
successivo alla baseline `30a8914`. Suite, wheel e controllo visivo verificano
il codice archiviato in tale commit. Il successivo incremento è soltanto
la registrazione documentale di queste evidenze; identificare HEAD con
`git log --oneline`. L’utente ha pubblicato `dev`: il candidato hosted e
`origin/dev` sono `9f666b0`; `main` rimane a `8d44c9d`.
Il successivo commit di chiusura modifica soltanto la documentazione e non
ha un proprio risultato CI attribuito.

Baseline: `30a8914`, working tree pulito, `dev` un commit oltre `origin/dev`.
D1 formalmente chiuso sul codice `fb37d9e`, 216 PASS in ciascuno dei quattro job
[hosted 37772436524](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37772436524).
La verifica mirata iniziale durante la pianificazione D2 ha dato 58 PASS in 34,93 s.
La storia D1 resta in [evidenze D1](../tests/results/d1-validation.md) e
[chiusura D1](d1-closure.md).

Consegnati: configurazione dichiarativa validata, discovery coerente, metadati
HTML espliciti, schema versionato con identità sorgente/sequenza, provenienza QC,
fit DETLIN indipendenti e transazioni per giorno/braccio, lock comune ai writer,
rebuild separato con backup/coverage e sostituzione atomica. Nessuna conversione
scientifica del binning o nuova definizione di notte osservativa.

Incompatibilità operativa: archivi senza versione non sono aperti in scrittura
né migrati automaticamente. Preflight ordinario li rifiuta; dry-run può leggere
i registri legacy. Rebuild esplicito richiede storico recuperabile e connessioni
esterne chiuse. Non eliminarne le sentinelle per far passare la ricostruzione.
Il file `.lock` resta sul disco; la lease termina con la chiusura del processo.

## Documenti e riproduzione

Leggere [contratti D2](d2-contracts.md), [procedure operative](operations.md),
[istruzioni test](../tests/README.md) e i risultati prima della prossima attività.
La roadmap/valutazione locale in `reference_docs` viene aggiornata senza essere
inclusa in Git. Tutti gli input/output delle prove sono sintetici e temporanei.

```sh
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
```

Ambienti osservati in [manifesto D2](qa/d2-environments.json); suite complete
senza warning pytest o skip, `actionlint` 1.7.12 verde. I percorsi temporanei
locali e le durate sono nei risultati.

La tavola [QA D2](qa/d2-reference.png) mostra latest/all per due sequenze
complete; il report sintetico standard con 12 figure resta verificato.
Nessuna regressione numerica viene sostituita con confronti pixel per pixel.

## Limiti e ripresa

- Matrice hosted D2 completata; distinguere il candidato verificato `9f666b0`
  dal successivo commit documentale di chiusura.
- Sequenze DETLIN su più date restano aperte. Binning assente assume 1 per asse
  con diagnosi; ROI e segnali restano nei pixel/ADU dell’immagine acquisita.
- Update e pubblicazione non sono coordinati dal lock D2. Coerenza HTML/PNG,
  retention immagini e isolamento per figura restano D3.
- Collaudo scientifico su dati rappresentativi, segnale di fine riduzione e
  prestazioni operative restano aperti. Riduzione completata prima del monitor.
- Backup retained per scelta; interruzione OS può lasciare uno staging non
  pubblicato. Nessuna pulizia generale o rielaborazione automatica dello storico.
- Push del candidato effettuato dall’utente. Questa chiusura non esegue nuovi
  push, merge, deployment o rebuild dei dati dell’utente.

Alla prossima sessione seguire il punto di ripresa D3-0 in apertura e leggere
i risultati D2. D2 resta chiuso, senza verifiche pendenti. D3-A non è avviata;
non pubblicare o integrare `main` automaticamente.

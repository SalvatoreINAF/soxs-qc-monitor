# Handover D2 — 8 ottobre 2026

D2 implementato e verificato localmente su `dev`, pacchetto **1.2.0**, SQLite
**schema 1**. **315 PASS su ciascuno di Python 3.11/3.12/3.13**, wheel isolata e
`pip check` verdi su tutti e tre. Verifiche e stato di chiusura sono registrati nei [risultati D2](../tests/results/d2-validation.md);
la matrice hosted D2 resta pendente fino a una pubblicazione richiesta dall’utente.
Non attribuire al candidato D2 i risultati CI di D1 e non iniziare D3.

## Baseline e scheda di consegna

Commit applicativo **`7f0f657`** (`7f0f657c3727aed5221fa9fb3ab5a3ca5c4d04ed`),
successivo alla baseline `30a8914`. Suite, wheel e controllo visivo verificano
il codice archiviato in tale commit. Il successivo incremento è soltanto
la registrazione documentale di queste evidenze; identificare HEAD con
`git log -2 --oneline`. `main` rimane a `8d44c9d` e `origin/dev` a `fb37d9e`.

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

- Matrice hosted D2 da eseguire sul commit candidato pubblicato dall’utente;
  distinguere sempre codice verificato e successivi commit documentali.
- Sequenze DETLIN su più date restano aperte. Binning assente assume 1 per asse
  con diagnosi; ROI e segnali restano nei pixel/ADU dell’immagine acquisita.
- Update e pubblicazione non sono coordinati dal lock D2. Coerenza HTML/PNG,
  retention immagini e isolamento per figura restano D3.
- Collaudo scientifico su dati rappresentativi, segnale di fine riduzione e
  prestazioni operative restano aperti. Riduzione completata prima del monitor.
- Backup retained per scelta; interruzione OS può lasciare uno staging non
  pubblicato. Nessuna pulizia generale o rielaborazione automatica dello storico.
- Nessun push, merge, deployment o rebuild dei dati dell’utente eseguito.

Alla prossima sessione verificare HEAD/working tree, leggere i risultati D2 e
completare soltanto eventuali verifiche D2 pendenti. Non avviare D3 senza una
nuova richiesta e non pubblicare o integrare `main` automaticamente.

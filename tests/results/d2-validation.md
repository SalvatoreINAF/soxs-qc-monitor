# D2 — Verifica e consegna, 8 ottobre 2026

**D2 completato e formalmente chiuso su `dev`**, pacchetto **1.2.0**,
SQLite **schema 1**. Baseline `30a8914`, inizialmente pulita e un commit oltre
`origin/dev`. Commit applicativo verificato: `7f0f657c3727aed5221fa9fb3ab5a3ca5c4d04ed`. Le suite e la wheel
verificano lo stesso codice archiviato in questo commit; il successivo commit
documentale registra il riferimento senza ulteriori modifiche di codice/test.
Consultare [handover](../../docs/handover.md) per lo stato di consegna.
Il candidato pubblicato dall’utente è `9f666b0e3382468ad7caf167d8437acabbe897c7`.
La [CI D2](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37793731551) è verde; i risultati CI D1 restano distinti.
Il successivo commit documentale di chiusura non modifica codice, test o workflow.

## Verifiche finali

| Sistema | Python | Suite completa | Durata | Exit | Wheel isolata / pip check |
|---|---|---:|---:|---:|---|
| macOS 15.8 arm64 | 3.12.15, riferimento | 315 PASS | 135,16 s | 0 | PASS / PASS |
| macOS 15.8 arm64 | 3.11.17, compatibilità | 315 PASS | 118,07 s | 0 | PASS / PASS |
| macOS 15.8 arm64 | 3.13.16, compatibilità | 315 PASS | 121,32 s | 0 | PASS / PASS |

Nessun FAIL/XFAIL/XPASS, skip o warning pytest; warning trattati come errori.
La suite comprende i 216 casi precedenti e 99 casi D2. Non sono state allargate
le tolleranze scientifiche (`rel=1e-10`, `abs=1e-8` dove applicabili). Le tre
esecuzioni sono indipendenti, con input/output temporanei separati. Le durate
non sono benchmark operativi; le fixture riutilizzano solo l’inventario font
creato dalla collection, copiato nelle cache CLI isolate.

Comandi effettivi dalla radice del repository:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error
```

Log locali: `/private/tmp/qc-d2-final312.log`, `qc-d2-final311.log`,
`qc-d2-final313.log`. Per un clone usare l’ambiente documentato nelle
[istruzioni test](../README.md); i percorsi temporanei non sono dipendenze
del repository. Versioni osservate in
[manifesto D2](../../docs/qa/d2-environments.json).

## Copertura significativa

- YAML con duplicati e override di ancore, tipi/colonne/query/stili/renderer, ROI,
  limiti delle figure, filenames e collisioni reali/symlink prima delle scritture.
- Discovery ricorsiva con DB diretto più annidati; deduplicazione/provenienza QC;
  vincolo SQL su file NULL distinto dalla stringa vuota; basename DSOL/OLOC uguali.
- Due sequenze VIS e NIR con pendenze indipendenti; una incompleta blocca il
  giorno/braccio; retry/force non mescolano tentativi e conservano il precedente.
- Binning e geometria, assunzioni esplicite, tempi invalidi, fit senza zeri
  artificiali e varianza nulla senza falso gain zero.
- Trigger SQL reali per rollback di dati, registri e metadati; writer concorrenti
  CLI/API respinti, lease rilasciata dopo terminazione del processo.
- Rebuild riuscito, sorgenti storiche mancanti, prodotti mancanti nello stesso
  giorno, schema/candidato invalido, backup/replace falliti, WAL e sidecar live,
  riferimenti DETLIN legacy non dimostrabili; archivio precedente conservato.
- Riepilogo di rebuild fallito: candidato scartato indicato come staged, senza
  dichiarare persistite righe non pubblicate.

Aspettative aggiornate deliberatamente: schema upstream incompatibile bloccato
in preflight (2), multisequenza supportata, rebuild subordinato alla copertura.
I loader vuoti e l’acquisizione indipendente via API rimangono verificati.

## Packaging, workflow e controllo visivo

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d2-wheel
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python scripts/check_installation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python scripts/check_installation.py
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python scripts/check_installation.py
```

Wheel `qc_monitor-1.2.0-py3-none-any.whl`, SHA-256:
`07f1eb56c784a49b1e9cd2b8be69520076e375ee4e4bebd93dca7323f8407511`.
I 15 file Python/template inclusi corrispondono byte per byte ai sorgenti verificati.
La wheel è stata installata senza import editable nei tre ambienti; il checker
esegue interpreti `-I` fuori checkout, elimina PYTHONPATH e verifica entry point,
template, configurazione, secondo avvio idempotente, dry-run immutabile, rigetto
configurazione invalida e rebuild con backup e schema verificato.
`pip check`: nessuna dipendenza incompatibile nei tre ambienti.

`actionlint` **1.7.12** accetta il workflow aggiornato, che conserva la matrice
Linux 3.11/3.12/3.13 e macOS 3.12 e tratta ora i warning pytest come errori.
`git diff --check` verde. Nessuna esecuzione hosted D2 viene attribuita a queste
verifiche macOS.

Report sintetico standard: 12 PNG e riferimenti HTML verificati dalla suite.
Ispezione visiva dei grafici VIS latest/all e della
[tavola D2](../../docs/qa/d2-reference.png): due fit distinti (8000/10000),
latest sceglie soltanto 10000, pannelli coerenti e legende senza sovrapposizione
agli assi. La tavola non è una golden image. Il controllo visivo ha portato a
riservare lo spazio effettivo della legenda multisequenza prima del salvataggio.

## Consegna e limiti

Documentazione: [contratti](../../docs/d2-contracts.md),
[operazioni](../../docs/operations.md), [handover](../../docs/handover.md), README
e istruzioni test aggiornati; roadmap/valutazione aggiornate localmente e ignorate.
Tutti i dati delle prove sono sintetici. Nessun archivio operativo, FITS
dell’utente, standalone, `main`, scheduler o servizio remoto è stato modificato.
D3 non avviato. D2 formalmente chiuso dopo la matrice hosted verde sul candidato
pubblicato dall’utente; nessun nuovo push, merge o deployment automatico.

## Chiusura hosted — 8 ottobre 2026

[Run 37793731551](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37793731551), **attempt 1**, workflow
`QC verification`, branch `dev`, SHA
`9f666b0e3382468ad7caf167d8437acabbe897c7`, esito `success`.
Avvio 14:35:34 UTC (16:35:34 Europe/Rome); ultimo job concluso 14:40:33 UTC.
Il confronto `7f0f657..9f666b0` contiene solo handover/evidenze documentali:
la CI verifica lo stesso codice applicativo consegnato localmente.

| Runner | Python | Suite | Durata pytest | Wheel | Installazione isolata |
|---|---|---|---:|---|---|
| ubuntu-latest | 3.11 | 315 PASS | 108,76 s | PASS | PASS |
| ubuntu-latest | 3.12 | 315 PASS | 144,78 s | PASS | PASS |
| ubuntu-latest | 3.13 | 315 PASS | 162,72 s | PASS | PASS |
| macos-latest | 3.12 | 315 PASS | 204,82 s | PASS | PASS |

Nessun FAIL/XFAIL/XPASS o skip nella suite; `-W error` attivo. Tutti i job
completati con successo. Lo step di installazione tcsh è correttamente saltato
su macOS perché destinato esclusivamente a Linux. Build wheel 1.2.0 e checker
fuori checkout riusciti in tutti i job. Log letto tramite `gh run view --log`,
copia temporanea `/private/tmp/qc-d2-hosted-37793731551.log`; il run è la fonte
remota delle evidenze, senza versionare log voluminosi.

**Criteri di accettazione D2 soddisfatti, nessuna verifica D2 pendente.**
Restano i limiti scientifici e operativi già dichiarati nell’handover.
La chiusura è documentale: non avvia D3 né autorizza merge o rilascio operativo.

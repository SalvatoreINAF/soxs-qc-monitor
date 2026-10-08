# D1 — evidenze di verifica, 8 ottobre 2026

Codice candidato: `7732ddb` su `dev`, dopo `aa46773` e `c61c6d6`; package 1.1.0.
Baseline iniziale `8d44c9d`: 177 PASS, 306,57 s.
La suite finale raccoglie 216 casi, senza marker XFAIL.

## Ambiente pulito e compatibilità locale

| Ambiente macOS arm64 | Verifica completa | Durata |
|---|---:|---:|
| Python 3.12.15, dipendenze di riferimento | 213 PASS (cutoff precedente) | 545,55 s |
| Python 3.11.17, dipendenze dichiarate risolte | 212 PASS (cutoff precedente) | 538,05 s |
| Python 3.13.16, dipendenze dichiarate risolte | 212 PASS (cutoff precedente) | 542,22 s |

L’ultimo caso del supervisore è passato nella suite mirata dei wrapper: 12 PASS
in 0,90 s. Le verifiche supplementari e la verifica finale completa sono riportate sotto.

Comandi effettivi (ambienti temporanei di questa sessione):

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest tests/test_run_result.py tests/test_batch_wrappers.py tests/test_scientific_rendering.py -q --tb=short
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest tests/test_run_result.py tests/test_batch_wrappers.py tests/test_scientific_rendering.py -q --tb=short
```

L’ambiente 3.12 è stato creato da zero e installato con i vincoli versionati.
Gli ambienti 3.11/3.13 sono separati; Astropy 6.1.2 è stato compilato da sorgente
su 3.13. `pip check` è verde su tutti e tre. Il manifesto delle versioni effettive
è in `docs/qa/d1-environments.json`. Nessun ambiente dell’utente è stato aggiornato.

## Build, installazione e QA

```sh
/private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d1-wheel
/private/tmp/qc-d1-reference/bin/python scripts/check_installation.py
/private/tmp/qc-d1-py311/bin/python scripts/check_installation.py
/private/tmp/qc-d1-py313/bin/python scripts/check_installation.py
```

Wheel 1.1.0 costruita e reinstallata nei tre ambienti: **PASS** per entry point,
import isolato fuori checkout, risorsa template, configurazione e idempotenza.
I checker eliminano `PYTHONPATH`, usano `-I` e fixture temporanee.

Controllo visivo: report sintetico con 12 PNG, schede VIS/NIR ispezionate nel
browser, tavola `docs/qa/d1-reference.png`. Verificati anche riferimenti HTML,
leggibilità e contenuto non vuoto dei PNG, senza confronto pixel per pixel.
I test timeout/SQLite lock/save failure sono reali; l’update è provato solo per
il dispatch, senza pull/install operativo. Schema e dati upstream preservati.

La revisione ha corretto due aspettative CLI per l’esito parziale e conservato
la diagnostica legacy read-only. Nessuna aspettativa è stata indebolita per
nascondere difetti e nessun XFAIL è stato aggiunto.

## CI hosted

Workflow configurato per quattro job: Linux 3.11/3.12/3.13, macOS 3.12. Configurati
suite, build e installazione separata. Alla consegna iniziale l’esecuzione hosted
era pendente. La successiva prima esecuzione è descritta nell’aggiornamento sotto;
D1 non è dichiarato formalmente completato finché la matrice non sarà verde.


## Verifiche supplementari di compatibilità

Dopo le suite complete da 212 casi, tutti i 37 casi D1 presenti a quel punto
sono stati rieseguiti sui runtime di compatibilità:

- Python 3.11.17: **37 PASS**, 191,15 s.
- Python 3.13.16: **37 PASS**, 191,41 s.

La revisione finale dell’update ha aggiunto due prove per i fallimenti git/pip
classificati come bloccanti (`7732ddb`). La suite del supervisore aggiornata
ha **14 PASS** su Python 3.12 (0,77 s); i risultati 3.11/3.13 sono riportati sotto. Il numero corrente di prove è pertanto 216.


Ulteriore verifica completa del cutoff da 214 casi: **214 PASS**, 483,68 s,
Python 3.12.15. Sul supervisore finale: **14 PASS** anche su Python 3.11.17
(0,69 s) e Python 3.13.16 (0,59 s). La verifica completa dei 216 casi è
l’ultima esecuzione sul codice candidato `7732ddb`.


## Verifica finale sul codice candidato

**216 PASS**, uscita 0, **483,91 secondi**, Python 3.12.15 con dipendenze
fissate e pytest 8.4.2. Nessun FAIL, XFAIL, XPASS, warning o skip.
Comando eseguito su `dev` al commit applicativo `7732ddb`:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short
```

La consegna documentale successiva modifica soltanto README, istruzioni,
handover ed evidenze; il codice applicativo e i test sono quelli verificati.
`git diff --check`, sintassi Python e struttura del workflow sono verdi.
La matrice hosted rimane l’unico criterio di chiusura D1 ancora pendente.


## Correzione della validazione hosted del workflow

Dopo il push eseguito dall’utente di `dev` (`c689c8b`), GitHub ha rifiutato il
workflow prima dell’avvio dei job: `runner.temp` non è consentito nel blocco
`jobs.tests.env`. Le righe 25/26 producevano `Unrecognized named-value: runner`.
La precedente verifica della struttura YAML non verificava la disponibilità dei
contesti Actions e non costituiva validazione semantica del workflow.

Fix: `MPLCONFIGDIR` e `XDG_CACHE_HOME` vengono ora creati e scritti in
`GITHUB_ENV` da uno step Bash, usando `$RUNNER_TEMP`, prima dell’installazione
scientifica e dei test. Gli altri riferimenti a `runner.temp` nei comandi degli
step rimangono validi. Matrice, dipendenze e codice applicativo sono invariati.

Verifiche effettive:

- `actionlint` **1.7.12**, binario della release ufficiale con SHA-256 verificato:
  workflow precedente **FAIL**, riproduzione dei due errori sui contesti;
  workflow corretto **PASS**, uscita 0.
- Esecuzione dello step cache in ambiente temporaneo: **PASS** per directory
  e valori esportati in `GITHUB_ENV`, anche con spazi nel percorso.
- `git diff --check`: **PASS**. Nessuna modifica al codice applicativo o ai test
  Python; non è necessario ripetere la suite scientifica per questo fix.

Comando di validazione (controlli di espressioni e struttura Actions; delegati
ShellCheck/Pyflakes disabilitati):

```sh
actionlint -shellcheck= -pyflakes= .github/workflows/tests.yml
```

Fonte: [disponibilità dei contesti GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability).
**Stato: nuovo candidato da pubblicare e verificare nei quattro job hosted.**
Un rerun del vecchio SHA non applica il fix; serve una nuova esecuzione sul
commit contenente la correzione. Nessun nuovo push eseguito da questa attività.

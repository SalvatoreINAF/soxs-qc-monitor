# D3-B — Validazione locale, 8 ottobre 2026

**Stato: consegna locale verificata; CI pendente, nessuna chiusura formale.**
Baseline `dev` / `8892af5`, working tree pulito, un commit oltre origin/dev.
D3-A formalmente chiusa, pacchetto 1.3.0/schema 1. La pianificazione aveva
verificato 70 PASS / 36,98 s su Python 3.12.15 (`-W error`).

Commit applicativo/candidato verificato localmente:
`98d51d341e4d85bc7e14e6f4abf6273e8e42bc32`, pacchetto **1.4.0**, schema **1**.
La consegna aggiunge documentazione: il suo HEAD deve avere gli stessi file
applicativi, test, scripts e workflow di questo commit. Nessun push effettuato.

## Prove implementate

**400 casi complessivi:** 315 D2, 48 D3-A, 37 D3-B. Solo dati sintetici e
percorsi temporanei. Le 37 prove D3-B includono:

- processi in contesa per progetto, ambiente e sorgenti; CLI run/rebuild,
  writer/API e update; riepilogo precedente e risorse protette invariati;
- destinazioni condivise (DB, HTML, PNG, immagini), directory annidate,
  alias symlink, include esterni e progetti annidati; progetti indipendenti
  consentiti con ambiente/sorgenti condivisi;
- pausa controllata nelle funzioni di rendering, HTML e riepilogo, con
  secondo run/API respinto mentre il primo mantiene le protezioni;
- acquisizione parziale, reentrancy e promozione rifiutata, proprietario
  terminato, figlio superstite con descrittori ereditati, timeout che termina
  anche il discendente che ignora SIGTERM;
- update con repository sintetico e backup reale di configurazioni,
  provenienza e archivio QC popolato; preflight/dry-run figli reali.
  Soltanto pull/installazione sono simulati; errori di backup sono indotti;
  errori dei controlli provengono dalla rimozione di un input temporaneo;
- cambio delle destinazioni dopo pull: uscita 2 prima di installare;
  cambiamento delle query senza cambio di risorse: consentito;
- ispezioni senza lock/scritture durante lease esclusive, file laterali
  SQLite protetti, symlink nei file del registro rifiutati senza toccare il target.

La sincronizzazione dei proprietari usa pipe stdin/stdout e segnali reali.
Le suite sono eseguite in sequenza: update prende protezioni esclusive sui
sorgenti comuni, anche tra interpreti differenti. Nessun cambiamento a formule,
tolleranze, schema, D3-A retry o risultati scientifici.

## Comandi e risultati finali

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error
/private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d3b-wheel
/private/tmp/qc-d3b-installed312/bin/python scripts/check_installation.py
/private/tmp/qc-d3b-installed312/bin/python -m pip check --cache-dir /private/tmp/qc-d3b-pip-cache
```

I comandi checker/pip check sono ripetuti negli ambienti puliti 3.11 e 3.13.
Ambienti, versioni delle librerie, durate e hash dell’artefatto sono registrati
nel [manifesto](../../docs/qa/d3-b-environments.json).

| Ambiente locale | Suite con `-W error` | Durata | Checker wheel | pip check sorgenti/wheel |
|---|---|---|---|---|
| macOS 3.12.15 | 400 PASS | 191.89 s | PASS | PASS |
| macOS 3.11.17 | 400 PASS | 169.61 s | PASS | PASS |
| macOS 3.13.16 | 400 PASS | 171.44 s | PASS | PASS |

Nessuno skip o XFAIL. Log finali: `/private/tmp/qc-d3b-verified312.log`,
`/private/tmp/qc-d3b-verified311.log`, `/private/tmp/qc-d3b-candidate313.log`.
Build: `/private/tmp/qc-d3b-build.log`; checker: `qc-d3b-check311/312/313.log`
sotto `/private/tmp`. Questi file temporanei non sono necessari per riprendere:
conteggi, ambiente e limiti sono conservati in questa scheda e nel manifesto.

Wheel `qc_monitor-1.4.0-py3-none-any.whl`, SHA256
`c2700d2c140ea40ccd4a33214892127d814a59e308b3d24c5f73ac74d137ccc3`.
Tutti i file Python/template della wheel e delle tre installazioni coincidono
con il commit applicativo; moduli scientifici, schema e `_sqlite_retry.py`
invariati rispetto alla baseline. Wheel installata in tre nuovi venv separati; checker
isolato e pip check PASS su 3.11/3.12/3.13. Il checker esegue importazioni `-I`
fuori checkout, entry point, template, validazione, idempotenza, dry-run
immutabile e rebuild protetto. 18 file Python/template nella wheel coincidono
con i sorgenti; percorso/hash nel manifesto. `git diff --check` PASS.

Le esecuzioni intermedie durante lo sviluppo non sono evidenze del candidato
finale: comprendevano correzioni alle fixture e verifiche aggiunte in seguito.
Le prove preliminari verdi sono sostituite dalle esecuzioni finali qui registrate.

## Limiti e ripresa

CI hosted **pendente** sullo SHA esatto da pubblicare: Linux Python
3.11/3.12/3.13 e macOS 3.12, suite/wheel/installazione isolata secondo workflow.
I risultati locali macOS non certificano Linux. Non è stato eseguito alcun
pull/install operativo, push, merge, deploy, modifica scheduler o rebuild dei
prodotti dell’utente. Le lease sono cooperative sullo stesso host/account
Linux/macOS: prima della messa in uso terminare i processi delle versioni precedenti.

Le ispezioni autonome non promettono una fotografia atomica durante update;
nessun rollback automatico, pubblicazione atomica o cleanup/retention introdotto.
Ripresa: verifica/chiusura hosted D3-B; **D3-C non avviata**.


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

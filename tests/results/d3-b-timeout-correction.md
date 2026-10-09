# D3-B — Correzione timeout, 9 ottobre 2026



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

## Comandi e dati conservati

```sh
python -m pytest -ra --tb=short -W error
python -m pytest tests/test_d3b_coordination.py -k 'group_wait or timeout_kills_descendant or timeout_waits_for_deferred' -ra --tb=short -W error
python -m pytest tests/test_read_only.py::test_dry_run_accepts_readable_inputs_and_unwritable_destinations -ra --tb=short -W error
```

Linux usa `python:3.12-slim` con procps/tcsh/git, repository montato in sola
lettura e copia di package/test/script/config/utils sotto `/tmp/project`.
Pacchetto/dipendenze installati nel solo contenitore, automaticamente rimosso
alla fine. Utente `qcvalidation` per i controlli non privilegiati. macOS usa
i venv temporanei di riferimento già documentati. Nessun input operativo usato.

Log finali in `/private/tmp`: `qc-d3b-timeout-final-mac312.log`,
`qc-d3b-timeout-final-linux312.log`, `qc-d3b-timeout-targeted311.log`,
`qc-d3b-timeout-targeted313.log`, `qc-d3b-timeout-unprivileged-linux.log`,
`qc-d3b-permission-unprivileged-linux.log`.
I tentativi preliminari Docker con copia incompleta delle fixture sono esclusi
dalle evidenze finali. Il test dei permessi non era selezionato dal filtro del
primo controllo non privilegiato: è stato eseguito esplicitamente in seguito.

[Evidenza del difetto Linux](d3-b-timeout-before-linux.json),
[log CI](d3-b-ci-37818741442-failed.log),
[metadati CI](d3-b-ci-37818741442.json),
[diagnosi iniziale](d3-b-ci-diagnosis.md),
[manifesto](../../docs/qa/d3-b-environments.json).

La matrice hosted va rieseguita sul candidato corretto prima della chiusura.
Non confondere il precedente macOS verde con l’approvazione della correzione.

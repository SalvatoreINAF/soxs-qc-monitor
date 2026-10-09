# D3-B — Coordinamento operativo

**Stato: consegna locale verificata; CI pendente, non formalmente chiusa.**
Baseline `dev` / `8892af5`, pulita; D3-A formalmente chiusa. Pacchetto **1.4.0**, schema **1**.
Stima approvata: **8–12 ore**, inclusi test e documentazione, esclusa attesa CI.

## Decisioni e implementazione

Una sola operazione per progetto (`config_path.parent.parent`, oppure `--root`
nel supervisore), anche con configurazioni e destinazioni separate. Contesa
immediata con codice 2, senza sovrascrivere il riepilogo precedente.
Progetti indipendenti possono condividere ambiente e sorgenti in lettura;
update ne richiede l’uso esclusivo. Le API dei writer partecipano anche senza
conoscere il progetto.

`coordination.py` usa flock non bloccante e identità canoniche, registro
`/tmp/soxs-qc-monitor-locks-<uid>` privato dell’account, file regolari posseduti,
nessun symlink o troncamento. I file persistono e non vanno cancellati.
Ordine: ambiente, progetto, sorgenti/risorse ordinate, infine `<db>.lock`.
File esclusivi e antenati condivisi impediscono interferenze con directory
annidate, anche per i progetti. I sorgenti sono protetti nelle guardie iniziali
prima delle risorse dipendenti dalla configurazione. Reentrancy nello stesso thread; esclusivo copre condiviso, nessuna
promozione implicita. Il lock storico dell’archivio è conservato.

L’entry point leggero e `python -m qc_monitor.main` proteggono l’avvio prima
delle importazioni applicative. Il run rilegge la configurazione dopo aver
acquisito le risorse e mantiene le lease attraverso archivio, rendering,
HTML, riepilogo e conclusione. `--no-plots` omette le risorse dei report.
Preflight e dry-run autonomi non creano/acquisiscono lock: non garantiscono
una fotografia atomica durante update.

Update acquisisce prima del backup, usa configurazione validata/normalizzata,
salva anche include e provenienza. Dopo pull confronta le destinazioni:
un cambiamento interrompe con 2 prima dell’installazione. Query/colori/titoli
che non cambiano destinazioni sono ammessi. Nessun rollback o rebuild
automatico. Descrittori esplicitamente ereditati dai comandi mantengono le
lease anche se muore il supervisore; timeout termina il gruppo dei processi.
I controlli figli reali sono senza lock, nessun bypass ambientale.

JSON v1 esteso con `coordination` (operazione, risorse, conflitto); update
registra righe `COORDINATION` JSON. Firme pubbliche e retry D3-A conservati.

## Verifiche e consegna

Processi reali sincronizzati, dati sintetici, pause in grafici/HTML/riepilogo,
contese CLI/API/update, alias e directory annidate, rilascio e figli superstiti,
backup e controlli figli reali. Pull/installazione soltanto simulati nelle prove.
Suite completa: **400 PASS** per macOS Python 3.11.17/3.12.15/3.13.16
con `-W error`, scientifiche invariate. Wheel, checker isolato e pip check PASS
in tre nuovi ambienti separati. [Evidenze](../../tests/results/d3-b-validation.md) e
[ambienti](../qa/d3-b-environments.json).

Chiusura formale subordinata alla CI sul candidato esatto: Linux Python
3.11/3.12/3.13 e macOS 3.12. Nessun push, merge, deploy o modifica scheduler.
Coordinamento cooperativo sullo stesso host/account Linux/macOS: terminare
prima i processi delle versioni precedenti. Nessuna pubblicazione atomica,
retention o cleanup introdotti. **D3-C non avviata.**
Ripresa: completare verifica/chiusura hosted D3-B, poi attendere nuova richiesta.


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

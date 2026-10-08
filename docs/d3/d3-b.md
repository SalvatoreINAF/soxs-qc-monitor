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

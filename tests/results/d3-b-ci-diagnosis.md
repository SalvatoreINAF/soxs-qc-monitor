# D3-B — Diagnosi CI, 9 ottobre 2026

Run 37818741442, attempt 1, candidato 0df371c43dfc3436dbb880525517bb12a618cf55.
Linux 3.11/3.12/3.13: 399 PASS, un fallimento identico nel test
`test_timeout_kills_descendant_after_leader_exits`, al tentativo di riacquisire
la lease. macOS 3.12: job verde. D3-B non formalmente chiusa.

`scripts/batch.py:execute` manda SIGKILL al gruppo ma attende soltanto
`process.wait()`, cioè il processo principale già terminato dopo SIGTERM.
Non attende la fine del discendente che ignora SIGTERM e conserva i descrittori.
L’invio del segnale non è una conferma che il discendente abbia già chiuso
le risorse. Il test prova subito la riacquisizione del lock.

Audit locale con 20 coppie di processi reali: nessuna contesa immediata su
macOS. Prova controllata, ritardando soltanto la consegna del SIGKILL al
figlio: execute ritorna mentre la lease è ancora occupata; dopo il segnale
reale la lease si libera. Confermata l’assenza di una barriera di terminazione.
Questa prova modella il ritardo di scheduling, non è un’esecuzione Linux.
Docker presente ma daemon non disponibile: nessuna riproduzione Linux locale.
La spiegazione è coerente con i tre errori Linux della CI; non è dimostrato
che un figlio rimanga vivo a lungo dopo l’invio reale del segnale.

Correzione da effettuare: rendere esplicita e limitata l’attesa della conclusione
dei figli e del rilascio delle lease, con test sincronizzati; evitare di
nascondere il problema con una pausa fissa. Poi verificare Linux e la matrice
CI sul nuovo candidato. Nessun sorgente applicativo modificato in questa audit,
nessun push, nessun avanzamento a D3-C.

Evidenze: `d3-b-ci-37818741442-failed.log`, `d3-b-ci-37818741442.json`,
`d3-b-timeout-audit.json`, script `d3-b-timeout-audit.py` nella stessa cartella.

Aggiornamento: Docker è stato avviato nella sessione successiva e la diagnosi
riprodotta su Linux 20 volte su 20. Correzione implementata e verificata:
[dettagli](d3-b-timeout-correction.md). Il precedente limite sulla disponibilità
Linux è superato; la CI del nuovo candidato resta pendente.

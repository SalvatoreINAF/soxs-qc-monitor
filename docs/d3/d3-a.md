# D3-A — Acquisizione resiliente

**Completata e formalmente chiusa l'8 ottobre 2026 su `dev`.** Dipendenza D3-0
soddisfatta; D2 resta formalmente chiuso. Pacchetto **1.3.0**, SQLite **schema 1**.
Stima concordata **6–8 ore**, incluse verifiche/documentazione, escluse attese CI;
non è consuntivo. Politiche comuni: [indice D3](../d3-roadmap.md).

## Baseline verificata

HEAD iniziale `957aa968578613612477e00f34998f72ea2977a3`, branch `dev`, un commit
oltre origin/dev. Presenti le modifiche documentali locali D3-0, preservate.
Pacchetto iniziale 1.2.0, schema 1. Verifica prima dello sviluppo: 315 PASS in
127,38 s, Python 3.12.15, warning come errori, uscita 0; git diff --check verde.

Il confronto ha confermato parsing/selezione DSOL/OLOC e letture FITS già
protetti per file; D2 salva atomicamente giorno/braccio. Il calcolo DETLIN batch
non isolava eccezioni per sequenza, SQLite usava timeout impliciti senza retry,
e i totali di famiglia venivano finalizzati solo alla fine del ciclo delle unità.

## Decisioni e implementazione

- Confermate dall'utente: politica retry fissa, senza YAML/CLI; filename senza
  giorno riconoscibile blocca prudentemente tutte le unità potenzialmente
  coinvolte della famiglia. Nessuna deduzione da directory/header.
- Il loader DETLIN calcola per sequenza e cattura le eccezioni di calcolo;
  scarta i risultati parziali falliti e conserva diagnosi con sequence_id,
  giorno/braccio, fase fit, tipo e motivo. Le altre sequenze proseguono.
  Il compute helper pubblico mantiene firma, ritorno DataFrame ed eccezioni.
- Tutte le sequenze del giorno/braccio devono essere complete per sostituire
  l'unità; force fallito conserva lo storico. Unità indipendenti possono essere
  committate; riparazione e retry non creano duplicati né mescolano fit.
- Helper interno `_sqlite_retry.py`: timeout connessioni 5 s, tre tentativi,
  attese 0,25/0,5 s soltanto per codici numerici BUSY/LOCKED, comprese varianti
  estese e cause avvolte da pandas/storage. Nessuna analisi delle stringhe.
- Il confine di retry racchiude l'operazione che possiede connessione e
  transazione, dentro la lease dei writer. Rollback/close precedono replay.
  Coperti upstream, preflight, inizializzazione, registri, storico, writer e
  letture di validazione/coverage rebuild; nessun retry annidato.
- Nessun retry per fit, WriterBusyError, schema, dati invalidi, permessi, disco
  pieno o altri errori permanenti. Backup/rename e manutenzione drop_all non
  sono rilanciati. Limite per operazione, non timeout dell'intero batch.
- JSON v1 esteso additivamente con diagnosi di sequenza, `sqlite_operations`
  globali e delle letture sorgenti QC. Store diretti conservano gli eventi
  nell'istanza. Stati recovered/exhausted/failed e codici/tentativi/attese sono
  strutturati, non ricavati dai log. Dettagli in [operazioni](../operations.md).
- Contatori aggiornati solo dopo commit, inclusi totali delle unità precedenti
  se una successiva fallisce. Busy esaurito in lettura non diventa falso vuoto
  nelle fallback legacy. Input/fit parziale: 1; archivio/preflight bloccante: 2;
  contesa risolta senza altri guasti: successo ordinario.

Firme/ritorni pubblici, schema, identità e tolleranze scientifiche invariati.
Nessun intervento in lock operativi B, renderer C, pubblicazione/retention/riuso
D–F, scheduler, standalone o dati dell'utente.

## Verifiche e criteri di accettazione

Nuovi test `test_d3a_resilience.py`: 48 casi, esclusivamente sintetici e temporanei.
Fit fallito VIS/NIR con altra sequenza valida, stesso giorno o giorno diverso;
prosecuzione delle famiglie, riparazione/idempotenza e force che preserva storico.
Nomi DSOL/OLOC malformati con prodotti validi e famiglie indipendenti.

Processo SQL esterno sincronizzato: letture upstream/registri/storico, init,
preflight e verifiche rebuild; contesa che si risolve e persistente. Scrittura
bloccata prima delle modifiche oppure sul commit dopo le modifiche: rollback e
retry dell'intera unità, con provenienza e registro coerenti. Un test usa la
politica reale di 5 s per tre tentativi; la matrice più ampia usa timeout ridotti
solo nelle fixture, registrando le attese programmate 0,25/0,5 s.

Codici LOCKED/BUSY estesi e wrapper pandas; errori permanenti mai riprovati;
letture legacy senza occultare guasti, contatori dopo trigger SQL reale su una
seconda unità, codici CLI 0/1/2 e JSON, preflight immutabile. Le regressioni D2
verificano anche dry-run/WAL, lease reali e risultati scientifici.

Evidenze di suite complete Python 3.11/3.12/3.13, wheel isolata, pip check,
ambiente e limiti in [risultati D3-A](../../tests/results/d3-a-validation.md).
Nessuna tolleranza allargata, XFAIL o sostituzione della verifica numerica con
confronti pixel. [Matrice hosted](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37807882167) verde, attempt 1,
su `be8b3d5202716679de7f46cf73ea984127e3aa8e`: Linux 3.11/3.12/3.13 e macOS 3.12,
363 PASS ciascuno, build/installazione isolata riuscite. Nessuna verifica pendente.

## Consegna e ripresa

Commit applicativo/candidato locale:
**`64d787d035b134f4eaed9f7f8935964ec156c73e`**. La successiva registrazione delle
evidenze modifica soltanto documentazione e conserva i documenti D3-0 preesistenti.
Candidato hosted verificato: **`be8b3d5202716679de7f46cf73ea984127e3aa8e`** (`be8b3d5`).
La chiusura successiva è solo documentale, senza una nuova CI attribuita.
Scheda sintetica, limiti e punto di ripresa: [handover](../handover.md).

Aggiornati indice/scheda, README, contratti, operazioni, istruzioni test,
risultati/ambiente e roadmap/valutazione locali (reference_docs ancora ignorata).

Prossima sessione: leggere handover/evidenze, verificare dev/HEAD/working tree,
D3-A è chiusa. La prossima attività è pianificare D3-B soltanto su una nuova
richiesta, leggendo la sua scheda e chiarendo le questioni aperte. Nessun nuovo
push/merge/deploy o rebuild operativo in questa chiusura. D3-B non avviata;
nessun avanzamento automatico. Nessuna decisione o verifica D3-A pendente.

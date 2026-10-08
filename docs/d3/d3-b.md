# D3-B — Coordinamento operativo

**Stato: pianificata, non implementata.** Scheda iniziale dell’8 ottobre 2026.
Dipendenze: **D3-0; D2 formalmente chiuso**. Stima: **6–8 ore**, incluse verifiche e documentazione.
Politiche comuni e procedura di consegna: [indice D3](../d3-roadmap.md).

## Obiettivo e completamento

Impedire che run, rebuild e update interferiscano con lo stesso progetto, archivio o destinazione di report; una contesa è rifiutata prima delle modifiche protette.

La milestone è completa quando i comportamenti qui descritti sono verificati,
le regressioni richieste passano e documentazione/evidenze sono consegnate.
Distinguere consegna locale e chiusura formale hosted secondo l’indice D3.

## Stato iniziale da ricontrollare

`locking.py` implementa lease per percorso canonico dell’archivio, rientranti nello stesso thread e basate su `flock`. Store, coordinatori e rebuild sono già protetti. La lease di `acquisition_store` termina prima dei grafici in `main.py`; `scripts/batch.py` esegue backup/pull/installazione/verifiche senza questo coordinamento. Il supervisore ha già timeout e terminazione del gruppo di processi.

## Interventi e compatibilità

- Estendere la durata della protezione del run fino a rendering/pubblicazione/cleanup; coordinare progetto, archivio e destinazioni condivise anche fra configurazioni differenti.
- Acquisire le protezioni dell’update prima del backup e mantenerle fino alla fine delle verifiche. Preflight/dry-run figli devono funzionare senza contesa con il proprio supervisore.
- Conservare rifiuto immediato, reentrancy dei writer, file di lock persistenti e rilascio OS alla terminazione; preservare ispezioni autonome senza nuove scritture.

Conservare `writer_lease` e contratti dei writer D2. Nuove lease operative interne e controlli dei percorsi devono essere compatibili con CLI/API e wrapper esistenti; non introdurre rollback automatico dell’update.

Fuori da questa milestone: Nuovo motore di report e retention (D/E), riuso (F), nuovi scheduler, aggiornamento reale del checkout durante i test e refactoring generale.

## Verifiche e accettazione

- Processi reali in contesa: run/run, run/rebuild, run/update, API/update; uscita 2 senza modifiche ai dati protetti.
- Configurazioni con stesso DB o stessa destinazione e DB diversi: nessuna esecuzione simultanea incompatibile; nessun deadlock.
- Terminazione del proprietario: lease liberata e tentativo successivo riuscito; nessuna cancellazione del file di lock.
- Dry-run/preflight senza creazione di lock; timeout del supervisore e update fallito verificati su fixture, simulando soltanto pull/installazione esterni.

Usare solo dati sintetici e directory temporanee. Completare suite con warning
come errori, wheel e checker isolato, poi matrice CI sul candidato esatto;
seguire [istruzioni test](../../tests/README.md). Non allargare le tolleranze
scientifiche per ottenere un esito verde. Conservare evidenze e limiti residui.

## Ripresa e consegna

1. Leggere [handover](../handover.md), [indice D3](../d3-roadmap.md),
   [contratti D2](../d2-contracts.md), [risultati D2](../../tests/results/d2-validation.md)
   e le evidenze delle dipendenze indicate sopra.
2. Controllare branch `dev`, HEAD, working tree e storia con i comandi dell’indice.
   Preservare modifiche locali; verificare quali protezioni sono già presenti.
3. Pianificare solo D3-B, risolvendo le questioni sotto prima delle scelte
   implementative interessate. Le domande non sono decisioni già approvate.
4. Alla consegna aggiornare questa scheda e indice, handover, README, procedure
   operative, istruzioni test e contratti coinvolti. Registrare prove in
   `tests/results/d3-b-validation.md` (da creare allora), eventuale QA e ambiente.
   Aggiornare roadmap/valutazione locali senza includerle in Git.
5. Presentare scheda sintetica con baseline/commit, cambiamenti, decisioni,
   test locali/CI, limiti e punto di ripresa. Non iniziare la milestone successiva.

## Questioni da fissare nella pianificazione dettagliata

- Fissare posizione e identità dei lock operativi, ordine totale di acquisizione e protezione dell’avvio prima delle letture/modifiche sensibili.
- Definire la procedura dei controlli figli durante update e la gestione della configurazione che può cambiare durante pull.

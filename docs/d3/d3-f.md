# D3-F — Riuso su errore e chiusura integrata

**Stato: pianificata, non implementata.** Scheda iniziale dell’8 ottobre 2026.
Dipendenze: **D3-A e D3-E formalmente concluse (include B, C e D)**. Stima: **6–10 ore**, incluse verifiche e documentazione.
Politiche comuni e procedura di consegna: [indice D3](../d3-roadmap.md).

## Obiettivo e completamento

Mostrare una precedente immagine compatibile soltanto in caso di errore, con data originale esplicita, e verificare insieme tutti i requisiti D3.

La milestone è completa quando i comportamenti qui descritti sono verificati,
le regressioni richieste passano e documentazione/evidenze sono consegnate.
Distinguere consegna locale e chiusura formale hosted secondo l’indice D3.

## Stato iniziale da ricontrollare

D2 non ha riuso tracciato. All’avvio ricontrollare gli esiti C, manifesto/motore D e retention/CLI E: il report è già coerente senza fallback. A fornisce il comportamento di recovery acquisizione per il collaudo integrato.

## Interventi e compatibilità

- Cercare l’immagine compatibile nel manifesto della generazione corrente; su failed copiarla nel nuovo insieme e indicare `reused`, motivo e data originale. Su no_data lasciare la scheda senza immagine.
- Verificare identità/configurazione della figura e leggibilità del PNG; fallback mancante o incompatibile resta errore senza immagine. Un’immagine già riusata conserva la data originale, senza catene di riferimenti.
- Eseguire il collaudo dati validi → input incompleto → errore → riparazione → retry → chiusura → run senza novità, controllando DB, riepiloghi, report e retention.
- Chiudere D3 soltanto con evidenze complete di A–F e matrice hosted sul candidato esatto; consegnare punto di ripresa, senza iniziare D4.

Estendere gli esiti con `reused` e manifesto/riepilogo con origine e compatibilità. Il fallimento originale mantiene uscita 2 anche con riuso; nessun cambiamento di schema SQLite o risultati scientifici.

Fuori da questa milestone: Riuso su assenza dati, accessi transitivi a vecchie generazioni, collaudo scientifico su strumenti reali non disponibile, ottimizzazioni D5, avvio D4, merge o deploy.

## Verifiche e accettazione

- Errore con PNG compatibile, incompatibile, mancante/corrotto; no_data con PNG disponibile: solo il primo caso riusa.
- Riuso ripetuto dopo nuove pubblicazioni: data originale invariata e nuova generazione autosufficiente anche dopo cleanup dell’origine.
- Errore durante copia/manifesto/HTML e cleanup: stato coerente, report precedente protetto fino al punto finale, nessun falso successo.
- Collaudo sequenziale completo, concorrenza/interruzione/rebuild/update fallito su archivi temporanei; QA visiva nominale/parziale/riusata, suite, wheel e CI finale.

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
3. Pianificare solo D3-F, risolvendo le questioni sotto prima delle scelte
   implementative interessate. Le domande non sono decisioni già approvate.
4. Alla consegna aggiornare questa scheda e indice, handover, README, procedure
   operative, istruzioni test e contratti coinvolti. Registrare prove in
   `tests/results/d3-f-validation.md` (da creare allora), eventuale QA e ambiente.
   Aggiornare roadmap/valutazione locali senza includerle in Git.
5. Presentare scheda sintetica con baseline/commit, cambiamenti, decisioni,
   test locali/CI, limiti e punto di ripresa. Non iniziare la milestone successiva.

## Questioni da fissare nella pianificazione dettagliata

- Fissare i campi della configurazione da confrontare per compatibilità del fallback; non basta il filename e non serve invalidare i dati scientifici archiviati.
- Precisare la data originale dell’immagine rispetto alla freschezza dei dati e del run, e il comportamento su fallimento della copia.

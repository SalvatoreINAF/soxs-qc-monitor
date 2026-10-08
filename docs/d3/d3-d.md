# D3-D — Motore di pubblicazione atomica

**Stato: pianificata, non implementata.** Scheda iniziale dell’8 ottobre 2026.
Dipendenze: **D3-B e D3-C formalmente concluse**. Stima: **6–10 ore**, incluse verifiche e documentazione.
Politiche comuni e procedura di consegna: [indice D3](../d3-roadmap.md).

## Obiettivo e completamento

Preparare un insieme completo di immagini, manifesto e HTML, poi rendere visibile il report con una sola sostituzione finale. Consegnare il motore senza attivarlo nella CLI ordinaria.

La milestone è completa quando i comportamenti qui descritti sono verificati,
le regressioni richieste passano e documentazione/evidenze sono consegnate.
Distinguere consegna locale e chiusura formale hosted secondo l’indice D3.

## Stato iniziale da ricontrollare

Fotografia D2: PNG e HTML sono scritti direttamente e non esistono manifesto/generazioni. All’avvio di questa milestone ricontrollare gli esiti introdotti da C e le lease estese da B; sono prerequisiti, non lavoro da duplicare.

## Interventi e compatibilità

- Creare staging per run e generazioni autosufficienti: PNG, manifesto versionato e copia consultabile del report. Registrare identità run, stati e date; nessun riuso in questa milestone.
- Calcolare e codificare i riferimenti rispetto a ciascun HTML; verificare tutte le immagini referenziate prima della pubblicazione, anche con directory separate.
- Finalizzare prima le immagini, quindi preparare l’HTML temporaneo sul filesystem del report e sostituirlo atomicamente. Proteggere tutto con le lease B e rimuovere lo staging posseduto nelle uscite controllate.
- Esporre il motore interno verificato e metadata di pubblicazione, senza collegarlo al percorso CLI ordinario finché E non aggiunge la retention.

Definire interfaccia interna del motore e formato v1 del manifesto, usando gli esiti C. Mantenere le interfacce HTML compatibili; aggiungere al JSON v1 metadata che distinguono pubblicazione e commit SQLite.

Fuori da questa milestone: Attivazione CLI e pulizia generale delle generazioni/orfani (E), riuso precedente (F), migrazione automatica dei PNG legacy e garanzie assolute contro perdita di alimentazione.

## Verifiche e accettazione

- PNG, manifesto, validazione riferimenti, HTML o rename falliti: prima del punto finale il report precedente è integro e leggibile.
- Immagini finalizzate ma HTML non sostituito: generazione non corrente riconoscibile come orfana per E.
- Percorsi HTML/immagini separati, spazi/caratteri speciali e copia archiviata consultabile: nessun riferimento rotto o transitivo.
- Report parziale coerente e nominale equivalente; nessuna attivazione involontaria nella CLI ordinaria.

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
3. Pianificare solo D3-D, risolvendo le questioni sotto prima delle scelte
   implementative interessate. Le domande non sono decisioni già approvate.
4. Alla consegna aggiornare questa scheda e indice, handover, README, procedure
   operative, istruzioni test e contratti coinvolti. Registrare prove in
   `tests/results/d3-d-validation.md` (da creare allora), eventuale QA e ambiente.
   Aggiornare roadmap/valutazione locali senza includerle in Git.
5. Presentare scheda sintetica con baseline/commit, cambiamenti, decisioni,
   test locali/CI, limiti e punto di ripresa. Non iniziare la milestone successiva.

## Questioni da fissare nella pianificazione dettagliata

- Fissare layout delle directory, metadati di proprietà, schema del manifesto e fonte autorevole della generazione corrente, evitando due puntatori non aggiornabili insieme.
- Definire crash intermedi, filesystem differenti e protezioni contro collisioni/symlink; precisare la sincronizzazione prima del punto finale.

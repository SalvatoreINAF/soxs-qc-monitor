# D3-C — Esiti delle figure

**Stato: pianificata, non implementata.** Scheda iniziale dell’8 ottobre 2026.
Dipendenze: **D3-0; D2 formalmente chiuso**. Stima: **6–8 ore**, incluse verifiche e documentazione.
Politiche comuni e procedura di consegna: [indice D3](../d3-roadmap.md).

## Obiettivo e completamento

Ogni figura configurata ha un esito esplicito; un renderer fallito non interrompe le altre figure e non appare come una vecchia immagine valida.

La milestone è completa quando i comportamenti qui descritti sono verificati,
le regressioni richieste passano e documentazione/evidenze sono consegnate.
Distinguere consegna locale e chiusura formale hosted secondo l’indice D3.

## Stato iniziale da ricontrollare

`plotting.py` importa direttamente `pyplot`; i wrapper/test selezionano già Agg, ma manca una garanzia nell’avvio batch autonomo. I cicli dei generatori non isolano ogni figura e numerosi renderer ritornano senza esito su dati vuoti. La chiusura avviene sul percorso nominale, non sempre in `finally`. `generate_html.py` usa tutte le figure configurate senza conoscere l’esito e scrive direttamente l’HTML con percorso fisso `plots/`.

## Interventi e compatibilità

- Introdurre esiti `produced`, `no_data`, `failed` con identità figura, motivo e percorso opzionale; distinguere vuoto valido da dati invalidi.
- Isolare ogni renderer, includendo OLOC e famiglie senza storico; chiudere sempre le figure. Selezionare Agg prima di pyplot nel batch, conservando richieste interattive esplicite delle API.
- Passare gli esiti a HTML e riepilogo: schede visibili senza immagine per no_data/failed, nessun riferimento al PNG legacy fallito. Pubblicare il report parziale con uscita 2 su errore.

Aggiungere risultati strutturati ai generatori e un argomento opzionale al generatore HTML mantenendo utilizzabili le chiamate pubbliche esistenti. JSON v1 con estensioni additive; placeholder dei template personalizzati conservati.

Fuori da questa milestone: Generazioni, sostituzione atomica e correzione generale del layout dei percorsi (D), retention/attivazione (E), immagini precedenti (F). La CLI usa ancora la pubblicazione diretta: documentare questo limite intermedio.

## Verifiche e accettazione

- Un renderer fallito fra figure valide: le altre prodotte, errore visibile, uscita 2 e traceback/diagnosi.
- Selezione vuota valida, dato invalido e famiglia senza storico: stati diversi e assenza di riferimenti a PNG mancanti o vecchi.
- Eccezione dopo creazione figura o durante save: nessuna figura lasciata aperta; batch Agg verificato fuori dal setup pytest.
- QA visiva del report nominale/parziale e regressioni numeriche; compatibilità delle chiamate senza il nuovo parametro.

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
3. Pianificare solo D3-C, risolvendo le questioni sotto prima delle scelte
   implementative interessate. Le domande non sono decisioni già approvate.
4. Alla consegna aggiornare questa scheda e indice, handover, README, procedure
   operative, istruzioni test e contratti coinvolti. Registrare prove in
   `tests/results/d3-c-validation.md` (da creare allora), eventuale QA e ambiente.
   Aggiornare roadmap/valutazione locali senza includerle in Git.
5. Presentare scheda sintetica con baseline/commit, cambiamenti, decisioni,
   test locali/CI, limiti e punto di ripresa. Non iniziare la milestone successiva.

## Questioni da fissare nella pianificazione dettagliata

- Fissare il tipo degli esiti e il modo in cui ogni renderer comunica assenza dati, senza dedurla da log o dall’esistenza di vecchi file.
- Definire la presentazione degli stati nei template personalizzati e la posizione dei campi additivi nel riepilogo.

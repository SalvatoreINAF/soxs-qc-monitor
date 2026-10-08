# D3-E — Retention sicura e attivazione

**Stato: pianificata, non implementata.** Scheda iniziale dell’8 ottobre 2026.
Dipendenze: **D3-D formalmente conclusa (include B e C)**. Stima: **6–10 ore**, incluse verifiche e documentazione.
Politiche comuni e procedura di consegna: [indice D3](../d3-roadmap.md).

## Obiettivo e completamento

Attivare il motore nella CLI con limiti verificati allo spazio occupato, conservando corrente e precedente e proteggendo dati estranei.

La milestone è completa quando i comportamenti qui descritti sono verificati,
le regressioni richieste passano e documentazione/evidenze sono consegnate.
Distinguere consegna locale e chiusura formale hosted secondo l’indice D3.

## Stato iniziale da ricontrollare

D2 limita già i log in `scripts/batch.py`, ma non le immagini; i backup SQLite restano gestiti dall’operatore. All’avvio ricontrollare il motore D, i marker delle directory possedute e il punto di pubblicazione. La CLI è ancora sul percorso precedente fino a questa milestone.

## Interventi e compatibilità

- Validare `plots.publication`: `retained_generations=2` (almeno due), `orphan_max_age_hours=24` e `max_orphan_staging=2`; controllare collisioni con input, config, DB, lock, summary e backup.
- Dopo pubblicazione riuscita eliminare generazioni eccedenti sotto le stesse lease, proteggendo corrente/precedente e riferimenti degli HTML conservati.
- All’avvio operativo rimuovere orfani oltre età o limite numerico; escludere run attivo. Non seguire symlink e cancellare soltanto directory riconosciute del monitor.
- Integrare il motore D nella CLI; `--no-plots` salta pubblicazione e relativo cleanup, dry-run/preflight restano senza scritture. Cleanup fallito dà uscita 2, senza ritirare il report già valido.

Aggiungere opzioni YAML con default centralizzati e tipi/limiti validati; estendere `publication` nel JSON v1 con esito cleanup. Non modificare retention dei backup SQLite o API di acquisizione.

Fuori da questa milestone: Riuso delle immagini (F), cleanup di PNG legacy/file estranei e backup, cache HTTP o deploy automatici. Documentare che un browser con HTML molto vecchio può perdere le immagini eliminate.

## Verifiche e accettazione

- Molte pubblicazioni successive: esattamente il numero configurato di generazioni, tutti i riferimenti correnti e conservati validi.
- Fallimenti ripetuti e interruzioni: staging limitati anche entro 24 ore, run attivo protetto e nessuna generazione orfana pubblicata.
- Symlink, directory con nomi simili, marker invalidi, immagini legacy e backup: nessuna cancellazione estranea.
- Cancellazione impedita: diagnosi e codice 2, report pubblicato disponibile; config invalida e no-plots/dry-run/preflight senza effetti non previsti.

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
3. Pianificare solo D3-E, risolvendo le questioni sotto prima delle scelte
   implementative interessate. Le domande non sono decisioni già approvate.
4. Alla consegna aggiornare questa scheda e indice, handover, README, procedure
   operative, istruzioni test e contratti coinvolti. Registrare prove in
   `tests/results/d3-e-validation.md` (da creare allora), eventuale QA e ambiente.
   Aggiornare roadmap/valutazione locali senza includerle in Git.
5. Presentare scheda sintetica con baseline/commit, cambiamenti, decisioni,
   test locali/CI, limiti e punto di ripresa. Non iniziare la milestone successiva.

## Questioni da fissare nella pianificazione dettagliata

- Fissare ordinamento degli orfani e criteri di riconoscimento, inclusi artefatti finalizzati prima di un fallimento HTML, usando il contratto D.
- Definire il controllo dei limiti e la diagnosi della retention non garantita quando il filesystem impedisce cleanup.

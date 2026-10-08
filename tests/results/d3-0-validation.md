# D3-0 — Verifica e consegna documentale, 8 ottobre 2026

**D3-0 completato su `dev`; D3-A…F soltanto pianificate.** Nessuna modifica
applicativa. Stato e ripresa: [handover](../../docs/handover.md);
articolazione e sei schede: [indice D3](../../docs/d3-roadmap.md).

## Baseline e confronto con il codice

HEAD iniziale/finale `957aa968578613612477e00f34998f72ea2977a3`, branch `dev`,
working tree inizialmente pulito, un commit documentale oltre `origin/dev`
(`9f666b0`). D2 chiuso sul codice `7f0f657`, candidato CI `9f666b0`;
[evidenze D2](d2-validation.md) conservate senza modifiche.
Pacchetto 1.2.0 e schema SQLite 1 invariati. D3-0 consegnato in modifiche locali,
senza creazione di commit; un futuro SHA va registrato dopo la sua creazione.

Confronto dei documenti con le responsabilità effettive:

- `main.py` e `acquisition.py`: parsing DSOL/OLOC e acquisizione per file già
  protetti; le schede richiedono di completare i confini, non riscriverli.
- `detector_linearity.py`: fit separati, calcolo complessivo senza confine
  di eccezione per sequenza; transazione giorno/braccio D2 conservata.
- `locking.py`, `rebuild.py`, `scripts/batch.py`: lease dei writer/rebuild
  esistente, pubblicazione/update fuori da quella durata; timeout supervisore già presente.
- `plotting.py`, `generate_html.py`, `run_result.py`: esiti per figura,
  manifesto, pubblicazione atomica e retention ancora da implementare.
- `storage.py`: timeout implicito SQLite; nessuna politica di retry esplicita.

## Verifiche D3-0

- Completezza di indice e sei schede: obiettivo, baseline, dipendenze, confini,
  interfacce, test/accettazione, ripresa/consegna, stima e questioni aperte.
- Coerenza ordine 0/A/B/C/D/E/F e dipendenze, decisioni comuni e stime:
  2–4 ore D3-0, 34–52 ore A–F, totale 36–56 ore (5–7 giornate), attese CI escluse.
- Collegamenti locali nei documenti D3 e handover; nuovi rimandi README,
  roadmap e valutazione locali; nessuna dipendenza dalla chat per la ripresa.
- `git diff --check` e controllo whitespace dei nuovi documenti.
- Confine delle modifiche: soltanto Markdown; codice/config/dati/versione
  invariati, risultati D1/D2 conservati; `reference_docs/` ancora ignorata.

Verifiche eseguite con comandi Git e controllo Python temporaneo, senza aggiungere
una suite applicativa al repository. Nessuna nuova esecuzione di pytest, build,
CI o QA visiva richiesta per questa consegna documentale.

Esito del controllo finale: **PASS**, 83 collegamenti locali verificati,
sei schede complete con stato pianificato; tre documenti già versionati modificati
e otto nuovi documenti, più due riferimenti locali ignorati. Set dei file conforme
alla consegna solo Markdown; evidenze D1/D2 e metadati del pacchetto identici a HEAD.
`git diff --check` e whitespace dei nuovi documenti verdi.

## Evidenza precedente, distinta dalla consegna documentale

Durante la pianificazione D3 sulla stessa baseline e prima di modificare i
documenti è stato eseguito:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error
```

**315 PASS in 128,22 s**, Python 3.12.15, pytest 8.4.2, macOS; uscita 0,
nessun fallimento o skip. Il percorso temporaneo non è una dipendenza del
progetto. Questo risultato verifica codice D2 invariato, non funzionalità D3
e non sostituisce nuove verifiche hosted delle milestone applicative.

## Scheda sintetica di consegna

Consegnati: roadmap locale aggiornata, indice versionato e sei schede,
richiamo nella valutazione locale, README e handover allineati. Le questioni
implementative aperte sono esplicite e vanno risolte durante la pianificazione
della rispettiva milestone. Motore D non attivo prima della retention E;
riuso precedente previsto solo in F.

Prossima attività: **pianificazione dettagliata D3-A**, su nuova richiesta,
leggendo la scheda e verificando stato Git e dipendenze. Nessun D3-A/D4,
commit, push, merge, deploy, modifica scheduler o rebuild dei dati dell’utente.

# D3-C — Consegna locale, 9 ottobre 2026

**D3-C consegnata e verificata localmente su `dev` il 9 ottobre 2026.**
Pacchetto **1.5.0**, SQLite **schema 1**. Commit applicativo **`45a7e3e5a2c8133120e185a42ded9e6f4256049f`**.
D3-A/B restano formalmente chiuse; **CI hosted D3-C pendente, D3-D…F non avviate**.

La milestone è implementata secondo il piano concordato conservato sotto.
[Evidenze](../../tests/results/d3-c-validation.md),
[ambienti](../qa/d3-c-environments.json), [handover](../handover.md).
490 PASS per ciascuno dei tre interpreti locali, wheel isolata e QA verificate.

Le tre decisioni sono concordate e implementate: API fail-fast per default,
scarti parziali visibili senza errore artificiale, figura fallita se una serie
identificabile perde tutti i campioni utilizzabili. Questo vale anche per
ordini DSOL, sequenze/modalità DETLIN e geometrie OLOC.
Il contesto di ciascun renderer registra l'esito di save riuscito e gli scarti;
`finally` chiude le figure della chiamata. Non vengono usati log/mtime/file
precedenti per decidere produced. I campi degli scarti sono per serie/fase di
preparazione, non un conteggio di righe uniche fra query differenti.

Ripresa: esclusivamente verifica/chiusura hosted C dopo pubblicazione richiesta;
nessun D3-D. Limiti di pubblicazione diretta/percorsi/retention restano quelli
previsti. Il piano storico sotto non descrive più lavoro da avviare.

---

# D3-C — Piano dettagliato degli esiti delle figure

**Piano del 9 ottobre 2026, successivamente concordato e implementato.**
Branch `dev`, baseline `08baf0c19bb839da23b46e5e942e9fff6db4d658`, working tree
inizialmente pulito e allineato a `origin/dev`. Pacchetto **1.4.0**, SQLite
**schema 1**, invariati in questa consegna documentale.
Dipendenza formale D3-0/D2; integrare sul codice corrente di D3-A e D3-B,
entrambe formalmente chiuse. [Indice](../d3-roadmap.md), [handover](../handover.md),
[verifica della pianificazione](../../tests/results/d3-c-planning.md).

## Obiettivo e perimetro

Per ogni figura del batch completato, fornire un esito esplicito: `produced`,
`no_data` oppure `failed`. Un guasto locale lascia proseguire le figure
indipendenti; il report mostra l'errore e la CLI termina con codice 2.
Le immagini precedenti non devono apparire come risultati del nuovo tentativo.

Questa sezione conserva il perimetro del piano originario. La consegna
applicativa e le evidenze correnti sono riportate sopra. D3-D/E/F non vengono avviate. Restano fuori:
generazioni, manifesti persistenti di pubblicazione, sostituzione atomica,
correzione generale dei percorsi HTML/PNG, retention e riuso di immagini.
La pubblicazione di C resta diretta e richiede il layout HTML/`plots/`.

## Stato verificato sul codice corrente

| Componente | Comportamento attuale | Intervento C |
|---|---|---|
| `main.py` | Importa plotting a livello modulo; salta QC/DSOL vuoti; letture e renderer sotto una sola fase | Backend scelto prima dell'import; orchestrare tutti gli esiti, comprese famiglie vuote/fallite |
| `plotting.py` | Dieci tipi di grafico; generatori senza risultati e senza isolamento, OLOC separato | Contratto comune e raccolta degli esiti per figura |
| Selezione/preparazione | Colonne mancanti e valori inutilizzabili spesso diventano DataFrame vuoti | Distinguere assenza legittima da dati invalidi |
| Figure Matplotlib | Close sul percorso nominale; errori durante disegno/save possono lasciare figure aperte | Gestione esplicita della figura e `finally` |
| `generate_html.py` | Tutte le figure configurate diventano link/immagini; nessuna conoscenza degli esiti | Schede di stato, immagini soltanto per `produced` |
| `RunResult` | JSON v1 con famiglie, errori, fasi, storage e coordination; errori danno codice 2 | Campi additivi `plots` e `report` |
| D3-B | Protezioni fino a HTML e riepilogo, inclusi timeout dei figli | Preservare e verificare durante report parziale |

La validazione D2 rende già unici nomi e filename, verifica tipi/query/bracci
prima delle scritture. Non duplicarla nei renderer. Sono da modificare anche
`_apply_filters`, `_apply_time_range` e preparazione delle serie: un semplice
wrapper intorno a `savefig` non risolverebbe le false assenze dati.
OLOC con modello selezionato ma metadati/gradi invalidi è oggi saltato.
L'errore reale di salvataggio è già coperto dalla suite, che deve chiudere le
figure manualmente: è una regressione significativa da migliorare.
Le evidenze D3-B registrano 405 PASS per ciascuno dei quattro job hosted sul
candidato `7a952c5`; HEAD successivo `08baf0c` contiene solo documentazione.
Non è stata eseguita una nuova CI in questa pianificazione.

## Decisioni concordate per lo sviluppo

Scelte progettuali concordate con l’utente e implementate nella consegna C.
Non restano domande bloccanti; eventuali scostamenti vanno motivati nella
consegna prima di considerarli parte del contratto.

1. **Tipo e identità.** Introdurre un piccolo modulo indipendente da pyplot
   (ad esempio `figure_result.py`) con dataclass `FigureResult`. Campi:
   `name`, `type`, `filename`, `state`, `reason_code`, `reason`, `path`,
   `error_type` e diagnostica degli scarti se pertinente. `name` è la chiave
   già univoca nella configurazione; filename identifica la destinazione.
   `path` è valorizzato soltanto per `produced` e serializzato come stringa;
   gli altri stati usano null. I motivi hanno codice stabile e testo leggibile.
   Nessun esito dedotto dai log o dall'esistenza/mtime di PNG preesistenti.
   `produced` viene emesso solo dopo un salvataggio riuscito in questo tentativo.
2. **Assenza o invalidità.** Storico vuoto, filtro valido senza corrispondenze,
   intervallo temporale valido vuoto e campioni insufficienti per il renderer
   sono `no_data` (esempio: XY con meno di due giorni comuni). Su dataset non
   vuoto, colonna richiesta assente, timestamp tutti inutilizzabili, campioni
   selezionati tutti invalidi/non finiti o modello OLOC privo di metadati/
   coefficienti richiesti sono `failed`. Controllare la struttura necessaria
   prima che un filtro con colonna assente possa svuotare artificialmente i dati.
   Conservare gli scarti già previsti quando restano campioni validi, tracciandoli;
   NULL scientificamente ammessi, fit DETLIN mancanti/saturazione e serie vuote
   legittime non diventano errori. Una figura può essere prodotta con serie
   legittimamente vuote; una serie strutturalmente invalida rende fallita la
   figura. Formule, selezione latest/all, soglie e tolleranze restano invariate.
3. **API e isolamento.** I renderer restituiscono un risultato esplicito su
   successo/assenza; gli errori continuano a sollevare eccezioni. I generatori
   restituiscono `list[FigureResult]` (lista vuota senza figure) e aggiungono
   il solo parametro keyword `continue_on_error=False`. Il default conserva
   la propagazione degli errori attesa dalle API esistenti; la CLI passa True
   e converte ogni `Exception` in `failed`, con traceback nel log, proseguendo.
   Tutti e dieci i renderer, compreso OLOC, usano la stessa disciplina.
   Non intercettare `KeyboardInterrupt`, `SystemExit` o altre `BaseException`.
   Nessun retry del renderer: i retry SQLite D3-A restano separati.
4. **Figure e backend.** Usare handle espliciti e `try/finally` in ogni renderer;
   chiudere soltanto le figure create dalla chiamata, anche su errore e dopo
   `show()`, senza `close('all')` che chiuderebbe figure altrui. La CLI con
   `plots.show=false` sceglie Agg prima di importare plotting/pyplot, anche con
   `MPLBACKEND` esterno non adatto al batch. Spostare l'import applicativo di
   plotting al punto corretto dopo configurazione validata e sotto le protezioni
   D3-B. `plots.show=true` è richiesta interattiva esplicita; conservare la scelta
   del backend. Importare direttamente le API non deve imporre Agg. Non
   importare plotting in dry-run/preflight/--no-plots se non necessario.
5. **Lettura dello storico.** Isolare le letture per dataset di rendering
   (QC, DSOL linee, DSOL statistiche, coppia OLOC, DETLIN). Dopo esaurimento
   della politica D3-A, errore di lettura implica `failed` per tutte le figure
   dipendenti, una causa di lettura identificabile e prosecuzione degli altri
   dataset. Non passare un DataFrame vuoto come sostituto di una lettura fallita.
   Eliminare i salti QC/DSOL vuoti: i generatori devono emettere `no_data`.
   Aggregare senza duplicati nell'ordine YAML e verificare copertura esatta.
   Un errore globale precedente al rendering non simula figure mai tentate.
6. **HTML compatibile.** Aggiungere `figure_results=None` a
   `generate_html_report`. Senza parametro conservare il comportamento legacy
   delle chiamate dirette. La CLI passa sempre la raccolta completa; con esiti
   espliciti rifiutare raccolte incoerenti/incomplete anziché ricadere su PNG
   legacy. Mostrare titolo, stato e motivo nelle schede `no_data`/`failed`,
   senza `<img>` o link all'immagine. Usare escaping HTML per tutti i valori.
   Mantenere `{{ page_title }}` e `{{ sections }}`: gli stati appartengono al
   frammento sections, con testo leggibile anche senza nuovo CSS nei template
   personalizzati. Non richiedere nuovi placeholder. Gli HTML legacy senza
   esiti non ottengono automaticamente la garanzia contro immagini obsolete.
7. **JSON e codici.** JSON resta v1. Aggiungere `plots` con `state`, `counts`
   (`produced`, `no_data`, `failed`) e `figures` serializzate; stato aggregato
   `completed`, `partial`, `failed` o `skipped`. `partial` indica almeno un
   fallimento e almeno un esito non fallito; tutti falliti danno `failed`.
   Senza fallimenti è `completed`, anche quando tutto è `no_data`.
   `report` contiene `state` (`published`, `failed`, `skipped`) e `path` soltanto
   dopo scrittura HTML riuscita. Un errore figura/lettura alimenta anche `errors`
   con fase, figura/dataset, tipo e motivo, così il codice 2 prevale sul codice 1
   di acquisizione parziale. Con `no_data` soltanto: codice 0, oppure 1 se
   acquisizione parziale. Dry-run/preflight/--no-plots: rendering/report skipped,
   elenco figure vuoto, nessun output aggiuntivo. Una fase eseguita non equivale
   a successo di tutte le figure: usare gli esiti aggregati per giudicarla.
8. **Errori di pubblicazione.** Provare a scrivere il report anche con tutte
   le figure `failed`/`no_data`. Errore HTML: codice 2 e report failed, senza
   affermare che il vecchio report sia aggiornato. Nessuna cancellazione di
   PNG legacy, nessun fallback/retention. C impedisce riferimenti obsoleti nel
   nuovo HTML, ma non protegge da interruzioni durante scritture dirette o da
   client che stanno ancora leggendo il report precedente: è il limite D/E.

## Sequenza di implementazione e stima

| Attività | Risultato reviewabile | Tempo di lavoro |
|---|---|---|
| 1. Contratto e orchestrazione | Tipo/serializzazione, mappa dataset→figure, casi vuoto/invalido | 1 ora |
| 2. Renderer e backend | Dieci renderer con esiti e cleanup; API compatibili; Agg batch | 3–4 ore |
| 3. CLI, HTML e riepilogo | Isolamento letture/figure, report parziale, JSON e codici coerenti | 2–3 ore |
| 4. Verifiche | Casi mirati, regressioni 3.11/3.12/3.13, wheel e QA visiva | 3–4 ore |
| 5. Consegna | Documentazione, evidenze, scheda sintetica e handover | 1–2 ore |

**Totale: 10–14 ore, circa 1,5–2 giornate di lavoro**, incluse verifiche e
consegna, escluse attese CI e accettazione sui dati reali. Supera la stima
preliminare 6–8 ore: comprende classificazione nei dieci renderer, compatibilità
API, guasti delle letture e prova backend fuori dall'ambiente pytest.
È una stima, non un consuntivo o un benchmark del batch. La stima complessiva
storica D3 passa da 38–58 a **42–64 ore** sostituendo soltanto la quota C;
non è una stima del lavoro ancora residuo dopo A/B.

## Verifiche previste e criteri di accettazione

Creare `tests/test_d3c_rendering.py`; estendere i test esistenti solo quando
il contratto effettivo lo richiede, conservando le prove di compatibilità.

| Verifica | Attesa |
|---|---|
| Tutti i dieci renderer: dati validi e assenza legittima | `produced`/`no_data` espliciti; PNG nuovi validi solo per produced |
| Filtri senza corrispondenze, XY insufficiente, famiglia senza storico | no_data; copertura figure completa, codice non artificialmente 2 |
| Colonna filtro/asse assente, timestamp invalido, valori tutti non finiti | failed distinto da assenza; motivo stabile |
| OLOC modello valido ma metadati/gradi/coefficiente invalidi | failed; altre figure prodotte |
| DETLIN NULL ammessi, saturazione, latest/all; serie miste | Nessuna regressione scientifica; scarti leciti distinti da struttura invalida |
| Guasto fra due figure valide, anche OLOC | Entrambe le valide prodotte; errore visibile e traceback; CLI 2 |
| Errore dopo creazione, disegno, save reale e show | Nessuna figura della chiamata aperta; figura preesistente del chiamante preservata |
| Errore reale di lettura di un dataset dopo preflight | Falliscono le figure dipendenti; indipendenti proseguono; causa registrata |
| PNG sentinella precedente e esito no_data/failed | Nuovo HTML senza img/href sentinella; file non cancellato o riusato |
| HTML normale, misto, tutto vuoto, tutto fallito | Schede VIS/NIR leggibili e conteggi/esiti coerenti; escaping verificato |
| Template personalizzato con placeholder esistenti | Stati visibili dentro sections senza CSS/placeholder nuovi obbligatori |
| API senza nuovi parametri e modalità tollerante | Posizionali compatibili; eccezione legacy conservata; nuova raccolta affidabile |
| CLI pulita senza MPLBACKEND e con backend GUI esterno | Processo autonomo con show=false usa Agg prima di pyplot |
| API/backend interattivo esplicito | Nessuna imposizione globale; test controllato senza richiedere un display in CI |
| CLI 0/1/2, JSON log/file, errore HTML/riepilogo | Precedenza 2; report published solo se riuscito; JSON v1 additivo e finito |
| Dry-run/preflight/--no-plots | Nessun PNG/HTML nuovo; diagnostica skipped senza falsi esiti |
| Contesa D3-B durante report parziale | Protezioni fino a HTML/riepilogo; nessuna nuova sovrapposizione |

Usare DB/FITS e output sintetici temporanei. Guasti di filesystem/SQL reali
quando praticabili; injection controllata per errori di disegno e verifica
backend, senza sostituire la catena scientifica nelle regressioni nominali.
Nessun confronto pixel-per-pixel; conservare aspettative analitiche e tolleranze
`rel=1e-10`, `abs=1e-8`. Ispezionare tavole nominale/parziale VIS/NIR e salvare
QA in `docs/qa/` (inclusi renderer OLOC/DETLIN e messaggi di assenza/errore).

Comandi dalla radice, in sequenza e con lo stesso interprete dell'ambiente:

```sh
python -m pytest tests/test_d3c_rendering.py tests/test_scientific_rendering.py tests/test_run_result.py -ra --tb=short -W error
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-d3c-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
/path/to/installed-env/bin/python -m pip check
```

Seguire [istruzioni ambiente](../../tests/README.md): riferimento Python 3.12
fissato, compatibilità locale 3.11/3.13, wheel in ambienti nuovi e checker fuori
checkout. Estendere il checker per modulo degli esiti, report parziale e batch
Agg senza ereditare la garanzia del workflow. Chiusura formale: CI Linux
3.11/3.12/3.13 e macOS 3.12 sul candidato esatto, con build/installazione isolata;
verifiche locali e hosted distinte. La CI D3-B non convalida C.

## Consegna dello sviluppo e handover obbligatori

Incrementare il pacchetto a **1.5.0** solo alla consegna applicativa, conservare
schema 1. Aggiornare questa scheda, indice D3, README, operations, contratti D2
per le sole estensioni pertinenti, tests/README e handover. Creare
`tests/results/d3-c-validation.md` e `docs/qa/d3-c-environments.json` con prove
realmente eseguite, durate, versioni e limiti. Aggiornare anche roadmap e
valutazione in `reference_docs/`, intenzionalmente ignorata da Git.

La scheda sintetica finale deve contenere baseline, commit applicativo,
candidato CI distinto dai commit documentali, funzionalità, decisioni adottate,
test locali/hosted con evidenze, limiti, pendenze e punto di ripresa. Se la CI
non è disponibile, dichiarare consegna locale con chiusura hosted pendente.
Nessun push/merge/deploy/rebuild operativo implicito. Fermarsi a C; D richiede
una nuova richiesta dopo la chiusura di C.

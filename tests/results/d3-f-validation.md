# D3-F — Consegna locale e validazione, 9 ottobre 2026

**D3-F implementata localmente su dev, 1.8.0/schema 1; CI hosted F/D3 pendente.**
A–E restano formalmente chiuse. D4 non avviata.
Baseline `9b38ea507e45887b35433fc379e134fa543f4936`, checkout inizialmente pulito.
Il commit applicativo e gli esiti finali sono registrati nell'handover e nella
sezione finale di questo documento; non è stato pubblicato un candidato F.
[Audit e decisioni](d3-f-planning.md), [contratto F](../../docs/d3/d3-f.md).

## Cambiamenti e compatibilità

Riuso soltanto su failed dal manifesto corrente, con verifica per figura/query,
percorso database/schema e configurazione DETLIN pertinente. PNG copiato nello
staging e verificato, generazioni autosufficienti, data UTC e UUID originari
invariati nei riusi ripetuti. Nessun riuso no_data o ricerca nei predecessori.
Metadati FigureResult/manifesto/JSON v1 additivi, conteggio reused, errore
originale e uscita 2 conservati. HTML corrente/archiviato esplicito con data.

Scelte approvate: manifesti E leggibili ma non candidati; copia fallita degrada
a report parziale solo se la pulizia riesce, altrimenti blocca; data originale
è produzione dell'immagine, non data dei dati. Per F, verifica strutturale degli
HTML esistenti e verifica individuale dei PNG candidati: fonte danneggiata resta
senza immagine, senza indebolire marker/proprietà/percorsi o validazione dei nuovi
PNG. Legacy mantiene i controlli PNG rigorosi. CSS impedisce che gli errori
lunghi alterino le colonne della griglia.

46 nuovi casi F, 655 complessivi. Test D/E legacy adattati creando realmente
manifesti pre-F con marker/hash coerenti, conservando l'aspettativa di rifiuto
dei PNG legacy danneggiati. Nessuna tolleranza scientifica modificata.
Acquisizione, storage/schema, scienza, retry, main, coordinamento e supervisore
sono identici byte per byte alla baseline (manifesto ambienti).

## Verifiche

- F mirato: **46 PASS / 17,54 s**, Python 3.12.15, `-W error`.
- F più regressioni dei manifesti legacy: **53 PASS / 16,55 s**, prima dei due
  nuovi casi di interruzione; distinto dalla suite finale di 655 casi.
- Suite complete macOS 3.11/3.12/3.13: esiti/durate finali nella sezione finale
  e in [manifesto ambienti](../../docs/qa/d3-f-environments.json).
- Linux Docker ARM64 Python 3.12.15, utente uid/gid 1000 non privilegiato:
  **165 PASS / 24,63 s, 0 SKIP**, suite D3-D/E/F. Verifica reale /tmp versus
  /dev/shm e permessi. Repository montato read-only, copia sotto /tmp;
  container temporaneo rimosso. Non è matrice hosted né suite Linux completa.
- Wheel **1.8.0**, checker fuori checkout e pip check PASS in tre venv isolati
  D3-D riutilizzati con reinstallazione della nuova wheel senza dipendenze.
  Il checker verifica anche errore reale di save, riuso/provenienza e uscita 2.
  Confronto checkout/wheel/installed e hash nel manifesto ambienti.
- CLI reale: QC valido → DSOL FITS incompleto → reale errore di save e riuso →
  riparazione FITS → retry → chiusura DSOL → run senza novità → rebuild sintetico.
  Controlli SQL indipendenti e snapshot verificano dati/registri/idempotenza;
  report/summary/retention coerenti. Il test forza solo il punto di guasto save,
  senza sostituire acquisizione, rendering o persistenza.
- Regressioni B su contesa, gruppi di processi, rebuild e update fallito incluse
  nelle suite complete. Nuovi test F interrompono copia/finalizzazione e
  verificano report precedente, lease liberate, orfani riconoscibili e retry.

QA generata con renderer reali da `scripts/render_d3f_qa.py`, screenshot Chrome
headless con profili temporanei. Ispezioni finali e file:
[nominale](../../docs/qa/d3-f-report-nominal.png),
[parziale](../../docs/qa/d3-f-report-partial.png),
[riusata](../../docs/qa/d3-f-report-reused.png),
[archiviata](../../docs/qa/d3-f-report-archive.png).
Riferimenti relativi validi fra destinazioni separate e nomi Unicode/speciali;
nessuna immagine in failed/no_data; data ed errore espliciti per reused.

## Tentativi intermedi

La prima regressione C/D/E aveva 218 PASS, 2 FAIL, 1 SKIP: i due vecchi casi
PNG costruivano ora manifesti F, per i quali è richiesto recupero da PNG
illeggibili. Le fixture sono state rese esplicitamente legacy; i due contratti
legacy passano insieme ai nuovi casi F. Nessuna aspettativa scientifica cambiata.

Primo F mirato: 43 PASS, 1 FAIL. La nuova iniezione di guasto non creava la
cartella padre e quindi falliva prima di lasciare una copia parziale. Corretta
la fixture, senza modifica al comportamento applicativo, e provato il blocco
quando la rimozione della copia realmente presente fallisce.

Prima QA nominale aveva screenshot incompleto: rigenerata con attesa del
rendering. La successiva ispezione del riuso ha mostrato colonne sbilanciate
con messaggi lunghi: aggiunti min-width e overflow-wrap, poi rigenerata QA,
ricostruita wheel e ripetuti checker sui tre interpreti. La suite 3.13 include
il template finale; suite C/F mirata finale 3.12 registrata sotto. Le suite
3.11/3.12 precedenti alla sola correzione CSS verificano gli stessi moduli Python.

La prima suite completa Python 3.13 aveva 653 PASS, 1 FAIL, 1 SKIP / 174,46 s:
ResourceWarning per una connessione SQLite della nuova fixture che aggiorna il
database, rilevato durante la raccolta garbage del test successivo. Il context
manager SQLite gestisce commit/rollback ma non chiude la connessione: aggiunta
chiusura esplicita, senza cambiare codice applicativo o filtri dei warning.
Ripetuti F mirato 3.13 e suite completa 3.13; esiti finali sotto.

## Riproduzione e limiti

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d3f-verified312.xml
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d3f-verified311.xml
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d3f-verified313.xml
/private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d3f-wheel
/private/tmp/qc-d3d-installed312/bin/python scripts/check_installation.py
/private/tmp/qc-d3d-installed312/bin/python -m pip check
/private/tmp/qc-d1-reference/bin/python scripts/render_d3f_qa.py /private/tmp/qc-d3f-qa
```

Tutti i dati sono sintetici/temporanei. Nessuna accettazione su strumenti reali
né misura della fine riduzione. Database identificato per percorso/schema;
nessun UUID di archivio o confronto dei contenuti. Nessuna soglia massima di età
per immagini riusate: leggere la data originale. F non ripara le vecchie
immagini archiviate danneggiate. Limiti E su quantità/età, browser e hosting
conservati. Stima 12–16 ore incluse verifiche/handover, escluse attese CI;
non consuntivo. reference_docs aggiornata localmente e ignorata da Git.

**CI hosted F/D3 pendente** sul candidato esatto Linux 3.11/3.12/3.13 e macOS 3.12.
La CI E non è attribuita a F. Nessun push, merge, deploy, modifica scheduler o
rebuild operativo. **Fermata a D3-F; D3 non ancora formalmente chiusa; nessun D4.**


## Esiti finali e consegna locale

Commit applicativo **`f416da6be0b50ef50d1c6640be7152610a1210e3`**.
Il successivo commit è documentale: registra evidenze/handover, senza nuovo
codice applicativo. Nessun candidato F pubblicato o verificato hosted.

| macOS 15.8 ARM64 | Suite con -W error | Durata pytest | Wheel/checker/pip check |
|---|---|---|---|
| Python 3.12.15 | 654 PASS, 1 SKIP | 189,31 s | PASS |
| Python 3.11.17 | 654 PASS, 1 SKIP | 173,83 s | PASS |
| Python 3.13.16, ripetizione finale | 654 PASS, 1 SKIP | 172,45 s | PASS |

Skip soltanto per secondo filesystem scrivibile assente sul Mac, prova passata
nel Linux mirato: **165 PASS, 0 SKIP / 24,63 s**. Nessun FAIL/XFAIL/XPASS finale.
Le durate JUnit, leggermente diverse dal totale pytest, sono nel manifesto.
C/F 3.12 sul template finale: **131 PASS / 41,19 s**; fixture di aggiornamento
database con chiusura esplicita riprovata su 3.12: **1 PASS / 9,40 s**.
F mirato 3.13 dopo correzione fixture: **46 PASS / 16,71 s**. La suite completa
3.13 finale verifica insieme fixture corretta e template finale. Docker ha
verificato gli stessi sorgenti applicativi prima della sola correzione CSS.

Tutti i moduli/template della wheel sono identici byte per byte a checkout e
installazioni isolate 3.11/3.12/3.13 (import fuori checkout con -I).
QA finale nominale/parziale/riusata/archiviata ispezionata; link documentali
e git diff --check PASS. Dati/config operativi, sorgenti scientifici, acquisizione,
storage/schema/retry, coordinamento, supervisore e workflow invariati.

Documentazione, scheda/indice, procedure/contratti, README/test e reference_docs
locali allineati. [Handover](../../docs/handover.md) è il punto di ripresa.
**Consegna locale completata; chiusura formale F/D3 hosted pendente.**
Fermarsi a F: verificare dev/HEAD/working tree, pubblicare solo su richiesta,
controllare la matrice sullo SHA esatto e registrare la chiusura. Nessun D4.

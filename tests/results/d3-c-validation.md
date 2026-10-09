# D3-C — Validazione locale e hosted, 9 ottobre 2026

**D3-C consegnata e verificata localmente su `dev` il 9 ottobre 2026.**
Pacchetto **1.5.0**, SQLite **schema 1**. Commit applicativo **`45a7e3e5a2c8133120e185a42ded9e6f4256049f`**.
D3-A/B restano formalmente chiuse; **D3-C formalmente chiusa, D3-D…F non avviate**.

## Baseline e decisioni

Baseline `08baf0c19bb839da23b46e5e942e9fff6db4d658` su dev, checkout inizialmente
con i soli documenti della pianificazione già modificati, preservati.
[Audit pianificazione](d3-c-planning.md): 82 PASS / 81,80 s sul codice 1.4.0.
Le scelte sono state **concordate con l'utente** prima dello sviluppo:
API dirette fail-fast per default, batch tollerante; scarti parziali segnalati
senza codice 2 quando resta una serie valida; serie interamente guasta rende
fallita la figura. NULL ammessi e saturazione non sono errori di dati.

## Funzionalità e prove aggiunte

85 casi in `test_d3c_rendering.py`: dieci renderer con produced/no_data/failed,
input vuoti, misure parzialmente invalide/tutte invalide, colonne mancanti;
serie guasta in grafici multipli e in ordini DSOL, statistiche, sequenze/modalità
DETLIN e geometrie OLOC; metadati, gradi, coefficienti e timestamp OLOC invalidi;
assenza legittima e XY insufficiente; salvataggio reale su destinazione bloccata,
injection disegno/save/show, cleanup anche su errore e figure altrui preservate.

Compatibilità API fail-fast e raccolta opzionale; PNG precedenti conservati ma
esclusi da link/immagini del nuovo report su no_data/failed; template personalizzato
ed escaping; raccolte di esiti incomplete/duplicate/incoerenti rifiutate prima
della scrittura. Batch in subprocess senza MPLBACKEND e con TkAgg esterno usa
Agg prima di pyplot; import API conserva un backend esplicito.

CLI: errore di lettura di un dataset (injection della frontiera di lettura),
altro dataset reale indipendente; errore di save reale e scrittura HTML fallita;
JSON log/file identici, v1 e report published/failed corretti; codici 0/1/2,
precedenza su acquisizione parziale, report con tutte le figure fallite/vuote,
skip di dry-run/preflight/no-plots e lease conservate durante report fallito.
Tutte le fixture/uscite sono sintetiche e temporanee.

Il test D3-B delle protezioni su plots/HTML/summary configura ora una figura
reale: prima dipendeva da chiamate vuote che C correttamente salta.
Nessuna aspettativa di protezione ridotta, nessuna tolleranza allargata.

## Comandi e risultati finali

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error
/private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d3c-wheel
/private/tmp/qc-d3c-installed312/bin/python scripts/check_installation.py
/private/tmp/qc-d3c-installed312/bin/python -m pip check
```

Checker/pip check ripetuti in nuovi venv 3.11/3.13. `pip check` verde anche nei
tre ambienti sorgente. Suite in sequenza per le protezioni esclusive D3-B.

| macOS 15.8 arm64 | Suite `-W error` | Durata | Wheel/checker/pip check |
|---|---|---|---|
| Python 3.12.15 | 490 PASS | 164.50 s | PASS |
| Python 3.11.17 | 490 PASS | 144.67 s | PASS |
| Python 3.13.16 | 490 PASS | 146.02 s | PASS |

Nessun FAIL, warning, skip o XFAIL nelle suite finali. 405 casi precedenti più
85 nuovi. Prova mirata precedente: 81 PASS / 32,67 s; rafforzamento serie:
86 PASS / 31,85 s (85 casi C e regressione API del filtro temporale).
Le durate sono della suite sintetica, non benchmark dei batch operativi.

Ambienti e hash: [manifesto](../../docs/qa/d3-c-environments.json).
Wheel 1.5.0, SHA256 **`b993d7039afe500dd4aa23e46ed21011537ace1d449c77c6a0351fc52a9b380d`**. File Python/template
confrontati byte per byte con checkout e tre installazioni: identici.
Checker -I fuori checkout verifica moduli/template, CLI, dry-run/rebuild,
report parziale con guasto save reale e Agg autonomo senza garanzia del workflow.

## Iterazioni diagnostiche e QA

Prima suite completa: 480 PASS / 6 FAIL. Tre FAIL erano il sandbox che vietava
`ps` ai test timeout D3-B (PermissionError), due una fixture D3-B senza figure,
uno il tipo timestamp restituito da `_apply_time_range`. Conservato il ritorno
originale del filtro; configurate vere figure nella prova di lease; suite finali
eseguite con accesso a ps, senza modificare il supervisore o saltare prove.
La prima suite 3.13 ha dato 489 PASS / 1 FAIL per due connessioni SQLite
non chiuse nella nuova fixture di acquisizione parziale: aggiunto closing al
context manager della fixture. I tre casi interessati sono ripassati su tutti
gli interpreti; ripetuta la suite completa 3.13, senza ignorare warning. Il codice
applicativo della wheel non è cambiato dopo le suite 3.11/3.12; tali suite
precedono solo questa correzione di rilascio delle risorse nel test.
Le prove CLI iniziali del nuovo harness includevano campi YAML non applicabili:
corretta la fixture, senza cambiare la validazione D2. La prova dei riferimenti
HTML controlla i tag img, permettendo che il nome file compaia nella diagnosi.

[Grafici](../../docs/qa/d3-c-reference.png),
[report nominale](../../docs/qa/d3-c-report-nominal.png),
[tab VIS del report parziale](../../docs/qa/d3-c-report-vis.png),
[tab NIR](../../docs/qa/d3-c-report-nir.png), tutti ispezionati visivamente.
Generatore ripetibile `scripts/render_d3c_qa.py`: dati di test sintetici,
scarto effettivo e save fallito reale. Gli screenshot Chrome headless usano
profili temporanei; per la schermata NIR è impostato solo il tab iniziale nella
copia QA, senza modificare template/script del prodotto. Nessuna golden image.

## Limiti e ripresa della consegna locale — pendenza CI superata dalla chiusura sotto

Pubblicazione diretta e layout HTML/plots richiesto; niente generazioni,
atomicità, retention o riuso C. Su interruzione o errore HTML il vecchio report
può restare obsoleto; `report.failed` evita di dichiararlo aggiornato. API HTML
senza esiti restano legacy e non offrono garanzie anti-stale.

**CI Linux 3.11/3.12/3.13 e macOS 3.12 pendente sul candidato esatto.** Nessuna
nuova CI attribuita a C, nessun push/merge/deploy/scheduler o rebuild operativo.
I commit documentali successivi non cambiano i file verificati. Dopo pubblicazione
richiesta dall'utente, verificare SHA/attempt/job/build/installazione e registrare
solo la chiusura C. Fermarsi prima di D3-D.

## D3-C — Chiusura formale, 9 ottobre 2026

**D3-C completata e formalmente chiusa.** [CI 37951987536](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37951987536), attempt 1,
sul candidato **`45257ccc71d62ba6fa8174256bca15964da3ac9d`**. **490 PASS per ciascun job**, nessuno skip/XFAIL,
warning come errori: Linux Python 3.11 (193,96 s), 3.12 (229,21 s),
3.13 (233,03 s), macOS 3.12 (221,36 s). Build wheel e checker di installazione
isolata PASS in tutti i quattro job. `pip check` verificato localmente;
il workflow hosted non lo esegue separatamente.

Pacchetto **1.5.0**, SQLite **schema 1**. Commit applicativo `45a7e3e`,
candidato hosted `45257cc`, differenze solo documentali. Nessuna verifica C
pendente. Questa nota supera le precedenti indicazioni di CI pendente.
L'utente ha pubblicato il candidato; questa registrazione modifica soltanto
documenti, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
Ripresa: pianificazione D3-D soltanto su nuova richiesta, dopo controllo del
checkout e lettura di scheda/indice/handover. **D3-D…F non avviate.**

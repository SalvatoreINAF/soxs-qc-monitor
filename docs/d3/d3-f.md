# D3-F — Riuso su errore e chiusura integrata

**D3-F e D3 formalmente chiuse su dev: 1.8.0/schema 1; CI hosted verde.**
Dipendenze D3-A/B/C/D/E formalmente chiuse. Stima approvata **12–16 ore**,
incluse verifiche e handover, escluse attese CI; sostituisce le iniziali 6–10 ore.
Stato di consegna e risultati effettivi: [handover](../handover.md),
[evidenze F](../../tests/results/d3-f-validation.md), [audit](../../tests/results/d3-f-planning.md).

## Contratto implementato

Il renderer produce ancora `produced`, `failed` o `no_data`. Solo il motore di
pubblicazione può trasformare `failed` in `reused`, dopo il rendering e prima di
manifesto/HTML. Cerca esclusivamente nel manifesto della generazione corrente,
tra immagini `produced` o `reused`: niente scansioni dei predecessori, PNG legacy
o accessi alla generazione originaria. `no_data` non riusa mai.

Il contratto di compatibilità versione **1** confronta:

- Tutti i parametri normalizzati della figura, compresi nome/tipo/filename,
  braccio, titolo, selezione, assi e stili; esclude soltanto `section` e `wide`.
- Le query effettivamente referenziate dalla figura, incluse serie e assi x/y,
  con filtri e processing. Query/figure estranee, titolo della pagina, template,
  destinazioni e retention non invalidano una figura indipendente.
- Percorso canonico del database QC e schema 1. Contenuti/mtime del database
  non sono confrontati. L'identità è il percorso, non un UUID dell'archivio.
- Per DETLIN: parametri generali di acquisizione DETLIN e configurazione del
  solo braccio della figura. Gli altri bracci sono esclusi.

La versione del pacchetto è informativa; futuri cambiamenti incompatibili dei
renderer devono incrementare `COMPATIBILITY_VERSION`. Omissione versus valore
esplicito di un parametro opzionale può produrre un confronto conservativo.

## Metadati e diagnostica

`FigureResult`, JSON di riepilogo v1 e figure del manifesto v1 aggiungono campi
opzionali, senza cambiare le firme pubbliche:

| Campo | Significato |
|---|---|
| `generated_utc` | UTC della prima produzione riuscita, distinta dalla data dei dati |
| `origin_generation_id` | UUID della generazione della prima produzione |
| `reused_from_generation_id` | UUID della generazione corrente dalla quale si copia |
| `compatibility` | Oggetto con `version`, `figure`, `queries`, `database` e, per DETLIN, `detector_linearity` |
| `fallback` | Esito `unavailable`/`reused`, codice diagnostico, generazione candidata; motivo/tipo dell'eventuale errore di lettura/copia |

`database` contiene `path` e `schema_version`. I codici fallback sono
`no_current_image`, `missing_metadata`, `incompatible`, `source_unreadable`,
`copy_failed`, `compatible_current_image`. Gli esiti senza immagine hanno path
null; `produced` e `reused` hanno path locale alla generazione. `data_utc` resta
null: non è disponibile una misura affidabile della freschezza dei dati.

Riuso ripetuto conserva data e UUID originari come valori, senza dereferenziare
l'origine. L'HTML corrente e quello archiviato mostrano stato di riuso, errore
attuale e “Original image produced (UTC)” con data originale. Nessuna scadenza
aggiuntiva: un'immagine può restare vecchia durante fallimenti ripetuti.

Il motivo, il codice e il tipo dell'errore originale restano presenti. Conteggi
JSON additivi: `produced`, `no_data`, `failed`, `reused`. Per lo stato aggregato,
`failed` e `reused` contano entrambi come errore: tutti errori = `failed`,
parte errori = `partial`. Il run mantiene **uscita 2** anche con report pubblicato.

## Copia, guasti e retention

Il candidato deve avere metadati completi/compatibili e PNG decodificabile.
Letture/copie non seguono symlink; hardlink e file non regolari non sono adottati.
Prima della copia si rimuove l'eventuale artefatto incompleto del renderer
nel solo staging del run. La copia è esclusiva, sincronizzata e verificata.

Candidato indisponibile/incompatibile/illeggibile: figura fallita senza immagine,
report parziale pubblicabile. Copia fallita: rimozione della copia incompleta,
report parziale, uscita 2. Se la rimozione fallisce, pubblicazione bloccata e
report precedente protetto. Errori manifesto/HTML/sync prima del commit
preservano il precedente report; cleanup finale fallito mantiene il nuovo
report pubblicato e dà uscita 2, secondo D3-E.

Per permettere il recupero da PNG F mancanti/danneggiati, la verifica dei report
esistenti controlla struttura, marker, manifesto e riferimenti senza imporre
la leggibilità dei PNG con metadati F. I candidati al riuso vengono verificati
individualmente e tutti i PNG del nuovo report vengono verificati rigorosamente.
La storia conservata può quindi contenere una vecchia immagine danneggiata;
F non ripara gli archivi precedenti. I controlli PNG dei manifesti legacy
restano rigorosi. Marker, proprietà, struttura o percorsi incoerenti bloccano
ancora l'operazione prima delle scritture dell'archivio.

Ogni nuovo report copia i PNG nella propria generazione; retention protegge
corrente/storia e non dipende dall'origine dell'immagine riusata. Lease e
politiche E (2 generazioni, 24 ore, 2 staging di default) restano attive.

## Passaggio da E e limiti

**Decisione approvata:** manifesti D3-E leggibili ma esclusi dal fallback:
mancano identità del database e provenienza completa. Occorre una prima
produzione riuscita con F. Nessuna migrazione automatica né adozione di PNG
legacy. Schema SQLite 1, acquisizione, retry, scienza e tolleranze invariati.
Nessuna nuova opzione YAML/CLI.

Tutte le prove usano dati sintetici e percorsi temporanei. Non certificano
strumenti reali, fine della riduzione o prestazioni operative. Restano i limiti
E su browser vecchi, hosting e retention per quantità/età anziché byte.

## Accettazione, chiusura e ripresa

46 casi F coprono compatibilità, provenienza, errori/copie, no_data, riusi
ripetuti, retention, interruzioni/concorrenza e CLI integrata
valido → incompleto → errore → riparazione → retry → chiusura → run senza novità,
con rebuild sintetico. Le regressioni A–E includono update fallito e supervisore.
QA riproducibile: `scripts/render_d3f_qa.py /private/tmp/qc-d3f-qa`.

Seguire [istruzioni test](../../tests/README.md): suite con `-W error`,
wheel/checker fuori checkout, pip check e matrice hosted Linux 3.11/3.12/3.13,
macOS 3.12 sul candidato esatto. Esiti in evidenze e manifesto ambienti.
Solo dopo quella CI si possono dichiarare formalmente chiuse F e D3.

Alla ripresa verificare dev/HEAD/working tree, leggere handover/risultati F,
pubblicare il candidato soltanto su richiesta e verificare SHA/job reali.
Distinguere commit applicativo, candidato CI e commit documentali successivi.
**Fermarsi a D3-F; nessun D4, merge, deploy o rebuild operativo implicito.**


## D3-F e D3 — Chiusura formale, 9 ottobre 2026

**D3-F completata e formalmente chiusa; D3 complessivamente chiusa.**
CI [37986639107](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37986639107),
attempt **1**, sul candidato **`fa9abac024f2f596d482e6385a564801dd1240fe`**.
Pacchetto **1.8.0**, SQLite **schema 1**; D3-A/B/C/D/E restano chiuse.

| Job hosted | Suite con warning come errori | Durata | Wheel / checker isolato |
|---|---|---|---|
| Linux Python 3.11 | 655 PASS, 0 SKIP | 263,35 s | PASS |
| Linux Python 3.12 | 655 PASS, 0 SKIP | 198,40 s | PASS |
| Linux Python 3.13 | 655 PASS, 0 SKIP | 249,40 s | PASS |
| macOS Python 3.12 | 654 PASS, 1 SKIP | 246,71 s | PASS |

Nessun FAIL/XFAIL/XPASS. Skip macOS soltanto per secondo filesystem scrivibile
assente; la stessa prova passa nei tre job Linux. Build wheel 1.8.0 e checker
isolato, incluso riuso/provenienza/uscita 2, verdi nei quattro job. Pip check
verificato localmente; il workflow non lo esegue separatamente.

Commit applicativo **`f416da6be0b50ef50d1c6640be7152610a1210e3`**;
candidato hosted **`fa9abac024f2f596d482e6385a564801dd1240fe`**: differenze
soltanto documentazione/evidenze/QA, verificate. Il successivo commit di
chiusura è documentale e non ha una propria CI attribuita.
**Nessuna verifica D3-F pendente.** Questa nota supera le precedenti indicazioni
di CI F/D3 pendente; le prove locali restano evidenze storiche distinte.

L'utente ha pubblicato il candidato. Questa chiusura modifica soltanto documenti
ed evidenze, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
Ripresa: leggere handover/indice e verificare dev/HEAD/working tree. D3 è chiusa;
**D4 non avviata: pianificazione soltanto su nuova richiesta**, dopo verifica
dello stato effettivo e chiarimento delle decisioni della prossima milestone.

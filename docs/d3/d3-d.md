# D3-D — Motore di pubblicazione atomica

**D3-D completata e formalmente chiusa; 1.6.0/schema 1. CI hosted verde.**
Dipendenze D3-B/C formalmente chiuse. D3-E/F non avviate.
Baseline `dev`, `3a9b705f686a5967d91caffd2fb1da3ca6b431c7`, working tree pulito,
un commit documentale oltre origin/dev. Audit pre-sviluppo: 159 PASS / 81,97 s,
Python 3.12.15, warning come errori; [registrazione](../../tests/results/d3-d-planning.md).
Stima approvata **10–14 ore**, inclusi test/documentazione, escluse attese CI;
non è un consuntivo. Stato finale/evidenze: [validazione](../../tests/results/d3-d-validation.md).

> Confine storico della versione 1.6.0: D3-E (1.7.0) attiva il motore nella CLI
> e aggiunge retention; vedere [contratto E](d3-e.md).

## Risultato e confini

Il motore interno prepara una generazione autosufficiente e rende visibile il
report con una sola sostituzione dell'HTML configurato. **La CLI ordinaria non
chiama il motore**: mantiene pubblicazione diretta, layout `plots/`, e JSON
`publication.state=skipped`. Nessuna nuova opzione YAML/CLI o retention.
Non sono introdotti riuso, migrazione immagini legacy o garanzie assolute contro
perdita di alimentazione; risultati scientifici e SQLite schema 1 invariati.

## Decisioni approvate e layout

L'utente ha scelto HTML configurato come unico punto di pubblicazione e `fsync`
esplicito. Non esistono puntatori `current`, symlink di switch o manifesto
riscritto per dichiarare una generazione corrente.

```text
plots.output_dir/
  .qc-publication/.owner.json
  .qc-publication/<sha256-del-percorso-HTML-canonico>/
    .owner.json
    staging/.owner.json
    staging/<uuid>/.owner.json
    generations/.owner.json
    generations/<uuid>/
      .owner.json
      plots/<filename-relativi>.png
      manifest.json
      report.html
plots.html_output   # unico punto di commit, con marker strutturato
```

Le directory riservate esistenti devono avere marker esatti di proprietà v1.
Un UUID canonico identifica run/generazione; staging o generazione già presenti
sono collisioni, non risorse da adottare o sovrascrivere. I marker contengono
proprietario applicativo `soxs-qc-monitor`, formato, identità report, percorso
HTML e, per generazione, UUID/data UTC di preparazione. Le protezioni sono
cooperative sullo stesso host/account, come in B; non costituiscono una barriera
contro un processo ostile che modifica risorse autorizzate dello stesso utente.

Il marker dell'HTML è un commento `qc-publication-v1:` con JSON codificato in
base64: owner, formato 1, report_id, generation_id, previous_generation_id e
SHA256 del manifesto. La base64 evita delimitatori/commenti accidentali; non è
una firma di autenticazione. Il manifesto e la proprietà della generazione
corrente vengono verificati, insieme ai PNG referenziati, prima di una nuova
pubblicazione. HTML legacy senza marker accettato; marker invalido/duplicato,
proprietà incoerente o immagine corrente corrotta bloccano prudentemente il motore.

## Interfacce e manifesto v1

`qc_monitor.publication.publish_report(cfg, *, project_root, config_path,
run_id, render, summary_path=None)` richiede configurazione già normalizzata.
Acquisisce autonomamente lease B per runtime/progetto/configurazione e risorse;
è reentrante sotto le lease già possedute dall'operazione. Le lease durano fino
alla pulizia dei temporanei, anche durante un errore.

`render(staging_plots_cfg)` riceve una copia della configurazione grafici,
con output_dir/html_output temporanei, e restituisce gli esiti FigureResult C.
Non deve scrivere fuori dallo staging. Il motore verifica copertura, identità,
percorsi effettivi, file regolari non condivisi e decodifica completa dei PNG.
Gli esiti restano produced/no_data/failed; ogni generazione ha soltanto riferimenti
alle proprie immagini. Un report tutto vuoto/fallito può essere pubblicato;
nessuna figura configurata restituisce skipped senza lease o artefatti.

Il manifesto contiene owner, format_version=1, report_id, report_path,
generation_id/run_id, previous_generation_id, prepared_utc, package_version,
rendering_config, detector_linearity e figures. La configurazione grafici originale
esclude output_dir/html_output; gli esiti produced hanno path `plots/<filename>`,
gli altri path null. Le diagnosi originali possono citare percorsi temporanei
come contesto del guasto; non sono destinazioni di artefatti pubblicati. `data_utc` è null: C non fornisce una data scientifica
aggregata e il timestamp di preparazione non la sostituisce. Non è fissata qui
la politica di compatibilità del futuro fallback F.

PublicationResult espone state, phase, generation_id, previous_generation_id,
report_path, manifest_path, durability, staging_cleanup, errors e figures.
`as_dict()` restituisce i soli metadata di pubblicazione. PublicationError
contiene `.result` e preserva il risultato raggiunto; la causa originale è nella
diagnosi strutturata. `result.apply_to(run)` è un adattatore esplicito, non usato
dalla CLI: registra pubblicazione, report, esiti e errori; run.finish() mantiene
uscita 2 per failed, anche quando l'HTML parziale è stato pubblicato. Non modifica
contatori/transazioni SQLite. Il campo additivo JSON v1 `publication` è skipped
per il percorso ordinario. Un errore del motore non cambia da solo il DB.

L'API `generate_html_report` conserva argomenti/ritorni/comportamento legacy e
aggiunge il keyword opzionale `image_urls`, mappa nome figura → URL. Il rendering
comune è separato dalla scrittura; il motore scrive con creazione esclusiva e
senza seguire symlink. URL relativi percent-encoded, poi HTML-escaped; vietati
base URL, immagini aggiuntive e link PNG estranei nei template del motore.
La API legacy conserva la propria semantica, senza promettere atomicità.

## Sequenza, guasti e proprietà

1. Validare percorsi/proprietà esistenti e corrente prima delle scritture.
2. Creare staging posseduto, renderizzare, verificare PNG ed esiti.
3. Preparare report.html relativo alla generazione e manifesto; sincronizzare
   tutti i file e directory dal basso verso l'alto.
4. Rinominare staging in generazione, quindi sincronizzare entrambe le directory.
5. Preparare HTML corrente temporaneo nella directory dell'HTML configurato,
   verificare esattamente le immagini prodotte, scrivere/flush/fsync.
6. `os.replace` dell'HTML e fsync della directory del report.

Ogni rename è sul proprio filesystem: HTML e immagini possono essere su
filesystem differenti. Il motore garantisce la raggiungibilità locale, non la
configurazione di un server HTTP; l'operatore deve esporre entrambe le destinazioni
con una corrispondenza di URL coerente. Le copie archiviate sono autonome.

Prima del replace finale il report precedente e le sue immagini restano
immutati. Dopo replace il risultato è published; un fsync finale fallito mantiene
published/durability=unconfirmed, genera PublicationError e uscita 2 tramite
adattatore, senza rollback. Dopo successo durability=confirmed; prima di commit
un errore restituisce failed, report_path null e la fase raggiunta.

Uscite controllate: rimuovere soltanto temporaneo esclusivamente creato e staging
con proprietà ancora valida, sotto lease. Cleanup fallito è visibile con
staging_cleanup=failed. Il marker viene eliminato per ultimo e ripristinato
se fallisce il rmdir finale; se il filesystem impedisce anche il ripristino,
il residuo non viene adottato o eliminato automaticamente. La generazione finalizzata non viene cancellata se la
pubblicazione fallisce; diventa un orfano identificabile dal confronto con il
marker corrente. Crash/SIGKILL possono lasciare staging o generazioni non correnti.
Nessuna pulizia generale, limite allo spazio o cancellazione legacy in D.

Il motore rifiuta symlink negli artefatti/antenati gestiti, hardlink e file non
regolari. Creazione, rename, sincronizzazione e cleanup usano descriptor di
directory e operazioni senza inseguimento dei symlink. Rifiuta sovrapposizioni
con namespace gestito, input, config/include, template, DB/sidecar/backup e
summary. Il namespace delle generazioni non può essere collocato dentro le
radici di input; cartelle preesistenti di output esterne al namespace sono preservate.

## Verifiche, consegna e ripresa

Test sintetici: nominale/parziale/tutte figure vuote o fallite, generazioni
successive e copie archiviate, ogni fsync, guasti prima/dopo commit, PNG reali
mancanti/corrotti, template, percorsi speciali/annidati, symlink/hardlink/FIFO,
collisioni/proprietà cambiate, temporanei estranei, lease reentranti e contesa
in processi reali, SIGKILL prima/dopo finalizzazione. Prova filesystem reale
quando disponibile, altrimenti skip motivato più controllo dei rename locali.
Regressioni C/scientifiche e CLI invariata; QA tramite `scripts/render_d3d_qa.py`.

Consegna: suite -W error su macOS 3.11/3.12/3.13 in sequenza, wheel/checker isolato
esteso e pip check. Matrice hosted Linux 3.11/3.12/3.13 e macOS 3.12 sul candidato
esatto per chiusura formale; le prove Docker ARM64 non la sostituiscono.
Aggiornare README, indice, contratti/operazioni, test/evidenze/ambiente/QA e
handover; roadmap/valutazione reference_docs restano locali ignorate.
Scheda finale: baseline/commit applicativo, decisioni, funzionalità, test reali,
limiti/pendenze e punto di ripresa. **Fermarsi a D3-D**: D3-E richiede una nuova
richiesta di pianificazione. Nessun push/merge/deploy/rebuild operativo implicito.


Commit applicativo **`a7a2ebb081f21a6b5e4330f2f200054fc480630d`**. Suite finale: 548 PASS/1 SKIP su ciascuno
di Python 3.11/3.12/3.13 macOS; Linux ARM64 D mirata 59 PASS, zero skip.
Wheel/checker/pip check e QA verdi. Evidenze e limiti nel documento collegato.


## D3-D — Chiusura formale, 9 ottobre 2026

**D3-D completata e formalmente chiusa.** [CI 37966108485](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37966108485), attempt **1**,
sul candidato **`dc3b736c6b62219c5f4e2fdae078fd5a03449e02`**. Suite con warning come errori:

| Job hosted | Esito suite | Durata | Wheel / checker isolato |
|---|---|---|---|
| Linux Python 3.11 | 549 PASS, 0 SKIP | 150,62 s | PASS |
| Linux Python 3.12 | 549 PASS, 0 SKIP | 232,58 s | PASS |
| Linux Python 3.13 | 549 PASS, 0 SKIP | 253,03 s | PASS |
| macOS Python 3.12 | 548 PASS, 1 SKIP | 274,41 s | PASS |

Nessun FAIL/XFAIL/XPASS. Lo skip macOS riguarda esclusivamente l'assenza di
un secondo filesystem scrivibile; la stessa prova reale passa nei tre job
Linux. Build wheel e checker di installazione isolata PASS in tutti i job.
`pip check` verificato localmente, non separatamente dal workflow hosted.

Pacchetto **1.6.0**, SQLite **schema 1**. Commit applicativo **`a7a2ebb`**,
candidato hosted **`dc3b736`**: differenze soltanto documentali. Nessuna verifica
D3-D pendente. Questa nota supera le precedenti indicazioni di CI pendente;
le evidenze locali e i relativi skip restano conservati come storia distinta.

L'utente ha pubblicato il candidato. Questa chiusura modifica soltanto
documenti/evidenze, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
CLI ordinaria ancora diretta; nessuna retention o riuso introdotti. Ripresa:
**pianificazione D3-E soltanto su nuova richiesta**, dopo controllo del checkout
e lettura di indice/scheda/handover. **D3-E/F non avviate.**

# D3-E — Retention sicura e attivazione nella CLI

**D3-E consegnata e verificata localmente su dev; CI hosted E pendente.** Pacchetto 1.7.0,
SQLite schema 1. D3-A/B/C/D formalmente chiuse; D3-F non avviata.
Baseline `3285f5bf4eb6b6600d9eafd81ca41bf2aabce525`, checkout pulito, un commit
documentale oltre origin/dev. [Audit di pianificazione](../../tests/results/d3-e-planning.md).
Stima approvata: **12–16 ore**, incluse verifiche e handover, escluse attese CI.

## Configurazione e contratti

La CLI usa `publish_report`: rendering nello staging, generazione autosufficiente,
manifesto v1 e HTML configurato come unico punto di commit. Conservate le API
legacy dei renderer e dell'HTML, backend batch Agg, isolamento delle letture,
acquisizione e codici 0/1/2. Nessun riuso, modifica della scienza o dello schema.

```yaml
plots:
  publication:
    retained_generations: 2
    orphan_max_age_hours: 24
    max_orphan_staging: 2
```

Default centralizzati; mapping parziale consentito. Generazioni: intero >=2;
staging: intero >=0, zero elimina tutti gli orfani riconosciuti; età: numero
finito >0. Booleani numerici, tipi invalidi e chiavi sconosciute sono rifiutati.
Nessun nuovo flag CLI. No-plots, dry-run e nessuna figura saltano pubblicazione
e cleanup; preflight controlla senza scrivere. Le opzioni YAML sono comunque
validate. Controlli di percorsi, namespace, proprietà e storia conservata prima
delle scritture nell'archivio. Summary nel namespace riservato rifiutato anche
come destinazione della diagnosi. Input, config/include, template, DB/sidecar,
backup e lock protetti; nessuna migrazione dei PNG legacy.

`validate_publication(cfg, *, config_path, summary_path=None)` è il controllo
in sola lettura condiviso da CLI/preflight e motore. Firma di `publish_report`
invariata; la retention è ora parte del motore, sotto le lease B fino al cleanup.
`PublicationError.result` viene applicato anche in caso di errore, senza duplicare
le diagnosi delle figure. Stato DB indipendente da pubblicazione e pulizia.

## Storia e pulizia

L'HTML corrente identifica la generazione corrente; i predecessori dei manifesti
identificano la storia pubblicata. Gli orfani finalizzati non sono storia.
Ogni HTML conservato e i suoi PNG sono validati prima delle cancellazioni.
La traversata si ferma dopo N elementi; il predecessore dell'ultimo può essere
stato eliminato. Manifesti immutabili, nessun puntatore riscritto.

Il campo additivo v1 `retained_history_length` registra la lunghezza disponibile
della storia da conservare al commit (al massimo N). Permette di aumentare N
senza richiedere immagini già eliminate: la storia cresce ai run successivi.
I manifesti D3-D senza campo restano leggibili con traversata limitata a N.
Un predecessore mancante dentro la storia dichiarata resta errore; cicli,
identità e riferimenti incoerenti bloccano prudentemente la pubblicazione.

Prima di creare lo staging attivo: validare tutto il piano di cancellazione,
rimuovere generazioni riconosciute fuori dalla storia e staging scaduti (età
>= soglia), poi staging eccedenti dal più vecchio. Ordinamento UTC di
`prepared_utc`, UUID come spareggio, mai mtime. Timestamp futuri non scadono per
età, ma sono soggetti al limite numerico. Collisioni UUID respinte prima del
cleanup. Dopo commit HTML e fsync riusciti, nuova riduzione alle ultime N.
Nessuna retention dopo commit con durability unconfirmed.

Cancellazione solo per directory UUID canoniche con marker D esatto per report,
namespace, generazione e timestamp UTC. Nomi estranei e directory senza marker
sono preservati e contati come ignorati; marker presenti ma invalidi/incoerenti
e candidati UUID con symlink o file non regolari bloccano il cleanup. Inventario
completo prima della prima cancellazione. Operazioni descriptor-relative senza
seguire symlink; eventuali link interni sono rimossi senza toccare il bersaglio.
Marker eliminato per ultimo/ripristinato su rmdir fallito come in D.

Decisioni approvate: fallimento iniziale blocca nuova pubblicazione (uscita 2),
report corrente preservato e acquisizione già committata valida. Fallimento
dopo pubblicazione lascia il nuovo report disponibile (uscita 2), senza rollback.
Le generazioni finalizzate non pubblicate vengono eliminate al prossimo avvio,
senza attesa delle 24 ore; tale soglia riguarda gli staging.

## Diagnostica JSON v1 e limiti

`publication.cleanup` aggiunge `startup` e `retention`, ciascuno con:
`state` (skipped/completed/failed), `removed` (conteggi generations/staging),
`remaining` (conteggi verificati o null), `ignored` (conteggi estranei o null),
`limits_guaranteed` (true/false/null). False su tentativo fallito anche se rmdir
è avvenuto prima di un fsync fallito; null se la fase non è stata verificata.
Il conteggio removed comprende directory realmente rimosse anche quando fallisce
la sincronizzazione della directory padre. `staging_cleanup` D è conservato.
Le diagnosi strutturate sono in publication.errors e nel riepilogo globale.

Limiti per quantità/età, non quota in byte. Applicati ai run operativi; se un
crash lascia residui, si recuperano al prossimo run. File estranei, PNG legacy,
backup SQLite e temporanei HTML senza proprietà verificabile restano esclusi.
Un browser con HTML molto vecchio può perdere immagini eliminate. Il server
HTTP deve esporre sia HTML sia namespace immagini; non cambiare scheduler o
hosting automaticamente. Non cancellare lock persistenti per sbloccare il run.

## Verifiche e consegna

Prove sintetiche/temporanee: molte pubblicazioni N=2/N=4, modifica dei limiti,
validità immagini correnti/archiviate, staging per età/numero/spareggio/zero,
orfani incompleti, SIGKILL prima/dopo finalizzazione e dopo commit, lease reali
durante entrambe le pulizie, permessi reali, proprietà/marker/link/estranei,
storia danneggiata, collisioni UUID e percorsi, codice 2 prima/dopo commit,
conteggi dopo fsync fallito, DB committato prima del cleanup fallito e modalità
senza scritture grafiche. Test C/D adattati ai nuovi percorsi; guasti reali
provocati nello staging. Checker wheel verifica CLI, report parziale e retention.

Consegna: suite -W error macOS 3.11/3.12/3.13 in sequenza; wheel/checker fuori
checkout/pip check; QA nominale, parziale e archiviata. Matrice hosted sul
candidato esatto richiesta per chiusura formale: Linux 3.11/3.12/3.13 e macOS
3.12. Evidenze locali non equivalgono a hosted. Nessun push implicito.

Aggiornare README, indice/scheda, contratti, operazioni, istruzioni test,
evidenze/ambiente/QA e handover; reference_docs solo locale ignorata da Git.
Scheda sintetica: baseline/commit, funzionalità, decisioni, test effettivi,
limiti/pendenze e punto di ripresa. **Fermarsi a D3-E: nessun D3-F o D4.**


Commit applicativo D3-E **`c48380dddaa33d48d2b66db4380bd454f0f7782b`**; consegna locale verificata,
CI E pendente sul candidato esatto. [Evidenze](../../tests/results/d3-e-validation.md).

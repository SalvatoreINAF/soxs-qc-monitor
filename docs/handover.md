# Handover — D3-E consegnata localmente, 9 ottobre 2026

**D3-E implementata e verificata localmente su dev, 1.7.0/schema 1.**
D3-A/B/C/D formalmente chiuse; **CI hosted E pendente, D3-F non avviata**.

## Scheda sintetica di consegna

- Baseline `3285f5bf4eb6b6600d9eafd81ca41bf2aabce525`, checkout inizialmente pulito.
  Commit applicativo **`c48380dddaa33d48d2b66db4380bd454f0f7782b`**. Il successivo commit di consegna
  modifica soltanto documenti/evidenze; nessun candidato E pubblicato o hosted verificato.
- CLI usa il motore atomico D; default YAML 2 generazioni, 24 ore e 2 staging.
  Retention protegge corrente/storia e tutti i riferimenti degli HTML conservati.
  Orfani finalizzati eliminati al prossimo avvio; staging ordinati per UTC/UUID.
- Cleanup iniziale fallito blocca pubblicazione; cleanup finale fallito mantiene
  report valido; uscita 2 senza rollback di report o dati committati.
  JSON v1 cleanup startup/retention, conteggi e limiti verificati; controlli prima
  del writer DB e summary fuori dal namespace anche tramite symlink.
- 60 casi E nuovi, 609 totali. **608 PASS/1 SKIP** per macOS Python
  3.11.17/3.12.15/3.13.16, warning come errori. Skip esclusivamente per secondo
  filesystem assente; Linux ARM64 E+D **119 PASS/0 SKIP**, utente normale,
  incluse prove reali filesystem/permessi. Wheel/checker fuori checkout/pip check
  e confronto byte per byte checkout/wheel/installed PASS sui tre interpreti.
- QA nominale/parziale/archiviata ispezionata. API legacy renderer/HTML mantenute;
  sorgenti scientifici, acquisizione, storage/schema/retry e supervisore B identici
  alla baseline. Nessun riuso F o nuova migrazione.
- [Contratto E](d3/d3-e.md), [evidenze](../tests/results/d3-e-validation.md),
  [audit](../tests/results/d3-e-planning.md), [ambienti/hash](qa/d3-e-environments.json).
  Stima 12–16 ore inclusi test/documentazione, escluse attese CI; non consuntivo.
- Documentazione versionata e reference_docs locale aggiornate; nessun
  push/merge/deploy/scheduler o archivio operativo modificato.

## Limiti e punto di ripresa vincolante

Limiti di quantità/età, non byte; cleanup applicato ai run operativi. Filesystem
non disponibile può impedirlo con codice 2. Estranei, PNG legacy, backup SQLite e
temporanei HTML senza proprietà verificabile preservati. Vecchi browser possono
perdere immagini eliminate; server HTTP deve esporre entrambe le destinazioni.
Non cancellare lock, modificare marker o adottare directory per forzare un run.

Controllare dev/HEAD/working tree e leggere scheda/evidenze. Dopo pubblicazione
esplicitamente richiesta del candidato, verificare la CI sul suo SHA esatto:
Linux 3.11/3.12/3.13 e macOS 3.12, suite/wheel/checker. Registrare solo allora
chiusura formale E. CI D3-D e Docker locale non equivalgono alla CI E.
**Fermarsi a D3-E: nessun D3-F/D4 senza nuova richiesta e chiusura E.**
Le sezioni successive sono storiche; questa apertura prevale sulle riprese precedenti.

---

# Handover — D3-D formalmente chiusa, 9 ottobre 2026

**D3-D completata e formalmente chiusa su dev.** Pacchetto **1.6.0**,
SQLite **schema 1**. D3-A/B/C restano chiuse; **D3-E/F non avviate**.

- Commit applicativo `a7a2ebb081f21a6b5e4330f2f200054fc480630d`.
- Candidato hosted **`dc3b736c6b62219c5f4e2fdae078fd5a03449e02`**, commit successivo soltanto documentale.
- [CI 37966108485](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37966108485), attempt 1: **549 PASS per ciascun job Linux Python
  3.11/3.12/3.13**; **548 PASS, 1 SKIP macOS Python 3.12**. Lo skip è solo
  la prova su due filesystem assente sul Mac, passata su tutti i job Linux.
- Suite con -W error, build wheel e checker isolato verdi nei quattro job.
  pip check verificato localmente, non separatamente dal workflow hosted.
  **Nessuna verifica D3-D pendente.**
- [Evidenze](../tests/results/d3-d-validation.md),
  [CI metadata](../tests/results/d3-d-hosted.json),
  [ambienti](qa/d3-d-environments.json), [contratto D](d3/d3-d.md).

Punto di ripresa: **pianificazione D3-E soltanto su nuova richiesta**, dopo
verifica dev/HEAD/working tree e lettura indice/scheda E. Non avviare sviluppo
o altre milestone automaticamente. Restano i limiti D: motore interno non
attivo nella CLI ordinaria, nessuna retention/riuso e nessun deploy automatico.

Chiusura solo documentale; sorgenti/test/workflow/versione invariati. Nessun
nuovo push/merge/deploy, scheduler o archivio operativo modificato. reference_docs
aggiornata localmente e ancora ignorata da Git. Le sezioni successive sono
storiche: questa apertura prevale sulle indicazioni precedenti di CI pendente.

---

# Handover — D3-D consegnata localmente, 9 ottobre 2026

**D3-D consegnata e verificata localmente su dev, 1.6.0/schema 1.**
D3-A/B/C restano formalmente chiuse; **CI hosted D pendente, D3-E/F non avviate**.

## Scheda sintetica di consegna

- Baseline `3a9b705f686a5967d91caffd2fb1da3ca6b431c7`, checkout inizialmente pulito.
  Commit applicativo **`a7a2ebb081f21a6b5e4330f2f200054fc480630d`**. Il successivo commit registra soltanto
  documentazione/evidenze; nessun candidato D verificato dalla CI hosted.
- Consegnati motore interno, generazioni autosufficienti, manifesto/proprietà v1,
  URL relativi codificati, PNG/HTML validati, fsync e HTML unico punto di commit,
  lease B fino al cleanup, PublicationResult/Error e campo JSON v1 publication.
- Decisioni concordate: HTML atomico e fsync esplicito. Cleanup conserva il marker
  fino alla rimozione effettiva. Errore dopo replace: published/unconfirmed,
  diagnosi e uscita 2 tramite adattatore, senza rollback.
- **548 PASS/1 SKIP per Python 3.11/3.12/3.13 macOS**, warning come errori.
  Skip esclusivamente per secondo filesystem assente. **Linux ARM64: 59 PASS,
  nessuno skip**, utente normale, inclusa prova /tmp → /dev/shm. Wheel/checker
  isolato/pip check verdi nei tre interpreti, file identici a checkout/wheel.
- QA nominale/parziale/archiviata/NIR ispezionata; test solo sintetici/temp.
  [Evidenze](../tests/results/d3-d-validation.md), [ambiente](qa/d3-d-environments.json),
  [contratto](d3/d3-d.md), [audit](../tests/results/d3-d-planning.md).
- Documentazione e reference_docs locale aggiornate; stima approvata 10–14 ore,
  non consuntivo. Nessun push/merge/deploy/scheduler/rebuild operativo.

## Limiti e punto di ripresa vincolante

La CLI ordinaria resta diretta e publication.state=skipped. Nessuna retention,
riuso o migrazione. Generazioni/staging non correnti possono restare su crash;
D non esegue cleanup generale. Il server web deve esporre entrambi i percorsi.
Nessuna garanzia assoluta di persistenza dopo power loss. Non cancellare lock
persistenti o adottare directory senza marker valido per aggirare un errore.

Controllare dev/HEAD/working tree, leggere questa apertura, indice/scheda D ed
evidenze. Pubblicare il candidato soltanto su richiesta; verificare la nuova
CI sul suo SHA esatto: Linux 3.11/3.12/3.13 e macOS 3.12, suite/wheel/checker.
Registrare quindi la chiusura formale D. Le prove Linux locali non sono hosted.
**Pianificare D3-E soltanto su nuova richiesta e dopo chiusura D. Fermarsi a D.**
Le sezioni seguenti sono storiche e questa apertura prevale sul loro stato.

---

# Handover — D3-C formalmente chiusa, 9 ottobre 2026

**D3-C completata e formalmente chiusa su `dev`.** Pacchetto **1.5.0**,
SQLite **schema 1**. D3-A/B restano chiuse; **D3-D…F non avviate**.

- Commit applicativo `45a7e3e5a2c8133120e185a42ded9e6f4256049f`.
- Candidato hosted **`45257ccc71d62ba6fa8174256bca15964da3ac9d`**, successivo commit di consegna solo documentale.
- [CI 37951987536](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37951987536), attempt 1: **490 PASS per job**, Linux Python
  3.11/3.12/3.13 e macOS 3.12; nessuno skip/XFAIL, warning come errori.
- Build wheel e checker isolato PASS nei quattro job. `pip check` verificato
  localmente, non separatamente dal workflow hosted. Nessuna verifica C pendente.
- [Evidenze](../tests/results/d3-c-validation.md),
  [ambienti](qa/d3-c-environments.json), [scheda C](d3/d3-c.md).

Punto di ripresa: **pianificazione D3-D soltanto su nuova richiesta**;
verificare dev/HEAD/working tree, leggere indice e relativa scheda. Non iniziare
lo sviluppo o altre milestone automaticamente. Restano i limiti C: pubblicazione
diretta/layout standard, nessuna retention/generazione/immagine riusata.

Questa chiusura modifica solo documenti; nessun nuovo push/merge/deploy,
scheduler o archivio operativo modificato. Le sezioni successive sono storiche:
questa apertura prevale sulle indicazioni di CI pendente. reference_docs
aggiornata e intenzionalmente ignorata da Git.

---

# Handover — D3-C consegnata localmente, 9 ottobre 2026

**D3-C consegnata e verificata localmente su `dev` il 9 ottobre 2026.**
Pacchetto **1.5.0**, SQLite **schema 1**. Commit applicativo **`45a7e3e5a2c8133120e185a42ded9e6f4256049f`**.
D3-A/B restano formalmente chiuse; **CI hosted D3-C pendente, D3-D…F non avviate**.

## Scheda sintetica di consegna

- Baseline `08baf0c`; documenti di pianificazione preesistenti preservati.
  Commit applicativo `45a7e3e5a2c8133120e185a42ded9e6f4256049f`. I successivi commit registrano documenti;
  non esiste ancora un candidato D3-C verificato dalla CI hosted.
- Consegnati esiti tipizzati per tutti i renderer, isolamento delle letture e
  dei guasti, cleanup e Agg batch, report parziale senza immagini obsolete,
  campi additivi JSON v1 `plots`/`report`. API dirette mantengono le eccezioni
  per default, con opzione `continue_on_error` usata nel batch.
- Decisioni **concordate**: produrre con scarti segnalati se restano misure
  sufficienti; una serie interamente guasta rende fallita la figura; errori
  di rendering/lettura/HTML danno codice 2, assenza legittima non lo dà.
- **490 PASS** per Python 3.11.17/3.12.15/3.13.16 su macOS arm64,
  `-W error`, nessuno skip/XFAIL. 85 casi C nuovi. Wheel/checker/pip check
  verdi nei tre nuovi venv; file installati identici a wheel e checkout.
- [Evidenze](../tests/results/d3-c-validation.md),
  [ambienti](qa/d3-c-environments.json), [scheda C](d3/d3-c.md),
  [QA](qa/d3-c-report-nir.png). Formule/tolleranze/schema/DETLIN/retry invariati.
- Documentazione aggiornata e reference_docs locale ignorata da Git.
  Stima prevista 10–14 ore, non consuntivo. Nessun push/merge/deploy,
  scheduler modificato o archivio operativo ricostruito.
- Limiti: scrittura diretta, layout standard, niente generazioni/retention/riuso;
  HTML API senza esiti conserva la modalità legacy.

## Punto di ripresa vincolante

Verificare dev/HEAD/working tree e leggere evidenze/scheda/manifesto. Pubblicare
il candidato soltanto su richiesta e verificare la nuova CI sul suo SHA esatto:
Linux 3.11/3.12/3.13 e macOS 3.12, suite/wheel/checker. Registrare poi la chiusura
formale C. Le prove locali non sono CI hosted o prove Linux.
**Nessun avvio di D3-D; questa consegna si arresta a D3-C.**
Le sezioni successive sono storiche e questa apertura prevale su di esse.

---

# Handover — Pianificazione D3-C consegnata, 9 ottobre 2026

**Piano dettagliato D3-C completato su `dev`; sviluppo non avviato.**
D3-A/B restano formalmente chiuse. Pacchetto **1.4.0**, SQLite **schema 1**.

## Scheda sintetica della consegna di pianificazione

- Baseline **`08baf0c19bb839da23b46e5e942e9fff6db4d658`**, working tree
  inizialmente pulito e allineato a origin/dev. Modifiche solo documentali,
  nessun commit applicativo D3-C né nuovo candidato CI.
- [Piano autonomo](d3/d3-c.md): esiti espliciti per i dieci renderer,
  assenza/invalidità, API compatibili, letture indipendenti, backend e cleanup,
  report parziale, campi additivi JSON v1 e criteri di accettazione.
- Scelte principali: risultato tipizzato; generatori con
  `continue_on_error=False` per compatibilità e True nel batch; HTML con
  `figure_results=None` legacy; CLI passa gli esiti completi. `no_data` senza
  immagini, errore figura/lettura porta codice 2. Agg nel batch non interattivo.
- [Verifica baseline](../tests/results/d3-c-planning.md): **82 PASS / 81,80 s**
  su macOS Python 3.12.15, warning come errori. La CI D3-B resta evidenza
  storica del codice precedente; nessuna verifica applicativa D3-C eseguita.
- Stima sviluppo completo C **10–14 ore**, circa 1,5–2 giornate, incluse prove
  e documentazione; attese CI escluse. Nessuna decisione progettuale bloccante
  rimasta nel piano; scostamenti da documentare alla consegna.
- Aggiornati indice, README, operations, contratti, test e roadmap/valutazione
  locali in reference_docs (ignorata da Git). Nessun push/merge/deploy o dato
  operativo modificato. Limite futuro intermedio C: pubblicazione diretta,
  layout standard, nessun riuso/retention/atomicità fino alle milestone dedicate.

## Punto di ripresa

Alla nuova richiesta di sviluppo, verificare branch/HEAD/working tree e leggere
scheda C, audit, indice, contratti ed evidenze D3-B. Implementare **solo C**
seguendo la sequenza e i test pianificati. Al termine consegnare scheda breve,
`tests/results/d3-c-validation.md`, manifesto ambiente e QA; aggiornare tutti i
documenti coinvolti. Versione 1.5.0 soltanto alla consegna applicativa, schema 1.
Chiusura formale con CI sul candidato esatto; se pendente, dichiararla.
**Non avviare D3-D o altre milestone automaticamente.**
Le aperture successive sono storiche: questa prevale sul loro punto di ripresa.

---

# Handover — D3-B formalmente chiusa, 9 ottobre 2026

**D3-B completata e formalmente chiusa su `dev`.** Pacchetto **1.4.0**,
SQLite **schema 1**. D3-A resta chiusa; **D3-C…F non avviate**.

- Implementazione iniziale: `98d51d3`; correzione timeout: `179f3ec`.
- Candidato hosted verificato: **`7a952c5972dfa7f00a0ccfefc5968e40f7e05d8a`**.
- [CI 37933559550](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37933559550), attempt 1: **405 PASS per job**,
  Linux Python 3.11/3.12/3.13 e macOS 3.12; nessuno skip/XFAIL.
- Wheel e checker isolato verdi in tutti i job. `pip check` verificato
  localmente; nessun controllo separato di pip check nel workflow hosted.
- Superata la CI fallita del candidato precedente. Nessuna verifica D3-B pendente.
- [Evidenze](../tests/results/d3-b-validation.md),
  [correzione](../tests/results/d3-b-timeout-correction.md),
  [ambienti](qa/d3-b-environments.json), [scheda](d3/d3-b.md).

Punto di ripresa: **pianificazione D3-C soltanto su nuova richiesta**,
verificando branch/working tree e leggendo la relativa scheda e l’indice D3.
Non iniziare lo sviluppo o le altre milestone automaticamente.
La chiusura cambia soltanto documenti; nessun push, merge, deploy, scheduler
modificato o rebuild operativo. `reference_docs` aggiornata e ignorata da Git.
Le sezioni successive sono storiche; questa apertura prevale sulle vecchie
indicazioni di CI pendente.

---

# Aggiornamento handover — 9 ottobre 2026

**D3-B corretta localmente dopo il fallimento CI; nuova CI pendente.**
Il candidato iniziale `0df371c` non può chiudere la milestone.
Commit correttivo verificato: **`179f3ecaa7cb1fce0faa2ffe79931650bf359cb4`**.
Pacchetto **1.4.0**, schema **1**. **D3-C non avviata**.

Il timeout ora attende la conclusione effettiva dei figli prima di liberare
le protezioni, con limite di 5 s e controllo dei processi attivi via `ps`.
Linux ha riprodotto il difetto precedente 20 volte su 20; la correzione è verde.
405 PASS macOS 3.12; Linux 404 PASS/1 SKIP root, caso saltato poi PASS utente
normale. Sei test mirati PASS anche su Linux non privilegiato e Python 3.11/3.13.
Moduli scientifici, schema, retry e file Python/template della wheel invariati.
[Correzione ed evidenze](../tests/results/d3-b-timeout-correction.md).

Ripresa: pubblicare il nuovo candidato soltanto su richiesta e verificarne
la CI esatta Linux 3.11/3.12/3.13 e macOS 3.12 prima della chiusura formale.
Nessun push, deploy o rebuild operativo eseguito. Le sezioni successive sono
storiche e questa apertura aggiorna le loro indicazioni sul candidato.

---

# Handover D3-B — 8 ottobre 2026

**D3-B consegnata e verificata localmente su `dev`; CI hosted pendente.** Pacchetto **1.4.0**, SQLite **schema 1**. D3-A resta
formalmente chiusa; **D3-C…F non avviate**.

## Scheda di consegna D3-B

- Baseline `8892af5`, working tree pulito, un commit oltre origin/dev.
  Verifica di pianificazione: 70 PASS / 36,98 s, Python 3.12.15, `-W error`.
- Commit applicativo **`98d51d341e4d85bc7e14e6f4abf6273e8e42bc32`**.
  Il candidato finale comprende questo codice/test più documentazione.
- Una sola operazione per progetto, compresi progetti annidati; runtime
  condiviso per run/API, esclusivo per update. Archivio/file laterali, report,
  include e riepilogo protetti attraverso la conclusione dell’operazione.
- Registro privato dell’account in `/tmp`, percorsi canonici, lock persistenti,
  reentrancy senza promozione; conservato `<db>.lock`. API dei writer e letture
  operative partecipano; le ispezioni esplicitamente read-only restano senza lock.
- Avvio leggero CLI/modulo, recheck della configurazione, diagnostica JSON v1
  `coordination`. Update prima del backup, include/provenienza, arresto prima
  di installare se pull cambia destinazioni; nessun rollback automatico.
- Descrittori ereditati dai figli, timeout dell’intero gruppo, wrapper run senza
  contesa con il figlio. Nessuna opzione YAML/CLI aggiunta, niente D3-C.
- Test: **400 PASS** su macOS Python **3.11.17, 3.12.15 e 3.13.16**, con
  `-W error`, nessuno skip/XFAIL. 37 nuovi casi D3-B; regressioni scientifiche
  senza cambi di tolleranze. Wheel in tre venv nuovi: checker e pip check PASS.
- Risultati e limiti: [evidenze D3-B](../tests/results/d3-b-validation.md),
  [manifesto](qa/d3-b-environments.json), [scheda](d3/d3-b.md).
- Protezioni cooperative sullo stesso host/account Linux/macOS. Prima
  dell’introduzione operativa terminare i processi delle versioni precedenti.
  Nessun push, merge, deploy, modifica scheduler o rebuild dei dati dell’utente.

## Punto di ripresa

Verificare branch e working tree, poi pubblicare il candidato solo su richiesta.
Verificare CI sullo SHA esatto (Linux Python 3.11/3.12/3.13, macOS 3.12)
prima della chiusura formale. Non confondere validazione locale e hosted.
**Non iniziare D3-C; attendere una nuova richiesta dopo la chiusura D3-B.**

Le sezioni seguenti conservano le consegne storiche; questa apertura prevale
sulle loro indicazioni di ripresa.

---

# Handover D3-A — 8 ottobre 2026

**D3-A completata e formalmente chiusa su `dev` l’8 ottobre 2026.** Pacchetto **1.3.0**, SQLite **schema 1**. **D3-B…F non avviate**.
Questa apertura prevale sulle precedenti istruzioni di ripresa, conservate sotto
come storia di D3-0/D2. D2 rimane formalmente chiuso.

## Scheda sintetica di consegna D3-A

- Baseline `957aa968578613612477e00f34998f72ea2977a3`, dev un commit oltre
  origin/dev; modifiche documentali locali D3-0 preservate. Prima dello sviluppo:
  315 PASS in 127,38 s, Python 3.12.15, warning come errori, uscita 0.
- Commit applicativo **`64d787d035b134f4eaed9f7f8935964ec156c73e`**;
  candidato hosted **`be8b3d5202716679de7f46cf73ea984127e3aa8e`** (`be8b3d5`, solo
  documenti oltre il codice applicativo). Il successivo commit di chiusura è
  documentale e si identifica con git log; nessuna nuova CI gli è attribuita.
- Consegnati: isolamento del calcolo DETLIN per sequenza, diagnosi strutturate,
  retry SQLite limitati nelle letture e transazioni, contatori corretti dopo
  errori successivi. Schema/scienza/firme e ritorni pubblici invariati.
- Decisioni confermate: timeout 5 s, due retry con attese 0,25/0,5 s, politica
  fissa senza YAML/CLI; filename senza giorno blocca prudentemente la famiglia.
  Giorno/braccio resta atomico, force fallito preserva storico.
- Suite completa locale: **363 PASS su ciascuno di Python 3.11/3.12/3.13**,
  warning come errori, nessuno skip; verifiche e durate: [evidenze D3-A](../tests/results/d3-a-validation.md);
  [manifesto ambiente](qa/d3-a-environments.json). Nuovi casi D3-A: 48.
  Wheel 1.3.0 installata in tre venv puliti: checker isolato e pip check
  PASS su 3.11/3.12/3.13. Tutti gli input/output sono sintetici e temporanei.
- Documentazione aggiornata: [indice](d3-roadmap.md), [scheda A](d3/d3-a.md),
  contratti/operazioni, README/test, risultati/ambiente; roadmap/valutazione in
  reference_docs restano locali e ignorate. D3-0 conservata, evidenze D1/D2 invariate.
- Limiti: retry per operazione, non deadline dell'intero batch; backup, rename
  e drop_all non sono rilanciati. Renderer, update/pubblicazione, generazioni,
  retention/riuso restano da sviluppare nelle rispettive milestone.
- **Hosted PASS:** [run 37807882167](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37807882167), attempt 1;
  Linux 3.11/3.12/3.13 e macOS 3.12, **363 PASS per job**, build wheel e
  installazione isolata riuscite. Nessuna verifica D3-A pendente.
  L'utente ha pubblicato il candidato; questa chiusura non esegue nuovi push,
  merge, deploy, modifiche scheduler o rebuild dei dati dell'utente.
- Stima concordata 6–8 ore inclusi test/documentazione; attese CI escluse.
  È una stima di sviluppo, non un tempo misurato o un benchmark del batch.

## Punto di ripresa vincolante

Verificare branch/HEAD/working tree e leggere scheda A, evidenze e istruzioni test.
D3-A è chiusa senza verifiche pendenti. La prossima milestone è la
**pianificazione dettagliata D3-B**, soltanto su una nuova richiesta: leggere
[scheda B](d3/d3-b.md), ricontrollare il codice effettivo e chiarire le decisioni
aperte. Il commit documentale di chiusura non cambia il codice: distinguere SHA
applicativo, candidato effettivamente eseguito dalla CI e registrazione finale.
**D3-B non avviata; nessun avanzamento automatico o merge/deploy implicito.**

## Handover storico D3-0 — 8 ottobre 2026

**D2 completato e formalmente chiuso l’8 ottobre 2026** su `dev`, pacchetto **1.2.0**, SQLite
**schema 1**. **315 PASS su ciascuno di Python 3.11/3.12/3.13**, wheel isolata e
`pip check` verdi su tutti e tre. Verifiche e stato di chiusura sono registrati nei [risultati D2](../tests/results/d2-validation.md);
La [matrice hosted D2](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37793731551), attempt 1, è verde sul commit
`9f666b0e3382468ad7caf167d8437acabbe897c7`: 315 PASS in ciascuno dei quattro
job, build e installazione isolata riuscite. Nessuna funzionalità D3 implementata.

## Stato corrente e scheda di consegna D3-0

**D3-0 completato: solo roadmap e documentazione per l’handover.** D3-A…F
sono pianificate, non implementate. Il riferimento per ogni nuova sessione è
[l’indice D3](d3-roadmap.md), con schede [A](d3/d3-a.md), [B](d3/d3-b.md),
[C](d3/d3-c.md), [D](d3/d3-d.md), [E](d3/d3-e.md), [F](d3/d3-f.md).

- Baseline verificata: `dev`, HEAD `957aa968578613612477e00f34998f72ea2977a3`,
  working tree inizialmente pulito; un commit oltre `origin/dev` (`9f666b0`).
- Consegnati: indice versionato, sei schede, roadmap/valutazione locali,
  collegamento README e questo handover. `reference_docs/` resta ignorata.
- Decisioni registrate: report parziale con errore visibile e uscita 2;
  riuso solo su errore con data originale; due generazioni, orfani 24 ore,
  massimo due staging orfani. Dettagli comuni e questioni aperte nelle schede.
- Verifiche documentali: confronto con sorgenti D2, coerenza e link locali,
  confini di modifica e `git diff --check`; [evidenze D3-0](../tests/results/d3-0-validation.md).
- La suite della pianificazione, precedente alle modifiche documentali, ha dato
  **315 PASS in 128,22 s**, Python 3.12.15, `-W error`. Non è una nuova CI D3.
- Codice, config, pacchetto 1.2.0, schema 1 e dati invariati. Nessun commit/push,
  merge, deploy o rebuild operativo eseguito nella consegna D3-0.
- Stima pianificata D3-0: 2–4 ore; D3 completa 36–56 ore (5–7 giornate),
  incluse verifiche/documentazione, escluse attese CI; non è consuntivo.

**Prossima attività: pianificazione dettagliata di D3-A**, soltanto su nuova
richiesta. Leggere indice/scheda A, verificare branch/HEAD/working tree e risultati
D2, poi chiarire le questioni di A senza iniziare B o D4. Le dipendenze e la
procedura di consegna sono nell’indice; non richiedono il contesto della chat.
I documenti D3-0 sono modifiche locali da identificare tramite `git status`;
un futuro commit di consegna va registrato senza inventarne preventivamente lo SHA.

## Baseline e scheda di consegna D2 (storia conservata)

Commit applicativo **`7f0f657`** (`7f0f657c3727aed5221fa9fb3ab5a3ca5c4d04ed`),
successivo alla baseline `30a8914`. Suite, wheel e controllo visivo verificano
il codice archiviato in tale commit. Il successivo incremento è soltanto
la registrazione documentale di queste evidenze; identificare HEAD con
`git log --oneline`. L’utente ha pubblicato `dev`: il candidato hosted e
`origin/dev` sono `9f666b0`; `main` rimane a `8d44c9d`.
Il successivo commit di chiusura modifica soltanto la documentazione e non
ha un proprio risultato CI attribuito.

Baseline: `30a8914`, working tree pulito, `dev` un commit oltre `origin/dev`.
D1 formalmente chiuso sul codice `fb37d9e`, 216 PASS in ciascuno dei quattro job
[hosted 37772436524](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37772436524).
La verifica mirata iniziale durante la pianificazione D2 ha dato 58 PASS in 34,93 s.
La storia D1 resta in [evidenze D1](../tests/results/d1-validation.md) e
[chiusura D1](d1-closure.md).

Consegnati: configurazione dichiarativa validata, discovery coerente, metadati
HTML espliciti, schema versionato con identità sorgente/sequenza, provenienza QC,
fit DETLIN indipendenti e transazioni per giorno/braccio, lock comune ai writer,
rebuild separato con backup/coverage e sostituzione atomica. Nessuna conversione
scientifica del binning o nuova definizione di notte osservativa.

Incompatibilità operativa: archivi senza versione non sono aperti in scrittura
né migrati automaticamente. Preflight ordinario li rifiuta; dry-run può leggere
i registri legacy. Rebuild esplicito richiede storico recuperabile e connessioni
esterne chiuse. Non eliminarne le sentinelle per far passare la ricostruzione.
Il file `.lock` resta sul disco; la lease termina con la chiusura del processo.

## Documenti e riproduzione

Leggere [contratti D2](d2-contracts.md), [procedure operative](operations.md),
[istruzioni test](../tests/README.md) e i risultati prima della prossima attività.
La roadmap/valutazione locale in `reference_docs` viene aggiornata senza essere
inclusa in Git. Tutti gli input/output delle prove sono sintetici e temporanei.

```sh
python -m pytest -ra --tb=short -W error
python -m build --wheel --no-isolation --outdir /tmp/qc-wheel
/path/to/installed-env/bin/python scripts/check_installation.py
```

Ambienti osservati in [manifesto D2](qa/d2-environments.json); suite complete
senza warning pytest o skip, `actionlint` 1.7.12 verde. I percorsi temporanei
locali e le durate sono nei risultati.

La tavola [QA D2](qa/d2-reference.png) mostra latest/all per due sequenze
complete; il report sintetico standard con 12 figure resta verificato.
Nessuna regressione numerica viene sostituita con confronti pixel per pixel.

## Limiti e ripresa

- Matrice hosted D2 completata; distinguere il candidato verificato `9f666b0`
  dal successivo commit documentale di chiusura.
- Sequenze DETLIN su più date restano aperte. Binning assente assume 1 per asse
  con diagnosi; ROI e segnali restano nei pixel/ADU dell’immagine acquisita.
- Update e pubblicazione non sono coordinati dal lock D2. Coerenza HTML/PNG,
  retention immagini e isolamento per figura restano D3.
- Collaudo scientifico su dati rappresentativi, segnale di fine riduzione e
  prestazioni operative restano aperti. Riduzione completata prima del monitor.
- Backup retained per scelta; interruzione OS può lasciare uno staging non
  pubblicato. Nessuna pulizia generale o rielaborazione automatica dello storico.
- Push del candidato effettuato dall’utente. Questa chiusura non esegue nuovi
  push, merge, deployment o rebuild dei dati dell’utente.

Alla prossima sessione seguire il punto di ripresa D3-0 in apertura e leggere
i risultati D2. D2 resta chiuso, senza verifiche pendenti. D3-A non è avviata;
non pubblicare o integrare `main` automaticamente.

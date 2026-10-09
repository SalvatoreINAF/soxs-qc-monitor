# D3 — Roadmap delle milestone

**Aggiornamento: 8 ottobre 2026.** D3-0 documentale consegnato; D3-A
completata e formalmente chiusa; D3-B implementata localmente, CI pendente; D3-C…F
pianificate e non implementate.
Questo indice è il riferimento versionato per le nuove sessioni. La roadmap e
la valutazione in `reference_docs/` restano locali e intenzionalmente escluse da Git.

## Obiettivo e baseline

Rendere affidabile l'esecuzione batch e pubblicare report coerenti con spazio
limitato, conservando risultati scientifici e contratti di acquisizione D2.
La singola milestone è un incremento verificabile e consegnabile; indipendenza
non significa assenza di dipendenze dalle milestone indicate nella tabella.

Baseline D3-0: branch `dev`, HEAD `957aa968578613612477e00f34998f72ea2977a3`,
working tree inizialmente pulito, un commit documentale oltre `origin/dev` (`9f666b0`).
Pacchetto 1.2.0, SQLite schema 1. D2 formalmente chiuso: leggere
[contratti D2](d2-contracts.md), [risultati D2](../tests/results/d2-validation.md)
e [handover](handover.md). La verifica durante la pianificazione D3 ha dato
315 PASS in 128,22 s su Python 3.12.15 con warning come errori; non è una nuova
esecuzione hosted né una verifica di funzionalità D3.

D3-A: commit applicativo **`64d787d035b134f4eaed9f7f8935964ec156c73e`**,
pacchetto **1.3.0**, schema **1**; [evidenze locali e hosted](../tests/results/d3-a-validation.md).
[CI D3-A](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37807882167) verde sul candidato
`be8b3d5202716679de7f46cf73ea984127e3aa8e`, attempt 1: 363 PASS in ciascuno dei quattro
job, build e installazione isolata riuscite. D3-A chiusa, nessuna verifica pendente.
D3-B: commit applicativo `98d51d341e4d85bc7e14e6f4abf6273e8e42bc32`,
pacchetto **1.4.0**, schema **1**. [Evidenze locali](../tests/results/d3-b-validation.md)
e [ambienti](qa/d3-b-environments.json). CI D3-B pendente sul candidato esatto.
Ripresa: verifica e chiusura hosted D3-B; D3-C non avviata.

## Milestone, dipendenze e stime

| Milestone | Risultato | Dipendenze | Stato | Stima |
|---|---|---|---|---|
| D3-0 | Roadmap, schede e handover | D2 | Consegnata, solo documenti | 2–4 ore |
| [D3-A](d3/d3-a.md) | Isolamento acquisizione e retry limitati | D3-0 | Formalmente chiusa | 6–8 ore |
| [D3-B](d3/d3-b.md) | Coordinamento run, rebuild e update | D3-0 | Consegna locale, CI pendente | 8–12 ore |
| [D3-C](d3/d3-c.md) | Esiti delle figure e gestione dei renderer | D3-0 | Pianificata | 6–8 ore |
| [D3-D](d3/d3-d.md) | Motore di pubblicazione atomica, non attivo nella CLI | D3-B, D3-C | Pianificata | 6–10 ore |
| [D3-E](d3/d3-e.md) | Retention sicura e attivazione nella CLI | D3-D | Pianificata | 6–10 ore |
| [D3-F](d3/d3-f.md) | Riuso su errore e chiusura integrata | D3-A, D3-E | Pianificata | 6–10 ore |

Ordine operativo: **D3-0 → A → B → C → D → E → F**. A, B e C possono essere
consegnate separatamente a partire da D3-0; non è richiesto lavoro parallelo.
D verifica il motore senza attivarlo nel batch; E lo attiva quando il controllo
dello spazio è disponibile; F aggiunge il riuso su errore.

Stima complessiva: **38–58 ore, circa 5–8 giornate**, incluse verifiche e
documentazione, escluse attese CI. Sono stime di lavoro, non durate dei test.
La stima D3-A iniziale di 4–6 ore è aggiornata a 6–8 dopo la pianificazione
dettagliata: include preflight, cause SQLite avvolte e contese reali.
Ogni sessione si arresta alla milestone richiesta. D4 richiede la chiusura di
tutte le milestone applicative D3 e una nuova richiesta; non parte automaticamente.

## Decisioni comuni approvate

Le politiche seguenti descrivono il risultato futuro, non funzionalità già disponibili.

- Report parziale pubblicabile, con errori visibili; una figura fallita dà uscita
  **2** anche se il report viene pubblicato. Assenza dati distinta da errore.
  Acquisizione incompleta conserva il codice 1 in assenza di errori bloccanti.
- Riuso di immagini precedenti **solo su errore**, copiate nella nuova generazione
  con data originale e motivo. Nessun riuso per `no_data`; nessun riferimento
  transitivo a generazioni più vecchie. Compatibilità verificata in D3-F.
- Default di pubblicazione: **due generazioni** (corrente e precedente), età
  massima orfani **24 ore**, massimo **due staging orfani**. Lo staging è la
  directory temporanea di preparazione; il run attivo non è un orfano.
- Contesa tra operazioni protette: rifiuto immediato e uscita 2. File di lock
  persistenti; non eliminarli per sbloccare un processo. Nessun rollback
  automatico dell'update o rebuild automatico dopo un aggiornamento fallito.
- Timeout SQLite esplicito di **5 secondi** e **due retry aggiuntivi** solo per
  busy/locked, con attese di 0,25 e 0,5 secondi. Una transazione si riprova
  integralmente dopo rollback, senza anticipare i contatori. Non riprovare
  errori di schema, dati invalidi, permessi o disco pieno.
- Acquisizione/API pubbliche, schema SQLite 1 e tolleranze scientifiche
  conservati. Nessuna nuova notte osservativa, conversione del binning o
  migrazione automatica degli archivi sperimentali.
- JSON di riepilogo v1 esteso con campi additivi; distinguere dati committati,
  report pubblicato e cleanup. Versioni del pacchetto incrementate solo quando
  vengono consegnate funzionalità; D3-0 non cambia 1.2.0.
- Nessun push, merge, deploy, modifica di scheduler o rebuild dei dati dell'utente
  è implicito nella consegna. Tutte le prove usano input/output temporanei.

## Procedura comune di ripresa e consegna

1. Leggere [handover](handover.md), questo indice, la scheda della milestone e
   le evidenze delle dipendenze. La fotografia D2 nelle schede va ricontrollata
   sul codice effettivo, perché le milestone precedenti possono averlo cambiato.
2. Dalla radice del checkout controllare:

   ```sh
   git branch --show-current
   git status --short --branch
   git log -5 --oneline
   git rev-parse HEAD
   ```

   Lavorare su `dev`; preservare modifiche sopravvenute, senza reset o pulizie.
3. Verificare cosa è già implementato, chiarire le questioni aperte della scheda
   e fissare il piano della sola milestone richiesta prima di svilupparla.
4. Per milestone applicative eseguire test mirati e regressioni; seguire
   [istruzioni test](../tests/README.md) per ambiente, suite con `-W error`,
   wheel e installazione isolata. La chiusura formale richiede la matrice CI
   Linux 3.11/3.12/3.13 e macOS 3.12 sul candidato esatto. Se non pubblicato,
   dichiarare consegna locale e verifica hosted pendente, senza attribuire CI vecchie.
5. Aggiornare indice/stato e scheda, contratti e procedure coinvolte, README,
   istruzioni test, risultati `tests/results/d3-<lettera>-validation.md` e
   handover. Roadmap/valutazione locali ricevono il corrispondente aggiornamento.
6. La scheda sintetica di consegna indica baseline e commit applicativo,
   funzionalità, decisioni, verifiche realmente eseguite, evidenze, limiti,
   pendenze e prossimo punto di ripresa. Distinguere commit applicativo,
   candidato CI e successivi commit documentali. Fermarsi alla milestone.

D3-0 usa soltanto verifiche documentali: coerenza con il codice, collegamenti,
dipendenze, presenza delle sezioni e `git diff --check`. Non richiede una nuova
suite applicativa o CI per dichiarare completata la documentazione.
Evidenze: [verifica D3-0](../tests/results/d3-0-validation.md).


## Correzione timeout dopo CI — 9 ottobre 2026

CI 37818741442 sul candidato `0df371c`: Linux 3.11/3.12/3.13, 399 PASS
più lo stesso fallimento nel rilascio della lease dopo timeout; macOS 3.12 verde.
Il supervisore attendeva soltanto il processo principale dopo SIGKILL.
Riproduzione Linux del vecchio codice: **20 contese immediate su 20 prove**.

Correzione applicativa **`179f3ecaa7cb1fce0faa2ffe79931650bf359cb4`**:
attesa verificabile della fine dei processi attivi del gruppo, limite **5 s**,
scansioni `ps` ogni massimo 20 ms. Processi zombie/dead, che hanno già chiuso
le risorse, non impediscono il completamento. Mancata terminazione o errore
nell’ispezione resta bloccante; nessuna pausa fissa usata come prova di rilascio.
Richiesto `ps` di sistema (macOS; pacchetto `procps` su Linux minimale).
Pacchetto 1.4.0/schema 1 conservati, moduli della wheel invariati.

Suite aggiornata: **405 casi**, cinque nuovi rispetto alla consegna iniziale.
macOS Python 3.12.15: **405 PASS / 207,52 s**, `-W error`.
Docker Linux ARM64 Python 3.12.15: **404 PASS, 1 SKIP / 174,76 s** sotto root;
il caso sui permessi è poi passato con utente normale (**1 PASS / 1,04 s**).
Sei casi mirati del timeout, tutti PASS: Linux utente normale (2,57 s),
macOS Python 3.11.17 (2,33 s) e 3.13.16 (2,31 s).
Il test aggiunto ritarda la consegna di SIGKILL al figlio e pretende la lease
libera al ritorno del supervisore; verifica anche gruppi con zombie e limite
massimo dell’attesa. Formule, tolleranze, schema e retry invariati.

Questa correzione aggiorna la consegna locale precedente. **Nuova CI pendente**
sul nuovo candidato: Linux x86_64 3.11/3.12/3.13 e macOS 3.12. Le prove locali
Docker ARM64 non equivalgono alla matrice hosted. D3-B non formalmente chiusa;
nessun push/merge/deploy, nessun D3-C.
Dettagli: tests/results/d3-b-timeout-correction.md e
 docs/qa/d3-b-environments.json. Le verifiche wheel precedenti restano valide
per i moduli Python/template invariati; il supervisore corretto vive nel checkout.

# Handover D1 — 8 ottobre 2026

D1 è implementato su `dev`, versione pacchetto **1.1.0**. La chiusura formale
resta subordinata alla matrice hosted Linux/macOS. **Non iniziare D2**.
Nessun push, merge, pubblicazione o utilizzo dei dati operativi è stato eseguito.

## Stato Git e incrementi

- Baseline `8d44c9d`: `main` e `dev` identici, 177 PASS in 306,57 s.
- `aa46773`: esiti per famiglia/tabella, riepilogo JSON v1, codici CLI 0/1/2,
  salvataggio protetto e atomico, compatibilità dei loader e regressioni.
- `c61c6d6`: CI, wheel, ambiente fissato, supervisione tcsh/Python, timeout/log
  retention/freschezza, standalone default 0,60 e baseline analitica.
- `7732ddb`: gli errori di git/pip durante update sono bloccanti, con due regressioni aggiuntive.
- La consegna documentale segue questi incrementi; leggere `git log -4 --oneline`
  e `git status --short --branch` per identificarne HEAD e modifiche successive.
- `main` rimane a `8d44c9d`; `reference_docs` resta locale e ignorata da Git.

## Scheda sintetica di consegna

Esito del run esplicito, fasi temporizzate, UUID e orari UTC, versioni installate,
errori con fonte/motivo, unità aperte/chiuse/saltate e conteggi transazionali.
Dry-run e preflight emettono solo il riepilogo nel log. Le API di caricamento e
consolidamento mantengono i ritorni precedenti. Due aspettative CLI su QC fallita
passano da 0 a 1; gli invarianti di storage e i messaggi read-only restano coperti.

Ambiente Python 3.12 fissato, CI su `dev`/pull request, wheel verificata fuori dal
checkout. Wrapper con interprete unico, timeout di 2 ore, log 30 giorni e controllo
esterno a 48 ore. Backup di configurazione, revisioni, ambiente e SQLite prima
che l’helper update esegua pull/install; nessuna prova esegue update reali.

Baseline scientifica sintetica con attese indipendenti e tolleranze dichiarate;
12 grafici controllati e riferimenti HTML verificati nel layout standard.
Lo standalone rimane indipendente dal pacchetto, permette le librerie scientifiche
esterne e usa default 0,60 preservando gli override e le differenze intenzionali.

## Verifiche e riproduzione

Verifica finale locale sul codice `7732ddb`: **216 PASS in 483,91 s**,
Python 3.12.15, senza FAIL, XFAIL, XPASS, warning o skip. Compatibilità macOS:
212 PASS completi più 37 casi D1 e 14 casi supervisore rieseguiti su entrambe
le versioni 3.11.17 e 3.13.16; wheel isolata verificata su tutte e tre.

La suite corrente comprende **216 casi** (177 baseline + 39 D1), senza nuovi
XFAIL. Gli esiti effettivi e le durate sono in
[risultati D1](../tests/results/d1-validation.md). Il controllo wheel ha verificato
console entry point, import isolati, template incluso, configurazione e secondo
avvio idempotente su Python 3.11/3.12/3.13.

Vedere [istruzioni test](../tests/README.md) e
[ambiente e procedure](operations.md) per installazione e comandi riproducibili.
Le versioni osservate sono conservate in [manifesto ambienti](qa/d1-environments.json).
La [tavola QA](qa/d1-reference.png) è un riferimento visivo, non una golden image.
Nel browser sono state ispezionate entrambe le schede VIS/NIR del report sintetico.

## Limiti e punto di ripresa

1. Completare esclusivamente la verifica D1 hosted. Il workflow è configurato,
   ma non è stato eseguito su GitHub: il push richiede una richiesta esplicita.
   Non è disponibile un daemon Docker/runtime Linux locale; i risultati macOS
   non certificano Linux. Non dichiarare D1 completato finché la matrice non è verde.
2. Confermare job 3.11/3.12/3.13 Linux e 3.12 macOS sul candidato pubblicato.
   Astropy 6.1.2 su Python 3.13 è stato compilato da sorgente nel test locale;
   in CI è necessario il normale toolchain del runner.
3. Nessuna modifica allo schema, al supporto multisequenza o alla discovery.
   Lock e isolamento dei guasti per figura restano D3. Un rendering fallito dà 2.
4. HTML continua a usare `plots/` relativo alla pagina; immagini mancanti/stale,
   pubblicazione coerente e retention PNG restano D3. Il JSON atomico non estende
   queste garanzie al report.
5. La validazione su dati rappresentativi reali e l’eventuale segnale di fine
   riduzione restano nel collaudo operativo. Non eseguire rebuild per verificare D1.

Riprendere da questo file e dalla sezione 12 della roadmap locale. Fermarsi a D1
anche dopo la matrice verde; nessun passaggio automatico allo step successivo.

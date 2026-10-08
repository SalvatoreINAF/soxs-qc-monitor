# Chiusura formale di D1

**D1 formalmente chiuso l’8 ottobre 2026.** La matrice GitHub Actions è verde
su `fb37d9e`: [run 37772436524](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37772436524), attempt 1, con 216 PASS
per ciascuno dei quattro job e build/installazione isolate riuscite.

Questa procedura è conservata come riferimento per l’audit della chiusura e per
eventuali nuove verifiche del candidato `dev`; non descrive attività pendenti.
La chiusura non autorizza merge, pubblicazione operativa o avvio di D2.

## 1. Identificare il candidato

Leggere `docs/handover.md` e `tests/results/d1-validation.md`. La consegna
precedente è `c689c8b`, versione 1.1.0; il codice applicativo verificato localmente
è `7732ddb`, con 216 PASS su Python 3.12. Le successive modifiche documentali
vanno incluse nel candidato pubblicato, senza perdere le evidenze storiche.

Dalla radice del checkout:

```sh
git switch dev
git status --short --branch
git log -5 --oneline
git rev-parse HEAD
git diff --check
```

Registrare lo SHA completo del candidato. Il working tree deve essere pulito:
conservare eventuali modifiche sopravvenute, senza reset o pulizie automatiche.
Completare e registrare le modifiche pertinenti prima della verifica hosted.
Validare anche espressioni e contesti Actions con `actionlint` (release ufficiale
1.7.12 verificata durante il fix):

```sh
actionlint -shellcheck= -pyflakes= .github/workflows/tests.yml
```

La sola lettura del YAML non verifica questi vincoli. `runner.temp` non è
consentito nel blocco `env` del job; le cache vengono impostate dallo step Bash
tramite `$RUNNER_TEMP` e `GITHUB_ENV`.
Non usare il monitor con i percorsi operativi per questa procedura.

## 2. Pubblicare `dev` e avviare la verifica

**Prerequisito: richiesta esplicita dell’utente di eseguire il push.** Scrivere
questa procedura non concede tale autorizzazione. Il remoto configurato è
`git@github.com:SalvatoreINAF/soxs-qc-monitor.git`.

Dopo l’autorizzazione, verificare il remoto e pubblicare il candidato:

```sh
git remote -v
git push -u origin dev
```

Non usare force-push. Se il push viene rifiutato per divergenza, ispezionare le
modifiche remote prima di integrare; non sovrascrivere lavoro altrui. Ogni
integrazione cambia il candidato e richiede nuove verifiche pertinenti.
Non è necessario aprire una pull request o toccare `main`.

Il push a `dev` attiva `.github/workflows/tests.yml`. Aprire
[GitHub Actions](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions),
selezionare **D1 verification** e verificare che il run sia associato allo SHA
registrato. Se il workflow non parte, verificare disponibilità e abilitazione
Actions; non considerare l’assenza di un run come successo. Prima di avviare
manualmente una verifica, accertare che usi il branch `dev` e lo stesso SHA.

## 3. Criteri di accettazione hosted

Per ciascuno dei quattro job devono risultare riuscite tutte queste fasi:

1. Installazione delle dipendenze; `tcsh` presente sui runner Linux.
2. Suite scientifica e applicativa: 216 PASS sul candidato senza ulteriori
   modifiche ai test; registrare il conteggio effettivo se un fix legittimo
   aggiunge casi. Nessun FAIL, XFAIL o XPASS, né warning inattesi.
3. Build della wheel 1.1.0 con template HTML incluso.
4. Installazione in ambiente separato e `scripts/check_installation.py`:
   entry point, import isolati fuori checkout, configurazione e idempotenza.

Nessun job può essere fallito, cancellato, ancora in corso o saltato. Un eventuale
skip del solo test dei permessi read-only è ammesso esclusivamente quando i
privilegi del runner impediscono il controllo, come già previsto dalla suite H1:
registrarne motivazione e conteggio. Ogni altro skip richiede indagine.

Python 3.12 usa `requirements/reference-py312.txt`; 3.11/3.13 verificano le
esigenze dichiarate del pacchetto. Astropy 6.1.2 su 3.13 può richiedere build da
sorgente: l’installazione deve riuscire sul runner effettivo, non essere sostituita
da una precedente prova macOS.

Se un job fallisce, D1 resta aperto. Distinguere problemi transitori del servizio
da difetti riproducibili. Un retry senza modifiche deve mantenere lo stesso SHA.
Un fix di codice, test, dipendenze o workflow richiede un nuovo commit su `dev`,
verifiche locali appropriate e l’intera matrice hosted verde sul nuovo SHA.
Non aggiungere XFAIL, ridurre le aspettative o cambiare la baseline scientifica
per ottenere artificiosamente un esito verde. Non anticipare interventi D2/D3.

## 4. Registrare le evidenze e chiudere D1

Dopo la matrice verde, conservare in `tests/results/d1-validation.md`:

- SHA completo verificato, URL del run, run ID/attempt e data UTC;
- tabella dei quattro job: sistema, versione Python, conteggio PASS/skip,
  eventuali warning, durata, build e verifica dell’installazione;
- eventuali fix e relative motivazioni, distinguendo risultati nuovi e storici.

Scaricare i log del run come evidenza locale, se necessario; non versionare cache,
ambienti, wheel o log voluminosi. Il riferimento al run e la sintesi versionata
sono sufficienti per la normale consultazione.

Aggiornare `docs/handover.md`, `tests/README.md` e, se cambia il comportamento,
README/guida operativa. Aggiornare anche la sezione 12 della roadmap e l’addendum
alla valutazione in `reference_docs`, mantenendo questa cartella esclusa da Git.
Sostituire lo stato «chiusura hosted pendente» con «D1 completato», indicando le
evidenze. Conservare i limiti ancora assegnati a D2/D3 e al collaudo operativo.

Registrare un commit documentale di chiusura su `dev`. Distinguere esplicitamente
il commit verificato dal successivo commit delle evidenze; non attribuire al
secondo risultati CI ottenuti sul primo. Se viene pubblicato anche il commit di
chiusura, attendere il relativo workflow e verificarne l’esito. Qualsiasi modifica
funzionale durante questa registrazione riapre la verifica del candidato.

La scheda finale deve indicare branch, commit verificato e commit di chiusura,
URL della CI verde, versione, risultati, documenti aggiornati e limiti residui.
D1 è formalmente chiuso soltanto quando evidenze e handover sono registrati.

## 5. Arresto al confine concordato

Lasciare `main` invariato. Nessun merge finale, rebuild di archivi, rilascio,
aggiornamento della macchina operativa o esecuzione sui dati dell’utente.
**Non iniziare D2**, anche dopo la chiusura D1: attendere una nuova richiesta.

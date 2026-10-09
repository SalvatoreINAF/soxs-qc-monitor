# D3-D — Consegna e validazione locale, 9 ottobre 2026

**D3-D consegnata localmente su dev, pacchetto 1.6.0/schema 1.**
Commit applicativo **`a7a2ebb081f21a6b5e4330f2f200054fc480630d`**. CI hosted D3-D pendente sul candidato esatto;
D3-A/B/C restano formalmente chiuse, D3-E/F non avviate.

## Baseline, decisioni e funzionalità

Baseline `3a9b705f686a5967d91caffd2fb1da3ca6b431c7`, working tree pulito,
un commit documentale oltre origin/dev. [Audit pianificazione](d3-d-planning.md):
159 PASS / 81,97 s sul codice 1.5.0; non collaudo di D.
Decisioni concordate: HTML configurato unico commit point e fsync esplicito.
[Piano e contratto implementato](../../docs/d3/d3-d.md).

Consegnati motore interno con generazioni autosufficienti e proprietà v1,
manifesto v1, URL relativi codificati, validazione PNG/HTML, sincronizzazione
prima/dopo commit, lease B reentranti fino al cleanup, diagnosi pre/post commit.
HTML API compatibile con keyword image_urls; RunResult JSON v1 esteso con
publication, lasciato skipped nella CLI ordinaria. Adattatore esplicito per
registrare esiti/errori senza confondere pubblicazione con commit SQLite.
Nessuna attivazione CLI, retention, riuso, nuova opzione YAML/CLI o migrazione.
Formule/tolleranze, acquisizione, retry SQLite, schema e supervisore B invariati.

## Nuove prove

**59 casi D3-D**, 490 precedenti più 59 = **549 casi**. Nominale, parziale,
tutte figure vuote/fallite, generazioni successive/copie autonome; guasti di
render/PNG/manifesto/HTML/rename/replace e ogni posizione di fsync. Report
precedente confrontato byte per byte prima del commit; report published con
persistenza unconfirmed ed errore/uscita 2 dopo il commit. Esiti/apply_to,
configurazione originale preservata e JSON storage distinto.

File reali mancanti/corrotti, percorsi diversi con spazi/Unicode/#/?/%/&, filename
annidati, symlink in namespace/generazione/PNG/HTML/antenati, hardlink, FIFO,
file non regolari, marker invalidi/duplicati/proprietà alterata, collisioni con
input/config/template/DB/summary e temporanei preesistenti. Template con base,
immagini o link PNG estranei rifiutati; renderer reale e API legacy verificati.

Processi reali sincronizzati tramite READY/stdin: contesa in staging e dopo
finalizzazione, SIGKILL, report precedente integro, orfani posseduti e lease
libere prima del run successivo. Prova reentrancy sotto lease B già possedute.
Guasti di unlink/rmdir verificano marker conservato/ripristinato e diagnosi del
cleanup. Proprietà modificata dal renderer impedisce la pubblicazione.
CLI ordinaria con figura reale: pubblicazione diretta e publication skipped.
Tutti gli input/output applicativi sono sintetici e temporanei.

## Verifiche finali effettivamente eseguite

Suite locali **in sequenza**, warning come errori, nessun FAIL/XFAIL/XPASS:

| macOS 15.8 arm64 | Suite -W error | Durata | Wheel/checker/pip check |
|---|---|---|---|
| Python 3.12.15 | 548 PASS, 1 SKIP | 167.32 s | PASS |
| Python 3.11.17 | 548 PASS, 1 SKIP | 148.41 s | PASS |
| Python 3.13.16 | 548 PASS, 1 SKIP | 150.31 s | PASS |

L'unico SKIP per ogni suite macOS è la prova su due filesystem reali:
/dev/shm non disponibile e /tmp e /private/tmp sullo stesso dispositivo.
Il controllo deterministico delle destinazioni dei due rename passa comunque.
Questo skip non riguarda guasti, permessi o test di timeout.

**Linux Docker ARM64 Python 3.12.15: 59 PASS, 0 SKIP / 3.33 s**,
utente non privilegiato qcvalidation, repository montato read-only e copia
sintetica sotto /tmp/project. Prova reale fra /tmp e /dev/shm PASS. È una suite
mirata D3-D, non una nuova suite completa Linux né la matrice hosted x86_64.
Immagine locale python:3.12-slim; procps/tcsh/git e dipendenze solo nel contenitore
--rm. Nessun archivio operativo usato o immagine persistente creata.

Comandi locali, dalla radice del checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest tests/test_d3d_publication.py -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error
/private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d3d-wheel
/private/tmp/qc-d3d-installed312/bin/python scripts/check_installation.py
PIP_CACHE_DIR=/private/tmp/qc-d3d-pip-cache /private/tmp/qc-d3d-installed312/bin/python -m pip check
/private/tmp/qc-d1-reference/bin/python scripts/render_d3d_qa.py /private/tmp/qc-d3d-visual
```

Checker e pip check ripetuti negli ambienti isolati 311/313; pip check verde
anche nei tre ambienti sorgente. Wheel 1.6.0 costruita con --no-isolation,
SHA256 **`02d19680a0f16658a9ee7d970650178818c94e1d605ac28c6e73f1f8d1f1e5df`**. Tre venv nuovi con installazione
isolata; wheel finale reinstallata dopo la correzione del cleanup. Moduli e
risorsa HTML confrontati byte per byte fra wheel, checkout e installazioni:
identici. Checker -I fuori checkout verifica motore installato/renderer reale,
pubblicazione riuscita, callback fallito con vecchio report preservato,
adattatore e codice 2, oltre ai controlli D1–C. [Manifesto ambienti/hash](../../docs/qa/d3-d-environments.json).
I percorsi /private/tmp sono evidenze locali, non requisiti per un nuovo clone.

## Diagnostica e QA

Primo gruppo D mirato: 40 PASS/1 SKIP; regressioni C/RunResult insieme:
142 PASS/1 SKIP. Casi poi estesi per file/template/collisioni/cleanup.
Prima suite completa nel sandbox: 527 PASS/3 FAIL/1 SKIP, 187,23 s;
tutti i FAIL erano PermissionError del sandbox su ps nei tre timeout B.
Ripetute le suite con accesso ps, senza skip o modifiche ai test/supervisore:
545 PASS/1 SKIP sui tre interpreti, prima della correzione finale del cleanup.

L'audit finale ha rilevato che il marker poteva essere eliminato troppo presto
nel cleanup: ora è eliminato per ultimo e ripristinato se rmdir fallisce.
Aggiunti tre casi (due guasti di cleanup e proprietà alterata con rendering
riuscito); mirati 58 PASS/1 SKIP, 15,66 s. Le suite nella tabella sono tutte
successive a questa correzione. Nessuna tolleranza scientifica allargata.

QA ripetibile: renderer scientifico reale, errore di save reale confinato allo
staging, no_data NIR; screenshot Chrome headless con profili temporanei:
[nominale](../../docs/qa/d3-d-report-nominal.png),
[parziale corrente](../../docs/qa/d3-d-report-partial.png),
[copia archiviata](../../docs/qa/d3-d-report-archive.png),
[NIR](../../docs/qa/d3-d-report-nir.png), tutti ispezionati visivamente.
Immagini caricate, layout/diagnosi leggibili, nessun placeholder stale.
La vista NIR usa soltanto una copia QA nella directory del report, cambiando
i tab iniziali; nessun HTML pubblicato o template del prodotto modificato.
Il primo tentativo screenshot non produsse il file nei 15 s previsti; ripetuto
con mock keychain/profili temporanei e attesa limitata, immagini effettivamente
verificate. Nessuna golden image e nessun processo Chrome dell'utente terminato.

## Documentazione, limiti e ripresa

Aggiornati scheda/indice D3, handover, README, contratti/operazioni e istruzioni
test; audit/evidenze/manifesto/QA consegnati. Roadmap/valutazione in reference_docs
aggiornate localmente e ancora ignorate da Git. Link locali e git diff --check
verificati. Stima 10–14 ore incluso handover/test, attese CI escluse; non consuntivo.

CLI ancora diretta; D non limita crescita di generazioni/orfani e non riusa
immagini. Raggiungibilità locale non configura un server HTTP. Fsync non è una
garanzia assoluta contro power loss; sync finale fallito segnala published con
persistenza non confermata. Un filesystem che impedisce anche il ripristino del
marker può lasciare un residuo non adottabile automaticamente: diagnosi esplicita,
nessuna cancellazione di directory senza proprietà verificabile.

**Consegna locale, chiusura formale hosted pendente.** Non attribuire CI B/C al
codice D. Dopo pubblicazione autorizzata verificare candidato SHA esatto, attempt,
suite/build/checker per Linux 3.11/3.12/3.13 e macOS 3.12, poi registrare la
chiusura D. Distinguere commit applicativo e successivo commit documentale.
Nessun push/merge/deploy/scheduler/rebuild operativo. **D3-E/F non avviate**;
pianificazione E solo su nuova richiesta e dopo chiusura D.

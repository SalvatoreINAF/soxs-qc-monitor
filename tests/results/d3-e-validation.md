# D3-E — Validazione locale e hosted, 9 ottobre 2026

**D3-E formalmente chiusa su dev: 1.7.0/schema 1. CI hosted verde.**
D3-A/B/C/D restano formalmente chiuse; D3-F non avviata.
Baseline `3285f5bf4eb6b6600d9eafd81ca41bf2aabce525`, checkout inizialmente pulito.
Commit applicativo **`c48380dddaa33d48d2b66db4380bd454f0f7782b`**; commit successivo solo documentale.
Candidato hosted `9e5cdd0310b7314b859457ee82a94d8a6648ba45`, pubblicato dall’utente.
Nessun nuovo push/merge/deploy da questa sessione.
[Audit baseline](d3-e-planning.md), [contratto E](../../docs/d3/d3-e.md).

## Implementazione e decisioni

Default YAML centralizzati/validati, controllo dei percorsi/proprietà/storia prima
delle scritture DB, summary fuori dal namespace riservato anche attraverso symlink,
CLI collegata al motore atomico D. Rendering/letture indipendenti nello staging,
API legacy dei renderer/HTML conservate, report parziale e codici 0/1/2.
Retenzione della storia pubblicata e cleanup orfani sotto lease B, UTC/UUID come
ordinamento staging, nessun mtime. Generazioni orfane finalizzate eliminate al
prossimo avvio. Limiti 2 generazioni, 24 ore, 2 staging (configurabili).

Scelte approvate dall'utente: cleanup iniziale fallito blocca pubblicazione;
cleanup finale fallito mantiene il report valido; entrambi uscita 2, senza
ritirare il report o i dati già committati. JSON v1 additivo publication.cleanup
con esiti, conteggi e limiti verificati; staging_cleanup D invariato. Manifesto v1
aggiunge retained_history_length per aumentare N dopo precedenti potature senza
pretendere immagini eliminate; manifesto D3-D precedente leggibile.

60 nuovi casi E; 549 baseline + 60 = 609. Nessuna modifica a formule, tolleranze,
schema, acquisizione, retry SQLite o supervisore B. Checker installato aggiornato
per nuovo layout e fallimento reale di save confinato nello staging.

## Verifiche effettive

Suite completa con warning come errori, interpreti in sequenza:

| macOS 15.8 arm64 | Suite | Durata | Wheel/checker/pip check |
|---|---|---|---|
| Python 3.12.15 | 608 PASS, 1 SKIP | 184,19 s | PASS |
| Python 3.11.17 | 608 PASS, 1 SKIP | 162,89 s | PASS |
| Python 3.13.16 | 608 PASS, 1 SKIP | 164,25 s | PASS |

Skip macOS: secondo filesystem scrivibile assente. Invariante dei rename locali
verificata comunque; la prova reale passa su Linux. Nessuno skip per permessi.

**Linux Docker ARM64 Python 3.12.15: 119 PASS, 0 SKIP / 18,09 s.** Suite E+D
mirata, immagine locale python:3.12-slim, utente uid/gid 1000 non privilegiato,
repository montato read-only e soli sorgenti/test copiati sotto /tmp. Prova reale
fra /tmp e /dev/shm e permessi PASS. Non è suite Linux completa né CI hosted.
Freeze, versioni, hash e risultati in [manifesto ambienti](../../docs/qa/d3-e-environments.json).

Wheel 1.7.0: checker fuori checkout e pip check PASS sui tre venv isolati D3-D
riutilizzati, pacchetto reinstallato dalla nuova wheel senza dipendenze né import
dal checkout. Moduli/template identici byte per byte a wheel/checkout/installed sui tre interpreti.
Sorgenti scientifici/storage/schema/retry/supervisore identici alla baseline.

QA nominale, parziale e copia archiviata generata con renderer reali da
scripts/render_d3e_qa.py e ispezionata tramite screenshot Chrome headless:
[nominale](../../docs/qa/d3-e-report-nominal.png),
[parziale](../../docs/qa/d3-e-report-partial.png),
[archiviata](../../docs/qa/d3-e-report-archive.png).
PNG presente e nessuna immagine per failed/no_data; errore leggibile e URL
relativi validi per destinazioni distinte, Unicode e caratteri speciali.

## Tentativi intermedi distinti dal risultato finale

- Audit baseline: 248 PASS/1 SKIP, 92,83 s; non collaudo E.
- Suite mirata intermedia C/D/E: 202 PASS/1 SKIP, 50,20 s, prima dell'ultimo
  caso summary con symlink. Un precedente tentativo aveva un errore nella nuova
  fixture (tabella upstream già esistente), corretto creando il nuovo input.
- Tentativi completi nel sandbox interrotti: ps negato al test timeout B;
  nessuna modifica al supervisore per aggirarlo. Verifica finale fuori sandbox.
- Primo run completo fuori sandbox: 607 PASS, 1 FAIL, 1 SKIP, 183,76 s.
  Il caso B html sospendeva il writer legacy non più usato; adattato al motore
  atomico, stessi controlli di contesa preservati. Tre casi mirati PASS/13,31 s.
- Checker iniziale confrontava stringhe PNG nell'intero HTML e scambiava un
  percorso nella diagnosi per un'immagine. Corretto per leggere solo src delle
  immagini; checker finale verde sui tre interpreti.
- Chrome non avviabile nel sandbox; QA fuori sandbox su profili temporanei.
  Primo screenshot archiviato vuoto: rigenerato con attesa del rendering e
  ispezionato. Cache QA impostata prima degli import scientifici.

## Comandi e limiti

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d3e-verified312.xml
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py311/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d3e-verified311.xml
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-py313/bin/python -m pytest -ra --tb=short -W error --junitxml=/private/tmp/qc-d3e-verified313.xml
/private/tmp/qc-d1-reference/bin/python -m build --wheel --no-isolation --outdir /private/tmp/qc-d3e-wheel
/private/tmp/qc-d3d-installed312/bin/python scripts/check_installation.py
/private/tmp/qc-d3d-installed312/bin/python -m pip check
/private/tmp/qc-d1-reference/bin/python scripts/render_d3e_qa.py /private/tmp/qc-d3e-visual-final
```

I controlli scientifici restano sintetici, non accettazione su strumenti reali.
Retention per quantità/età, non byte; filesystem non disponibile può impedirla
con diagnosi e codice 2. Estranei, PNG legacy, backup e temporanei HTML senza
proprietà verificabile preservati; browser molto vecchi possono perdere immagini.
Server HTTP deve esporre entrambe le destinazioni; nessun cambio hosting automatico.
Stima approvata 12–16 ore incluse verifiche/handover, non consuntivo.

Chiusura formale E richiede CI sul candidato esatto Linux 3.11/3.12/3.13 e macOS
3.12. CI D3-D non attribuita a E. Pubblicazione soltanto su richiesta;
**fermata a D3-E, nessun D3-F/D4, push/merge/deploy/scheduler/rebuild operativo.**


## D3-E — Chiusura formale, 9 ottobre 2026

**D3-E completata e formalmente chiusa.** [CI 37981677957](https://github.com/SalvatoreINAF/soxs-qc-monitor/actions/runs/37981677957), attempt **1**,
sul candidato **`9e5cdd0310b7314b859457ee82a94d8a6648ba45`**. Suite con warning come errori:

| Job hosted | Esito suite | Durata | Wheel / checker isolato |
|---|---|---|---|
| Linux Python 3.11 | 609 PASS, 0 SKIP | 192,33 s | PASS |
| Linux Python 3.12 | 609 PASS, 0 SKIP | 232,66 s | PASS |
| Linux Python 3.13 | 609 PASS, 0 SKIP | 242,13 s | PASS |
| macOS Python 3.12 | 608 PASS, 1 SKIP | 336,86 s | PASS |

Nessun FAIL/XFAIL/XPASS. Lo skip macOS riguarda esclusivamente il secondo
filesystem scrivibile assente; la stessa prova reale passa nei tre job Linux.
Build wheel 1.7.0 e checker di installazione isolata PASS nei quattro job.
`pip check` verificato localmente, non separatamente dal workflow hosted.

Pacchetto **1.7.0**, SQLite **schema 1**. Commit applicativo **`c48380d`**,
candidato hosted **`9e5cdd0`**: differenze soltanto documentali, verificate.
**Nessuna verifica D3-E pendente.** Questa nota supera le indicazioni precedenti
di CI pendente; le prove locali restano evidenze storiche distinte.

L'utente ha pubblicato il candidato. Questa chiusura modifica soltanto documenti
ed evidenze, senza nuovo push/merge/deploy, scheduler o rebuild operativo.
Ripresa: **pianificazione D3-F soltanto su nuova richiesta**, dopo controllo di
checkout, indice, scheda F e handover. **D3-F non avviata; D3 non ancora chiusa.**

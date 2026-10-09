# D3-D — Audit della pianificazione, 9 ottobre 2026

Baseline `dev`, HEAD `3a9b705f686a5967d91caffd2fb1da3ca6b431c7`, pulita;
un commit documentale oltre origin/dev. Pacchetto 1.5.0/schema 1.
D3-B/C formalmente chiuse nelle evidenze archiviate; nessuna nuova CI interrogata.
Il confronto con candidato C `45257cc` non mostrava differenze applicative,
nei test Python, negli script o nel workflow. Pubblicazione diretta e HTML con
`plots/` fisso; nessun manifesto/generazione prima dell'implementazione D.

Letti roadmap/valutazione reference_docs, indice D3, handover, schede D/E/F,
evidenze B/C, contratti/configurazione, renderer/esiti, HTML, RunResult,
coordinamento, istruzioni test e workflow. Questioni risolte con l'utente:
HTML configurato unico punto di commit e fsync esplicito. Definiti layout,
manifesto/proprietà, crash/orfani, filesystem diversi e compatibilità delle API.
[Piano e contratto finale](../../docs/d3/d3-d.md).

Verifica pre-sviluppo effettivamente eseguita nella pianificazione:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest tests/test_d3c_rendering.py tests/test_run_result.py tests/test_d2_config.py -ra --tb=short -W error
```

**159 PASS / 81,97 s**, Python 3.12.15, pytest 8.4.2, macOS arm64; nessun
warning, skip o XFAIL. git diff --check verde e checkout rimasto pulito.
È audit della baseline 1.5.0, non validazione di D3-D. Stima approvata 10–14 ore,
inclusi test/documentazione, escluse attese CI, non consuntivo.

La pianificazione in chat non ha modificato file. Questa registrazione è creata
nella successiva implementazione autorizzata; risultati dello sviluppo separati
in [validazione D3-D](d3-d-validation.md). Nessun avanzamento a D3-E.

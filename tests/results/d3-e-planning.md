# D3-E — Audit e decisioni di pianificazione, 9 ottobre 2026

Baseline dev `3285f5bf4eb6b6600d9eafd81ca41bf2aabce525`, pulita, un commit
documentale oltre origin/dev. Versione 1.6.0/schema 1. D3-D formalmente chiusa.
Audit codice: motore atomico D già implementato, CLI ancora diretta, retention
assente. Letti reference_docs, indice/schede/handover, codice e risultati D.

Verifica mirata realmente eseguita prima dello sviluppo: **248 PASS, 1 SKIP /
92,83 s**, macOS Python 3.12.15, warning come errori. Skip per secondo filesystem
scrivibile assente, non per una funzionalità di retention. Comando:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest tests/test_d3d_publication.py tests/test_d3c_rendering.py tests/test_d2_config.py tests/test_run_result.py tests/test_read_only.py -ra --tb=short -W error
```

Decisioni dell'utente: bloccare pubblicazione se cleanup iniziale fallisce;
rimuovere al prossimo avvio gli orfani finalizzati fuori dalla storia conservata.
Default già approvati: N=2, età staging=24 ore, massimo staging=2. Validazione
prima delle scritture DB, storia da manifesti, marker e lease D/B conservati,
JSON v1 additivo, API legacy mantenute, niente riuso F.

Piano implementativo e accettazione in docs/d3/d3-e.md. Stima aggiornata da
6–10 a **12–16 ore**, incluse verifiche/handover, escluse attese CI. Questa
verifica appartiene alla baseline, non al collaudo del nuovo E.

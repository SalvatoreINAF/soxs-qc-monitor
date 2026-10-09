# D3-F — Audit e decisioni di pianificazione, 9 ottobre 2026

Baseline dev `9b38ea507e45887b35433fc379e134fa543f4936`, checkout pulito,
un commit documentale oltre origin/dev. Pacchetto 1.7.0/schema 1.
D3-A/B/C/D/E formalmente chiuse nelle evidenze locali/hosted registrate.
Letti reference_docs, indice, scheda F, handover, codice e risultati test.

Audit locale prima dello sviluppo: **251 PASS/1 SKIP, 86,52 s**, Python 3.12.15,
warning come errori. Skip solo per secondo filesystem scrivibile assente.
Questa esecuzione verifica la baseline, non il nuovo F:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/qc-d1-reference/bin/python -m pytest tests/test_d3d_publication.py tests/test_d3e_retention.py tests/test_d3c_rendering.py tests/test_run_result.py tests/test_read_only.py -ra --tb=short -W error
```

Decisioni dell'utente: compatibilità per figura; copia fallita degrada a report
parziale se la pulizia riesce, altrimenti blocca; data della prima produzione
in UTC distinta dai dati; fallback solo da manifesti F completi, niente adozione
E perché manca il database QC di origine. Nessun riuso no_data, nessun accesso
transitivo, uscita 2 conservata. Piano approvato integralmente per implementazione.

Contratto e criteri in docs/d3/d3-f.md. Stima aggiornata **12–16 ore** incluse
verifiche, QA, installazione e handover, escluse attese CI; non consuntivo.
Versione applicativa prevista/consegnata 1.8.0/schema 1. Fermata a F, nessun D4.

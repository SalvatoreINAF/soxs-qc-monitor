# D4 — Audit della baseline, 9 ottobre 2026

Branch dev, HEAD `ddf67a85793e8dd64bbac19fe29e7a84634b89f0`, checkout pulito,
un commit documentale oltre origin/dev. 1.8.0/schema 1. D3 formalmente chiusa
nelle evidenze salvate; differenze da candidato hosted fa9abac solo documentali.

Suite Python 3.12.15, pytest 8.4.2, macOS: **651 PASS, 3 FAIL, 1 SKIP / 245,94 s**,
`PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg python -m pytest -ra --tb=short -W error`.
Tre FAIL esclusivamente `PermissionError` per ps bloccato dalla sandbox:
test_timeout_terminates_real_job, test_timeout_kills_descendant_after_leader_exits,
test_timeout_waits_for_deferred_child_termination. Ripetizione con accesso ps
consentito: **3 PASS / 2,47 s**. Non è una suite completa unica verde.
Skip per secondo filesystem scrivibile assente sul Mac. Pip check e diff check PASS.

Schema/config/esiti/cleanup figure già centralizzati. Duplicazioni effettive nei
writer/registri, conversioni finite, discovery DSOL/OLOC e dispatch dei renderer;
main e plotting restano monolitici. Conservare seconda lettura config (recheck sotto
protezioni), formule, selezioni temporali e transazioni. Nessun difetto applicativo
emerso. Piano e scelte approvate in [scheda D4](../../docs/d4.md): refactoring completo,
moduli per famiglia e compatibilità degli import, incluso processing vuoto.
Stima 28–40 ore, verifiche/handover inclusi, attese CI escluse. Nessun D5.

# D3-C — Verifica della pianificazione, 9 ottobre 2026

**Pianificazione completata, sviluppo non avviato.** Questo documento registra
l'audit del codice corrente, non la validazione dell'implementazione futura C.

## Baseline e fonti

- Branch `dev`, HEAD **`08baf0c19bb839da23b46e5e942e9fff6db4d658`**;
  working tree inizialmente pulito, allineato a `origin/dev`.
- Pacchetto **1.4.0**, SQLite **schema 1**. D3-A/B formalmente chiuse.
- Letti roadmap/valutazione in `reference_docs`, indice/scheda C, handover,
  contratti D2, istruzioni test ed evidenze D3-B, comprese correzione timeout
  e chiusura hosted; esaminati CLI/bootstrap, config, renderer, HTML/template,
  RunResult, test scientifici e workflow.
- Il confronto `git diff 7a952c5972dfa7f00a0ccfefc5968e40f7e05d8a HEAD --
  qc_monitor tests/*.py scripts pyproject.toml .github/workflows/tests.yml`
  è vuoto: il codice corrente coincide con quello del candidato D3-B
  registrato come hosted verde. La CI non è stata interrogata o rieseguita;
  evidenza storica locale: [D3-B](d3-b-validation.md).

## Verifica applicativa mirata eseguita

Dalla radice del checkout, nell'ambiente di riferimento già disponibile:

```sh
/private/tmp/qc-d1-reference/bin/python -m pytest tests/test_scientific_rendering.py tests/test_run_result.py tests/test_d2_config.py -ra --tb=short -W error
```

**82 PASS in 81,80 s**, uscita 0; nessun warning, skip o XFAIL.
Include i renderer nominali, aspettative numeriche, HTML standard, vuoto e
fallimento save legacy, diagnostica CLI/JSON e validazione configurazione.
Le prove usano fixture sintetiche e directory temporanee. Questo risultato
non verifica ancora isolamento per figura, esiti C o report parziale C.

Ambiente: macOS **15.8 arm64**, Python **3.12.15**, pytest **8.4.2**,
numpy **2.1.0**, pandas **2.3.3**, matplotlib **3.10.8**, astropy **6.1.2**,
PyYAML **6.0.2**. Il percorso temporaneo dell'interprete è evidenza di questa
esecuzione, non requisito per un clone: usare le istruzioni in tests/README.

## Consegna documentale

[Piano C](../../docs/d3/d3-c.md): audit concreto, decisioni fissate,
ordine implementativo, matrice delle verifiche, stima **10–14 ore** incluse
prove/documentazione e attese CI escluse. Nessuna questione bloccante residua.
Aggiornati indice, handover, README, operations, contratti e istruzioni test;
roadmap/valutazione locali aggiornate senza cambiare l'esclusione da Git.

Verifiche documentali: collegamenti locali dei documenti modificati controllati;
`git diff --check` verde. Sorgenti, test applicativi, configurazioni, versione e
workflow invariati. Nessuna suite completa nuova, build wheel, prova su altri
interpreti o nuova CI: sono previste nella consegna dello sviluppo C.
Nessun commit/push/merge/deploy o rebuild operativo eseguito.

Ripresa: su nuova richiesta verificare il checkout e implementare solo C;
creare allora `d3-c-validation.md` con evidenze reali e ambiente/QA. Presentare
scheda sintetica finale e aggiornare handover; fermarsi prima di D3-D.

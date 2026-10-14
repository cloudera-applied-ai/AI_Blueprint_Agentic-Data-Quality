# governance/ — model cards

**Governance packaged** — model documentation travels with the repo, so intended use,
provenance, evaluation, and limitations ship alongside the solution rather than being bolted
on later.

## What goes here

| Path | Contents | Automated by |
|------|----------|--------------|
| `model-cards/` | One card per bundled/served model — [`column_classifiers.md`](./model-cards/column_classifiers.md) covers the three sklearn column classifiers; [`example_model_card.md`](./model-cards/example_model_card.md) is the blank template. | (authored; kept in step with `app/backend/classification/`) |
| `policies/` *(add as needed)* | SDX/Ranger-style access policies. Not yet packaged here — access is governed by CML project permissions; classified **sensitivity** columns (PII/PHI) are exactly what downstream Ranger policies would key on. | Cloudera SDX policy APIs |

## Conventions

- The bundled classifiers (`classification/models/*.pkl`) and any LLM used for
  classification fallback **must** be covered in [`model-cards/`](./model-cards/).
- Healthcare data caveat: uploads may contain PHI — the estate stays in-process (DuckDB),
  and only schema/profile summaries reach the LLM; keep it that way.
- Secrets never live here (or anywhere in the repo): LLM settings are UI-managed and
  gitignored.

Retraining the classifiers (`train_classifiers.py`) is the trigger to re-check the card.

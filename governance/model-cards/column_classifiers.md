# Model card — AGT Column Classifiers

- **Accelerator:** `cloudera-forge-healthcare-dataquality`
- **Serving:** in-process — loaded lazily by `app/backend/classification/classifiers.py`
  and exposed via the classification router and agent tools
- **Artifacts:** `app/backend/classification/models/{format,semantic_type,sensitivity}.pkl`
  (committed sklearn pipelines)
- **Model:** three scikit-learn text-feature classifiers over column names + metadata:
  **format** (data format), **semantic_type** (business meaning), **sensitivity**
  (PII/PHI/none)
- **LLM fallback:** low-confidence columns are re-classified by the configured LLM
  (`classification/llm_classifier.py`) — a separate, account-configurable endpoint.
- **NIM model ID:** _n/a (custom sklearn models)_

## Intended use

Automatic first-pass classification of healthcare AGT (member eligibility) columns to drive
profiling, quality rules, and sensitivity handling. Human review in the UI is part of the
intended workflow — classifications are suggestions, not decisions.

## Training / source data

- Labeled examples in `app/backend/classification/training_data/`, AGT-shaped (healthcare
  member-eligibility fields).
- Retrain with `python train_classifiers.py` (from `app/backend/`) after extending the
  training data.

## Evaluation

- Evaluated informally during development on held-out AGT fields; low-confidence
  predictions are routed to the LLM fallback and to human review rather than trusted.
- No versioned eval set ships yet — adding one under `tests/ai-eval/` is the standing
  gap (see [`../../tests/README.md`](../../tests/README.md)).

## Limitations & risks

- Trained on AGT-shaped healthcare fields — expect degraded accuracy on other verticals'
  schemas; retrain or lean on the LLM fallback there.
- **Sensitivity classification is advisory** — never the sole control for PHI handling;
  downstream Ranger/SDX policies must be authored by governance owners.
- The LLM fallback inherits whatever endpoint the account configures — its behavior is not
  pinned by this card.

## Owner

- Forge Engineering · <team-contact>

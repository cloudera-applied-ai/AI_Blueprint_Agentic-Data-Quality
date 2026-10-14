# ai/ — the AI layer

The intelligence of this accelerator: a streaming (SSE) **tool-calling agent** for
data-quality analysis plus **column classification** (three sklearn classifiers with an LLM
fallback). The implementation lives inside the backend package — the coupling is documented
in [ADR-001](../docs/architecture/ADR-001-monolithic-backend.md); this folder documents the
layer.

## Where the AI layer actually lives

| Component | Code |
|-----------|------|
| Agent loop (SSE, multi-round tool calling) | `app/backend/agent/agent_loop.py` |
| Agent tools (profile, detect issues, query, classify, generate flow/job/YAML) | `app/backend/agent/tools.py` |
| LLM client (OpenAI-compatible: Cloudera AI Inference or any endpoint) | `app/backend/agent/llm_client.py` |
| Prompts | `app/backend/agent/prompts.py` · `analysis_prompts` |
| Column classifiers (format · semantic type · sensitivity) | `app/backend/classification/` (`classifiers.py`, models in `classification/models/*.pkl`) |
| LLM classification fallback | `app/backend/classification/llm_classifier.py` |
| Classifier training | `app/backend/classification/train_classifiers.py` (labeled data in `classification/training_data/`) |

`notebooks/` and `inference/` *(add as needed)* — interactive walkthroughs and standalone
serving code would go here.

## Conventions

- Every served/bundled model gets a **model card** in
  [`../governance/model-cards/`](../governance/model-cards/) — the column classifiers' card
  is [`column_classifiers.md`](../governance/model-cards/column_classifiers.md).
- LLM credentials are UI-managed and persisted to the gitignored `app/backend/settings/` —
  never in code or env defaults.
- The agent's tools call the same code paths as the REST routers — one implementation, two
  front doors.

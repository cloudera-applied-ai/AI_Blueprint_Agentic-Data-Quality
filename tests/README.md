# tests/ — data quality · AI eval

The verification layer before a change ships. This accelerator's live verification is
manual-plus-probe today; this folder documents that harness and is where standalone suites
go as they are added.

## What verifies this accelerator today

| Check | Where | What it asserts |
|-------|-------|-----------------|
| Backend boot + static serving | `cd app/backend && uvicorn app:app` | The package imports (6 routers register) and `/` serves the built frontend. |
| LLM endpoint probe | [`llm_endpoint_probe.py`](./llm_endpoint_probe.py) | A configured Cloudera AI Inference endpoint answers a streamed completion (reads the workbench JWT from `/tmp/jwt`; edit the endpoint/model first). |
| End-to-end chat round trip | manual, in the UI | Upload → profile → chat → generate a NiFi flow / Spark job / YAML. |

## What goes here (as suites are added)

| Path | Contents |
|------|----------|
| `data-quality/` *(add as needed)* | Checks on profiling/issue detection against a golden AGT sample — profile values, issue codes (`VALID_CODES`), classification accuracy vs. labeled columns. |
| `ai-eval/` *(add as needed)* | A versioned eval set for the column classifiers + agent-tool regression prompts with expected tool-call sequences. |

## Conventions

- Evals must be runnable headless (plain `pytest tests/`) and offline where possible —
  `llm_endpoint_probe.py` is deliberately **not** named `test_*` so pytest never collects a
  network-dependent script.
- Generated-artifact tests should assert on the JSON/YAML the generators emit, not on
  downstream NiFi/CDE behavior.

There is no `make test`; the bar before shipping is: backend boots clean + a full chat
round trip against a configured endpoint.

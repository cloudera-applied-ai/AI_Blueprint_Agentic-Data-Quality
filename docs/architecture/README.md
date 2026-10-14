# docs/architecture/ — reference architecture & ADRs

## Architecture

This accelerator realizes the **build standard** (§5 of the operating model):

```
Ingest (pipe-delimited AGT upload → DuckDB) → Lakehouse (in-app DuckDB + versioned
generated assets) → Process (generated NiFi v2 flows + CDE Spark jobs for remediation) →
AI layer (agentic chat loop + column classifiers on Cloudera AI Inference) → Serve
(data-quality dashboard Application)
```

The deployed-platform view is the target-architecture slide,
[`../../assets/architecture.svg`](../../assets/architecture.svg), with the detailed
level 1–4 diagrams in [`../presentations/deck_build/diagrams/`](../presentations/deck_build/diagrams/).

- ADRs record any deviation from the standard stack:
  - **[ADR-001](./ADR-001-monolithic-backend.md)** — the agent and generators stay inside
    the monolithic `app/backend/` package rather than splitting into `ai/` and `pipelines/`
    layers; the app *generates* Process-layer artifacts at runtime.

## Design system (the `app/` / Serve layer)

The canonical Forge design-system docs live in the template repository,
`demo-design-template/docs/architecture/`, and are not copied here. This app's frontend
predates the template's adoption and keeps its own styling — the rationale is in
[ADR-001](./ADR-001-monolithic-backend.md).

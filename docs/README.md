# docs/ — app guide · architecture · business case

Everything a reviewer needs to understand *why* this accelerator exists and *how* it is built
and operated.

## Start here

- **[APP_GUIDE.md](./APP_GUIDE.md)** — the authoritative build/run guide for this
  application (formerly the root README): feature tour, LLM settings, Docker deployment,
  API walkthrough.
- **[DataQuality-AI-Executive-Summary.md](./DataQuality-AI-Executive-Summary.md)** and
  **[DataQuality-AI-Value-Proposition.md](./DataQuality-AI-Value-Proposition.md)** — the
  business case for this accelerator.

## What goes here

| Path | Contents |
|------|----------|
| `APP_GUIDE.md` | The authoritative build/run guide for this accelerator's application. |
| `architecture/` | Architecture notes and ADRs for deviations from the standard stack. |
| `DataQuality-AI-Executive-Summary.md` / `DataQuality-AI-Value-Proposition.md` | The business case and value proposition documents. |
| `presentations/` | Deck sources — the Cloudera brand toolkit, the deployment-blueprint deck, and its source diagrams (`deck_build/diagrams/` — drawio + PNG). |

## Conventions

- The **architecture** must conform to the build standard (Ingest → Lakehouse → Process →
  AI → Serve); where this accelerator deviates (the monolithic backend keeps the agent
  in-package), the deviation is recorded as an ADR in [`architecture/`](./architecture/).
- Operational facts cited in these docs come from the repo itself
  (`.project-metadata.yaml`, `app/backend/`) — never invented.

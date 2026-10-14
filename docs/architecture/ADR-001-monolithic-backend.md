# ADR-001 — Keep the monolithic backend package (agent + generators in-package)

**Status:** accepted · **Date:** 2026-08

## Context

The Forge standard separates the AI layer (`ai/agents/`) and the Process layer
(`pipelines/`) into their own top-level directories. This accelerator's backend
(`app/backend/`) is a single, tightly coupled FastAPI package:

- The agent (`agent/`) imports `config`, `data.*`, and `routers.data`; the routers import
  `agent.*` back — the coupling is **bidirectional**, and the process runs with
  `cwd = app/backend` (uvicorn `app:app`; the Dockerfile sets the same WORKDIR).
- The NiFi flow generator (`nifi/`), Spark job generator (`spark/`), and metadata YAML
  generator (`metadata/`) are agent tools and router endpoints — application features, not
  standalone pipeline scripts. Their **outputs** (versioned flows, jobs, YAML) are the
  Process-layer artifacts, written at runtime to `app/backend/{flows,spark_jobs,
  metadata_files}` (gitignored, bind-mounted in Docker).

Splitting `agent/` into `ai/agents/` would require rewriting imports in both directions and
re-plumbing `sys.path` for every entry point — pure churn against the restructure's "only
change code needed to run" rule.

## Decision

1. Move `02_backend` **intact** to `app/backend` and `03_frontend` to `app/frontend`;
   do not split the package.
2. `ai/README.md` and `pipelines/README.md` document where their layer's implementation
   actually lives (in-package) and what would move there if the backend is ever modularized.
3. Keep the frontend's existing design system (predates the Forge template).

## Consequences

- The `ai/` and `pipelines/` directories hold layer documentation (and future standalone
  suites), not code — readers are redirected by their READMEs.
- Runtime asset directories (`settings/`, `flows/`, `spark_jobs/`, `metadata_files/`,
  `classification_files/`) stay under `app/backend/` (gitignored; Docker bind-mounts) —
  the LLM settings file holds credentials and must never be committed or baked into images.
- A future modularization is localized: the import graph documented here is the work list.

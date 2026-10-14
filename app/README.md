# app/ — the data-quality assistant (Serve layer)

The user-facing application, run as a **CML Application**: `launch.py` starts the FastAPI
backend on `127.0.0.1:8090` and the frontend on `CDSW_APP_PORT` (locally: backend `:8000`,
Vite dev server `:5173`). The backend also serves the built frontend at `/` when
`frontend/dist` exists (the Docker path).

## What goes here

| Path | Contents |
|------|----------|
| `launch.py` | The Application entry point (AMP task 2) — environment detection (CML vs. standalone), starts backend + frontend, cleans up children on exit. |
| `backend/` | The monolithic FastAPI package (runs with cwd = `app/backend`, `uvicorn app:app`): `app.py` (mounts 6 routers + static frontend) · `routers/` (data, chat, nifi, spark, metadata, classification) · `agent/` (SSE tool-calling loop — the AI layer, see [ADR-001](../docs/architecture/ADR-001-monolithic-backend.md)) · `classification/` · `nifi/` · `spark/` · `metadata/` (generators) · `data/` (DuckDB loader/profiler) · `settings_store.py` + `settings/` (UI-managed LLM config, gitignored) · runtime asset dirs (`flows/`, `spark_jobs/`, `metadata_files/`, `classification_files/`, gitignored). |
| `frontend/` | React + TypeScript + Vite: chat, data explorer, profiling, classification review, generated-asset management. Vite proxies `/api` to the backend. |

## Run it

```bash
python app/launch.py                       # both services (auto-detects CML vs. local)
cd app/backend && uvicorn app:app --reload # backend only (:8000)
cd app/frontend && npm run dev             # frontend only (:5173, proxies /api)
docker compose up -d --build               # containerized → http://localhost:8000
```

## Conventions

- The backend **must run with cwd = `app/backend`** — internal imports and runtime asset
  paths are relative to it (launch.py, the Dockerfile WORKDIR, and compose all do this).
- LLM settings live in `backend/settings/` via the Settings panel — gitignored, and
  bind-mounted (not baked) in Docker.
- Business logic stays in the backend packages; routers only route.

Full operational guide: [`../docs/APP_GUIDE.md`](../docs/APP_GUIDE.md).

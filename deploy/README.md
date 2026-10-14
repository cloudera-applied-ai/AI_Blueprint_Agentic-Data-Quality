# deploy/ — CML AMP provisioning (in place of CDP CLI / Terraform)

Stands up the environment this accelerator runs in. There is no IaC here: the platform is an
existing **CML workspace**, and provisioning is an idempotent Python setup executed as the
AMP's first task — so the solution still deploys clean from the repo alone.

## What goes here

| Path | Contents | Automated by |
|------|----------|--------------|
| `install.py` | The full environment setup: Python deps from `app/backend/requirements.txt`, Node.js (if absent), and `npm install` for `app/frontend`. | CML AMP task 1 (`run_session`, 2 vCPU / 4 GB) |
| *(repo root)* `Dockerfile` · `docker-compose.yml` · `.dockerignore` | The container path — backend serves the built frontend; runtime asset dirs (settings, flows, jobs) are bind-mounted, never baked into layers. Root: Docker build-context convention. | `docker compose up -d --build` |

## Environment variables

- `CDSW_APP_PORT` — set by CML; the frontend binds it (backend stays on 127.0.0.1:8090).
- `BACKEND_HOST` / `BACKEND_PORT` — override the Vite dev proxy target locally.
- LLM provider settings are **UI-managed** (Settings panel → `app/backend/settings/`,
  gitignored) — not environment variables.

## Conventions

- Provisioning is **idempotent** — `install.py` reruns safely.
- Never put accelerator *logic* here — only the environment it runs on.

`python deploy/install.py` stands the environment up; `python app/launch.py` runs the app.

# Data Quality AI

An AI-powered assistant for analyzing healthcare member eligibility data (AGT format). It provides interactive chat-based data exploration, column profiling, automated quality issue detection, and generates Apache NiFi flows, CDE Spark jobs, and YAML metadata for data remediation.

## Features

- **Agentic Chat Interface** — Conversational data analysis powered by an LLM with tool-calling capabilities. The agent can run SQL queries, profile columns, detect quality issues, and generate NiFi flows, Spark jobs, and metadata YAML autonomously.
- **Column Profiling** — Statistical analysis of individual columns including value distributions, null rates, and pattern detection with optional AI-generated insights.
- **Quality Issue Detection** — Automated scanning for invalid codes, phone number format errors, length violations, corrupted data, and blank field anomalies.
- **NiFi Flow Generation** — Produces Apache NiFi v2 `VersionedDataflow` JSON with RouteOnAttribute processors using NiFi Expression Language to remediate detected issues.
- **CDE Spark Job Generation** — Generates PySpark scripts and CDE job definitions for data quality remediation, including flag columns, fix expressions, and valid/corrected/rejected data splitting.
- **YAML Metadata Generation** — Produces structured YAML data dictionaries with column definitions, data type inference, constraints, profiling statistics, and quality summaries.
- **Asset Management** — Save, edit, clone, delete, and version NiFi flows, Spark jobs, and metadata files with full revision history.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, Uvicorn |
| Frontend | React 19, TypeScript, Vite |
| Data Engine | DuckDB (in-memory) |
| LLM | OpenAI-compatible API (Ollama, Cloudera AI Inference) |
| Data Pipeline | Apache NiFi v2 |
| Batch Processing | CDE Spark (PySpark) |
| Streaming | Server-Sent Events (SSE) |

## Project Structure

```
dataquality-ai/
├── .project-metadata.yaml   # Cloudera AI platform manifest
├── launch.py                # Unified application launcher
├── 01_install/
│   └── install.py           # Dependency installer (Node.js, Python, npm)
├── 02_backend/
│   ├── app.py               # FastAPI entry point
│   ├── config.py            # Environment-based configuration
│   ├── requirements.txt     # Python dependencies
│   ├── agent/               # Agentic LLM loop (10 tools, function calling, SSE)
│   ├── data/                # DuckDB loader, profiler, metadata, issue detection
│   ├── nifi/                # NiFi v2 flow generator, templates, persistence
│   ├── spark/               # CDE Spark job generator, templates, persistence
│   ├── metadata/            # YAML metadata generator, persistence
│   └── routers/             # FastAPI route handlers (data, chat, nifi, spark, metadata)
├── 03_frontend/
│   ├── src/
│   │   ├── components/      # Chat, DataView, DataProfile, NiFiFlows, SparkJobs, MetadataFiles, Sidebar
│   │   ├── hooks/           # useChat, usePipeline, useAnalysisStream
│   │   ├── api/             # Typed API client + SSE streaming
│   │   └── types/           # TypeScript type definitions
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- An OpenAI-compatible LLM endpoint (Ollama running locally works out of the box)

## Quick Start

### Cloudera AI

The project includes a `.project-metadata.yaml` that defines two tasks for the Cloudera AI platform:

1. **Install Dependencies** — Run the `01_install/install.py` session to install Node.js, Python packages, and npm dependencies.
2. **Data Quality AI** — Launch the application. The launcher auto-detects the Cloudera environment and configures networking accordingly.

### Standalone

**Install dependencies:**

```bash
pip install -r 02_backend/requirements.txt
cd 03_frontend && npm install
```

**Run the application:**

```bash
python launch.py
```

This starts both the FastAPI backend (port 8000) and the Vite dev server (port 5173). The frontend proxies `/api` requests to the backend.

**Or run backend and frontend separately:**

```bash
# Terminal 1 — Backend
cd 02_backend && python app.py

# Terminal 2 — Frontend
cd 03_frontend && npm run dev
```

### Production Build

```bash
cd 03_frontend && npm run build
```

This generates `03_frontend/dist/`, which FastAPI serves automatically as static files.

## Configuration

All settings are controlled via environment variables with sensible defaults for local development with Ollama:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | _(unset)_ | Generic OpenAI-compatible API base URL (e.g. `https://api.openai.com/v1`); takes precedence over `CLOUDERA_AI_URL` |
| `LLM_MODEL` | _(unset)_ | Generic model name (e.g. `gpt-4o-mini`); takes precedence over `CLOUDERA_AI_MODEL` |
| `LLM_API_KEY` | _(unset)_ | Generic API key (e.g. `sk-...`); takes precedence over all other key sources |
| `CLOUDERA_AI_URL` | `http://localhost:11434/v1` | LLM API base URL |
| `CLOUDERA_AI_MODEL` | `qwen2.5:14b` | Model name |
| `CLOUDERA_AI_KEY` | `ollama` | API key |
| `LLM_ENDPOINT_TYPE` | `ollama` | Endpoint type identifier (`ollama`, `openai`, or `openai-compatible` for Cloudera AI Inference) |
| `CDSW_APP_PORT` | _(auto-detected)_ | Cloudera app port (frontend binds to this) |

The LLM endpoint can also be reconfigured at runtime via the sidebar in the UI (Ollama, OpenAI Compatible, or Cloudera Inferencing) or the `/api/chat/configure` endpoint.

## Data Format

The application expects **AGT member eligibility data**:

- **Data file**: Pipe-delimited (`|`) text file (e.g., `AGT_simulated_data.txt`)
- **Metadata file**: JSON with column definitions including field names, max lengths, data types, and valid code sets (e.g., `AGT_metadata.json`)

Data can be loaded from the default location or uploaded through the UI.

## Architecture

```
Frontend (React/TS/Vite)  ──SSE + JSON──▶  FastAPI Backend
                                              │
                ┌──────────┬──────────┬───────┼───────┬──────────┐
                ▼          ▼          ▼       ▼       ▼          ▼
          routers/    routers/   routers/  routers/ routers/   /api/health
          data.py     chat.py    nifi.py   spark.py metadata.py
              │            │          │       │       │
          data/        agent/      nifi/   spark/  metadata/
          loader       agent_loop  flow_   job_    yaml_
          profiler     tools (9)   generator generator generator
          metadata     llm_client  flow_   job_    meta_
                       prompts     store   store   store
                                   templates templates
```

### Key Modules

- **`agent/`** — Agentic loop with OpenAI function-calling. Iterates up to 10 times per message, executing 10 tools (SQL queries, profiling, issue detection, field metadata, code validation, NiFi flow generation, Spark job generation, metadata YAML generation, data summary, column classification) and streaming results back via SSE. Includes a fallback parser for models that don't support native function calling.
- **`data/`** — DuckDB-based data loading (all columns as VARCHAR, pipe-delimited), column profiling with statistical analysis, and quality issue detection driven by field metadata flags.
- **`nifi/`** — Generates NiFi v2 VersionedDataflow JSON from detected quality issues. Flow persistence uses filesystem storage (`flows/{uuid}/v{N}.json`) with a manifest index and thread-safe file locking.
- **`spark/`** — Generates CDE Spark job definitions and PySpark scripts for data quality remediation. Uses batched `.select()` for flag columns (performance optimization over sequential `.withColumn()`). Includes field name and code value validation via regex. Same versioned persistence pattern as NiFi flows.
- **`metadata/`** — Generates structured YAML data dictionaries with inferred data types, column constraints, profiling statistics, and quality summaries. Same versioned persistence pattern.
- **`routers/`** — FastAPI route handlers organized by domain: data management, chat/agent, NiFi flow CRUD, Spark job CRUD, and metadata file CRUD.
- **`frontend/`** — React SPA with five main views: Chat, Data Profile, NiFi Flows, Spark Jobs, and Metadata Files. Uses custom hooks for SSE streaming and a typed API client.

### Persistence

All generated assets (NiFi flows, Spark jobs, metadata files) use the same versioned filesystem pattern:

```
02_backend/{asset_type}/
├── manifest.json           # Index of all saved assets
└── {uuid}/
    ├── v1.json             # Version 1
    ├── v2.json             # Version 2
    └── ...
```

Each store maintains an in-memory manifest cache with O(1) lookups and thread-safe file locking.

### API Routes

All routes are prefixed with `/api/`:

| Prefix | Endpoints |
|--------|-----------|
| `/api/data/*` | Load data, upload, query, profile columns, detect quality issues |
| `/api/chat/*` | LLM configuration, connection testing, agent chat (SSE) |
| `/api/nifi/*` | NiFi flow generation, CRUD, version management, cloning |
| `/api/spark/*` | Spark job generation, CRUD, version management, cloning |
| `/api/metadata/*` | Metadata YAML generation, CRUD, version management, cloning |
| `/api/health` | Health check |

### Agent Tools

The agentic chat interface exposes 10 tools to the LLM:

| Tool | Description |
|------|-------------|
| `run_sql_query` | Execute read-only DuckDB SQL against the AGT table |
| `profile_column` | Statistical profiling of a single column |
| `detect_quality_issues` | Scan for data quality issues |
| `get_field_metadata` | Retrieve field definitions and constraints |
| `validate_coded_values` | Check values against valid code sets |
| `generate_nifi_flow` | Generate a NiFi v2 dataflow for issue remediation |
| `generate_spark_job` | Generate a CDE Spark job for issue remediation |
| `generate_metadata_yaml` | Generate a YAML data dictionary |
| `get_data_summary` | Get an overview of loaded data |
| `classify_metadata` | Classify columns for sensitivity (PII/PHI), semantic type, business terms, HL7/FHIR mappings and regulatory tags |

## Security

- Field names validated via `^[A-Za-z_][A-Za-z0-9_]*$` regex
- Code values validated via `^[A-Za-z0-9 _.-]*$` regex
- Job/flow IDs validated as UUIDs at function entry
- Path traversal protection via `resolve()` + `startswith()` containment
- SQL injection prevention via field name validation against loaded fields
- Output formats enforced with Literal types and set-based whitelists

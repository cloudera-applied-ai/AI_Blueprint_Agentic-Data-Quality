# pipelines/ — the Process layer (generated at runtime)

This accelerator **generates** its Process layer instead of shipping one: the agent and the
API turn detected quality issues into remediation pipelines on demand. The generators live
inside the backend package (see
[ADR-001](../docs/architecture/ADR-001-monolithic-backend.md)); this folder documents the
layer and is where standalone pipeline scripts would go if any are added.

## Where the Process layer actually lives

| Generator | Code | Output (runtime, gitignored) |
|-----------|------|------------------------------|
| NiFi v2 flow generator | `app/backend/nifi/flow_generator.py` | `app/backend/flows/` — importable NiFi flow JSON |
| CDE Spark job generator | `app/backend/spark/job_generator.py` | `app/backend/spark_jobs/` — PySpark remediation jobs |
| Metadata YAML generator | `app/backend/metadata/yaml_generator.py` | `app/backend/metadata_files/` — field metadata YAML |

All three are exposed both as **agent tools** (generate from chat) and as REST routers, and
their outputs are **versioned** by the asset store.

## Conventions

- Generated artifacts are deployment inputs for **NiFi 2** and **Cloudera Data Engineering**
  — download from the UI and import/submit there.
- If a standalone, scheduled pipeline is ever added (e.g. batch re-profiling), it goes here
  as a numbered script and gets declared in `.project-metadata.yaml`.

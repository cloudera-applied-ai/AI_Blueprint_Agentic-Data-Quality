# data/ — the Lakehouse snapshot

The **Ingest + Lakehouse** layers of this accelerator are **runtime-fed**: the user uploads
a pipe-delimited AGT (member eligibility) extract in the app, and it lands in an in-process
DuckDB estate. This folder is the placeholder for any packaged datasets.

## Where the data actually lives

| What | Where | Automated by |
|------|-------|--------------|
| Sample field metadata | `app/backend/AGT_metadata.json` — the AGT layout (field names, types, descriptions) that drives profiling and classification when no custom metadata is supplied. | ships with the repo |
| The queryable estate | DuckDB, in-process in the backend (no file to manage; rebuilt per upload). | `app/backend/data/loader.py` |
| Classifier training data | `app/backend/classification/training_data/` — labeled examples for the three column classifiers. | `app/backend/classification/train_classifiers.py` |
| Generated assets | `app/backend/{flows,spark_jobs,metadata_files,classification_files}/` — versioned runtime outputs (gitignored; bind-mounted in Docker). | the agent + routers |

## Conventions

- Put **packaged datasets** here if this accelerator ever ships one; today the demo runs on
  the customer's own upload plus the in-repo AGT metadata.
- Uploaded data is the customer's — never commit an extract.

The upload API is this accelerator's Ingest — see the `/api/data/*` endpoints in
[`../docs/APP_GUIDE.md`](../docs/APP_GUIDE.md).

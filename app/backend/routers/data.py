"""Data loading, profiling, and query endpoints."""

import json
import os
import tempfile
import threading

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import config
from data.metadata import parse_metadata, get_column_names
from data.loader import create_connection, load_data, run_query
from data.profiler import profile_column, detect_quality_issues

router = APIRouter(prefix="/api/data", tags=["data"])

# In-memory state — _db_lock serialises all DuckDB access so concurrent
# requests (e.g. pipeline SSE + metadata detect-issues) don't corrupt memory.
_db_lock = threading.Lock()

_state = {
    "conn": None,
    "fields": None,
    "row_count": None,
    "loaded": False,
}


def get_state():
    return _state


def get_db_lock():
    return _db_lock


class QueryRequest(BaseModel):
    sql: str


class ProfileRequest(BaseModel):
    field_name: str


class DetectRequest(BaseModel):
    field_names: list[str] = []


class SchemaRequest(BaseModel):
    table_name: str | None = None


@router.post("/load")
def load_preloaded():
    """Load the pre-existing AGT data files."""
    data_path = config.DEFAULT_DATA_PATH
    meta_path = config.DEFAULT_METADATA_PATH

    if not os.path.exists(data_path):
        raise HTTPException(404, f"Data file not found: {data_path}")
    if not os.path.exists(meta_path):
        raise HTTPException(404, f"Metadata file not found: {meta_path}")

    try:
        fields = parse_metadata(meta_path)
        conn = create_connection()
        row_count = load_data(conn, data_path, fields)

        _state["conn"] = conn
        _state["fields"] = fields
        _state["row_count"] = row_count
        _state["loaded"] = True

        return {
            "status": "ok",
            "row_count": row_count,
            "column_count": len(fields),
            "columns": [f.field_name for f in fields],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/upload")
async def upload_files(
    data_file: UploadFile = File(...),
    metadata_file: UploadFile = File(...),
):
    """Upload data + metadata files and load into DuckDB."""
    try:
        # Write uploaded files to temp dir
        tmp_dir = tempfile.mkdtemp()
        data_path = os.path.join(tmp_dir, "data.txt")
        meta_path = os.path.join(tmp_dir, "metadata.json")

        with open(data_path, "wb") as f:
            content = await data_file.read()
            f.write(content)

        with open(meta_path, "wb") as f:
            content = await metadata_file.read()
            f.write(content)

        fields = parse_metadata(meta_path)
        conn = create_connection()
        row_count = load_data(conn, data_path, fields)

        _state["conn"] = conn
        _state["fields"] = fields
        _state["row_count"] = row_count
        _state["loaded"] = True

        return {
            "status": "ok",
            "row_count": row_count,
            "column_count": len(fields),
            "columns": [f.field_name for f in fields],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/status")
def data_status():
    """Check if data is loaded."""
    if not _state["loaded"]:
        return {"loaded": False}
    return {
        "loaded": True,
        "row_count": _state["row_count"],
        "column_count": len(_state["fields"]) if _state["fields"] else 0,
    }


@router.post("/query")
def execute_query(req: QueryRequest):
    """Execute a read-only SQL query."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")
    try:
        with _db_lock:
            result = run_query(_state["conn"], req.sql)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/profile")
def profile(req: ProfileRequest):
    """Profile a single column."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")

    fname = req.field_name.upper()
    field = next((f for f in _state["fields"] if f.field_name == fname), None)
    if not field:
        raise HTTPException(404, f"Field '{fname}' not found")

    with _db_lock:
        result = profile_column(_state["conn"], field)
    return result.to_dict()


@router.post("/detect-issues")
def detect_issues(req: DetectRequest):
    """Detect quality issues across columns."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")

    target = req.field_names if req.field_names else None
    with _db_lock:
        issues = detect_quality_issues(_state["conn"], _state["fields"], target)
    return [i.to_dict() for i in issues]


@router.get("/columns")
def list_columns():
    """List all columns with metadata."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")
    return [
        {
            "position": f.position,
            "field_name": f.field_name,
            "max_length": f.max_length,
            "business_name": f.business_name,
            "is_code_field": f.is_code_field,
            "is_date_field": f.is_date_field,
            "is_phone_field": f.is_phone_field,
            "is_blank_field": f.is_blank_field,
        }
        for f in _state["fields"]
    ]


@router.post("/generate-schema")
def generate_schema(req: SchemaRequest):
    """Generate JSON Schema and column definitions from field metadata."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")

    from data.profiler import VALID_CODES

    fields = _state["fields"]
    conn = _state["conn"]
    table_name = req.table_name or config.TABLE_NAME
    total_rows = _state["row_count"] or 0

    properties = {}
    required = []
    columns = []

    for fld in fields:
        col = fld.field_name

        # Count nulls for this field
        with _db_lock:
            null_count = conn.execute(
                f'SELECT SUM(CASE WHEN "{col}" IS NULL OR TRIM("{col}") = \'\' THEN 1 ELSE 0 END) FROM {config.TABLE_NAME}'
            ).fetchone()[0] or 0
        nullable = null_count > 0

        prop: dict = {"type": "string", "maxLength": fld.max_length}
        col_def: dict = {
            "name": col,
            "type": "string",
            "maxLength": fld.max_length,
            "nullable": nullable,
            "format": None,
            "constraints": None,
            "notes": None,
        }

        if fld.is_blank_field:
            col_def["notes"] = "Blank/unused field"
        else:
            if not nullable:
                required.append(col)

            if fld.is_date_field:
                prop["format"] = "date"
                col_def["format"] = "date"
                col_def["notes"] = "Date field (YYYYMMDD)"

            if fld.is_phone_field:
                prop["format"] = "phone"
                prop["pattern"] = r"^[2-9]\d{9}$"
                col_def["format"] = "phone"
                col_def["notes"] = "US phone number (10 digits)"

            if col in VALID_CODES:
                valid = VALID_CODES[col]
                prop["enum"] = valid
                col_def["constraints"] = {"enum": valid}
                col_def["notes"] = "Code field"

            if col_def["notes"] is None:
                is_id = col.endswith("ID") or col.endswith("NBR") or col.endswith("KEY")
                if is_id:
                    col_def["notes"] = "Identifier field"

        properties[col] = prop
        columns.append(col_def)

    json_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": table_name,
        "type": "object",
        "properties": properties,
        "required": required,
    }

    return {"json_schema": json_schema, "columns": columns}


@router.get("/preview")
def preview_data(limit: int = 100):
    """Get a preview of the data."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")
    with _db_lock:
        result = run_query(_state["conn"], f"SELECT * FROM {config.TABLE_NAME} LIMIT {min(limit, 1000)}")
    return result


# ---------------------------------------------------------------------------
# SSE endpoints: structured data first, then streaming LLM analysis
# ---------------------------------------------------------------------------

@router.post("/pipeline")
async def run_pipeline():
    """Run the full data quality pipeline as SSE: profile → detect → schema → rules."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")

    conn = _state["conn"]
    fields = _state["fields"]

    async def event_generator():
        try:
            # --- Stage 1: Profiling ---
            non_blank = [f for f in fields if not f.is_blank_field]
            total = len(non_blank)
            yield {"event": "stage", "data": json.dumps({"stage": "profiling", "status": "started", "total": total})}

            profiles = []
            for i, fld in enumerate(non_blank):
                try:
                    with _db_lock:
                        prof = profile_column(conn, fld)
                    prof_dict = prof.to_dict()
                    profiles.append(prof_dict)
                    yield {"event": "profile_result", "data": json.dumps(prof_dict)}
                except Exception:
                    pass
                yield {"event": "stage", "data": json.dumps({"stage": "profiling", "status": "progress", "completed": i + 1, "total": total})}

            yield {"event": "stage", "data": json.dumps({"stage": "profiling", "status": "completed"})}

            # --- Stage 2: Issue Detection ---
            yield {"event": "stage", "data": json.dumps({"stage": "detecting", "status": "started"})}

            with _db_lock:
                issues = detect_quality_issues(conn, fields)
            issues_dicts = [iss.to_dict() for iss in issues]
            yield {"event": "issues_data", "data": json.dumps(issues_dicts)}
            yield {"event": "stage", "data": json.dumps({"stage": "detecting", "status": "completed", "count": len(issues_dicts)})}

            # --- Stage 3: Schema Recommendation (LLM) ---
            yield {"event": "stage", "data": json.dumps({"stage": "schema", "status": "started"})}

            try:
                from routers.chat import resolve_llm_client
                from agent.analysis_prompts import schema_recommendation_prompt
                from agent.analysis_stream import stream_analysis

                client, model = resolve_llm_client()

                fields_meta = [
                    {
                        "field_name": f.field_name,
                        "max_length": f.max_length,
                        "is_code_field": f.is_code_field,
                        "is_date_field": f.is_date_field,
                        "is_phone_field": f.is_phone_field,
                        "is_blank_field": f.is_blank_field,
                    }
                    for f in fields
                ]

                system_prompt, user_content = schema_recommendation_prompt(profiles, issues_dicts, fields_meta)

                async for evt in stream_analysis(client, model, system_prompt, user_content):
                    if evt["event"] == "content":
                        yield {"event": "schema_content", "data": json.dumps(evt["data"])}

                yield {"event": "stage", "data": json.dumps({"stage": "schema", "status": "completed"})}
            except Exception as e:
                yield {"event": "stage", "data": json.dumps({"stage": "schema", "status": "skipped", "reason": str(e)[:200]})}

            # --- Stage 4: Rules Derivation ---
            yield {"event": "stage", "data": json.dumps({"stage": "rules", "status": "started"})}

            total_rows = _state["row_count"] or 1
            rules = []
            for idx, iss in enumerate(issues_dicts):
                pct = iss.get("affected_pct", 0)
                if pct > 50:
                    severity = "critical"
                elif pct > 10:
                    severity = "high"
                elif pct > 1:
                    severity = "medium"
                else:
                    severity = "low"

                rules.append({
                    "id": idx + 1,
                    "field_name": iss["field_name"],
                    "issue_type": iss["issue_type"],
                    "description": iss["description"],
                    "affected_count": iss["affected_count"],
                    "affected_pct": iss["affected_pct"],
                    "sample_bad_values": iss.get("sample_bad_values", []),
                    "suggested_fix": iss["suggested_fix"],
                    "params": iss.get("params", {}),
                    "severity": severity,
                    "enabled": True,
                })

            yield {"event": "rules_data", "data": json.dumps(rules)}
            yield {"event": "stage", "data": json.dumps({"stage": "rules", "status": "completed"})}

            # --- Stage 5: NiFi Flow Generation ---
            yield {"event": "stage", "data": json.dumps({"stage": "nifi_generation", "status": "started"})}
            try:
                from nifi.flow_generator import generate_flow_json
                from nifi.flow_store import save_flow

                nifi_flow_json = generate_flow_json(issues)
                nifi_flow_obj = json.loads(nifi_flow_json)
                nifi_issues_dicts = [i.to_dict() for i in issues]
                nifi_entry = save_flow(
                    name="Pipeline: AGT Data Quality Remediation",
                    flow_json=nifi_flow_obj,
                    issues=nifi_issues_dicts,
                    note=f"Auto-generated by pipeline: {len(issues)} issues",
                )
                yield {"event": "nifi_generated", "data": json.dumps({"flow_id": nifi_entry["id"]})}
                yield {"event": "stage", "data": json.dumps({"stage": "nifi_generation", "status": "completed"})}
            except Exception as e:
                yield {"event": "stage", "data": json.dumps({"stage": "nifi_generation", "status": "skipped", "reason": str(e)[:200]})}

            # --- Stage 6: Spark Job Generation ---
            yield {"event": "stage", "data": json.dumps({"stage": "spark_generation", "status": "started"})}
            try:
                from spark.job_generator import generate_spark_job as gen_spark
                from spark.job_store import save_job

                spark_result = gen_spark(issues)
                spark_entry = save_job(
                    name="Pipeline: AGT Data Quality Remediation",
                    job_definition=spark_result["job_definition"],
                    pyspark_script=spark_result["pyspark_script"],
                    script_name=spark_result["script_name"],
                    issues=[i.to_dict() for i in issues],
                    note=f"Auto-generated by pipeline: {len(issues)} issues",
                )
                yield {"event": "spark_generated", "data": json.dumps({"job_id": spark_entry["id"]})}
                yield {"event": "stage", "data": json.dumps({"stage": "spark_generation", "status": "completed"})}
            except Exception as e:
                yield {"event": "stage", "data": json.dumps({"stage": "spark_generation", "status": "skipped", "reason": str(e)[:200]})}

            # --- Stage 7: Classification ---
            yield {"event": "stage", "data": json.dumps({"stage": "classification", "status": "started"})}
            try:
                from classification.orchestrator import classify_metadata as _classify_meta
                from classification.classification_store import save_classification as _save_clf

                # Try to get LLM client
                clf_llm_client, clf_llm_model = None, ""
                try:
                    from routers.chat import resolve_llm_client
                    clf_llm_client, clf_llm_model = resolve_llm_client()
                except Exception:
                    pass

                clf_result = _classify_meta(
                    fields=fields,
                    name="Pipeline: AGT Classification",
                    use_llm=bool(clf_llm_client),
                    llm_client=clf_llm_client,
                    llm_model=clf_llm_model,
                )
                clf_entry = _save_clf(
                    name="Pipeline: AGT Classification",
                    classification_data=clf_result.to_dict(),
                    note=f"Auto-generated by pipeline: {clf_result.total_columns} columns",
                )
                yield {"event": "classification_generated", "data": json.dumps({"classification_id": clf_entry["id"]})}
                yield {"event": "stage", "data": json.dumps({"stage": "classification", "status": "completed"})}
            except Exception as e:
                yield {"event": "stage", "data": json.dumps({"stage": "classification", "status": "skipped", "reason": str(e)[:200]})}

            # --- Stage 8: Metadata YAML Generation ---
            yield {"event": "stage", "data": json.dumps({"stage": "metadata_generation", "status": "started"})}
            try:
                from metadata.yaml_generator import generate_metadata_yaml, generate_metadata_yaml_dict
                from metadata.meta_store import save_metadata_file

                row_count_val = _state["row_count"]
                yaml_dict = generate_metadata_yaml_dict(
                    issues, fields, profiles=profiles, row_count=row_count_val,
                    spec_name="Pipeline: AGT Data Ingestion Specification",
                )
                import yaml
                yaml_content = yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)
                meta_entry = save_metadata_file(
                    name="Pipeline: AGT Data Ingestion Specification",
                    yaml_content=yaml_content,
                    yaml_dict=yaml_dict,
                    issues=[i.to_dict() for i in issues],
                    note=f"Auto-generated by pipeline: {len(issues)} issues",
                )
                yield {"event": "metadata_generated", "data": json.dumps({"meta_id": meta_entry["id"]})}
                yield {"event": "stage", "data": json.dumps({"stage": "metadata_generation", "status": "completed"})}
            except Exception as e:
                yield {"event": "stage", "data": json.dumps({"stage": "metadata_generation", "status": "skipped", "reason": str(e)[:200]})}

            yield {"event": "done", "data": json.dumps({})}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)[:500]})}

    return EventSourceResponse(event_generator())


@router.post("/detect-issues/analyze")
async def detect_issues_analyze(req: DetectRequest):
    """Detect issues then stream LLM analysis via SSE."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")

    target = req.field_names if req.field_names else None
    with _db_lock:
        issues = detect_quality_issues(_state["conn"], _state["fields"], target)
    issues_dicts = [i.to_dict() for i in issues]

    # Lazy imports to avoid circular dependency
    from routers.chat import resolve_llm_client
    from agent.analysis_prompts import quality_issues_analysis_prompt
    from agent.analysis_stream import stream_analysis

    try:
        client, model = resolve_llm_client()
    except ValueError as e:
        raise HTTPException(400, str(e))
    system_prompt, user_content = quality_issues_analysis_prompt(issues_dicts)

    async def event_generator():
        # Emit structured data immediately
        yield {"event": "issues_data", "data": json.dumps(issues_dicts)}

        # Stream LLM analysis
        async for evt in stream_analysis(client, model, system_prompt, user_content):
            yield {"event": evt["event"], "data": json.dumps(evt["data"])}

    return EventSourceResponse(event_generator())


@router.post("/profile/analyze")
async def profile_analyze(req: ProfileRequest):
    """Profile a column then stream LLM interpretation via SSE."""
    if not _state["loaded"]:
        raise HTTPException(400, "No data loaded")

    fname = req.field_name.upper()
    field = next((f for f in _state["fields"] if f.field_name == fname), None)
    if not field:
        raise HTTPException(404, f"Field '{fname}' not found")

    with _db_lock:
        prof = profile_column(_state["conn"], field)
    profile_dict = prof.to_dict()

    from routers.chat import resolve_llm_client
    from agent.analysis_prompts import column_profile_analysis_prompt
    from agent.analysis_stream import stream_analysis

    try:
        client, model = resolve_llm_client()
    except ValueError as e:
        raise HTTPException(400, str(e))
    system_prompt, user_content = column_profile_analysis_prompt(profile_dict)

    async def event_generator():
        yield {"event": "profile_data", "data": json.dumps(profile_dict)}

        async for evt in stream_analysis(client, model, system_prompt, user_content):
            yield {"event": evt["event"], "data": json.dumps(evt["data"])}

    return EventSourceResponse(event_generator())

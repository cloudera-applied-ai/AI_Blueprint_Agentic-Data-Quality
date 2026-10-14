"""Spark job generation endpoints."""

import json
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from data.profiler import detect_quality_issues, QualityIssue
from spark.job_generator import generate_spark_job
from spark.job_store import (
    list_jobs,
    get_job,
    get_job_version,
    save_job,
    update_job,
    delete_job,
    clone_job,
)
from routers.data import get_state, get_db_lock

router = APIRouter(prefix="/api/spark", tags=["spark"])


class GenerateJobRequest(BaseModel):
    issue_indices: list[int] = []
    rules: list[dict] = []
    job_name: str = "Data Quality Remediation"
    output_format: Literal["parquet", "delta", "csv", "json"] = "parquet"


import re as _re

_SAFE_FIELD_RE = _re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
_SAFE_VALUE_RE = _re.compile(r'^[A-Za-z0-9 _.\-]{0,50}$')


def _rules_to_issues(rules: list[dict]) -> list[QualityIssue]:
    """Convert frontend rule dicts to QualityIssue objects with validation."""
    issues = []
    for r in rules:
        field_name = str(r.get("field_name", ""))
        if not _SAFE_FIELD_RE.match(field_name):
            raise HTTPException(400, f"Invalid field_name in rule: {field_name!r}")
        # Validate params that feed into code generation
        params = r.get("params", {})
        if "max_length" in params:
            try:
                ml = int(params["max_length"])
                if ml < 1 or ml > 10000:
                    raise ValueError
                params["max_length"] = ml
            except (ValueError, TypeError):
                raise HTTPException(400, f"Invalid max_length in params for {field_name}")
        if "valid_values" in params:
            for v in params["valid_values"]:
                if not _SAFE_VALUE_RE.match(str(v)):
                    raise HTTPException(400, f"Invalid valid_value in params for {field_name}")
        issues.append(QualityIssue(
            field_name=field_name,
            issue_type=str(r.get("issue_type", "custom")),
            description=str(r.get("description", "")),
            affected_count=int(r.get("affected_count", 0)),
            affected_pct=float(r.get("affected_pct", 0.0)),
            sample_bad_values=r.get("sample_bad_values", []),
            suggested_fix=str(r.get("suggested_fix", "")),
            params=params,
        ))
    return issues


def _resolve_issues(req: GenerateJobRequest) -> list[QualityIssue]:
    """Resolve selected issues from the request (shared by generate endpoints)."""
    if req.rules:
        return _rules_to_issues(req.rules)

    state = get_state()
    if not state["loaded"]:
        raise HTTPException(400, "No data loaded")

    with get_db_lock():
        all_issues = detect_quality_issues(state["conn"], state["fields"])

    if req.issue_indices:
        return [all_issues[i] for i in req.issue_indices if 0 <= i < len(all_issues)]

    return all_issues


class SaveJobRequest(BaseModel):
    name: str
    job: dict
    pyspark_script: str = ""
    script_name: str = "quality_remediation.py"
    issues: list[dict] = []
    design_rationale: Optional[str] = None
    note: str = "Initial generation"


class UpdateJobRequest(BaseModel):
    name: Optional[str] = None
    job: Optional[dict] = None
    pyspark_script: Optional[str] = None
    note: str = "Updated"


class CloneJobRequest(BaseModel):
    new_name: Optional[str] = None


@router.post("/detect-issues")
def detect_issues():
    """Detect all quality issues for Spark job generation."""
    state = get_state()
    if not state["loaded"]:
        raise HTTPException(400, "No data loaded")

    try:
        with get_db_lock():
            issues = detect_quality_issues(state["conn"], state["fields"])
    except Exception as e:
        raise HTTPException(500, f"Issue detection failed — the data connection may be stale. Try reloading. ({e})")
    return [i.to_dict() for i in issues]


@router.post("/generate")
def generate(req: GenerateJobRequest):
    """Generate CDE Spark job + PySpark script for selected issues."""
    selected = _resolve_issues(req)
    if not selected:
        raise HTTPException(400, "No issues selected")

    result = generate_spark_job(selected, req.job_name, req.output_format)
    return {
        "job_name": req.job_name,
        "issues_addressed": len(selected),
        "issues": [i.to_dict() for i in selected],
        "job": result["job_definition"],
        "pyspark_script": result["pyspark_script"],
        "script_name": result["script_name"],
    }


@router.post("/generate/design")
async def generate_design(req: GenerateJobRequest):
    """Generate Spark job + stream LLM design rationale via SSE."""
    selected = _resolve_issues(req)
    if not selected:
        raise HTTPException(400, "No issues selected")

    result = generate_spark_job(selected, req.job_name, req.output_format)
    job_result = {
        "job_name": req.job_name,
        "issues_addressed": len(selected),
        "issues": [i.to_dict() for i in selected],
        "job": result["job_definition"],
        "pyspark_script": result["pyspark_script"],
        "script_name": result["script_name"],
    }
    issues_dicts = [i.to_dict() for i in selected]

    from routers.chat import resolve_llm_client
    from agent.analysis_prompts import spark_job_design_prompt
    from agent.analysis_stream import stream_analysis

    try:
        client, model = resolve_llm_client()
    except ValueError as e:
        raise HTTPException(400, str(e))
    system_prompt, user_content = spark_job_design_prompt(issues_dicts, job_result)

    async def event_generator():
        yield {"event": "spark_job_data", "data": json.dumps(job_result)}

        async for evt in stream_analysis(client, model, system_prompt, user_content):
            yield {"event": evt["event"], "data": json.dumps(evt["data"])}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Saved job CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("/jobs")
def list_saved_jobs():
    """List all saved jobs."""
    return list_jobs()


@router.post("/jobs")
def save_new_job(req: SaveJobRequest):
    """Save a new job."""
    return save_job(
        name=req.name,
        job_definition=req.job,
        pyspark_script=req.pyspark_script,
        script_name=req.script_name,
        issues=req.issues,
        design_rationale=req.design_rationale,
        note=req.note,
    )


@router.get("/jobs/{job_id}")
def get_saved_job(job_id: str):
    """Get a saved job with its current version data."""
    try:
        return get_job(job_id)
    except KeyError:
        raise HTTPException(404, "Job not found")


@router.get("/jobs/{job_id}/versions/{version}")
def get_saved_job_version(job_id: str, version: int):
    """Get a specific version of a saved job."""
    try:
        return get_job_version(job_id, version)
    except KeyError:
        raise HTTPException(404, "Job not found")
    except FileNotFoundError:
        raise HTTPException(404, "Version not found")


@router.put("/jobs/{job_id}")
def update_saved_job(job_id: str, req: UpdateJobRequest):
    """Update a saved job (rename and/or create new version)."""
    try:
        return update_job(
            job_id=job_id,
            name=req.name,
            job_definition=req.job,
            pyspark_script=req.pyspark_script,
            note=req.note,
        )
    except KeyError:
        raise HTTPException(404, "Job not found")


@router.delete("/jobs/{job_id}")
def delete_saved_job(job_id: str):
    """Delete a saved job and all its versions."""
    try:
        delete_job(job_id)
        return {"status": "deleted"}
    except KeyError:
        raise HTTPException(404, "Job not found")


@router.post("/jobs/{job_id}/clone")
def clone_saved_job(job_id: str, req: CloneJobRequest):
    """Clone a saved job."""
    try:
        return clone_job(job_id, new_name=req.new_name)
    except KeyError:
        raise HTTPException(404, "Job not found")

"""NiFi flow generation endpoints."""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from data.profiler import detect_quality_issues, QualityIssue
from nifi.flow_generator import generate_flow_json, generate_flow
from nifi.flow_store import (
    list_flows,
    get_flow,
    get_flow_version,
    save_flow,
    update_flow,
    delete_flow,
    clone_flow,
)
from routers.data import get_state, get_db_lock

router = APIRouter(prefix="/api/nifi", tags=["nifi"])


class GenerateFlowRequest(BaseModel):
    issue_indices: list[int] = []
    rules: list[dict] = []  # Explicit rules from the UI (takes precedence)
    flow_name: str = "Data Quality Remediation"


def _rules_to_issues(rules: list[dict]) -> list[QualityIssue]:
    """Convert frontend rule dicts to QualityIssue objects."""
    issues = []
    for r in rules:
        issues.append(QualityIssue(
            field_name=r.get("field_name", ""),
            issue_type=r.get("issue_type", "custom"),
            description=r.get("description", ""),
            affected_count=r.get("affected_count", 0),
            affected_pct=r.get("affected_pct", 0.0),
            sample_bad_values=r.get("sample_bad_values", []),
            suggested_fix=r.get("suggested_fix", ""),
            params=r.get("params", {}),
        ))
    return issues


class SaveFlowRequest(BaseModel):
    name: str
    flow: dict
    issues: list[dict] = []
    design_rationale: Optional[str] = None
    note: str = "Initial generation"


class UpdateFlowRequest(BaseModel):
    name: Optional[str] = None
    flow: Optional[dict] = None
    note: str = "Updated"


class CloneFlowRequest(BaseModel):
    new_name: Optional[str] = None


@router.post("/detect-issues")
def detect_issues():
    """Detect all quality issues for NiFi flow generation."""
    state = get_state()
    if not state["loaded"]:
        raise HTTPException(400, "No data loaded")

    with get_db_lock():
        issues = detect_quality_issues(state["conn"], state["fields"])
    return [i.to_dict() for i in issues]


@router.post("/generate")
def generate(req: GenerateFlowRequest):
    """Generate NiFi flow JSON for selected issues or explicit rules."""
    if req.rules:
        # Use explicit rules from the frontend (edited/custom rules)
        selected = _rules_to_issues(req.rules)
    else:
        # Fall back to auto-detected issues by index
        state = get_state()
        if not state["loaded"]:
            raise HTTPException(400, "No data loaded")

        with get_db_lock():
            all_issues = detect_quality_issues(state["conn"], state["fields"])

        if req.issue_indices:
            selected = [all_issues[i] for i in req.issue_indices if i < len(all_issues)]
        else:
            selected = all_issues

    if not selected:
        raise HTTPException(400, "No issues selected")

    flow = generate_flow(selected, req.flow_name)
    return {
        "flow_name": req.flow_name,
        "issues_addressed": len(selected),
        "issues": [i.to_dict() for i in selected],
        "flow": flow,
    }


@router.post("/generate/design")
async def generate_design(req: GenerateFlowRequest):
    """Generate NiFi flow + stream LLM design rationale via SSE."""
    if req.rules:
        selected = _rules_to_issues(req.rules)
    else:
        state = get_state()
        if not state["loaded"]:
            raise HTTPException(400, "No data loaded")

        with get_db_lock():
            all_issues = detect_quality_issues(state["conn"], state["fields"])

        if req.issue_indices:
            selected = [all_issues[i] for i in req.issue_indices if i < len(all_issues)]
        else:
            selected = all_issues

    if not selected:
        raise HTTPException(400, "No issues selected")

    flow = generate_flow(selected, req.flow_name)
    flow_result = {
        "flow_name": req.flow_name,
        "issues_addressed": len(selected),
        "issues": [i.to_dict() for i in selected],
        "flow": flow,
    }
    issues_dicts = [i.to_dict() for i in selected]

    from routers.chat import resolve_llm_client
    from agent.analysis_prompts import nifi_flow_design_prompt
    from agent.analysis_stream import stream_analysis

    try:
        client, model = resolve_llm_client()
    except ValueError as e:
        raise HTTPException(400, str(e))
    system_prompt, user_content = nifi_flow_design_prompt(issues_dicts, flow_result)

    async def event_generator():
        yield {"event": "flow_data", "data": json.dumps(flow_result)}

        async for evt in stream_analysis(client, model, system_prompt, user_content):
            yield {"event": evt["event"], "data": json.dumps(evt["data"])}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Saved flow CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("/flows")
def list_saved_flows():
    """List all saved flows."""
    return list_flows()


@router.post("/flows")
def save_new_flow(req: SaveFlowRequest):
    """Save a new flow."""
    return save_flow(
        name=req.name,
        flow_json=req.flow,
        issues=req.issues,
        design_rationale=req.design_rationale,
        note=req.note,
    )


@router.get("/flows/{flow_id}")
def get_saved_flow(flow_id: str):
    """Get a saved flow with its current version data."""
    try:
        return get_flow(flow_id)
    except KeyError:
        raise HTTPException(404, "Flow not found")


@router.get("/flows/{flow_id}/versions/{version}")
def get_saved_flow_version(flow_id: str, version: int):
    """Get a specific version of a saved flow."""
    try:
        return get_flow_version(flow_id, version)
    except KeyError:
        raise HTTPException(404, "Flow not found")
    except FileNotFoundError:
        raise HTTPException(404, "Version not found")


@router.put("/flows/{flow_id}")
def update_saved_flow(flow_id: str, req: UpdateFlowRequest):
    """Update a saved flow (rename and/or create new version)."""
    try:
        return update_flow(
            flow_id=flow_id,
            name=req.name,
            flow_json=req.flow,
            note=req.note,
        )
    except KeyError:
        raise HTTPException(404, "Flow not found")


@router.delete("/flows/{flow_id}")
def delete_saved_flow(flow_id: str):
    """Delete a saved flow and all its versions."""
    try:
        delete_flow(flow_id)
        return {"status": "deleted"}
    except KeyError:
        raise HTTPException(404, "Flow not found")


@router.post("/flows/{flow_id}/clone")
def clone_saved_flow(flow_id: str, req: CloneFlowRequest):
    """Clone a saved flow."""
    try:
        return clone_flow(flow_id, new_name=req.new_name)
    except KeyError:
        raise HTTPException(404, "Flow not found")

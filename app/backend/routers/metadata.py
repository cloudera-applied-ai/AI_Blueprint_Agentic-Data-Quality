"""Metadata YAML file generation and management endpoints."""

import re as _re
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data.profiler import detect_quality_issues, QualityIssue
from metadata.yaml_generator import generate_metadata_yaml, generate_metadata_yaml_dict
from metadata.meta_store import (
    list_metadata_files,
    get_metadata_file,
    get_metadata_file_version,
    save_metadata_file,
    update_metadata_file,
    delete_metadata_file,
    clone_metadata_file,
)
from routers.data import get_state, get_db_lock

router = APIRouter(prefix="/api/metadata", tags=["metadata"])


class GenerateMetadataRequest(BaseModel):
    issue_indices: list[int] = []
    rules: list[dict] = []
    spec_name: str = "AGT Data Ingestion Specification"


_SAFE_FIELD_RE = _re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
_SAFE_VALUE_RE = _re.compile(r'^[A-Za-z0-9 _.\-]{0,50}$')


def _rules_to_issues(rules: list[dict]) -> list[QualityIssue]:
    """Convert frontend rule dicts to QualityIssue objects with validation."""
    issues = []
    for r in rules:
        field_name = str(r.get("field_name", ""))
        if not _SAFE_FIELD_RE.match(field_name):
            raise HTTPException(400, f"Invalid field_name in rule: {field_name!r}")
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


def _resolve_issues(req: GenerateMetadataRequest) -> list[QualityIssue]:
    """Resolve selected issues from the request."""
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


class SaveMetadataRequest(BaseModel):
    name: str
    yaml_content: str = ""
    yaml_dict: dict = {}
    issues: list[dict] = []
    design_rationale: Optional[str] = None
    note: str = "Initial generation"


class UpdateMetadataRequest(BaseModel):
    name: Optional[str] = None
    yaml_content: Optional[str] = None
    yaml_dict: Optional[dict] = None
    note: str = "Updated"


class CloneMetadataRequest(BaseModel):
    new_name: Optional[str] = None


@router.post("/detect-issues")
def detect_issues():
    """Detect all quality issues for metadata generation."""
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
def generate(req: GenerateMetadataRequest):
    """Generate metadata YAML from selected issues/rules."""
    state = get_state()
    if not state["loaded"]:
        raise HTTPException(400, "No data loaded")

    selected = _resolve_issues(req)
    if not selected:
        raise HTTPException(400, "No issues selected")

    fields = state["fields"]
    row_count = state["row_count"]

    yaml_dict = generate_metadata_yaml_dict(selected, fields, row_count=row_count, spec_name=req.spec_name)
    yaml_content = yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Validate generated metadata against the original field definitions
    validation = _validate_against_source(yaml_dict, fields)

    return {
        "spec_name": req.spec_name,
        "issues_addressed": len(selected),
        "issues": [i.to_dict() for i in selected],
        "yaml_content": yaml_content,
        "yaml_dict": yaml_dict,
        "validation": validation,
    }


def _validate_against_source(yaml_dict: dict, source_fields: list) -> dict:
    """Compare generated metadata columns against the original field definitions.

    Returns a validation report with per-column match status and overall score.
    """
    gen_columns: list[dict] = yaml_dict.get("columns") or []
    gen_lookup = {str(c.get("name", "")).upper(): c for c in gen_columns}

    source_lookup = {f.field_name.upper(): f for f in source_fields}
    source_names = {f.field_name.upper() for f in source_fields}
    gen_names = set(gen_lookup.keys())

    matched = sorted(source_names & gen_names)
    missing = sorted(source_names - gen_names)
    extra = sorted(gen_names - source_names)

    column_checks: list[dict] = []
    match_count = 0

    for name in matched:
        src = source_lookup[name]
        gen = gen_lookup[name]

        pos_match = gen.get("position") == src.position
        len_match = gen.get("max_length") == src.max_length

        src_biz = src.business_name or ""
        gen_biz = str(gen.get("business_name") or "")
        biz_match = gen_biz.lower() == src_biz.lower() if (src_biz or gen_biz) else True

        all_ok = pos_match and len_match
        if all_ok:
            match_count += 1

        entry: dict = {
            "column": name,
            "match": all_ok,
            "position": {"match": pos_match, "source": src.position, "generated": gen.get("position")},
            "max_length": {"match": len_match, "source": src.max_length, "generated": gen.get("max_length")},
            "business_name": {"match": biz_match, "source": src_biz, "generated": gen_biz},
        }
        column_checks.append(entry)

    total = len(source_fields) or 1
    score = round((match_count / total) * 100, 1)

    return {
        "score": score,
        "total_source_fields": len(source_fields),
        "total_generated_fields": len(gen_columns),
        "matched": len(matched),
        "fully_correct": match_count,
        "missing_fields": missing,
        "extra_fields": extra,
        "column_checks": column_checks,
    }


# ---------------------------------------------------------------------------
# Saved metadata CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/files")
def list_saved_metadata():
    """List all saved metadata files."""
    return list_metadata_files()


@router.post("/files")
def save_new_metadata(req: SaveMetadataRequest):
    """Save a new metadata file."""
    return save_metadata_file(
        name=req.name,
        yaml_content=req.yaml_content,
        yaml_dict=req.yaml_dict,
        issues=req.issues,
        design_rationale=req.design_rationale,
        note=req.note,
    )


@router.get("/files/{meta_id}")
def get_saved_metadata(meta_id: str):
    """Get a saved metadata file with its current version data."""
    try:
        return get_metadata_file(meta_id)
    except KeyError:
        raise HTTPException(404, "Metadata file not found")


@router.get("/files/{meta_id}/versions/{version}")
def get_saved_metadata_version(meta_id: str, version: int):
    """Get a specific version of a saved metadata file."""
    try:
        return get_metadata_file_version(meta_id, version)
    except KeyError:
        raise HTTPException(404, "Metadata file not found")
    except FileNotFoundError:
        raise HTTPException(404, "Version not found")


@router.put("/files/{meta_id}")
def update_saved_metadata(meta_id: str, req: UpdateMetadataRequest):
    """Update a saved metadata file (rename and/or create new version)."""
    yaml_content = req.yaml_content
    yaml_dict = req.yaml_dict

    # When yaml_dict is provided without yaml_content, regenerate YAML from the dict
    if yaml_dict and not yaml_content:
        yaml_content = yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # When yaml_content is provided without yaml_dict, try to parse the YAML
    if yaml_content and not yaml_dict:
        try:
            yaml_dict = yaml.safe_load(yaml_content)
        except yaml.YAMLError:
            pass  # keep yaml_dict as None; store raw content only

    try:
        return update_metadata_file(
            meta_id=meta_id,
            name=req.name,
            yaml_content=yaml_content,
            yaml_dict=yaml_dict,
            note=req.note,
        )
    except KeyError:
        raise HTTPException(404, "Metadata file not found")


@router.delete("/files/{meta_id}")
def delete_saved_metadata(meta_id: str):
    """Delete a saved metadata file and all its versions."""
    try:
        delete_metadata_file(meta_id)
        return {"status": "deleted"}
    except KeyError:
        raise HTTPException(404, "Metadata file not found")


@router.post("/files/{meta_id}/clone")
def clone_saved_metadata(meta_id: str, req: CloneMetadataRequest):
    """Clone a saved metadata file."""
    try:
        return clone_metadata_file(meta_id, new_name=req.new_name)
    except KeyError:
        raise HTTPException(404, "Metadata file not found")

"""Classification endpoints for metadata column classification."""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from classification.orchestrator import classify_metadata, classify_metadata_stream
from classification.classification_store import (
    list_classifications,
    get_classification,
    get_classification_version,
    save_classification,
    update_classification,
    delete_classification,
    clone_classification,
)
from routers.data import get_state

router = APIRouter(prefix="/api/classification", tags=["classification"])


class ClassifyRequest(BaseModel):
    name: str = "AGT Classification"
    confidence_threshold: float = 0.7
    use_llm: bool = True


class SaveClassificationRequest(BaseModel):
    name: str
    classification_data: dict = {}
    note: str = "Initial classification"


class UpdateClassificationRequest(BaseModel):
    name: Optional[str] = None
    classification_data: Optional[dict] = None
    note: str = "Updated"


class CloneClassificationRequest(BaseModel):
    new_name: Optional[str] = None


def _resolve_llm_client():
    """Try to get LLM client from chat router config."""
    try:
        from routers.chat import resolve_llm_client
        client, model = resolve_llm_client()
        return client, model
    except (ValueError, ImportError, Exception):
        return None, ""


@router.post("/classify")
def run_classification(req: ClassifyRequest):
    """Run classification (synchronous)."""
    state = get_state()
    if not state["loaded"]:
        raise HTTPException(400, "No data loaded")

    fields = state["fields"]
    llm_client, llm_model = (None, "")
    if req.use_llm:
        llm_client, llm_model = _resolve_llm_client()

    result = classify_metadata(
        fields=fields,
        name=req.name,
        confidence_threshold=req.confidence_threshold,
        use_llm=req.use_llm,
        llm_client=llm_client,
        llm_model=llm_model,
    )
    return result.to_dict()


@router.post("/classify/stream")
async def run_classification_stream(req: ClassifyRequest):
    """Run classification with SSE progress events."""
    state = get_state()
    if not state["loaded"]:
        raise HTTPException(400, "No data loaded")

    fields = state["fields"]
    llm_client, llm_model = (None, "")
    if req.use_llm:
        llm_client, llm_model = _resolve_llm_client()

    async def event_generator():
        try:
            for event in classify_metadata_stream(
                fields=fields,
                name=req.name,
                confidence_threshold=req.confidence_threshold,
                use_llm=req.use_llm,
                llm_client=llm_client,
                llm_model=llm_model,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)[:500]}),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Saved classification CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/files")
def list_saved_classifications():
    """List all saved classifications."""
    return list_classifications()


@router.post("/files")
def save_new_classification(req: SaveClassificationRequest):
    """Save a new classification."""
    return save_classification(
        name=req.name,
        classification_data=req.classification_data,
        note=req.note,
    )


@router.get("/files/{classification_id}")
def get_saved_classification(classification_id: str):
    """Get a saved classification with its current version data."""
    try:
        return get_classification(classification_id)
    except KeyError:
        raise HTTPException(404, "Classification not found")


@router.get("/files/{classification_id}/versions/{version}")
def get_saved_classification_version(classification_id: str, version: int):
    """Get a specific version of a saved classification."""
    try:
        return get_classification_version(classification_id, version)
    except KeyError:
        raise HTTPException(404, "Classification not found")
    except FileNotFoundError:
        raise HTTPException(404, "Version not found")


@router.put("/files/{classification_id}")
def update_saved_classification(classification_id: str, req: UpdateClassificationRequest):
    """Update a saved classification (rename and/or create new version)."""
    try:
        return update_classification(
            classification_id=classification_id,
            name=req.name,
            classification_data=req.classification_data,
            note=req.note,
        )
    except KeyError:
        raise HTTPException(404, "Classification not found")


@router.delete("/files/{classification_id}")
def delete_saved_classification(classification_id: str):
    """Delete a saved classification and all its versions."""
    try:
        delete_classification(classification_id)
        return {"status": "deleted"}
    except KeyError:
        raise HTTPException(404, "Classification not found")


@router.post("/files/{classification_id}/clone")
def clone_saved_classification(classification_id: str, req: CloneClassificationRequest):
    """Clone a saved classification."""
    try:
        return clone_classification(classification_id, new_name=req.new_name)
    except KeyError:
        raise HTTPException(404, "Classification not found")

"""Chat endpoint with SSE streaming."""

import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.llm_client import create_client, test_connection
from agent.agent_loop import run_agent_stream
from routers.data import get_state
import settings_store

router = APIRouter(prefix="/api/chat", tags=["chat"])

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Pre-database installs saved settings as JSON (migrated into the DB on startup)
_LEGACY_JSON_FILES = (
    os.path.join(_BACKEND_DIR, "settings", "llm_settings.json"),
    os.path.join(_BACKEND_DIR, "llm_settings.json"),
)

# LLM config state — persisted (api_key included) to the settings database
_llm_config = {
    "base_url": None,
    "model": None,
    "endpoint_type": None,
    "api_key": None,
}


def _read_legacy_json() -> dict:
    for path in _LEGACY_JSON_FILES:
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _load_settings():
    """Load persisted LLM settings, migrating any legacy JSON file into the DB."""
    saved = settings_store.get_all()
    if not saved:
        saved = {k: v for k, v in _read_legacy_json().items() if k in _llm_config and v}
        if saved:
            settings_store.set_many(saved)
    for key in _llm_config:
        if saved.get(key):
            _llm_config[key] = saved[key]


def _save_settings():
    """Persist current LLM settings to the database."""
    settings_store.set_many({k: v or "" for k, v in _llm_config.items()})


_load_settings()


def get_llm_config():
    return _llm_config


def resolve_llm_client():
    """Return (client, model) using saved settings + fresh API key.

    Shared by all routers (chat, data, nifi, spark) so LLM access is
    configured in one place.  User-provided api_key takes priority over
    auto-detected tokens.
    """
    import config as cfg
    base_url = _llm_config.get("base_url") or cfg.LLM_BASE_URL
    api_key = _llm_config.get("api_key") or cfg.get_api_key()
    model = _llm_config.get("model") or cfg.LLM_MODEL
    if not base_url or not model:
        raise ValueError("LLM not configured. Set configuration first.")
    client = create_client(base_url, api_key)
    return client, model


def _get_key_source() -> str:
    """Determine where the API key is coming from."""
    import config as cfg

    if _llm_config.get("api_key"):
        return "user"
    if os.environ.get("LLM_API_KEY", "") or os.environ.get("CDP_TOKEN", "") or os.environ.get("CLOUDERA_AI_KEY", ""):
        return "env"
    if os.environ.get("CDP_ACCESS_KEY_ID") and os.environ.get("CDP_PRIVATE_KEY"):
        return "cdpcli"
    if cfg._read_cdp_token():
        return "jwt"
    return "default"


class LLMConfigRequest(BaseModel):
    endpoint_type: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5:14b"
    api_key: str = ""


class ChatRequest(BaseModel):
    messages: list[dict]


@router.post("/configure")
def configure_llm(req: LLMConfigRequest):
    """Set LLM configuration and persist to disk."""
    import config as cfg
    _llm_config["endpoint_type"] = req.endpoint_type
    _llm_config["base_url"] = req.base_url or cfg.LLM_BASE_URL
    _llm_config["model"] = req.model or cfg.LLM_MODEL
    if req.api_key:
        # Blank means "keep the saved key" — the UI never echoes it back
        _llm_config["api_key"] = req.api_key
    _save_settings()
    return {"status": "ok", "config": {k: v for k, v in _llm_config.items() if k != "api_key"}}


@router.post("/test-connection")
def test_llm_connection():
    """Test the LLM connection."""
    import config as cfg
    base_url = _llm_config.get("base_url") or cfg.LLM_BASE_URL
    api_key = _llm_config.get("api_key") or cfg.get_api_key()
    model = _llm_config.get("model") or cfg.LLM_MODEL
    return test_connection(base_url, api_key, model)


@router.get("/config")
def get_config():
    """Get current LLM config (no key)."""
    import config as cfg
    key_source = _get_key_source()
    return {
        "endpoint_type": _llm_config.get("endpoint_type") or cfg.LLM_ENDPOINT_TYPE,
        "base_url": _llm_config.get("base_url") or cfg.LLM_BASE_URL,
        "model": _llm_config.get("model") or cfg.LLM_MODEL,
        "has_key": bool(_llm_config.get("api_key") or cfg.get_api_key()),
        "key_source": key_source,
    }


@router.post("/message")
async def chat_message(req: ChatRequest):
    """Send a chat message and get SSE stream response."""
    data_state = get_state()
    if not data_state["loaded"]:
        raise HTTPException(400, "No data loaded. Load data first.")

    try:
        client, model = resolve_llm_client()
    except ValueError as e:
        raise HTTPException(400, str(e))

    async def event_generator():
        async for event in run_agent_stream(
            client=client,
            model=model,
            user_messages=req.messages,
            conn=data_state["conn"],
            fields=data_state["fields"],
            row_count=data_state["row_count"],
        ):
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(event_generator())

import json
import os
import subprocess
import time

# Data paths — use abspath to handle symlinks / Jupyter kernel cwd issues
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(_BACKEND_DIR, "AGT_simulated_data.txt")
DEFAULT_METADATA_PATH = os.path.join(_BACKEND_DIR, "AGT_metadata.json")

# DuckDB
QUERY_TIMEOUT_SECONDS = 30
QUERY_ROW_LIMIT = 1000
TABLE_NAME = "agt"


def _read_cdp_token() -> str:
    """Read CDP JWT access token from /tmp/jwt if available."""
    try:
        with open("/tmp/jwt") as f:
            return json.load(f)["access_token"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return ""


# Cached CDP workload auth token (auto-refreshed via cdpcli)
_cdp_token_cache = {"token": "", "expires_at": 0.0}


def _generate_cdp_token() -> str:
    """Generate a fresh CDP workload auth token using the cdp CLI.

    Requires CDP_ACCESS_KEY_ID and CDP_PRIVATE_KEY env vars to be set.
    Tokens are cached until 60s before expiry.
    """
    now = time.time()
    if _cdp_token_cache["token"] and now < _cdp_token_cache["expires_at"] - 60:
        return _cdp_token_cache["token"]

    if not (os.environ.get("CDP_ACCESS_KEY_ID") and os.environ.get("CDP_PRIVATE_KEY")):
        return ""

    try:
        result = subprocess.run(
            ["cdp", "iam", "generate-workload-auth-token", "--workload-name", "DE"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ""
        data = json.loads(result.stdout)
        token = data["token"]
        # Parse ISO datetime expiry
        expire_str = data.get("expireAt", "")
        if expire_str:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(expire_str.replace("Z", "+00:00"))
            _cdp_token_cache["expires_at"] = dt.timestamp()
        else:
            _cdp_token_cache["expires_at"] = now + 3600
        _cdp_token_cache["token"] = token
        return token
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError):
        return ""


def get_api_key() -> str:
    """Return a fresh API key, re-reading each call (tokens expire).

    Resolution order:
      1. LLM_API_KEY env var          — generic OpenAI-compatible key (e.g. sk-...)
      2. CDP_TOKEN env var            — manual token from Model Endpoint > Code Sample
      3. cdp CLI workload auth token  — auto-generated if CDP_ACCESS_KEY_ID is set
      4. /tmp/jwt access_token        — auto-injected in CML pods
      5. "ollama" fallback            — standalone / local dev
    """
    return (
        os.environ.get("LLM_API_KEY", "")
        or os.environ.get("CDP_TOKEN", "")
        or os.environ.get("CLOUDERA_AI_KEY", "")
        or _generate_cdp_token()
        or _read_cdp_token()
        or "ollama"
    )


# LLM defaults — generic LLM_* vars (any OpenAI-compatible endpoint) take
# precedence over the Cloudera CML fallbacks
LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or os.environ.get("CLOUDERA_AI_URL", "http://localhost:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL") or os.environ.get("CLOUDERA_AI_MODEL", "qwen2.5:14b")
LLM_API_KEY = get_api_key()
LLM_ENDPOINT_TYPE = os.environ.get("LLM_ENDPOINT_TYPE", "cloudera" if _read_cdp_token() else "ollama")

# Agent
MAX_AGENT_ITERATIONS = 10

# Environment detection: Cloudera AI sets CDSW_APP_PORT; fall back to home dir check
IS_CLOUDERA = bool(os.environ.get("CDSW_APP_PORT")) or os.path.expanduser("~") == "/home/cdsw"

# Server — backend always on a fixed port (CDSW_APP_PORT is reserved for the frontend)
API_PORT = 8090 if IS_CLOUDERA else 8000

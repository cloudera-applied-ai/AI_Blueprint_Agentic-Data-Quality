"""Persistence layer for saved classification results.

Storage layout:
  classification_files/
    manifest.json         <- lightweight metadata index
    {uuid}/
      v1.json             <- version 1 classification data
      v2.json             <- version 2, etc.
"""

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_CLASSIFICATION_DIR = Path(__file__).resolve().parent.parent / "classification_files"
_MANIFEST = _CLASSIFICATION_DIR / "manifest.json"
_lock = threading.Lock()

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

# In-memory manifest cache
_cache: list[dict] | None = None
_cache_index: dict[str, dict] = {}


def _validate_classification_id(classification_id: str) -> None:
    """Validate classification_id is a UUID to prevent path traversal."""
    if not _UUID_RE.match(classification_id):
        raise ValueError(f"Invalid classification ID format: {classification_id}")


def _validate_version(version: int) -> None:
    """Validate version is a positive integer."""
    if version < 1:
        raise ValueError(f"Invalid version: {version}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir():
    _CLASSIFICATION_DIR.mkdir(parents=True, exist_ok=True)


def _rebuild_index(entries: list[dict]):
    """Rebuild the in-memory dict index from the entries list."""
    global _cache_index
    _cache_index = {e["id"]: e for e in entries}


def _read_manifest() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache
    _ensure_dir()
    if not _MANIFEST.exists():
        _cache = []
    else:
        with open(_MANIFEST, "r") as f:
            _cache = json.load(f)
    _rebuild_index(_cache)
    return _cache


def _write_manifest(entries: list[dict]):
    global _cache
    _ensure_dir()
    tmp = _MANIFEST.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=2)
    os.replace(str(tmp), str(_MANIFEST))
    _cache = entries
    _rebuild_index(entries)


def _read_version_file(classification_id: str, version: int) -> dict:
    _validate_classification_id(classification_id)
    _validate_version(version)
    path = (_CLASSIFICATION_DIR / classification_id / f"v{version}.json").resolve()
    if not str(path).startswith(str(_CLASSIFICATION_DIR.resolve())):
        raise ValueError("Path traversal detected")
    if not path.exists():
        raise FileNotFoundError(f"Version {version} not found for classification {classification_id}")
    with open(path, "r") as f:
        return json.load(f)


def _write_version_file(classification_id: str, version: int, data: dict):
    _validate_classification_id(classification_id)
    _validate_version(version)
    clf_dir = (_CLASSIFICATION_DIR / classification_id).resolve()
    if not str(clf_dir).startswith(str(_CLASSIFICATION_DIR.resolve())):
        raise ValueError("Path traversal detected")
    clf_dir.mkdir(parents=True, exist_ok=True)
    path = clf_dir / f"v{version}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _find_entry(entries: list[dict], classification_id: str) -> dict | None:
    """O(1) lookup via cached index, with list fallback."""
    if _cache_index:
        return _cache_index.get(classification_id)
    for e in entries:
        if e["id"] == classification_id:
            return e
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_classifications() -> list[dict]:
    """Return all manifest entries."""
    with _lock:
        return _read_manifest()


def get_classification(classification_id: str) -> dict:
    """Return manifest entry + current version data."""
    _validate_classification_id(classification_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, classification_id)
        if not entry:
            raise KeyError(f"Classification {classification_id} not found")
        version_data = _read_version_file(classification_id, entry["current_version"])
        return {"metadata": entry, "classification_data": version_data}


def get_classification_version(classification_id: str, version: int) -> dict:
    """Return manifest entry + specific version data."""
    _validate_classification_id(classification_id)
    _validate_version(version)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, classification_id)
        if not entry:
            raise KeyError(f"Classification {classification_id} not found")
        version_data = _read_version_file(classification_id, version)
        return {"metadata": entry, "classification_data": version_data}


def save_classification(
    name: str,
    classification_data: dict,
    note: str = "Initial classification",
) -> dict:
    """Create a new saved classification. Returns the manifest entry."""
    classification_id = str(uuid.uuid4())
    now = _now_iso()

    version_data = {
        "classification_data": classification_data,
        "saved_at": now,
        "note": note,
    }

    columns = classification_data.get("columns", [])
    summary = classification_data.get("summary", {})
    sensitivity_counts = summary.get("sensitivity_counts", {})

    entry = {
        "id": classification_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "total_columns": len(columns),
        "llm_used": classification_data.get("llm_used", False),
        "sensitivity_summary": sensitivity_counts,
        "versions": [{"version": 1, "created_at": now, "note": note}],
        "current_version": 1,
    }

    with _lock:
        _write_version_file(classification_id, 1, version_data)
        entries = _read_manifest()
        entries.append(entry)
        _write_manifest(entries)

    return entry


def update_classification(
    classification_id: str,
    name: str | None = None,
    classification_data: dict | None = None,
    note: str = "Updated",
) -> dict:
    """Rename and/or create a new version. Returns updated manifest entry."""
    _validate_classification_id(classification_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, classification_id)
        if not entry:
            raise KeyError(f"Classification {classification_id} not found")

        now = _now_iso()

        if name is not None:
            entry["name"] = name

        if classification_data is not None:
            current_data = _read_version_file(classification_id, entry["current_version"])
            new_version = entry["current_version"] + 1
            version_data = {
                "classification_data": classification_data,
                "saved_at": now,
                "note": note,
            }
            _write_version_file(classification_id, new_version, version_data)
            entry["versions"].append(
                {"version": new_version, "created_at": now, "note": note}
            )
            entry["current_version"] = new_version

            # Update summary in manifest
            columns = classification_data.get("columns", [])
            summary = classification_data.get("summary", {})
            entry["total_columns"] = len(columns)
            entry["sensitivity_summary"] = summary.get("sensitivity_counts", {})

        entry["updated_at"] = now
        _write_manifest(entries)

    return entry


def delete_classification(classification_id: str):
    """Remove classification directory and manifest entry."""
    _validate_classification_id(classification_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, classification_id)
        if not entry:
            raise KeyError(f"Classification {classification_id} not found")

        clf_dir = (_CLASSIFICATION_DIR / classification_id).resolve()
        if not str(clf_dir).startswith(str(_CLASSIFICATION_DIR.resolve())):
            raise ValueError("Path traversal detected")
        if clf_dir.exists():
            shutil.rmtree(clf_dir)

        entries = [e for e in entries if e["id"] != classification_id]
        _write_manifest(entries)


def clone_classification(classification_id: str, new_name: str | None = None) -> dict:
    """Copy current version as v1 of a new classification. Returns new entry."""
    _validate_classification_id(classification_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, classification_id)
        if not entry:
            raise KeyError(f"Classification {classification_id} not found")

        current_data = _read_version_file(classification_id, entry["current_version"])

    clone_name = new_name or f"{entry['name']} (Copy)"
    return save_classification(
        name=clone_name,
        classification_data=current_data.get("classification_data", {}),
        note=f"Cloned from {entry['name']}",
    )

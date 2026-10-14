"""Persistence layer for saved metadata YAML files.

Storage layout:
  metadata_files/
    manifest.json         <- lightweight metadata index
    {uuid}/
      v1.json             <- version 1 yaml_content + yaml_dict + issues
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

_META_DIR = Path(__file__).resolve().parent.parent / "metadata_files"
_MANIFEST = _META_DIR / "manifest.json"
_lock = threading.Lock()

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

# In-memory manifest cache (same pattern as job_store)
_cache: list[dict] | None = None
_cache_index: dict[str, dict] = {}  # meta_id -> entry


def _validate_meta_id(meta_id: str) -> None:
    """Validate meta_id is a UUID to prevent path traversal."""
    if not _UUID_RE.match(meta_id):
        raise ValueError(f"Invalid metadata file ID format: {meta_id}")


def _validate_version(version: int) -> None:
    """Validate version is a positive integer."""
    if version < 1:
        raise ValueError(f"Invalid version: {version}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir():
    _META_DIR.mkdir(parents=True, exist_ok=True)


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


def _read_version_file(meta_id: str, version: int) -> dict:
    _validate_meta_id(meta_id)
    _validate_version(version)
    path = (_META_DIR / meta_id / f"v{version}.json").resolve()
    if not str(path).startswith(str(_META_DIR.resolve())):
        raise ValueError("Path traversal detected")
    if not path.exists():
        raise FileNotFoundError(f"Version {version} not found for metadata file {meta_id}")
    with open(path, "r") as f:
        return json.load(f)


def _write_version_file(meta_id: str, version: int, data: dict):
    _validate_meta_id(meta_id)
    _validate_version(version)
    meta_dir = (_META_DIR / meta_id).resolve()
    if not str(meta_dir).startswith(str(_META_DIR.resolve())):
        raise ValueError("Path traversal detected")
    meta_dir.mkdir(parents=True, exist_ok=True)
    path = meta_dir / f"v{version}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _find_entry(entries: list[dict], meta_id: str) -> dict | None:
    """O(1) lookup via cached index, with list fallback."""
    if _cache_index:
        return _cache_index.get(meta_id)
    for e in entries:
        if e["id"] == meta_id:
            return e
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_metadata_files() -> list[dict]:
    """Return all manifest entries."""
    with _lock:
        return _read_manifest()


def get_metadata_file(meta_id: str) -> dict:
    """Return manifest entry + current version data."""
    _validate_meta_id(meta_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, meta_id)
        if not entry:
            raise KeyError(f"Metadata file {meta_id} not found")
        version_data = _read_version_file(meta_id, entry["current_version"])
        return {"metadata": entry, "file_data": version_data}


def get_metadata_file_version(meta_id: str, version: int) -> dict:
    """Return manifest entry + specific version data."""
    _validate_meta_id(meta_id)
    _validate_version(version)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, meta_id)
        if not entry:
            raise KeyError(f"Metadata file {meta_id} not found")
        version_data = _read_version_file(meta_id, version)
        return {"metadata": entry, "file_data": version_data}


def save_metadata_file(
    name: str,
    yaml_content: str,
    yaml_dict: dict,
    issues: list[dict],
    design_rationale: str | None = None,
    note: str = "Initial generation",
) -> dict:
    """Create a new saved metadata file. Returns the manifest entry."""
    meta_id = str(uuid.uuid4())
    now = _now_iso()

    version_data = {
        "yaml_content": yaml_content,
        "yaml_dict": yaml_dict,
        "issues": issues,
        "design_rationale": design_rationale,
        "saved_at": now,
        "note": note,
    }

    issues_summary = [
        f"{iss.get('issue_type', 'unknown')}: {iss.get('field_name', '?')}"
        for iss in issues[:10]
    ]

    entry = {
        "id": meta_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "issues_addressed": len(issues),
        "issues_summary": issues_summary,
        "versions": [{"version": 1, "created_at": now, "note": note}],
        "current_version": 1,
    }

    with _lock:
        _write_version_file(meta_id, 1, version_data)
        entries = _read_manifest()
        entries.append(entry)
        _write_manifest(entries)

    return entry


def update_metadata_file(
    meta_id: str,
    name: str | None = None,
    yaml_content: str | None = None,
    yaml_dict: dict | None = None,
    note: str = "Updated",
) -> dict:
    """Rename and/or create a new version. Returns updated manifest entry."""
    _validate_meta_id(meta_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, meta_id)
        if not entry:
            raise KeyError(f"Metadata file {meta_id} not found")

        now = _now_iso()

        if name is not None:
            entry["name"] = name

        if yaml_content is not None or yaml_dict is not None:
            current_data = _read_version_file(meta_id, entry["current_version"])
            new_version = entry["current_version"] + 1
            version_data = {
                "yaml_content": yaml_content if yaml_content is not None else current_data.get("yaml_content", ""),
                "yaml_dict": yaml_dict if yaml_dict is not None else current_data.get("yaml_dict", {}),
                "issues": current_data.get("issues", []),
                "design_rationale": current_data.get("design_rationale"),
                "saved_at": now,
                "note": note,
            }
            _write_version_file(meta_id, new_version, version_data)
            entry["versions"].append(
                {"version": new_version, "created_at": now, "note": note}
            )
            entry["current_version"] = new_version

        entry["updated_at"] = now
        _write_manifest(entries)

    return entry


def delete_metadata_file(meta_id: str):
    """Remove metadata file directory and manifest entry."""
    _validate_meta_id(meta_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, meta_id)
        if not entry:
            raise KeyError(f"Metadata file {meta_id} not found")

        meta_dir = (_META_DIR / meta_id).resolve()
        if not str(meta_dir).startswith(str(_META_DIR.resolve())):
            raise ValueError("Path traversal detected")
        if meta_dir.exists():
            shutil.rmtree(meta_dir)

        entries = [e for e in entries if e["id"] != meta_id]
        _write_manifest(entries)


def clone_metadata_file(meta_id: str, new_name: str | None = None) -> dict:
    """Copy current version of a metadata file as v1 of a new file. Returns new entry."""
    _validate_meta_id(meta_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, meta_id)
        if not entry:
            raise KeyError(f"Metadata file {meta_id} not found")

        current_data = _read_version_file(meta_id, entry["current_version"])

    clone_name = new_name or f"{entry['name']} (Copy)"
    return save_metadata_file(
        name=clone_name,
        yaml_content=current_data.get("yaml_content", ""),
        yaml_dict=current_data.get("yaml_dict", {}),
        issues=current_data.get("issues", []),
        design_rationale=current_data.get("design_rationale"),
        note=f"Cloned from {entry['name']}",
    )

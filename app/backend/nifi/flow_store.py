"""Persistence layer for saved NiFi flows.

Storage layout:
  flows/
    manifest.json         ← lightweight metadata index
    {uuid}/
      v1.json             ← version 1 flow + issues + rationale
      v2.json             ← version 2, etc.
"""

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_FLOWS_DIR = Path(__file__).resolve().parent.parent / "flows"
_MANIFEST = _FLOWS_DIR / "manifest.json"
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir():
    _FLOWS_DIR.mkdir(parents=True, exist_ok=True)


def _read_manifest() -> list[dict]:
    _ensure_dir()
    if not _MANIFEST.exists():
        return []
    with open(_MANIFEST, "r") as f:
        return json.load(f)


def _write_manifest(entries: list[dict]):
    _ensure_dir()
    tmp = _MANIFEST.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=2)
    os.replace(str(tmp), str(_MANIFEST))


def _read_version_file(flow_id: str, version: int) -> dict:
    path = _FLOWS_DIR / flow_id / f"v{version}.json"
    if not path.exists():
        raise FileNotFoundError(f"Version {version} not found for flow {flow_id}")
    with open(path, "r") as f:
        return json.load(f)


def _write_version_file(flow_id: str, version: int, data: dict):
    flow_dir = _FLOWS_DIR / flow_id
    flow_dir.mkdir(parents=True, exist_ok=True)
    path = flow_dir / f"v{version}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _find_entry(entries: list[dict], flow_id: str) -> dict | None:
    for e in entries:
        if e["id"] == flow_id:
            return e
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_flows() -> list[dict]:
    """Return all manifest entries."""
    with _lock:
        return _read_manifest()


def get_flow(flow_id: str) -> dict:
    """Return manifest entry + current version data."""
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, flow_id)
        if not entry:
            raise KeyError(f"Flow {flow_id} not found")
        flow_data = _read_version_file(flow_id, entry["current_version"])
        return {"metadata": entry, "flow_data": flow_data}


def get_flow_version(flow_id: str, version: int) -> dict:
    """Return manifest entry + specific version data."""
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, flow_id)
        if not entry:
            raise KeyError(f"Flow {flow_id} not found")
        flow_data = _read_version_file(flow_id, version)
        return {"metadata": entry, "flow_data": flow_data}


def save_flow(
    name: str,
    flow_json: dict,
    issues: list[dict],
    design_rationale: str | None = None,
    note: str = "Initial generation",
) -> dict:
    """Create a new saved flow. Returns the manifest entry."""
    flow_id = str(uuid.uuid4())
    now = _now_iso()

    version_data = {
        "flow": flow_json,
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
        "id": flow_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "issues_addressed": len(issues),
        "issues_summary": issues_summary,
        "versions": [{"version": 1, "created_at": now, "note": note}],
        "current_version": 1,
    }

    with _lock:
        _write_version_file(flow_id, 1, version_data)
        entries = _read_manifest()
        entries.append(entry)
        _write_manifest(entries)

    return entry


def update_flow(
    flow_id: str,
    name: str | None = None,
    flow_json: dict | None = None,
    note: str = "Updated",
) -> dict:
    """Rename and/or create a new version. Returns updated manifest entry."""
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, flow_id)
        if not entry:
            raise KeyError(f"Flow {flow_id} not found")

        now = _now_iso()

        if name is not None:
            entry["name"] = name

        if flow_json is not None:
            # Read current version to carry forward issues/rationale
            current_data = _read_version_file(flow_id, entry["current_version"])
            new_version = entry["current_version"] + 1
            version_data = {
                "flow": flow_json,
                "issues": current_data.get("issues", []),
                "design_rationale": current_data.get("design_rationale"),
                "saved_at": now,
                "note": note,
            }
            _write_version_file(flow_id, new_version, version_data)
            entry["versions"].append(
                {"version": new_version, "created_at": now, "note": note}
            )
            entry["current_version"] = new_version

        entry["updated_at"] = now
        _write_manifest(entries)

    return entry


def delete_flow(flow_id: str):
    """Remove flow directory and manifest entry."""
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, flow_id)
        if not entry:
            raise KeyError(f"Flow {flow_id} not found")

        flow_dir = _FLOWS_DIR / flow_id
        if flow_dir.exists():
            shutil.rmtree(flow_dir)

        entries = [e for e in entries if e["id"] != flow_id]
        _write_manifest(entries)


def clone_flow(flow_id: str, new_name: str | None = None) -> dict:
    """Copy current version of a flow as v1 of a new flow. Returns new entry."""
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, flow_id)
        if not entry:
            raise KeyError(f"Flow {flow_id} not found")

        current_data = _read_version_file(flow_id, entry["current_version"])

    # Use save_flow (which acquires its own lock)
    clone_name = new_name or f"{entry['name']} (Copy)"
    return save_flow(
        name=clone_name,
        flow_json=current_data["flow"],
        issues=current_data.get("issues", []),
        design_rationale=current_data.get("design_rationale"),
        note=f"Cloned from {entry['name']}",
    )

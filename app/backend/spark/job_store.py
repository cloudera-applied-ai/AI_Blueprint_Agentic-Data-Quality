"""Persistence layer for saved Spark jobs.

Storage layout:
  spark_jobs/
    manifest.json         <- lightweight metadata index
    {uuid}/
      v1.json             <- version 1 job + script + issues + rationale
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

_JOBS_DIR = Path(__file__).resolve().parent.parent / "spark_jobs"
_MANIFEST = _JOBS_DIR / "manifest.json"
_lock = threading.Lock()

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

# In-memory manifest cache (P3/P4: avoid disk reads + O(1) lookups)
_cache: list[dict] | None = None
_cache_index: dict[str, dict] = {}  # job_id -> entry


def _validate_job_id(job_id: str) -> None:
    """Validate job_id is a UUID to prevent path traversal."""
    if not _UUID_RE.match(job_id):
        raise ValueError(f"Invalid job ID format: {job_id}")


def _validate_version(version: int) -> None:
    """Validate version is a positive integer."""
    if version < 1:
        raise ValueError(f"Invalid version: {version}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir():
    _JOBS_DIR.mkdir(parents=True, exist_ok=True)


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


def _read_version_file(job_id: str, version: int) -> dict:
    _validate_job_id(job_id)
    _validate_version(version)
    path = (_JOBS_DIR / job_id / f"v{version}.json").resolve()
    if not str(path).startswith(str(_JOBS_DIR.resolve())):
        raise ValueError("Path traversal detected")
    if not path.exists():
        raise FileNotFoundError(f"Version {version} not found for job {job_id}")
    with open(path, "r") as f:
        return json.load(f)


def _write_version_file(job_id: str, version: int, data: dict):
    _validate_job_id(job_id)
    _validate_version(version)
    job_dir = (_JOBS_DIR / job_id).resolve()
    if not str(job_dir).startswith(str(_JOBS_DIR.resolve())):
        raise ValueError("Path traversal detected")
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / f"v{version}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _find_entry(entries: list[dict], job_id: str) -> dict | None:
    """O(1) lookup via cached index, with list fallback."""
    if _cache_index:
        return _cache_index.get(job_id)
    for e in entries:
        if e["id"] == job_id:
            return e
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_jobs() -> list[dict]:
    """Return all manifest entries."""
    with _lock:
        return _read_manifest()


def get_job(job_id: str) -> dict:
    """Return manifest entry + current version data."""
    _validate_job_id(job_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, job_id)
        if not entry:
            raise KeyError(f"Job {job_id} not found")
        job_data = _read_version_file(job_id, entry["current_version"])
        return {"metadata": entry, "job_data": job_data}


def get_job_version(job_id: str, version: int) -> dict:
    """Return manifest entry + specific version data."""
    _validate_job_id(job_id)
    _validate_version(version)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, job_id)
        if not entry:
            raise KeyError(f"Job {job_id} not found")
        job_data = _read_version_file(job_id, version)
        return {"metadata": entry, "job_data": job_data}


def save_job(
    name: str,
    job_definition: dict,
    pyspark_script: str,
    script_name: str,
    issues: list[dict],
    design_rationale: str | None = None,
    note: str = "Initial generation",
) -> dict:
    """Create a new saved job. Returns the manifest entry."""
    job_id = str(uuid.uuid4())
    now = _now_iso()

    version_data = {
        "job": job_definition,
        "pyspark_script": pyspark_script,
        "script_name": script_name,
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
        "id": job_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "issues_addressed": len(issues),
        "issues_summary": issues_summary,
        "versions": [{"version": 1, "created_at": now, "note": note}],
        "current_version": 1,
    }

    with _lock:
        _write_version_file(job_id, 1, version_data)
        entries = _read_manifest()
        entries.append(entry)
        _write_manifest(entries)

    return entry


def update_job(
    job_id: str,
    name: str | None = None,
    job_definition: dict | None = None,
    pyspark_script: str | None = None,
    note: str = "Updated",
) -> dict:
    """Rename and/or create a new version. Returns updated manifest entry."""
    _validate_job_id(job_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, job_id)
        if not entry:
            raise KeyError(f"Job {job_id} not found")

        now = _now_iso()

        if name is not None:
            entry["name"] = name

        if job_definition is not None or pyspark_script is not None:
            current_data = _read_version_file(job_id, entry["current_version"])
            new_version = entry["current_version"] + 1
            version_data = {
                "job": job_definition if job_definition is not None else current_data.get("job", {}),
                "pyspark_script": pyspark_script if pyspark_script is not None else current_data.get("pyspark_script", ""),
                "script_name": current_data.get("script_name", "quality_remediation.py"),
                "issues": current_data.get("issues", []),
                "design_rationale": current_data.get("design_rationale"),
                "saved_at": now,
                "note": note,
            }
            _write_version_file(job_id, new_version, version_data)
            entry["versions"].append(
                {"version": new_version, "created_at": now, "note": note}
            )
            entry["current_version"] = new_version

        entry["updated_at"] = now
        _write_manifest(entries)

    return entry


def delete_job(job_id: str):
    """Remove job directory and manifest entry."""
    _validate_job_id(job_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, job_id)
        if not entry:
            raise KeyError(f"Job {job_id} not found")

        job_dir = (_JOBS_DIR / job_id).resolve()
        if not str(job_dir).startswith(str(_JOBS_DIR.resolve())):
            raise ValueError("Path traversal detected")
        if job_dir.exists():
            shutil.rmtree(job_dir)

        entries = [e for e in entries if e["id"] != job_id]
        _write_manifest(entries)


def clone_job(job_id: str, new_name: str | None = None) -> dict:
    """Copy current version of a job as v1 of a new job. Returns new entry."""
    _validate_job_id(job_id)
    with _lock:
        entries = _read_manifest()
        entry = _find_entry(entries, job_id)
        if not entry:
            raise KeyError(f"Job {job_id} not found")

        current_data = _read_version_file(job_id, entry["current_version"])

    clone_name = new_name or f"{entry['name']} (Copy)"
    return save_job(
        name=clone_name,
        job_definition=current_data["job"],
        pyspark_script=current_data.get("pyspark_script", ""),
        script_name=current_data.get("script_name", "quality_remediation.py"),
        issues=current_data.get("issues", []),
        design_rationale=current_data.get("design_rationale"),
        note=f"Cloned from {entry['name']}",
    )

"""Generate YAML data dictionary for use in data ingestion pipelines.

The output describes the dataset source format, column definitions with
inferred data types and constraints, profiling statistics, and a quality
summary — everything a downstream ingestion tool needs to parse, validate,
and load the data correctly.
"""

from datetime import datetime, timezone

import yaml

from data.profiler import QualityIssue, VALID_CODES


def _severity_for_pct(pct: float) -> str:
    if pct > 50:
        return "critical"
    elif pct > 10:
        return "high"
    elif pct > 1:
        return "medium"
    return "low"


def _infer_data_type(field, profile: dict | None) -> str:
    """Infer a logical data type from field metadata and profiling stats."""
    if field.is_date_field:
        return "date"
    if field.is_phone_field:
        return "phone"
    if field.is_code_field:
        return "code"

    if profile:
        # If every non-null value is length 1, likely a flag/indicator
        if profile.get("max_length", 0) == 1 and profile.get("min_length", 0) == 1:
            return "flag"
        # If distinct count == total non-null count, may be identifier
        non_null = profile.get("total_count", 0) - profile.get("null_count", 0)
        if non_null > 0 and profile.get("distinct_count", 0) == non_null:
            return "identifier"

    name_upper = field.field_name.upper()
    if name_upper.endswith("ID") or name_upper.endswith("NBR"):
        return "identifier"
    if name_upper.endswith("NM") or name_upper.endswith("NAME"):
        return "text"
    if name_upper.endswith("AMT"):
        return "amount"
    if name_upper.endswith("CNT") or name_upper.endswith("QTY"):
        return "integer"
    if field.is_blank_field:
        return "reserved"

    return "string"


def generate_metadata_yaml_dict(
    issues: list[QualityIssue],
    fields: list,
    profiles: list[dict] | None = None,
    row_count: int | None = None,
    spec_name: str = "AGT Data Ingestion Specification",
) -> dict:
    """Build ingestion-oriented data dictionary as a plain dict.

    Args:
        issues: Detected quality issues.
        fields: List of FieldMeta objects from data/metadata.
        profiles: Optional list of profile dicts (from profiler.to_dict()).
        row_count: Total rows in the dataset.
        spec_name: Human-readable name for this spec.

    Returns:
        dict suitable for YAML rendering or JSON storage.
    """
    profile_lookup: dict[str, dict] = {}
    if profiles:
        for p in profiles:
            profile_lookup[p.get("field_name", "")] = p

    # Build issue lookup by field for embedding constraints into columns
    issue_lookup: dict[str, list[QualityIssue]] = {}
    for iss in issues:
        issue_lookup.setdefault(iss.field_name, []).append(iss)

    # --- metadata section ---
    meta = {
        "name": spec_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "format": "delimited",
            "delimiter": "|",
            "encoding": "UTF-8",
            "has_header": False,
            "row_count": row_count,
            "column_count": len(fields),
        },
    }

    # --- columns section (the primary content) ---
    columns_list = []
    for f in fields:
        prof = profile_lookup.get(f.field_name)
        data_type = _infer_data_type(f, prof)

        col: dict = {
            "name": f.field_name,
            "position": f.position,
            "business_name": f.business_name or None,
            "data_type": data_type,
            "max_length": f.max_length,
        }

        # Nullable info from profiling
        if prof:
            null_pct = prof.get("null_pct", 0)
            col["nullable"] = null_pct > 0
            col["null_pct"] = null_pct
            col["distinct_count"] = prof.get("distinct_count")

        # Constraints
        constraints = []
        constraints.append({"type": "max_length", "value": f.max_length})

        if f.field_name in VALID_CODES:
            constraints.append({
                "type": "valid_values",
                "values": list(VALID_CODES[f.field_name]),
            })

        col["constraints"] = constraints

        # Flags for downstream tools
        flags: dict = {}
        if f.is_code_field:
            flags["code_field"] = True
        if f.is_date_field:
            flags["date_field"] = True
        if f.is_phone_field:
            flags["phone_field"] = True
        if f.is_blank_field:
            flags["reserved"] = True
        if f.field_name.upper().endswith("ID") or f.field_name.upper().endswith("NBR"):
            flags["id_field"] = True
        if flags:
            col["flags"] = flags

        # Profiling statistics
        if prof:
            col["profiling"] = {
                "min_length": prof.get("min_length"),
                "max_length_actual": prof.get("max_length"),
                "avg_length": prof.get("avg_length"),
                "top_values": prof.get("top_values", [])[:5],
            }

        columns_list.append(col)

    # --- valid_value_sets section ---
    valid_value_sets: dict[str, list[str]] = {}
    for iss in issues:
        if iss.issue_type == "invalid_code_value":
            params = iss.params or {}
            vals = params.get("valid_values")
            if vals:
                valid_value_sets[iss.field_name] = list(vals)
    for field_name, codes in VALID_CODES.items():
        if field_name not in valid_value_sets:
            valid_value_sets[field_name] = list(codes)

    # --- quality_summary section (secondary, for reference) ---
    quality_issues = []
    for idx, iss in enumerate(issues):
        pct = iss.affected_pct
        quality_issues.append({
            "field": iss.field_name,
            "issue_type": iss.issue_type,
            "severity": _severity_for_pct(pct),
            "affected_pct": round(pct, 2),
            "description": iss.description,
            "suggested_fix": iss.suggested_fix,
        })

    return {
        "metadata": meta,
        "columns": columns_list,
        "valid_value_sets": valid_value_sets,
        "quality_summary": {
            "total_issues": len(issues),
            "issues": quality_issues,
        },
    }


def generate_metadata_yaml(
    issues: list[QualityIssue],
    fields: list,
    profiles: list[dict] | None = None,
    row_count: int | None = None,
    spec_name: str = "AGT Data Ingestion Specification",
) -> str:
    """Generate YAML string from issues, fields, and optional profiles."""
    data = generate_metadata_yaml_dict(issues, fields, profiles, row_count, spec_name)
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def enrich_metadata_with_classification(yaml_dict: dict, classification_data: dict) -> dict:
    """Merge classification results into an existing metadata YAML dict.

    Adds sensitivity_level, semantic_type, business_term, hl7_fhir_mapping,
    and regulatory_tags to each column entry.

    Args:
        yaml_dict: Existing metadata YAML dict (from generate_metadata_yaml_dict).
        classification_data: Classification result dict (from orchestrator.to_dict()).

    Returns:
        Enriched yaml_dict (modified in place and returned).
    """
    clf_lookup = {}
    for col in classification_data.get("columns", []):
        clf_lookup[col.get("field_name", "")] = col

    columns = yaml_dict.get("columns", [])
    for col in columns:
        name = col.get("name", "")
        clf = clf_lookup.get(name)
        if not clf:
            continue

        if clf.get("sensitivity_label"):
            col["sensitivity_level"] = clf["sensitivity_label"]
        if clf.get("semantic_type"):
            col["semantic_type"] = clf["semantic_type"]
        if clf.get("business_term"):
            col["business_term"] = clf["business_term"]
        if clf.get("hl7_fhir_mapping"):
            col["hl7_fhir_mapping"] = clf["hl7_fhir_mapping"]
        if clf.get("regulatory_tags"):
            col["regulatory_tags"] = clf["regulatory_tags"]

    return yaml_dict

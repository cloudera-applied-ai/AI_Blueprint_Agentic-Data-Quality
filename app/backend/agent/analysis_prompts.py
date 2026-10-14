"""Prompt builders for LLM-enhanced analysis on Data Profile and NiFi tabs."""

import json


def quality_issues_analysis_prompt(issues_data: list[dict]) -> tuple[str, str]:
    """Return (system_prompt, user_content) for quality-issues analysis."""
    system = (
        "You are a senior healthcare data quality analyst specializing in "
        "Medicaid/CMS member eligibility data (AGT format). "
        "You provide severity rankings, root-cause hypotheses, "
        "compliance implications (HIPAA, CMS regulations), "
        "and recommend additional checks.\n\n"
        "Structure your response with clear sections using markdown:\n"
        "1. **Severity Ranking** - rank issues from most to least critical with rationale\n"
        "2. **Healthcare & Compliance Context** - HIPAA, CMS, and patient-impact implications\n"
        "3. **Root Cause Hypotheses** - likely upstream causes for each issue pattern\n"
        "4. **Recommended Additional Checks** - further validations to perform\n"
        "5. **Remediation Priority** - suggested order of fixes with justification\n\n"
        "Be concise but thorough. Use bullet points. Reference specific field names and counts."
    )

    user = (
        "Analyze the following data quality issues detected in our AGT member "
        "eligibility dataset. Provide severity ranking, healthcare context, "
        "root cause hypotheses, and recommended additional checks.\n\n"
        f"Detected Issues:\n```json\n{json.dumps(issues_data, indent=2)}\n```"
    )

    return system, user


def column_profile_analysis_prompt(profile_data: dict) -> tuple[str, str]:
    """Return (system_prompt, user_content) for column-profile interpretation."""
    system = (
        "You are a senior healthcare data quality analyst specializing in "
        "Medicaid/CMS member eligibility data (AGT format). "
        "You interpret column profile statistics in a healthcare context, "
        "identifying anomalies, patterns, and data quality concerns.\n\n"
        "Structure your response with clear sections using markdown:\n"
        "1. **Data Quality Assessment** - overall health of this field\n"
        "2. **Pattern Analysis** - what the value distribution reveals\n"
        "3. **Anomaly Detection** - any unexpected patterns, outliers, or red flags\n"
        "4. **Healthcare Field Context** - what this field means in Medicaid/CMS and "
        "what correct data should look like\n"
        "5. **Recommendations** - specific actions to improve data quality\n\n"
        "Be concise. Reference specific values and percentages from the profile."
    )

    user = (
        "Analyze this column profile from our AGT member eligibility dataset. "
        "Provide a data quality assessment, pattern analysis, anomaly detection, "
        "and healthcare context.\n\n"
        f"Column Profile:\n```json\n{json.dumps(profile_data, indent=2)}\n```"
    )

    return system, user


def schema_recommendation_prompt(
    profiles: list[dict],
    issues: list[dict],
    fields_meta: list[dict],
) -> tuple[str, str]:
    """Return (system_prompt, user_content) for schema recommendation."""
    system = (
        "You are a senior healthcare data architect specializing in "
        "Medicaid/CMS AGT member eligibility data. "
        "Analyze column profiles and quality issues, then recommend proper "
        "data types, constraints, and keys.\n\n"
        "Provide your response as a structured markdown table:\n\n"
        "| Column | Recommended Type | Nullable | PK | Constraints | Notes |\n"
        "|--------|-----------------|----------|-----|-------------|-------|\n\n"
        "After the table, add:\n"
        "1. **Key Observations** - patterns in data quality\n"
        "2. **Schema Recommendations** - indexing, partitioning, normalization\n"
        "3. **Data Governance Notes** - HIPAA considerations for PHI fields\n\n"
        "Be concise. Reference specific column statistics."
    )

    # Build condensed profile summaries
    profile_summaries = []
    for p in profiles:
        top5 = p.get("top_values", [])[:5]
        top5_str = ", ".join(f"{v['value']}({v['count']})" for v in top5)
        profile_summaries.append({
            "field": p["field_name"],
            "distinct": p.get("distinct_count", 0),
            "null_pct": p.get("null_pct", 0),
            "max_len": p.get("max_length", 0),
            "top_values": top5_str,
        })

    # Build field metadata flags
    meta_flags = []
    for m in fields_meta:
        flags = []
        if m.get("is_code_field"):
            flags.append("CODE")
        if m.get("is_date_field"):
            flags.append("DATE")
        if m.get("is_phone_field"):
            flags.append("PHONE")
        if m.get("is_blank_field"):
            flags.append("BLANK")
        if flags:
            meta_flags.append({"field": m["field_name"], "flags": flags})

    user = (
        "Analyze this AGT member eligibility dataset and recommend a target schema.\n\n"
        f"Column Profiles:\n```json\n{json.dumps(profile_summaries, indent=2)}\n```\n\n"
        f"Quality Issues:\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
        f"Field Metadata Flags:\n```json\n{json.dumps(meta_flags, indent=2)}\n```"
    )

    return system, user


def schema_recommendation_prompt(
    profiles: list[dict],
    issues: list[dict],
    fields_meta: list[dict],
) -> tuple[str, str]:
    """Return (system_prompt, user_content) for schema recommendation."""
    system = (
        "You are a senior healthcare data architect specializing in "
        "Medicaid/CMS AGT member eligibility data. "
        "Analyze column profiles and quality issues, then recommend proper "
        "data types, constraints, and keys.\n\n"
        "Provide your response as a structured markdown table:\n\n"
        "| Column | Recommended Type | Nullable | PK | Constraints | Notes |\n"
        "|--------|-----------------|----------|-----|-------------|-------|\n\n"
        "After the table, add:\n"
        "1. **Key Observations** - patterns in data quality\n"
        "2. **Schema Recommendations** - indexing, partitioning, normalization\n"
        "3. **Data Governance Notes** - HIPAA considerations for PHI fields\n\n"
        "Be concise. Reference specific column statistics."
    )

    # Build condensed profile summaries
    profile_summaries = []
    for p in profiles:
        top5 = p.get("top_values", [])[:5]
        top5_str = ", ".join(f"{v['value']}({v['count']})" for v in top5)
        profile_summaries.append({
            "field": p["field_name"],
            "distinct": p.get("distinct_count", 0),
            "null_pct": p.get("null_pct", 0),
            "max_len": p.get("max_length", 0),
            "top_values": top5_str,
        })

    # Build field metadata flags
    meta_flags = []
    for m in fields_meta:
        flags = []
        if m.get("is_code_field"):
            flags.append("CODE")
        if m.get("is_date_field"):
            flags.append("DATE")
        if m.get("is_phone_field"):
            flags.append("PHONE")
        if m.get("is_blank_field"):
            flags.append("BLANK")
        if flags:
            meta_flags.append({"field": m["field_name"], "flags": flags})

    user = (
        "Analyze this AGT member eligibility dataset and recommend a target schema.\n\n"
        f"Column Profiles:\n```json\n{json.dumps(profile_summaries, indent=2)}\n```\n\n"
        f"Quality Issues:\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
        f"Field Metadata Flags:\n```json\n{json.dumps(meta_flags, indent=2)}\n```"
    )

    return system, user


def spark_job_design_prompt(
    issues_data: list[dict],
    job_data: dict,
) -> tuple[str, str]:
    """Return (system_prompt, user_content) for Spark job design rationale."""
    system = (
        "You are a senior data engineer specializing in PySpark and Cloudera Data "
        "Engineering (CDE) for healthcare data quality remediation. "
        "You explain Spark job design decisions, PySpark transformations, "
        "quality detection logic, and HIPAA compliance considerations.\n\n"
        "Structure your response with clear sections using markdown:\n"
        "1. **Remediation Strategy** - overall approach for each issue\n"
        "2. **PySpark Pipeline Architecture** - how the script processes data "
        "through flag, split, fix, and write stages\n"
        "3. **Quality Detection Logic** - what each flag column checks "
        "and the PySpark expressions used\n"
        "4. **Fix Expressions** - how corrected records are transformed\n"
        "5. **CDE Job Configuration** - driver/executor sizing rationale "
        "and Spark configuration choices\n"
        "6. **HIPAA & Audit Notes** - logging, data lineage, and compliance considerations\n"
        "7. **Deployment Recommendations** - CDE resource setup, "
        "scheduling, and operational tips\n\n"
        "Be specific about PySpark expressions and CDE configuration. "
        "Reference the actual issue fields and fix strategies."
    )

    job_summary = {
        "job_name": job_data.get("job_name", ""),
        "issues_addressed": job_data.get("issues_addressed", 0),
        "issues": job_data.get("issues", []),
        "script_name": job_data.get("script_name", ""),
        "job_type": job_data.get("job", {}).get("type", "spark"),
        "num_executors": job_data.get("job", {}).get("spark", {}).get("numExecutors", 4),
    }

    user = (
        "Explain the design rationale for this CDE Spark data quality remediation job. "
        "Cover the remediation strategy, PySpark logic, quality detection expressions, "
        "fix transformations, CDE configuration, and HIPAA compliance.\n\n"
        f"Issues Being Remediated:\n```json\n{json.dumps(issues_data, indent=2)}\n```\n\n"
        f"Job Summary:\n```json\n{json.dumps(job_summary, indent=2)}\n```"
    )

    return system, user


def nifi_flow_design_prompt(
    issues_data: list[dict],
    flow_data: dict,
) -> tuple[str, str]:
    """Return (system_prompt, user_content) for NiFi flow design rationale."""
    system = (
        "You are a senior Apache NiFi architect specializing in healthcare data "
        "quality remediation pipelines for Medicaid/CMS data. "
        "You explain NiFi flow design decisions, processor configurations, "
        "Expression Language usage, and HIPAA audit considerations.\n\n"
        "Structure your response with clear sections using markdown:\n"
        "1. **Remediation Strategy** - overall approach for each issue\n"
        "2. **Flow Architecture** - how processors chain together and why\n"
        "3. **Processor Explanations** - what each key processor does "
        "and its NiFi Expression Language logic\n"
        "4. **HIPAA & Audit Notes** - logging, provenance, and compliance considerations\n"
        "5. **Deployment Recommendations** - environment setup, "
        "parameter contexts, and operational tips\n\n"
        "Be specific about NiFi EL expressions and processor types. "
        "Reference the actual issue fields and fix strategies."
    )

    # Summarize flow structure instead of sending full JSON
    flow_summary = {
        "flow_name": flow_data.get("flow_name", ""),
        "issues_addressed": flow_data.get("issues_addressed", 0),
        "issues": flow_data.get("issues", []),
    }
    # Count processor types from the full flow if available
    flow_obj = flow_data.get("flow", {})
    fg = flow_obj.get("flowContents", {})
    processors = fg.get("processors", [])
    connections = fg.get("connections", [])
    flow_summary["processor_count"] = len(processors)
    flow_summary["connection_count"] = len(connections)
    flow_summary["processor_types"] = list(
        {p.get("type", "unknown") for p in processors}
    )

    user = (
        "Explain the design rationale for this NiFi data quality remediation flow. "
        "Cover the remediation strategy, processor logic, NiFi EL expressions, "
        "and HIPAA audit considerations.\n\n"
        f"Issues Being Remediated:\n```json\n{json.dumps(issues_data, indent=2)}\n```\n\n"
        f"Flow Summary:\n```json\n{json.dumps(flow_summary, indent=2)}\n```"
    )

    return system, user

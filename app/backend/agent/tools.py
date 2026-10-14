"""Tool definitions and implementations for the agent."""

import json

import duckdb

from data.metadata import FieldMeta
from data.loader import run_query
from data.profiler import profile_column, detect_quality_issues, VALID_CODES
from nifi.flow_generator import generate_flow_json
from spark.job_generator import generate_spark_job
from metadata.yaml_generator import generate_metadata_yaml_dict

# OpenAI function-calling tool definitions
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "run_sql_query",
            "description": "Execute a read-only DuckDB SQL query against the AGT table. Only SELECT statements are allowed. Results are auto-limited to 1000 rows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SELECT SQL query to execute against the 'agt' table",
                    }
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "profile_column",
            "description": "Get detailed statistics and value distribution for ONE column at a time: count, nulls, distinct values, min/max/avg length, top 20 values, length violations. You must provide an exact column name — wildcards like '*' are NOT supported. Call this tool once per column you want to profile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "Exact column name to profile (e.g. 'MRTLSTTSCD', 'PRMRYPHONENBR'). Must match a real column name. Use get_field_metadata or get_data_summary to discover column names first.",
                    }
                },
                "required": ["field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_quality_issues",
            "description": "Scan columns for data quality issues: invalid codes, bad phone numbers, data in blank fields, length violations, corrupted data. Returns issue details with counts and sample bad values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of specific field names to check. If empty, checks all known problem fields.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_field_metadata",
            "description": "Get schema information for one or more fields: position, field name, max length, business name, field type flags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Field names to look up. Use '*' or empty array for all fields.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_coded_values",
            "description": "Check a specific field's actual values against a provided list of valid values. Returns counts of valid vs invalid records and sample invalid values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "The column name to validate",
                    },
                    "valid_values": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of acceptable values for this field",
                    },
                },
                "required": ["field_name", "valid_values"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_nifi_flow",
            "description": "Generate a complete Apache NiFi v2 dataflow JSON to remediate specified quality issues. The flow includes routing, validation, and correction processors with proper NiFi Expression Language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_descriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of issue descriptions to build remediation for (e.g., 'invalid phone numbers in PRMRYPHONENBR', 'corrupted MRTLSTTSCD values'). Will auto-detect matching issues.",
                    },
                    "flow_name": {
                        "type": "string",
                        "description": "Name for the NiFi flow (default: 'AGT Data Quality Remediation')",
                    },
                },
                "required": ["issue_descriptions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_spark_job",
            "description": "Generate a Cloudera Data Engineering (CDE) Spark job definition and PySpark script to remediate specified quality issues. Produces a CDE-importable JSON and a complete PySpark script that reads the data, flags issues, splits into valid/corrected/rejected, applies fixes, and writes output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_descriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of issue descriptions to build remediation for (e.g., 'invalid phone numbers in PRMRYPHONENBR'). Will auto-detect matching issues.",
                    },
                    "job_name": {
                        "type": "string",
                        "description": "Name for the CDE Spark job (default: 'AGT Data Quality Remediation')",
                    },
                    "output_format": {
                        "type": "string",
                        "description": "Output format: 'parquet' or 'delta' (default: 'parquet')",
                    },
                },
                "required": ["issue_descriptions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_metadata_yaml",
            "description": "Generate a YAML data quality specification file capturing fields, rules, valid values, and profiling stats. Produces a complete metadata spec that can be saved and downloaded.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_descriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of issue descriptions to include in the spec (e.g., 'invalid phone numbers in PRMRYPHONENBR'). Will auto-detect matching issues.",
                    },
                    "spec_name": {
                        "type": "string",
                        "description": "Name for the metadata specification (default: 'AGT Data Ingestion Specification')",
                    },
                },
                "required": ["issue_descriptions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_summary",
            "description": "Get a high-level overview of the loaded dataset: row count, column count, column names with types, and sample data.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_metadata",
            "description": "Classify all dataset columns for data sensitivity (PII/PHI/internal/public), semantic type, format, business terms, HL7/FHIR mappings, and regulatory tags. Uses fast ML classifiers for basic classification and optionally an LLM for complex tasks like business term mapping and ontology alignment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for this classification run (default: 'AGT Classification')",
                    },
                    "use_llm": {
                        "type": "boolean",
                        "description": "Whether to use LLM for enhanced classification (business terms, HL7/FHIR). Default: true",
                    },
                },
                "required": [],
            },
        },
    },
]


def execute_tool(
    tool_name: str,
    arguments: dict,
    conn: duckdb.DuckDBPyConnection,
    fields: list[FieldMeta],
    issues_cache: list | None = None,
) -> str:
    """Execute a tool and return the result as a JSON string."""
    try:
        if tool_name == "run_sql_query":
            result = run_query(conn, arguments["sql"])
            return json.dumps(result, default=str)

        elif tool_name == "profile_column":
            fname = arguments["field_name"].strip().upper()
            if fname in ("*", "ALL", ""):
                return json.dumps({
                    "error": "profile_column requires an exact column name — wildcards are not supported. "
                             "Call profile_column once per column, or use get_data_summary for a high-level overview."
                })
            field = next((f for f in fields if f.field_name == fname), None)
            if not field:
                return json.dumps({
                    "error": f"Field '{fname}' not found. Use get_field_metadata or get_data_summary to list available columns."
                })
            profile = profile_column(conn, field)
            return json.dumps(profile.to_dict(), default=str)

        elif tool_name == "detect_quality_issues":
            target = arguments.get("field_names", [])
            issues = detect_quality_issues(conn, fields, target if target else None)
            return json.dumps([i.to_dict() for i in issues], default=str)

        elif tool_name == "get_field_metadata":
            names = arguments.get("field_names", [])
            if not names or names == ["*"]:
                result = fields
            else:
                name_set = {n.upper() for n in names}
                result = [f for f in fields if f.field_name in name_set]
            return json.dumps([
                {
                    "position": f.position,
                    "field_name": f.field_name,
                    "max_length": f.max_length,
                    "business_name": f.business_name,
                    "is_code_field": f.is_code_field,
                    "is_date_field": f.is_date_field,
                    "is_phone_field": f.is_phone_field,
                    "is_blank_field": f.is_blank_field,
                }
                for f in result
            ])

        elif tool_name == "validate_coded_values":
            fname = arguments["field_name"].strip().upper()
            # S16: Validate field name against loaded fields to prevent SQL injection
            field = next((f for f in fields if f.field_name == fname), None)
            if not field:
                return json.dumps({
                    "error": f"Field '{fname}' not found. Use get_field_metadata to list available columns."
                })
            valid_values = arguments["valid_values"]
            if not valid_values or len(valid_values) > 100:
                return json.dumps({"error": "valid_values must be a non-empty list with at most 100 entries."})
            # Sanitize values: only allow safe characters for code values
            import re as _re
            _safe_val = _re.compile(r'^[A-Za-z0-9 _.\-]{0,50}$')
            valid_upper = []
            for v in valid_values:
                v_str = str(v).strip().upper()
                if not _safe_val.match(v_str):
                    return json.dumps({"error": f"Invalid character in valid_value: {v!r}"})
                valid_upper.append(v_str)

            import config
            # Use parameterized-safe quoting: values are validated above
            valid_list = ", ".join(f"'{v}'" for v in valid_upper)
            total = conn.execute(f"""
                SELECT COUNT(*) FROM {config.TABLE_NAME}
                WHERE "{fname}" IS NOT NULL AND TRIM("{fname}") != ''
            """).fetchone()[0]

            invalid = conn.execute(f"""
                SELECT COUNT(*), LIST(DISTINCT "{fname}" LIMIT 10)
                FROM {config.TABLE_NAME}
                WHERE "{fname}" IS NOT NULL AND TRIM("{fname}") != ''
                  AND UPPER(TRIM("{fname}")) NOT IN ({valid_list})
            """).fetchone()

            return json.dumps({
                "field_name": fname,
                "total_non_null": total,
                "valid_count": total - (invalid[0] or 0),
                "invalid_count": invalid[0] or 0,
                "invalid_pct": round((invalid[0] or 0) / total * 100, 2) if total else 0,
                "sample_invalid": [str(v) for v in (invalid[1] or [])],
                "valid_values_checked": valid_values,
            })

        elif tool_name == "generate_nifi_flow":
            descriptions = arguments.get("issue_descriptions", [])
            flow_name = arguments.get("flow_name", "AGT Data Quality Remediation")

            # Get issues if not cached
            if issues_cache:
                issues = issues_cache
            else:
                issues = detect_quality_issues(conn, fields)

            # Match requested issues
            if descriptions:
                matched = []
                for issue in issues:
                    for desc in descriptions:
                        desc_lower = desc.lower()
                        if (issue.field_name.lower() in desc_lower
                                or issue.issue_type.lower() in desc_lower
                                or any(w in desc_lower for w in issue.description.lower().split()[:3])):
                            matched.append(issue)
                            break
                if not matched:
                    matched = issues
            else:
                matched = issues

            flow_json_str = generate_flow_json(matched, flow_name)
            flow_obj = json.loads(flow_json_str)

            # Build a human-readable summary instead of dumping full JSON
            processors = flow_obj.get("rootGroup", {}).get("processors", [])
            connections = flow_obj.get("rootGroup", {}).get("connections", [])
            processor_summary = [
                {"name": p.get("name", "?"), "type": p.get("type", "?").rsplit(".", 1)[-1]}
                for p in processors
            ]

            return json.dumps({
                "flow_name": flow_name,
                "issues_addressed": len(matched),
                "issues": [
                    f"{i.issue_type}: {i.field_name} ({i.affected_pct}% affected)"
                    for i in matched
                ],
                "flow_summary": {
                    "total_processors": len(processors),
                    "total_connections": len(connections),
                    "processors": processor_summary,
                },
                "note": "The full NiFi flow JSON is available in the NiFi Flows tab. Use the Generate tab to create and save flows, or the Saved Flows tab to manage them.",
            }, default=str)

        elif tool_name == "generate_spark_job":
            import re as _re
            descriptions = arguments.get("issue_descriptions", [])
            job_name = arguments.get("job_name", "AGT Data Quality Remediation")
            # Sanitize job_name: allow only alphanumeric, spaces, hyphens, underscores
            if not _re.match(r'^[A-Za-z0-9 _-]{1,128}$', job_name):
                job_name = "AGT Data Quality Remediation"
            output_format = arguments.get("output_format", "parquet")
            if output_format not in ("parquet", "delta", "csv", "json"):
                output_format = "parquet"

            # Get issues if not cached
            if issues_cache:
                issues = issues_cache
            else:
                issues = detect_quality_issues(conn, fields)

            # Match requested issues
            if descriptions:
                matched = []
                for issue in issues:
                    for desc in descriptions:
                        desc_lower = desc.lower()
                        if (issue.field_name.lower() in desc_lower
                                or issue.issue_type.lower() in desc_lower
                                or any(w in desc_lower for w in issue.description.lower().split()[:3])):
                            matched.append(issue)
                            break
                if not matched:
                    matched = issues
            else:
                matched = issues

            result = generate_spark_job(matched, job_name, output_format)

            return json.dumps({
                "job_name": job_name,
                "output_format": output_format,
                "issues_addressed": len(matched),
                "issues": [
                    f"{i.issue_type}: {i.field_name} ({i.affected_pct}% affected)"
                    for i in matched
                ],
                "job_summary": {
                    "type": result["job_definition"].get("type", "spark"),
                    "script_name": result["script_name"],
                    "num_executors": result["job_definition"].get("spark", {}).get("numExecutors", 4),
                },
                "note": "The full CDE job JSON and PySpark script are available in the Spark Jobs tab. Use the Generate tab to create and save jobs, or the Saved Jobs tab to manage them.",
            }, default=str)

        elif tool_name == "generate_metadata_yaml":
            import re as _re
            descriptions = arguments.get("issue_descriptions", [])
            spec_name = arguments.get("spec_name", "AGT Data Ingestion Specification")
            if not _re.match(r'^[A-Za-z0-9 _\-]{1,128}$', spec_name):
                spec_name = "AGT Data Ingestion Specification"

            # Get issues if not cached
            if issues_cache:
                issues = issues_cache
            else:
                issues = detect_quality_issues(conn, fields)

            # Match requested issues
            if descriptions:
                matched = []
                for issue in issues:
                    for desc in descriptions:
                        desc_lower = desc.lower()
                        if (issue.field_name.lower() in desc_lower
                                or issue.issue_type.lower() in desc_lower
                                or any(w in desc_lower for w in issue.description.lower().split()[:3])):
                            matched.append(issue)
                            break
                if not matched:
                    matched = issues
            else:
                matched = issues

            import config
            row_count_val = conn.execute(f"SELECT COUNT(*) FROM {config.TABLE_NAME}").fetchone()[0]
            yaml_dict = generate_metadata_yaml_dict(matched, fields, row_count=row_count_val, spec_name=spec_name)

            return json.dumps({
                "spec_name": spec_name,
                "issues_addressed": len(matched),
                "issues": [
                    f"{i.issue_type}: {i.field_name} ({i.affected_pct}% affected)"
                    for i in matched
                ],
                "rules_count": len(yaml_dict.get("rules", [])),
                "fields_count": len(yaml_dict.get("fields", [])),
                "valid_value_sets_count": len(yaml_dict.get("valid_value_sets", {})),
                "note": "The full metadata YAML file is available in the Metadata tab. Use the Generate tab to create and save files, or the Saved Files tab to manage them.",
            }, default=str)

        elif tool_name == "get_data_summary":
            import config
            row_count = conn.execute(f"SELECT COUNT(*) FROM {config.TABLE_NAME}").fetchone()[0]
            sample = run_query(conn, f"SELECT * FROM {config.TABLE_NAME} LIMIT 5")
            return json.dumps({
                "table_name": config.TABLE_NAME,
                "row_count": row_count,
                "column_count": len(fields),
                "columns": [
                    {"name": f.field_name, "max_length": f.max_length, "business_name": f.business_name}
                    for f in fields
                ],
                "sample_data": sample,
            }, default=str)

        elif tool_name == "classify_metadata":
            from classification.orchestrator import classify_metadata as _classify
            name = arguments.get("name", "AGT Classification")
            use_llm = arguments.get("use_llm", True)

            # Try to get LLM client
            llm_client, llm_model = None, ""
            if use_llm:
                try:
                    from routers.chat import resolve_llm_client
                    llm_client, llm_model = resolve_llm_client()
                except Exception:
                    pass

            result = _classify(
                fields=fields,
                name=name,
                use_llm=use_llm,
                llm_client=llm_client,
                llm_model=llm_model,
            )
            result_dict = result.to_dict()

            # Return summary for chat, not all 124 columns
            summary = result_dict.get("summary", {})
            return json.dumps({
                "name": result_dict["name"],
                "total_columns": result_dict["total_columns"],
                "llm_used": result_dict["llm_used"],
                "sensitivity_counts": summary.get("sensitivity_counts", {}),
                "avg_sensitivity_confidence": summary.get("avg_sensitivity_confidence", 0),
                "avg_semantic_confidence": summary.get("avg_semantic_confidence", 0),
                "sample_classifications": [c for c in result_dict["columns"][:5]],
                "note": "Full classification results with all columns are available in the Classification tab. Use the Generate tab to view and save complete results.",
            }, default=str)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except (KeyError, ValueError, TypeError) as e:
        return json.dumps({"error": str(e)})
    except duckdb.Error as e:
        return json.dumps({"error": f"Database error: {e}"})
    except Exception:
        return json.dumps({"error": "An unexpected error occurred while executing the tool."})

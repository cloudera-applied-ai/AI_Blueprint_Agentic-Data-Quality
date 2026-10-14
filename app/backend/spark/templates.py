"""PySpark code snippet builders and CDE job envelope templates."""

import re

_SAFE_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_SAFE_VALUE_RE = re.compile(r'^[A-Za-z0-9_ .-]*$')


def _validate_field_name(name: str) -> str:
    """Validate field name is a safe identifier for code embedding."""
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid field name for code generation: {name!r}")
    return name


def _validate_code_value(value: str) -> str:
    """Validate a code value is safe to embed in generated PySpark strings."""
    if not _SAFE_VALUE_RE.match(value):
        raise ValueError(f"Invalid code value for code generation: {value!r}")
    return value


def cde_job_definition(
    job_name: str = "AGT Data Quality Remediation",
    script_name: str = "quality_remediation.py",
    spark_config: dict | None = None,
) -> dict:
    """Build a CDE REST API job definition (POST /api/v1/jobs)."""
    cfg = spark_config or {}
    return {
        "name": job_name,
        "type": "spark",
        "retentionPolicy": "keep_indefinitely",
        "mounts": [{"dirPrefix": "/", "resourceName": "dq-scripts"}],
        "spark": {
            "file": script_name,
            "driverCores": cfg.get("driverCores", 2),
            "driverMemory": cfg.get("driverMemory", "4g"),
            "executorCores": cfg.get("executorCores", 2),
            "executorMemory": cfg.get("executorMemory", "4g"),
            "numExecutors": cfg.get("numExecutors", 4),
            "conf": {
                "spark.pyspark.python": "python3",
                "spark.sql.adaptive.enabled": "true",
                **(cfg.get("conf", {})),
            },
        },
        "schedule": {"enabled": False},
    }


def pyspark_quality_check(issue_type: str, field_name: str, params: dict | None = None) -> str:
    """Return a PySpark F.when() condition string for detecting a quality issue."""
    params = params or {}
    _validate_field_name(field_name)
    col = f'F.col("{field_name}")'

    if issue_type == "corrupted_data":
        return f'{col}.rlike(r"[a-z]{{3,}}")'

    elif issue_type == "invalid_code_value":
        valid_values = params.get("valid_values", [])
        if valid_values:
            vals = ", ".join(f'"{_validate_code_value(v).upper()}"' for v in valid_values)
            return f"~F.upper({col}).isin([{vals}])"
        return f'{col}.isNotNull() & (F.trim({col}) != "")'

    elif issue_type == "invalid_phone_number":
        return f'{col}.startswith("0") | {col}.startswith("1")'

    elif issue_type == "data_in_blank_field":
        return f'{col}.isNotNull() & (F.trim({col}) != "")'

    elif issue_type == "length_violation":
        max_len = int(params.get("max_length", 50))
        return f"F.length({col}) > {max_len}"

    elif issue_type == "format_mismatch":
        return f'{col}.rlike(r"^[0-9]+$")'

    else:
        return f'{col}.isNotNull() & (F.trim({col}) != "")'


def pyspark_fix_expression(issue_type: str, field_name: str, params: dict | None = None) -> str:
    """Return a PySpark .withColumn() fix expression string for an issue."""
    params = params or {}
    _validate_field_name(field_name)
    col = f'F.col("{field_name}")'

    if issue_type == "length_violation":
        max_len = int(params.get("max_length", 50))
        return f'F.substring({col}, 1, {max_len})'

    # Default for most issue types: null out the bad value
    return "F.lit(None).cast(StringType())"

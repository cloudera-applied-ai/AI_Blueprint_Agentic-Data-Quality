"""Generate CDE Spark job definitions and PySpark scripts for data quality remediation."""

import json
import re

from data.profiler import QualityIssue
from spark.templates import (
    cde_job_definition,
    pyspark_quality_check,
    pyspark_fix_expression,
)

_ALLOWED_FORMATS = {"parquet", "delta", "csv", "json"}


def _sanitize_name(name: str) -> str:
    """Make a string safe for use as a Python identifier suffix."""
    return re.sub(r'[^a-z0-9_]', '', name.lower().replace(" ", "_").replace("-", "_")) or "unnamed"


def generate_pyspark_script(
    issues: list[QualityIssue],
    input_path: str = "/data/input/agt_data.txt",
    output_base: str = "/data/output",
    output_format: str = "parquet",
) -> str:
    """Generate a complete PySpark script that performs quality remediation.

    The script:
    1. Reads the pipe-delimited input
    2. Adds boolean flag columns per issue
    3. Creates a composite _has_quality_issue column
    4. Splits into valid / corrected / rejected DataFrames
    5. Applies fix expressions to corrected records
    6. Writes each split to the output directory
    """
    if output_format.lower() not in _ALLOWED_FORMATS:
        raise ValueError(f"Invalid output format: {output_format!r}. Allowed: {_ALLOWED_FORMATS}")

    lines: list[str] = []

    # Header
    lines.append('"""')
    lines.append("PySpark Data Quality Remediation Script")
    lines.append(f"Issues addressed: {len(issues)}")
    lines.append('"""')
    lines.append("")
    lines.append("from pyspark.sql import SparkSession, DataFrame")
    lines.append("from pyspark.sql import functions as F")
    lines.append("from pyspark.sql.types import StringType")
    lines.append("")
    lines.append("")

    # SparkSession
    lines.append('spark = SparkSession.builder \\')
    lines.append('    .appName("AGT Data Quality Remediation") \\')
    lines.append('    .getOrCreate()')
    lines.append("")

    # Read input
    lines.append("# Read pipe-delimited input")
    lines.append("df = spark.read \\")
    lines.append('    .option("header", "true") \\')
    lines.append('    .option("delimiter", "|") \\')
    lines.append('    .option("inferSchema", "false") \\')
    lines.append(f'    .csv("{input_path}")')
    lines.append("")

    # Flag columns — batched into a single .select() to avoid deep query plan
    lines.append("# === Quality flag columns (batched select) ===")
    flag_cols: list[str] = []
    flag_exprs: list[str] = []
    for issue in issues:
        flag_name = f"_flag_{_sanitize_name(issue.field_name)}_{_sanitize_name(issue.issue_type)}"
        check_expr = pyspark_quality_check(issue.issue_type, issue.field_name, issue.params)
        flag_exprs.append(
            f'    F.when({check_expr}, F.lit(True)).otherwise(F.lit(False)).alias("{flag_name}")'
        )
        flag_cols.append(flag_name)

    if flag_exprs:
        lines.append("df = df.select(")
        lines.append('    "*",')
        lines.append(",\n".join(flag_exprs))
        lines.append(")")
    lines.append("")

    # Composite flag
    lines.append("# Composite quality flag")
    if flag_cols:
        or_expr = " | ".join(f'F.col("{fc}")' for fc in flag_cols)
        lines.append(f"df = df.withColumn(\"_has_quality_issue\", {or_expr})")
    else:
        lines.append('df = df.withColumn("_has_quality_issue", F.lit(False))')
    lines.append("")

    # Split DataFrames
    lines.append("# Split into valid / corrected / rejected")
    lines.append('valid_df = df.filter(~F.col("_has_quality_issue"))')
    lines.append('issues_df = df.filter(F.col("_has_quality_issue"))')
    lines.append("")

    # Build corrected DataFrame — batched select for fix expressions
    lines.append("# Apply fixes to create corrected records (batched select)")
    if issues:
        # Build a dict of field -> list of (flag, fix_expr) to handle multiple issues per field
        fix_exprs: list[str] = []
        fixed_fields: set[str] = set()
        for issue in issues:
            fix_expr = pyspark_fix_expression(issue.issue_type, issue.field_name, issue.params)
            flag_name = f"_flag_{_sanitize_name(issue.field_name)}_{_sanitize_name(issue.issue_type)}"
            fix_exprs.append(
                f'    F.when(F.col("{flag_name}"), {fix_expr})'
                f'.otherwise(F.col("{issue.field_name}")).alias("{issue.field_name}")'
            )
            fixed_fields.add(issue.field_name)
        # Select all non-fixed columns plus fixed ones
        lines.append("_fixed_fields = " + repr(fixed_fields))
        lines.append("_other_cols = [F.col(c) for c in issues_df.columns if c not in _fixed_fields]")
        lines.append("corrected_df = issues_df.select(")
        lines.append("    *_other_cols,")
        lines.append(",\n".join(fix_exprs))
        lines.append(")")
    else:
        lines.append("corrected_df = issues_df")
    lines.append("")

    # Rejected = original issues (before fixes)
    lines.append("rejected_df = issues_df")
    lines.append("")

    # Drop flag columns for output
    lines.append("# Drop internal flag columns for final output")
    all_flags = flag_cols + ["_has_quality_issue"]
    flag_list_str = ", ".join(f'"{f}"' for f in all_flags)
    lines.append(f"drop_cols = [{flag_list_str}]")
    lines.append("valid_df = valid_df.drop(*drop_cols)")
    lines.append("corrected_df = corrected_df.drop(*drop_cols)")
    lines.append("rejected_df = rejected_df.drop(*drop_cols)")
    lines.append("")

    # Write output
    fmt = output_format.lower()
    lines.append(f"# Write output as {fmt}")
    lines.append(f'valid_df.write.mode("overwrite").{fmt}("{output_base}/valid")')
    lines.append(f'corrected_df.write.mode("overwrite").{fmt}("{output_base}/corrected")')
    lines.append(f'rejected_df.write.mode("overwrite").{fmt}("{output_base}/rejected")')
    lines.append("")

    # Summary
    lines.append("# Print summary")
    lines.append('print(f"Valid records:     {valid_df.count()}")')
    lines.append('print(f"Corrected records: {corrected_df.count()}")')
    lines.append('print(f"Rejected records:  {rejected_df.count()}")')
    lines.append("")
    lines.append("spark.stop()")
    lines.append("")

    return "\n".join(lines)


def generate_spark_job(
    issues: list[QualityIssue],
    job_name: str = "AGT Data Quality Remediation",
    output_format: str = "parquet",
    input_path: str = "/data/input/agt_data.txt",
    output_base: str = "/data/output",
    spark_config: dict | None = None,
) -> dict:
    """Generate CDE job definition + PySpark script.

    Returns dict with:
        - job_definition: CDE REST API JSON
        - pyspark_script: full .py file content
        - script_name: filename for the script
    """
    script_name = f"{_sanitize_name(job_name)}.py"
    script = generate_pyspark_script(issues, input_path, output_base, output_format)
    job_def = cde_job_definition(job_name, script_name, spark_config)

    return {
        "job_definition": job_def,
        "pyspark_script": script,
        "script_name": script_name,
    }


def generate_spark_job_json(
    issues: list[QualityIssue],
    job_name: str = "AGT Data Quality Remediation",
    output_format: str = "parquet",
    input_path: str = "/data/input/agt_data.txt",
    output_base: str = "/data/output",
    spark_config: dict | None = None,
) -> str:
    """Generate spark job and return as formatted JSON string."""
    result = generate_spark_job(issues, job_name, output_format, input_path, output_base, spark_config)
    return json.dumps(result, indent=2)

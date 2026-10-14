"""Column profiling and data quality issue detection."""

from dataclasses import dataclass, field, asdict
from typing import Optional

import duckdb

import config
from data.metadata import FieldMeta

T = config.TABLE_NAME


@dataclass
class ColumnProfile:
    field_name: str
    total_count: int = 0
    null_count: int = 0
    null_pct: float = 0.0
    distinct_count: int = 0
    min_length: int = 0
    max_length: int = 0
    avg_length: float = 0.0
    max_allowed_length: int = 0
    length_violation_count: int = 0
    top_values: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityIssue:
    field_name: str
    issue_type: str
    description: str
    affected_count: int
    affected_pct: float
    sample_bad_values: list[str]
    suggested_fix: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def profile_column(
    conn: duckdb.DuckDBPyConnection,
    field: FieldMeta,
) -> ColumnProfile:
    """Generate profile statistics for a single column."""
    col = field.field_name

    stats = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN "{col}" IS NULL OR TRIM("{col}") = '' THEN 1 ELSE 0 END) as nulls,
            COUNT(DISTINCT "{col}") as distincts,
            MIN(LENGTH("{col}")) as min_len,
            MAX(LENGTH("{col}")) as max_len,
            AVG(LENGTH("{col}")) as avg_len,
            SUM(CASE WHEN LENGTH("{col}") > {field.max_length} THEN 1 ELSE 0 END) as len_violations
        FROM {T}
        WHERE "{col}" IS NOT NULL AND TRIM("{col}") != ''
    """).fetchone()

    result = conn.execute(f"SELECT COUNT(*) FROM {T}").fetchone()
    if result is None:
        raise duckdb.Error(f"Table '{T}' not found — try reloading data.")
    total_rows = result[0]

    top = conn.execute(f"""
        SELECT "{col}" as val, COUNT(*) as cnt
        FROM {T}
        WHERE "{col}" IS NOT NULL AND TRIM("{col}") != ''
        GROUP BY "{col}"
        ORDER BY cnt DESC
        LIMIT 20
    """).fetchall()

    return ColumnProfile(
        field_name=col,
        total_count=total_rows,
        null_count=stats[1] if stats[1] else 0,
        null_pct=round((stats[1] or 0) / total_rows * 100, 2) if total_rows else 0,
        distinct_count=stats[2] or 0,
        min_length=stats[3] or 0,
        max_length=stats[4] or 0,
        avg_length=round(stats[5] or 0, 1),
        max_allowed_length=field.max_length,
        length_violation_count=stats[6] or 0,
        top_values=[{"value": str(r[0]), "count": r[1]} for r in top],
    )


# Known valid values for code fields
VALID_CODES = {
    "MRTLSTTSCD": ["S", "M", "D", "W", "U", "P", "L"],
    "GNDRCD": ["M", "F", "U"],
    "MBRRLTNSHPCD": ["01", "02", "03", "04", "05", "06", "07", "08", "09",
                      "10", "11", "12", "13", "14", "15", "16", "17", "18", "19"],
    "ETHNCTYCD": ["1", "2", "3", "4", "5", "6", "7",
                   "H", "N", "U"],
    "CNTRYCD": ["US", "USA", "CA", "MX", "PR", "VI", "GU", "AS", "MP"],
    "ADRSTYPECD": ["H", "M", "W", "T", "HOME", "MAIL", "WORK", "TEMP"],
    "SRCMBRCD": ["01", "02", "03", "04", "05", "1", "2", "3", "4", "5"],
    "STPRVNCCD": [
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC", "PR", "VI", "GU", "AS", "MP",
    ],
}

# Fields known to be 100% corrupted with random words
CORRUPTED_FIELDS = {"MRTLSTTSCD", "EMPIID", "MBRSQNCNBR", "SRCMBRCD", "ADRSTYPECD", "ETHNCTYCD", "CNTRYCD"}


def _sample_values(conn: duckdb.DuckDBPyConnection, col: str, where: str, n: int = 5) -> list[str]:
    """Get up to n distinct sample values matching a WHERE condition."""
    rows = conn.execute(f"""
        SELECT DISTINCT "{col}" FROM {T} WHERE {where} LIMIT {n}
    """).fetchall()
    return [str(r[0]) for r in rows]


def _count_where(conn: duckdb.DuckDBPyConnection, where: str) -> int:
    """Count rows matching a WHERE condition."""
    result = conn.execute(f"SELECT COUNT(*) FROM {T} WHERE {where}").fetchone()
    if result is None:
        raise duckdb.Error(f"Query returned no result — the DuckDB connection or table '{T}' may be invalid. Try reloading data.")
    return result[0]


def detect_quality_issues(
    conn: duckdb.DuckDBPyConnection,
    fields: list[FieldMeta],
    target_fields: Optional[list[str]] = None,
) -> list[QualityIssue]:
    """Detect data quality issues across columns."""
    issues = []
    _res = conn.execute(f"SELECT COUNT(*) FROM {T}").fetchone()
    if _res is None:
        raise duckdb.Error(f"Table '{T}' not found — try reloading data.")
    total_rows = _res[0]

    check_fields = fields
    if target_fields:
        target_set = {f.upper() for f in target_fields}
        check_fields = [f for f in fields if f.field_name.upper() in target_set]

    for fld in check_fields:
        col = fld.field_name

        # Check blank fields containing data
        if fld.is_blank_field:
            where = f'"{col}" IS NOT NULL AND TRIM("{col}") != \'\''
            cnt = _count_where(conn, where)
            if cnt > 0:
                samples = _sample_values(conn, col, where)
                issues.append(QualityIssue(
                    field_name=col,
                    issue_type="data_in_blank_field",
                    description=f"Blank field '{col}' contains {cnt:,} non-empty values",
                    affected_count=cnt,
                    affected_pct=round(cnt / total_rows * 100, 2),
                    sample_bad_values=samples,
                    suggested_fix=f"NULL out values in '{col}' - field should be empty per spec",
                ))

        # Check invalid code values
        if col in VALID_CODES:
            valid = VALID_CODES[col]
            valid_sql = ", ".join(f"'{v.upper()}'" for v in valid)
            where = f'"{col}" IS NOT NULL AND TRIM("{col}") != \'\' AND UPPER(TRIM("{col}")) NOT IN ({valid_sql})'
            cnt = _count_where(conn, where)
            if cnt > 0:
                samples = _sample_values(conn, col, where)
                issues.append(QualityIssue(
                    field_name=col,
                    issue_type="invalid_code_value",
                    description=f"'{col}' has {cnt:,} values not in valid set {valid}",
                    affected_count=cnt,
                    affected_pct=round(cnt / total_rows * 100, 2),
                    sample_bad_values=samples,
                    suggested_fix=f"Validate '{col}' against allowed codes; route invalid to rejected/review",
                    params={"valid_values": valid},
                ))

        # Check invalid phone numbers (starting with 0 or 1)
        if fld.is_phone_field:
            where = f'"{col}" IS NOT NULL AND TRIM("{col}") != \'\' AND (LEFT("{col}", 1) = \'0\' OR LEFT("{col}", 1) = \'1\')'
            cnt = _count_where(conn, where)
            if cnt > 0:
                samples = _sample_values(conn, col, where)
                issues.append(QualityIssue(
                    field_name=col,
                    issue_type="invalid_phone_number",
                    description=f"'{col}' has {cnt:,} numbers starting with 0 or 1",
                    affected_count=cnt,
                    affected_pct=round(cnt / total_rows * 100, 2),
                    sample_bad_values=samples,
                    suggested_fix=f"US phone numbers cannot start with 0/1; flag for review or correction",
                ))

        # Check length violations
        if not fld.is_blank_field:
            where = f'"{col}" IS NOT NULL AND LENGTH("{col}") > {fld.max_length}'
            cnt = _count_where(conn, where)
            if cnt > 0:
                samples = _sample_values(conn, col, where)
                issues.append(QualityIssue(
                    field_name=col,
                    issue_type="length_violation",
                    description=f"'{col}' has {cnt:,} values exceeding max length {fld.max_length}",
                    affected_count=cnt,
                    affected_pct=round(cnt / total_rows * 100, 2),
                    sample_bad_values=samples,
                    suggested_fix=f"Truncate or flag values exceeding {fld.max_length} chars",
                    params={"max_length": fld.max_length},
                ))

        # Check format mismatch for numeric code fields with values out of range
        if fld.is_code_field and col in VALID_CODES:
            valid = VALID_CODES[col]
            # If all valid values are numeric, check for out-of-range numeric values
            if all(v.isdigit() for v in valid):
                max_valid = max(int(v) for v in valid)
                where = f'"{col}" IS NOT NULL AND TRIM("{col}") != \'\' AND TRY_CAST("{col}" AS INTEGER) IS NOT NULL AND CAST("{col}" AS INTEGER) > {max_valid}'
                cnt = _count_where(conn, where)
                if cnt > 0:
                    samples = _sample_values(conn, col, where)
                    issues.append(QualityIssue(
                        field_name=col,
                        issue_type="format_mismatch",
                        description=f"'{col}' has {cnt:,} numeric values outside expected range (01-{max_valid:02d})",
                        affected_count=cnt,
                        affected_pct=round(cnt / total_rows * 100, 2),
                        sample_bad_values=samples,
                        suggested_fix=f"Map numeric values to standard codes or flag for review",
                    ))

        # Check corrupted fields: random words in code/ID fields
        # Works for any dataset - checks code fields and known-corrupted fields
        is_id_field = col.endswith("ID") or col.endswith("NBR")
        if (fld.is_code_field or is_id_field or col in CORRUPTED_FIELDS) and col not in VALID_CODES:
            where = f""""{col}" IS NOT NULL AND TRIM("{col}") != '' AND regexp_matches("{col}", '[a-z]{{3,}}')"""
            cnt = _count_where(conn, where)
            if cnt > 0:
                pct = round(cnt / total_rows * 100, 2)
                samples = _sample_values(conn, col, where)
                issues.append(QualityIssue(
                    field_name=col,
                    issue_type="corrupted_data",
                    description=f"'{col}' contains {cnt:,} random word values instead of valid codes/IDs",
                    affected_count=cnt,
                    affected_pct=pct,
                    sample_bad_values=samples,
                    suggested_fix=f"Field appears corrupted; NULL out and flag for data source investigation",
                ))

    return issues

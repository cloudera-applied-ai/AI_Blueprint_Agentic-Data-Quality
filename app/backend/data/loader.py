"""DuckDB data loading and query execution."""

import duckdb

import config
from data.metadata import FieldMeta, get_column_names


def create_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:")


def load_data(
    conn: duckdb.DuckDBPyConnection,
    data_path: str,
    fields: list[FieldMeta],
) -> int:
    """Load pipe-delimited file into DuckDB. Returns row count."""
    col_names = get_column_names(fields)
    names_sql = ", ".join(f"'{c}'" for c in col_names)

    conn.execute(f"""
        CREATE TABLE {config.TABLE_NAME} AS
        SELECT * FROM read_csv(
            '{data_path}',
            delim='|',
            header=false,
            all_varchar=true,
            names=[{names_sql}],
            strict_mode=false
        )
    """)

    result = conn.execute(f"SELECT COUNT(*) FROM {config.TABLE_NAME}").fetchone()
    return result[0]


def run_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
) -> dict:
    """Execute a read-only SQL query with safety checks.

    Returns dict with 'columns' and 'rows' keys.
    """
    stripped = sql.strip().rstrip(";").strip()
    upper = stripped.upper()

    # Only allow SELECT and WITH (CTEs)
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("Only SELECT queries are allowed.")

    # Block destructive keywords
    for kw in ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"]:
        if kw in upper.split():
            raise ValueError(f"Keyword '{kw}' is not allowed in queries.")

    # Auto-add LIMIT if not present
    if "LIMIT" not in upper:
        stripped = f"{stripped} LIMIT {config.QUERY_ROW_LIMIT}"

    result = conn.execute(stripped)
    columns = [desc[0] for desc in result.description]
    rows = result.fetchall()

    return {
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
    }

"""
agents/tools/db_query.py — SQLite database query tool.

Cho phép agent query SQLite databases để lấy data.
Chỉ cho phép SELECT (read-only) để an toàn.
"""

import sqlite3
from pathlib import Path

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger(__name__)

# Default DB path — có thể override
DEFAULT_DB_PATH = "data/nexus.db"


@tool
def query_database(sql: str, db_path: str = DEFAULT_DB_PATH) -> str:
    """Execute a read-only SQL query on the SQLite database.

    Only SELECT statements are allowed for safety.

    Args:
        sql: SQL SELECT query
        db_path: Path to SQLite database file

    Returns:
        Query results as formatted string, or error message
    """
    logger.info("DB query", sql=sql[:100])

    # Security: chỉ cho phép SELECT
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return "Error: Only SELECT queries are allowed"

    db_file = Path(db_path)
    if not db_file.exists():
        return f"Database not found: {db_path}"

    try:
        with sqlite3.connect(str(db_file)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchmany(50)  # max 50 rows

            if not rows:
                return "No results"

            # Format thành table
            headers = [d[0] for d in cursor.description]
            lines = [" | ".join(headers)]
            lines.append("-" * len(lines[0]))
            for row in rows:
                lines.append(" | ".join(str(v) for v in row))

            if len(rows) == 50:
                lines.append("... (limited to 50 rows)")

            return "\n".join(lines)

    except sqlite3.Error as e:
        logger.error("DB query failed", error=str(e))
        return f"Query error: {e}"

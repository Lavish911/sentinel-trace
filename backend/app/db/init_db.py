from pathlib import Path
from typing import Dict, Optional, Tuple
import sqlite3
from backend.app.core.config import settings

ST_SCHEMA_V1_DIGEST_SQL = """
SELECT sha256_hex(
    'ST-SCHEMA-V1|' || COALESCE(
        (
            SELECT group_concat(
                '4:type=S' || CAST(length(CAST(type AS BLOB)) AS TEXT) || ':' || type || ';'
                || '4:name=S' || CAST(length(CAST(name AS BLOB)) AS TEXT) || ':' || name || ';'
                || '8:tbl_name=S' || CAST(length(CAST(tbl_name AS BLOB)) AS TEXT) || ':' || tbl_name || ';'
                || '3:sql=S' || CAST(length(CAST(sql AS BLOB)) AS TEXT) || ':' || sql || ';',
                ''
            )
            FROM (
                SELECT type, name, tbl_name, sql
                FROM sqlite_master
                WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
                ORDER BY type ASC, name ASC, tbl_name ASC
            )
        ),
        ''
    )
);
"""


def compute_schema_digest(connection: sqlite3.Connection) -> str:
    """Compute the deterministic, order-independent ST-SCHEMA-V1 digest."""
    cursor = connection.execute(ST_SCHEMA_V1_DIGEST_SQL)
    row = cursor.fetchone()
    return str(row[0]) if row and row[0] is not None else ""


def get_schema_counts(connection: sqlite3.Connection) -> Tuple[int, int]:
    """Return counts of operational tables and triggers in the database."""
    n_tables = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    n_triggers = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'"
    ).fetchone()[0]
    return int(n_tables), int(n_triggers)


def verify_schema(connection: sqlite3.Connection) -> Dict[str, object]:
    """Verify current database schema against the provisional approved baseline."""
    n_tables, n_triggers = get_schema_counts(connection)
    digest = compute_schema_digest(connection)
    verified = digest == settings.EXPECTED_SCHEMA_SHA256 and (
        n_tables,
        n_triggers,
    ) == (12, 24)

    return {
        "baseline": settings.SCHEMA_BASELINE,
        "table_count": n_tables,
        "trigger_count": n_triggers,
        "expected_table_count": 12,
        "expected_trigger_count": 24,
        "schema_digest": digest,
        "expected_schema_digest": settings.EXPECTED_SCHEMA_SHA256,
        "verified": verified,
    }


def initialize_database(
    connection: sqlite3.Connection,
    ops_sql_path: Optional[Path] = None,
    trigs_sql_path: Optional[Path] = None,
) -> Dict[str, object]:
    """Initialize SQLite database with approved ARCH-ST-010.2 schema and triggers."""
    ops_path = ops_sql_path or settings.OPS_SQL_PATH
    trigs_path = trigs_sql_path or settings.TRIGS_SQL_PATH

    if not ops_path.exists():
        raise FileNotFoundError(f"Operational schema file not found: {ops_path}")
    if not trigs_path.exists():
        raise FileNotFoundError(f"Trigger suite file not found: {trigs_path}")

    ops_sql = ops_path.read_text(encoding="utf-8")
    trigs_sql = trigs_path.read_text(encoding="utf-8")

    connection.executescript(ops_sql)
    connection.executescript(trigs_sql)

    return verify_schema(connection)


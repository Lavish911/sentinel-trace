from pathlib import Path
from typing import Dict, Optional, Tuple
import sqlite3
from backend.app.core.config import settings
from db.engine import compute_schema_digest, EXPECTED_SCHEMA_DIGEST


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
    """Verify current database schema against the canonical ARCH-ST-010.3 baseline."""
    n_tables, n_triggers = get_schema_counts(connection)
    digest = compute_schema_digest(connection)
    verified = digest == settings.EXPECTED_SCHEMA_SHA256 and (
        n_tables,
        n_triggers,
    ) == (12, 27)

    return {
        "baseline": settings.SCHEMA_BASELINE,
        "table_count": n_tables,
        "trigger_count": n_triggers,
        "expected_table_count": 12,
        "expected_trigger_count": 27,
        "schema_digest": digest,
        "expected_schema_digest": settings.EXPECTED_SCHEMA_SHA256,
        "verified": verified,
    }


def initialize_database(
    connection: sqlite3.Connection,
    ops_sql_path: Optional[Path] = None,
    trigs_sql_path: Optional[Path] = None,
) -> Dict[str, object]:
    """Initialize SQLite database with canonical ARCH-ST-010.3 schema and triggers."""
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

import sqlite3
from contextlib import contextmanager
from typing import Generator, Optional
from backend.app.core.config import settings
from backend.app.db.udfs import register_udfs


def create_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with required PRAGMAs and UDFs."""
    target_path = db_path if db_path is not None else settings.DATABASE_PATH
    connection = sqlite3.connect(target_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row

    # Enforce database integrity and trigger PRAGMAs
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA recursive_triggers = ON;")
    connection.execute("PRAGMA trusted_schema = ON;")

    if target_path != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA synchronous = NORMAL;")

    # Register deterministic UDFs required by schema check constraints and triggers
    register_udfs(connection)

    return connection


@contextmanager
def get_db_context(
    db_path: Optional[str] = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite connections ensuring proper closure."""
    conn = create_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency for accessing database connection per request."""
    with get_db_context() as conn:
        yield conn


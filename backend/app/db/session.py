import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
from backend.app.core.config import settings
from db.engine import register_udfs, open_operational_db


def create_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with canonical ARCH-ST-010.3 PRAGMAs and UDFs."""
    target_path = db_path if db_path is not None else settings.DATABASE_PATH
    target = Path(target_path)

    # If target does not exist and root operational.db exists, fallback
    if target_path != ":memory:" and not target.exists():
        root_alt = Path(__file__).resolve().parent.parent.parent.parent / "operational.db"
        if root_alt.exists():
            target_path = str(root_alt)

    connection = sqlite3.connect(str(target_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row

    # Enforce canonical ARCH-ST-010.3 UDFs and PRAGMAs
    register_udfs(connection)

    if target_path != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA synchronous = NORMAL;")

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

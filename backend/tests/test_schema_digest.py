import re
import sqlite3
import pytest
from backend.app.core.config import settings
from backend.app.db.session import create_connection
from backend.app.db.init_db import (
    compute_schema_digest,
    get_schema_counts,
    verify_schema,
    initialize_database,
)


def test_schema_object_counts(in_memory_db: sqlite3.Connection):
    """Verify that ARCH-ST-010.3 builds exactly 12 STRICT tables and 27 triggers."""
    n_tables, n_triggers = get_schema_counts(in_memory_db)
    assert n_tables == 12, f"Expected 12 tables, got {n_tables}"
    assert n_triggers == 27, f"Expected 27 triggers, got {n_triggers}"


def test_schema_digest_matches_baseline_constant(in_memory_db: sqlite3.Connection):
    """Verify that computed ST-SCHEMA-V1 digest matches §6.3 constant byte-for-byte."""
    digest = compute_schema_digest(in_memory_db)
    assert digest == settings.EXPECTED_SCHEMA_SHA256
    assert digest == "2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab"


def test_verify_schema_helper(in_memory_db: sqlite3.Connection):
    """Verify that verify_schema returns verified: True on compliant database."""
    res = verify_schema(in_memory_db)
    assert res["verified"] is True
    assert res["baseline"] == "ARCH-ST-010.3"
    assert res["table_count"] == 12
    assert res["trigger_count"] == 27


def test_digest_order_independence():
    """Verify that ST-SCHEMA-V1 digest is strictly order-independent across DDL ordering."""
    ops_sql = settings.OPS_SQL_PATH.read_text(encoding="utf-8")
    trigs_sql = settings.TRIGS_SQL_PATH.read_text(encoding="utf-8")

    # DB A: Forward document order
    db_a = create_connection(":memory:")
    db_a.executescript(ops_sql)
    db_a.executescript(trigs_sql)
    digest_a = compute_schema_digest(db_a)

    # DB B: Reversed table creation order
    db_b = create_connection(":memory:")
    table_stmts = [
        m.group(0) for m in re.finditer(r"(?s)CREATE TABLE.*?\) STRICT;", ops_sql)
    ][::-1]

    db_b.execute("PRAGMA foreign_keys = OFF;")
    pending = list(table_stmts)
    while pending:
        progress = False
        for stmt in list(pending):
            try:
                db_b.execute(stmt)
                pending.remove(stmt)
                progress = True
            except Exception:
                pass
        if not progress:
            pytest.fail("Cannot create tables in reversed order")

    db_b.execute("PRAGMA foreign_keys = ON;")
    db_b.executescript(trigs_sql)
    digest_b = compute_schema_digest(db_b)

    assert digest_a == digest_b, "ST-SCHEMA-V1 digest must be order-independent"
    assert digest_a == settings.EXPECTED_SCHEMA_SHA256

"""
SENTINEL//TRACE — SQLite Database Engine, UDF Registration & Schema Verification
================================================================================
Provides deterministic SQLite connection management for both `operational.db`
(12 STRICT tables, 27 triggers) and `ground_truth.db` (4 STRICT tables),
registers the required deterministic SQLite UDFs (`sha256_hex`, `is_canonical_json`),
and verifies the `ST-SCHEMA-V1` schema digest on connection open.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
OPS_SQL_PATH = REPO_ROOT / "archive" / "verify-0103" / "ops_0103.sql"
TRIGS_SQL_PATH = REPO_ROOT / "archive" / "verify-0103" / "trigs_0103.sql"

EXPECTED_SCHEMA_DIGEST = "2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab"

GROUND_TRUTH_DDL = """
PRAGMA foreign_keys = ON;
PRAGMA trusted_schema = ON;

CREATE TABLE ground_truth_rings (
    ring_id TEXT PRIMARY KEY,
    ring_archetype TEXT NOT NULL,
    observability_mode TEXT NOT NULL,
    claim_count INTEGER NOT NULL,
    entity_count INTEGER NOT NULL,
    CHECK (ring_id GLOB 'RING-2026-[0-9][0-9][0-9]'),
    CHECK (observability_mode IN ('FULL_OBSERVABLE','PARTIAL_MISSING_EDGES_YF_NEG_4'))
) STRICT;

CREATE TABLE ground_truth_claim_labels (
    claim_id TEXT PRIMARY KEY,
    is_fraud INTEGER NOT NULL,
    ring_id TEXT REFERENCES ground_truth_rings(ring_id),
    scenario_code TEXT NOT NULL,
    CHECK (claim_id GLOB 'CLM-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (is_fraud IN (0, 1))
) STRICT;

CREATE TABLE ground_truth_entity_labels (
    entity_key TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    is_fraud_participant INTEGER NOT NULL,
    ring_id TEXT REFERENCES ground_truth_rings(ring_id),
    CHECK (entity_type IN ('CLAIMANT','PROVIDER')),
    CHECK (is_fraud_participant IN (0, 1))
) STRICT;

CREATE TABLE ground_truth_missing_edges (
    missing_edge_id TEXT PRIMARY KEY,
    ring_id TEXT NOT NULL REFERENCES ground_truth_rings(ring_id),
    edge_type TEXT NOT NULL,
    canonical_src_key TEXT NOT NULL,
    canonical_dst_key TEXT NOT NULL,
    planted_reason TEXT NOT NULL,
    CHECK (missing_edge_id GLOB 'GTME-2026-[0-9][0-9][0-9][0-9]'),
    CHECK (canonical_src_key < canonical_dst_key)
) STRICT;
"""


def sha256_hex(val: Any) -> str | None:
    """Deterministic SHA-256 lowercase hex digest over UTF-8 bytes."""
    if val is None:
        return None
    if isinstance(val, bytes):
        return hashlib.sha256(val).hexdigest()
    return hashlib.sha256(str(val).encode("utf-8")).hexdigest()


def is_canonical_json(s: Any) -> int:
    """
    Validates that `s` is a canonical JSON object string with UTF-8 sorted keys,
    zero whitespace, raw UTF-8 characters (ensure_ascii=False), no duplicate keys
    at any depth, and no non-finite numbers (NaN, Infinity, -Infinity).
    """
    if not isinstance(s, str) or not s:
        return 0
    try:
        def _no_dup(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            d: dict[str, Any] = {}
            for k, v in pairs:
                if k in d:
                    raise ValueError("duplicate key")
                d[k] = v
            return d

        def _no_const(c: str) -> None:
            raise ValueError(f"non-finite constant: {c}")

        obj = json.loads(s, object_pairs_hook=_no_dup, parse_constant=_no_const)
        if not isinstance(obj, dict):
            return 0
        canonical = json.dumps(
            obj,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        return 1 if canonical == s else 0
    except Exception:
        return 0


def canonical_json_str(obj: dict[str, Any]) -> str:
    """Serializes a dictionary into canonical JSON per §6.5."""
    return json.dumps(
        obj,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def register_udfs(conn: sqlite3.Connection) -> None:
    """Registers deterministic UDFs and enables SQLite integrity pragmas."""
    conn.create_function("sha256_hex", 1, sha256_hex, deterministic=True)
    conn.create_function("is_canonical_json", 1, is_canonical_json, deterministic=True)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA recursive_triggers = ON;")
    conn.execute("PRAGMA trusted_schema = ON;")


def compute_schema_digest(conn: sqlite3.Connection) -> str:
    """Computes the ST-SCHEMA-V1 digest over sqlite_master tables and triggers."""
    rows = conn.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'trigger')
          AND name NOT LIKE 'sqlite_%'
          AND sql IS NOT NULL
        ORDER BY type ASC, name ASC, tbl_name ASC
        """
    ).fetchall()
    parts = ["ST-SCHEMA-V1|"]
    for obj_type, name, tbl_name, sql in rows:
        for k, v in (("type", obj_type), ("name", name), ("tbl_name", tbl_name), ("sql", sql)):
            kb = k.encode("utf-8")
            vb = v.encode("utf-8")
            parts.append(f"{len(kb)}:{k}=S{len(vb)}:{v};")
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


def open_operational_db(
    db_path: str | Path = ":memory:",
    create_schema: bool = True,
    verify_digest: bool = True,
) -> sqlite3.Connection:
    """Opens an operational database connection, initializes DDL/triggers if requested, and verifies digest."""
    conn = sqlite3.connect(str(db_path))
    register_udfs(conn)
    if create_schema:
        conn.executescript(OPS_SQL_PATH.read_text(encoding="utf-8"))
        conn.executescript(TRIGS_SQL_PATH.read_text(encoding="utf-8"))
        register_udfs(conn)
    if verify_digest:
        actual = compute_schema_digest(conn)
        if actual != EXPECTED_SCHEMA_DIGEST:
            conn.close()
            raise RuntimeError(
                f"ERR_SCHEMA_DIGEST_MISMATCH: expected {EXPECTED_SCHEMA_DIGEST}, got {actual}"
            )
    return conn


def open_ground_truth_db(
    db_path: str | Path = ":memory:",
    create_schema: bool = True,
) -> sqlite3.Connection:
    """Opens a quarantined ground-truth database connection."""
    conn = sqlite3.connect(str(db_path))
    register_udfs(conn)
    if create_schema:
        conn.executescript(GROUND_TRUTH_DDL)
        register_udfs(conn)
    return conn


def compute_database_checksum(conn: sqlite3.Connection) -> str:
    """
    Computes a deterministic ST-DUMP-V1 SHA-256 digest over all user tables and rows
    ordered by table name and primary key / row contents.
    """
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC"
        ).fetchall()
    ]
    hasher = hashlib.sha256(b"ST-DUMP-V1|")
    for tbl in tables:
        hasher.update(f"TABLE:{tbl}|".encode("utf-8"))
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
        order_clause = ", ".join(cols)
        for row in conn.execute(f"SELECT * FROM {tbl} ORDER BY {order_clause}").fetchall():
            row_repr = json.dumps(list(row), ensure_ascii=False, separators=(",", ":"))
            hasher.update(row_repr.encode("utf-8") + b"\n")
    return hasher.hexdigest()

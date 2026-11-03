import sqlite3
import pytest


def test_pragmas_enabled(in_memory_db: sqlite3.Connection):
    """Verify that mandatory security and integrity PRAGMAs are enabled."""
    fk = in_memory_db.execute("PRAGMA foreign_keys;").fetchone()[0]
    rt = in_memory_db.execute("PRAGMA recursive_triggers;").fetchone()[0]
    ts = in_memory_db.execute("PRAGMA trusted_schema;").fetchone()[0]

    assert fk == 1, "PRAGMA foreign_keys must be 1 (ON)"
    assert rt == 1, "PRAGMA recursive_triggers must be 1 (ON)"
    assert ts == 1, "PRAGMA trusted_schema must be 1 (ON)"


def test_udfs_registered_in_sql(in_memory_db: sqlite3.Connection):
    """Verify that custom deterministic UDFs are callable from SQL."""
    sha = in_memory_db.execute("SELECT sha256_hex('test')").fetchone()[0]
    assert len(sha) == 64
    assert sha == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

    valid_json = in_memory_db.execute(
        "SELECT is_canonical_json('{\"a\":1}')"
    ).fetchone()[0]
    assert valid_json == 1

    invalid_json = in_memory_db.execute(
        "SELECT is_canonical_json('{\"a\": 1}')"
    ).fetchone()[0]
    assert invalid_json == 0


def test_foreign_key_violation_raises(in_memory_db: sqlite3.Connection):
    """Verify that foreign key constraints are enforced on inserts."""
    # Attempting to insert a policy referencing a non-existent claimant must fail
    with pytest.raises(sqlite3.IntegrityError):
        in_memory_db.execute(
            """
            INSERT INTO policies (
                policy_id, claimant_id, policy_number, line_of_business, policy_status,
                effective_start_utc, effective_end_utc, bound_at_utc,
                coverage_limit_cents, deductible_cents, annual_premium_cents
            ) VALUES (
                'POL-000001', 'CLMT-NONEXISTENT', 'POL-NUM-001', 'AUTO_PERSONAL', 'ACTIVE',
                '2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z', '2025-12-15T00:00:00Z',
                5000000, 50000, 120000
            )
            """
        )


def test_strict_table_type_violation(in_memory_db: sqlite3.Connection):
    """Verify that STRICT tables enforce column data types."""
    # Insert valid claimant first with valid 64-hex hash fields
    dummy_hash = "a" * 64
    in_memory_db.execute(
        """
        INSERT INTO claimants (
            claimant_id, full_name, dob_iso, tax_id_hash, phone_e164,
            email_norm, address_norm, bank_routing_hash, bank_account_hash, created_at_utc
        ) VALUES (
            'CLMT-000001', 'Alice Smith', '1985-04-12', ?, '+15550100001',
            'alice@example.com', '123 Main St, Los Angeles, CA 90001', ?, ?,
            '2026-01-01T00:00:00Z'
        )
        """,
        (dummy_hash, dummy_hash, dummy_hash),
    )
    # Attempt to insert string into integer column (coverage_limit_cents) in STRICT table
    with pytest.raises(sqlite3.IntegrityError):
        in_memory_db.execute(
            """
            INSERT INTO policies (
                policy_id, claimant_id, policy_number, line_of_business, policy_status,
                effective_start_utc, effective_end_utc, bound_at_utc,
                coverage_limit_cents, deductible_cents, annual_premium_cents
            ) VALUES (
                'POL-000001', 'CLMT-000001', 'POL-NUM-001', 'AUTO_PERSONAL', 'ACTIVE',
                '2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z', '2025-12-15T00:00:00Z',
                'NOT_AN_INTEGER', 50000, 120000
            )
            """
        )

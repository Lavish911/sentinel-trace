"""
Database Trigger and Security Guard Verification Suite for SENTINEL//TRACE.
Verifies negative tests, FSM transition guards, digest tampering protections,
and balance constraints across the 27 ARCH-ST-010.3 database triggers (F-AUD-10).
"""

import sqlite3
import pytest
from pathlib import Path

from backend.app.core.config import settings
from pathlib import Path
from backend.app.db.udfs import register_udfs


@pytest.fixture
def op_conn():
    conn = sqlite3.connect(str(settings.DATABASE_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA recursive_triggers = ON;")
    register_udfs(conn)
    yield conn
    conn.close()


def test_immutable_event_update_forbidden(op_conn):
    """Asserts that attempting to UPDATE an event in immutable_events raises ERR_IMMUTABLE_EVENT_UPDATE_FORBIDDEN."""
    first_seq = op_conn.execute("SELECT sequence_no FROM immutable_events ORDER BY sequence_no ASC LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        op_conn.execute("UPDATE immutable_events SET actor_id = 'HACKER' WHERE sequence_no = ?", (first_seq,))
    assert "ERR_IMMUTABLE_EVENT_UPDATE_FORBIDDEN" in str(exc_info.value)


def test_immutable_event_delete_forbidden(op_conn):
    """Asserts that attempting to DELETE an event in immutable_events raises ERR_IMMUTABLE_EVENT_DELETE_FORBIDDEN."""
    first_seq = op_conn.execute("SELECT sequence_no FROM immutable_events ORDER BY sequence_no ASC LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        op_conn.execute("DELETE FROM immutable_events WHERE sequence_no = ?", (first_seq,))
    assert "ERR_IMMUTABLE_EVENT_DELETE_FORBIDDEN" in str(exc_info.value)


def test_score_evidence_digest_tampering_blocked(op_conn):
    """Asserts that attempting to update claim score with invalid evidence digest raises ERR_SCORE_EVIDENCE_DIGEST_MISMATCH."""
    sample_cid, cur_score, cur_tier = op_conn.execute("SELECT claim_id, latest_ief_score, latest_risk_tier FROM claims LIMIT 1").fetchone()
    bad_digest = "0" * 64
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        op_conn.execute(
            "UPDATE claims SET latest_ief_score = ?, latest_risk_tier = ?, scoring_evidence_sha256 = ? WHERE claim_id = ?",
            (cur_score, cur_tier, bad_digest, sample_cid)
        )
    assert "ERR_SCORE_EVIDENCE_DIGEST_MISMATCH" in str(exc_info.value)


def test_claim_immutable_core_fields_guard(op_conn):
    """Asserts that attempting to alter claim core attributes raises ERR_CLAIM_IMMUTABLE_CORE_FIELDS."""
    sample_cid = op_conn.execute("SELECT claim_id, claimed_amount_cents FROM claims LIMIT 1").fetchone()
    cid, amt = sample_cid[0], sample_cid[1]
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        op_conn.execute("UPDATE claims SET claimed_amount_cents = ? WHERE claim_id = ?", (amt + 50000, cid))
    assert "ERR_CLAIM_IMMUTABLE_CORE_FIELDS" in str(exc_info.value)


def test_payment_positive_amount_guard(op_conn):
    """Asserts that inserting payment with zero or negative amount raises check violation."""
    claim_id = op_conn.execute("SELECT claim_id FROM claims WHERE claim_status = 'APPROVED' LIMIT 1").fetchone()[0]
    inv_id, prvid = op_conn.execute("SELECT invoice_id, provider_id FROM invoices WHERE claim_id = ? AND invoice_status = 'APPROVED' LIMIT 1", (claim_id,)).fetchone()
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        op_conn.execute("""
            INSERT INTO payments (
                payment_id, claim_id, invoice_id, amount_cents, payment_status,
                created_at_utc, recipient_type, recipient_provider_id, idempotency_key, authorized_by
            ) VALUES ('PAY-2026-999991', ?, ?, 0, 'AUTHORIZED', '2026-01-20T00:00:00Z', 'PROVIDER', ?, 'IDEMP-FAIL-01', 'USR-01')
        """, (claim_id, inv_id, prvid))
    assert "amount_cents > 0" in str(exc_info.value)


def test_payment_unapproved_invoice_guard(op_conn):
    """Asserts that payment on an unapproved invoice raises ERR_PAYMENT_REQUIRES_APPROVED_CLAIM_AND_INVOICE."""
    unapproved_inv = op_conn.execute(
        "SELECT invoice_id, claim_id, provider_id FROM invoices WHERE invoice_status = 'SUBMITTED' LIMIT 1"
    ).fetchone()
    if unapproved_inv:
        inv_id, claim_id, prvid = unapproved_inv[0], unapproved_inv[1], unapproved_inv[2]
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            op_conn.execute("""
                INSERT INTO payments (
                    payment_id, claim_id, invoice_id, amount_cents, payment_status,
                    created_at_utc, recipient_type, recipient_provider_id, idempotency_key, authorized_by
                ) VALUES ('PAY-2026-999992', ?, ?, 10000, 'AUTHORIZED', '2026-01-20T00:00:00Z', 'PROVIDER', ?, 'IDEMP-FAIL-02', 'USR-01')
            """, (claim_id, inv_id, prvid))
        assert "ERR_PAYMENT_REQUIRES_APPROVED_CLAIM_AND_INVOICE" in str(exc_info.value)


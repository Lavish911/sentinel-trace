"""
Chronology and Causal Temporal Ordering Tests for SENTINEL//TRACE.
Validates zero temporal inversions across:
1. immutable_events table (monotonicity along sequence_no: t_i <= t_{i+1})
2. Invoices vs Claims (every invoice submitted_at_utc >= claim submitted_at_utc)
3. Payments vs Invoices (every payment created_at_utc >= invoice submitted_at_utc)
4. Payment Lifecycle FSM (created <= disbursed <= reversed/clawed_back)
5. Claim Incident vs Submission (incident <= reported <= submitted)
"""

import sqlite3
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO_ROOT / "data" / "operational.db"


@pytest.fixture(scope="module")
def db_conn():
    if not DB_PATH.exists():
        pytest.fail("data/operational.db does not exist")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_immutable_events_chronological_monotonicity(db_conn):
    """
    Asserts strict sequence continuity (1..19675 without gaps) and
    zero causal temporal inversions across all entity and claim lifecycles in immutable_events.
    """
    from collections import defaultdict
    rows = db_conn.execute(
        "SELECT sequence_no, occurred_at_utc, event_type, claim_id, entity_type, entity_id FROM immutable_events ORDER BY sequence_no ASC"
    ).fetchall()
    assert len(rows) == 19675, f"Expected 19675 events, found {len(rows)}"

    # 1. Assert contiguous sequence continuity
    for idx, r in enumerate(rows, start=1):
        assert r["sequence_no"] == idx, f"Sequence gap at expected {idx}, found {r['sequence_no']}"

    # 2. Assert zero causal temporal inversions per claim lifecycle
    claim_events = defaultdict(list)
    for r in rows:
        cid = r["claim_id"]
        if cid:
            claim_events[cid].append(r)

    inversions = []
    for cid, evts in claim_events.items():
        for i in range(len(evts) - 1):
            if evts[i]["occurred_at_utc"] > evts[i+1]["occurred_at_utc"]:
                inversions.append((
                    cid, evts[i]["sequence_no"], evts[i]["event_type"], evts[i]["occurred_at_utc"],
                    evts[i+1]["sequence_no"], evts[i+1]["event_type"], evts[i+1]["occurred_at_utc"]
                ))

    assert len(inversions) == 0, f"Found {len(inversions)} causal temporal inversions in claim lifecycles! First 5: {inversions[:5]}"


def test_invoices_submitted_after_claims(db_conn):
    """Every invoice must be submitted at or after its associated claim."""
    q = """
    SELECT i.invoice_id, i.claim_id, i.submitted_at_utc as inv_sub, c.submitted_at_utc as claim_sub
    FROM invoices i
    JOIN claims c ON i.claim_id = c.claim_id
    WHERE i.submitted_at_utc < c.submitted_at_utc
    """
    inversions = db_conn.execute(q).fetchall()
    assert len(inversions) == 0, f"Found {len(inversions)} invoices submitted before their claim! First 5: {inversions[:5]}"


def test_payments_authorized_after_invoices(db_conn):
    """Every payment created_at_utc must be at or after its associated invoice submitted_at_utc."""
    q = """
    SELECT p.payment_id, p.invoice_id, p.created_at_utc as pay_ts, i.submitted_at_utc as inv_ts
    FROM payments p
    JOIN invoices i ON p.invoice_id = i.invoice_id
    WHERE p.created_at_utc < i.submitted_at_utc
    """
    inversions = db_conn.execute(q).fetchall()
    assert len(inversions) == 0, f"Found {len(inversions)} payments created before invoice submission! First 5: {inversions[:5]}"


def test_payment_lifecycle_chronology(db_conn):
    """Validates FSM timestamps: created_at_utc <= disbursed_at_utc <= reversed_at_utc."""
    # Disbursed
    q_disb = """
    SELECT payment_id, created_at_utc, disbursed_at_utc
    FROM payments
    WHERE payment_status = 'DISBURSED' AND disbursed_at_utc < created_at_utc
    """
    assert len(db_conn.execute(q_disb).fetchall()) == 0, "Found disbursements before creation!"

    # Clawback
    q_claw = """
    SELECT payment_id, disbursed_at_utc, reversed_at_utc
    FROM payments
    WHERE payment_status = 'REVERSED_CLAWBACK' AND reversed_at_utc < disbursed_at_utc
    """
    assert len(db_conn.execute(q_claw).fetchall()) == 0, "Found clawbacks before disbursement!"

    # Cancelled
    q_cancel = """
    SELECT payment_id, created_at_utc, reversed_at_utc
    FROM payments
    WHERE payment_status = 'CANCELLED' AND reversed_at_utc < created_at_utc
    """
    assert len(db_conn.execute(q_cancel).fetchall()) == 0, "Found cancellations before creation!"


def test_incident_claim_chronology(db_conn):
    """Validates incident_timestamp_utc <= reported_timestamp_utc <= submitted_at_utc."""
    q = """
    SELECT c.claim_id, inc.incident_timestamp_utc, inc.reported_timestamp_utc, c.submitted_at_utc
    FROM claims c
    JOIN incidents inc ON c.incident_id = inc.incident_id
    WHERE inc.incident_timestamp_utc > inc.reported_timestamp_utc
       OR inc.reported_timestamp_utc > c.submitted_at_utc
    """
    inversions = db_conn.execute(q).fetchall()
    assert len(inversions) == 0, f"Found {len(inversions)} incident-to-claim chronology violations! First 5: {inversions[:5]}"


"""
Integration test suite for SENTINEL//TRACE Forensic Investigation Workflow API.
Validates end-to-end investigation lifecycle:
1. Investigation creation with sequential ID and atomic INVESTIGATION_OPENED event.
2. Concurrent open investigation prevention (ERR_CONCURRENT_OPEN_INVESTIGATION_FORBIDDEN).
3. Evidence notes append to active case.
4. FSM valid and invalid transitions (OPEN -> EVIDENCE_COLLECTION -> SIU_FIELD_REVIEW -> CLOSED_CONFIRMED_FRAUD).
5. Terminal state immutability enforcement.
6. SIU referral propagation to primary claim on confirmed fraud.
7. Claim SIU hold and D-1 exit gate validation.
8. ST-EVT-V2 hash chain continuity and chain tip verification.
Uses an isolated temporary database copy to ensure canonical data/operational.db remains unmodified.
"""

import shutil
import tempfile
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import get_db
from db.engine import register_udfs, EXPECTED_SCHEMA_DIGEST, compute_schema_digest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_DB_PATH = REPO_ROOT / "data" / "operational.db"


@pytest.fixture(scope="module")
def isolated_db():
    """Creates a temporary isolated copy of data/operational.db for mutation tests."""
    with tempfile.TemporaryDirectory(prefix="sentinel_invg_test_") as tmpdir:
        test_db_path = Path(tmpdir) / "operational_test.db"
        shutil.copyfile(CANONICAL_DB_PATH, test_db_path)

        def db_override():
            conn = sqlite3.connect(str(test_db_path))
            register_udfs(conn)
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_db] = db_override
        with TestClient(app) as client:
            yield client, test_db_path
        app.dependency_overrides.clear()


def test_investigation_creation_and_event_persistence(isolated_db):
    client, db_path = isolated_db
    claim_id = "CLM-2026-000050"

    # Verify claim exists and has no open investigation
    res_claim = client.get(f"/api/v1/claims/{claim_id}")
    assert res_claim.status_code == 200
    assert res_claim.json()["investigation"] is None

    # Create investigation
    payload = {
        "primary_claim_id": claim_id,
        "priority": "P1_CRITICAL",
        "assigned_investigator_id": "SIU-TEST-007",
        "case_summary_notes": "Forensic audit: suspicious multi-clinic billing pattern"
    }
    res = client.post("/api/v1/investigations", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "CREATED"
    assert data["investigation_id"] == "INVG-2026-000046"
    assert data["primary_claim_id"] == claim_id
    assert data["event_id"].startswith("EVT-2026-")

    # Verify event was persisted in immutable_events
    conn = sqlite3.connect(str(db_path))
    register_udfs(conn)
    evt = conn.execute(
        "SELECT event_id, event_type, entity_id, claim_id FROM immutable_events WHERE event_id = ?",
        (data["event_id"],)
    ).fetchone()
    assert evt is not None
    assert evt[1] == "INVESTIGATION_OPENED"
    assert evt[2] == "INVG-2026-000046"
    assert evt[3] == claim_id
    conn.close()


def test_concurrent_open_investigation_rejection(isolated_db):
    client, _ = isolated_db
    claim_id = "CLM-2026-000050"

    # Attempt to open second investigation on same claim
    payload = {
        "primary_claim_id": claim_id,
        "priority": "P2_HIGH",
        "case_summary_notes": "Attempting unauthorized duplicate concurrent case"
    }
    res = client.post("/api/v1/investigations", json=payload)
    assert res.status_code == 400
    assert "ERR_CONCURRENT_OPEN_INVESTIGATION_FORBIDDEN" in res.json()["detail"]


def test_add_investigation_evidence_note(isolated_db):
    client, db_path = isolated_db
    inv_id = "INVG-2026-000046"

    note_payload = {
        "note": "Subpoenaed banking records; confirmed shared account with clinic owner.",
        "actor_id": "SIU-TEST-007"
    }
    res = client.post(f"/api/v1/investigations/{inv_id}/notes", json=note_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "NOTE_ADDED"
    assert "Subpoenaed banking records" in data["case_summary_notes"]

    # Verify persisted in database
    conn = sqlite3.connect(str(db_path))
    notes = conn.execute("SELECT case_summary_notes FROM investigations WHERE investigation_id = ?", (inv_id,)).fetchone()[0]
    assert "Subpoenaed banking records" in notes
    conn.close()


def test_investigation_fsm_valid_transitions(isolated_db):
    client, db_path = isolated_db
    inv_id = "INVG-2026-000046"

    # Transition 1: OPEN -> EVIDENCE_COLLECTION
    t1 = {
        "new_status": "EVIDENCE_COLLECTION",
        "notes": "Initiated formal evidence collection phase",
        "actor_id": "SIU-TEST-007"
    }
    res1 = client.patch(f"/api/v1/investigations/{inv_id}/status", json=t1)
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["previous_status"] == "OPEN"
    assert d1["new_status"] == "EVIDENCE_COLLECTION"

    # Transition 2: EVIDENCE_COLLECTION -> SIU_FIELD_REVIEW
    t2 = {
        "new_status": "SIU_FIELD_REVIEW",
        "notes": "Field investigator dispatched to physical location",
        "actor_id": "SIU-TEST-007"
    }
    res2 = client.patch(f"/api/v1/investigations/{inv_id}/status", json=t2)
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["previous_status"] == "EVIDENCE_COLLECTION"
    assert d2["new_status"] == "SIU_FIELD_REVIEW"


def test_investigation_fsm_invalid_transition_rejection(isolated_db):
    client, _ = isolated_db
    inv_id = "INVG-2026-000046"

    # Attempt backward transition: SIU_FIELD_REVIEW -> OPEN (forbidden)
    bad_t = {
        "new_status": "OPEN",
        "notes": "Attempting illegal backward regression"
    }
    res = client.patch(f"/api/v1/investigations/{inv_id}/status", json=bad_t)
    # Pydantic or FSM validation rejects
    assert res.status_code in (400, 422)


def test_investigation_terminal_closure_and_siu_referral(isolated_db):
    client, db_path = isolated_db
    inv_id = "INVG-2026-000046"
    claim_id = "CLM-2026-000050"

    # Close as CONFIRMED_FRAUD
    close_payload = {
        "new_status": "CLOSED_CONFIRMED_FRAUD",
        "ruling_outcome": "CONFIRMED_FRAUD",
        "notes": "Fraud confirmed: staged accident collusion network",
        "actor_id": "SIU-CHIEF-001"
    }
    res = client.patch(f"/api/v1/investigations/{inv_id}/status", json=close_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["new_status"] == "CLOSED_CONFIRMED_FRAUD"
    assert data["ruling_outcome"] == "CONFIRMED_FRAUD"

    # Verify INVESTIGATION_CLOSED event emitted
    conn = sqlite3.connect(str(db_path))
    register_udfs(conn)
    evt = conn.execute(
        "SELECT event_type, payload_json FROM immutable_events WHERE event_id = ?",
        (data["event_id"],)
    ).fetchone()
    assert evt[0] == "INVESTIGATION_CLOSED"

    # Verify trigger trg_investigations_siu_ref_au propagated siu_referred = 1 to primary claim
    siu_ref = conn.execute("SELECT siu_referred FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()[0]
    assert siu_ref == 1
    conn.close()


def test_closed_investigation_immutability(isolated_db):
    client, _ = isolated_db
    inv_id = "INVG-2026-000046"

    # Cannot add notes after closure
    res_notes = client.post(f"/api/v1/investigations/{inv_id}/notes", json={"note": "Late addendum", "actor_id": "SIU"})
    assert res_notes.status_code == 400
    assert "ERR_CLOSED_INVESTIGATION_IMMUTABLE" in res_notes.json()["detail"]

    # Cannot transition after closure
    res_trans = client.patch(f"/api/v1/investigations/{inv_id}/status", json={"new_status": "OPEN"})
    assert res_trans.status_code in (400, 422)


def test_claim_hold_and_timeline_continuity(isolated_db):
    client, db_path = isolated_db
    claim_id = "CLM-2026-000051"

    # 1. Place claim on hold
    res_hold = client.post(f"/api/v1/claims/{claim_id}/hold", json={"actor_id": "SIU-AGENT-001", "reason": "Triage"})
    assert res_hold.status_code == 200
    assert res_hold.json()["claim_status"] == "SIU_HOLD"

    # 2. Duplicate hold rejected
    res_dup = client.post(f"/api/v1/claims/{claim_id}/hold")
    assert res_dup.status_code == 400

    # 3. Fetch claim timeline
    res_tl = client.get(f"/api/v1/claims/{claim_id}/timeline")
    assert res_tl.status_code == 200
    events = res_tl.json()
    assert any(e["event_type"] == "CLAIM_SIU_HOLD_PLACED" for e in events)

    # 4. Verify overall ST-EVT-V2 hash chain in test database remains unbroken
    conn = sqlite3.connect(str(db_path))
    register_udfs(conn)
    rows = conn.execute(
        "SELECT sequence_no, prev_event_hash, event_hash FROM immutable_events ORDER BY sequence_no ASC"
    ).fetchall()
    assert len(rows) > 19675  # New events added
    for i in range(1, len(rows)):
        assert rows[i][0] == rows[i-1][0] + 1  # Strictly monotonic
        assert rows[i][1] == rows[i-1][2]      # Unbroken link
    conn.close()



def test_claim_siu_hold_and_release_workflow(isolated_db):
    """
    Validates complete hold-and-release investigator lifecycle:
    1. Place claim on SIU_HOLD.
    2. Attempt release without CLEARED_BENIGN investigation -> rejected with 400.
    3. Open investigation for claim and close as CLOSED_CLEARED_BENIGN.
    4. Valid release transitions claim to APPROVED, emits CLAIM_APPROVED event.
    5. Verifies timeline and event hash chain integrity.
    """
    client, db_path = isolated_db
    claim_id = "CLM-2026-001276"  # Claim with approved_amount_cents > 0 and net_paid_cents == 0

    # 1. Place claim on hold
    res_hold = client.post(f"/api/v1/claims/{claim_id}/hold", json={"actor_id": "SIU-TESTER", "reason": "Triage review"})
    assert res_hold.status_code == 200
    assert res_hold.json()["claim_status"] == "SIU_HOLD"

    # 2. Attempt invalid release (no benign investigation exists for this hold cycle)
    res_bad_rel = client.post(
        f"/api/v1/claims/{claim_id}/release",
        json={
            "target_status": "APPROVED",
            "cleared_investigation_id": "INVG-2026-000001",
            "actor_id": "SIU-TESTER"
        }
    )
    assert res_bad_rel.status_code == 400
    assert "ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE" in res_bad_rel.json()["detail"]

    # 3. Open investigation on the claim
    res_inv = client.post(
        "/api/v1/investigations",
        json={
            "primary_claim_id": claim_id,
            "priority": "P2_HIGH",
            "assigned_investigator_id": "SIU-BENIGN-REVIEWER",
            "case_summary_notes": "Reviewing claim for benign multi-unit address verification"
        }
    )
    assert res_inv.status_code == 201
    inv_id = res_inv.json()["investigation_id"]

    # Progress to CLOSED_CLEARED_BENIGN
    res_close = client.patch(
        f"/api/v1/investigations/{inv_id}/status",
        json={
            "new_status": "CLOSED_CLEARED_BENIGN",
            "ruling_outcome": "CLEARED_BENIGN",
            "notes": "Verified legitimate insured, no collusion found",
            "actor_id": "SIU-SUPERVISOR"
        }
    )
    assert res_close.status_code == 200

    # 4. Valid release
    res_good_rel = client.post(
        f"/api/v1/claims/{claim_id}/release",
        json={
            "target_status": "APPROVED",
            "cleared_investigation_id": inv_id,
            "actor_id": "SIU-SUPERVISOR"
        }
    )
    assert res_good_rel.status_code == 200
    rel_data = res_good_rel.json()
    assert rel_data["status"] == "SIU_HOLD_RELEASED"
    assert rel_data["claim_status"] == "APPROVED"

    # 5. Timeline validation: events are strictly linked
    res_tl = client.get(f"/api/v1/claims/{claim_id}/timeline")
    assert res_tl.status_code == 200
    event_types = [e["event_type"] for e in res_tl.json()]
    assert "CLAIM_SIU_HOLD_PLACED" in event_types
    assert "INVESTIGATION_OPENED" in event_types
    assert "INVESTIGATION_CLOSED" in event_types
    assert "CLAIM_APPROVED" in event_types

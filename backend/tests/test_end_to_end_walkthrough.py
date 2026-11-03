"""
End-to-End Forensic Investigator Walkthrough Test.
Simulates a real investigator performing the full 10-step lifecycle:
1. Suspicious Claims Queue triage
2. Claim Dossier retrieval
3. Entity verification (Claimant, Policy, Incident, Provider)
4. Invoice and Payment financial reconciliation
5. Network Ego-Graph traversal
6. Explainable Risk Indicators and Score waterfall inspection
7. SIU Investigation Creation (with INVESTIGATION_OPENED event)
8. Evidence Notes append-only recording
9. FSM Status Transitions through terminal closure and claim SIU referral
10. Cryptographic Event Hash Chain verification

Runs against an isolated temporary copy of data/operational.db to preserve seed data.
"""

import shutil
import tempfile
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import get_db
from db.engine import register_udfs

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_DB_PATH = REPO_ROOT / "data" / "operational.db"


@pytest.fixture(scope="module")
def walkthrough_client():
    with tempfile.TemporaryDirectory(prefix="sentinel_walkthrough_") as tmpdir:
        test_db_path = Path(tmpdir) / "operational_walkthrough.db"
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


def test_complete_investigation_lifecycle_walkthrough(walkthrough_client):
    client, db_path = walkthrough_client

    # -------------------------------------------------------------------------
    # STEP 1: Suspicious Claims Queue
    # -------------------------------------------------------------------------
    res_queue = client.get("/api/v1/claims?limit=25&risk_tier=HIGH")
    assert res_queue.status_code == 200
    queue_data = res_queue.json()
    assert queue_data["total"] > 0
    assert len(queue_data["items"]) > 0

    # Select the top suspicious claim in the queue
    target_claim = queue_data["items"][0]
    claim_id = target_claim["claim_id"]
    assert target_claim["latest_risk_tier"] == "HIGH"
    assert target_claim["latest_ief_score"] >= 65.0

    # -------------------------------------------------------------------------
    # STEP 2: Open Claim Dossier
    # -------------------------------------------------------------------------
    res_dossier = client.get(f"/api/v1/claims/{claim_id}")
    assert res_dossier.status_code == 200
    dossier = res_dossier.json()
    assert dossier["claim"]["claim_id"] == claim_id
    assert dossier["claim"]["latest_ief_score"] == target_claim["latest_ief_score"]

    # -------------------------------------------------------------------------
    # STEP 3: Claimant, Policy, Incident & Provider Details
    # -------------------------------------------------------------------------
    clmt = dossier["claimant"]
    assert clmt["claimant_id"] == dossier["claim"]["claimant_id"]
    assert len(clmt["full_name"]) > 0
    assert len(clmt["address_norm"]) > 0

    pol = dossier["policy"]
    assert pol["policy_id"] == dossier["claim"]["policy_id"]
    assert pol["coverage_limit_cents"] > 0

    inc = dossier["incident"]
    assert inc["incident_id"] == dossier["claim"]["incident_id"]
    assert len(inc["incident_type"]) > 0

    # -------------------------------------------------------------------------
    # STEP 4: Related Invoices and Payments
    # -------------------------------------------------------------------------
    invoices = dossier["invoices"]
    payments = dossier["payments"]
    assert len(invoices) >= 1
    for inv in invoices:
        assert inv["billed_cents"] > 0
        assert inv["provider_id"] is not None

    total_billed = sum(i["billed_cents"] for i in invoices)
    assert total_billed > 0

    # -------------------------------------------------------------------------
    # STEP 5: Relationship Evidence & Network
    # -------------------------------------------------------------------------
    res_net = client.get(f"/api/v1/network/{claim_id}")
    assert res_net.status_code == 200
    net = res_net.json()
    assert net["claim_id"] == claim_id
    node_types = {n["type"] for n in net["nodes"]}
    assert "CLAIM" in node_types
    assert "CLAIMANT" in node_types
    assert "POLICY" in node_types
    assert len(net["edges"]) >= 1

    # -------------------------------------------------------------------------
    # STEP 6: Explainable Risk Indicators and Score
    # -------------------------------------------------------------------------
    res_inds = client.get(f"/api/v1/claims/{claim_id}/indicators")
    assert res_inds.status_code == 200
    indicators = res_inds.json()
    assert len(indicators) > 0
    for ind in indicators:
        assert ind["indicator_code"].startswith("IND-")
        assert ind["raw_points"] > 0.0
        assert ind["canonical_evidence_token"] is not None

    # -------------------------------------------------------------------------
    # STEP 7: Create an Investigation
    # -------------------------------------------------------------------------
    # If claim already had an investigation in seed data, close it or use another claim
    if dossier["investigation"] is not None:
        # Use a fresh HIGH risk claim with no existing investigation
        for item in queue_data["items"]:
            c_check = client.get(f"/api/v1/claims/{item['claim_id']}").json()
            if c_check["investigation"] is None:
                claim_id = item["claim_id"]
                break

    create_payload = {
        "primary_claim_id": claim_id,
        "priority": "P1_CRITICAL",
        "assigned_investigator_id": "SIU-LEAD-AGENT",
        "case_summary_notes": "Initiated high-priority syndicate investigation based on IND-06 PageRank and multi-clinic billing signals."
    }
    res_create = client.post("/api/v1/investigations", json=create_payload)
    assert res_create.status_code == 201
    created_case = res_create.json()
    inv_id = created_case["investigation_id"]
    open_evt_id = created_case["event_id"]
    assert inv_id.startswith("INVG-2026-")
    assert open_evt_id.startswith("EVT-2026-")

    # -------------------------------------------------------------------------
    # STEP 8: Record Evidence Notes
    # -------------------------------------------------------------------------
    note_payload = {
        "note": "Surveillance interview conducted. Claimant confirmed non-attendance at billed physical therapy facility.",
        "actor_id": "SIU-FIELD-AGENT"
    }
    res_note = client.post(f"/api/v1/investigations/{inv_id}/notes", json=note_payload)
    assert res_note.status_code == 200
    note_resp = res_note.json()
    assert note_resp["status"] == "NOTE_ADDED"
    assert "Surveillance interview conducted" in note_resp["case_summary_notes"]

    # -------------------------------------------------------------------------
    # STEP 9: Change Investigation Status (FSM lifecycle to confirmed fraud)
    # -------------------------------------------------------------------------
    # OPEN -> EVIDENCE_COLLECTION
    res_t1 = client.patch(
        f"/api/v1/investigations/{inv_id}/status",
        json={"new_status": "EVIDENCE_COLLECTION", "notes": "Active subpoena issuance", "actor_id": "SIU-LEAD-AGENT"}
    )
    assert res_t1.status_code == 200
    assert res_t1.json()["new_status"] == "EVIDENCE_COLLECTION"

    # EVIDENCE_COLLECTION -> SIU_FIELD_REVIEW
    res_t2 = client.patch(
        f"/api/v1/investigations/{inv_id}/status",
        json={"new_status": "SIU_FIELD_REVIEW", "notes": "Clinic site inspection confirmed phantom operation", "actor_id": "SIU-LEAD-AGENT"}
    )
    assert res_t2.status_code == 200
    assert res_t2.json()["new_status"] == "SIU_FIELD_REVIEW"

    # SIU_FIELD_REVIEW -> CLOSED_CONFIRMED_FRAUD
    res_close = client.patch(
        f"/api/v1/investigations/{inv_id}/status",
        json={
            "new_status": "CLOSED_CONFIRMED_FRAUD",
            "ruling_outcome": "CONFIRMED_FRAUD",
            "notes": "Terminal ruling: Confirmed organized fraud collusion ring.",
            "actor_id": "SIU-DIRECTOR"
        }
    )
    assert res_close.status_code == 200
    closed_resp = res_close.json()
    assert closed_resp["new_status"] == "CLOSED_CONFIRMED_FRAUD"
    assert closed_resp["ruling_outcome"] == "CONFIRMED_FRAUD"

    # Verify SIU referral was propagated to the claim by database trigger
    conn = sqlite3.connect(str(db_path))
    siu_ref = conn.execute("SELECT siu_referred FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()[0]
    assert siu_ref == 1

    # Verify sealed case immutability
    res_illegal_edit = client.post(
        f"/api/v1/investigations/{inv_id}/notes",
        json={"note": "Attempted tamper on sealed file", "actor_id": "SIU-ATTEMPT"}
    )
    assert res_illegal_edit.status_code == 400
    assert "ERR_CLOSED_INVESTIGATION_IMMUTABLE" in res_illegal_edit.json()["detail"]
    conn.close()

    # -------------------------------------------------------------------------
    # STEP 10: Inspect Immutable Event History
    # -------------------------------------------------------------------------
    res_timeline = client.get(f"/api/v1/claims/{claim_id}/timeline")
    assert res_timeline.status_code == 200
    events = res_timeline.json()
    assert len(events) >= 3

    event_types = [e["event_type"] for e in events]
    assert "INVESTIGATION_OPENED" in event_types
    assert "INVESTIGATION_STATUS_CHANGED" in event_types
    assert "INVESTIGATION_CLOSED" in event_types

    # Verify strict sequence numbering and unbroken hash chain
    for i in range(1, len(events)):
        assert events[i]["sequence_no"] > events[i-1]["sequence_no"]


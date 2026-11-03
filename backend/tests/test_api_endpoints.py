"""
End-to-End API and Investigator Cockpit test suite for SENTINEL//TRACE.
Validates all 11 steps of the investigator workflow via FastAPI TestClient.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_root_json_and_html():
    # JSON request
    res_json = client.get("/", headers={"Accept": "application/json"})
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["service"] == "SENTINEL//TRACE"
    assert data["schema_baseline"] == "ARCH-ST-010.3"

    # HTML request
    res_html = client.get("/", headers={"Accept": "text/html"})
    assert res_html.status_code == 200
    assert "SENTINEL // TRACE" in res_html.text
    assert "ARCH-ST-010.3 VERIFIED" in res_html.text

    # Direct cockpit endpoint
    res_cockpit = client.get("/cockpit")
    assert res_cockpit.status_code == 200
    assert "Forensic Fraud Intelligence Cockpit" in res_cockpit.text


def test_health_endpoint():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert data["schema_verified"] is True
    assert data["table_count"] == 12
    assert data["trigger_count"] == 27


def test_dashboard_stats():
    res = client.get("/api/v1/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_claims"] == 5000
    assert data["indicators"]["total_persisted"] == 4120
    assert data["entities"]["investigations"] == 45
    assert data["entities"]["relationship_edges"] == 8000
    assert data["entities"]["immutable_events"] == 19675
    assert len(data["merkle_root"]) == 64


def test_claims_list_and_filters():
    # General list
    res = client.get("/api/v1/claims?limit=25")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5000
    assert len(data["items"]) == 25

    # Filter by risk tier
    res_high = client.get("/api/v1/claims?risk_tier=HIGH&limit=10")
    assert res_high.status_code == 200
    data_high = res_high.json()
    for item in data_high["items"]:
        assert item["latest_risk_tier"] == "HIGH"
        assert item["latest_ief_score"] >= 65.0

    # Scenario YF-NEG-4: Collusion Ring claims are quarantined; operational API rejects scenario=yf_neg_4 with 400
    res_neg4 = client.get("/api/v1/claims?scenario=yf_neg_4")
    assert res_neg4.status_code == 400
    assert "quarantined" in res_neg4.json()["detail"].lower()

    # Scenario YF-NEG-5: 80 Apartment claims
    res_neg5 = client.get("/api/v1/claims?scenario=yf_neg_5")
    assert res_neg5.status_code == 200
    data_neg5 = res_neg5.json()
    assert data_neg5["total"] == 80
    for c in data_neg5["items"]:
        assert c["latest_ief_score"] <= 12.0


def test_claim_detail_dossier():
    claim_id = "CLM-2026-000050"
    res = client.get(f"/api/v1/claims/{claim_id}")
    assert res.status_code == 200
    d = res.json()
    assert d["claim"]["claim_id"] == claim_id
    assert d["claimant"]["claimant_id"] == "CLMT-000014"
    assert "policy" in d
    assert "incident" in d
    assert len(d["invoices"]) > 0


def test_claim_indicators_endpoint():
    claim_id = "CLM-2026-000050"
    res = client.get(f"/api/v1/claims/{claim_id}/indicators")
    assert res.status_code == 200
    inds = res.json()
    assert len(inds) > 0
    for ind in inds:
        assert "indicator_code" in ind
        assert "raw_points" in ind
        assert "canonical_evidence_token" in ind


def test_claim_timeline_endpoint():
    claim_id = "CLM-2026-000050"
    res = client.get(f"/api/v1/claims/{claim_id}/timeline")
    assert res.status_code == 200
    events = res.json()
    assert len(events) > 0
    seqs = [e["sequence_no"] for e in events]
    assert seqs == sorted(seqs)


def test_claim_network_endpoint():
    claim_id = "CLM-2026-000050"
    res = client.get(f"/api/v1/network/{claim_id}")
    assert res.status_code == 200
    net = res.json()
    assert net["claim_id"] == claim_id
    assert len(net["nodes"]) >= 4
    assert len(net["edges"]) >= 3
    assert net["metrics"]["total_nodes"] == len(net["nodes"])


def test_investigations_endpoints():
    # List
    res = client.get("/api/v1/investigations?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 45
    assert len(data["items"]) == 10

    # Detail
    first_id = data["items"][0]["investigation_id"]
    res_det = client.get(f"/api/v1/investigations/{first_id}")
    assert res_det.status_code == 200
    det = res_det.json()
    assert det["investigation"]["investigation_id"] == first_id
    assert "claim" in det

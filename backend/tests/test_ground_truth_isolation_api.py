"""
Regression test for P1 DEF-01: Ground-Truth Physical & Logical Isolation in Operational APIs.

Validates:
1. Operational API endpoints NEVER open, query, or depend upon data/ground_truth.db.
2. Operational API endpoints succeed completely even if ground_truth.db is absent or inaccessible.
3. Attempting to query `scenario=yf_neg_4` via operational API is rejected with 400 Bad Request.
4. Nonexistent claim IDs return 404 for indicators and timeline endpoints.
5. Nonexistent investigation IDs return 404 for timeline endpoints.
6. Invalid risk_tier, claim_status, priority, and status query parameters return 400 Bad Request.
7. Legitimate operational queries (pagination, search, scenario=yf_neg_5) function normally.
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_operational_endpoints_without_ground_truth_db(monkeypatch, tmp_path):
    """
    Asserts operational API endpoints never attempt to access ground_truth.db.
    Simulates total absence of ground_truth.db by patching the path to a non-existent file.
    """
    fake_gt_path = tmp_path / "non_existent_ground_truth.db"
    assert not fake_gt_path.exists()

    with patch("backend.app.api.v1.endpoints.claims.REPO_ROOT", tmp_path):
        # 1. Dashboard stats
        r_stats = client.get("/api/v1/dashboard/stats")
        assert r_stats.status_code == 200
        data_stats = r_stats.json()
        assert data_stats["total_claims"] == 5000

        # 2. Claims list
        r_claims = client.get("/api/v1/claims?limit=10")
        assert r_claims.status_code == 200
        data_claims = r_claims.json()
        assert data_claims["total"] == 5000
        assert len(data_claims["items"]) == 10

        # 3. Specific claim dossier
        target_id = data_claims["items"][0]["claim_id"]
        r_dossier = client.get(f"/api/v1/claims/{target_id}")
        assert r_dossier.status_code == 200
        assert r_dossier.json()["claim"]["claim_id"] == target_id

        # 4. Indicators
        r_inds = client.get(f"/api/v1/claims/{target_id}/indicators")
        assert r_inds.status_code == 200

        # 5. Timeline
        r_time = client.get(f"/api/v1/claims/{target_id}/timeline")
        assert r_time.status_code == 200

        # 6. Network ego-graph
        r_net = client.get(f"/api/v1/network/{target_id}")
        assert r_net.status_code == 200


def test_scenario_yf_neg_4_filter_rejected_in_operational_api():
    """
    Asserts that scenario=yf_neg_4 is blocked with 400 Bad Request
    because collusion scenario labels are strictly quarantined in ground_truth.db.
    """
    r = client.get("/api/v1/claims?scenario=yf_neg_4")
    assert r.status_code == 400
    assert "strictly quarantined" in r.json()["detail"].lower()


def test_scenario_yf_neg_5_operational_address_filter():
    """
    Asserts that scenario=yf_neg_5 functions purely via operational normalized address query.
    """
    r = client.get("/api/v1/claims?scenario=yf_neg_5&limit=100")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 80
    assert len(data["items"]) == 80
    for item in data["items"]:
        assert item["latest_risk_tier"] == "LOW"


def test_invalid_query_parameters_return_400():
    """Asserts that invalid risk_tier, claim_status, or scenario return 400 Bad Request."""
    # Invalid risk tier
    r1 = client.get("/api/v1/claims?risk_tier=EXTREME")
    assert r1.status_code == 400
    assert "Invalid risk_tier" in r1.json()["detail"]

    # Invalid claim status
    r2 = client.get("/api/v1/claims?claim_status=UNDER_REVIEW")
    assert r2.status_code == 400
    assert "Invalid claim_status" in r2.json()["detail"]

    # Invalid scenario
    r3 = client.get("/api/v1/claims?scenario=UNKNOWN_SCENARIO")
    assert r3.status_code == 400
    assert "Invalid scenario filter" in r3.json()["detail"]

    # Invalid investigation status
    r4 = client.get("/api/v1/investigations?status=DELETED")
    assert r4.status_code == 400
    assert "Invalid status" in r4.json()["detail"]

    # Invalid investigation priority
    r5 = client.get("/api/v1/investigations?priority=URGENT")
    assert r5.status_code == 400
    assert "Invalid priority" in r5.json()["detail"]


def test_nonexistent_ids_return_404():
    """Asserts that nonexistent IDs return 404 across sub-resource endpoints."""
    # Claim indicators
    r1 = client.get("/api/v1/claims/CLM-9999-999999/indicators")
    assert r1.status_code == 404
    assert "not found" in r1.json()["detail"].lower()

    # Claim timeline
    r2 = client.get("/api/v1/claims/CLM-9999-999999/timeline")
    assert r2.status_code == 404
    assert "not found" in r2.json()["detail"].lower()

    # Investigation timeline
    r3 = client.get("/api/v1/investigations/INVG-9999-999999/timeline")
    assert r3.status_code == 404
    assert "not found" in r3.json()["detail"].lower()

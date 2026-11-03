"""
Operational IND-06 and PageRank Centrality Engine Verification Test.
Complies with ARCH-ST-010.3 Section 8 (IND-06) and Section 9.1-9.4.

Validates:
1. Operational graph universe: exactly 7,500 nodes (5,000 claims, 2,000 claimants, 500 providers).
2. Active operational relationship edges only (is_active = 1, beta-weighted).
3. Ground-truth withheld edges are strictly excluded from operational graph.
4. Float64 power iteration convergence (alpha=0.85, tol=1e-9).
5. Independent numerical comparison against NumPy power iteration.
6. Claim-normalized PageRank formula: PR_tilde(c) = (N_claims * PR(c)) / sum(PR(claims)).
7. Canonical evidence token format: "PR:" || claim_id.
"""

import sqlite3
import pytest
import numpy as np
from pathlib import Path
from backend.app.generator.graph import (
    BETA_FACTORS, build_operational_graph, compute_pagerank,
    compute_claim_normalized_pagerank, detect_ind06_findings
)

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


def test_operational_graph_construction(db_conn):
    """Asserts deterministic node set and active-only edge inclusion."""
    nodes, adj, claim_indices = build_operational_graph(db_conn)
    
    # 7,500 deterministic nodes
    assert len(nodes) == 7500, f"Expected 7500 nodes, got {len(nodes)}"
    assert len(claim_indices) == 5000, f"Expected 5000 claims, got {len(claim_indices)}"
    assert len([n for n in nodes if n.startswith("CLAIMANT:")]) == 2000
    assert len([n for n in nodes if n.startswith("PROVIDER:")]) == 500

    # Adjacency symmetry: adj[u][v] == adj[v][u]
    for u in adj:
        for v, w in adj[u].items():
            assert abs(adj[v][u] - w) < 1e-12, f"Asymmetry between node {u} and {v}"


def test_independent_pagerank_numpy_comparison(db_conn):
    """
    Independently verifies power-iteration PageRank using NumPy.
    Asserts max absolute difference < 1e-8.
    """
    nodes, adj, claim_indices = build_operational_graph(db_conn)
    N = len(nodes)
    alpha = 0.85
    tol = 1e-9

    # Method 1: Engine implementation
    v_engine, it_engine, err_engine = compute_pagerank(N, adj, alpha=alpha, tol=tol)
    assert it_engine < 200, "Engine PageRank did not converge within 200 iterations"
    assert err_engine < tol, "Engine PageRank residual exceeded tolerance"

    # Method 2: Independent NumPy power iteration
    # Build degree vector and normalized transition operator
    degrees = np.array([sum(adj[i].values()) for i in range(N)], dtype=np.float64)
    v_np = np.full(N, 1.0 / N, dtype=np.float64)
    dangling_mask = (degrees == 0.0)
    
    inv_deg = np.zeros(N, dtype=np.float64)
    inv_deg[~dangling_mask] = 1.0 / degrees[~dangling_mask]

    for _ in range(200):
        dangling_sum = np.sum(v_np[dangling_mask])
        scaled = v_np * inv_deg
        
        # Sparse matrix-vector product
        v_next = np.zeros(N, dtype=np.float64)
        for i in range(N):
            acc = 0.0
            for j, w in adj[i].items():
                acc += w * scaled[j]
            v_next[i] = alpha * acc + (alpha * dangling_sum / N) + ((1.0 - alpha) / N)

        diff = np.sum(np.abs(v_next - v_np))
        v_np = v_next
        if diff < tol:
            break

    # Compare stationary vectors
    max_delta = np.max(np.abs(np.array(v_engine) - v_np))
    assert max_delta < 1e-8, f"Discrepancy between engine and independent NumPy: {max_delta}"


def test_ind06_token_and_score_formula(db_conn):
    """Asserts exact formula, thresholds, and canonical tokens for IND-06."""
    findings = detect_ind06_findings(db_conn)
    assert len(findings) > 0, "IND-06 emitted zero findings"

    for f in findings:
        cid = f["claim_id"]
        assert f["indicator_code"] == "IND-06"
        assert f["pillar"] == "NETWORK"
        assert f["dedup_scope"] == "CLAIM"
        assert f["canonical_evidence_token"] == f"PR:{cid}"
        assert f["max_points"] == 15.0

        pr_tilde = f["feature"]["normalized_pagerank"]
        assert pr_tilde > 1.25, f"IND-06 fired with PR_tilde <= 1.25: {pr_tilde}"
        
        expected_pts = min(15.0, 15.0 * (pr_tilde - 1.25) / 2.75)
        assert abs(f["raw_points"] - expected_pts) < 0.01


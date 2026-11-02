"""
Operational Graph and PageRank Centrality Engine for SENTINEL//TRACE.
Complies with ARCH-ST-010.2 Section 9.1-9.4 and Section 8 (IND-06).

Features:
- Deterministic 7,500-node universe (5,000 claims, 2,000 claimants, 500 providers)
- Structural FK edges (1.0 weight each)
- Active operational relationship_edges only (is_active = 1, beta-weighted)
- Strict exclusion of withheld / ground-truth edges
- Float64 power-iteration PageRank (alpha = 0.85, tol = 1e-9)
- Claim-level normalization PR_tilde(c) = (N_claims * PR(c)) / sum(PR(claims))
- IND-06 indicator emission with canonical token "PR:" || claim_id
"""

import sqlite3
from typing import Dict, List, Tuple, Any, Optional


BETA_FACTORS = {
    "SHARED_BANK_ACCOUNT": 3.0,
    "SHARED_TAX_ID": 3.0,
    "SHARED_PHONE": 2.0,
    "CROSS_CLAIM_DUPLICATE_INVOICE": 3.0,
    "SAME_INCIDENT_PARTICIPANT": 1.2,
    "SHARED_ADDRESS": 1.5,
    "CLAIMANT_TREATED_BY_PROVIDER": 1.0,
    "PROVIDER_REFERRAL_LINK": 1.0,
}


def build_operational_graph(conn: sqlite3.Connection) -> Tuple[List[str], Dict[int, Dict[int, float]], List[int]]:
    """
    Constructs the operational graph W from SQLite database.
    Returns:
    - nodes: ordered list of node keys (format: 'CLAIM:<id>', 'CLAIMANT:<id>', 'PROVIDER:<id>')
    - adj: sparse adjacency dictionary: adj[u][v] = weight
    - claim_indices: list of node indices corresponding to claims
    """
    # 1. Deterministic node ordering: Claims -> Claimants -> Providers
    claims = [r[0] for r in conn.execute("SELECT claim_id FROM claims ORDER BY claim_id ASC").fetchall()]
    claimants = [r[0] for r in conn.execute("SELECT claimant_id FROM claimants ORDER BY claimant_id ASC").fetchall()]
    providers = [r[0] for r in conn.execute("SELECT provider_id FROM providers ORDER BY provider_id ASC").fetchall()]

    nodes: List[str] = []
    node_to_idx: Dict[str, int] = {}
    claim_indices: List[int] = []

    for cid in claims:
        idx = len(nodes)
        key = f"CLAIM:{cid}"
        nodes.append(key)
        node_to_idx[key] = idx
        node_to_idx[cid] = idx  # short alias
        claim_indices.append(idx)

    for clmt_id in claimants:
        idx = len(nodes)
        key = f"CLAIMANT:{clmt_id}"
        nodes.append(key)
        node_to_idx[key] = idx
        node_to_idx[clmt_id] = idx

    for prvid in providers:
        idx = len(nodes)
        key = f"PROVIDER:{prvid}"
        nodes.append(key)
        node_to_idx[key] = idx
        node_to_idx[prvid] = idx

    N = len(nodes)
    adj: Dict[int, Dict[int, float]] = {i: {} for i in range(N)}

    def add_edge(u: int, v: int, w: float):
        if u == v or w <= 0.0:
            return
        adj[u][v] = adj[u].get(v, 0.0) + w
        adj[v][u] = adj[v].get(u, 0.0) + w

    # 2. Structural FK edges (weight 1.0 each)
    # Claim <-> Claimant
    q_claim_clmt = "SELECT claim_id, claimant_id FROM claims"
    for cid, clmt_id in conn.execute(q_claim_clmt).fetchall():
        if cid in node_to_idx and clmt_id in node_to_idx:
            add_edge(node_to_idx[cid], node_to_idx[clmt_id], 1.0)

    # Claim <-> Invoicing Provider (distinct provider per claim)
    q_claim_prv = "SELECT DISTINCT claim_id, provider_id FROM invoices WHERE provider_id IS NOT NULL"
    for cid, prvid in conn.execute(q_claim_prv).fetchall():
        if cid in node_to_idx and prvid in node_to_idx:
            add_edge(node_to_idx[cid], node_to_idx[prvid], 1.0)

    # 3. Operational relationship edges (only is_active = 1)
    q_edges = """
    SELECT canonical_src_key, canonical_dst_key, edge_type, strength_weight
    FROM relationship_edges
    WHERE is_active = 1
    """
    for src_key, dst_key, etype, strength in conn.execute(q_edges).fetchall():
        beta = BETA_FACTORS.get(etype, 1.0)
        weight = beta * float(strength)
        u = node_to_idx.get(src_key)
        v = node_to_idx.get(dst_key)
        if u is not None and v is not None:
            add_edge(u, v, weight)

    return nodes, adj, claim_indices


def compute_pagerank(
    N: int,
    adj: Dict[int, Dict[int, float]],
    alpha: float = 0.85,
    tol: float = 1e-9,
    max_iter: int = 200
) -> Tuple[List[float], int, float]:
    """
    Computes float64 power-iteration PageRank over symmetric adjacency matrix.
    Handles dangling nodes (d_j == 0) via uniform redistribution.
    Returns:
    - v: stationary probability vector
    - it: iteration count at convergence
    - err: L1 norm difference ||v^{(t)} - v^{(t-1)}||_1
    """
    degrees = [sum(adj[i].values()) for i in range(N)]
    v = [1.0 / N] * N
    it = 0
    err = 1.0

    while it < max_iter:
        dangling_mass = sum(v[j] for j in range(N) if degrees[j] == 0.0)
        
        # Pre-divide v[j] / degree[j] for non-dangling nodes
        scaled_v = [v[j] / degrees[j] if degrees[j] > 0.0 else 0.0 for j in range(N)]
        
        vnext = [0.0] * N
        dangling_contrib = (alpha * dangling_mass / N) + ((1.0 - alpha) / N)

        for i in range(N):
            # Sum M[i][j] * v[j] where M[i][j] = W[i][j] / d[j]
            accum = sum(w * scaled_v[j] for j, w in adj[i].items())
            vnext[i] = alpha * accum + dangling_contrib

        err = sum(abs(vnext[i] - v[i]) for i in range(N))
        v = vnext
        it += 1
        if err < tol:
            break

    if err >= tol and it >= max_iter:
        raise RuntimeError(f"PageRank NOT CONVERGED at max_iter={max_iter}, err={err:.6e}")

    return v, it, err


def compute_claim_normalized_pagerank(
    v: List[float],
    claim_indices: List[int]
) -> Dict[int, float]:
    """
    Computes claim-normalized PageRank:
    PR_tilde(c) = (N_claims * PR(c)) / sum(PR(claims))
    Returns mapping: claim_node_idx -> PR_tilde
    """
    N_claims = len(claim_indices)
    claim_sum = sum(v[idx] for idx in claim_indices)
    if claim_sum == 0.0:
        return {idx: 0.0 for idx in claim_indices}

    factor = float(N_claims) / claim_sum
    return {idx: v[idx] * factor for idx in claim_indices}


def detect_ind06_findings(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Executes operational graph construction, computes claim-normalized PageRank,
    and returns IND-06 indicator findings for all claims where PR_tilde(c) > 1.25.
    """
    nodes, adj, claim_indices = build_operational_graph(conn)
    v, it, err = compute_pagerank(len(nodes), adj, alpha=0.85, tol=1e-9)
    pr_tilde_map = compute_claim_normalized_pagerank(v, claim_indices)

    findings: List[Dict[str, Any]] = []
    for c_idx in claim_indices:
        pr_tilde = pr_tilde_map[c_idx]
        if pr_tilde > 1.25:
            cid = nodes[c_idx].replace("CLAIM:", "")
            raw_pts = min(15.0, 15.0 * (pr_tilde - 1.25) / 2.75)
            sev = "HIGH" if raw_pts >= 10.0 else "MEDIUM"
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-06",
                "pillar": "NETWORK",
                "dedup_scope": "CLAIM",
                "canonical_evidence_token": f"PR:{cid}",
                "severity": sev,
                "raw_points": round(raw_pts, 3),
                "max_points": 15.0,
                "normalized_value": round(raw_pts / 15.0, 4),
                "feature": {"normalized_pagerank": round(pr_tilde, 6), "iterations": it}
            })

    return findings


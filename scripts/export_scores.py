import sqlite3
import csv
from pathlib import Path

op_conn = sqlite3.connect("sentinel_trace.db")
gt_conn = sqlite3.connect("ground_truth.db")

# 1. Export yf_neg_4_scores.csv
yf4_rows = gt_conn.execute("""
    SELECT rm.claim_id, rm.ring_id
    FROM ring_members rm
    WHERE rm.ring_id IN ('RING-2026-016','RING-2026-017','RING-2026-018','RING-2026-019','RING-2026-020')
    ORDER BY rm.ring_id ASC, rm.claim_id ASC
""").fetchall()

with open("yf_neg_4_scores.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "claim_id", "ring_id", "indicator_ids", "evidence_ids",
        "p_net", "p_fin", "p_beh", "p_doc", "base_score", "final_score", "risk_tier"
    ])
    for cid, rid in yf4_rows:
        # Fetch indicators
        inds = op_conn.execute(
            "SELECT indicator_code, pillar, raw_points, canonical_evidence_token FROM fraud_indicators WHERE claim_id = ? ORDER BY indicator_code ASC",
            (cid,)
        ).fetchall()
        ind_codes = ";".join([r[0] for r in inds])
        ev_tokens = ";".join([r[3] for r in inds])
        
        # Calculate pillar scores
        net_pts = sum(r[2] for r in inds if r[1] == 'NETWORK')
        fin_pts = sum(r[2] for r in inds if r[1] == 'FINANCIAL')
        beh_pts = sum(r[2] for r in inds if r[1] == 'BEHAVIORAL')
        doc_pts = sum(r[2] for r in inds if r[1] == 'DOCUMENT')
        
        p_net = min(100.0, 100.0 * net_pts / 60.0)
        p_fin = min(100.0, 100.0 * fin_pts / 55.0)
        p_beh = min(100.0, 100.0 * beh_pts / 45.0)
        p_doc = min(100.0, 100.0 * doc_pts / 40.0)
        
        base_s = 0.35 * p_net + 0.30 * p_fin + 0.20 * p_beh + 0.15 * p_doc
        
        # Fetch DB stored final score and tier
        clm_row = op_conn.execute("SELECT latest_ief_score, latest_risk_tier FROM claims WHERE claim_id = ?", (cid,)).fetchone()
        final_s = clm_row[0]
        tier = clm_row[1]
        
        writer.writerow([
            cid, rid, ind_codes, ev_tokens,
            f"{p_net:.2f}", f"{p_fin:.2f}", f"{p_beh:.2f}", f"{p_doc:.2f}",
            f"{base_s:.2f}", f"{final_s:.2f}", tier
        ])

print("Exported yf_neg_4_scores.csv successfully.")

# 2. Export yf_neg_5_scores.csv (80 claims for the 80 apartment claimants at 100 Ocean Ave)
yf5_claims = op_conn.execute("""
    SELECT c.claim_id, c.claimant_id, clmt.address_norm, c.latest_ief_score, c.latest_risk_tier
    FROM claims c
    JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
    WHERE clmt.address_norm LIKE '100 Ocean Ave%'
    ORDER BY c.claim_id ASC
""").fetchall()

# Exactly 80 claims (first claim per claimant) or all claims
with open("yf_neg_5_scores.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "claim_id", "claimant_id", "address_norm", "indicator_ids",
        "p_net", "p_fin", "p_beh", "p_doc", "base_score", "final_score", "risk_tier"
    ])
    seen_clmts = set()
    count = 0
    for cid, clmt_id, addr, final_s, tier in yf5_claims:
        if clmt_id in seen_clmts:
            continue
        seen_clmts.add(clmt_id)
        count += 1
        inds = op_conn.execute(
            "SELECT indicator_code, pillar, raw_points FROM fraud_indicators WHERE claim_id = ? ORDER BY indicator_code ASC",
            (cid,)
        ).fetchall()
        ind_codes = ";".join([r[0] for r in inds]) if inds else "NONE"
        net_pts = sum(r[2] for r in inds if r[1] == 'NETWORK')
        fin_pts = sum(r[2] for r in inds if r[1] == 'FINANCIAL')
        beh_pts = sum(r[2] for r in inds if r[1] == 'BEHAVIORAL')
        doc_pts = sum(r[2] for r in inds if r[1] == 'DOCUMENT')
        
        p_net = min(100.0, 100.0 * net_pts / 60.0)
        p_fin = min(100.0, 100.0 * fin_pts / 55.0)
        p_beh = min(100.0, 100.0 * beh_pts / 45.0)
        p_doc = min(100.0, 100.0 * doc_pts / 40.0)
        base_s = 0.35 * p_net + 0.30 * p_fin + 0.20 * p_beh + 0.15 * p_doc
        
        writer.writerow([
            cid, clmt_id, addr, ind_codes,
            f"{p_net:.2f}", f"{p_fin:.2f}", f"{p_beh:.2f}", f"{p_doc:.2f}",
            f"{base_s:.2f}", f"{final_s:.2f}", tier
        ])
        if count == 80:
            break

print(f"Exported yf_neg_5_scores.csv ({count} claims) successfully.")


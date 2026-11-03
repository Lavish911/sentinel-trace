"""
Dashboard summary statistics endpoint for SENTINEL//TRACE.
Directly queries operational tables in sentinel_trace.db.
"""

from fastapi import APIRouter, Depends
import sqlite3
from typing import Dict, Any

from backend.app.db.session import get_db

router = APIRouter()


@router.get("/stats")
def get_dashboard_stats(conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
    """Returns operational database summary metrics and risk distribution."""
    # Claim totals & risk tier distribution
    tier_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for row in conn.execute("SELECT latest_risk_tier, COUNT(*) FROM claims GROUP BY latest_risk_tier").fetchall():
        tier_counts[row[0]] = row[1]

    # Status distribution
    status_counts = {}
    for row in conn.execute("SELECT claim_status, COUNT(*) FROM claims GROUP BY claim_status").fetchall():
        status_counts[row[0]] = row[1]

    # Financial aggregates
    fin_row = conn.execute("""
        SELECT 
            SUM(claimed_amount_cents),
            SUM(payout_cap_cents),
            SUM(approved_amount_cents),
            SUM(gross_disbursed_cents),
            SUM(clawed_back_cents),
            SUM(net_paid_cents)
        FROM claims
    """).fetchone()

    # Fraud indicators total & pillar breakdown
    ind_total = conn.execute("SELECT COUNT(*) FROM fraud_indicators").fetchone()[0]
    pillar_counts = {}
    for row in conn.execute("SELECT pillar, COUNT(*) FROM fraud_indicators GROUP BY pillar").fetchall():
        pillar_counts[row[0]] = row[1]

    # Entity counts
    claimants_count = conn.execute("SELECT COUNT(*) FROM claimants").fetchone()[0]
    providers_count = conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    invoices_count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    payments_count = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    edges_count = conn.execute("SELECT COUNT(*) FROM relationship_edges").fetchone()[0]
    investigations_count = conn.execute("SELECT COUNT(*) FROM investigations").fetchone()[0]
    events_count = conn.execute("SELECT COUNT(*) FROM immutable_events").fetchone()[0]

    # Merkle root
    last_event = conn.execute("SELECT event_hash FROM immutable_events ORDER BY sequence_no DESC LIMIT 1").fetchone()
    merkle_root = last_event[0] if last_event else ""

    return {
        "dataset_baseline": "ARCH-ST-010.2 (Seed 42)",
        "total_claims": sum(tier_counts.values()),
        "risk_tiers": tier_counts,
        "claim_statuses": status_counts,
        "financials": {
            "total_claimed_dollars": round((fin_row[0] or 0) / 100.0, 2),
            "total_payout_cap_dollars": round((fin_row[1] or 0) / 100.0, 2),
            "total_approved_dollars": round((fin_row[2] or 0) / 100.0, 2),
            "total_disbursed_dollars": round((fin_row[3] or 0) / 100.0, 2),
            "total_clawed_back_dollars": round((fin_row[4] or 0) / 100.0, 2),
            "total_net_paid_dollars": round((fin_row[5] or 0) / 100.0, 2),
        },
        "indicators": {
            "total_persisted": ind_total,
            "by_pillar": pillar_counts,
        },
        "entities": {
            "claimants": claimants_count,
            "providers": providers_count,
            "invoices": invoices_count,
            "payments": payments_count,
            "relationship_edges": edges_count,
            "investigations": investigations_count,
            "immutable_events": events_count,
        },
        "merkle_root": merkle_root,
    }

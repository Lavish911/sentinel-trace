"""
Claim management and dossier endpoints for SENTINEL//TRACE.
Provides forensic investigation views over claims, claimants, policies, invoices, and payments.
Directly interfaces with canonical db.operations for claim hold and release mutations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import sqlite3
import json
from typing import Dict, Any, List, Optional

from backend.app.db.session import get_db
from db.operations import place_claim_on_siu_hold, release_claim_from_siu_hold
from db.seed import EventChainEmitter

router = APIRouter()


class ClaimHoldRequest(BaseModel):
    actor_id: str = "USR-SIU-001"
    reason: Optional[str] = "High-risk indicators requiring SIU review"


class ClaimReleaseRequest(BaseModel):
    cleared_investigation_id: str
    target_status: str = Field(default="UNDER_REVIEW", pattern="^(UNDER_REVIEW|APPROVED)$")
    actor_id: str = "USR-SIU-001"


@router.get("")
def list_claims(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    risk_tier: Optional[str] = None,
    claim_status: Optional[str] = None,
    search: Optional[str] = None,
    scenario: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Returns paginated, filterable list of claims with forensic triage metadata."""
    where_clauses = []
    params = []

    if risk_tier and risk_tier != "ALL":
        where_clauses.append("c.latest_risk_tier = ?")
        params.append(risk_tier)

    if claim_status and claim_status != "ALL":
        where_clauses.append("c.claim_status = ?")
        params.append(claim_status)

    if search:
        s_term = f"%{search}%"
        where_clauses.append("(c.claim_id LIKE ? OR clmt.full_name LIKE ? OR c.policy_id LIKE ?)")
        params.extend([s_term, s_term, s_term])

    if scenario == "yf_neg_4":
        # 40 collusion ring claims (CLM-2026-000711..000750)
        where_clauses.append("c.claim_id BETWEEN 'CLM-2026-000711' AND 'CLM-2026-000750'")
    elif scenario == "yf_neg_5":
        # 80 high-density apartment claims (742 Evergreen Terrace / 100 Ocean Ave)
        where_clauses.append("(clmt.address_norm LIKE '742 EVERGREEN TERRACE%' OR clmt.address_norm LIKE '100 Ocean Ave%' OR c.claim_id BETWEEN 'CLM-2026-000776' AND 'CLM-2026-000855')")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_query = f"""
        SELECT COUNT(*) 
        FROM claims c 
        JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
        {where_sql}
    """
    total = conn.execute(count_query, params).fetchone()[0]

    select_query = f"""
        SELECT 
            c.claim_id,
            c.claimant_id,
            clmt.full_name as claimant_name,
            c.policy_id,
            p.line_of_business,
            c.incident_id,
            inc.incident_type,
            c.claim_status,
            c.claimed_amount_cents,
            c.payout_cap_cents,
            c.latest_ief_score,
            c.latest_risk_tier,
            c.submitted_at_utc,
            c.scoring_evidence_sha256
        FROM claims c
        JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
        JOIN policies p ON c.policy_id = p.policy_id
        JOIN incidents inc ON c.incident_id = inc.incident_id
        {where_sql}
        ORDER BY c.latest_ief_score DESC, c.claim_id ASC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(select_query, params + [limit, skip]).fetchall()

    items = []
    for r in rows:
        items.append({
            "claim_id": r[0],
            "claimant_id": r[1],
            "claimant_name": r[2],
            "policy_id": r[3],
            "line_of_business": r[4],
            "incident_id": r[5],
            "incident_type": r[6],
            "claim_status": r[7],
            "claimed_amount_dollars": round(r[8] / 100.0, 2),
            "payout_cap_dollars": round(r[9] / 100.0, 2),
            "latest_ief_score": float(r[10]),
            "latest_risk_tier": r[11],
            "submitted_at_utc": r[12],
            "scoring_evidence_sha256": r[13],
        })

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.get("/{claim_id}")
def get_claim_detail(claim_id: str, conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
    """Retrieves complete multi-entity dossier for an individual claim."""
    # 1. Core claim record
    q_claim = "SELECT * FROM claims WHERE claim_id = ?"
    c_row = conn.execute(q_claim, (claim_id,)).fetchone()
    if not c_row:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    claim_dict = dict(c_row)

    # 2. Claimant details
    q_clmt = "SELECT * FROM claimants WHERE claimant_id = ?"
    clmt_row = conn.execute(q_clmt, (claim_dict["claimant_id"],)).fetchone()
    claimant_dict = dict(clmt_row) if clmt_row else {}

    # 3. Policy details
    q_pol = "SELECT * FROM policies WHERE policy_id = ?"
    pol_row = conn.execute(q_pol, (claim_dict["policy_id"],)).fetchone()
    policy_dict = dict(pol_row) if pol_row else {}

    # 4. Incident details
    q_inc = "SELECT * FROM incidents WHERE incident_id = ?"
    inc_row = conn.execute(q_inc, (claim_dict["incident_id"],)).fetchone()
    incident_dict = dict(inc_row) if inc_row else {}

    # 5. Invoices
    q_inv = """
        SELECT i.*, p.provider_name, p.provider_type, p.network_tier
        FROM invoices i
        LEFT JOIN providers p ON i.provider_id = p.provider_id
        WHERE i.claim_id = ?
        ORDER BY i.submitted_at_utc ASC
    """
    invoices = [dict(r) for r in conn.execute(q_inv, (claim_id,)).fetchall()]

    # 6. Payments
    q_pay = "SELECT * FROM payments WHERE claim_id = ? ORDER BY created_at_utc ASC"
    payments = [dict(r) for r in conn.execute(q_pay, (claim_id,)).fetchall()]

    # 7. Fraud indicators summary
    q_inds = "SELECT * FROM fraud_indicators WHERE claim_id = ? ORDER BY pillar, raw_points DESC"
    indicators = [dict(r) for r in conn.execute(q_inds, (claim_id,)).fetchall()]

    # 8. Associated active investigation if any (latest)
    q_invg = "SELECT * FROM investigations WHERE primary_claim_id = ? ORDER BY opened_at_utc DESC, investigation_id DESC LIMIT 1"
    invg_row = conn.execute(q_invg, (claim_id,)).fetchone()
    investigation = dict(invg_row) if invg_row else None

    return {
        "claim": claim_dict,
        "claimant": claimant_dict,
        "policy": policy_dict,
        "incident": incident_dict,
        "invoices": invoices,
        "payments": payments,
        "fraud_indicators": indicators,
        "investigation": investigation,
    }


@router.get("/{claim_id}/indicators")
def get_claim_indicators(claim_id: str, conn: sqlite3.Connection = Depends(get_db)) -> List[Dict[str, Any]]:
    """Returns all fraud indicators and score contributions for a claim."""
    q = """
        SELECT 
            indicator_id,
            indicator_code,
            pillar,
            dedup_scope,
            canonical_evidence_token,
            severity,
            raw_points,
            max_points,
            normalized_value,
            feature_snapshot_json,
            computed_at_utc
        FROM fraud_indicators
        WHERE claim_id = ?
        ORDER BY pillar ASC, raw_points DESC
    """
    rows = conn.execute(q, (claim_id,)).fetchall()
    results = []
    for r in rows:
        feat = {}
        if r[9]:
            try:
                feat = json.loads(r[9])
            except Exception:
                pass
        results.append({
            "indicator_id": r[0],
            "indicator_code": r[1],
            "pillar": r[2],
            "dedup_scope": r[3],
            "canonical_evidence_token": r[4],
            "severity": r[5],
            "raw_points": float(r[6]),
            "max_points": float(r[7]),
            "normalized_value": float(r[8]),
            "feature": feat,
            "computed_at_utc": r[10],
        })
    return results


@router.get("/{claim_id}/timeline")
def get_claim_timeline(claim_id: str, conn: sqlite3.Connection = Depends(get_db)) -> List[Dict[str, Any]]:
    """Returns chronological sequence of immutable events linked to this claim."""
    q = """
        SELECT 
            sequence_no,
            event_id,
            event_type,
            entity_type,
            entity_id,
            actor_id,
            occurred_at_utc,
            payload_json,
            event_hash,
            prev_event_hash
        FROM immutable_events
        WHERE claim_id = ?
        ORDER BY sequence_no ASC
    """
    rows = conn.execute(q, (claim_id,)).fetchall()
    events = []
    for r in rows:
        p = {}
        if r[7]:
            try:
                p = json.loads(r[7])
            except Exception:
                pass
        events.append({
            "sequence_no": r[0],
            "event_id": r[1],
            "event_type": r[2],
            "entity_type": r[3],
            "entity_id": r[4],
            "actor_id": r[5],
            "occurred_at_utc": r[6],
            "payload": p,
            "event_hash": r[8],
            "prev_event_hash": r[9],
        })
    return events


@router.post("/{claim_id}/hold")
def place_claim_on_hold(
    claim_id: str,
    payload: ClaimHoldRequest = ClaimHoldRequest(),
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Places a claim on SIU_HOLD using db.operations.place_claim_on_siu_hold."""
    row = conn.execute("SELECT claim_status FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    if row[0] == "SIU_HOLD":
        raise HTTPException(status_code=400, detail=f"Claim {claim_id} is already on SIU_HOLD")

    from backend.app.api.v1.endpoints.investigations import get_operation_timestamp
    now_utc = get_operation_timestamp(conn)
    emitter = EventChainEmitter(conn)
    emitter.sync_from_db()

    try:
        ev_id = place_claim_on_siu_hold(
            conn=conn,
            emitter=emitter,
            claim_id=claim_id,
            actor_id=payload.actor_id,
            occurred_at_utc=now_utc,
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Database integrity error: {e}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to place claim on SIU hold: {e}")

    return {
        "status": "SIU_HOLD_PLACED",
        "claim_id": claim_id,
        "claim_status": "SIU_HOLD",
        "event_id": ev_id,
        "occurred_at_utc": now_utc,
    }


@router.post("/{claim_id}/release")
def release_claim_hold(
    claim_id: str,
    payload: ClaimReleaseRequest,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """
    Releases a claim from SIU_HOLD following a CLEARED_BENIGN investigation.
    Strictly verified against D-1 SIU exit gate in trg_claims_fsm_upd.
    """
    row = conn.execute("SELECT claim_status FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    if row[0] != "SIU_HOLD":
        raise HTTPException(status_code=400, detail=f"Claim {claim_id} is not on SIU_HOLD")

    from backend.app.api.v1.endpoints.investigations import get_operation_timestamp
    now_utc = get_operation_timestamp(conn)
    emitter = EventChainEmitter(conn)
    emitter.sync_from_db()

    try:
        ev_id = release_claim_from_siu_hold(
            conn=conn,
            emitter=emitter,
            claim_id=claim_id,
            target_status=payload.target_status,
            cleared_investigation_id=payload.cleared_investigation_id,
            actor_id=payload.actor_id,
            occurred_at_utc=now_utc,
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Database integrity error: {e}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to release claim from SIU hold: {e}")

    return {
        "status": "SIU_HOLD_RELEASED",
        "claim_id": claim_id,
        "claim_status": payload.target_status,
        "event_id": ev_id,
        "occurred_at_utc": now_utc,
    }

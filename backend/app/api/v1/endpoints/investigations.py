"""
Investigation and SIU Case Management endpoints for SENTINEL//TRACE.
Directly interfaces with operational `investigations` table in sentinel_trace.db.
Supports case triage, case creation, status lifecycle updates, and dossier linkages.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from backend.app.db.session import get_db

router = APIRouter()


class InvestigationCreate(BaseModel):
    primary_claim_id: str
    subject_claimant_id: Optional[str] = None
    subject_provider_id: Optional[str] = None
    priority: str = Field(default="P2_HIGH", pattern="^(P1_CRITICAL|P2_HIGH|P3_STANDARD)$")
    assigned_investigator_id: str = "SIU-AGENT-001"
    estimated_exposure_cents: int = Field(default=0, ge=0)
    case_summary_notes: str = Field(..., min_length=5)


class InvestigationUpdate(BaseModel):
    investigation_status: Optional[str] = Field(
        None,
        pattern="^(OPEN|EVIDENCE_COLLECTION|SIU_FIELD_REVIEW|LEGAL_ESCALATION|CLOSED_CONFIRMED_FRAUD|CLOSED_CLEARED_BENIGN|CLOSED_INSUFFICIENT_EVIDENCE)$"
    )
    priority: Optional[str] = Field(None, pattern="^(P1_CRITICAL|P2_HIGH|P3_STANDARD)$")
    assigned_investigator_id: Optional[str] = None
    recovered_clawback_cents: Optional[int] = Field(None, ge=0)
    case_summary_notes: Optional[str] = None
    ruling_outcome: Optional[str] = Field(None, pattern="^(CONFIRMED_FRAUD|CLEARED_BENIGN|INSUFFICIENT_EVIDENCE)$")


@router.get("")
def list_investigations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Lists investigations with triage filters and linked claim risk metrics."""
    where_clauses = []
    params = []

    if status and status != "ALL":
        where_clauses.append("inv.investigation_status = ?")
        params.append(status)

    if priority and priority != "ALL":
        where_clauses.append("inv.priority = ?")
        params.append(priority)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql = f"SELECT COUNT(*) FROM investigations inv {where_sql}"
    total = conn.execute(count_sql, params).fetchone()[0]

    select_sql = f"""
        SELECT 
            inv.investigation_id,
            inv.primary_claim_id,
            inv.subject_claimant_id,
            inv.subject_provider_id,
            inv.investigation_status,
            inv.priority,
            inv.assigned_investigator_id,
            inv.opened_at_utc,
            inv.updated_at_utc,
            inv.closed_at_utc,
            inv.ruling_outcome,
            inv.estimated_exposure_cents,
            inv.recovered_clawback_cents,
            inv.case_summary_notes,
            c.latest_ief_score,
            c.latest_risk_tier,
            clmt.full_name as claimant_name,
            prov.provider_name
        FROM investigations inv
        JOIN claims c ON inv.primary_claim_id = c.claim_id
        LEFT JOIN claimants clmt ON inv.subject_claimant_id = clmt.claimant_id
        LEFT JOIN providers prov ON inv.subject_provider_id = prov.provider_id
        {where_sql}
        ORDER BY 
            CASE inv.priority 
                WHEN 'P1_CRITICAL' THEN 1 
                WHEN 'P2_HIGH' THEN 2 
                ELSE 3 
            END,
            c.latest_ief_score DESC,
            inv.opened_at_utc DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(select_sql, params + [limit, skip]).fetchall()

    items = []
    for r in rows:
        items.append({
            "investigation_id": r[0],
            "primary_claim_id": r[1],
            "subject_claimant_id": r[2],
            "subject_provider_id": r[3],
            "investigation_status": r[4],
            "priority": r[5],
            "assigned_investigator_id": r[6],
            "opened_at_utc": r[7],
            "updated_at_utc": r[8],
            "closed_at_utc": r[9],
            "ruling_outcome": r[10],
            "estimated_exposure_dollars": round(r[11] / 100.0, 2),
            "recovered_clawback_dollars": round(r[12] / 100.0, 2),
            "case_summary_notes": r[13],
            "claim_score": float(r[14]) if r[14] is not None else 0.0,
            "claim_risk_tier": r[15],
            "claimant_name": r[16],
            "provider_name": r[17],
        })

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.get("/{investigation_id}")
def get_investigation_detail(
    investigation_id: str,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Retrieves full investigation dossier including linked claim, claimant, provider, and fraud indicators."""
    row = conn.execute(
        "SELECT * FROM investigations WHERE investigation_id = ?",
        (investigation_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")

    inv_dict = dict(row)

    # Linked claim info
    c_row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (inv_dict["primary_claim_id"],)).fetchone()
    claim_dict = dict(c_row) if c_row else {}

    # Indicators for the claim
    inds = [dict(r) for r in conn.execute(
        "SELECT indicator_code, pillar, severity, raw_points, canonical_evidence_token FROM fraud_indicators WHERE claim_id = ?",
        (inv_dict["primary_claim_id"],)
    ).fetchall()]

    return {
        "investigation": inv_dict,
        "claim": claim_dict,
        "indicators": inds,
    }


@router.post("")
def create_investigation(
    payload: InvestigationCreate,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Creates a new SIU investigation with next sequential ID."""
    # Verify primary claim exists
    c_row = conn.execute("SELECT claimant_id, claimed_amount_cents FROM claims WHERE claim_id = ?", (payload.primary_claim_id,)).fetchone()
    if not c_row:
        raise HTTPException(status_code=400, detail=f"Claim {payload.primary_claim_id} does not exist")

    clmt_id = payload.subject_claimant_id or c_row[0]
    prov_id = payload.subject_provider_id
    exposure = payload.estimated_exposure_cents or c_row[1]

    # Find highest investigation_id number
    max_id_row = conn.execute("SELECT MAX(investigation_id) FROM investigations").fetchone()
    if max_id_row and max_id_row[0]:
        max_num = int(max_id_row[0].split("-")[-1])
        new_id = f"INVG-2026-{max_num + 1:06d}"
    else:
        new_id = "INVG-2026-000001"

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn.execute("""
        INSERT INTO investigations (
            investigation_id, primary_claim_id, subject_claimant_id, subject_provider_id,
            investigation_status, priority, assigned_investigator_id,
            opened_at_utc, updated_at_utc, closed_at_utc, ruling_outcome,
            estimated_exposure_cents, recovered_clawback_cents, case_summary_notes
        ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, NULL, NULL, ?, 0, ?)
    """, (
        new_id, payload.primary_claim_id, clmt_id, prov_id,
        payload.priority, payload.assigned_investigator_id,
        now_utc, now_utc, exposure, payload.case_summary_notes
    ))
    conn.commit()

    return {
        "status": "CREATED",
        "investigation_id": new_id,
        "primary_claim_id": payload.primary_claim_id,
        "opened_at_utc": now_utc,
    }

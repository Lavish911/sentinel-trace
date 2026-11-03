"""
Investigation and SIU Case Management endpoints for SENTINEL//TRACE.
Directly interfaces with operational `investigations` and `immutable_events` tables.
Uses canonical db.operations lifecycle functions to ensure full event atomicity
and ST-EVT-V2 hash chain continuity under ARCH-ST-010.3.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import sqlite3
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

from backend.app.db.session import get_db
from db.operations import open_investigation, transition_investigation
from db.seed import EventChainEmitter

router = APIRouter()


class InvestigationCreate(BaseModel):
    primary_claim_id: str
    subject_claimant_id: Optional[str] = None
    subject_provider_id: Optional[str] = None
    priority: str = Field(default="P2_HIGH", pattern="^(P1_CRITICAL|P2_HIGH|P3_STANDARD)$")
    assigned_investigator_id: str = "SIU-AGENT-001"
    estimated_exposure_cents: Optional[int] = Field(default=None, ge=0)
    case_summary_notes: str = Field(..., min_length=5)


class InvestigationTransition(BaseModel):
    new_status: str = Field(
        ...,
        pattern="^(EVIDENCE_COLLECTION|SIU_FIELD_REVIEW|LEGAL_ESCALATION|CLOSED_CONFIRMED_FRAUD|CLOSED_CLEARED_BENIGN|CLOSED_INSUFFICIENT_EVIDENCE)$"
    )
    ruling_outcome: Optional[str] = Field(
        None,
        pattern="^(CONFIRMED_FRAUD|CLEARED_BENIGN|INSUFFICIENT_EVIDENCE)$"
    )
    notes: Optional[str] = None
    actor_id: str = "USR-SIU-001"


class InvestigationNoteCreate(BaseModel):
    note: str = Field(..., min_length=3)
    actor_id: str = "USR-SIU-001"


def get_operation_timestamp(conn: sqlite3.Connection) -> str:
    """Returns an ISO UTC timestamp strictly monotonic with respect to the latest event."""
    max_row = conn.execute("SELECT MAX(occurred_at_utc) FROM immutable_events").fetchone()
    max_evt = max_row[0] if max_row and max_row[0] else ""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if max_evt and now_utc <= max_evt:
        try:
            dt = datetime.fromisoformat(max_evt.replace("Z", "+00:00"))
            dt_next = dt + timedelta(seconds=1)
            return dt_next.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return now_utc
    return now_utc


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


@router.post("", status_code=201)
def create_investigation(
    payload: InvestigationCreate,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """
    Creates a new SIU investigation with next sequential ID using canonical db.operations.open_investigation.
    Guarantees INVESTIGATION_OPENED event emission and ST-EVT-V2 hash chain atomicity.
    """
    # 1. Verify primary claim exists
    c_row = conn.execute(
        "SELECT claimant_id, claimed_amount_cents FROM claims WHERE claim_id = ?",
        (payload.primary_claim_id,)
    ).fetchone()
    if not c_row:
        raise HTTPException(status_code=400, detail=f"Claim {payload.primary_claim_id} does not exist")

    # 2. Check for active open investigation on this claim
    active_inv = conn.execute(
        "SELECT investigation_id FROM investigations WHERE primary_claim_id = ? AND investigation_status NOT LIKE 'CLOSED_%'",
        (payload.primary_claim_id,)
    ).fetchone()
    if active_inv:
        raise HTTPException(
            status_code=400,
            detail=f"ERR_CONCURRENT_OPEN_INVESTIGATION_FORBIDDEN: Claim {payload.primary_claim_id} already has active investigation {active_inv[0]}"
        )

    clmt_id = payload.subject_claimant_id or c_row[0]
    prov_id = payload.subject_provider_id
    exposure = payload.estimated_exposure_cents if payload.estimated_exposure_cents is not None else c_row[1]

    # 3. Next sequential investigation ID (INVG-2026-XXXXXX)
    max_id_row = conn.execute("SELECT MAX(investigation_id) FROM investigations").fetchone()
    if max_id_row and max_id_row[0]:
        max_num = int(max_id_row[0].split("-")[-1])
        new_id = f"INVG-2026-{max_num + 1:06d}"
    else:
        new_id = "INVG-2026-000001"

    now_utc = get_operation_timestamp(conn)

    # 4. Atomic transaction & event emission via canonical db.operations
    emitter = EventChainEmitter(conn)
    emitter.sync_from_db()
    try:
        ev_id = open_investigation(
            conn=conn,
            emitter=emitter,
            investigation_id=new_id,
            claim_id=payload.primary_claim_id,
            claimant_id=clmt_id,
            provider_id=prov_id,
            priority=payload.priority,
            assigned_investigator_id=payload.assigned_investigator_id,
            opened_at_utc=now_utc,
            estimated_exposure_cents=exposure,
            case_summary_notes=payload.case_summary_notes,
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Database integrity violation: {e}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to create investigation: {e}")

    return {
        "status": "CREATED",
        "investigation_id": new_id,
        "primary_claim_id": payload.primary_claim_id,
        "event_id": ev_id,
        "opened_at_utc": now_utc,
    }


@router.patch("/{investigation_id}/status")
def transition_investigation_status(
    investigation_id: str,
    payload: InvestigationTransition,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """
    Transitions an active investigation to a new lifecycle state per ARCH-ST-010.3 FSM rules.
    Emits INVESTIGATION_STATUS_CHANGED or INVESTIGATION_CLOSED event into immutable_events.
    """
    row = conn.execute(
        "SELECT primary_claim_id, investigation_status, case_summary_notes, opened_at_utc FROM investigations WHERE investigation_id = ?",
        (investigation_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")

    claim_id, curr_status, curr_notes, opened_at = row
    if curr_status.startswith("CLOSED_"):
        raise HTTPException(
            status_code=400,
            detail=f"ERR_CLOSED_INVESTIGATION_IMMUTABLE: Investigation {investigation_id} is already in terminal state {curr_status}"
        )

    # Validate FSM progression per trg_investigations_fsm_upd
    valid_fsm = {
        "OPEN": {"EVIDENCE_COLLECTION", "SIU_FIELD_REVIEW", "CLOSED_CLEARED_BENIGN"},
        "EVIDENCE_COLLECTION": {"SIU_FIELD_REVIEW", "LEGAL_ESCALATION", "CLOSED_CONFIRMED_FRAUD", "CLOSED_CLEARED_BENIGN", "CLOSED_INSUFFICIENT_EVIDENCE"},
        "SIU_FIELD_REVIEW": {"LEGAL_ESCALATION", "CLOSED_CONFIRMED_FRAUD", "CLOSED_CLEARED_BENIGN", "CLOSED_INSUFFICIENT_EVIDENCE"},
        "LEGAL_ESCALATION": {"CLOSED_CONFIRMED_FRAUD", "CLOSED_CLEARED_BENIGN", "CLOSED_INSUFFICIENT_EVIDENCE"},
    }
    allowed_next = valid_fsm.get(curr_status, set())
    if payload.new_status not in allowed_next:
        raise HTTPException(
            status_code=400,
            detail=f"ERR_INVALID_INVESTIGATION_FSM_TRANSITION: Cannot transition from {curr_status} to {payload.new_status}"
        )

    is_closing = payload.new_status.startswith("CLOSED_")
    now_utc = get_operation_timestamp(conn)
    closed_at_utc = now_utc if is_closing else None
    ruling_outcome = payload.ruling_outcome

    if is_closing:
        expected_outcomes = {
            "CLOSED_CONFIRMED_FRAUD": "CONFIRMED_FRAUD",
            "CLOSED_CLEARED_BENIGN": "CLEARED_BENIGN",
            "CLOSED_INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
        }
        required_outcome = expected_outcomes.get(payload.new_status)
        if not ruling_outcome:
            ruling_outcome = required_outcome
        elif ruling_outcome != required_outcome:
            raise HTTPException(
                status_code=400,
                detail=f"Ruling outcome {ruling_outcome} does not match closure status {payload.new_status} (must be {required_outcome})"
            )

    emitter = EventChainEmitter(conn)
    emitter.sync_from_db()

    try:
        # If notes provided, update case_summary_notes first
        if payload.notes:
            updated_notes = f"{curr_notes}\n[{now_utc}] ({payload.actor_id}): {payload.notes.strip()}"
            conn.execute(
                "UPDATE investigations SET case_summary_notes = ? WHERE investigation_id = ?",
                (updated_notes, investigation_id)
            )

        ev_id = transition_investigation(
            conn=conn,
            emitter=emitter,
            investigation_id=investigation_id,
            new_status=payload.new_status,
            updated_at_utc=now_utc,
            actor_id=payload.actor_id,
            ruling_outcome=ruling_outcome,
            closed_at_utc=closed_at_utc,
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Database integrity violation: {e}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to transition investigation: {e}")

    return {
        "status": "TRANSITIONED",
        "investigation_id": investigation_id,
        "previous_status": curr_status,
        "new_status": payload.new_status,
        "ruling_outcome": ruling_outcome,
        "event_id": ev_id,
        "updated_at_utc": now_utc,
    }


@router.post("/{investigation_id}/notes")
def add_investigation_note(
    investigation_id: str,
    payload: InvestigationNoteCreate,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Appends an evidence note to an active investigation."""
    row = conn.execute(
        "SELECT investigation_status, case_summary_notes, opened_at_utc FROM investigations WHERE investigation_id = ?",
        (investigation_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")

    status, curr_notes, opened_at = row
    if status.startswith("CLOSED_"):
        raise HTTPException(
            status_code=400,
            detail=f"ERR_CLOSED_INVESTIGATION_IMMUTABLE: Cannot add notes to closed investigation {investigation_id}"
        )

    now_utc = get_operation_timestamp(conn)
    updated_notes = f"{curr_notes}\n[{now_utc}] ({payload.actor_id}): {payload.note.strip()}"

    try:
        conn.execute(
            "UPDATE investigations SET case_summary_notes = ?, updated_at_utc = ? WHERE investigation_id = ?",
            (updated_notes, now_utc, investigation_id)
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Database integrity violation: {e}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to update investigation notes: {e}")

    return {
        "status": "NOTE_ADDED",
        "investigation_id": investigation_id,
        "case_summary_notes": updated_notes,
        "updated_at_utc": now_utc,
    }


@router.get("/{investigation_id}/timeline")
def get_investigation_timeline(
    investigation_id: str,
    conn: sqlite3.Connection = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Returns chronological immutable events directly related to this investigation."""
    rows = conn.execute("""
        SELECT 
            sequence_no, event_id, event_type, entity_type, entity_id,
            claim_id, actor_id, occurred_at_utc, payload_json,
            payload_sha256, prev_event_hash, event_hash
        FROM immutable_events
        WHERE entity_id = ? OR payload_json LIKE ?
        ORDER BY sequence_no ASC
    """, (investigation_id, f'%"{investigation_id}"%')).fetchall()

    events = []
    for r in rows:
        p = {}
        if r[8]:
            try:
                p = json.loads(r[8])
            except Exception:
                pass
        events.append({
            "sequence_no": r[0],
            "event_id": r[1],
            "event_type": r[2],
            "entity_type": r[3],
            "entity_id": r[4],
            "claim_id": r[5],
            "actor_id": r[6],
            "occurred_at_utc": r[7],
            "payload": p,
            "payload_sha256": r[9],
            "prev_event_hash": r[10],
            "event_hash": r[11],
        })
    return events

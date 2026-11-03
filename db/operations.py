"""
SENTINEL//TRACE — Atomic Application Operations & Transaction Management
========================================================================
Implements transaction boundaries for business state mutations and their
corresponding ST-EVT-V2 immutable events.

Guarantees:
1. Atomicity: Both the business state mutation and event commit together, or
   both roll back together.
2. Failure Isolation: If event insertion fails (or is rejected), the entity mutation
   is completely rolled back to its pre-operation state.
3. Anti-Phantom Protection: If entity mutation fails, no phantom event is created.
4. Emitter Synchronization: The in-memory EventChainEmitter sequence number and
   tip hash are restored on rollback, preserving hash chain integrity.
"""

from __future__ import annotations

import contextlib
import sqlite3
import uuid
from typing import Any, Callable, Generator, Optional

from db.engine import canonical_json_str
from db.seed import EventChainEmitter, _compute_line_item_fp


@contextlib.contextmanager
def atomic_transaction(
    conn: sqlite3.Connection,
    emitter: Optional[EventChainEmitter] = None,
) -> Generator[None, None, None]:
    """
    Context manager establishing a SAVEPOINT boundary for an application operation.
    Rolls back both database changes and in-memory emitter state upon any exception.
    """
    sp_id = f"sp_op_{uuid.uuid4().hex[:12]}"
    conn.execute(f"SAVEPOINT {sp_id}")
    emitter_snapshot = emitter.snapshot() if emitter is not None else None
    try:
        yield
        conn.execute(f"RELEASE SAVEPOINT {sp_id}")
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {sp_id}")
        conn.execute(f"RELEASE SAVEPOINT {sp_id}")
        if emitter is not None and emitter_snapshot is not None:
            emitter.restore(emitter_snapshot)
        raise


def submit_claim(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    claim_id: str,
    policy_id: str,
    claimant_id: str,
    incident_id: str,
    submitted_at_utc: str,
    claimed_cents: int,
    payout_cap_cents: int,
    adjustor_id: str = "USR-ADJ-001",
) -> str:
    """Atomically inserts claim in SUBMITTED state and emits CLAIM_SUBMITTED event."""
    with atomic_transaction(conn, emitter):
        conn.execute(
            """
            INSERT INTO claims (
                claim_id, policy_id, claimant_id, incident_id, claim_status,
                submitted_at_utc, claimed_amount_cents, approved_amount_cents,
                historical_approved_cents, reserved_authorized_cents, gross_disbursed_cents,
                clawed_back_cents, net_paid_cents, payout_cap_cents, adjustor_id,
                siu_referred, latest_ief_score, latest_risk_tier, scoring_evidence_sha256
            ) VALUES (?, ?, ?, ?, 'SUBMITTED', ?, ?, 0, 0, 0, 0, 0, 0, ?, ?, 0, 0.0, 'LOW', NULL)
            """,
            (
                claim_id,
                policy_id,
                claimant_id,
                incident_id,
                submitted_at_utc,
                claimed_cents,
                payout_cap_cents,
                adjustor_id,
            ),
        )
        ev_id = emitter.emit(
            "CLAIM_SUBMITTED",
            "Claim",
            claim_id,
            claim_id,
            "SYSTEM_INGEST",
            submitted_at_utc,
            {
                "claim_id": claim_id,
                "claim_status": "SUBMITTED",
                "claimed_amount_cents": claimed_cents,
                "incident_id": incident_id,
                "policy_id": policy_id,
            },
        )
        return ev_id


def place_claim_on_siu_hold(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    claim_id: str,
    actor_id: str,
    occurred_at_utc: str,
) -> str:
    """Atomically places claim on SIU_HOLD and emits CLAIM_SIU_HOLD_PLACED event."""
    with atomic_transaction(conn, emitter):
        conn.execute(
            "UPDATE claims SET claim_status = 'SIU_HOLD' WHERE claim_id = ?",
            (claim_id,),
        )
        ev_id = emitter.emit(
            "CLAIM_SIU_HOLD_PLACED",
            "Claim",
            claim_id,
            claim_id,
            actor_id,
            occurred_at_utc,
            {
                "claim_id": claim_id,
                "claim_status": "SIU_HOLD",
            },
        )
        return ev_id


def release_claim_from_siu_hold(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    claim_id: str,
    target_status: str,
    cleared_investigation_id: str,
    actor_id: str,
    occurred_at_utc: str,
) -> str:
    """
    Atomically transitions a claim out of SIU_HOLD to a target approved/resume state
    after a valid post-hold CLOSED_CLEARED_BENIGN investigation outcome.
    """
    with atomic_transaction(conn, emitter):
        conn.execute(
            "UPDATE claims SET claim_status = ? WHERE claim_id = ?",
            (target_status, claim_id),
        )
        approved_cents = conn.execute(
            "SELECT approved_amount_cents FROM claims WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()[0]
        ev_id = emitter.emit(
            "CLAIM_APPROVED",
            "Claim",
            claim_id,
            claim_id,
            actor_id,
            occurred_at_utc,
            {
                "approved_amount_cents": approved_cents,
                "claim_id": claim_id,
                "claim_status": target_status,
                "cleared_investigation_id": cleared_investigation_id,
                "previous_status": "SIU_HOLD",
                "release_reason": "CLEARED_BENIGN",
            },
        )
        return ev_id


def deny_claim(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    claim_id: str,
    actor_id: str,
    occurred_at_utc: str,
) -> str:
    """Atomically transitions claim to DENIED and emits CLAIM_DENIED event."""
    with atomic_transaction(conn, emitter):
        conn.execute(
            "UPDATE claims SET claim_status = 'DENIED' WHERE claim_id = ?",
            (claim_id,),
        )
        ev_id = emitter.emit(
            "CLAIM_DENIED",
            "Claim",
            claim_id,
            claim_id,
            actor_id,
            occurred_at_utc,
            {
                "claim_id": claim_id,
                "claim_status": "DENIED",
            },
        )
        return ev_id


def submit_invoice(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    invoice_id: str,
    claim_id: str,
    provider_id: str,
    provider_invoice_number: str,
    service_start_utc: str,
    service_end_utc: str,
    submitted_at_utc: str,
    cpt_or_line_code: str,
    billed_cents: int,
    invoice_status: str = "SUBMITTED",
    duplicate_of_invoice_id: Optional[str] = None,
) -> str:
    """Atomically inserts invoice and emits INVOICE_SUBMITTED event."""
    with atomic_transaction(conn, emitter):
        fp = _compute_line_item_fp(
            cpt_or_line_code,
            service_start_utc,
            service_end_utc,
            billed_cents,
        )
        conn.execute(
            """
            INSERT INTO invoices VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, ?
            )
            """,
            (
                invoice_id,
                claim_id,
                provider_id,
                provider_invoice_number,
                invoice_status,
                service_start_utc,
                service_end_utc,
                submitted_at_utc,
                cpt_or_line_code,
                fp,
                billed_cents,
                duplicate_of_invoice_id,
            ),
        )
        ev_id = emitter.emit(
            "INVOICE_SUBMITTED",
            "Invoice",
            invoice_id,
            claim_id,
            "SYSTEM_SEED",
            submitted_at_utc,
            {
                "billed_cents": billed_cents,
                "claim_id": claim_id,
                "invoice_id": invoice_id,
                "invoice_status": invoice_status,
                "provider_id": provider_id,
            },
        )
        return ev_id


def approve_invoice(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    invoice_id: str,
    approved_cents: int,
    approved_at_utc: str,
    actor_id: str = "USR-ADJ-001",
) -> tuple[str, str]:
    """
    Atomically updates invoice to APPROVED (cascading approved balances to the parent claim)
    and emits both INVOICE_APPROVED and CLAIM_APPROVED events.
    """
    with atomic_transaction(conn, emitter):
        conn.execute(
            """
            UPDATE invoices
               SET invoice_status = 'APPROVED',
                   approved_cents = ?,
                   historical_approved_cents = ?
             WHERE invoice_id = ?
            """,
            (approved_cents, approved_cents, invoice_id),
        )
        claim_id = conn.execute(
            "SELECT claim_id FROM invoices WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()[0]

        ev_inv = emitter.emit(
            "INVOICE_APPROVED",
            "Invoice",
            invoice_id,
            claim_id,
            actor_id,
            approved_at_utc,
            {
                "approved_cents": approved_cents,
                "claim_id": claim_id,
                "invoice_id": invoice_id,
                "invoice_status": "APPROVED",
            },
        )
        ev_clm = emitter.emit(
            "CLAIM_APPROVED",
            "Claim",
            claim_id,
            claim_id,
            actor_id,
            approved_at_utc,
            {
                "approved_amount_cents": approved_cents,
                "claim_id": claim_id,
                "claim_status": "APPROVED",
                "historical_approved_cents": approved_cents,
            },
        )
        return ev_inv, ev_clm


def open_investigation(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    investigation_id: str,
    claim_id: str,
    claimant_id: Optional[str],
    provider_id: Optional[str],
    priority: str,
    assigned_investigator_id: str,
    opened_at_utc: str,
    estimated_exposure_cents: int,
    case_summary_notes: str,
) -> str:
    """Atomically inserts investigation in OPEN state and emits INVESTIGATION_OPENED event."""
    with atomic_transaction(conn, emitter):
        conn.execute(
            """
            INSERT INTO investigations VALUES (
                ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, NULL, NULL, ?, 0, ?
            )
            """,
            (
                investigation_id,
                claim_id,
                claimant_id,
                provider_id,
                priority,
                assigned_investigator_id,
                opened_at_utc,
                opened_at_utc,
                estimated_exposure_cents,
                case_summary_notes,
            ),
        )
        ev_id = emitter.emit(
            "INVESTIGATION_OPENED",
            "Investigation",
            investigation_id,
            claim_id,
            "USR-SIU-001",
            opened_at_utc,
            {
                "assigned_investigator_id": assigned_investigator_id,
                "claim_id": claim_id,
                "investigation_id": investigation_id,
                "investigation_status": "OPEN",
                "priority": priority,
            },
        )
        return ev_id


def transition_investigation(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    investigation_id: str,
    new_status: str,
    updated_at_utc: str,
    actor_id: str,
    ruling_outcome: Optional[str] = None,
    closed_at_utc: Optional[str] = None,
) -> str:
    """
    Atomically updates investigation status (non-terminal or terminal closure)
    and emits INVESTIGATION_STATUS_CHANGED or INVESTIGATION_CLOSED event.
    """
    with atomic_transaction(conn, emitter):
        row = conn.execute(
            "SELECT primary_claim_id, investigation_status FROM investigations WHERE investigation_id = ?",
            (investigation_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Investigation not found: {investigation_id}")
        claim_id, prev_status = row

        if new_status.startswith("CLOSED_"):
            if not ruling_outcome or not closed_at_utc:
                raise ValueError("Closing investigation requires ruling_outcome and closed_at_utc")
            conn.execute(
                """
                UPDATE investigations
                   SET investigation_status = ?,
                       ruling_outcome = ?,
                       updated_at_utc = ?,
                       closed_at_utc = ?
                 WHERE investigation_id = ?
                """,
                (new_status, ruling_outcome, updated_at_utc, closed_at_utc, investigation_id),
            )
            ev_id = emitter.emit(
                "INVESTIGATION_CLOSED",
                "Investigation",
                investigation_id,
                claim_id,
                actor_id,
                closed_at_utc,
                {
                    "claim_id": claim_id,
                    "closed_at_utc": closed_at_utc,
                    "investigation_id": investigation_id,
                    "investigation_status": new_status,
                    "ruling_outcome": ruling_outcome,
                },
            )
        else:
            conn.execute(
                """
                UPDATE investigations
                   SET investigation_status = ?,
                       updated_at_utc = ?
                 WHERE investigation_id = ?
                """,
                (new_status, updated_at_utc, investigation_id),
            )
            ev_id = emitter.emit(
                "INVESTIGATION_STATUS_CHANGED",
                "Investigation",
                investigation_id,
                claim_id,
                actor_id,
                updated_at_utc,
                {
                    "claim_id": claim_id,
                    "investigation_id": investigation_id,
                    "investigation_status": new_status,
                    "previous_status": prev_status,
                },
            )
        return ev_id


def authorize_payment(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    payment_id: str,
    claim_id: str,
    invoice_id: str,
    provider_id: str,
    amount_cents: int,
    idempotency_key: str,
    created_at_utc: str,
    authorized_by: str = "USR-FIN-001",
) -> str:
    """Atomically inserts payment in AUTHORIZED status and emits PAYMENT_AUTHORIZED event."""
    with atomic_transaction(conn, emitter):
        conn.execute(
            """
            INSERT INTO payments VALUES (
                ?, ?, ?, 'PROVIDER', NULL, ?, 'AUTHORIZED', ?, 0, 0, 0,
                ?, ?, NULL, NULL, ?, NULL, NULL, NULL
            )
            """,
            (
                payment_id,
                claim_id,
                invoice_id,
                provider_id,
                amount_cents,
                idempotency_key,
                created_at_utc,
                authorized_by,
            ),
        )
        ev_id = emitter.emit(
            "PAYMENT_AUTHORIZED",
            "Payment",
            payment_id,
            claim_id,
            authorized_by,
            created_at_utc,
            {
                "amount_cents": amount_cents,
                "claim_id": claim_id,
                "invoice_id": invoice_id,
                "payment_id": payment_id,
                "payment_status": "AUTHORIZED",
                "recipient_provider_id": provider_id,
            },
        )
        return ev_id


def disburse_payment(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    payment_id: str,
    external_bank_tx_ref: str,
    disbursed_at_utc: str,
    actor_id: str = "USR-FIN-001",
) -> str:
    """
    Atomically transitions an AUTHORIZED payment to DISBURSED.
    (Note: trg_payments_validate_upd checks that PAYMENT_AUTHORIZED event exists).
    Then emits PAYMENT_DISBURSED event.
    """
    with atomic_transaction(conn, emitter):
        row = conn.execute(
            "SELECT claim_id, invoice_id, amount_cents FROM payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Payment not found: {payment_id}")
        claim_id, invoice_id, amount_cents = row

        conn.execute(
            """
            UPDATE payments
               SET payment_status = 'DISBURSED',
                   disbursed_amount_cents = ?,
                   net_paid_cents = ?,
                   disbursed_at_utc = ?,
                   external_bank_tx_ref = ?
             WHERE payment_id = ?
            """,
            (amount_cents, amount_cents, disbursed_at_utc, external_bank_tx_ref, payment_id),
        )
        ev_id = emitter.emit(
            "PAYMENT_DISBURSED",
            "Payment",
            payment_id,
            claim_id,
            actor_id,
            disbursed_at_utc,
            {
                "amount_cents": amount_cents,
                "claim_id": claim_id,
                "disbursed_amount_cents": amount_cents,
                "external_bank_tx_ref": external_bank_tx_ref,
                "invoice_id": invoice_id,
                "payment_id": payment_id,
                "payment_status": "DISBURSED",
            },
        )
        return ev_id


def cancel_payment(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    payment_id: str,
    reason_code: str,
    reversed_at_utc: str,
    actor_id: str = "USR-FIN-001",
) -> str:
    """
    Atomically cancels an AUTHORIZED payment.
    trg_payments_validate_upd requires PAYMENT_CANCELLED event before the update;
    atomic_transaction ensures that if the update fails, the event is rolled back.
    """
    with atomic_transaction(conn, emitter):
        row = conn.execute(
            "SELECT claim_id, amount_cents FROM payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Payment not found: {payment_id}")
        claim_id, amount_cents = row

        ev_id = emitter.emit(
            "PAYMENT_CANCELLED",
            "Payment",
            payment_id,
            claim_id,
            actor_id,
            reversed_at_utc,
            {
                "amount_cents": amount_cents,
                "claim_id": claim_id,
                "payment_id": payment_id,
                "payment_status": "CANCELLED",
                "reason_code": reason_code,
            },
        )
        conn.execute(
            """
            UPDATE payments
               SET payment_status = 'CANCELLED',
                   reversed_at_utc = ?,
                   cancel_reason = ?
             WHERE payment_id = ?
            """,
            (reversed_at_utc, reason_code, payment_id),
        )
        return ev_id


def clawback_payment(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    payment_id: str,
    clawback_cents: int,
    reversed_at_utc: str,
    actor_id: str = "USR-SIU-001",
) -> str:
    """
    Atomically applies a full or incremental clawback to a DISBURSED or REVERSED_CLAWBACK payment.
    trg_payments_validate_upd requires PAYMENT_CLAWBACK_REVERSED event before the update;
    atomic_transaction ensures that if the update fails, the event is rolled back.
    """
    with atomic_transaction(conn, emitter):
        row = conn.execute(
            "SELECT claim_id, invoice_id, amount_cents, disbursed_amount_cents, clawed_back_cents FROM payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Payment not found: {payment_id}")
        claim_id, invoice_id, amount_cents, disbursed_cents, current_clawback = row

        new_total_clawback = current_clawback + clawback_cents
        new_net_paid = disbursed_cents - new_total_clawback

        ev_id = emitter.emit(
            "PAYMENT_CLAWBACK_REVERSED",
            "Payment",
            payment_id,
            claim_id,
            actor_id,
            reversed_at_utc,
            {
                "amount_cents": amount_cents,
                "claim_id": claim_id,
                "clawed_back_cents": new_total_clawback,
                "invoice_id": invoice_id,
                "net_paid_cents": new_net_paid,
                "payment_id": payment_id,
                "payment_status": "REVERSED_CLAWBACK",
            },
        )
        conn.execute(
            """
            UPDATE payments
               SET payment_status = 'REVERSED_CLAWBACK',
                   clawed_back_cents = ?,
                   net_paid_cents = ?,
                   reversed_at_utc = ?
             WHERE payment_id = ?
            """,
            (new_total_clawback, new_net_paid, reversed_at_utc, payment_id),
        )
        return ev_id


def record_ingestion_exception(
    conn: sqlite3.Connection,
    emitter: EventChainEmitter,
    exception_id: str,
    attempted_claim_id: str,
    rejected_policy_id: str,
    claimant_id: str,
    incident_id: str,
    attempted_claimed_cents: int,
    exception_code: str,
    occurred_at_utc: str,
    actor_id: str = "SYSTEM_INGEST",
) -> str:
    """Atomically records an ingestion exception audit row and event."""
    with atomic_transaction(conn, emitter):
        raw_payload = {
            "attempted_claim_id": attempted_claim_id,
            "attempted_claimed_cents": attempted_claimed_cents,
            "claimant_id": claimant_id,
            "exception_code": exception_code,
            "incident_id": incident_id,
            "rejected_policy_id": rejected_policy_id,
        }
        ev_id = emitter.emit(
            "INGESTION_EXCEPTION_RECORDED",
            "IngestionException",
            exception_id,
            None,
            actor_id,
            occurred_at_utc,
            raw_payload,
        )
        conn.execute(
            """
            INSERT INTO ingestion_exceptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exception_id,
                attempted_claim_id,
                rejected_policy_id,
                claimant_id,
                incident_id,
                attempted_claimed_cents,
                exception_code,
                canonical_json_str(raw_payload),
                occurred_at_utc,
                ev_id,
            ),
        )
        return ev_id

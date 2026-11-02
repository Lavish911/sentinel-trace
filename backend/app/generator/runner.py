"""
Dataset Generation Orchestrator for SENTINEL//TRACE (Milestone B).
Executes end-to-end deterministic generation:
1. Operational schema initialization & UDF registration
2. Operational entity & source fact generation
3. Causal Merkle event chain execution & financial lifecycle updates
4. Operational indicator detection (IND-01..IND-15)
5. 10-Stage IEF scoring pipeline & trigger-compliant claim state updates
6. Independent ground truth database population
7. Full verification gate assertions
"""

import sys
import os
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from backend.app.generator.config import (
    DEFAULT_SEED, OPS_SQL_PATH, TRIGS_SQL_PATH,
    DEFAULT_OPERATIONAL_DB, DEFAULT_GROUND_TRUTH_DB,
    COUNT_CLAIMANTS, COUNT_POLICIES, COUNT_INCIDENTS, COUNT_CLAIMS,
    COUNT_PROVIDERS, COUNT_INVOICES, COUNT_PAYMENTS, COUNT_RELATIONSHIP_EDGES,
    COUNT_FRAUD_INDICATORS, COUNT_INVESTIGATIONS, COUNT_IMMUTABLE_EVENTS,
    COUNT_INGESTION_EXCEPTIONS
)
from backend.app.db.udfs import register_udfs
from backend.app.generator.id_factory import (
    claimant_id, policy_id, incident_id, provider_id,
    invoice_id, payment_id, edge_id, indicator_id,
    investigation_id, event_id, exception_id, ClaimIdFactory
)
from backend.app.generator.entities import generate_entities
from backend.app.generator.relationships import generate_relationships
from backend.app.generator.financial import generate_financials
from backend.app.generator.events import EventChainBuilder
from backend.app.generator.ground_truth import init_ground_truth_db, populate_ground_truth
from backend.app.generator.detector import OperationalIndicatorDetector, deduplicate_and_persist_indicators
from backend.app.generator.scorer import OperationalScorer
from backend.app.generator.validator import DatasetValidator


def create_operational_connection(db_path: Path) -> sqlite3.Connection:
    """Creates a configured connection to operational SQLite database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA recursive_triggers = ON;")
    conn.execute("PRAGMA trusted_schema = ON;")
    register_udfs(conn)
    return conn


def init_operational_db(db_path: Path):
    """Initializes the ARCH-ST-010.2 operational schema."""
    if db_path.exists():
        db_path.unlink()
        
    conn = create_operational_connection(db_path)
    ops_sql = OPS_SQL_PATH.read_text(encoding="utf-8")
    trigs_sql = TRIGS_SQL_PATH.read_text(encoding="utf-8")
    conn.executescript(ops_sql)
    conn.executescript(trigs_sql)
    conn.commit()
    conn.close()


def run_generator(
    seed: int = DEFAULT_SEED,
    op_db_path: Path = DEFAULT_OPERATIONAL_DB,
    gt_db_path: Path = DEFAULT_GROUND_TRUTH_DB,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Executes complete deterministic dataset generation and verification.
    """
    if verbose:
        print("=" * 80)
        print(f"SENTINEL//TRACE — DETERMINISTIC DATASET GENERATOR (SEED={seed})")
        print("=" * 80)

    # 1. Initialize Databases
    if verbose:
        print("[1/7] Initializing ARCH-ST-010.2 Operational & Ground-Truth Databases...")
    init_operational_db(op_db_path)
    init_ground_truth_db(gt_db_path)
    
    op_conn = create_operational_connection(op_db_path)
    event_builder = EventChainBuilder()

    # 2. Generate Entities
    if verbose:
        print("[2/7] Generating Operational Entities & Source Facts...")
    claimants, policies, incidents, claims, providers, claim_factory, scenario_metadata = generate_entities(seed=seed)

    # Insert Claimants
    op_conn.executemany(
        """
        INSERT INTO claimants (
            claimant_id, full_name, dob_iso, tax_id_hash, phone_e164,
            email_norm, address_norm, bank_routing_hash, bank_account_hash, created_at_utc
        ) VALUES (:claimant_id, :full_name, :dob_iso, :tax_id_hash, :phone_e164,
                  :email_norm, :address_norm, :bank_routing_hash, :bank_account_hash, :created_at_utc)
        """,
        claimants
    )

    # Insert Policies
    op_conn.executemany(
        """
        INSERT INTO policies (
            policy_id, claimant_id, policy_number, line_of_business, policy_status,
            effective_start_utc, effective_end_utc, bound_at_utc,
            coverage_limit_cents, deductible_cents, annual_premium_cents
        ) VALUES (:policy_id, :claimant_id, :policy_number, :line_of_business, :policy_status,
                  :effective_start_utc, :effective_end_utc, :bound_at_utc,
                  :coverage_limit_cents, :deductible_cents, :annual_premium_cents)
        """,
        policies
    )

    # Insert Providers
    op_conn.executemany(
        """
        INSERT INTO providers (
            provider_id, provider_name, provider_type, npi_or_license_id,
            tax_id_hash, phone_e164, address_norm, bank_routing_hash,
            bank_account_hash, network_tier, created_at_utc
        ) VALUES (:provider_id, :provider_name, :provider_type, :npi_or_license_id,
                  :tax_id_hash, :phone_e164, :address_norm, :bank_routing_hash,
                  :bank_account_hash, :network_tier, :created_at_utc)
        """,
        providers
    )

    # Insert Incidents
    op_conn.executemany(
        """
        INSERT INTO incidents (
            incident_id, incident_timestamp_utc, reported_timestamp_utc,
            incident_type, jurisdiction_state, location_address_norm,
            location_geohash, police_report_number, weather_condition, description
        ) VALUES (:incident_id, :incident_timestamp_utc, :reported_timestamp_utc,
                  :incident_type, :jurisdiction_state, :location_address_norm,
                  :location_geohash, :police_report_number, :weather_condition, :description)
        """,
        incidents
    )

    # Insert Claims (initial state: SUBMITTED, 0 balances, 0 scores)
    op_conn.executemany(
        """
        INSERT INTO claims (
            claim_id, policy_id, claimant_id, incident_id, claim_status,
            submitted_at_utc, claimed_amount_cents, approved_amount_cents,
            historical_approved_cents, reserved_authorized_cents,
            gross_disbursed_cents, clawed_back_cents, net_paid_cents,
            payout_cap_cents, adjustor_id, siu_referred, latest_ief_score,
            latest_risk_tier, scoring_evidence_sha256
        ) VALUES (:claim_id, :policy_id, :claimant_id, :incident_id, :claim_status,
                  :submitted_at_utc, :claimed_amount_cents, :approved_amount_cents,
                  :historical_approved_cents, :reserved_authorized_cents,
                  :gross_disbursed_cents, :clawed_back_cents, :net_paid_cents,
                  :payout_cap_cents, :adjustor_id, :siu_referred, :latest_ief_score,
                  :latest_risk_tier, :scoring_evidence_sha256)
        """,
        claims
    )
    op_conn.commit()

    # 3. Generate Relationships & Withheld Edges
    if verbose:
        print("[3/7] Generating Relationship Graph & Withholding Cross-Ring Bridges...")
    edges, withheld_edges = generate_relationships(claimants, claims, providers, scenario_metadata, seed=seed)
    
    op_conn.executemany(
        """
        INSERT INTO relationship_edges (
            edge_id, edge_type, source_entity_type, source_claimant_id, source_provider_id,
            target_entity_type, target_claimant_id, target_provider_id, canonical_src_key,
            canonical_dst_key, strength_weight, evidence_count, first_observed_utc,
            last_observed_utc, supporting_claim_id, is_active
        ) VALUES (:edge_id, :edge_type, :source_entity_type, :source_claimant_id, :source_provider_id,
                  :target_entity_type, :target_claimant_id, :target_provider_id, :canonical_src_key,
                  :canonical_dst_key, :strength_weight, :evidence_count, :first_observed_utc,
                  :last_observed_utc, :supporting_claim_id, :is_active)
        """,
        edges
    )
    op_conn.commit()

    # 4. Generate Financials, Invoices, and Payments
    if verbose:
        print("[4/7] Generating Financials & Invoices...")
    invoices, payments, lifecycle_plan = generate_financials(claims, providers, scenario_metadata, seed=seed)

    op_conn.executemany(
        """
        INSERT INTO invoices (
            invoice_id, claim_id, provider_id, provider_invoice_number, invoice_status,
            service_start_utc, service_end_utc, submitted_at_utc, cpt_or_line_code,
            line_item_fingerprint, billed_cents, approved_cents, historical_approved_cents,
            reserved_authorized_cents, gross_disbursed_cents, clawed_back_cents,
            net_paid_cents, duplicate_of_invoice_id
        ) VALUES (:invoice_id, :claim_id, :provider_id, :provider_invoice_number, :invoice_status,
                  :service_start_utc, :service_end_utc, :submitted_at_utc, :cpt_or_line_code,
                  :line_item_fingerprint, :billed_cents, :approved_cents, :historical_approved_cents,
                  :reserved_authorized_cents, :gross_disbursed_cents, :clawed_back_cents,
                  :net_paid_cents, :duplicate_of_invoice_id)
        """,
        invoices
    )
    op_conn.commit()

    # Helper to insert freshly added events into immutable_events sequentially
    last_inserted_event_idx = 0

    def sync_events_to_db(last_idx: int) -> int:
        pending = event_builder.events[last_idx:]
        if not pending:
            return last_idx
        op_conn.executemany(
            """
            INSERT INTO immutable_events (
                sequence_no, event_id, event_type, entity_type, entity_id, claim_id,
                actor_id, occurred_at_utc, payload_json, payload_sha256, prev_event_hash, event_hash
            ) VALUES (:sequence_no, :event_id, :event_type, :entity_type, :entity_id, :claim_id,
                      :actor_id, :occurred_at_utc, :payload_json, :payload_sha256, :prev_event_hash, :event_hash)
            """,
            pending
        )
        op_conn.commit()
        return len(event_builder.events)

    # 5. Build Causal Merkle Event Chain & Execute Lifecycle FSM
    if verbose:
        print("[5/7] Executing Causal Merkle Event Chain (Target: 19,615 Events)...")
        
    # 5.1 Event: INGESTION_EXCEPTION_RECORDED (25 events) & Ingestion Exceptions
    iex_records = []
    for i in range(COUNT_INGESTION_EXCEPTIONS):
        iex_id = exception_id(i + 1)
        att_cid = f"CLM-2026-99{i+1:04d}"
        rej_pid = f"POL-2026-99{i+1:04d}"
        clmt_id = claimant_id(i + 1)
        inc_id = incident_id(i + 1)
        cents = 250000 + i * 10000
        det_ts = (datetime(2026, 1, 1, 0, 0, 0) + timedelta(seconds=i * 120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Add event first to satisfy FK immutable_event_id
        ev = event_builder.add_event(
            event_type="INGESTION_EXCEPTION_RECORDED",
            entity_type="IngestionException",
            entity_id=iex_id,
            claim_id=None,
            actor_id="SYSTEM",
            occurred_at_utc=det_ts,
            payload_dict={"exception_code": "ERR_NONEXISTENT_POLICY_REFERENCE", "exception_id": iex_id, "rejected_policy_id": rej_pid}
        )
        
        iex_records.append((
            iex_id, att_cid, rej_pid, clmt_id, inc_id, cents,
            "ERR_NONEXISTENT_POLICY_REFERENCE",
            event_builder.events[-1]["payload_json"],
            det_ts,
            ev["event_id"]
        ))

    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    # Insert ingestion exceptions
    op_conn.executemany(
        """
        INSERT INTO ingestion_exceptions (
            exception_id, attempted_claim_id, rejected_policy_id, claimant_id,
            incident_id, attempted_claimed_cents, exception_code, raw_payload_json,
            detected_at_utc, immutable_event_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        iex_records
    )
    op_conn.commit()

    # 5.2 Events: CLAIM_SUBMITTED (5,000 events)
    for c in claims:
        event_builder.add_event(
            event_type="CLAIM_SUBMITTED",
            entity_type="Claim",
            entity_id=c["claim_id"],
            claim_id=c["claim_id"],
            actor_id="SYSTEM",
            occurred_at_utc=c["submitted_at_utc"],
            payload_dict={"claim_id": c["claim_id"], "claimed_amount_cents": c["claimed_amount_cents"]}
        )
    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    # 5.3 Events: INVOICE_SUBMITTED (7,500 events)
    for inv in invoices:
        event_builder.add_event(
            event_type="INVOICE_SUBMITTED",
            entity_type="Invoice",
            entity_id=inv["invoice_id"],
            claim_id=inv["claim_id"],
            actor_id="SYSTEM",
            occurred_at_utc=inv["submitted_at_utc"],
            payload_dict={"billed_cents": inv["billed_cents"], "claim_id": inv["claim_id"], "invoice_id": inv["invoice_id"]}
        )
    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    # 5.4 Lifecycle Transitions: Invoices Approved (1,200) & Claims Approved (1,200)
    # Trigger trg_invoices_sync_claim_au cascades claim to APPROVED!
    for inv_idx, inv in enumerate(lifecycle_plan["approved_invoices"]):
        invid = inv["invoice_id"]
        cid = inv["claim_id"]
        app_cents = inv["billed_cents"]
        app_ts = (datetime(2026, 1, 15, 0, 0, 0) + timedelta(seconds=inv_idx * 200)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        event_builder.add_event(
            event_type="INVOICE_APPROVED",
            entity_type="Invoice",
            entity_id=invid,
            claim_id=cid,
            actor_id="USR-ADJ-001",
            occurred_at_utc=app_ts,
            payload_dict={"approved_cents": app_cents, "claim_id": cid, "invoice_id": invid}
        )
        event_builder.add_event(
            event_type="CLAIM_APPROVED",
            entity_type="Claim",
            entity_id=cid,
            claim_id=cid,
            actor_id="USR-ADJ-001",
            occurred_at_utc=app_ts,
            payload_dict={"approved_amount_cents": app_cents, "claim_id": cid}
        )

    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    # Update 1,200 invoices to APPROVED (cascades claims to APPROVED via trigger)
    for inv in lifecycle_plan["approved_invoices"]:
        invid = inv["invoice_id"]
        app_cents = inv["billed_cents"]
        op_conn.execute(
            """
            UPDATE invoices
            SET invoice_status = 'APPROVED',
                approved_cents = ?,
                historical_approved_cents = ?
            WHERE invoice_id = ?
            """,
            (app_cents, app_cents, invid)
        )
    op_conn.commit()

    # 5.5 Payments Authorized (4,115) & Blocked (85)
    auth_payments = [p for p in payments if p["payment_status"] == "AUTHORIZED"]
    blocked_payments = [p for p in payments if p["payment_status"] != "AUTHORIZED"]
    assert len(auth_payments) == 4115
    assert len(blocked_payments) == 85
    
    for p in auth_payments:
        event_builder.add_event(
            event_type="PAYMENT_AUTHORIZED",
            entity_type="Payment",
            entity_id=p["payment_id"],
            claim_id=p["claim_id"],
            actor_id="USR-FIN-001",
            occurred_at_utc=p["created_at_utc"],
            payload_dict={
                "amount_cents": p["amount_cents"],
                "claim_id": p["claim_id"],
                "invoice_id": p["invoice_id"],
                "payment_id": p["payment_id"],
                "payment_status": "AUTHORIZED",
                "recipient_provider_id": p["recipient_provider_id"]
            }
        )

    for p in blocked_payments:
        event_builder.add_event(
            event_type="PAYMENT_BLOCKED",
            entity_type="Payment",
            entity_id=p["payment_id"],
            claim_id=p["claim_id"],
            actor_id="USR-FIN-001",
            occurred_at_utc=p["created_at_utc"],
            payload_dict={
                "amount_cents": p["amount_cents"],
                "block_reason": "BLOCKED_UNAPPROVED",
                "claim_id": p["claim_id"],
                "payment_id": p["payment_id"]
            }
        )

    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)
    
    # Insert payments into payments table
    # All 4,115 authorized payments
    op_conn.executemany(
        """
        INSERT INTO payments (
            payment_id, claim_id, invoice_id, recipient_type, recipient_provider_id,
            payment_status, amount_cents, idempotency_key, created_at_utc, authorized_by
        ) VALUES (:payment_id, :claim_id, :invoice_id, :recipient_type, :recipient_provider_id,
                  :payment_status, :amount_cents, :idempotency_key, :created_at_utc, :authorized_by)
        """,
        auth_payments
    )

    # All 85 blocked payments
    op_conn.executemany(
        """
        INSERT INTO payments (
            payment_id, claim_id, invoice_id, recipient_type, recipient_provider_id,
            payment_status, amount_cents, idempotency_key, created_at_utc, authorized_by,
            block_reason_code
        ) VALUES (:payment_id, :claim_id, :invoice_id, :recipient_type, :recipient_provider_id,
                  :payment_status, :amount_cents, :idempotency_key, :created_at_utc, :authorized_by,
                  :block_reason_code)
        """,
        blocked_payments
    )
    op_conn.commit()

    # 5.6 Payments Disbursed (315)
    # trg_payments_validate_upd checks that latest event at time of update is PAYMENT_AUTHORIZED!
    for idx in range(lifecycle_plan["payments_to_disburse"]):
        p = auth_payments[idx]
        pid = p["payment_id"]
        amt = p["amount_cents"]
        disb_ts = (datetime(2026, 1, 21, 0, 0, 0) + timedelta(seconds=idx * 270)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        op_conn.execute(
            """
            UPDATE payments
            SET payment_status = 'DISBURSED',
                disbursed_amount_cents = ?,
                net_paid_cents = ?,
                disbursed_at_utc = ?,
                external_bank_tx_ref = ?
            WHERE payment_id = ?
            """,
            (amt, amt, disb_ts, f"ACH-{pid}", pid)
        )
        
        # Add disbursement event
        event_builder.add_event(
            event_type="PAYMENT_DISBURSED",
            entity_type="Payment",
            entity_id=pid,
            claim_id=p["claim_id"],
            actor_id="USR-FIN-001",
            occurred_at_utc=disb_ts,
            payload_dict={"amount_cents": amt, "claim_id": p["claim_id"], "external_bank_tx_ref": f"ACH-{pid}", "payment_id": pid}
        )

    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)
    op_conn.commit()

    # 5.7 Payments Clawback (20)
    # trg_payments_validate_upd requires PAYMENT_CLAWBACK_REVERSED event present BEFORE update
    claw_timestamps = []
    for idx in range(lifecycle_plan["payments_to_clawback"]):
        p = auth_payments[idx]
        pid = p["payment_id"]
        cid = p["claim_id"]
        invid = p["invoice_id"]
        amt = p["amount_cents"]
        cb_amt = max(1, amt // 2)
        net_paid = amt - cb_amt
        claw_ts = (datetime(2026, 1, 22, 0, 0, 0) + timedelta(seconds=idx * 3600)).strftime("%Y-%m-%dT%H:%M:%SZ")
        claw_timestamps.append(claw_ts)
        
        event_builder.add_event(
            event_type="PAYMENT_CLAWBACK_REVERSED",
            entity_type="Payment",
            entity_id=pid,
            claim_id=cid,
            actor_id="USR-SIU-001",
            occurred_at_utc=claw_ts,
            payload_dict={
                "amount_cents": amt,
                "claim_id": cid,
                "clawed_back_cents": cb_amt,
                "invoice_id": invid,
                "net_paid_cents": net_paid,
                "payment_id": pid,
                "payment_status": "REVERSED_CLAWBACK"
            }
        )
    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    for idx in range(lifecycle_plan["payments_to_clawback"]):
        p = auth_payments[idx]
        pid = p["payment_id"]
        amt = p["amount_cents"]
        cb_amt = max(1, amt // 2)
        claw_ts = claw_timestamps[idx]
        op_conn.execute(
            """
            UPDATE payments
            SET payment_status = 'REVERSED_CLAWBACK',
                clawed_back_cents = ?,
                net_paid_cents = ?,
                reversed_at_utc = ?
            WHERE payment_id = ?
            """,
            (cb_amt, amt - cb_amt, claw_ts, pid)
        )
    op_conn.commit()

    # 5.8 Claims placed on SIU_HOLD (60)
    # Select SUBMITTED claims (500..559)
    for idx in range(lifecycle_plan["claims_to_siu_hold"]):
        c = claims[500 + idx]
        cid = c["claim_id"]
        siu_ts = (datetime(2026, 1, 23, 0, 0, 0) + timedelta(seconds=idx * 1400)).strftime("%Y-%m-%dT%H:%M:%SZ")
        event_builder.add_event(
            event_type="CLAIM_SIU_HOLD_PLACED",
            entity_type="Claim",
            entity_id=cid,
            claim_id=cid,
            actor_id="USR-SIU-001",
            occurred_at_utc=siu_ts,
            payload_dict={"claim_id": cid, "reason": "SUSPECTED_NETWORK_COLLUSION"}
        )
    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    for idx in range(lifecycle_plan["claims_to_siu_hold"]):
        c = claims[500 + idx]
        cid = c["claim_id"]
        op_conn.execute("UPDATE claims SET claim_status = 'SIU_HOLD' WHERE claim_id = ?", (cid,))
    op_conn.commit()

    # 5.9 Payments Cancelled (25)
    # Select 25 authorized payments that remain in AUTHORIZED status (e.g. 1000..1024)
    cancel_timestamps = []
    for idx in range(lifecycle_plan["payments_to_cancel"]):
        p = auth_payments[1000 + idx]
        pid = p["payment_id"]
        cid = p["claim_id"]
        amt = p["amount_cents"]
        cancel_ts = (datetime(2026, 1, 24, 0, 0, 0) + timedelta(seconds=idx * 3400)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cancel_timestamps.append(cancel_ts)
        event_builder.add_event(
            event_type="PAYMENT_CANCELLED",
            entity_type="Payment",
            entity_id=pid,
            claim_id=cid,
            actor_id="USR-SIU-001",
            occurred_at_utc=cancel_ts,
            payload_dict={
                "amount_cents": amt,
                "claim_id": cid,
                "payment_id": pid,
                "payment_status": "CANCELLED",
                "reason_code": "SIU_HOLD_RESERVATION_CLEARED"
            }
        )
    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    for idx in range(lifecycle_plan["payments_to_cancel"]):
        p = auth_payments[1000 + idx]
        pid = p["payment_id"]
        cancel_ts = cancel_timestamps[idx]
        op_conn.execute(
            """
            UPDATE payments
            SET payment_status = 'CANCELLED',
                reversed_at_utc = ?,
                cancel_reason = 'SIU_HOLD_RESERVATION_CLEARED'
            WHERE payment_id = ?
            """,
            (cancel_ts, pid)
        )
    op_conn.commit()

    # 5.10 Claims Denied (25)
    # Select SUBMITTED claims with 0 exposure (e.g. 4000..4024)
    for idx in range(lifecycle_plan["claims_to_deny"]):
        c = claims[4000 + idx]
        cid = c["claim_id"]
        deny_ts = (datetime(2026, 1, 25, 0, 0, 0) + timedelta(seconds=idx * 3400)).strftime("%Y-%m-%dT%H:%M:%SZ")
        event_builder.add_event(
            event_type="CLAIM_DENIED",
            entity_type="Claim",
            entity_id=cid,
            claim_id=cid,
            actor_id="USR-SIU-001",
            occurred_at_utc=deny_ts,
            payload_dict={"claim_id": cid, "reason": "CONFIRMED_FRAUD_FABRICATED_LOSS"}
        )
    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)

    for idx in range(lifecycle_plan["claims_to_deny"]):
        c = claims[4000 + idx]
        cid = c["claim_id"]
        op_conn.execute("UPDATE claims SET claim_status = 'DENIED' WHERE claim_id = ?", (cid,))
    op_conn.commit()

    # 5.11 Investigations Opened (45)
    invg_rows = []
    for idx in range(lifecycle_plan["investigations_to_open"]):
        invg_id = investigation_id(idx + 1)
        c = claims[idx]
        cid = c["claim_id"]
        clmt_id = c["claimant_id"]
        exp_cents = c["claimed_amount_cents"]
        invg_ts = (datetime(2026, 1, 26, 0, 0, 0) + timedelta(seconds=idx * 1900)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        event_builder.add_event(
            event_type="INVESTIGATION_OPENED",
            entity_type="Investigation",
            entity_id=invg_id,
            claim_id=cid,
            actor_id="USR-SIU-001",
            occurred_at_utc=invg_ts,
            payload_dict={"investigation_id": invg_id, "primary_claim_id": cid, "priority": "P2_HIGH"}
        )
        invg_rows.append((
            invg_id, cid, clmt_id, None, "OPEN", "P2_HIGH", "USR-SIU-001",
            invg_ts, invg_ts, None, None,
            exp_cents, 0, f"SIU investigation into claim {cid}"
        ))

    last_inserted_event_idx = sync_events_to_db(last_inserted_event_idx)
    op_conn.executemany(
        """
        INSERT INTO investigations (
            investigation_id, primary_claim_id, subject_claimant_id, subject_provider_id,
            investigation_status, priority, assigned_investigator_id, opened_at_utc,
            updated_at_utc, closed_at_utc, ruling_outcome, estimated_exposure_cents,
            recovered_clawback_cents, case_summary_notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        invg_rows
    )
    op_conn.commit()

    assert len(event_builder.events) == COUNT_IMMUTABLE_EVENTS, (
        f"Event count mismatch: expected {COUNT_IMMUTABLE_EVENTS}, got {len(event_builder.events)}"
    )

    # 6. Run Operational Fraud Indicator Detection
    if verbose:
        print("[6/7] Running Operational Fraud Indicator Detector (15 Rules)...")
    detector = OperationalIndicatorDetector(op_conn)
    raw_findings, det_metrics = detector.run_detection()
    
    raw_cnt, dedup_cnt, per_rule_counts = deduplicate_and_persist_indicators(op_conn, raw_findings)
    if verbose:
        print(f"      Emitted Findings: {raw_cnt} | Persisted Indicators: {dedup_cnt}")

    # 7. Run Operational 10-Stage Scoring Pipeline
    if verbose:
        print("[7/7] Running 10-Stage IEF Scoring Pipeline & Claim Score Lockdown Gate...")
    scorer = OperationalScorer(op_conn)
    score_summary = scorer.score_all_claims()
    if verbose:
        print(f"      Scored {score_summary['total_scored']} claims. Tiers: {score_summary['tier_counts']}")

    # 8. Populate Isolated Ground Truth Database
    if verbose:
        print("[*] Populating Isolated Ground Truth Database (ground_truth.db)...")
    populate_ground_truth(gt_db_path, claims, claimants, withheld_edges, scenario_metadata)

    # 9. Execute Validation Gates
    gt_conn = sqlite3.connect(str(gt_db_path))
    validator = DatasetValidator(op_conn, gt_conn)
    
    fk_violations = validator.validate_foreign_keys()
    table_counts = validator.validate_table_counts()
    fin_violations = validator.validate_financial_invariants()
    ev_total, ev_valid, ev_err = validator.validate_event_chain()
    digest_val, digest_exp, digest_ok = validator.validate_schema_digest()
    scenario_res = validator.validate_scenarios()

    op_conn.close()
    gt_conn.close()

    result_report = {
        "seed": seed,
        "operational_db": str(op_db_path),
        "ground_truth_db": str(gt_db_path),
        "foreign_key_violations": len(fk_violations),
        "table_counts": table_counts,
        "financial_violations": len(fin_violations),
        "event_chain_valid": ev_valid,
        "event_chain_total": ev_total,
        "event_chain_error": ev_err,
        "schema_digest": digest_val,
        "schema_digest_match": digest_ok,
        "detector_metrics": det_metrics,
        "per_rule_indicators": per_rule_counts,
        "total_indicators_persisted": dedup_cnt,
        "scoring_summary": score_summary,
        "scenarios": scenario_res
    }

    if verbose:
        print("\n" + "=" * 80)
        print("DATASET GENERATION AND VALIDATION COMPLETE")
        print("=" * 80)
        print(f"[*] Schema Digest: {digest_val} (Matches baseline: {digest_ok})")
        print(f"[*] FK Violations: {len(fk_violations)}")
        print(f"[*] Financial Invariant Violations: {len(fin_violations)}")
        print(f"[*] Event Chain Status: {'PASS' if ev_valid else 'FAIL'} ({ev_total} events)")
        print(f"[*] YF-NEG-4 Passed: {scenario_res.get('YF-NEG-4', {}).get('passed')}")
        print(f"[*] YF-NEG-5 Passed: {scenario_res.get('YF-NEG-5', {}).get('passed')}")
        print(f"[*] Withheld Edges in Operational DB: {scenario_res.get('WITHHELD_EDGES', {}).get('operational_count')}")

    return result_report


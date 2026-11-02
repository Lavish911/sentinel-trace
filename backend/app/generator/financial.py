"""
Financial entity generator (invoices, payments, lifecycle operations).
Ensures 100% financial consistency across claimed, approved, authorized, disbursed,
clawed back, and net paid amounts, fully satisfying ARCH-ST-010.2 trigger prerequisites.
"""

import hashlib
import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
from backend.app.generator.config import COUNT_INVOICES, COUNT_PAYMENTS
from backend.app.generator.id_factory import invoice_id, payment_id


def sha256_hex(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def compute_line_item_fingerprint(cpt_code: str, start_utc: str, end_utc: str, billed_cents: int) -> str:
    norm_code = cpt_code.strip().upper()
    start_day = start_utc[:10]
    end_day = end_utc[:10]
    raw = f"{norm_code}|{start_day}|{end_day}|{billed_cents}"
    return sha256_hex(raw)
    


CPT_CODES = [
    ("CPT99213", 15000),      # Office visit level 3: $150
    ("CPT99214", 28000),      # Office visit level 4: $280
    ("CPT99215", 45000),      # Office visit level 5: $450
    ("AB-FRAME-101", 370000), # Auto body frame alignment: $3,700
    ("DIAG-MRI-01", 120000),  # MRI Scan: $1,200
    ("CHIRO-ADJ-01", 8500),   # Spinal adjustment: $85
    ("REST-WATER-01", 520000),# Water extraction: $5,200
    ("TOW-STORAGE-01", 45000) # Vehicle recovery: $450
]


def generate_financials(
    claims: List[Dict[str, Any]],
    providers: List[Dict[str, Any]],
    scenario_metadata: Dict[str, Any],
    seed: int = 42
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generates:
    - invoices (7,500 rows)
    - payments (4,200 rows: 4,115 authorized + 85 blocked)
    - lifecycle_plan: deterministic directives for database lifecycle updates
    """
    rng = random.Random(seed)
    invoices: List[Dict[str, Any]] = []
    
    # 1. GENERATE INVOICES (7,500)
    prv_invoice_counters: Dict[str, int] = {}
    
    # YF-NEG-3: 25 claims across distinct claimants sharing duplicate invoices
    yf3_indices = set(scenario_metadata.get("yf3_indices", []))
    shared_yf3_cpt = "AB-FRAME-101"
    shared_yf3_date = "2026-01-10T10:00:00Z"
    shared_yf3_billed = 420000
    shared_yf3_fp = compute_line_item_fingerprint(shared_yf3_cpt, shared_yf3_date, shared_yf3_date, shared_yf3_billed)

    first_yf3_invid = None
    seen_fingerprints: Dict[str, str] = {}

    yf4_core_indices = [710 + r * 8 + c for r in range(5) for c in range(7)]

    for idx in range(COUNT_INVOICES):
        if 5000 <= idx < 5035:
            # Map to YF-NEG-4 core claims for split-billing (IND-12)
            claim_idx = yf4_core_indices[idx - 5000]
            is_yf4_second_item = True
        elif idx < len(claims):
            claim_idx = idx
            is_yf4_second_item = False
        else:
            # Secondary invoices for non-scenario claims (range 1100 to 4899)
            claim_idx = 1100 + ((idx - 5035) % 3800)
            is_yf4_second_item = False

        target_claim = claims[claim_idx]
        cid = target_claim["claim_id"]
        
        # Provider selection
        if claim_idx in scenario_metadata.get("yf4_indices", []):
            r_num = 16 + ((claim_idx - 710) // 8)
            prv = providers[r_num - 1]
        else:
            prv = providers[(claim_idx * 3) % len(providers)]
            
        prvid = prv["provider_id"]
        prv_seq = prv_invoice_counters.get(prvid, 0) + 1
        prv_invoice_counters[prvid] = prv_seq
        invid = invoice_id(prvid, prv_seq)
        
        # Timing
        if is_yf4_second_item:
            # Same day split billing from ring provider
            svc_start = "2026-02-15T09:00:00Z"
            svc_end = "2026-02-15T17:00:00Z"
            sub_ts = "2026-02-15T19:00:00Z"
        elif claim_idx in yf4_core_indices:
            svc_start = "2026-02-15T09:00:00Z"
            svc_end = "2026-02-15T17:00:00Z"
            sub_ts = "2026-02-15T19:00:00Z"
        else:
            svc_date = datetime(2026, 1, 5) + timedelta(days=idx % 30)
            svc_start = svc_date.strftime("%Y-%m-%dT09:00:00Z")
            svc_end = svc_date.strftime("%Y-%m-%dT17:00:00Z")
            sub_ts = (svc_date + timedelta(hours=2)).strftime("%Y-%m-%dT19:00:00Z")
        
        # Line item & fingerprint
        if claim_idx in yf3_indices:
            cpt = shared_yf3_cpt
            billed = shared_yf3_billed
            fp = shared_yf3_fp
            if first_yf3_invid is None:
                first_yf3_invid = invid
                status = "SUBMITTED"
                dup_of = None
                seen_fingerprints[fp] = invid
            else:
                status = "REJECTED_DUPLICATE"
                dup_of = first_yf3_invid
        elif claim_idx in scenario_metadata.get("yf4_indices", []):
            if is_yf4_second_item:
                cpt = "CPT99213"
                billed = 15000 + (claim_idx - 710) * 10
            else:
                cpt = "CPT99214"
                billed = 35000 + (claim_idx - 710) * 10  # Upcoded billing fact
            fp = compute_line_item_fingerprint(cpt, svc_start, svc_end, billed)
            status = "SUBMITTED"
            dup_of = None
            while fp in seen_fingerprints:
                billed += 1
                fp = compute_line_item_fingerprint(cpt, svc_start, svc_end, billed)
            seen_fingerprints[fp] = invid
        else:
            cpt_choice, billed_base = CPT_CODES[idx % len(CPT_CODES)]
            cpt = cpt_choice
            max_cap = target_claim["payout_cap_cents"]
            # Ensure billed fits within claim payout cap while remaining strictly unique
            billed = min(billed_base, max_cap - 20000) + (idx % 500) * 10 + (idx // 500)
            fp = compute_line_item_fingerprint(cpt, svc_start, svc_end, billed)
            status = "SUBMITTED"
            dup_of = None
            while fp in seen_fingerprints:
                billed += 1
                fp = compute_line_item_fingerprint(cpt, svc_start, svc_end, billed)
            seen_fingerprints[fp] = invid

        pinv_num = f"PI-{prvid}-{prv_seq:06d}"
        
        invoices.append({
            "invoice_id": invid,
            "claim_id": cid,
            "provider_id": prvid,
            "provider_invoice_number": pinv_num,
            "invoice_status": status,
            "service_start_utc": svc_start,
            "service_end_utc": svc_end,
            "submitted_at_utc": sub_ts,
            "cpt_or_line_code": cpt,
            "line_item_fingerprint": fp,
            "billed_cents": billed,
            "approved_cents": 0,
            "historical_approved_cents": 0,
            "reserved_authorized_cents": 0,
            "gross_disbursed_cents": 0,
            "clawed_back_cents": 0,
            "net_paid_cents": 0,
            "duplicate_of_invoice_id": dup_of
        })

    # --------------------------------------------------------------------------
    # 2. GENERATE PAYMENTS (4,200)
    # 4,115 authorized payments distributed across 1,200 approved invoices
    # 85 blocked payments on unapproved invoices
    # --------------------------------------------------------------------------
    payments: List[Dict[str, Any]] = []
    
    # 1,200 invoices to approve: selected strictly from SUBMITTED invoices
    approved_invoices = [inv for inv in invoices if inv["invoice_status"] == "SUBMITTED"][:1200]
    unapproved_invoices = [inv for inv in invoices if inv["invoice_status"] == "SUBMITTED"][1200:1285]
    
    # 515 approved invoices get 4 payments, 685 get 3 payments = 4,115 payments
    k_per_invoice = [4] * 515 + [3] * 685
    pay_seq = 0

    for inv_idx, target_inv in enumerate(approved_invoices):
        cid = target_inv["claim_id"]
        invid = target_inv["invoice_id"]
        prvid = target_inv["provider_id"]
        total_cents = target_inv["billed_cents"]
        k = k_per_invoice[inv_idx]
        
        base_amt = total_cents // k
        rem = total_cents % k
        
        for p_i in range(k):
            pay_seq += 1
            pid = payment_id(pay_seq)
            amt = base_amt + (rem if p_i == k - 1 else 0)
            idem_key = sha256_hex(f"IDEM-PAY-{pay_seq:06d}-{seed}")
            created_ts = "2026-01-10T08:00:00Z"
            
            payments.append({
                "payment_id": pid,
                "claim_id": cid,
                "invoice_id": invid,
                "recipient_type": "PROVIDER",
                "recipient_claimant_id": None,
                "recipient_provider_id": prvid,
                "payment_status": "AUTHORIZED",
                "amount_cents": amt,
                "disbursed_amount_cents": 0,
                "clawed_back_cents": 0,
                "net_paid_cents": 0,
                "idempotency_key": idem_key,
                "created_at_utc": created_ts,
                "disbursed_at_utc": None,
                "reversed_at_utc": None,
                "authorized_by": "USR-FIN-001",
                "block_reason_code": None,
                "external_bank_tx_ref": None,
                "cancel_reason": None
            })

    assert len(payments) == 4115, f"Expected 4115 authorized payments, got {len(payments)}"

    # 85 Blocked payments on unapproved invoices
    for blk_idx, target_inv in enumerate(unapproved_invoices):
        pay_seq += 1
        pid = payment_id(pay_seq)
        cid = target_inv["claim_id"]
        invid = target_inv["invoice_id"]
        prvid = target_inv["provider_id"]
        amt = target_inv["billed_cents"]
        idem_key = sha256_hex(f"IDEM-PAY-{pay_seq:06d}-{seed}")
        created_ts = "2026-01-10T08:00:00Z"
        
        payments.append({
            "payment_id": pid,
            "claim_id": cid,
            "invoice_id": invid,
            "recipient_type": "PROVIDER",
            "recipient_claimant_id": None,
            "recipient_provider_id": prvid,
            "payment_status": "BLOCKED_UNAPPROVED",
            "amount_cents": amt,
            "disbursed_amount_cents": 0,
            "clawed_back_cents": 0,
            "net_paid_cents": 0,
            "idempotency_key": idem_key,
            "created_at_utc": created_ts,
            "disbursed_at_utc": None,
            "reversed_at_utc": None,
            "authorized_by": "USR-FIN-001",
            "block_reason_code": "INV_NOT_APPROVED",
            "external_bank_tx_ref": None,
            "cancel_reason": None
        })

    assert len(payments) == COUNT_PAYMENTS, f"Expected {COUNT_PAYMENTS} total payments, got {len(payments)}"

    # --------------------------------------------------------------------------
    # 3. LIFECYCLE RECONCILIATION PLAN (Exact budget to hit 19,615 events)
    # --------------------------------------------------------------------------
    lifecycle_plan = {
        "invoices_to_approve": 1200,      # Updates invoice to APPROVED -> cascades claim to APPROVED
        "approved_invoices": approved_invoices,
        "payments_to_disburse": 315,      # Disburses authorized payments with ACH ref
        "payments_to_clawback": 20,       # Reverses clawback on disbursed payments
        "payments_to_cancel": 25,         # Cancels authorized payments
        "payments_to_block": 85,          # Authorizations blocked for unapproved invoice
        "claims_to_siu_hold": 60,         # Places claim on SIU_HOLD (siu_referred = 1)
        "claims_to_deny": 25,             # Denies claims
        "investigations_to_open": 45,     # Opens 45 SIU investigations
        "ingestion_exceptions": 25        # Records 25 YF-NEG-1 nonexistent policy exceptions
    }

    return invoices, payments, lifecycle_plan

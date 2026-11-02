import re
import json
import hashlib
import sqlite3
import os
import sys
import subprocess

WORK = os.path.dirname(os.path.abspath(__file__))
ops_path = os.path.join(WORK, 'ops_0102.sql') if os.path.exists(os.path.join(WORK, 'ops_0102.sql')) else os.path.join(WORK, 'ops_0101.sql')
trigs_path = os.path.join(WORK, 'trigs_0102.sql') if os.path.exists(os.path.join(WORK, 'trigs_0102.sql')) else os.path.join(WORK, 'trigs_0101.sql')
ops = open(ops_path, encoding='utf-8').read()
trigs = open(trigs_path, encoding='utf-8').read()


def sha256_hex(s):
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def is_canonical_json(s):
    """RFC 8259 canonical JSON object validator (rejects NaN, Infinity, duplicate keys, non-dict roots, whitespace, unsorted keys)."""
    if not isinstance(s, str):
        return 0

    def reject_const(val):
        raise ValueError(f"Non-standard JSON constant forbidden: {val}")

    def check_dups(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate key")
        return dict(pairs)

    try:
        obj = json.loads(s, parse_constant=reject_const, object_pairs_hook=check_dups)
    except Exception:
        return 0
    if not isinstance(obj, dict):
        return 0
    try:
        canon = json.dumps(
            obj,
            ensure_ascii=False,
            allow_nan=False,
            separators=(',', ':'),
            sort_keys=True,
        )
        return 1 if canon == s else 0
    except Exception:
        return 0


class TestRunner:
    def __init__(self, con):
        self.con = con
        self.passed = 0
        self.failed = 0
        self.records = []

    def t(self, test_id, label, sql, params=()):
        try:
            self.con.execute(sql, params)
            self.passed += 1
            self.records.append((test_id, label, True))
            print(f"[PASS ] {test_id}: {label}")
            return True
        except sqlite3.Error as e:
            self.failed += 1
            self.records.append((test_id, label, False))
            print(f"[FAIL ] {test_id}: {label} -> unexpected block: {e}")
            return False

    def elabel(self, test_id, label, expected_err, sql, params=()):
        try:
            self.con.execute(sql, params)
            self.failed += 1
            self.records.append((test_id, label, False))
            print(f"[FAIL ] {test_id}: {label} -> expected {expected_err} but succeeded")
            return False
        except sqlite3.Error as e:
            ok = expected_err in str(e)
            if ok:
                self.passed += 1
                self.records.append((test_id, label, True))
                print(f"[PASS ] {test_id}: {label} -> {e}")
            else:
                self.failed += 1
                self.records.append((test_id, label, False))
                print(f"[FAIL ] {test_id}: {label} -> expected {expected_err}, got: {e}")
            return ok

    def assert_eq(self, test_id, label, actual, expected):
        ok = (actual == expected)
        if ok:
            self.passed += 1
            self.records.append((test_id, label, True))
            print(f"[PASS ] {test_id}: {label} -> {actual!r}")
        else:
            self.failed += 1
            self.records.append((test_id, label, False))
            print(f"[FAIL ] {test_id}: {label} -> expected {expected!r}, got {actual!r}")
        return ok


def run_self_test():
    """Deliberate mutation check proving that broken positive, negative, or state expectations fail the runner."""
    mem = sqlite3.connect(':memory:')
    mem.execute("CREATE TABLE dummy (x INTEGER PRIMARY KEY, CHECK (x > 0)) STRICT;")
    tr = TestRunner(mem)
    # 1. Deliberately broken positive test (violates CHECK x > 0)
    r1 = tr.t("MUT-1", "deliberate broken positive", "INSERT INTO dummy VALUES (0)")
    # 2. Deliberately broken negative test (succeeds when error expected)
    r2 = tr.elabel("MUT-2", "deliberate broken negative", "ERR_NONEXISTENT", "INSERT INTO dummy VALUES (1)")
    # 3. Deliberately broken negative error substring
    r3 = tr.elabel("MUT-3", "deliberate wrong error code", "ERR_WRONG_CODE", "INSERT INTO dummy VALUES (-1)")
    # 4. Deliberately broken state assertion
    r4 = tr.assert_eq("MUT-4", "deliberate state mismatch", 1, 2)
    mem.close()
    if any([r1, r2, r3, r4]) or tr.failed != 4 or tr.passed != 0:
        print("[FAIL ] Runner self-test did not catch deliberate mutations!")
        sys.exit(1)
    if '--mutate-self-test' in sys.argv:
        print("[SELF-TEST] Deliberate mutation mode triggered -> exiting with code 1 as required.")
        sys.exit(1)


def main():
    if '--mutate-self-test' in sys.argv:
        run_self_test()

    print("== RUNNER FAIL-CLOSED SELF-TEST ==")
    run_self_test()
    # Also verify via subprocess that --mutate-self-test exits with non-zero code
    sub = subprocess.run([sys.executable, os.path.abspath(__file__), '--mutate-self-test'], capture_output=True, text=True)
    if sub.returncode == 0:
        print("[FAIL ] Subprocess --mutate-self-test exited with 0!")
        sys.exit(1)
    print(f"[PASS ] SELF-00: Subprocess mutation check exited with non-zero code ({sub.returncode})")

    con = sqlite3.connect(':memory:')
    chain = '0' * 64
    con.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
    con.create_function('is_canonical_json', 1, is_canonical_json, deterministic=True)
    con.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
    con.executescript(ops)
    con.executescript(trigs)

    R = TestRunner(con)

    # Check fence byte-identity against ARCH-ST-010.2.md
    MD = os.path.join(WORK, '..', '..', 'ARCH-ST-010.2.md')
    _fences = re.findall(r'```sql\n(.*?)```', open(MD, encoding='utf-8').read(), re.S)
    R.assert_eq(
        "V-00",
        "SQL fences in ARCH-ST-010.2.md (§5.1, §5.2) match shipped ops/trigs SQL byte-for-byte",
        (len(_fences), ops.strip() == _fences[1].strip(), trigs.strip() == _fences[2].strip()),
        (5, True, True),
    )

    n_tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    n_trigs = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
    R.assert_eq("V-01", "Operational schema builds 12 STRICT tables and 24 triggers", (n_tables, n_trigs), (12, 24))

    def add_event(event_type, entity_type, entity_id, claim_id, actor, occ, payload):
        nonlocal chain
        psha = sha256_hex(payload)
        prev = chain
        seq = con.execute("SELECT COALESCE(MAX(sequence_no),0)+1 FROM immutable_events").fetchone()[0]
        eid = f"EVT-2026-{seq:07d}"

        def L(s):
            return len(s.encode('utf-8'))

        parts = [
            'ST-EVT-V2|',
            f'11:sequence_no=I{seq};',
            f'8:event_id=S{L(eid)}:{eid};',
            f'10:event_type=S{L(event_type)}:{event_type};',
            f'11:entity_type=S{L(entity_type)}:{entity_type};',
            f'9:entity_id=S{L(entity_id)}:{entity_id};',
            '8:claim_id=N;' if claim_id is None else f'8:claim_id=S{L(claim_id)}:{claim_id};',
            f'8:actor_id=S{L(actor)}:{actor};',
            f'15:occurred_at_utc=S{L(occ)}:{occ};',
            f'14:payload_sha256=S64:{psha};',
            f'15:prev_event_hash=S64:{prev};',
        ]
        preimage = ''.join(parts)
        eh = sha256_hex(preimage)
        con.execute(
            "INSERT INTO immutable_events (sequence_no,event_id,event_type,entity_type,entity_id,claim_id,actor_id,occurred_at_utc,payload_json,payload_sha256,prev_event_hash,event_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (seq, eid, event_type, entity_type, entity_id, claim_id, actor, occ, payload, psha, prev, eh),
        )
        chain = eh
        return seq

    print("\n== SEED BASE ENTITIES ==")
    R.t("SEED-01", "Insert claimant CLMT-000001", "INSERT INTO claimants VALUES ('CLMT-000001','T','1990-05-10','" + 'ab'*32 + "','+12025550001','u@x.com','100 MAIN ST','" + 'cd'*32 + "','" + 'b1'*32 + "','2025-12-01T00:00:00Z')")
    R.t("SEED-02", "Insert claimant CLMT-000002", "INSERT INTO claimants VALUES ('CLMT-000002','T2','1990-05-10','" + 'ff'*31 + 'c0' + "','+12025550003','u2@x.com','100 MAIN ST','" + 'ee'*31 + 'd0' + "','" + 'b1'*32 + "','2025-12-01T00:00:00Z')")
    R.t("SEED-03", "Insert provider PRV-000001", "INSERT INTO providers VALUES ('PRV-000001','B','AUTO_BODY','NPI-1','" + '12'*32 + "','+12025550002','200 OAK','" + '34'*32 + "','" + '56'*32 + "','IN_NETWORK','2025-12-01T00:00:00Z')")
    R.t("SEED-04", "Insert policy POL-2026-000001", "INSERT INTO policies VALUES ('POL-2026-000001','CLMT-000001','PN-1','AUTO','ACTIVE','2025-01-01T00:00:00Z','2026-12-31T00:00:00Z','2025-01-01T00:00:00Z',500000,50000,10000)")
    R.t("SEED-05", "Insert policy POL-2026-000002", "INSERT INTO policies VALUES ('POL-2026-000002','CLMT-000002','PN-2','AUTO','ACTIVE','2025-01-01T00:00:00Z','2026-12-31T00:00:00Z','2025-01-01T00:00:00Z',500000,50000,10000)")
    R.t("SEED-06", "Insert incident INC-2026-000001", "INSERT INTO incidents VALUES ('INC-2026-000001','2026-01-05T08:00:00Z','2026-01-05T20:00:00Z','AUTO_COLLISION','TX','300 ELM','9==aw2','RPT-1','CLEAR','x')")

    print("\n== NEW-1 & NEW-2: CLAIM INSERT BYPASS PROTECTION ==")
    R.elabel(
        "NEW-1a",
        "Reject claim INSERT with pre-populated nonzero score / CRITICAL tier",
        "ERR_CLAIM_INITIAL_SCORE_STATE_INVALID",
        "INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id,latest_ief_score,latest_risk_tier) VALUES ('CLM-2026-000001','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1',95.0,'CRITICAL')",
    )
    R.elabel(
        "NEW-1b",
        "Reject claim INSERT with pre-populated scoring_evidence_sha256",
        "ERR_CLAIM_INITIAL_SCORE_STATE_INVALID",
        "INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id,scoring_evidence_sha256) VALUES ('CLM-2026-000001','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1','" + 'a'*64 + "')",
    )
    R.elabel(
        "NEW-2a",
        "Reject claim INSERT with initial siu_referred=1",
        "ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO",
        "INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id,siu_referred) VALUES ('CLM-2026-000001','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1',1)",
    )

    R.t("SEED-07", "Insert valid claim CLM-2026-000001", "INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id) VALUES ('CLM-2026-000001','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1')")
    fp = sha256_hex("AB-FRAME-101|2026-01-05|2026-01-05|420000")
    R.t("SEED-08", "Insert valid invoice INV-PRV-PRV-000001-000001", "INSERT INTO invoices (invoice_id,claim_id,provider_id,provider_invoice_number,invoice_status,service_start_utc,service_end_utc,submitted_at_utc,cpt_or_line_code,line_item_fingerprint,billed_cents) VALUES ('INV-PRV-PRV-000001-000001','CLM-2026-000001','PRV-000001','PI-1','SUBMITTED','2026-01-05T09:00:00Z','2026-01-05T10:00:00Z','2026-01-05T22:00:00Z','AB-FRAME-101',?,420000)", (fp,))

    print("\n== C-1: INVOICE APPROVAL CASCADE FROM SUBMITTED ==")
    R.t("C-1a", "Approve invoice at 370000 while claim is SUBMITTED", "UPDATE invoices SET invoice_status='APPROVED', approved_cents=370000, historical_approved_cents=370000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
    R.assert_eq(
        "C-1a-state",
        "Claim cascades to APPROVED with 370000 approved and historical_approved",
        con.execute("SELECT claim_status, approved_amount_cents, historical_approved_cents, net_paid_cents FROM claims WHERE claim_id='CLM-2026-000001'").fetchone(),
        ('APPROVED', 370000, 370000, 0),
    )
    R.t("SEED-09", "Insert second claim CLM-2026-000002", "INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id) VALUES ('CLM-2026-000002','POL-2026-000002','CLMT-000002','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1')")
    R.elabel("C-1b", "Block direct claim APPROVED update without approved invoice", "ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH", "UPDATE claims SET claim_status='APPROVED' WHERE claim_id='CLM-2026-000002'")

    print("\n== A-2 & NEW-5: PAYMENT EVENT GATES, SIU_HOLD LIFECYCLE, AND INCREMENTAL CLAWBACK ==")
    R.t("PAY-01", "Authorize PAY-2026-000001 (200000)", "INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000001','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',200000,'ID1','2026-01-07T08:00:00Z','USR-FIN-001')")
    R.t("PAY-02", "Authorize PAY-2026-000002 (170000)", "INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000002','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',170000,'ID2','2026-01-07T08:00:00Z','USR-FIN-001')")

    R.elabel(
        "A-2a",
        "Block disbursement of PAY-2026-000001 without PAYMENT_AUTHORIZED event",
        "ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT",
        "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=200000, net_paid_cents=200000, disbursed_at_utc='2026-01-07T12:00:00Z', external_bank_tx_ref='ACH-1' WHERE payment_id='PAY-2026-000001'",
    )

    add_event('PAYMENT_AUTHORIZED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-FIN-001', '2026-01-07T08:00:00Z', '{"amount_cents":200000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}')
    R.t(
        "A-2b",
        "Disburse PAY-2026-000001 with matching PAYMENT_AUTHORIZED event",
        "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=200000, net_paid_cents=200000, disbursed_at_utc='2026-01-07T12:00:00Z', external_bank_tx_ref='ACH-1' WHERE payment_id='PAY-2026-000001'",
    )
    R.assert_eq(
        "A-2b-state",
        "Claim transitions to PARTIALLY_PAID with net_paid=200000, reserved=170000",
        con.execute("SELECT claim_status, net_paid_cents, reserved_authorized_cents FROM claims WHERE claim_id='CLM-2026-000001'").fetchone(),
        ('PARTIALLY_PAID', 200000, 170000),
    )

    R.t("A-1a", "Place PARTIALLY_PAID claim CLM-2026-000001 onto SIU_HOLD", "UPDATE claims SET claim_status='SIU_HOLD' WHERE claim_id='CLM-2026-000001'")
    R.assert_eq(
        "C-6j-hold",
        "Entering SIU_HOLD automatically flips claims.siu_referred from 0 to 1",
        con.execute("SELECT claim_status, siu_referred, reserved_authorized_cents FROM claims WHERE claim_id='CLM-2026-000001'").fetchone(),
        ('SIU_HOLD', 1, 170000),
    )
    R.elabel(
        "NEW-2b",
        "Block resetting claims.siu_referred from 1 back to 0",
        "ERR_CLAIM_SIU_REFERRED_IRREVERSIBLE",
        "UPDATE claims SET siu_referred=0 WHERE claim_id='CLM-2026-000001'",
    )

    R.elabel(
        "A-2c",
        "Block disbursement of PAY-2026-000002 while claim is on SIU_HOLD",
        "ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL",
        "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=170000, net_paid_cents=170000, disbursed_at_utc='2026-01-08T12:00:00Z', external_bank_tx_ref='ACH-2' WHERE payment_id='PAY-2026-000002'",
    )
    R.elabel(
        "A-2d-reason",
        "Block payment cancellation without cancel_reason",
        "ERR_PAYMENT_CANCELLATION_REQUIRES_REASON",
        "UPDATE payments SET payment_status='CANCELLED', reversed_at_utc='2026-01-08T12:00:00Z', cancel_reason=NULL WHERE payment_id='PAY-2026-000002'",
    )
    R.elabel(
        "A-2d-event",
        "Block payment cancellation without PAYMENT_CANCELLED event",
        "ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT",
        "UPDATE payments SET payment_status='CANCELLED', reversed_at_utc='2026-01-08T12:00:00Z', cancel_reason='SIU_HOLD_RESERVATION_CLEARED' WHERE payment_id='PAY-2026-000002'",
    )

    cancel_payload = '{"amount_cents":170000,"claim_id":"CLM-2026-000001","payment_id":"PAY-2026-000002","payment_status":"CANCELLED","reason_code":"SIU_HOLD_RESERVATION_CLEARED"}'
    R.assert_eq(
        "NEW-7a",
        "PAYMENT_CANCELLED payload digest matches documented constant 14b3a52b...",
        sha256_hex(cancel_payload),
        "14b3a52b35a0d83eab9e483fbe017c39fe173609589a627e084b632fc0024efe",
    )
    add_event('PAYMENT_CANCELLED', 'Payment', 'PAY-2026-000002', 'CLM-2026-000001', 'USR-SIU-001', '2026-01-08T12:00:00Z', cancel_payload)
    R.t(
        "A-2e",
        "Cancel PAY-2026-000002 with matching PAYMENT_CANCELLED event and cancel_reason",
        "UPDATE payments SET payment_status='CANCELLED', reversed_at_utc='2026-01-08T12:00:00Z', cancel_reason='SIU_HOLD_RESERVATION_CLEARED' WHERE payment_id='PAY-2026-000002'",
    )
    R.assert_eq(
        "A-2e-state",
        "Cancellation releases reservation (reserved_authorized_cents=0, net_paid_cents=200000)",
        con.execute("SELECT claim_status, reserved_authorized_cents, net_paid_cents, siu_referred FROM claims WHERE claim_id='CLM-2026-000001'").fetchone(),
        ('SIU_HOLD', 0, 200000, 1),
    )

    # NEW-5: Test legitimate-payment SIU_HOLD exit (SIU_HOLD -> PARTIALLY_PAID when cleared as benign)
    R.elabel(
        "NEW-5a",
        "Block SIU_HOLD -> APPROVED when net_paid_cents > 0",
        "ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH",
        "UPDATE claims SET claim_status='APPROVED' WHERE claim_id='CLM-2026-000001'",
    )
    R.t(
        "NEW-5b",
        "Allow SIU_HOLD -> PARTIALLY_PAID when partially-paid claim is cleared as benign without clawback",
        "UPDATE claims SET claim_status='PARTIALLY_PAID' WHERE claim_id='CLM-2026-000001'",
    )
    R.t(
        "NEW-5c",
        "Return CLM-2026-000001 to SIU_HOLD for confirmed-fraud clawback test",
        "UPDATE claims SET claim_status='SIU_HOLD' WHERE claim_id='CLM-2026-000001'",
    )

    R.elabel(
        "A-2f-block",
        "Block initial clawback on PAY-2026-000001 without PAYMENT_CLAWBACK_REVERSED event",
        "ERR_CLAWBACK_REQUIRES_EVENT",
        "UPDATE payments SET payment_status='REVERSED_CLAWBACK', clawed_back_cents=100000, net_paid_cents=100000, reversed_at_utc='2026-01-12T10:00:00Z' WHERE payment_id='PAY-2026-000001'",
    )
    cb1_payload = '{"amount_cents":200000,"claim_id":"CLM-2026-000001","clawed_back_cents":100000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":100000,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}'
    add_event('PAYMENT_CLAWBACK_REVERSED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-SIU-001', '2026-01-12T10:00:00Z', cb1_payload)
    R.t(
        "A-2f-part1",
        "Execute partial clawback (100000) with matching PAYMENT_CLAWBACK_REVERSED event",
        "UPDATE payments SET payment_status='REVERSED_CLAWBACK', clawed_back_cents=100000, net_paid_cents=100000, reversed_at_utc='2026-01-12T10:00:00Z' WHERE payment_id='PAY-2026-000001'",
    )
    R.elabel(
        "NEW-5d",
        "Block incremental clawback (REVERSED_CLAWBACK -> REVERSED_CLAWBACK) without fresh event",
        "ERR_CLAWBACK_REQUIRES_EVENT",
        "UPDATE payments SET clawed_back_cents=200000, net_paid_cents=0, reversed_at_utc='2026-01-12T16:45:00Z' WHERE payment_id='PAY-2026-000001'",
    )
    cb2_payload = '{"amount_cents":200000,"claim_id":"CLM-2026-000001","clawed_back_cents":200000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}'
    add_event('PAYMENT_CLAWBACK_REVERSED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-SIU-001', '2026-01-12T16:45:00Z', cb2_payload)
    R.t(
        "NEW-5e",
        "Execute incremental clawback to 200000 with fresh PAYMENT_CLAWBACK_REVERSED event",
        "UPDATE payments SET clawed_back_cents=200000, net_paid_cents=0, reversed_at_utc='2026-01-12T16:45:00Z' WHERE payment_id='PAY-2026-000001'",
    )
    R.assert_eq(
        "A-2f-state",
        "Post-clawback claim balances preserve historical_approved_cents=370000 with net_paid_cents=0",
        con.execute("SELECT claim_status, reserved_authorized_cents, net_paid_cents, historical_approved_cents FROM claims WHERE claim_id='CLM-2026-000001'").fetchone(),
        ('SIU_HOLD', 0, 0, 370000),
    )

    print("\n== C-6 & NEW-4: RELATIONSHIP EDGES IMMUTABILITY, CANONICAL ORDERING, AND TIMESTAMP REGRESSION ==")
    # Fixed column order (target_claimant_id='CLMT-000001', target_provider_id=NULL) so CHECK(canonical_src_key < canonical_dst_key) is genuinely tested
    R.elabel(
        "C-6b-self",
        "Reject self-edge where canonical_src_key == canonical_dst_key",
        "canonical_src_key < canonical_dst_key",
        "INSERT INTO relationship_edges VALUES ('EDGE-2026-000001','SHARED_BANK_ACCOUNT','CLAIMANT','CLMT-000001',NULL,'CLAIMANT','CLMT-000001',NULL,'CLAIMANT:CLMT-000001','CLAIMANT:CLMT-000001',1.0,1,'2026-01-05T00:00:00Z','2026-01-05T00:00:00Z','CLM-2026-000001',1)",
    )
    R.elabel(
        "C-6b-order",
        "Reject reversed edge where canonical_src_key > canonical_dst_key",
        "canonical_src_key < canonical_dst_key",
        "INSERT INTO relationship_edges VALUES ('EDGE-2026-000001','SHARED_BANK_ACCOUNT','CLAIMANT','CLMT-000002',NULL,'CLAIMANT','CLMT-000001',NULL,'CLAIMANT:CLMT-000002','CLAIMANT:CLMT-000001',1.0,1,'2026-01-05T00:00:00Z','2026-01-05T00:00:00Z','CLM-2026-000001',1)",
    )
    R.t(
        "SEED-10",
        "Insert valid relationship edge EDGE-2026-000001",
        "INSERT INTO relationship_edges VALUES ('EDGE-2026-000001','SHARED_BANK_ACCOUNT','CLAIMANT','CLMT-000001',NULL,'CLAIMANT','CLMT-000002',NULL,'CLAIMANT:CLMT-000001','CLAIMANT:CLMT-000002',1.0,1,'2026-01-05T00:00:00Z','2026-01-10T00:00:00Z','CLM-2026-000001',1)",
    )
    R.elabel(
        "C-6b-strength",
        "Reject edge strength_weight mutation",
        "ERR_EDGE_CORE_FIELDS_IMMUTABLE",
        "UPDATE relationship_edges SET strength_weight=0.01 WHERE edge_id='EDGE-2026-000001'",
    )
    R.elabel(
        "C-6b-endpoint",
        "Reject edge endpoint/key mutation",
        "ERR_EDGE_CORE_FIELDS_IMMUTABLE",
        "UPDATE relationship_edges SET target_claimant_id='CLMT-000001', canonical_dst_key='CLAIMANT:CLMT-000001' WHERE edge_id='EDGE-2026-000001'",
    )
    R.elabel(
        "NEW-4a",
        "Reject edge last_observed_utc regression while is_active remains unchanged",
        "ERR_EDGE_OBSERVED_TIME_REGRESSION",
        "UPDATE relationship_edges SET last_observed_utc='2026-01-06T00:00:00Z' WHERE edge_id='EDGE-2026-000001'",
    )
    R.t(
        "NEW-4b",
        "Allow valid edge last_observed_utc advancement while is_active remains unchanged",
        "UPDATE relationship_edges SET last_observed_utc='2026-01-11T00:00:00Z' WHERE edge_id='EDGE-2026-000001'",
    )
    R.elabel(
        "C-6c",
        "Reject silent edge deactivation without RELATIONSHIP_EDGE_DEACTIVATED event",
        "ERR_EDGE_DEACTIVATION_REQUIRES_EVENT",
        "UPDATE relationship_edges SET is_active=0 WHERE edge_id='EDGE-2026-000001'",
    )
    deact_payload = '{"claim_id":"CLM-2026-000001","edge_id":"EDGE-2026-000001"}'
    add_event('RELATIONSHIP_EDGE_DEACTIVATED', 'RelationshipEdge', 'EDGE-2026-000001', 'CLM-2026-000001', 'USR-SIU-001', '2026-01-11T01:00:00Z', deact_payload)
    R.t(
        "C-6c-ok",
        "Deactivate EDGE-2026-000001 with matching RELATIONSHIP_EDGE_DEACTIVATED event",
        "UPDATE relationship_edges SET is_active=0 WHERE edge_id='EDGE-2026-000001'",
    )
    R.elabel(
        "C-6d",
        "Reject edge reactivation (is_active 0 -> 1)",
        "ERR_EDGE_REACTIVATION_FORBIDDEN",
        "UPDATE relationship_edges SET is_active=1 WHERE edge_id='EDGE-2026-000001'",
    )
    R.elabel(
        "C-6e",
        "Reject DELETE FROM relationship_edges",
        "ERR_EDGE_DELETE_FORBIDDEN",
        "DELETE FROM relationship_edges WHERE edge_id='EDGE-2026-000001'",
    )

    print("\n== C-6: FRAUD INDICATORS APPEND-ONLY & CANONICAL JSON NUMERIC POLICY (NEW-6) ==")
    R.t(
        "SEED-11",
        "Insert indicator FIND-2026-000001 (IND-03, 35.0) on CLM-2026-000001",
        "INSERT INTO fraud_indicators (indicator_id,claim_id,indicator_code,pillar,dedup_scope,canonical_evidence_token,severity,raw_points,max_points,normalized_value,feature_snapshot_json,computed_at_utc) VALUES ('FIND-2026-000001','CLM-2026-000001','IND-03','FINANCIAL','CLAIM','DUP_FP:' || ?,'CRITICAL',35.0,35.0,1.0,'{\"k\":1}','2026-01-05T00:00:00Z')",
        (fp,),
    )
    R.elabel(
        "C-6f-upd",
        "Reject UPDATE on fraud_indicators",
        "ERR_FRAUD_INDICATOR_MUTATION_FORBIDDEN",
        "UPDATE fraud_indicators SET raw_points=10.0 WHERE indicator_id='FIND-2026-000001'",
    )
    R.elabel(
        "C-6f-del",
        "Reject DELETE on fraud_indicators",
        "ERR_FRAUD_INDICATOR_DELETE_FORBIDDEN",
        "DELETE FROM fraud_indicators WHERE indicator_id='FIND-2026-000001'",
    )
    # Test finite float allowed in feature_snapshot_json (NEW-6)
    R.t(
        "NEW-6a",
        "Insert indicator FIND-2026-000002 (IND-14, 12.0) with finite canonical float in feature_snapshot_json",
        "INSERT INTO fraud_indicators VALUES ('FIND-2026-000002','CLM-2026-000001','IND-14','BEHAVIORAL','CLAIM','VEL:CLMT-000001','HIGH',12.0,16.0,0.75,'{\"k\":2,\"z_score\":2.5}','2026-01-05T00:00:00Z')",
    )
    # Test NaN, Infinity, whitespace, key order, and float rejection in immutable_events
    R.assert_eq(
        "NEW-6b",
        "is_canonical_json rejects NaN, Infinity, -Infinity, duplicate keys, unsorted keys, whitespace, ASCII-escaped UTF-8",
        [
            is_canonical_json('{"a":NaN}'),
            is_canonical_json('{"a":Infinity}'),
            is_canonical_json('{"a":-Infinity}'),
            is_canonical_json('{"a":1,"a":2}'),
            is_canonical_json('{"b":1,"a":2}'),
            is_canonical_json('{"a": 1}'),
            is_canonical_json('{"note":"Ren\\u00e9e"}'),
            is_canonical_json('[1,2,3]'),
            is_canonical_json('invalid'),
        ],
        [0, 0, 0, 0, 0, 0, 0, 0, 0],
    )
    R.assert_eq(
        "NEW-6c",
        "is_canonical_json accepts canonical integer, finite float (for feature snapshots), and raw UTF-8 Unicode objects",
        [
            is_canonical_json('{"a":1,"b":"x"}'),
            is_canonical_json('{"z_cpt":2.5}'),
            is_canonical_json('{"note":"Renée|東京|🔍"}'),
        ],
        [1, 1, 1],
    )
    # Verify float in immutable_events.payload_json is rejected by trg_events_chain_insert
    float_payload = '{"amount_cents":1.5}'
    float_psha = sha256_hex(float_payload)
    next_seq = con.execute("SELECT COALESCE(MAX(sequence_no),0)+1 FROM immutable_events").fetchone()[0]
    next_eid = f"EVT-2026-{next_seq:07d}"
    float_pi = (
        f"ST-EVT-V2|11:sequence_no=I{next_seq};8:event_id=S16:{next_eid};"
        f"10:event_type=S15:CLAIM_SUBMITTED;11:entity_type=S5:Claim;"
        f"9:entity_id=S15:CLM-2026-000001;8:claim_id=S15:CLM-2026-000001;"
        f"8:actor_id=S3:SYS;15:occurred_at_utc=S20:2026-01-12T17:00:00Z;"
        f"14:payload_sha256=S64:{float_psha};15:prev_event_hash=S64:{chain};"
    )
    R.elabel(
        "NEW-6d",
        "Reject float numeric value inside immutable_events.payload_json",
        "ERR_EVENT_PAYLOAD_FLOAT_FORBIDDEN",
        "INSERT INTO immutable_events VALUES (?,?,?,?,?,?,'SYS','2026-01-12T17:00:00Z',?,?,?,?)",
        (next_seq, next_eid, 'CLAIM_SUBMITTED', 'Claim', 'CLM-2026-000001', 'CLM-2026-000001', float_payload, float_psha, chain, sha256_hex(float_pi)),
    )

    print("\n== C-6 & NEW-2: INVESTIGATIONS FSM, DELETE BLOCK, AND FRESH SIU_REFERRED PROPAGATION ==")
    R.elabel(
        "NEW-2c",
        "Block direct fabrication of siu_referred=1 on fresh claim CLM-2026-000002",
        "ERR_CLAIM_SIU_REFERRAL_REQUIRES_HOLD_OR_CONFIRMED_FRAUD",
        "UPDATE claims SET siu_referred=1 WHERE claim_id='CLM-2026-000002'",
    )
    # Test investigation on fresh claim CLM-2026-000002 (where siu_referred is still 0!)
    R.t(
        "SEED-12",
        "Insert investigation INVG-2026-000001 on fresh claim CLM-2026-000002 (siu_referred=0)",
        "INSERT INTO investigations (investigation_id,primary_claim_id,subject_claimant_id,investigation_status,priority,assigned_investigator_id,opened_at_utc,updated_at_utc,estimated_exposure_cents,case_summary_notes) VALUES ('INVG-2026-000001','CLM-2026-000002','CLMT-000002','OPEN','P2_HIGH','I1','2026-01-07T09:00:00Z','2026-01-07T09:00:00Z',420000,'n')",
    )
    R.elabel(
        "C-6a-del",
        "Reject DELETE FROM investigations",
        "ERR_INVESTIGATION_DELETE_FORBIDDEN",
        "DELETE FROM investigations WHERE investigation_id='INVG-2026-000001'",
    )
    R.t("INVG-01", "Advance investigation to EVIDENCE_COLLECTION", "UPDATE investigations SET investigation_status='EVIDENCE_COLLECTION', updated_at_utc='2026-01-09T09:00:00Z' WHERE investigation_id='INVG-2026-000001'")
    R.t("INVG-02", "Advance investigation to SIU_FIELD_REVIEW", "UPDATE investigations SET investigation_status='SIU_FIELD_REVIEW', updated_at_utc='2026-01-10T09:00:00Z' WHERE investigation_id='INVG-2026-000001'")
    R.t("INVG-03", "Close investigation as CLOSED_CONFIRMED_FRAUD", "UPDATE investigations SET investigation_status='CLOSED_CONFIRMED_FRAUD', updated_at_utc='2026-01-11T09:00:00Z', closed_at_utc='2026-01-11T09:00:00Z', ruling_outcome='CONFIRMED_FRAUD' WHERE investigation_id='INVG-2026-000001'")
    R.assert_eq(
        "C-6j-invg",
        "Closing investigation as CLOSED_CONFIRMED_FRAUD flips fresh claim CLM-2026-000002 siu_referred 0 -> 1",
        con.execute("SELECT siu_referred FROM claims WHERE claim_id='CLM-2026-000002'").fetchone()[0],
        1,
    )
    R.elabel(
        "C-6a-closed",
        "Reject mutation of closed investigation (ERR_CLOSED_INVESTIGATION_IMMUTABLE)",
        "ERR_CLOSED_INVESTIGATION_IMMUTABLE",
        "UPDATE investigations SET case_summary_notes='tampered' WHERE investigation_id='INVG-2026-000001'",
    )

    print("\n== C-6 & NEW-1: ST-SCORE-V1 RECONCILIATION & SQLITE SCORE BOUNDS ==")
    # First test 0-indicator claim CLM-2026-000002: cannot be assigned nonzero score!
    bad_zero_ind_digest = sha256_hex("ST-SCORE-V1|CLM-2026-000002|IND_COUNT:0|IEF:99.99")
    R.elabel(
        "NEW-1c",
        "Block assigning nonzero score (99.99) to claim with 0 fraud_indicators",
        "ERR_SCORE_ZERO_INDICATORS_NONZERO_FORBIDDEN",
        "UPDATE claims SET latest_ief_score=99.99, latest_risk_tier='CRITICAL', scoring_evidence_sha256=? WHERE claim_id='CLM-2026-000002'",
        (bad_zero_ind_digest,),
    )
    zero_ind_digest = sha256_hex("ST-SCORE-V1|CLM-2026-000002|IND_COUNT:0|IEF:0.00")
    R.t(
        "NEW-1d",
        "Accept 0.00 LOW score with valid ST-SCORE-V1 digest on 0-indicator claim",
        "UPDATE claims SET latest_ief_score=0.0, latest_risk_tier='LOW', scoring_evidence_sha256=? WHERE claim_id='CLM-2026-000002'",
        (zero_ind_digest,),
    )

    # Next test CLM-2026-000001 which currently has IND-03 (35.0) + IND-14 (12.0) -> true S_base = 24.424242 -> 24.42 (LOW)
    rows = con.execute(
        "SELECT indicator_code, pillar, raw_points, normalized_value, canonical_evidence_token FROM fraud_indicators WHERE claim_id='CLM-2026-000001' ORDER BY indicator_code ASC, canonical_evidence_token ASC"
    ).fetchall()
    tok = ''.join(f"|IND:{c}:{p}:{rp:.3f}:{nv:.3f}:{t_}" for c, p, rp, nv, t_ in rows)

    # Verify that old un-reconciled score 30.76 is rejected for IND-03 + IND-14!
    digest_3076 = sha256_hex(f"ST-SCORE-V1|CLM-2026-000001|IND_COUNT:{len(rows)}{tok}|IEF:30.76")
    R.elabel(
        "NEW-1e",
        "Block out-of-bounds score 30.76 on CLM-2026-000001 (IND-03 + IND-14 has max S_base=24.42)",
        "ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS",
        "UPDATE claims SET latest_ief_score=30.76, latest_risk_tier='MEDIUM', scoring_evidence_sha256=? WHERE claim_id='CLM-2026-000001'",
        (digest_3076,),
    )
    # Verify that zeroing the score (0.00) on a claim with indicators is blocked!
    digest_000 = sha256_hex(f"ST-SCORE-V1|CLM-2026-000001|IND_COUNT:{len(rows)}{tok}|IEF:0.00")
    R.elabel(
        "NEW-1f",
        "Block zeroing score (0.00) on CLM-2026-000001 when indicators are present",
        "ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS",
        "UPDATE claims SET latest_ief_score=0.0, latest_risk_tier='LOW', scoring_evidence_sha256=? WHERE claim_id='CLM-2026-000001'",
        (digest_000,),
    )

    # Now write reconciled true score 24.42 (LOW) for IND-03 (35.0) + IND-14 (12.0, norm 0.750)
    content_2442 = f"ST-SCORE-V1|CLM-2026-000001|IND_COUNT:{len(rows)}{tok}|IEF:24.42"
    exp_digest_2442 = sha256_hex(content_2442)
    R.t(
        "C-6g",
        "Accept reconciled score 24.42 (LOW) with valid ST-SCORE-V1 digest on CLM-2026-000001",
        "UPDATE claims SET latest_ief_score=24.42, latest_risk_tier='LOW', scoring_evidence_sha256=? WHERE claim_id='CLM-2026-000001'",
        (exp_digest_2442,),
    )
    R.elabel(
        "C-6h",
        "Reject score write with mismatched risk tier",
        "ERR_SCORE_TIER_MISMATCH",
        "UPDATE claims SET latest_risk_tier='HIGH' WHERE claim_id='CLM-2026-000001'",
    )
    R.elabel(
        "C-6i",
        "Reject score write with mismatched ST-SCORE-V1 digest",
        "ERR_SCORE_EVIDENCE_DIGEST_MISMATCH",
        "UPDATE claims SET latest_ief_score=20.0, scoring_evidence_sha256='" + '0'*64 + "' WHERE claim_id='CLM-2026-000001'",
    )

    # Also test hard-collusion pair (IND-01 + IND-03 shared between CLM-2026-000001 and CLM-2026-000002) -> 65.00 HIGH
    R.t(
        "SEED-13",
        "Insert IND-01 shared payout account on CLM-2026-000001",
        "INSERT INTO fraud_indicators VALUES ('FIND-2026-000003','CLM-2026-000001','IND-01','NETWORK','ENTITY','BANK:' || ?,'HIGH',20.0,35.0,0.571,'{\"k\":2}','2026-01-05T00:00:00Z')",
        ('b1'*32,),
    )
    R.t(
        "SEED-14",
        "Insert IND-01 shared payout account on CLM-2026-000002",
        "INSERT INTO fraud_indicators VALUES ('FIND-2026-000004','CLM-2026-000002','IND-01','NETWORK','ENTITY','BANK:' || ?,'HIGH',20.0,35.0,0.571,'{\"k\":2}','2026-01-05T00:00:00Z')",
        ('b1'*32,),
    )
    R.t(
        "SEED-15",
        "Insert IND-03 shared duplicate fingerprint on CLM-2026-000002",
        "INSERT INTO fraud_indicators VALUES ('FIND-2026-000005','CLM-2026-000002','IND-03','FINANCIAL','CLAIM','DUP_FP:' || ?,'CRITICAL',35.0,35.0,1.0,'{\"k\":1}','2026-01-05T00:00:00Z')",
        (fp,),
    )
    rows_c2 = con.execute(
        "SELECT indicator_code, pillar, raw_points, normalized_value, canonical_evidence_token FROM fraud_indicators WHERE claim_id='CLM-2026-000002' ORDER BY indicator_code ASC, canonical_evidence_token ASC"
    ).fetchall()
    tok_c2 = ''.join(f"|IND:{c}:{p}:{rp:.3f}:{nv:.3f}:{t_}" for c, p, rp, nv, t_ in rows_c2)
    digest_c2_65 = sha256_hex(f"ST-SCORE-V1|CLM-2026-000002|IND_COUNT:{len(rows_c2)}{tok_c2}|IEF:65.00")
    R.t(
        "C-7-sql",
        "Accept hard-collusion floor score 65.00 (HIGH) on CLM-2026-000002 with shared (IND-01, IND-03) pair",
        "UPDATE claims SET latest_ief_score=65.0, latest_risk_tier='HIGH', scoring_evidence_sha256=? WHERE claim_id='CLM-2026-000002'",
        (digest_c2_65,),
    )

    con.close()
    total = R.passed + R.failed
    print(f"\n== SUMMARY: passed={R.passed} failed={R.failed} total={total} (plus 1 subprocess self-test) ==")
    if R.failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()

import re, json, hashlib, sqlite3, os

MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ARCH-ST-010.md")
md = open(MD, encoding='utf-8').read()
fences = re.findall(r"```sql\n(.*?)```", md, re.S)
print("num sql fences:", len(fences))
ops, trigs, gt = fences[1], fences[2], fences[3]

def sha256_hex(s):
    if isinstance(s, bytes): s = s.decode('utf-8')
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def is_canonical_json(s):
    try:
        obj = json.loads(s)
    except Exception:
        return 0
    try:
        canon = json.dumps(obj, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    except Exception:
        return 0
    return 1 if canon == s else 0

def connect():
    con = sqlite3.connect(':memory:')
    con.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
    con.create_function('is_canonical_json', 1, is_canonical_json, deterministic=True)
    con.executescript("""PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;""")
    con.executescript(ops)
    con.executescript(trigs)
    return con

def try_sql(con, label, sql, params=()):
    try:
        con.execute(sql, params)
        print(f"[OK   ] {label}")
        return True, None
    except sqlite3.Error as e:
        print(f"[BLOCK] {label} -> {e}")
        return False, str(e)

events = []
def chain_head(con):
    return len(events)

def add_event(con, seq, event_type, entity_type, entity_id, claim_id, actor, occ, payload, expected_ok=True, bad_prev=None, bad_seq=None):
    global events
    psha = sha256_hex(payload)
    prev = bad_prev if bad_prev is not None else (events[-1] if events else '0'*64)
    useseq = bad_seq if bad_seq is not None else len(events)+1
    # compute preimage exactly per grammar
    def L(s): return len(s.encode('utf-8'))
    parts=['ST-EVT-V2|']
    parts.append(f'11:sequence_no=I{useseq};')
    parts.append(f'8:event_id=S16:EVT-2026-{useseq:07d};')
    parts.append(f'10:event_type=S{L(etype_map[event_type])}:{etype_map[event_type]};')
    parts.append(f'11:entity_type=S{L(entity_type)}:{entity_type};')
    parts.append(f'9:entity_id=S{L(entity_id)}:{entity_id};')
    parts.append('8:claim_id=N;' if claim_id is None else f'8:claim_id=S{L(claim_id)}:{claim_id};')
    parts.append(f'8:actor_id=S{L(actor)}:{actor};')
    parts.append(f'15:occurred_at_utc=S{L(occ)}:{occ};')
    parts.append(f'14:payload_sha256=S64:{psha};')
    parts.append(f'15:prev_event_hash=S64:{prev};')
    preimage=''.join(parts)
    eh = sha256_hex(preimage)
    eid = f'EVT-2026-{useseq:07d}'
    sql = "INSERT INTO immutable_events (sequence_no,event_id,event_type,entity_type,entity_id,claim_id,actor_id,occurred_at_utc,payload_json,payload_sha256,prev_event_hash,event_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
    try:
        con.execute(sql,(useseq,eid,event_type,entity_type,entity_id,claim_id,actor,occ,payload,psha,prev,eh))
        print(f"[OK   ] EVENT seq={useseq} {event_type}")
        events.append(eh)
        return True
    except sqlite3.Error as e:
        print(f"[BLOCK] EVENT seq={useseq} {event_type} -> {e}")
        raise

etype_map = {t:t for t in ['INGESTION_EXCEPTION_RECORDED','CLAIM_SUBMITTED','INVOICE_SUBMITTED','INVOICE_APPROVED','INVOICE_APPROVAL_ADJUSTED','CLAIM_APPROVED','PAYMENT_AUTHORIZED','PAYMENT_BLOCKED','PAYMENT_DISBURSED','PAYMENT_CLAWBACK_REVERSED','CLAIM_SIU_HOLD_PLACED','CLAIM_DENIED','INVESTIGATION_OPENED','INVESTIGATION_STATUS_CHANGED','INVESTIGATION_CLOSED']}

sha256_hex_pre_prev = '0'*64  # placeholder set after genesis

con = connect()
print("\n== schema objects ==")
n_tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
n_triggers = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
print("tables:", n_tables, "| triggers:", n_triggers)

# --- seed minimal data ---
try_sql(con, "seed claimant", "INSERT INTO claimants VALUES ('CLMT-000001','Test User','1990-05-10','" + 'a'*64 + "','+12025550001','u@x.com','100 MAIN ST','" + 'b'*64 + "','" + 'c'*64 + "','2025-12-01T00:00:00Z')")
try_sql(con, "seed provider", "INSERT INTO providers VALUES ('PRV-000001','TestBody','AUTO_BODY','NPI-1','" + 'd'*64 + "','+12025550002','200 OAK ST','" + 'e'*64 + "','" + 'f'*64 + "','IN_NETWORK','2025-12-01T00:00:00Z')")
try_sql(con, "seed policy", "INSERT INTO policies VALUES ('POL-2026-000001','CLMT-000001','PN-1','AUTO','ACTIVE','2025-01-01T00:00:00Z','2026-12-31T00:00:00Z','2025-01-01T00:00:00Z',500000,50000,10000)")
try_sql(con, "seed incident", "INSERT INTO incidents VALUES ('INC-2026-000001','2026-01-05T08:00:00Z','2026-01-05T20:00:00Z','AUTO_COLLISION','TX','300 ELM ST','9==aw2','RPT-1','CLEAR','collision')")
fp = sha256_hex("AB-FRAME-101|2026-01-05|2026-01-05|420000")
try_sql(con, "seed claim", "INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id) VALUES ('CLM-2026-000001','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1')")
try_sql(con, "seed invoice", "INSERT INTO invoices (invoice_id,claim_id,provider_id,provider_invoice_number,invoice_status,service_start_utc,service_end_utc,submitted_at_utc,cpt_or_line_code,line_item_fingerprint,billed_cents) VALUES ('INV-PRV-PRV-000001-000001','CLM-2026-000001','PRV-000001','PI-1','SUBMITTED','2026-01-05T09:00:00Z','2026-01-05T10:00:00Z','2026-01-05T22:00:00Z','AB-FRAME-101',?,420000)", (fp,))

print("\n== TEST A: direct invoice SUBMITTED->APPROVED while claim is SUBMITTED (doc FSM permits this) ==")
try_sql(con, "A1 direct invoice approval", "UPDATE invoices SET invoice_status='APPROVED', approved_cents=370000, historical_approved_cents=370000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
st = con.execute("SELECT invoice_status, approved_cents FROM invoices").fetchone()
print("   invoice after A1:", st)

print("\n== TEST B: move claim to UNDER_REVIEW then approve invoice (canonical path) ==")
try_sql(con, "B1 claim -> UNDER_REVIEW", "UPDATE claims SET claim_status='UNDER_REVIEW' WHERE claim_id='CLM-2026-000001'")
try_sql(con, "B2 invoice approval", "UPDATE invoices SET invoice_status='APPROVED', approved_cents=370000, historical_approved_cents=370000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
print("   claim/invoice state:", con.execute("SELECT claim_status, approved_amount_cents, historical_approved_cents, reserved_authorized_cents FROM claims").fetchone(), con.execute("SELECT invoice_status FROM invoices").fetchone())

print("\n== TEST C: same-status tamper of approved_cents (should be blocked) ==")
try_sql(con, "C1 tamper approved 370000->400000", "UPDATE invoices SET approved_cents=400000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")

print("\n== TEST D: authorized adjustment via INVOICE_APPROVAL_ADJUSTED event ==")
payload_adj = '{"adjustment_authorized":true,"invoice_id":"INV-PRV-PRV-000001-000001","new_approved_cents":400000,"old_approved_cents":370000}'
add_event(con, 1, 'INVOICE_APPROVAL_ADJUSTED', 'Invoice', 'INV-PRV-PRV-000001-000001', 'CLM-2026-000001', 'USR-ADJ-001', '2026-01-06T15:00:00Z', payload_adj)
try_sql(con, "D1 authorized adjustment to 400000", "UPDATE invoices SET approved_cents=400000, historical_approved_cents=400000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
try_sql(con, "D2 unauthorized same-status adjustment w/o event", "UPDATE invoices SET approved_cents=410000, historical_approved_cents=410000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
print("   invoice:", con.execute("SELECT invoice_status, approved_cents, historical_approved_cents FROM invoices").fetchone())
print("   claim  :", con.execute("SELECT claim_status, approved_amount_cents, historical_approved_cents FROM claims").fetchone())

print("\n== TEST E: payment authorization + cap enforcement ==")
try_sql(con, "E1 authorize 200000", "INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000001','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',200000,'ID1','2026-01-07T08:00:00Z','USR-FIN-001')")
try_sql(con, "E2 authorize 150000", "INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000002','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',150000,'ID2','2026-01-07T08:00:00Z','USR-FIN-001')")
try_sql(con, "E3 overpay attempt 1 cent", "INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000003','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',51000,'ID3','2026-01-07T08:00:00Z','USR-FIN-001')")
try_sql(con, "E4 record BLOCKED_OVERPAYMENT", "INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by,block_reason_code) VALUES ('PAY-2026-000003','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','BLOCKED_OVERPAYMENT',51000,'ID3','2026-01-07T08:00:00Z','USR-FIN-001','ERR_PAYMENT_EXCEEDS_APPROVED_CAP')")
print("   claim rollups:", con.execute("SELECT claim_status, approved_amount_cents, reserved_authorized_cents FROM claims").fetchone())
print("   invoice rollups:", con.execute("SELECT invoice_status, approved_cents, reserved_authorized_cents FROM invoices").fetchone())

print("\n== TEST F: blocked-overpayment cannot be re-used/converted to AUTHORIZED (Any-other-update) ==")
try_sql(con, "F1 BLOCKED -> AUTHORIZED", "UPDATE payments SET payment_status='AUTHORIZED' WHERE payment_id='PAY-2026-000003'")

print("\n== TEST G: disbursement lifecycle ==")
try_sql(con, "G1 disburse PAY-1", "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=200000, net_paid_cents=200000, disbursed_at_utc='2026-01-07T12:00:00Z', external_bank_tx_ref='ACH-2026-000001' WHERE payment_id='PAY-2026-000001'")
print("   claim/invoice:", con.execute("SELECT claim_status FROM claims").fetchone(), con.execute("SELECT invoice_status, net_paid_cents, reserved_authorized_cents FROM invoices").fetchone())
try_sql(con, "G2 tamper bank ref after disbursement", "UPDATE payments SET external_bank_tx_ref='ACH-HACKED' WHERE payment_id='PAY-2026-000001'")
try_sql(con, "G3 tamper amount after disbursement", "UPDATE payments SET amount_cents=999999 WHERE payment_id='PAY-2026-000001'")
try_sql(con, "G4 direct INSERT of DISBURSED row", "INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,disbursed_amount_cents,net_paid_cents,idempotency_key,created_at_utc,disbursed_at_utc,external_bank_tx_ref,authorized_by) VALUES ('PAY-2026-000009','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','DISBURSED',100000,100000,100000,'ID9','2026-01-07T08:00:00Z','2026-01-07T12:00:00Z','ACH-X','USR')")

print("\n== TEST H: claim -> SIU_HOLD while reservation outstanding (concern #5) ==")
# claim currently PARTIALLY_PAID (PAY-2 still AUTHORIZED, reservation 150000)
res = con.execute("SELECT claim_status, reserved_authorized_cents, net_paid_cents, approved_amount_cents FROM claims").fetchone()
print("   pre-HOLD state:", res)
try_sql(con, "H1 APPROVED/PARTIALLY_PAID -> SIU_HOLD with reservation outstanding", "UPDATE claims SET claim_status='SIU_HOLD' WHERE claim_id='CLM-2026-000001'")
try_sql(con, "H2 disburse PAY-2 while on SIU_HOLD", "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=150000, net_paid_cents=150000, disbursed_at_utc='2026-01-08T12:00:00Z', external_bank_tx_ref='ACH-2026-000002' WHERE payment_id='PAY-2026-000002'")
try_sql(con, "H3 deny claim while reservation outstanding", "UPDATE claims SET claim_status='DENIED', claim_status='DENIED' WHERE claim_id='CLM-2026-000001'")
try_sql(con, "H4 SIU_HOLD -> APPROVED with reservation still outstanding", "UPDATE claims SET claim_status='APPROVED' WHERE claim_id='CLM-2026-000001'")
try_sql(con, "H5 now disbursement after hold release", "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=150000, net_paid_cents=150000, disbursed_at_utc='2026-01-08T12:00:00Z', external_bank_tx_ref='ACH-2026-000002' WHERE payment_id='PAY-2026-000002'")
print("   post-H5:", con.execute("SELECT claim_status, reserved_authorized_cents, net_paid_cents FROM claims").fetchone())

print("\n== TEST I: clawbacks + historical_approved_cents preservation ==")
try_sql(con, "I1 full clawback PAY-1", "UPDATE payments SET payment_status='REVERSED_CLAWBACK', clawed_back_cents=200000, net_paid_cents=0, reversed_at_utc='2026-01-12T16:45:00Z' WHERE payment_id='PAY-2026-000001'")
try_sql(con, "I2 full clawback PAY-2", "UPDATE payments SET payment_status='REVERSED_CLAWBACK', clawed_back_cents=150000, net_paid_cents=0, reversed_at_utc='2026-01-12T17:00:00Z' WHERE payment_id='PAY-2026-000002'")
print("   after full clawback:", con.execute("SELECT claim_status, approved_amount_cents, gross_disbursed_cents, clawed_back_cents, net_paid_cents, historical_approved_cents FROM claims").fetchone())
try_sql(con, "I3 reduce historical_approved_cents on invoice", "UPDATE invoices SET historical_approved_cents=100000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")

print("\n== TEST J: revocation then denial (CRITICAL 7) ==")
try_sql(con, "J1 revoke invoice", "UPDATE invoices SET invoice_status='REVOKED_POST_APPROVAL', approved_cents=0 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
print("   claim after revoke:", con.execute("SELECT claim_status, approved_amount_cents, historical_approved_cents FROM claims").fetchone())
try_sql(con, "J2 deny claim", "UPDATE claims SET claim_status='DENIED' WHERE claim_id='CLM-2026-000001'")
print("   after deny:", con.execute("SELECT claim_status, historical_approved_cents FROM claims").fetchone())
try_sql(con, "J3 resurrect denied claim (DENIED->APPROVED not in FSM)", "UPDATE claims SET claim_status='APPROVED' WHERE claim_id='CLM-2026-000001'")

print("\n== TEST K: event chain integrity ==")
try_sql(con, "K1 update immutable event", "UPDATE immutable_events SET actor_id='HACKED' WHERE sequence_no=1")
try_sql(con, "K2 delete immutable event", "DELETE FROM immutable_events WHERE sequence_no=1")
payload=pd = '{\"x\":1}'
try:
    add_event(con, 2, 'CLAIM_SUBMITTED','Claim','CLM-2026-000001','CLM-2026-000001','USR','2026-01-06T00:00:00Z','{"y":2}', bad_prev='f'*64)
except Exception: pass
try_sql(con, "K4 non-monotonic sequence", "INSERT INTO immutable_events (sequence_no,event_id,event_type,entity_type,entity_id,claim_id,actor_id,occurred_at_utc,payload_json,payload_sha256,prev_event_hash,event_hash) VALUES (5,'EVT-2026-0000005','CLAIM_SUBMITTED','Claim','CLM-2026-000001','CLM-2026-000001','X','2026-01-06T00:00:00Z','{\"z\":3}','" + sha256_hex('{"z":3}') + "','" + events[-1] + "','" + sha256_hex('x') + "')")

print("\n== TEST L: invoice duplicates ==")
try_sql(con, "L1 second invoice with same fingerprint", "INSERT INTO invoices (invoice_id,claim_id,provider_id,provider_invoice_number,invoice_status,service_start_utc,service_end_utc,submitted_at_utc,cpt_or_line_code,line_item_fingerprint,billed_cents) VALUES ('INV-PRV-PRV-000001-000002','CLM-2026-000001','PRV-000001','PI-2','SUBMITTED','2026-01-06T09:00:00Z','2026-01-06T10:00:00Z','2026-01-06T22:00:00Z','AB-FRAME-101',?,420000)", (fp,))

print("\n== TEST M: claim under_review -> direct APPROVED with fabricated aggregates ==")
try_sql(con, "M1 direct claim update attempt", "UPDATE claims SET claim_status='APPROVED' WHERE claim_id='CLM-2026-000001'")

print("\n== TEST N: investigations FSM ==")
try_sql(con, "N1 seed investigation", "INSERT INTO investigations (investigation_id,primary_claim_id,subject_claimant_id,investigation_status,priority,assigned_investigator_id,opened_at_utc,updated_at_utc,estimated_exposure_cents,case_summary_notes) VALUES ('INVG-2026-000001','CLM-2026-000001','CLMT-000001','OPEN','P2_HIGH','INV-1','2026-01-07T09:00:00Z','2026-01-07T09:00:00Z',400000,'notes')")
try_sql(con, "N2 OPEN -> EVIDENCE_COLLECTION", "UPDATE investigations SET investigation_status='EVIDENCE_COLLECTION', updated_at_utc='2026-01-08T09:00:00Z' WHERE investigation_id='INVG-2026-000001'")
try_sql(con, "N3 EVIDENCE_COLLECTION -> CLOSED_CONFIRMED_FRAUD", "UPDATE investigations SET investigation_status='CLOSED_CONFIRMED_FRAUD', updated_at_utc='2026-01-09T09:00:00Z', closed_at_utc='2026-01-09T09:00:00Z', ruling_outcome='CONFIRMED_FRAUD' WHERE investigation_id='INVG-2026-000001'")
try_sql(con, "N4 mutate closed investigation", "UPDATE investigations SET investigation_status='OPEN', closed_at_utc=NULL, ruling_outcome=NULL, updated_at_utc='2026-01-10T09:00:00Z' WHERE investigation_id='INVG-2026-000001'")

con.close()
print("\nALL DONE")

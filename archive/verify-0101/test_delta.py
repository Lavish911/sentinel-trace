import re, json, hashlib, sqlite3, os

WORK = os.path.dirname(os.path.abspath(__file__))
ops = open(os.path.join(WORK,'ops_0101.sql'), encoding='utf-8').read()
trigs = open(os.path.join(WORK,'trigs_0101.sql'), encoding='utf-8').read()

# Prove the sibling SQL is byte-identical to the document's §5.1/§5.2 fences.
MD = os.path.join(WORK, '..', '..', 'ARCH-ST-010.1.md')
_fences = re.findall(r'```sql\n(.*?)```', open(MD, encoding='utf-8').read(), re.S)
assert len(_fences) == 5, f"expected 5 sql fences in ARCH-ST-010.1.md, got {len(_fences)}"
assert ops.strip() == _fences[1].strip() and trigs.strip() == _fences[2].strip(), \
    "sibling SQL does not match the document fences"
print("fence byte-identity: document §5.1/§5.2 == ops_0101.sql/trigs_0101.sql")

def sha256_hex(s):
    if isinstance(s, bytes): s = s.decode('utf-8')
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def is_canonical_json(s):
    try: obj = json.loads(s)
    except Exception: return 0
    try: return 1 if json.dumps(obj, ensure_ascii=False, separators=(',',':'), sort_keys=True) == s else 0
    except Exception: return 0

con = sqlite3.connect(':memory:')
chain = '0'*64
con.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
con.create_function('is_canonical_json', 1, is_canonical_json, deterministic=True)
con.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
con.executescript(ops)
con.executescript(trigs)

n_tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
n_trigs = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
print(f"schema build OK: tables={n_tables} triggers={n_trigs}")

def t(label, sql, params=()):
    try:
        con.execute(sql, params); print(f"[OK   ] {label}")
        return True
    except sqlite3.Error as e:
        print(f"[BLOCK] {label} -> {e}")
        return False

def elabel(lbl, err, sql, params=()):
    """expect specific error substring"""
    try:
        con.execute(sql, params); print(f"[FAIL ] {lbl} expected {err} but succeeded"); return False
    except sqlite3.Error as e:
        ok = err in str(e); print(f"[{'PASS' if ok else 'FAIL '}] {lbl} -> {e}"); return ok

def add_event(con, event_type, entity_type, entity_id, claim_id, actor, occ, payload):
    global chain
    # syntax: CLAIM|INVOICE subqueries reference NEW chains? we maintain Python-side prev hash
    psha = sha256_hex(payload)
    prev = chain; seq = con.execute("SELECT COALESCE(MAX(sequence_no),0)+1 FROM immutable_events").fetchone()[0]
    eid = f"EVT-2026-{seq:07d}"
    def L(s): return len(s.encode('utf-8'))
    parts = ['ST-EVT-V2|',
        f'11:sequence_no=I{seq};',
        f'8:event_id=S{L(eid)}:{eid};',
        f'10:event_type=S{L(event_type)}:{event_type};',
        f'11:entity_type=S{L(entity_type)}:{entity_type};',
        f'9:entity_id=S{L(entity_id)}:{entity_id};',
        '8:claim_id=N;' if claim_id is None else f'8:claim_id=S{L(claim_id)}:{claim_id};',
        f'8:actor_id=S{L(actor)}:{actor};',
        f'15:occurred_at_utc=S{L(occ)}:{occ};',
        f'14:payload_sha256=S64:{psha};',
        f'15:prev_event_hash=S64:{prev};']
    preimage = ''.join(parts)
    eh = sha256_hex(preimage)
    con.execute("INSERT INTO immutable_events (sequence_no,event_id,event_type,entity_type,entity_id,claim_id,actor_id,occurred_at_utc,payload_json,payload_sha256,prev_event_hash,event_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (seq,eid,event_type,entity_type,entity_id,claim_id,actor,occ,payload,psha,prev,eh))
    chain = eh
    return seq

print("\n== SEED ==")
t("seed claimant","INSERT INTO claimants VALUES ('CLMT-000001','T','1990-05-10','" + 'ab'*32 + "','+12025550001','u@x.com','100 MAIN ST','" + 'cd'*32 + "','" + 'ef'*32 + "','2025-12-01T00:00:00Z')")
t("seed provider","INSERT INTO providers VALUES ('PRV-000001','B','AUTO_BODY','NPI-1','" + '12'*32 + "','+12025550002','200 OAK','" + '34'*32 + "','" + '56'*32 + "','IN_NETWORK','2025-12-01T00:00:00Z')")
t("seed policy","INSERT INTO policies VALUES ('POL-2026-000001','CLMT-000001','PN-1','AUTO','ACTIVE','2025-01-01T00:00:00Z','2026-12-31T00:00:00Z','2025-01-01T00:00:00Z',500000,50000,10000)")
t("seed incident","INSERT INTO incidents VALUES ('INC-2026-000001','2026-01-05T08:00:00Z','2026-01-05T20:00:00Z','AUTO_COLLISION','TX','300 ELM','9==aw2','RPT-1','CLEAR','x')")
t("seed claim","INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id) VALUES ('CLM-2026-000001','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1')")
fp = sha256_hex("AB-FRAME-101|2026-01-05|2026-01-05|420000")
t("seed invoice","INSERT INTO invoices (invoice_id,claim_id,provider_id,provider_invoice_number,invoice_status,service_start_utc,service_end_utc,submitted_at_utc,cpt_or_line_code,line_item_fingerprint,billed_cents) VALUES ('INV-PRV-PRV-000001-000001','CLM-2026-000001','PRV-000001','PI-1','SUBMITTED','2026-01-05T09:00:00Z','2026-01-05T10:00:00Z','2026-01-05T22:00:00Z','AB-FRAME-101',?,420000)",(fp,))

print("\n== C-1: invoice approval with claim in SUBMITTED (was dead-lock; now valid) ==")
t("invoice approve 370000 (claim SUBMITTED)","UPDATE invoices SET invoice_status='APPROVED', approved_cents=370000, historical_approved_cents=370000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
print("   claim after:", con.execute("SELECT claim_status, approved_amount_cents, historical_approved_cents, net_paid_cents FROM claims").fetchone())
t("seed second claim","INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id) VALUES ('CLM-2026-000002','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',100000,100000,'ADJ-1')")
try:
    con.execute("UPDATE claims SET claim_status='APPROVED' WHERE claim_id='CLM-2026-000002'")
    print("[FAIL ] C-1b expected block")
except sqlite3.Error as e:
    print("[PASS ] C-1b direct fabricated approval blocked ->", e)

print("\n== PAYMENT + A-2 event enforcement ==")
t("authorize 200000 (pay1)","INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000001','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',200000,'ID1','2026-01-07T08:00:00Z','USR-FIN-001')")
t("authorize 170000 (pay2)","INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000002','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',170000,'ID2','2026-01-07T08:00:00Z','USR-FIN-001')")

elabel("disburse pay1 WITHOUT PAYMENT_AUTHORIZED event","ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT",
       "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=200000, net_paid_cents=200000, disbursed_at_utc='2026-01-07T12:00:00Z', external_bank_tx_ref='ACH-1' WHERE payment_id='PAY-2026-000001'")

psha_authorized = sha256_hex('{"amount_cents":200000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}')
add_event(con,'PAYMENT_AUTHORIZED','Payment','PAY-2026-000001','CLM-2026-000001','USR-FIN-001','2026-01-07T08:00:00Z','{"amount_cents":200000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}')
print("   payer auth event inserted (psha match:", psha_authorized, ")")
t("disburse pay1 WITH event","UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=200000, net_paid_cents=200000, disbursed_at_utc='2026-01-07T12:00:00Z', external_bank_tx_ref='ACH-1' WHERE payment_id='PAY-2026-000001'")
print("   claim status now:", con.execute("SELECT claim_status, net_paid_cents, reserved_authorized_cents FROM claims").fetchone())

print("\n== A-1: SIU_HOLD protocol ==")
t("claim -> SIU_HOLD (allowed, reservations outstanding)","UPDATE claims SET claim_status='SIU_HOLD' WHERE claim_id='CLM-2026-000001'")
print("  claim:", con.execute("SELECT claim_status, siu_referred, reserved_authorized_cents FROM claims").fetchone())
elabel("disburse pay2 on hold","ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL",
       "UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=170000, net_paid_cents=170000, disbursed_at_utc='2026-01-08T12:00:00Z', external_bank_tx_ref='ACH-2' WHERE payment_id='PAY-2026-000002'")
elabel("cancel pay2 WITHOUT event","ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT",
       "UPDATE payments SET payment_status='CANCELLED', reversed_at_utc='2026-01-08T12:00:00Z', cancel_reason='SIU_HOLD_RESERVATION_CLEARED' WHERE payment_id='PAY-2026-000002'")
cancel_payload = '{"amount_cents":170000,"claim_id":"CLM-2026-000001","payment_id":"PAY-2026-000002","payment_status":"CANCELLED","reason_code":"SIU_HOLD_RESERVATION_CLEARED"}'
add_event(con,'PAYMENT_CANCELLED','Payment','PAY-2026-000002','CLM-2026-000001','USR-SIU-001','2026-01-08T12:00:00Z',cancel_payload)
t("cancel pay2 with event","UPDATE payments SET payment_status='CANCELLED', reversed_at_utc='2026-01-08T12:00:00Z', cancel_reason='SIU_HOLD_RESERVATION_CLEARED' WHERE payment_id='PAY-2026-000002'")
print("   claim:", con.execute("SELECT claim_status, reserved_authorized_cents, net_paid_cents, siu_referred FROM claims").fetchone())

elabel("clawback pay1 without event","ERR_CLAWBACK_REQUIRES_EVENT",
       "UPDATE payments SET payment_status='REVERSED_CLAWBACK', clawed_back_cents=200000, net_paid_cents=0, reversed_at_utc='2026-01-12T16:45:00Z' WHERE payment_id='PAY-2026-000001'")
cb_payload = '{"amount_cents":200000,"claim_id":"CLM-2026-000001","clawed_back_cents":200000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}'
add_event(con,'PAYMENT_CLAWBACK_REVERSED','Payment','PAY-2026-000001','CLM-2026-000001','USR-SIU-001','2026-01-12T16:45:00Z',cb_payload)
t("clawback pay1 with event","UPDATE payments SET payment_status='REVERSED_CLAWBACK', clawed_back_cents=200000, net_paid_cents=0, reversed_at_utc='2026-01-12T16:45:00Z' WHERE payment_id='PAY-2026-000001'")
print("   claim post-clawback:", con.execute("SELECT claim_status, reserved_authorized_cents, net_paid_cents, historical_approved_cents FROM claims").fetchone())

t("seed second claimant","INSERT INTO claimants VALUES ('CLMT-000002','T','1990-05-10','" + 'ff'*31 + 'c0' + "','+12025550003','u2@x.com','100 MAIN ST','" + 'ee'*31 + 'd0' + "','" + 'dd'*31 + 'e0' + "','2025-12-01T00:00:00Z')")
print("\n== C-6: edges ==")
try:
    con.execute("INSERT INTO relationship_edges VALUES ('EDGE-2026-000001','SHARED_BANK_ACCOUNT','CLAIMANT','CLMT-000001',NULL,'CLAIMANT',NULL,'CLMT-000001','CLAIMANT:CLMT-000001','CLAIMANT:CLMT-000001',1.0,1,'2026-01-05T00:00:00Z','2026-01-05T00:00:00Z','CLM-2026-000001',1)")
    print("[FAIL ] edge self-edge should be blocked by canonical_src<dst")
except sqlite3.Error as e:
    print("[PASS ] canonical ordering enforced ->", e)
t("seed legit edge","INSERT INTO relationship_edges VALUES ('EDGE-2026-000001','SHARED_BANK_ACCOUNT','CLAIMANT','CLMT-000001',NULL,'CLAIMANT','CLMT-000002',NULL,'CLAIMANT:CLMT-000001','CLAIMANT:CLMT-000002',1.0,1,'2026-01-05T00:00:00Z','2026-01-05T00:00:00Z','CLM-2026-000001',1)")
try:
    con.execute("UPDATE relationship_edges SET strength_weight=0.01 WHERE edge_id='EDGE-2026-000001'")
    print("[FAIL ] strength tamper should block")
except sqlite3.Error as e:
    print("[PASS ] strength immutable ->", e)
elabel("silent deactivate blocked","ERR_EDGE_DEACTIVATION_REQUIRES_EVENT",
       "UPDATE relationship_edges SET is_active=0 WHERE edge_id='EDGE-2026-000001'")
deact_payload = '{"claim_id":"CLM-2026-000001","edge_id":"EDGE-2026-000001"}'
add_event(con,'RELATIONSHIP_EDGE_DEACTIVATED','RelationshipEdge','EDGE-2026-000001','CLM-2026-000001','USR-SIU-001','2026-01-09T00:00:00Z',deact_payload)
t("deactivate with event","UPDATE relationship_edges SET is_active=0 WHERE edge_id='EDGE-2026-000001'")
elabel("reactivation forbidden","ERR_EDGE_REACTIVATION_FORBIDDEN",
       "UPDATE relationship_edges SET is_active=1 WHERE edge_id='EDGE-2026-000001'")
try:
    con.execute("DELETE FROM relationship_edges WHERE edge_id='EDGE-2026-000001'")
    print("[FAIL ] edge delete should block")
except sqlite3.Error as e:
    print("[PASS ] edge delete blocked ->", e)

print("\n== C-6: fraud_indicators append-only ==")
t("insert indicator","INSERT INTO fraud_indicators (indicator_id,claim_id,indicator_code,pillar,dedup_scope,canonical_evidence_token,severity,raw_points,max_points,normalized_value,feature_snapshot_json,computed_at_utc) VALUES ('FIND-2026-000001','CLM-2026-000001','IND-03','FINANCIAL','CLAIM','DUP_FP:' || ?,'CRITICAL',35.0,35.0,1.0,'{\"k\":1}','2026-01-05T00:00:00Z')",(fp,))
try:
    con.execute("UPDATE fraud_indicators SET raw_points=35.0 WHERE indicator_id='FIND-2026-000001'")
    print("[FAIL ] indicator update should block")
    raise SystemExit(1)
except sqlite3.Error as e:
    print("[PASS ] indicator update blocked ->", e)
try:
    con.execute("DELETE FROM fraud_indicators WHERE indicator_id='FIND-2026-000001'")
    print("[FAIL ] indicator delete should block")
except sqlite3.Error as e:
    print("[PASS ] indicator delete blocked ->", e)
try:
    con.execute("INSERT INTO fraud_indicators VALUES ('FIND-2026-000003','CLM-2026-000001','IND-14','BEHAVIORAL','CLAIM','VEL:CLMT-000001','HIGH',12.0,16.0,1.0,'{\"k\":2}','2026-01-05T00:00:00Z')")
    print("[OK   ] third indicator (3 rows) inserted")
except sqlite3.Error as e:
    print("[BLOCK] third indicator insert ->", e)

print("\n== C-6: investigations delete protection + siu_referred propagation ==")
t("seed investigation","INSERT INTO investigations (investigation_id,primary_claim_id,subject_claimant_id,investigation_status,priority,assigned_investigator_id,opened_at_utc,updated_at_utc,estimated_exposure_cents,case_summary_notes) VALUES ('INVG-2026-000001','CLM-2026-000001','CLMT-000001','OPEN','P2_HIGH','I1','2026-01-07T09:00:00Z','2026-01-07T09:00:00Z',420000,'n')")
try:
    con.execute("DELETE FROM investigations WHERE investigation_id='INVG-2026-000001'")
    print("[FAIL ] investigation delete should block")
except sqlite3.Error as e:
    print("[PASS ] investigation delete blocked ->", e)
t("close confirmed fraud","UPDATE investigations SET investigation_status='EVIDENCE_COLLECTION', updated_at_utc='2026-01-09T09:00:00Z' WHERE investigation_id='INVG-2026-000001'")
t("close confirmed fraud 2","UPDATE investigations SET investigation_status='SIU_FIELD_REVIEW', updated_at_utc='2026-01-10T09:00:00Z' WHERE investigation_id='INVG-2026-000001'")
t("close confirmed fraud 3","UPDATE investigations SET investigation_status='CLOSED_CONFIRMED_FRAUD', updated_at_utc='2026-01-11T09:00:00Z', closed_at_utc='2026-01-11T09:00:00Z', ruling_outcome='CONFIRMED_FRAUD' WHERE investigation_id='INVG-2026-000001'")
print("   claim siu_referred now:", con.execute("SELECT siu_referred FROM claims WHERE claim_id='CLM-2026-000001'").fetchone())

print("\n== C-6: ST-SCORE-V1 reconciliation ==")
# recompute expected digest in Python (mirror of SQL contract)
rows = con.execute("SELECT indicator_code, pillar, raw_points, normalized_value, canonical_evidence_token FROM fraud_indicators WHERE claim_id='CLM-2026-000001' ORDER BY indicator_code ASC, canonical_evidence_token ASC").fetchall()
def fmt3(x): return f"{x:.3f}"
def fmt2(x): return f"{x:.2f}"
tok = ''.join('|IND:'+c+':'+p+':'+fmt3(rp)+':'+fmt3(nv)+':'+tok_ for c,p,rp,nv,tok_ in rows)
score = 30.76  # test value
content = f"ST-SCORE-V1|CLM-2026-000001|IND_COUNT:{len(rows)}{tok}|IEF:{fmt2(score)}"
exp_digest = sha256_hex(content)
print("   py mirror content:", content)
print("   py mirror digest :", exp_digest)
try:
    con.execute("UPDATE claims SET latest_ief_score=?, latest_risk_tier='MEDIUM', scoring_evidence_sha256=? WHERE claim_id='CLM-2026-000001'", (score, exp_digest))
    print("[OK   ] score write with valid digest accepted")
except sqlite3.Error as e:
    print("[FAIL ] valid digest rejected ->", e)
elabel("score write with WRONG tier","ERR_SCORE_TIER_MISMATCH",
       "UPDATE claims SET latest_risk_tier='HIGH' WHERE claim_id='CLM-2026-000001'")
elabel("score write with WRONG digest","ERR_SCORE_EVIDENCE_DIGEST_MISMATCH",
       "UPDATE claims SET latest_ief_score=35.0, scoring_evidence_sha256='" + '0'*64 + "' WHERE claim_id='CLM-2026-000001'")
# cross-check: SQL-recompute digest equals python mirror
sql_digest = con.execute("""SELECT sha256_hex(
        'ST-SCORE-V1|' || 'CLM-2026-000001'
        || '|IND_COUNT:' || CAST((SELECT COUNT(*) FROM fraud_indicators WHERE claim_id='CLM-2026-000001') AS TEXT)
        || COALESCE(group_concat(ind_tok,''), '')
        || '|IEF:' || printf('%.2f', 30.76))
        FROM (SELECT '|IND:' || indicator_code || ':' || pillar || ':' || printf('%.3f', raw_points)
                     || ':' || printf('%.3f', normalized_value) || ':' || canonical_evidence_token AS ind_tok
              FROM fraud_indicators
              WHERE claim_id='CLM-2026-000001'
              ORDER BY indicator_code ASC, canonical_evidence_token ASC)""").fetchone()[0]
print("   sql-side digest :", sql_digest, "match py:", sql_digest == exp_digest)

print("\n== C-4/new counts & digest ==")
chain_head = None
n_tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
n_trigs = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
print(f"final object counts: tables={n_tables} triggers={n_trigs}")
print("event rows:", con.execute("SELECT COUNT(*) FROM immutable_events").fetchone()[0])
con.close()
print("\nALL DONE")

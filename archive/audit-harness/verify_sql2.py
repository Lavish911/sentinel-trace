import re, json, hashlib, sqlite3, os

MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ARCH-ST-010.md")
md = open(MD, encoding='utf-8').read()
fences = re.findall(r"```sql\n(.*?)```", md, re.S)
ops, trigs = fences[1], fences[2]

def sha256_hex(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def canon(s):
    try: obj = json.loads(s)
    except Exception: return 0
    try: return 1 if json.dumps(obj, ensure_ascii=False, separators=(',',':'), sort_keys=True) == s else 0
    except Exception: return 0

con = sqlite3.connect(':memory:')
con.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
con.create_function('is_canonical_json', 1, canon, deterministic=True)
con.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
con.executescript(ops); con.executescript(trigs)

def t(label, sql, params=()):
    try:
        con.execute(sql, params); print(f"[OK   ] {label}")
    except sqlite3.Error as e:
        print(f"[BLOCK] {label} -> {e}")

hex6='0123456789abcdef'*4
t("seed claimant","INSERT INTO claimants VALUES ('CLMT-000001','T','1990-05-10','" + hex6 + "','+12025550001','u@x.com','100 MAIN ST','" + hex6 + "','" + hex6 + "','2025-12-01T00:00:00Z')")
t("seed provider","INSERT INTO providers VALUES ('PRV-000001','B','AUTO_BODY','NPI-1','" + hex6 + "','+12025550002','200 OAK','" + hex6 + "','" + hex6 + "','IN_NETWORK','2025-12-01T00:00:00Z')")
t("seed policy","INSERT INTO policies VALUES ('POL-2026-000001','CLMT-000001','PN-1','AUTO','ACTIVE','2025-01-01T00:00:00Z','2026-12-31T00:00:00Z','2025-01-01T00:00:00Z',500000,50000,10000)")
t("seed incident","INSERT INTO incidents VALUES ('INC-2026-000001','2026-01-05T08:00:00Z','2026-01-05T20:00:00Z','AUTO_COLLISION','TX','300 ELM','9==aw2','RPT-1','CLEAR','x')")
t("seed claim","INSERT INTO claims (claim_id,policy_id,claimant_id,incident_id,claim_status,submitted_at_utc,claimed_amount_cents,payout_cap_cents,adjustor_id) VALUES ('CLM-2026-000001','POL-2026-000001','CLMT-000001','INC-2026-000001','SUBMITTED','2026-01-05T21:00:00Z',420000,420000,'ADJ-1')")
fp=sha256_hex("AB-FRAME-101|2026-01-05|2026-01-05|420000")
t("seed invoice","INSERT INTO invoices (invoice_id,claim_id,provider_id,provider_invoice_number,invoice_status,service_start_utc,service_end_utc,submitted_at_utc,cpt_or_line_code,line_item_fingerprint,billed_cents) VALUES ('INV-PRV-PRV-000001-000001','CLM-2026-000001','PRV-000001','PI-1','SUBMITTED','2026-01-05T09:00:00Z','2026-01-05T10:00:00Z','2026-01-05T22:00:00Z','AB-FRAME-101',?,420000)",(fp,))

t("delete claim","DELETE FROM claims WHERE claim_id='CLM-2026-000001'")
t("delete invoice","DELETE FROM invoices WHERE invoice_id='INV-PRV-PRV-000001-000001'")
t("delete investigation attempt (no rows yet)","DELETE FROM investigations")

t("claim->UNDER_REVIEW","UPDATE claims SET claim_status='UNDER_REVIEW' WHERE claim_id='CLM-2026-000001'")
t("invoice approve 370000","UPDATE invoices SET invoice_status='APPROVED', approved_cents=370000, historical_approved_cents=370000 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
t("authorize 370000","INSERT INTO payments (payment_id,claim_id,invoice_id,recipient_type,recipient_provider_id,payment_status,amount_cents,idempotency_key,created_at_utc,authorized_by) VALUES ('PAY-2026-000001','CLM-2026-000001','INV-PRV-PRV-000001-000001','PROVIDER','PRV-000001','AUTHORIZED',370000,'ID1','2026-01-07T08:00:00Z','USR')")
t("disburse full","UPDATE payments SET payment_status='DISBURSED', disbursed_amount_cents=370000, net_paid_cents=370000, disbursed_at_utc='2026-01-07T12:00:00Z', external_bank_tx_ref='ACH-1' WHERE payment_id='PAY-2026-000001'")
print("   post-disburse:", con.execute("SELECT claim_status, net_paid_cents FROM claims").fetchone(), con.execute("SELECT invoice_status FROM invoices").fetchone())

t("falsify claim net_paid_cents directly (tamper aggregate)","UPDATE claims SET net_paid_cents=1 WHERE claim_id='CLM-2026-000001'")
t("falsify invoice reserved directly","UPDATE invoices SET reserved_authorized_cents=1 WHERE invoice_id='INV-PRV-PRV-000001-000001'")

t("full clawback","UPDATE payments SET payment_status='REVERSED_CLAWBACK', clawed_back_cents=370000, net_paid_cents=0, reversed_at_utc='2026-01-12T16:45:00Z' WHERE payment_id='PAY-2026-000001'")
print("   post-clawback:", con.execute("SELECT claim_status, net_paid_cents, historical_approved_cents FROM claims").fetchone(), con.execute("SELECT invoice_status FROM invoices").fetchone())
t("revoke invoice","UPDATE invoices SET invoice_status='REVOKED_POST_APPROVAL', approved_cents=0 WHERE invoice_id='INV-PRV-PRV-000001-000001'")
print("   post-revoke claim:", con.execute("SELECT claim_status, approved_amount_cents, historical_approved_cents FROM claims").fetchone())
t("deny claim","UPDATE claims SET claim_status='DENIED' WHERE claim_id='CLM-2026-000001'")
print("   post-deny:", con.execute("SELECT claim_status, historical_approved_cents FROM claims").fetchone())

t("seed investigation","INSERT INTO investigations (investigation_id,primary_claim_id,subject_claimant_id,investigation_status,priority,assigned_investigator_id,opened_at_utc,updated_at_utc,estimated_exposure_cents,case_summary_notes) VALUES ('INVG-2026-000001','CLM-2026-000001','CLMT-000001','OPEN','P2_HIGH','I1','2026-01-07T09:00:00Z','2026-01-07T09:00:00Z',400000,'n')")
t("DELETE investigation (no block trigger?)","DELETE FROM investigations WHERE investigation_id='INVG-2026-000001'")
t("seed edge","INSERT INTO relationship_edges VALUES ('EDGE-2026-000001','SHARED_BANK_ACCOUNT','CLAIMANT','CLMT-000001',NULL,'CLAIMANT',NULL,'CLMT-000002','CLAIMANT:CLMT-000001','CLAIMANT:CLMT-000002',1.0,1,'2026-01-05T00:00:00Z','2026-01-05T00:00:00Z','CLM-2026-000001',1)")
t("silently flip edge is_active=0 (no trigger/audit)","UPDATE relationship_edges SET is_active=0, strength_weight=0.01 WHERE edge_id='EDGE-2026-000001'")
t("seed fraud_indicator","INSERT INTO fraud_indicators (indicator_id,claim_id,indicator_code,pillar,dedup_scope,canonical_evidence_token,severity,raw_points,max_points,normalized_value,feature_snapshot_json,computed_at_utc) VALUES ('FIND-2026-000001','CLM-2026-000001','IND-03','FINANCIAL','CLAIM','DUP_FP:x','CRITICAL',35.0,35.0,1.0,'{\"k\":1}','2026-01-05T00:00:00Z')")
t("silently raise raw_points beyond any cap (no trigger/audit)","UPDATE fraud_indicators SET raw_points=35.0 WHERE indicator_id='FIND-2026-000001'")

print("\nstate:", con.execute("SELECT claim_status FROM claims").fetchone())

export interface EntityContractRow {
  tier: string;
  tableName: string;
  entityName: string;
  seed42Count: number;
  idFormat: string;
  globPattern: string;
}

export const TEN_MANDATORY_AND_SUPPORT_ENTITIES: EntityContractRow[] = [
  { tier: 'Tier A (1)', tableName: 'claimants', entityName: 'Claimant', seed42Count: 2000, idFormat: 'CLMT-000001 .. CLMT-002000', globPattern: 'CLMT-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (2)', tableName: 'policies', entityName: 'Policy', seed42Count: 2200, idFormat: 'POL-2026-000001 .. POL-2026-002200', globPattern: 'POL-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (3)', tableName: 'incidents', entityName: 'Incident', seed42Count: 3800, idFormat: 'INC-2026-000001 .. INC-2026-003800', globPattern: 'INC-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (4)', tableName: 'claims', entityName: 'Claim', seed42Count: 5000, idFormat: 'CLM-2026-000001 .. CLM-2026-005000', globPattern: 'CLM-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (5)', tableName: 'providers', entityName: 'Provider', seed42Count: 500, idFormat: 'PRV-000001 .. PRV-000500', globPattern: 'PRV-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (6)', tableName: 'invoices', entityName: 'Invoice', seed42Count: 7500, idFormat: 'INV-PRV-<provider_id>-<6d_seq>', globPattern: "'INV-PRV-' || provider_id || '-[0-9][0-9][0-9][0-9][0-9][0-9]'" },
  { tier: 'Tier A (7)', tableName: 'payments', entityName: 'Payment', seed42Count: 4200, idFormat: 'PAY-2026-000001 .. PAY-2026-004200', globPattern: 'PAY-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (8)', tableName: 'relationship_edges', entityName: 'RelationshipEdge', seed42Count: 8000, idFormat: 'EDGE-2026-000001 .. EDGE-2026-008000', globPattern: 'EDGE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (9)', tableName: 'fraud_indicators', entityName: 'FraudIndicator', seed42Count: 4120, idFormat: 'FIND-2026-000001 .. FIND-2026-004120', globPattern: 'FIND-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier A (10)', tableName: 'investigations', entityName: 'Investigation', seed42Count: 45, idFormat: 'INVG-2026-000001 .. INVG-2026-000045', globPattern: 'INVG-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier B (11)', tableName: 'immutable_events', entityName: 'ImmutableEvent', seed42Count: 19495, idFormat: 'EVT-2026-0000001 .. EVT-2026-0019495', globPattern: 'EVT-2026-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]' },
  { tier: 'Tier B (12)', tableName: 'ingestion_exceptions', entityName: 'IngestionException', seed42Count: 25, idFormat: 'IEX-2026-000001 .. IEX-2026-000025', globPattern: 'IEX-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' },
];

export interface KavVector {
  id: string;
  sequenceNo: number;
  eventId: string;
  eventType: string;
  entityType: string;
  entityId: string;
  claimId: string | null;
  actorId: string;
  occurredAtUtc: string;
  payloadJson: string;
  payloadSha256: string;
  prevEventHash: string;
  expectedEventHash: string;
}

export const KAV_VECTORS: KavVector[] = [
  {
    id: 'KAV-1',
    sequenceNo: 1,
    eventId: 'EVT-2026-0000001',
    eventType: 'CLAIM_SUBMITTED',
    entityType: 'Claim',
    entityId: 'CLM-2026-000001',
    claimId: 'CLM-2026-000001',
    actorId: 'SYSTEM_SEED',
    occurredAtUtc: '2026-01-05T09:00:00Z',
    payloadJson: '{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}',
    payloadSha256: '45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3',
    prevEventHash: '0000000000000000000000000000000000000000000000000000000000000000',
    expectedEventHash: '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305',
  },
  {
    id: 'KAV-2',
    sequenceNo: 2,
    eventId: 'EVT-2026-0000002',
    eventType: 'INVOICE_SUBMITTED',
    entityType: 'Invoice',
    entityId: 'INV-PRV-PRV-000001-000001',
    claimId: 'CLM-2026-000001',
    actorId: 'SYSTEM_SEED',
    occurredAtUtc: '2026-01-05T10:15:00Z',
    payloadJson: '{"billed_cents":420000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"SUBMITTED","provider_id":"PRV-000001"}',
    payloadSha256: 'e9fe644e3853d49ee2134783b6d3321ba44eb5d34ccb53ee2d898a9ccb6cd60e',
    prevEventHash: '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305',
    expectedEventHash: 'e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e',
  },
  {
    id: 'KAV-3',
    sequenceNo: 3,
    eventId: 'EVT-2026-0000003',
    eventType: 'CLAIM_APPROVED',
    entityType: 'Claim',
    entityId: 'CLM-2026-000001',
    claimId: 'CLM-2026-000001',
    actorId: 'USR-ADJ-001',
    occurredAtUtc: '2026-01-06T14:20:00Z',
    payloadJson: '{"approved_amount_cents":370000,"claim_id":"CLM-2026-000001","claim_status":"APPROVED","historical_approved_cents":370000}',
    payloadSha256: '702bfd27038da09f50dd068a2413531612b0cf9c51f8454d75b8fb0e2ccdb172',
    prevEventHash: 'e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e',
    expectedEventHash: '9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686',
  },
  {
    id: 'KAV-4',
    sequenceNo: 4,
    eventId: 'EVT-2026-0000004',
    eventType: 'PAYMENT_AUTHORIZED',
    entityType: 'Payment',
    entityId: 'PAY-2026-000001',
    claimId: 'CLM-2026-000001',
    actorId: 'USR-FIN-001',
    occurredAtUtc: '2026-01-07T08:00:00Z',
    payloadJson: '{"amount_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}',
    payloadSha256: '42913a85d1e8fcaff502429d18df7b7b132bb7f92f11c9af0f65f2842d9d73ce',
    prevEventHash: '9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686',
    expectedEventHash: 'ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5',
  },
  {
    id: 'KAV-5',
    sequenceNo: 5,
    eventId: 'EVT-2026-0000005',
    eventType: 'PAYMENT_DISBURSED',
    entityType: 'Payment',
    entityId: 'PAY-2026-000001',
    claimId: 'CLM-2026-000001',
    actorId: 'USR-FIN-001',
    occurredAtUtc: '2026-01-07T12:00:00Z',
    payloadJson: '{"amount_cents":370000,"claim_id":"CLM-2026-000001","disbursed_amount_cents":370000,"external_bank_tx_ref":"ACH-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"DISBURSED"}',
    payloadSha256: '5663eee591086d12e4641cac76bf6f8ce82ae56eabd229045482ea1bc2958ee3',
    prevEventHash: 'ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5',
    expectedEventHash: '0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d',
  },
  {
    id: 'KAV-6',
    sequenceNo: 6,
    eventId: 'EVT-2026-0000006',
    eventType: 'PAYMENT_CLAWBACK_REVERSED',
    entityType: 'Payment',
    entityId: 'PAY-2026-000001',
    claimId: 'CLM-2026-000001',
    actorId: 'USR-SIU-001',
    occurredAtUtc: '2026-01-12T16:45:00Z',
    payloadJson: '{"claim_id":"CLM-2026-000001","clawed_back_cents":370000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}',
    payloadSha256: '8a79ad34c4312208ba53d45a78aab83286d449f4cdbed29282edf971a7cd7412',
    prevEventHash: '0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d',
    expectedEventHash: '00b7871a82451bd6e85ac1b85d58e41b8fa77f24071f557121e4586570b9b564',
  },
  {
    id: 'KAV-7 (Unicode + Pipe Injection)',
    sequenceNo: 2,
    eventId: 'EVT-2026-0000002',
    eventType: 'INGESTION_EXCEPTION_RECORDED',
    entityType: 'IngestionException',
    entityId: 'IEX-2026-000001',
    claimId: null,
    actorId: 'USR|Renée;東京',
    occurredAtUtc: '2026-01-05T09:01:00Z',
    payloadJson: '{"note":"Renée|東京|🔍;8:claim_id=S15:CLM-2026-000001;"}',
    payloadSha256: '551e1e170eb912f3d695924f3e62f2db7b1ca9c5ececd433cd42e80c8e03b07a',
    prevEventHash: '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305',
    expectedEventHash: 'c20f59e45969c8c8fef46fcab1bc2645b123aa695f00f7761c291b9a243e8dbe',
  },
];

export interface ScenarioSpecRow {
  code: string;
  category: 'YF-NEG' | 'BL' | 'BC';
  title: string;
  countOrMultiplier: string;
  ruleSummary: string;
  expectedOutcome: string;
}

export const SCENARIO_CATALOG: ScenarioSpecRow[] = [
  {
    code: 'YF-NEG-1',
    category: 'YF-NEG',
    title: 'Nonexistent Policy Reference',
    countOrMultiplier: '25 attempts',
    ruleSummary: 'Claim references POL-2026-990001..990025 absent from policies. Caught pre-insert and recorded in ingestion_exceptions + immutable_events (claim_id=NULL).',
    expectedOutcome: '0 rows in claims; 25 rows in ingestion_exceptions; 100% FK integrity.',
  },
  {
    code: 'YF-NEG-2',
    category: 'YF-NEG',
    title: 'Payment Exceeds Approved Amount',
    countOrMultiplier: '30 claims',
    ruleSummary: 'Direct AUTHORIZED insert above approved_cents or payout_cap_cents blocked by trg_payments_validate_ins; recorded as BLOCKED_OVERPAYMENT.',
    expectedOutcome: '0 cents disbursed; net_paid_cents unchanged; benign claims stay LOW (< 30.00).',
  },
  {
    code: 'YF-NEG-3',
    category: 'YF-NEG',
    title: 'Cross-Claimant Duplicate Invoice',
    countOrMultiplier: '25 fraud claims',
    ruleSummary: 'Same line_item_fingerprint across distinct claimants. Duplicate invoice set to REJECTED_DUPLICATE (approved_cents=0); both claims get has_cross_dup(c)=1.',
    expectedOutcome: 'IND-03 (35.0 pts) + hard_collusion_override=1 -> IEF >= 65.00 (HIGH/CRITICAL).',
  },
  {
    code: 'YF-NEG-4',
    category: 'YF-NEG',
    title: 'Planted Ground-Truth Edge Missing Operational Record',
    countOrMultiplier: '5 rings / 40 claims',
    ruleSummary: '25 collusive edges planted in ground_truth_missing_edges (ground_truth.db) and omitted from relationship_edges.',
    expectedOutcome: 'Zero reads from ground_truth.db; >= 32/40 (>= 80%) score >= 65.00.',
  },
  {
    code: 'YF-NEG-5',
    category: 'YF-NEG',
    title: 'Common Address Alone Not Proof of Fraud',
    countOrMultiplier: '80 claims',
    ruleSummary: 'Claimants share apartment address (SHARED_ADDRESS weight 0.40, IND-05 max 4.0 pts) with BC-1 active (m_1=0.35).',
    expectedOutcome: '100% score <= 12.00 (LOW); 0 false positives; address ablation delta = 0.',
  },
  {
    code: 'BL-1',
    category: 'BL',
    title: 'High-Volume Regional Trauma Hospital',
    countOrMultiplier: '84 claims',
    ruleSummary: 'In-network trauma center treats many emergency patients; BC-2 (m_2=0.30) suppresses IND-11 and dampens score.',
    expectedOutcome: 'IEF <= 18.00 (LOW for 100%).',
  },
  {
    code: 'BL-2',
    category: 'BL',
    title: 'Catastrophic Hailstorm / Flood Surge',
    countOrMultiplier: '84 claims',
    ruleSummary: 'Severe weather cluster in same 5-char geohash within 48h; BC-3 (m_3=0.25) suppresses IND-09 and dampens score.',
    expectedOutcome: 'IEF <= 18.00 (LOW for 100%).',
  },
  {
    code: 'BL-3',
    category: 'BL',
    title: 'Joint-Policy Household Co-Habitation',
    countOrMultiplier: '84 claims',
    ruleSummary: 'Two household family members share address/phone/bank with 0 provider links; BC-4 (m_4=0.20) suppresses IND-01.',
    expectedOutcome: 'IEF <= 15.00 (LOW for 100%).',
  },
  {
    code: 'BL-4',
    category: 'BL',
    title: 'Multi-Vehicle Freeway Pileup (Shared Incident)',
    countOrMultiplier: '84 claims',
    ruleSummary: 'Innocent driver shares incident (SAME_INCIDENT_PARTICIPANT) with a confirmed fraudster; BC-5 (m_5=0.25) & mixed-cluster safety.',
    expectedOutcome: 'IEF <= 15.00 (LOW for 100%); B_cluster = 0.00.',
  },
  {
    code: 'BL-5',
    category: 'BL',
    title: 'Rural Sole-Provider Township Monopoly',
    countOrMultiplier: '84 claims',
    ruleSummary: 'Sole licensed repair/towing provider in rural 5-char geohash; BC-2 (m_2=0.30) + BC-6 (m_6=0.75).',
    expectedOutcome: 'IEF <= 18.00 (LOW for 100%).',
  },
];

export interface IndicatorSpecRow {
  code: string;
  name: string;
  pillar: 'NETWORK' | 'FINANCIAL' | 'BEHAVIORAL' | 'DOCUMENT';
  scope: 'CLAIM' | 'ENTITY' | 'PAIR' | 'RING';
  maxPoints: number;
  formula: string;
  tokenFormat: string;
}

export const FIFTEEN_INDICATORS: IndicatorSpecRow[] = [
  { code: 'IND-01', name: 'SHARED_PAYOUT_ACCOUNT', pillar: 'NETWORK', scope: 'ENTITY', maxPoints: 35.0, formula: 'I(k_acct >= 2 & !BC-4) * min(35, 20 + 7.5*(k_acct - 2))', tokenFormat: 'BANK:<bank_account_hash>' },
  { code: 'IND-02', name: 'SHARED_TAX_OR_PHONE_IDENTITY', pillar: 'NETWORK', scope: 'PAIR', maxPoints: 25.0, formula: 'max(25*I_tax, I(k_phone >= 2 & !BC-4)*min(18, 8 + 5*(k_phone - 2)))', tokenFormat: 'TAX:<tax_id_hash> | PHONE:<phone_e164>' },
  { code: 'IND-03', name: 'CROSS_CLAIMANT_DUPLICATE_INVOICE', pillar: 'FINANCIAL', scope: 'CLAIM', maxPoints: 35.0, formula: '35.0 * has_cross_dup(c)', tokenFormat: 'DUP_FP:<line_item_fingerprint>' },
  { code: 'IND-04', name: 'INTRA_CLAIM_DUPLICATE_RESUBMISSION', pillar: 'FINANCIAL', scope: 'CLAIM', maxPoints: 8.0, formula: '8.0 * I(has_intra_dup(c) == 1 & has_cross_dup(c) == 0)', tokenFormat: 'INTRA_DUP:<claim_id>:<line_item_fingerprint>' },
  { code: 'IND-05', name: 'SHARED_ADDRESS_CLUSTER', pillar: 'NETWORK', scope: 'ENTITY', maxPoints: 4.0, formula: 'I(k_addr >= 2) * min(4.0, 1.5 + 0.5*(k_addr - 2))', tokenFormat: 'ADDR:<sha256_hex(address_norm)>' },
  { code: 'IND-06', name: 'PAGERANK_CENTRALITY_SPIKE', pillar: 'NETWORK', scope: 'CLAIM', maxPoints: 15.0, formula: 'I(PR_tilde(c) > 1.25) * min(15.0, 15.0*(PR_tilde(c) - 1.25)/2.75)', tokenFormat: 'PR:<claim_id>' },
  { code: 'IND-07', name: 'DENSE_COLLUSIVE_RING_MEMBERSHIP', pillar: 'NETWORK', scope: 'RING', maxPoints: 30.0, formula: 'I(|V_K| >= 3 & rho_K > 0.35) * min(30.0, 15.0 + 25.0*(rho_K - 0.35))', tokenFormat: 'RING_COMP:<sorted_csv(V_K)>' },
  { code: 'IND-08', name: 'UPCODING_BILLED_ZSCORE', pillar: 'FINANCIAL', scope: 'CLAIM', maxPoints: 20.0, formula: 'I(z_cpt > 2.0) * min(20.0, 8.0 + 6.0*(z_cpt - 2.0))', tokenFormat: 'UPCODE:<claim_id>:<cpt_or_line_code>' },
  { code: 'IND-09', name: 'EARLY_POLICY_INCEPTION_CLAIM', pillar: 'BEHAVIORAL', scope: 'CLAIM', maxPoints: 18.0, formula: 'I(0 <= delta_bind <= 14 & !BC-3) * min(18.0, 18.0*(15 - delta_bind)/15)', tokenFormat: 'INCEPT:<policy_id>:<claim_id>' },
  { code: 'IND-10', name: 'DELAYED_INCIDENT_REPORTING', pillar: 'BEHAVIORAL', scope: 'CLAIM', maxPoints: 12.0, formula: 'I(delta_rep > 72) * min(12.0, 4.0 + 8.0*(delta_rep - 72)/168)', tokenFormat: 'DELAY:<incident_id>:<claim_id>' },
  { code: 'IND-11', name: 'PROVIDER_CLAIMANT_REFERRAL_CONCENTRATION', pillar: 'BEHAVIORAL', scope: 'PAIR', maxPoints: 15.0, formula: 'I(N_p >= 5 & r_pair > 0.35 & !BC-2) * min(15.0, 15.0*(r_pair - 0.35)/0.45)', tokenFormat: 'CONC:<claimant_id>:<provider_id>' },
  { code: 'IND-12', name: 'UNBUNDLED_LINE_ITEM_SPLITTING', pillar: 'DOCUMENT', scope: 'CLAIM', maxPoints: 20.0, formula: 'I(k_split >= 3) * min(20.0, 10.0 + 5.0*(k_split - 3))', tokenFormat: 'SPLIT:<claim_id>:<provider_id>:<date>' },
  { code: 'IND-13', name: 'MISSING_POLICE_REPORT_HIGH_SEVERITY', pillar: 'DOCUMENT', scope: 'CLAIM', maxPoints: 15.0, formula: 'I(no_police_report & claimed >= 250000) * min(15.0, 9.0 + 6.0*(claimed - 250000)/250000)', tokenFormat: 'NOPR:<incident_id>:<claim_id>' },
  { code: 'IND-14', name: 'CLAIMANT_VELOCITY_BURST', pillar: 'BEHAVIORAL', scope: 'ENTITY', maxPoints: 16.0, formula: 'I(n_90d >= 2) * min(16.0, 8.0*(n_90d - 1))', tokenFormat: 'VEL:<claimant_id>' },
  { code: 'IND-15', name: 'WATCHLIST_OR_SUSPENDED_PROVIDER', pillar: 'DOCUMENT', scope: 'ENTITY', maxPoints: 15.0, formula: '15.0*I(SUSPENDED) + 10.0*I(WATCHLIST)', tokenFormat: 'PRV_TIER:<provider_id>' },
];

export interface AcceptanceTestRow {
  testId: string;
  criticalRef: string;
  scope: string;
  sqliteAssertion: string;
  status: string;
}

export const ACCEPTANCE_TESTS_T21_T28: AcceptanceTestRow[] = [
  {
    testId: 'T-21',
    criticalRef: 'CRITICAL 1',
    scope: 'Invoice Approval Immutability & Authorized Adjustment Cap Enforcement',
    sqliteAssertion: 'Rejects direct/same-status UPDATE of approved_cents or historical_approved_cents without latest INVOICE_APPROVAL_ADJUSTED event; re-verifies claim/policy/deductible caps and ACTIVE policy on every approval or adjustment.',
    status: 'SPECIFIED — NOT YET EXECUTED (SQLite 3.40.1 Trigger Verified)',
  },
  {
    testId: 'T-22',
    criticalRef: 'CRITICAL 2',
    scope: 'Direct Invoice FSM Financial Consistency',
    sqliteAssertion: 'PAID requires net_paid_cents = approved_cents and reserved_authorized_cents = 0; PARTIALLY_PAID requires 0 < net_paid_cents < approved_cents; rejects direct status updates violating financial balances.',
    status: 'SPECIFIED — NOT YET EXECUTED (SQLite 3.40.1 Trigger Verified)',
  },
  {
    testId: 'T-23',
    criticalRef: 'CRITICAL 2',
    scope: 'Direct Claim FSM Financial Consistency & Trigger Cascade',
    sqliteAssertion: 'Enforces exact status-to-balance invariants on claims and verifies atomic cascade across APPROVED <-> PARTIALLY_PAID <-> PAID <-> SIU_HOLD <-> DENIED.',
    status: 'SPECIFIED — NOT YET EXECUTED (SQLite 3.40.1 Trigger Verified)',
  },
  {
    testId: 'T-24',
    criticalRef: 'CRITICAL 3',
    scope: 'Payment Immutable Fields & Post-Disbursement Audit Protection',
    sqliteAssertion: 'Blocks direct INSERT of DISBURSED; protects idempotency_key, created_at_utc, authorized_by, block_reason_code across all updates; locks external_bank_tx_ref and disbursed_at_utc post-disbursement.',
    status: 'SPECIFIED — NOT YET EXECUTED (SQLite 3.40.1 Trigger Verified)',
  },
  {
    testId: 'T-25',
    criticalRef: 'CRITICAL 4',
    scope: 'ST-EVT-V2 Length-Prefixed Event Serialization & KAV-1..7 Verification',
    sqliteAssertion: 'Validates UTF-8 byte-length prefixed ST-EVT-V2 hashes on KAV-1..KAV-7, multi-byte Unicode (Renée|東京|🔍), NULL claim_id, and all 64 hex chars via NOT GLOB *[^0-9a-f]*.',
    status: 'SPECIFIED — NOT YET EXECUTED (SQLite 3.40.1 CHECK Verified)',
  },
  {
    testId: 'T-26',
    criticalRef: 'CRITICAL 6',
    scope: 'Deterministic sqlite_master Schema Digest (ST-SCHEMA-V1)',
    sqliteAssertion: 'Computes ST-SCHEMA-V1 SHA-256 over ORDER BY type ASC, name ASC, tbl_name ASC; produces identical 64-hex digest regardless of table creation order.',
    status: 'SPECIFIED — NOT YET EXECUTED (SQLite 3.40.1 Verified)',
  },
  {
    testId: 'T-27',
    criticalRef: 'CRITICAL 7',
    scope: 'Historical Financial Accounting Protection (historical_approved_cents)',
    sqliteAssertion: 'Preserves historical_approved_cents across partial/full clawbacks, REVOKED_POST_APPROVAL, and DENIED; blocks direct SQL reduction via ERR_INVOICE/CLAIM_HISTORICAL_APPROVED_DECREASE_FORBIDDEN.',
    status: 'SPECIFIED — NOT YET EXECUTED (SQLite 3.40.1 Trigger Verified)',
  },
  {
    testId: 'T-28',
    criticalRef: 'CRITICAL 8',
    scope: 'Clean-Room 8-Node / 4-Claim End-to-End Verification',
    sqliteAssertion: 'Verifies 8x8 W, M, PageRank convergence at iteration 78 (err=9.740e-10), PR_tilde=[1.054745, 1.058274, 1.170781, 0.716200], and final IEF=[65.00, 65.00, 0.00, 0.67].',
    status: 'SPECIFIED — NOT YET EXECUTED (Standalone Math Verified)',
  },
];

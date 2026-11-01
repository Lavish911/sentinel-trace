PRAGMA foreign_keys = ON;
PRAGMA trusted_schema = ON;
PRAGMA recursive_triggers = ON;

-- 1. CLAIMANTS (2,000 rows)
CREATE TABLE claimants (
    claimant_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    dob_iso TEXT NOT NULL,
    tax_id_hash TEXT NOT NULL UNIQUE,
    phone_e164 TEXT NOT NULL,
    email_norm TEXT NOT NULL,
    address_norm TEXT NOT NULL,
    bank_routing_hash TEXT NOT NULL,
    bank_account_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    CHECK (claimant_id GLOB 'CLMT-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (dob_iso GLOB '[1-2][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    CHECK (length(tax_id_hash) = 64 AND tax_id_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (phone_e164 GLOB '+1[2-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (length(bank_routing_hash) = 64 AND bank_routing_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(bank_account_hash) = 64 AND bank_account_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (created_at_utc GLOB '202[0-6]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z')
) STRICT;

-- 2. POLICIES (2,200 rows)
CREATE TABLE policies (
    policy_id TEXT PRIMARY KEY,
    claimant_id TEXT NOT NULL REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    policy_number TEXT NOT NULL UNIQUE,
    line_of_business TEXT NOT NULL,
    policy_status TEXT NOT NULL,
    effective_start_utc TEXT NOT NULL,
    effective_end_utc TEXT NOT NULL,
    bound_at_utc TEXT NOT NULL,
    coverage_limit_cents INTEGER NOT NULL,
    deductible_cents INTEGER NOT NULL,
    annual_premium_cents INTEGER NOT NULL,
    CHECK (policy_id GLOB 'POL-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (line_of_business IN ('AUTO','PROPERTY','WORKERS_COMP','COMMERCIAL_GENERAL','MEDICAL')),
    CHECK (policy_status IN ('ACTIVE','LAPSED','CANCELLED','EXPIRED')),
    CHECK (effective_end_utc > effective_start_utc),
    CHECK (coverage_limit_cents > 0),
    CHECK (deductible_cents >= 0 AND deductible_cents < coverage_limit_cents),
    CHECK (annual_premium_cents > 0)
) STRICT;

-- 3. INCIDENTS (3,800 rows)
CREATE TABLE incidents (
    incident_id TEXT PRIMARY KEY,
    incident_timestamp_utc TEXT NOT NULL,
    reported_timestamp_utc TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    jurisdiction_state TEXT NOT NULL,
    location_address_norm TEXT NOT NULL,
    location_geohash TEXT NOT NULL,
    police_report_number TEXT,
    weather_condition TEXT NOT NULL,
    description TEXT NOT NULL,
    CHECK (incident_id GLOB 'INC-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (reported_timestamp_utc >= incident_timestamp_utc),
    CHECK (incident_type IN ('AUTO_COLLISION','WATER_DAMAGE','FIRE_LOSS','SLIP_AND_FALL','WORKPLACE_INJURY','THEFT_BURGLARY')),
    CHECK (length(jurisdiction_state) = 2 AND jurisdiction_state GLOB '[A-Z][A-Z]'),
    CHECK (length(location_geohash) BETWEEN 6 AND 12),
    CHECK (weather_condition IN ('CLEAR','RAIN','SNOW_ICE','FOG','STORM'))
) STRICT;

-- 4. CLAIMS (5,000 rows)
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL REFERENCES policies(policy_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    claimant_id TEXT NOT NULL REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    claim_status TEXT NOT NULL,
    submitted_at_utc TEXT NOT NULL,
    claimed_amount_cents INTEGER NOT NULL,
    approved_amount_cents INTEGER NOT NULL DEFAULT 0,
    historical_approved_cents INTEGER NOT NULL DEFAULT 0,
    reserved_authorized_cents INTEGER NOT NULL DEFAULT 0,
    gross_disbursed_cents INTEGER NOT NULL DEFAULT 0,
    clawed_back_cents INTEGER NOT NULL DEFAULT 0,
    net_paid_cents INTEGER NOT NULL DEFAULT 0,
    payout_cap_cents INTEGER NOT NULL,
    adjustor_id TEXT NOT NULL,
    siu_referred INTEGER NOT NULL DEFAULT 0,
    latest_ief_score REAL NOT NULL DEFAULT 0.0,
    latest_risk_tier TEXT NOT NULL DEFAULT 'LOW',
    scoring_evidence_sha256 TEXT,
    CHECK (claim_id GLOB 'CLM-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (claim_status IN ('SUBMITTED','UNDER_REVIEW','APPROVED','PARTIALLY_PAID','PAID','SIU_HOLD','DENIED','CLOSED_NO_PAY')),
    CHECK (claimed_amount_cents > 0),
    CHECK (approved_amount_cents >= 0 AND approved_amount_cents <= claimed_amount_cents),
    CHECK (historical_approved_cents >= approved_amount_cents),
    CHECK (reserved_authorized_cents >= 0),
    CHECK (gross_disbursed_cents >= 0),
    CHECK (clawed_back_cents >= 0 AND clawed_back_cents <= gross_disbursed_cents),
    CHECK (net_paid_cents = gross_disbursed_cents - clawed_back_cents),
    CHECK (reserved_authorized_cents + net_paid_cents <= historical_approved_cents),
    CHECK (payout_cap_cents >= 0),
    CHECK (approved_amount_cents <= payout_cap_cents),
    CHECK (siu_referred IN (0, 1)),
    CHECK (scoring_evidence_sha256 IS NULL OR (length(scoring_evidence_sha256) = 64 AND scoring_evidence_sha256 NOT GLOB '*[^0-9a-f]*')),
    CHECK (latest_ief_score >= 0.0 AND latest_ief_score <= 100.0),
    CHECK (latest_risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL'))
) STRICT;

-- 5. PROVIDERS (500 rows)
CREATE TABLE providers (
    provider_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    npi_or_license_id TEXT NOT NULL UNIQUE,
    tax_id_hash TEXT NOT NULL,
    phone_e164 TEXT NOT NULL,
    address_norm TEXT NOT NULL,
    bank_routing_hash TEXT NOT NULL,
    bank_account_hash TEXT NOT NULL,
    network_tier TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    CHECK (provider_id GLOB 'PRV-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (provider_type IN ('AUTO_BODY','MEDICAL_CLINIC','CHIROPRACTIC','RESTORATION_CONTRACTOR','LEGAL_REPRESENTATIVE','TOWING_STORAGE','DIAGNOSTIC_IMAGING')),
    CHECK (network_tier IN ('IN_NETWORK','OUT_OF_NETWORK','WATCHLIST','SUSPENDED')),
    CHECK (length(tax_id_hash) = 64 AND tax_id_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (phone_e164 GLOB '+1[2-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (length(bank_routing_hash) = 64 AND bank_routing_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(bank_account_hash) = 64 AND bank_account_hash NOT GLOB '*[^0-9a-f]*')
) STRICT;

-- 6. INVOICES (7,500 rows)
CREATE TABLE invoices (
    invoice_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_invoice_number TEXT NOT NULL,
    invoice_status TEXT NOT NULL,
    service_start_utc TEXT NOT NULL,
    service_end_utc TEXT NOT NULL,
    submitted_at_utc TEXT NOT NULL,
    cpt_or_line_code TEXT NOT NULL,
    line_item_fingerprint TEXT NOT NULL,
    billed_cents INTEGER NOT NULL,
    approved_cents INTEGER NOT NULL DEFAULT 0,
    historical_approved_cents INTEGER NOT NULL DEFAULT 0,
    reserved_authorized_cents INTEGER NOT NULL DEFAULT 0,
    gross_disbursed_cents INTEGER NOT NULL DEFAULT 0,
    clawed_back_cents INTEGER NOT NULL DEFAULT 0,
    net_paid_cents INTEGER NOT NULL DEFAULT 0,
    duplicate_of_invoice_id TEXT REFERENCES invoices(invoice_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CHECK (invoice_id GLOB 'INV-PRV-' || provider_id || '-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (length(invoice_id) = 25),
    CHECK (invoice_status IN ('SUBMITTED','UNDER_REVIEW','APPROVED','PARTIALLY_PAID','PAID','REJECTED_DUPLICATE','REJECTED_ELIGIBILITY','REVOKED_POST_APPROVAL')),
    CHECK (service_end_utc >= service_start_utc),
    CHECK (submitted_at_utc >= service_start_utc),
    CHECK (length(line_item_fingerprint) = 64 AND line_item_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK (billed_cents > 0),
    CHECK (approved_cents >= 0 AND approved_cents <= billed_cents),
    CHECK (historical_approved_cents >= approved_cents AND historical_approved_cents <= billed_cents),
    CHECK (reserved_authorized_cents >= 0),
    CHECK (gross_disbursed_cents >= 0),
    CHECK (clawed_back_cents >= 0 AND clawed_back_cents <= gross_disbursed_cents),
    CHECK (net_paid_cents = gross_disbursed_cents - clawed_back_cents),
    CHECK (reserved_authorized_cents + net_paid_cents <= historical_approved_cents),
    CHECK (
        (invoice_status = 'REJECTED_DUPLICATE' AND duplicate_of_invoice_id IS NOT NULL AND duplicate_of_invoice_id != invoice_id AND approved_cents = 0)
        OR (invoice_status != 'REJECTED_DUPLICATE' AND duplicate_of_invoice_id IS NULL)
    )
) STRICT;

-- 7. PAYMENTS (4,200 rows)
CREATE TABLE payments (
    payment_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    recipient_type TEXT NOT NULL,
    recipient_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    recipient_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    payment_status TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    disbursed_amount_cents INTEGER NOT NULL DEFAULT 0,
    clawed_back_cents INTEGER NOT NULL DEFAULT 0,
    net_paid_cents INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL,
    disbursed_at_utc TEXT,
    reversed_at_utc TEXT,
    authorized_by TEXT NOT NULL,
    block_reason_code TEXT,
    external_bank_tx_ref TEXT,
    cancel_reason TEXT,
    CHECK (payment_id GLOB 'PAY-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (
        (recipient_type = 'CLAIMANT' AND recipient_claimant_id IS NOT NULL AND recipient_provider_id IS NULL)
        OR (recipient_type = 'PROVIDER' AND recipient_provider_id IS NOT NULL AND recipient_claimant_id IS NULL)
    ),
    CHECK (payment_status IN ('AUTHORIZED','DISBURSED','BLOCKED_OVERPAYMENT','BLOCKED_UNAPPROVED','BLOCKED_INVALID_RECIPIENT','REVERSED_CLAWBACK','CANCELLED')),
    CHECK (amount_cents > 0),
    CHECK (
        (payment_status = 'DISBURSED' AND disbursed_amount_cents = amount_cents AND clawed_back_cents = 0 AND net_paid_cents = amount_cents AND disbursed_at_utc IS NOT NULL AND external_bank_tx_ref IS NOT NULL AND length(external_bank_tx_ref) >= 4 AND reversed_at_utc IS NULL AND block_reason_code IS NULL AND cancel_reason IS NULL)
        OR (payment_status = 'REVERSED_CLAWBACK' AND disbursed_amount_cents = amount_cents AND clawed_back_cents > 0 AND clawed_back_cents <= disbursed_amount_cents AND net_paid_cents = disbursed_amount_cents - clawed_back_cents AND disbursed_at_utc IS NOT NULL AND external_bank_tx_ref IS NOT NULL AND reversed_at_utc IS NOT NULL AND block_reason_code IS NULL AND cancel_reason IS NULL)
        OR (payment_status = 'AUTHORIZED' AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NULL AND block_reason_code IS NULL AND cancel_reason IS NULL)
        OR (payment_status = 'CANCELLED' AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NOT NULL AND block_reason_code IS NULL AND cancel_reason IS NOT NULL)
        OR (payment_status IN ('BLOCKED_OVERPAYMENT','BLOCKED_UNAPPROVED','BLOCKED_INVALID_RECIPIENT') AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NULL AND block_reason_code IS NOT NULL AND cancel_reason IS NULL)
    ),
    CHECK (cancel_reason IS NULL OR cancel_reason IN ('SIU_HOLD_RESERVATION_CLEARED','FINANCE_WITHDRAWAL','SUBSEQUENT_ADJUSTMENT'))
) STRICT;

-- 8. RELATIONSHIP_EDGES (8,000 rows)
CREATE TABLE relationship_edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    source_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    target_entity_type TEXT NOT NULL,
    target_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    target_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    canonical_src_key TEXT NOT NULL,
    canonical_dst_key TEXT NOT NULL,
    strength_weight REAL NOT NULL,
    evidence_count INTEGER NOT NULL,
    first_observed_utc TEXT NOT NULL,
    last_observed_utc TEXT NOT NULL,
    supporting_claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    is_active INTEGER NOT NULL DEFAULT 1,
    CHECK (edge_id GLOB 'EDGE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (edge_type IN ('SHARED_ADDRESS','SHARED_PHONE','SHARED_BANK_ACCOUNT','SHARED_TAX_ID','SAME_INCIDENT_PARTICIPANT','CLAIMANT_TREATED_BY_PROVIDER','PROVIDER_REFERRAL_LINK','CROSS_CLAIM_DUPLICATE_INVOICE')),
    CHECK (
        (source_entity_type = 'CLAIMANT' AND source_claimant_id IS NOT NULL AND source_provider_id IS NULL AND canonical_src_key = 'CLAIMANT:' || source_claimant_id)
        OR (source_entity_type = 'PROVIDER' AND source_provider_id IS NOT NULL AND source_claimant_id IS NULL AND canonical_src_key = 'PROVIDER:' || source_provider_id)
    ),
    CHECK (
        (target_entity_type = 'CLAIMANT' AND target_claimant_id IS NOT NULL AND target_provider_id IS NULL AND canonical_dst_key = 'CLAIMANT:' || target_claimant_id)
        OR (target_entity_type = 'PROVIDER' AND target_provider_id IS NOT NULL AND target_claimant_id IS NULL AND canonical_dst_key = 'PROVIDER:' || target_provider_id)
    ),
    CHECK (canonical_src_key < canonical_dst_key),
    CHECK (strength_weight > 0.0 AND strength_weight <= 1.0),
    CHECK (evidence_count >= 1),
    CHECK (last_observed_utc >= first_observed_utc),
    CHECK (is_active IN (0, 1)),
    UNIQUE (edge_type, canonical_src_key, canonical_dst_key)
) STRICT;

-- 9. FRAUD_INDICATORS (4,120 rows)
CREATE TABLE fraud_indicators (
    indicator_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    indicator_code TEXT NOT NULL,
    pillar TEXT NOT NULL,
    dedup_scope TEXT NOT NULL,
    canonical_evidence_token TEXT NOT NULL,
    severity TEXT NOT NULL,
    raw_points REAL NOT NULL,
    max_points REAL NOT NULL,
    normalized_value REAL NOT NULL,
    feature_snapshot_json TEXT NOT NULL,
    computed_at_utc TEXT NOT NULL,
    CHECK (indicator_id GLOB 'FIND-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (indicator_code IN ('IND-01','IND-02','IND-03','IND-04','IND-05','IND-06','IND-07','IND-08','IND-09','IND-10','IND-11','IND-12','IND-13','IND-14','IND-15')),
    CHECK (pillar IN ('NETWORK','FINANCIAL','BEHAVIORAL','DOCUMENT')),
    CHECK (dedup_scope IN ('CLAIM','ENTITY','PAIR','RING')),
    CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CHECK (raw_points > 0.0 AND raw_points <= max_points),
    CHECK (max_points > 0.0 AND max_points <= 40.0),
    CHECK (normalized_value >= 0.0 AND normalized_value <= 1.0),
    CHECK (is_canonical_json(feature_snapshot_json) = 1),
    UNIQUE (claim_id, indicator_code, canonical_evidence_token)
) STRICT;

-- 10. INVESTIGATIONS (45 rows)
CREATE TABLE investigations (
    investigation_id TEXT PRIMARY KEY,
    primary_claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    subject_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    subject_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    investigation_status TEXT NOT NULL,
    priority TEXT NOT NULL,
    assigned_investigator_id TEXT NOT NULL,
    opened_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    closed_at_utc TEXT,
    ruling_outcome TEXT,
    estimated_exposure_cents INTEGER NOT NULL,
    recovered_clawback_cents INTEGER NOT NULL DEFAULT 0,
    case_summary_notes TEXT NOT NULL,
    CHECK (investigation_id GLOB 'INVG-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (subject_claimant_id IS NOT NULL OR subject_provider_id IS NOT NULL),
    CHECK (investigation_status IN ('OPEN','EVIDENCE_COLLECTION','SIU_FIELD_REVIEW','LEGAL_ESCALATION','CLOSED_CONFIRMED_FRAUD','CLOSED_CLEARED_BENIGN','CLOSED_INSUFFICIENT_EVIDENCE')),
    CHECK (priority IN ('P1_CRITICAL','P2_HIGH','P3_STANDARD')),
    CHECK (updated_at_utc >= opened_at_utc),
    CHECK (estimated_exposure_cents >= 0),
    CHECK (recovered_clawback_cents >= 0),
    CHECK (
        (investigation_status LIKE 'CLOSED_%' AND closed_at_utc IS NOT NULL AND closed_at_utc >= opened_at_utc AND ruling_outcome IN ('CONFIRMED_FRAUD','CLEARED_BENIGN','INSUFFICIENT_EVIDENCE'))
        OR (investigation_status NOT LIKE 'CLOSED_%' AND closed_at_utc IS NULL AND ruling_outcome IS NULL)
    )
) STRICT;

-- 11. IMMUTABLE_EVENTS (19,615 rows — Length-Prefixed ST-EVT-V2 Chain)
CREATE TABLE immutable_events (
    sequence_no INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    claim_id TEXT REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    actor_id TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    prev_event_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    CHECK (sequence_no >= 1),
    CHECK (event_id GLOB 'EVT-2026-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (event_type IN ('INGESTION_EXCEPTION_RECORDED','CLAIM_SUBMITTED','INVOICE_SUBMITTED','INVOICE_APPROVED','INVOICE_APPROVAL_ADJUSTED','CLAIM_APPROVED','PAYMENT_AUTHORIZED','PAYMENT_CANCELLED','PAYMENT_BLOCKED','PAYMENT_DISBURSED','PAYMENT_CLAWBACK_REVERSED','CLAIM_SIU_HOLD_PLACED','CLAIM_DENIED','RELATIONSHIP_EDGE_DEACTIVATED','INVESTIGATION_OPENED','INVESTIGATION_STATUS_CHANGED','INVESTIGATION_CLOSED')),
    CHECK (entity_type IN ('Claimant','Policy','Incident','Claim','Provider','Invoice','Payment','RelationshipEdge','FraudIndicator','Investigation','IngestionException')),
    CHECK (is_canonical_json(payload_json) = 1),
    CHECK (length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(prev_event_hash) = 64 AND prev_event_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(event_hash) = 64 AND event_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (payload_sha256 = sha256_hex(payload_json)),
    CHECK (
        event_hash = sha256_hex(
            'ST-EVT-V2|'
            || '11:sequence_no=I' || CAST(sequence_no AS TEXT) || ';'
            || '8:event_id=S' || CAST(length(CAST(event_id AS BLOB)) AS TEXT) || ':' || event_id || ';'
            || '10:event_type=S' || CAST(length(CAST(event_type AS BLOB)) AS TEXT) || ':' || event_type || ';'
            || '11:entity_type=S' || CAST(length(CAST(entity_type AS BLOB)) AS TEXT) || ':' || entity_type || ';'
            || '9:entity_id=S' || CAST(length(CAST(entity_id AS BLOB)) AS TEXT) || ':' || entity_id || ';'
            || CASE
                WHEN claim_id IS NULL THEN '8:claim_id=N;'
                ELSE '8:claim_id=S' || CAST(length(CAST(claim_id AS BLOB)) AS TEXT) || ':' || claim_id || ';'
               END
            || '8:actor_id=S' || CAST(length(CAST(actor_id AS BLOB)) AS TEXT) || ':' || actor_id || ';'
            || '15:occurred_at_utc=S' || CAST(length(CAST(occurred_at_utc AS BLOB)) AS TEXT) || ':' || occurred_at_utc || ';'
            || '14:payload_sha256=S' || CAST(length(CAST(payload_sha256 AS BLOB)) AS TEXT) || ':' || payload_sha256 || ';'
            || '15:prev_event_hash=S' || CAST(length(CAST(prev_event_hash AS BLOB)) AS TEXT) || ':' || prev_event_hash || ';'
        )
    )
) STRICT;

-- 12. INGESTION_EXCEPTIONS (25 rows — YF-NEG-1 Nonexistent Policy References)
CREATE TABLE ingestion_exceptions (
    exception_id TEXT PRIMARY KEY,
    attempted_claim_id TEXT NOT NULL UNIQUE,
    rejected_policy_id TEXT NOT NULL,
    claimant_id TEXT NOT NULL REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    attempted_claimed_cents INTEGER NOT NULL,
    exception_code TEXT NOT NULL,
    raw_payload_json TEXT NOT NULL,
    detected_at_utc TEXT NOT NULL,
    immutable_event_id TEXT NOT NULL REFERENCES immutable_events(event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CHECK (exception_id GLOB 'IEX-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (attempted_claim_id GLOB 'CLM-2026-99[0-9][0-9][0-9][0-9]'),
    CHECK (rejected_policy_id GLOB 'POL-2026-99[0-9][0-9][0-9][0-9]'),
    CHECK (attempted_claimed_cents > 0),
    CHECK (exception_code = 'ERR_NONEXISTENT_POLICY_REFERENCE'),
    CHECK (is_canonical_json(raw_payload_json) = 1)
) STRICT;

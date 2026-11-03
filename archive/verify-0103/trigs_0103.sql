-- 1. Immutable Events Hash-Chain Triggers
CREATE TRIGGER trg_events_chain_insert
BEFORE INSERT ON immutable_events
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN (SELECT COUNT(*) FROM immutable_events) = 0 AND NEW.sequence_no != 1
            THEN RAISE(ABORT, 'ERR_GENESIS_SEQ_MUST_BE_1')
        WHEN (SELECT COUNT(*) FROM immutable_events) = 0 AND NEW.prev_event_hash != '0000000000000000000000000000000000000000000000000000000000000000'
            THEN RAISE(ABORT, 'ERR_GENESIS_PREV_HASH_MUST_BE_ZEROS')
        WHEN (SELECT COUNT(*) FROM immutable_events) > 0 AND NEW.sequence_no != (SELECT MAX(sequence_no) + 1 FROM immutable_events)
            THEN RAISE(ABORT, 'ERR_NON_MONOTONIC_SEQUENCE_NO')
        WHEN (SELECT COUNT(*) FROM immutable_events) > 0 AND NEW.prev_event_hash != (SELECT event_hash FROM immutable_events WHERE sequence_no = NEW.sequence_no - 1)
            THEN RAISE(ABORT, 'ERR_BROKEN_HASH_CHAIN_LINK')
        WHEN EXISTS (SELECT 1 FROM json_tree(NEW.payload_json) WHERE type = 'real')
            THEN RAISE(ABORT, 'ERR_EVENT_PAYLOAD_FLOAT_FORBIDDEN')
    END;
END;

CREATE TRIGGER trg_events_block_update
BEFORE UPDATE ON immutable_events
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_IMMUTABLE_EVENT_UPDATE_FORBIDDEN');
END;

CREATE TRIGGER trg_events_block_delete
BEFORE DELETE ON immutable_events
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_IMMUTABLE_EVENT_DELETE_FORBIDDEN');
END;

-- 2. Claims Validation, Financial Consistency & FSM Triggers
--     [ARCH-ST-010.3 / D-1 / NEW-5] trg_claims_fsm_upd now also requires an investigation
--     closed as 'CLOSED_CLEARED_BENIGN' (same claim) for benign SIU_HOLD exits.
CREATE TRIGGER trg_claims_validate_ins
BEFORE INSERT ON claims
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.claim_status != 'SUBMITTED'
            THEN RAISE(ABORT, 'ERR_CLAIM_INITIAL_STATUS_MUST_BE_SUBMITTED')
        WHEN NEW.approved_amount_cents != 0 OR NEW.historical_approved_cents != 0
             OR NEW.reserved_authorized_cents != 0 OR NEW.gross_disbursed_cents != 0
             OR NEW.clawed_back_cents != 0 OR NEW.net_paid_cents != 0
            THEN RAISE(ABORT, 'ERR_CLAIM_INITIAL_BALANCES_MUST_BE_ZERO')
        WHEN NEW.siu_referred != 0
            THEN RAISE(ABORT, 'ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO')
        WHEN NEW.latest_ief_score != 0.0 OR NEW.latest_risk_tier != 'LOW' OR NEW.scoring_evidence_sha256 IS NOT NULL
            THEN RAISE(ABORT, 'ERR_CLAIM_INITIAL_SCORE_STATE_INVALID')
        WHEN NEW.claimant_id != (SELECT claimant_id FROM policies WHERE policy_id = NEW.policy_id)
            THEN RAISE(ABORT, 'ERR_CLAIM_POLICY_CLAIMANT_MISMATCH')
        WHEN NEW.payout_cap_cents != MIN(
            NEW.claimed_amount_cents,
            MAX(0, (SELECT coverage_limit_cents - deductible_cents FROM policies WHERE policy_id = NEW.policy_id))
        )
            THEN RAISE(ABORT, 'ERR_CLAIM_PAYOUT_CAP_FORMULA_MISMATCH')
    END;
END;

CREATE TRIGGER trg_claims_fsm_upd
BEFORE UPDATE ON claims
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.claim_id != OLD.claim_id OR NEW.policy_id != OLD.policy_id
             OR NEW.claimant_id != OLD.claimant_id OR NEW.incident_id != OLD.incident_id
             OR NEW.claimed_amount_cents != OLD.claimed_amount_cents
             OR NEW.payout_cap_cents != OLD.payout_cap_cents
             OR NEW.submitted_at_utc != OLD.submitted_at_utc
            THEN RAISE(ABORT, 'ERR_CLAIM_IMMUTABLE_CORE_FIELDS')
        WHEN NEW.siu_referred < OLD.siu_referred
            THEN RAISE(ABORT, 'ERR_CLAIM_SIU_REFERRED_IRREVERSIBLE')
        WHEN NEW.siu_referred > OLD.siu_referred
             AND NEW.claim_status != 'SIU_HOLD'
             AND NOT EXISTS (
                 SELECT 1 FROM investigations
                 WHERE primary_claim_id = NEW.claim_id
                   AND investigation_status = 'CLOSED_CONFIRMED_FRAUD'
             )
            THEN RAISE(ABORT, 'ERR_CLAIM_SIU_REFERRAL_REQUIRES_HOLD_OR_CONFIRMED_FRAUD')
        WHEN NEW.historical_approved_cents < OLD.historical_approved_cents
            THEN RAISE(ABORT, 'ERR_CLAIM_HISTORICAL_APPROVED_DECREASE_FORBIDDEN')
        WHEN NEW.approved_amount_cents != COALESCE((
            SELECT SUM(approved_cents) FROM invoices
            WHERE claim_id = NEW.claim_id AND invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
        ), 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_APPROVED_AGGREGATE_TAMPERING')
        WHEN NEW.historical_approved_cents != COALESCE((
            SELECT SUM(historical_approved_cents) FROM invoices
            WHERE claim_id = NEW.claim_id
        ), 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_HISTORICAL_AGGREGATE_TAMPERING')
        WHEN NEW.reserved_authorized_cents != COALESCE((
            SELECT SUM(amount_cents) FROM payments
            WHERE claim_id = NEW.claim_id AND payment_status = 'AUTHORIZED'
        ), 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_RESERVED_AGGREGATE_TAMPERING')
        WHEN NEW.gross_disbursed_cents != COALESCE((
            SELECT SUM(disbursed_amount_cents) FROM payments
            WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
        ), 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_GROSS_DISBURSED_AGGREGATE_TAMPERING')
        WHEN NEW.clawed_back_cents != COALESCE((
            SELECT SUM(clawed_back_cents) FROM payments
            WHERE claim_id = NEW.claim_id AND payment_status = 'REVERSED_CLAWBACK'
        ), 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_CLAWBACK_AGGREGATE_TAMPERING')
        WHEN NEW.net_paid_cents != COALESCE((
            SELECT SUM(net_paid_cents) FROM payments
            WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
        ), 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_NET_PAID_AGGREGATE_TAMPERING')
        WHEN NEW.claim_status IN ('SUBMITTED','UNDER_REVIEW')
             AND (NEW.approved_amount_cents != 0 OR NEW.historical_approved_cents != 0
                  OR NEW.reserved_authorized_cents != 0 OR NEW.gross_disbursed_cents != 0
                  OR NEW.clawed_back_cents != 0 OR NEW.net_paid_cents != 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_PRE_APPROVAL_NONZERO_BALANCE')
        WHEN NEW.claim_status = 'APPROVED'
             AND NOT (NEW.approved_amount_cents > 0 AND NEW.net_paid_cents = 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH')
        WHEN NEW.claim_status = 'PARTIALLY_PAID'
             AND NOT (NEW.approved_amount_cents > 0 AND NEW.net_paid_cents > 0 AND NEW.net_paid_cents < NEW.approved_amount_cents)
            THEN RAISE(ABORT, 'ERR_CLAIM_PARTIALLY_PAID_FINANCIAL_MISMATCH')
        WHEN NEW.claim_status = 'PAID'
             AND NOT (NEW.approved_amount_cents > 0 AND NEW.net_paid_cents = NEW.approved_amount_cents AND NEW.reserved_authorized_cents = 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_PAID_FINANCIAL_MISMATCH')
        WHEN NEW.claim_status = 'DENIED'
             AND NOT (NEW.approved_amount_cents = 0 AND NEW.reserved_authorized_cents = 0 AND NEW.net_paid_cents = 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_DENIED_MUST_HAVE_ZERO_ACTIVE_EXPOSURE')
        WHEN NEW.claim_status = 'CLOSED_NO_PAY'
             AND NOT (NEW.approved_amount_cents = 0 AND NEW.reserved_authorized_cents = 0 AND NEW.net_paid_cents = 0)
            THEN RAISE(ABORT, 'ERR_CLAIM_CLOSED_NO_PAY_NONZERO_EXPOSURE')
        -- [ARCH-ST-010.3 / D-1 / NEW-5] Benign exit from SIU_HOLD requires an investigation
        -- for this exact claim closed as the schema's benign terminal state
        -- 'CLOSED_CLEARED_BENIGN' (ruling_outcome = 'CLEARED_BENIGN'), with zero active or
        -- confirmed-fraud investigations on the claim and the latest closed investigation
        -- being 'CLOSED_CLEARED_BENIGN'. Ordered AFTER the per-status financial consistency
        -- clauses so financial mismatches still surface first.
        WHEN OLD.claim_status = 'SIU_HOLD'
             AND NEW.claim_status IN ('UNDER_REVIEW','APPROVED','PARTIALLY_PAID','PAID')
             AND (
                 (
                     SELECT COUNT(*) FROM investigations
                     WHERE primary_claim_id = NEW.claim_id
                       AND investigation_status = 'CLOSED_CLEARED_BENIGN'
                       AND ruling_outcome = 'CLEARED_BENIGN'
                 ) < MAX(1, NEW.siu_referred)
                 OR EXISTS (
                     SELECT 1 FROM investigations
                     WHERE primary_claim_id = NEW.claim_id
                       AND (
                           investigation_status = 'CLOSED_CONFIRMED_FRAUD'
                           OR investigation_status NOT LIKE 'CLOSED_%'
                       )
                 )
                 OR (
                     SELECT i.investigation_status FROM investigations i
                     WHERE i.primary_claim_id = NEW.claim_id
                     ORDER BY i.closed_at_utc DESC, i.updated_at_utc DESC, i.investigation_id DESC
                     LIMIT 1
                 ) != 'CLOSED_CLEARED_BENIGN'
                 OR EXISTS (
                     SELECT 1 FROM immutable_events e
                     WHERE e.entity_type = 'Claim'
                       AND e.entity_id = NEW.claim_id
                       AND e.event_type = 'CLAIM_SIU_HOLD_PLACED'
                       AND e.occurred_at_utc > (
                           SELECT MAX(i.opened_at_utc) FROM investigations i
                           WHERE i.primary_claim_id = NEW.claim_id
                             AND i.investigation_status = 'CLOSED_CLEARED_BENIGN'
                             AND i.ruling_outcome = 'CLEARED_BENIGN'
                       )
                 )
             )
            THEN RAISE(ABORT, 'ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE')
        WHEN OLD.claim_status != NEW.claim_status AND NOT (
            (OLD.claim_status = 'SUBMITTED' AND NEW.claim_status IN ('UNDER_REVIEW','APPROVED','SIU_HOLD','DENIED'))
            OR (OLD.claim_status = 'UNDER_REVIEW' AND NEW.claim_status IN ('APPROVED','SIU_HOLD','DENIED','CLOSED_NO_PAY'))
            OR (OLD.claim_status = 'APPROVED' AND NEW.claim_status IN ('PARTIALLY_PAID','PAID','SIU_HOLD'))
            OR (OLD.claim_status = 'PARTIALLY_PAID' AND NEW.claim_status IN ('PAID','APPROVED','SIU_HOLD'))
            OR (OLD.claim_status = 'PAID' AND NEW.claim_status IN ('PARTIALLY_PAID','APPROVED','SIU_HOLD'))
            OR (OLD.claim_status = 'SIU_HOLD' AND NEW.claim_status IN ('UNDER_REVIEW','APPROVED','PARTIALLY_PAID','PAID','DENIED','CLOSED_NO_PAY'))
        )
            THEN RAISE(ABORT, 'ERR_CLAIM_INVALID_FSM_TRANSITION')
    END;
END;

CREATE TRIGGER trg_claims_block_delete
BEFORE DELETE ON claims
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_CLAIM_DELETE_FORBIDDEN');
END;

-- 3. Invoices Validation, Cap Enforcement, Financial Consistency & FSM Triggers
CREATE TRIGGER trg_invoices_validate_ins
BEFORE INSERT ON invoices
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.invoice_status NOT IN ('SUBMITTED','REJECTED_DUPLICATE')
            THEN RAISE(ABORT, 'ERR_INVOICE_INITIAL_STATUS_INVALID')
        WHEN NEW.approved_cents != 0 OR NEW.historical_approved_cents != 0
             OR NEW.reserved_authorized_cents != 0 OR NEW.gross_disbursed_cents != 0
             OR NEW.clawed_back_cents != 0 OR NEW.net_paid_cents != 0
            THEN RAISE(ABORT, 'ERR_INVOICE_INITIAL_BALANCES_MUST_BE_ZERO')
        WHEN NEW.invoice_status = 'SUBMITTED' AND EXISTS (
            SELECT 1 FROM invoices i
            WHERE i.invoice_status NOT IN ('REJECTED_DUPLICATE','REJECTED_ELIGIBILITY')
              AND (
                  (i.provider_id = NEW.provider_id AND i.provider_invoice_number = NEW.provider_invoice_number)
                  OR i.line_item_fingerprint = NEW.line_item_fingerprint
              )
        )
            THEN RAISE(ABORT, 'ERR_UNFLAGGED_DUPLICATE_INVOICE')
    END;
END;

CREATE TRIGGER trg_invoices_fsm_upd
BEFORE UPDATE ON invoices
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.invoice_id != OLD.invoice_id OR NEW.claim_id != OLD.claim_id
             OR NEW.provider_id != OLD.provider_id
             OR NEW.provider_invoice_number != OLD.provider_invoice_number
             OR NEW.service_start_utc != OLD.service_start_utc
             OR NEW.service_end_utc != OLD.service_end_utc
             OR NEW.submitted_at_utc != OLD.submitted_at_utc
             OR NEW.cpt_or_line_code != OLD.cpt_or_line_code
             OR NEW.line_item_fingerprint != OLD.line_item_fingerprint
             OR NEW.billed_cents != OLD.billed_cents
            THEN RAISE(ABORT, 'ERR_INVOICE_IMMUTABLE_CORE_FIELDS')
        WHEN NEW.historical_approved_cents < OLD.historical_approved_cents
            THEN RAISE(ABORT, 'ERR_INVOICE_HISTORICAL_APPROVED_DECREASE_FORBIDDEN')
        WHEN NEW.reserved_authorized_cents != COALESCE((
            SELECT SUM(amount_cents) FROM payments
            WHERE invoice_id = NEW.invoice_id AND payment_status = 'AUTHORIZED'
        ), 0)
            THEN RAISE(ABORT, 'ERR_INVOICE_RESERVED_AGGREGATE_TAMPERING')
        WHEN NEW.gross_disbursed_cents != COALESCE((
            SELECT SUM(disbursed_amount_cents) FROM payments
            WHERE invoice_id = NEW.invoice_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
        ), 0)
            THEN RAISE(ABORT, 'ERR_INVOICE_GROSS_DISBURSED_AGGREGATE_TAMPERING')
        WHEN NEW.clawed_back_cents != COALESCE((
            SELECT SUM(clawed_back_cents) FROM payments
            WHERE invoice_id = NEW.invoice_id AND payment_status = 'REVERSED_CLAWBACK'
        ), 0)
            THEN RAISE(ABORT, 'ERR_INVOICE_CLAWBACK_AGGREGATE_TAMPERING')
        WHEN NEW.net_paid_cents != COALESCE((
            SELECT SUM(net_paid_cents) FROM payments
            WHERE invoice_id = NEW.invoice_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
        ), 0)
            THEN RAISE(ABORT, 'ERR_INVOICE_NET_PAID_AGGREGATE_TAMPERING')
        WHEN OLD.invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
             AND NEW.invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
             AND (NEW.approved_cents != OLD.approved_cents OR NEW.historical_approved_cents != OLD.historical_approved_cents)
             AND NOT (
                 OLD.invoice_status = 'APPROVED' AND NEW.invoice_status = 'APPROVED'
                 AND NEW.historical_approved_cents = MAX(OLD.historical_approved_cents, NEW.approved_cents)
                 AND EXISTS (
                     SELECT 1 FROM immutable_events e
                     WHERE e.sequence_no = (
                         SELECT MAX(e2.sequence_no) FROM immutable_events e2
                         WHERE e2.entity_type = 'Invoice' AND e2.entity_id = NEW.invoice_id
                     )
                       AND e.event_type = 'INVOICE_APPROVAL_ADJUSTED'
                       AND e.payload_sha256 = sha256_hex(
                           '{"adjustment_authorized":true,"invoice_id":"' || NEW.invoice_id
                           || '","new_approved_cents":' || CAST(NEW.approved_cents AS TEXT)
                           || ',"old_approved_cents":' || CAST(OLD.approved_cents AS TEXT) || '}'
                       )
                 )
             )
            THEN RAISE(ABORT, 'ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE')
        WHEN OLD.invoice_status IN ('SUBMITTED','UNDER_REVIEW')
             AND NEW.invoice_status = 'APPROVED'
             AND (NEW.approved_cents <= 0 OR NEW.historical_approved_cents != NEW.approved_cents)
            THEN RAISE(ABORT, 'ERR_INVOICE_INITIAL_APPROVAL_HISTORICAL_MISMATCH')
        WHEN NEW.invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
             AND (
                 NEW.approved_cents <= 0
                 OR NEW.approved_cents > NEW.billed_cents
                 OR NEW.approved_cents < NEW.reserved_authorized_cents + NEW.net_paid_cents
                 OR (
                     (OLD.invoice_status IN ('SUBMITTED','UNDER_REVIEW') OR NEW.approved_cents != OLD.approved_cents OR NEW.historical_approved_cents != OLD.historical_approved_cents)
                     AND (SELECT p.policy_status FROM claims c JOIN policies p ON p.policy_id = c.policy_id WHERE c.claim_id = NEW.claim_id) != 'ACTIVE'
                 )
                 OR (SELECT inc.incident_timestamp_utc FROM claims c JOIN incidents inc ON inc.incident_id = c.incident_id WHERE c.claim_id = NEW.claim_id)
                    < (SELECT p.effective_start_utc FROM claims c JOIN policies p ON p.policy_id = c.policy_id WHERE c.claim_id = NEW.claim_id)
                 OR (SELECT inc.incident_timestamp_utc FROM claims c JOIN incidents inc ON inc.incident_id = c.incident_id WHERE c.claim_id = NEW.claim_id)
                    > (SELECT p.effective_end_utc FROM claims c JOIN policies p ON p.policy_id = c.policy_id WHERE c.claim_id = NEW.claim_id)
                 OR (
                     COALESCE((
                         SELECT SUM(i.approved_cents) FROM invoices i
                         WHERE i.claim_id = NEW.claim_id
                           AND i.invoice_id != NEW.invoice_id
                           AND i.invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
                     ), 0) + NEW.approved_cents
                 ) > MIN(
                     (SELECT c.claimed_amount_cents FROM claims c WHERE c.claim_id = NEW.claim_id),
                     (SELECT c.payout_cap_cents FROM claims c WHERE c.claim_id = NEW.claim_id),
                     MAX(0, (
                         SELECT p.coverage_limit_cents - p.deductible_cents
                         FROM claims c JOIN policies p ON p.policy_id = c.policy_id
                         WHERE c.claim_id = NEW.claim_id
                     ))
                 )
             )
            THEN RAISE(ABORT, 'ERR_INVOICE_EXCEEDS_CLAIM_OR_POLICY_CAP')
        WHEN NEW.invoice_status IN ('SUBMITTED','UNDER_REVIEW','REJECTED_DUPLICATE','REJECTED_ELIGIBILITY')
             AND (NEW.approved_cents != 0 OR NEW.historical_approved_cents != 0
                  OR NEW.reserved_authorized_cents != 0 OR NEW.gross_disbursed_cents != 0
                  OR NEW.clawed_back_cents != 0 OR NEW.net_paid_cents != 0)
            THEN RAISE(ABORT, 'ERR_INVOICE_UNAPPROVED_NONZERO_BALANCE')
        WHEN NEW.invoice_status = 'APPROVED'
             AND NOT (NEW.approved_cents > 0 AND NEW.net_paid_cents = 0)
            THEN RAISE(ABORT, 'ERR_INVOICE_APPROVED_FINANCIAL_MISMATCH')
        WHEN NEW.invoice_status = 'PARTIALLY_PAID'
             AND NOT (NEW.approved_cents > 0 AND NEW.net_paid_cents > 0 AND NEW.net_paid_cents < NEW.approved_cents)
            THEN RAISE(ABORT, 'ERR_INVOICE_PARTIALLY_PAID_FINANCIAL_MISMATCH')
        WHEN NEW.invoice_status = 'PAID'
             AND NOT (NEW.approved_cents > 0 AND NEW.net_paid_cents = NEW.approved_cents AND NEW.reserved_authorized_cents = 0)
            THEN RAISE(ABORT, 'ERR_INVOICE_PAID_FINANCIAL_MISMATCH')
        WHEN NEW.invoice_status = 'REVOKED_POST_APPROVAL'
             AND NOT (
                 OLD.invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID','REVOKED_POST_APPROVAL')
                 AND NEW.approved_cents = 0
                 AND NEW.historical_approved_cents = OLD.historical_approved_cents
                 AND NEW.historical_approved_cents > 0
                 AND NEW.reserved_authorized_cents = 0
                 AND NEW.net_paid_cents = 0
             )
            THEN RAISE(ABORT, 'ERR_INVOICE_REVOKED_FINANCIAL_MISMATCH')
        WHEN OLD.invoice_status != NEW.invoice_status AND NOT (
            (OLD.invoice_status = 'SUBMITTED' AND NEW.invoice_status IN ('UNDER_REVIEW','APPROVED','REJECTED_DUPLICATE','REJECTED_ELIGIBILITY'))
            OR (OLD.invoice_status = 'UNDER_REVIEW' AND NEW.invoice_status IN ('APPROVED','REJECTED_DUPLICATE','REJECTED_ELIGIBILITY'))
            OR (OLD.invoice_status = 'APPROVED' AND NEW.invoice_status IN ('PARTIALLY_PAID','PAID','REVOKED_POST_APPROVAL'))
            OR (OLD.invoice_status = 'PARTIALLY_PAID' AND NEW.invoice_status IN ('PAID','APPROVED','REVOKED_POST_APPROVAL'))
            OR (OLD.invoice_status = 'PAID' AND NEW.invoice_status IN ('PARTIALLY_PAID','APPROVED','REVOKED_POST_APPROVAL'))
        )
            THEN RAISE(ABORT, 'ERR_INVOICE_INVALID_FSM_TRANSITION')
    END;
END;

CREATE TRIGGER trg_invoices_sync_claim_au
AFTER UPDATE OF approved_cents, historical_approved_cents, invoice_status ON invoices
FOR EACH ROW
BEGIN
    UPDATE claims
       SET approved_amount_cents = COALESCE((
               SELECT SUM(approved_cents) FROM invoices
               WHERE claim_id = NEW.claim_id AND invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
           ), 0),
           historical_approved_cents = COALESCE((
               SELECT SUM(historical_approved_cents) FROM invoices
               WHERE claim_id = NEW.claim_id
           ), 0),
           reserved_authorized_cents = COALESCE((
               SELECT SUM(amount_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status = 'AUTHORIZED'
           ), 0),
           gross_disbursed_cents = COALESCE((
               SELECT SUM(disbursed_amount_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
           ), 0),
           clawed_back_cents = COALESCE((
               SELECT SUM(clawed_back_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status = 'REVERSED_CLAWBACK'
           ), 0),
           net_paid_cents = COALESCE((
               SELECT SUM(net_paid_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
           ), 0),
           claim_status = CASE
               WHEN claim_status IN ('DENIED','CLOSED_NO_PAY','SIU_HOLD') THEN claim_status
               WHEN COALESCE((
                   SELECT SUM(approved_cents) FROM invoices
                   WHERE claim_id = NEW.claim_id AND invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
               ), 0) = 0 THEN CASE
                   WHEN claim_status IN ('APPROVED','PARTIALLY_PAID','PAID') THEN 'SIU_HOLD'
                   ELSE claim_status
               END
               WHEN COALESCE((
                   SELECT SUM(net_paid_cents) FROM payments
                   WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
               ), 0) = COALESCE((
                   SELECT SUM(approved_cents) FROM invoices
                   WHERE claim_id = NEW.claim_id AND invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')
               ), 0)
               AND COALESCE((
                   SELECT SUM(amount_cents) FROM payments
                   WHERE claim_id = NEW.claim_id AND payment_status = 'AUTHORIZED'
               ), 0) = 0 THEN 'PAID'
               WHEN COALESCE((
                   SELECT SUM(net_paid_cents) FROM payments
                   WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
               ), 0) > 0 THEN 'PARTIALLY_PAID'
               ELSE 'APPROVED'
           END
     WHERE claim_id = NEW.claim_id;
END;

CREATE TRIGGER trg_invoices_block_delete
BEFORE DELETE ON invoices
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_INVOICE_DELETE_FORBIDDEN');
END;

-- 4. Payments Validation, Atomic Rollup & Immutable Field Enforcement Triggers
CREATE TRIGGER trg_payments_validate_ins
BEFORE INSERT ON payments
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.payment_status NOT IN ('AUTHORIZED','BLOCKED_INVALID_RECIPIENT','BLOCKED_UNAPPROVED','BLOCKED_OVERPAYMENT')
            THEN RAISE(ABORT, 'ERR_PAYMENT_INSERT_MUST_BE_AUTHORIZED_OR_BLOCKED')
        WHEN (SELECT claim_id FROM invoices WHERE invoice_id = NEW.invoice_id) != NEW.claim_id
            THEN RAISE(ABORT, 'ERR_PAYMENT_INVOICE_CLAIM_MISMATCH')
        WHEN NEW.payment_status = 'AUTHORIZED' AND (
            (NEW.recipient_type = 'CLAIMANT' AND NEW.recipient_claimant_id != (SELECT claimant_id FROM claims WHERE claim_id = NEW.claim_id))
            OR (NEW.recipient_type = 'PROVIDER' AND NEW.recipient_provider_id != (SELECT provider_id FROM invoices WHERE invoice_id = NEW.invoice_id))
        )
            THEN RAISE(ABORT, 'ERR_PAYMENT_RECIPIENT_OWNERSHIP_MISMATCH')
        WHEN NEW.payment_status = 'AUTHORIZED' AND (
            (SELECT invoice_status FROM invoices WHERE invoice_id = NEW.invoice_id) NOT IN ('APPROVED','PARTIALLY_PAID')
            OR (SELECT claim_status FROM claims WHERE claim_id = NEW.claim_id) NOT IN ('APPROVED','PARTIALLY_PAID')
        )
            THEN RAISE(ABORT, 'ERR_PAYMENT_REQUIRES_APPROVED_CLAIM_AND_INVOICE')
        WHEN NEW.payment_status = 'AUTHORIZED' AND (
            (
                COALESCE((SELECT SUM(p.amount_cents) FROM payments p WHERE p.invoice_id = NEW.invoice_id AND p.payment_status = 'AUTHORIZED'), 0)
                + COALESCE((SELECT SUM(p.net_paid_cents) FROM payments p WHERE p.invoice_id = NEW.invoice_id AND p.payment_status IN ('DISBURSED','REVERSED_CLAWBACK')), 0)
                + NEW.amount_cents
            ) > (SELECT i.approved_cents FROM invoices i WHERE i.invoice_id = NEW.invoice_id)
            OR (
                COALESCE((SELECT SUM(p.amount_cents) FROM payments p WHERE p.claim_id = NEW.claim_id AND p.payment_status = 'AUTHORIZED'), 0)
                + COALESCE((SELECT SUM(p.net_paid_cents) FROM payments p WHERE p.claim_id = NEW.claim_id AND p.payment_status IN ('DISBURSED','REVERSED_CLAWBACK')), 0)
                + NEW.amount_cents
            ) > MIN(
                (SELECT c.approved_amount_cents FROM claims c WHERE c.claim_id = NEW.claim_id),
                (SELECT c.payout_cap_cents FROM claims c WHERE c.claim_id = NEW.claim_id)
            )
        )
            THEN RAISE(ABORT, 'ERR_PAYMENT_EXCEEDS_APPROVED_CAP')
    END;
END;

CREATE TRIGGER trg_payments_validate_upd
BEFORE UPDATE ON payments
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.payment_id != OLD.payment_id
             OR NEW.claim_id != OLD.claim_id
             OR NEW.invoice_id != OLD.invoice_id
             OR NEW.recipient_type != OLD.recipient_type
             OR NEW.recipient_claimant_id IS NOT OLD.recipient_claimant_id
             OR NEW.recipient_provider_id IS NOT OLD.recipient_provider_id
             OR NEW.amount_cents != OLD.amount_cents
             OR NEW.idempotency_key != OLD.idempotency_key
             OR NEW.created_at_utc != OLD.created_at_utc
             OR NEW.authorized_by != OLD.authorized_by
             OR NEW.block_reason_code IS NOT OLD.block_reason_code
            THEN RAISE(ABORT, 'ERR_PAYMENT_IMMUTABLE_AUDIT_FIELD')
        WHEN OLD.payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
             AND (
                 NEW.disbursed_at_utc IS NOT OLD.disbursed_at_utc
                 OR NEW.external_bank_tx_ref IS NOT OLD.external_bank_tx_ref
                 OR NEW.disbursed_amount_cents != OLD.disbursed_amount_cents
             )
            THEN RAISE(ABORT, 'ERR_PAYMENT_POST_DISBURSEMENT_BANK_REF_IMMUTABLE')
        WHEN OLD.payment_status = 'AUTHORIZED' AND NEW.payment_status = 'DISBURSED' THEN CASE
            WHEN (SELECT invoice_status FROM invoices WHERE invoice_id = NEW.invoice_id) NOT IN ('APPROVED','PARTIALLY_PAID')
                 OR (SELECT claim_status FROM claims WHERE claim_id = NEW.claim_id) NOT IN ('APPROVED','PARTIALLY_PAID')
                THEN RAISE(ABORT, 'ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL')
            WHEN NEW.disbursed_at_utc < OLD.created_at_utc
                THEN RAISE(ABORT, 'ERR_DISBURSED_TIMESTAMP_BEFORE_CREATED')
            WHEN NOT EXISTS (
                 SELECT 1 FROM immutable_events e
                 WHERE e.sequence_no = (
                     SELECT MAX(e2.sequence_no) FROM immutable_events e2
                     WHERE e2.entity_type = 'Payment' AND e2.entity_id = NEW.payment_id
                 )
                   AND e.event_type = 'PAYMENT_AUTHORIZED'
                   AND e.claim_id = NEW.claim_id
                   AND e.occurred_at_utc >= OLD.created_at_utc
                   AND e.occurred_at_utc <= NEW.disbursed_at_utc
                   AND e.payload_sha256 = sha256_hex(
                       CASE NEW.recipient_type
                           WHEN 'PROVIDER' THEN
                               '{"amount_cents":' || CAST(NEW.amount_cents AS TEXT)
                               || ',"claim_id":"' || NEW.claim_id
                               || '","invoice_id":"' || NEW.invoice_id
                               || '","payment_id":"' || NEW.payment_id
                               || '","payment_status":"AUTHORIZED"'
                               || ',"recipient_provider_id":"' || NEW.recipient_provider_id || '"}'
                           ELSE
                               '{"amount_cents":' || CAST(NEW.amount_cents AS TEXT)
                               || ',"claim_id":"' || NEW.claim_id
                               || '","payment_id":"' || NEW.payment_id
                               || '","payment_status":"AUTHORIZED"'
                               || ',"recipient_claimant_id":"' || NEW.recipient_claimant_id || '"}'
                       END
                   )
             )
                THEN RAISE(ABORT, 'ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT')
        END
        WHEN OLD.payment_status = 'AUTHORIZED' AND NEW.payment_status = 'CANCELLED' THEN CASE
            WHEN NEW.reversed_at_utc < OLD.created_at_utc
                THEN RAISE(ABORT, 'ERR_CANCELLED_TIMESTAMP_BEFORE_CREATED')
            WHEN NEW.cancel_reason IS NULL
                THEN RAISE(ABORT, 'ERR_PAYMENT_CANCELLATION_REQUIRES_REASON')
            WHEN NOT EXISTS (
                 SELECT 1 FROM immutable_events e
                 WHERE e.sequence_no = (
                     SELECT MAX(e2.sequence_no) FROM immutable_events e2
                     WHERE e2.entity_type = 'Payment' AND e2.entity_id = NEW.payment_id
                 )
                   AND e.event_type = 'PAYMENT_CANCELLED'
                   AND e.claim_id = NEW.claim_id
                   AND e.occurred_at_utc >= OLD.created_at_utc
                   AND e.occurred_at_utc <= NEW.reversed_at_utc
                   AND e.payload_sha256 = sha256_hex(
                       '{"amount_cents":' || CAST(NEW.amount_cents AS TEXT)
                       || ',"claim_id":"' || NEW.claim_id
                       || '","payment_id":"' || NEW.payment_id
                       || '","payment_status":"CANCELLED"'
                       || ',"reason_code":"' || NEW.cancel_reason || '"}'
                   )
             )
                THEN RAISE(ABORT, 'ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT')
        END
        WHEN OLD.payment_status = 'DISBURSED' AND NEW.payment_status = 'REVERSED_CLAWBACK' THEN CASE
            WHEN NEW.reversed_at_utc < OLD.disbursed_at_utc
                THEN RAISE(ABORT, 'ERR_CLAWBACK_TIMESTAMP_BEFORE_DISBURSED')
            WHEN NOT EXISTS (
                 SELECT 1 FROM immutable_events e
                 WHERE e.sequence_no = (
                     SELECT MAX(e2.sequence_no) FROM immutable_events e2
                     WHERE e2.entity_type = 'Payment' AND e2.entity_id = NEW.payment_id
                 )
                   AND e.event_type = 'PAYMENT_CLAWBACK_REVERSED'
                   AND e.claim_id = NEW.claim_id
                   AND e.occurred_at_utc >= OLD.disbursed_at_utc
                   AND e.occurred_at_utc <= NEW.reversed_at_utc
                   AND e.payload_sha256 = sha256_hex(
                       '{"amount_cents":' || CAST(NEW.amount_cents AS TEXT)
                       || ',"claim_id":"' || NEW.claim_id
                       || '","clawed_back_cents":' || CAST(NEW.clawed_back_cents AS TEXT)
                       || ',"invoice_id":"' || NEW.invoice_id
                       || '","net_paid_cents":' || CAST(NEW.net_paid_cents AS TEXT)
                       || ',"payment_id":"' || NEW.payment_id
                       || '","payment_status":"REVERSED_CLAWBACK"}'
                   )
             )
                THEN RAISE(ABORT, 'ERR_CLAWBACK_REQUIRES_EVENT')
        END
        WHEN OLD.payment_status = 'REVERSED_CLAWBACK' AND NEW.payment_status = 'REVERSED_CLAWBACK' THEN CASE
            WHEN NEW.clawed_back_cents <= OLD.clawed_back_cents
                THEN RAISE(ABORT, 'ERR_CLAWBACK_MUST_STRICTLY_INCREASE')
            WHEN NEW.reversed_at_utc < OLD.reversed_at_utc
                THEN RAISE(ABORT, 'ERR_CLAWBACK_TIMESTAMP_REGRESSION')
            WHEN NOT EXISTS (
                 SELECT 1 FROM immutable_events e
                 WHERE e.sequence_no = (
                     SELECT MAX(e2.sequence_no) FROM immutable_events e2
                     WHERE e2.entity_type = 'Payment' AND e2.entity_id = NEW.payment_id
                 )
                   AND e.event_type = 'PAYMENT_CLAWBACK_REVERSED'
                   AND e.claim_id = NEW.claim_id
                   AND e.occurred_at_utc >= OLD.reversed_at_utc
                   AND e.occurred_at_utc <= NEW.reversed_at_utc
                   AND e.payload_sha256 = sha256_hex(
                       '{"amount_cents":' || CAST(NEW.amount_cents AS TEXT)
                       || ',"claim_id":"' || NEW.claim_id
                       || '","clawed_back_cents":' || CAST(NEW.clawed_back_cents AS TEXT)
                       || ',"invoice_id":"' || NEW.invoice_id
                       || '","net_paid_cents":' || CAST(NEW.net_paid_cents AS TEXT)
                       || ',"payment_id":"' || NEW.payment_id
                       || '","payment_status":"REVERSED_CLAWBACK"}'
                   )
             )
                THEN RAISE(ABORT, 'ERR_CLAWBACK_REQUIRES_EVENT')
        END
        ELSE RAISE(ABORT, 'ERR_PAYMENT_INVALID_STATE_TRANSITION')
    END;
END;

CREATE TRIGGER trg_payments_sync_aggregates_ai
AFTER INSERT ON payments
FOR EACH ROW
WHEN NEW.payment_status = 'AUTHORIZED'
BEGIN
    UPDATE invoices
       SET reserved_authorized_cents = COALESCE((
           SELECT SUM(amount_cents) FROM payments
           WHERE invoice_id = NEW.invoice_id AND payment_status = 'AUTHORIZED'
       ), 0)
     WHERE invoice_id = NEW.invoice_id;

    UPDATE claims
       SET reserved_authorized_cents = COALESCE((
           SELECT SUM(amount_cents) FROM payments
           WHERE claim_id = NEW.claim_id AND payment_status = 'AUTHORIZED'
       ), 0)
     WHERE claim_id = NEW.claim_id;
END;

CREATE TRIGGER trg_payments_sync_aggregates_au
AFTER UPDATE ON payments
FOR EACH ROW
BEGIN
    UPDATE invoices
       SET reserved_authorized_cents = COALESCE((
               SELECT SUM(amount_cents) FROM payments
               WHERE invoice_id = NEW.invoice_id AND payment_status = 'AUTHORIZED'
           ), 0),
           gross_disbursed_cents = COALESCE((
               SELECT SUM(disbursed_amount_cents) FROM payments
               WHERE invoice_id = NEW.invoice_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
           ), 0),
           clawed_back_cents = COALESCE((
               SELECT SUM(clawed_back_cents) FROM payments
               WHERE invoice_id = NEW.invoice_id AND payment_status = 'REVERSED_CLAWBACK'
           ), 0),
           net_paid_cents = COALESCE((
               SELECT SUM(net_paid_cents) FROM payments
               WHERE invoice_id = NEW.invoice_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
           ), 0),
           invoice_status = CASE
               WHEN invoice_status = 'REVOKED_POST_APPROVAL' THEN 'REVOKED_POST_APPROVAL'
               WHEN COALESCE((
                   SELECT SUM(net_paid_cents) FROM payments
                   WHERE invoice_id = NEW.invoice_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
               ), 0) = approved_cents
               AND COALESCE((
                   SELECT SUM(amount_cents) FROM payments
                   WHERE invoice_id = NEW.invoice_id AND payment_status = 'AUTHORIZED'
               ), 0) = 0 THEN 'PAID'
               WHEN COALESCE((
                   SELECT SUM(net_paid_cents) FROM payments
                   WHERE invoice_id = NEW.invoice_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
               ), 0) > 0 THEN 'PARTIALLY_PAID'
               ELSE 'APPROVED'
           END
     WHERE invoice_id = NEW.invoice_id;

    UPDATE claims
       SET reserved_authorized_cents = COALESCE((
               SELECT SUM(amount_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status = 'AUTHORIZED'
           ), 0),
           gross_disbursed_cents = COALESCE((
               SELECT SUM(disbursed_amount_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
           ), 0),
           clawed_back_cents = COALESCE((
               SELECT SUM(clawed_back_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status = 'REVERSED_CLAWBACK'
           ), 0),
           net_paid_cents = COALESCE((
               SELECT SUM(net_paid_cents) FROM payments
               WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
           ), 0),
           claim_status = CASE
               WHEN claim_status IN ('SIU_HOLD','DENIED','CLOSED_NO_PAY') THEN claim_status
               WHEN COALESCE((
                   SELECT SUM(net_paid_cents) FROM payments
                   WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
               ), 0) = approved_amount_cents
               AND COALESCE((
                   SELECT SUM(amount_cents) FROM payments
                   WHERE claim_id = NEW.claim_id AND payment_status = 'AUTHORIZED'
               ), 0) = 0 THEN 'PAID'
               WHEN COALESCE((
                   SELECT SUM(net_paid_cents) FROM payments
                   WHERE claim_id = NEW.claim_id AND payment_status IN ('DISBURSED','REVERSED_CLAWBACK')
               ), 0) > 0 THEN 'PARTIALLY_PAID'
               ELSE 'APPROVED'
           END
     WHERE claim_id = NEW.claim_id;
END;

CREATE TRIGGER trg_payments_block_delete
BEFORE DELETE ON payments
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_PAYMENT_DELETE_FORBIDDEN');
END;

-- 5. Investigations Validation & FSM Triggers
CREATE TRIGGER trg_investigations_validate_ins
BEFORE INSERT ON investigations
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.investigation_status != 'OPEN'
            THEN RAISE(ABORT, 'ERR_INVESTIGATION_INITIAL_STATUS_MUST_BE_OPEN')
        WHEN NEW.recovered_clawback_cents != 0
            THEN RAISE(ABORT, 'ERR_INVESTIGATION_INITIAL_CLAWBACK_MUST_BE_ZERO')
        WHEN EXISTS (
            SELECT 1 FROM investigations i
            WHERE i.primary_claim_id = NEW.primary_claim_id
              AND i.investigation_status NOT LIKE 'CLOSED_%'
        )
            THEN RAISE(ABORT, 'ERR_CONCURRENT_OPEN_INVESTIGATION_FORBIDDEN')
        WHEN EXISTS (
            SELECT 1 FROM investigations i
            WHERE i.primary_claim_id = NEW.primary_claim_id
              AND (
                  NEW.opened_at_utc < i.opened_at_utc
                  OR (i.closed_at_utc IS NOT NULL AND NEW.opened_at_utc < i.closed_at_utc)
              )
        )
            THEN RAISE(ABORT, 'ERR_INVESTIGATION_TIMESTAMP_REGRESSION')
    END;
END;

CREATE TRIGGER trg_investigations_fsm_upd
BEFORE UPDATE ON investigations
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN OLD.investigation_status LIKE 'CLOSED_%'
            THEN RAISE(ABORT, 'ERR_CLOSED_INVESTIGATION_IMMUTABLE')
        WHEN NEW.investigation_id != OLD.investigation_id
             OR NEW.primary_claim_id != OLD.primary_claim_id
             OR NEW.subject_claimant_id IS NOT OLD.subject_claimant_id
             OR NEW.subject_provider_id IS NOT OLD.subject_provider_id
             OR NEW.opened_at_utc != OLD.opened_at_utc
            THEN RAISE(ABORT, 'ERR_INVESTIGATION_IMMUTABLE_CORE_FIELDS')
        WHEN NEW.updated_at_utc < OLD.updated_at_utc
            THEN RAISE(ABORT, 'ERR_INVESTIGATION_TIMESTAMP_REGRESSION')
        WHEN NEW.investigation_status LIKE 'CLOSED_%'
             AND (
                 NEW.closed_at_utc IS NULL
                 OR NEW.closed_at_utc != NEW.updated_at_utc
                 OR EXISTS (
                     SELECT 1 FROM investigations i
                     WHERE i.primary_claim_id = NEW.primary_claim_id
                       AND i.investigation_id != NEW.investigation_id
                       AND (
                           NEW.closed_at_utc < i.opened_at_utc
                           OR NEW.closed_at_utc < i.updated_at_utc
                           OR (i.closed_at_utc IS NOT NULL AND NEW.closed_at_utc <= i.closed_at_utc)
                       )
                 )
             )
            THEN RAISE(ABORT, 'ERR_INVESTIGATION_TIMESTAMP_REGRESSION')
        WHEN OLD.investigation_status != NEW.investigation_status AND NOT (
            (OLD.investigation_status = 'OPEN' AND NEW.investigation_status IN ('EVIDENCE_COLLECTION','SIU_FIELD_REVIEW','CLOSED_CLEARED_BENIGN'))
            OR (OLD.investigation_status = 'EVIDENCE_COLLECTION' AND NEW.investigation_status IN ('SIU_FIELD_REVIEW','LEGAL_ESCALATION','CLOSED_CONFIRMED_FRAUD','CLOSED_CLEARED_BENIGN','CLOSED_INSUFFICIENT_EVIDENCE'))
            OR (OLD.investigation_status = 'SIU_FIELD_REVIEW' AND NEW.investigation_status IN ('LEGAL_ESCALATION','CLOSED_CONFIRMED_FRAUD','CLOSED_CLEARED_BENIGN','CLOSED_INSUFFICIENT_EVIDENCE'))
            OR (OLD.investigation_status = 'LEGAL_ESCALATION' AND NEW.investigation_status IN ('CLOSED_CONFIRMED_FRAUD','CLOSED_CLEARED_BENIGN','CLOSED_INSUFFICIENT_EVIDENCE'))
        )
            THEN RAISE(ABORT, 'ERR_INVALID_INVESTIGATION_FSM_TRANSITION')
    END;
END;

-- 6. [ARCH-ST-010.1 / C-6] Investigation Delete Protection
CREATE TRIGGER trg_investigations_block_delete
BEFORE DELETE ON investigations
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_INVESTIGATION_DELETE_FORBIDDEN');
END;

-- 7. [ARCH-ST-010.2 / C-6 / NEW-4] Relationship-Edge Tamper Protection
CREATE TRIGGER trg_edges_flow_upd
BEFORE UPDATE ON relationship_edges
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.edge_id != OLD.edge_id
             OR NEW.edge_type != OLD.edge_type
             OR NEW.source_entity_type != OLD.source_entity_type
             OR NEW.source_claimant_id IS NOT OLD.source_claimant_id
             OR NEW.source_provider_id IS NOT OLD.source_provider_id
             OR NEW.target_entity_type != OLD.target_entity_type
             OR NEW.target_claimant_id IS NOT OLD.target_claimant_id
             OR NEW.target_provider_id IS NOT OLD.target_provider_id
             OR NEW.canonical_src_key != OLD.canonical_src_key
             OR NEW.canonical_dst_key != OLD.canonical_dst_key
             OR NEW.strength_weight != OLD.strength_weight
             OR NEW.evidence_count != OLD.evidence_count
             OR NEW.first_observed_utc != OLD.first_observed_utc
             OR NEW.supporting_claim_id != OLD.supporting_claim_id
            THEN RAISE(ABORT, 'ERR_EDGE_CORE_FIELDS_IMMUTABLE')
        WHEN NEW.last_observed_utc < OLD.last_observed_utc
            THEN RAISE(ABORT, 'ERR_EDGE_OBSERVED_TIME_REGRESSION')
        WHEN NEW.is_active = 1 AND OLD.is_active = 0
            THEN RAISE(ABORT, 'ERR_EDGE_REACTIVATION_FORBIDDEN')
        WHEN NEW.is_active = 0 AND OLD.is_active = 1
             AND NOT EXISTS (
                 SELECT 1 FROM immutable_events e
                 WHERE e.sequence_no = (
                     SELECT MAX(e2.sequence_no) FROM immutable_events e2
                     WHERE e2.entity_type = 'RelationshipEdge' AND e2.entity_id = NEW.edge_id
                 )
                   AND e.event_type = 'RELATIONSHIP_EDGE_DEACTIVATED'
                   AND e.payload_sha256 = sha256_hex(
                       '{"claim_id":"' || NEW.supporting_claim_id
                       || '","edge_id":"' || NEW.edge_id || '"}'
                   )
             )
            THEN RAISE(ABORT, 'ERR_EDGE_DEACTIVATION_REQUIRES_EVENT')
        WHEN NEW.is_active = 0 AND OLD.is_active = 1
            THEN NULL
        WHEN NEW.is_active = OLD.is_active
            THEN NULL
        ELSE RAISE(ABORT, 'ERR_EDGE_MUTATION_INVALID')
    END;
END;

CREATE TRIGGER trg_edges_block_delete
BEFORE DELETE ON relationship_edges
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_EDGE_DELETE_FORBIDDEN');
END;

-- 8. [ARCH-ST-010.1 / C-6] Fraud-Indicator Append-Only Protection
CREATE TRIGGER trg_findings_block_upd
BEFORE UPDATE ON fraud_indicators
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_FRAUD_INDICATOR_MUTATION_FORBIDDEN');
END;

CREATE TRIGGER trg_findings_block_delete
BEFORE DELETE ON fraud_indicators
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_FRAUD_INDICATOR_DELETE_FORBIDDEN');
END;

-- 9. [ARCH-ST-010.1 / C-6] claims.siu_referred lifecycle
CREATE TRIGGER trg_claims_siu_referred_au
AFTER UPDATE OF claim_status ON claims
FOR EACH ROW
WHEN OLD.claim_status != 'SIU_HOLD' AND NEW.claim_status = 'SIU_HOLD'
BEGIN
    UPDATE claims
       SET siu_referred = MAX(
           OLD.siu_referred + 1,
           1,
           (
               SELECT COUNT(*) FROM investigations
               WHERE primary_claim_id = NEW.claim_id
                 AND (
                     (investigation_status = 'CLOSED_CLEARED_BENIGN' AND ruling_outcome = 'CLEARED_BENIGN')
                     OR investigation_status NOT LIKE 'CLOSED_%'
                 )
           ) + 1
       )
     WHERE claim_id = NEW.claim_id;
END;

-- 10. [ARCH-ST-010.1 / C-6] Investigation confirmed-fraud outcome propagates
--     the SIU referral to the primary claim.
CREATE TRIGGER trg_investigations_siu_ref_au
AFTER UPDATE OF investigation_status ON investigations
FOR EACH ROW
WHEN NEW.investigation_status = 'CLOSED_CONFIRMED_FRAUD'
BEGIN
    UPDATE claims SET siu_referred = MAX(siu_referred, 1) WHERE claim_id = NEW.primary_claim_id;
END;

-- 11. [ARCH-ST-010.2 / C-6 / NEW-1] Score-to-evidence reconciliation (ST-SCORE-V1)
CREATE TRIGGER trg_claims_score_upd
BEFORE UPDATE OF latest_ief_score, latest_risk_tier, scoring_evidence_sha256 ON claims
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.scoring_evidence_sha256 IS NULL
            THEN RAISE(ABORT, 'ERR_SCORE_EVIDENCE_DIGEST_REQUIRED')
        WHEN (SELECT COUNT(*) FROM fraud_indicators WHERE claim_id = NEW.claim_id) = 0
             AND NEW.latest_ief_score != 0.0
            THEN RAISE(ABORT, 'ERR_SCORE_ZERO_INDICATORS_NONZERO_FORBIDDEN')
        WHEN (SELECT COUNT(*) FROM fraud_indicators WHERE claim_id = NEW.claim_id) > 0
             AND NOT (
                 CASE
                     WHEN EXISTS (
                         SELECT 1
                         FROM fraud_indicators f1_bank
                         JOIN fraud_indicators f1_dup
                           ON f1_dup.claim_id = f1_bank.claim_id
                         JOIN fraud_indicators f2_bank
                           ON f2_bank.indicator_code = 'IND-01'
                          AND f2_bank.canonical_evidence_token = f1_bank.canonical_evidence_token
                          AND f2_bank.claim_id != f1_bank.claim_id
                         JOIN fraud_indicators f2_dup
                           ON f2_dup.claim_id = f2_bank.claim_id
                          AND f2_dup.indicator_code = 'IND-03'
                          AND f2_dup.canonical_evidence_token = f1_dup.canonical_evidence_token
                         WHERE f1_bank.claim_id = NEW.claim_id
                           AND f1_bank.indicator_code = 'IND-01'
                           AND f1_dup.indicator_code = 'IND-03'
                     ) THEN
                         NEW.latest_ief_score >= MAX(65.0, ROUND((
                             0.35 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'NETWORK' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 60.0)
                             + 0.30 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'FINANCIAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 55.0)
                             + 0.20 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'BEHAVIORAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 45.0)
                             + 0.15 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'DOCUMENT' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 40.0)
                         ) - 0.005, 2))
                         AND NEW.latest_ief_score <= MIN(100.0, MAX(65.0, ROUND((
                             0.35 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'NETWORK' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 60.0)
                             + 0.30 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'FINANCIAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 55.0)
                             + 0.20 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'BEHAVIORAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 45.0)
                             + 0.15 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'DOCUMENT' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 40.0)
                         ) + 20.0 + 0.005, 2)))
                     ELSE
                         NEW.latest_ief_score >= ROUND(0.15 * (
                             0.35 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'NETWORK' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 60.0)
                             + 0.30 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'FINANCIAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 55.0)
                             + 0.20 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'BEHAVIORAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 45.0)
                             + 0.15 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'DOCUMENT' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 40.0)
                         ) - 0.005, 2)
                         AND NEW.latest_ief_score <= ROUND((
                             0.35 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'NETWORK' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 60.0)
                             + 0.30 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'FINANCIAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 55.0)
                             + 0.20 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'BEHAVIORAL' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 45.0)
                             + 0.15 * MIN(100.0, 100.0 * COALESCE((SELECT SUM(max_pts) FROM (SELECT MAX(raw_points) AS max_pts FROM fraud_indicators WHERE claim_id = NEW.claim_id AND pillar = 'DOCUMENT' GROUP BY indicator_code, canonical_evidence_token)), 0.0) / 40.0)
                         ) + 0.005, 2)
                 END
             )
            THEN RAISE(ABORT, 'ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS')
        WHEN NEW.scoring_evidence_sha256 != (
                SELECT COALESCE(
                    sha256_hex(
                        'ST-SCORE-V1|' || NEW.claim_id
                        || '|IND_COUNT:' || CAST((SELECT COUNT(*) FROM fraud_indicators WHERE claim_id = NEW.claim_id) AS TEXT)
                        || COALESCE(f.tokens, '')
                        || '|IEF:' || printf('%.2f', NEW.latest_ief_score)
                    ),
                    sha256_hex(
                        'ST-SCORE-V1|' || NEW.claim_id
                        || '|IND_COUNT:0'
                        || '|IEF:' || printf('%.2f', NEW.latest_ief_score)
                    )
                )
                FROM (
                    SELECT group_concat(ind_tok, '') AS tokens FROM (
                        SELECT '|IND:' || indicator_code
                               || ':' || pillar
                               || ':' || printf('%.3f', raw_points)
                               || ':' || printf('%.3f', normalized_value)
                               || ':' || canonical_evidence_token AS ind_tok
                        FROM fraud_indicators
                        WHERE claim_id = NEW.claim_id
                        ORDER BY indicator_code ASC, canonical_evidence_token ASC
                    )
                ) f
             )
            THEN RAISE(ABORT, 'ERR_SCORE_EVIDENCE_DIGEST_MISMATCH')
        WHEN NEW.latest_risk_tier != CASE
                WHEN NEW.latest_ief_score >= 85.0 THEN 'CRITICAL'
                WHEN NEW.latest_ief_score >= 65.0 THEN 'HIGH'
                WHEN NEW.latest_ief_score >= 30.0 THEN 'MEDIUM'
                ELSE 'LOW'
             END
            THEN RAISE(ABORT, 'ERR_SCORE_TIER_MISMATCH')
    END;
END;

-- 12. [ARCH-ST-010.3 / D-6] Ingestion-Exception Immutability
--     Audit-exception records are append-only; mutation or deletion is forbidden.
CREATE TRIGGER trg_ingestion_exceptions_block_upd
BEFORE UPDATE ON ingestion_exceptions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_INGESTION_EXCEPTION_IMMUTABLE');
END;

CREATE TRIGGER trg_ingestion_exceptions_block_del
BEFORE DELETE ON ingestion_exceptions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_INGESTION_EXCEPTION_DELETE_FORBIDDEN');
END;

# CHANGE SUMMARY — `SENTINEL//TRACE` `ARCH-ST-010.2`

- **Repository:** `Lavish911/sentinel-trace`
- **Base Branch / Commit:** `audit/arch-st-010` (`44f5b67`)
- **Working Branch:** `fix/arch-st-010-2`
- **Target Specification:** `ARCH-ST-010.2.md`

---

## 1. Concise Summary of Changes (`ARCH-ST-010.1` $\to$ `ARCH-ST-010.2`)

1. **`NEW-1` — Claim `INSERT` Lockdown & SQLite Indicator-Envelope Score Verification (`trg_claims_validate_ins`, `trg_claims_score_upd`, §6.6):**
   - `trg_claims_validate_ins` now enforces `NEW.latest_ief_score = 0.0`, `NEW.latest_risk_tier = 'LOW'`, `NEW.scoring_evidence_sha256 IS NULL` (`ERR_CLAIM_INITIAL_SCORE_STATE_INVALID`), and `NEW.siu_referred = 0` (`ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO`) on every `INSERT INTO claims`.
   - `trg_claims_score_upd` now computes the Stage S3–S5 deduplicated base score $S_{\text{base}}(c)$ directly from `fraud_indicators` inside SQLite and evaluates the §9.4-S7 hard-collusion eligibility predicate (`IND-01` + `IND-03` shared `(BANK, DUP_FP)` token pair across $\ge 2$ claims). It blocks nonzero scores when `IND_COUNT = 0` (`ERR_SCORE_ZERO_INDICATORS_NONZERO_FORBIDDEN`), blocks scores outside $[\text{round}(0.15 S_{\text{base}} - 0.005, 2), \text{round}(S_{\text{base}} + 0.005, 2)]$ for non-eligible claims (`ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS`), and blocks scores outside $[\max(65.0, \text{round}(S_{\text{base}} - 0.005, 2)), \min(100.0, \max(65.0, \text{round}(S_{\text{base}} + 20.0 + 0.005, 2)))]$ for hard-collusion eligible claims.
   - Reconciled the §6.6 `IND-03 (35.0) + IND-14 (12.0)` vector to its true $S_{\text{base}} = 24.42$ (`LOW`, digest `b00249984688081e409d3da5dd98a735147fa3b3803cb4d8c936581b92496227`) and proved `30.76` is rejected (`ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS`).
   - Documented the explicit trust boundary between `[DB-ENFORCED]` trigger bounds and `[APP-ENFORCED]` exact dampening/cluster-boost selection.
2. **`NEW-2` — `claims.siu_referred` Irreversibility & Workflow Gating (`trg_claims_validate_ins`, `trg_claims_fsm_upd`, §4.5):**
   - Blocked `1 -> 0` reset (`ERR_CLAIM_SIU_REFERRED_IRREVERSIBLE`) and blocked `0 -> 1` unless `NEW.claim_status = 'SIU_HOLD'` or a `CLOSED_CONFIRMED_FRAUD` investigation exists (`ERR_CLAIM_SIU_REFERRAL_REQUIRES_HOLD_OR_CONFIRMED_FRAUD`).
3. **`NEW-3` — Fail-Closed Verification Harnesses (`archive/verify-0102/`, `archive/verify-0101/`, `archive/audit-harness/verify_math.py`):**
   - Replaced passive print helpers with a fail-closed `TestRunner` (`test_delta_0102.py`, 77/77 assertions) and fail-closed `verify_digest_0102.py` and `verify_math.py`, each verified with `--mutate-self-test` (exits `1` on mutation).
4. **`NEW-4` — `trg_edges_flow_upd` Dead-Code Removal & Timestamp Monotonicity (`trigs_0102.sql`):**
   - Moved `WHEN NEW.last_observed_utc < OLD.last_observed_utc THEN RAISE(ABORT, 'ERR_EDGE_OBSERVED_TIME_REGRESSION')` before `is_active` branches, added `WHEN NEW.is_active = 0 AND OLD.is_active = 1 THEN NULL` after the `RELATIONSHIP_EDGE_DEACTIVATED` event check, and removed unreachable `WHEN` clauses after `ELSE`.
5. **`NEW-5` — Incremental Clawback Fresh-Event Gate & Benign `SIU_HOLD` Exit (`trg_payments_validate_upd`, `trg_claims_fsm_upd`, §4.3, §4.5):**
   - Enforced `MAX(sequence_no)` latest-event matching across all payment event gates and added `PAYMENT_CLAWBACK_REVERSED` verification (`ERR_CLAWBACK_REQUIRES_EVENT`) to incremental `REVERSED_CLAWBACK -> REVERSED_CLAWBACK` updates.
   - Extended `SIU_HOLD` exit targets in `trg_claims_fsm_upd` to `{'UNDER_REVIEW', 'APPROVED', 'PARTIALLY_PAID', 'PAID', 'DENIED', 'CLOSED_NO_PAY'}`, strictly partitioned by live financial balances so partially-paid or fully-paid claims cleared as benign return to `PARTIALLY_PAID` or `PAID` without artificial clawbacks.
6. **`NEW-6` — `is_canonical_json` Hardening & Split Numeric Policy (`trg_events_chain_insert`, §6.5):**
   - Hardened `is_canonical_json` with `parse_constant` trap + `allow_nan=False` to reject `NaN`, `Infinity`, `-Infinity`, duplicate keys, and non-object roots while allowing finite canonical floats in `fraud_indicators.feature_snapshot_json`.
   - Added `json_tree(NEW.payload_json)` check in `trg_events_chain_insert` (`ERR_EVENT_PAYLOAD_FLOAT_FORBIDDEN`) to reject floats in `immutable_events.payload_json` inside SQLite.
7. **`NEW-7`, `NEW-8`, `NEW-9` — Vector Verification, Pinned Runtime Execution, and Repo Hygiene:**
   - Added `VH-1..VH-7` and `PAYMENT_CANCELLED` verification to `verify_math.py` and `test_delta_0102.py`.
   - Executed all suites on **Python `3.10.12` / SQLite `3.40.1`** and published the new operational schema digest:
     `EXPECTED_OPERATIONAL_SCHEMA_SHA256 = 26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a`.

---

## 2. Compatibility Effects

- **Table Schema (`ops_0102.sql`):** 100% column- and constraint-compatible with `ops_0101.sql` (`12` `STRICT` tables unchanged).
- **Trigger Count:** Preserved at exactly **`24` triggers** (`36` `sqlite_master` objects total).
- **Schema Digest (`ST-SCHEMA-V1`):** Updated from `63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93` (`010.1`) to `26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a` (`010.2`) reflecting the updated trigger definitions in `trigs_0102.sql`.
- **Preserved History:** All `ARCH-ST-001.md` .. `ARCH-ST-010.1.md`, `CORRECTION_TRACEABILITY.md`, `VERIFICATION_REPORT.md`, `CHANGE_SUMMARY.md`, and `archive/verify-0101/baseline_0101/` files are preserved intact.

---

## 3. Remaining Limitations & Honest Scope Boundary

1. **Unkeyed SQLite Trust Boundary (`ST-SCORE-V1` & Event Gates):** Because SQLite triggers have no secret HMAC key isolated from a raw SQL writer, a principal with raw SQL write access to *both* `fraud_indicators` (or `immutable_events`) and `claims`/`payments` can insert synthetic indicator or event rows. However, `trg_claims_score_upd` strictly bounds `latest_ief_score` within the mathematical $[0.15 \cdot S_{\text{base}}, S_{\text{base}}]$ (or hard-collusion) envelope derived from `fraud_indicators`.
2. **Application & Seed-Generator Implementation (`T-01..T-20`):** The 5,000-claim seed generator (`seed=42`), FastAPI backend, and React/TypeScript frontend are out of scope for this architecture specification task and remain `SPECIFIED — NOT EXECUTED`.

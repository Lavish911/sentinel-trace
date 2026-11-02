# CORRECTION TRACEABILITY MATRIX — `ARCH-ST-010.2` (`NEW-1` through `NEW-9`)

- **Repository:** `Lavish911/sentinel-trace`
- **Starting Branch & Commit:** `audit/arch-st-010` (`44f5b67`)
- **Working Branch:** `fix/arch-st-010-2`
- **Target Baseline:** `ARCH-ST-010.2.md`
- **Pinned Execution Runtime:** **Python `3.10.12`** / **SQLite `3.40.1`** (`sqlite3` stdlib module, Linux x86_64)
- **Preserved `ARCH-ST-010.1` Artifacts:** `ARCH-ST-010.1.md`, `CORRECTION_TRACEABILITY.md`, `VERIFICATION_REPORT.md`, `CHANGE_SUMMARY.md`, and `archive/verify-0101/baseline_0101/` (`ops_0101.sql`, `trigs_0101.sql`, `test_delta.py`, `verify_digest_0101.py`).

---

## Summary Traceability Matrix (`NEW-1` .. `NEW-9`)

| Finding ID | Severity | Argon Review Claim | Reproduced on `010.1`? | Exact Resolution in `ARCH-ST-010.2` | Fail-Closed Test IDs (`test_delta_0102.py` / `verify_math.py`) | Status on Pinned `3.10.12` / `3.40.1` |
|---|---|---|---|---|---|---|
| **NEW-1** | **CRITICAL** | Score manipulation (`30.76` accepted for `24.42` indicators; `99.99` accepted with `0` indicators) and `claims` `INSERT` score bypass | **YES** (3/3 bypasses reproduced) | 1. `trg_claims_validate_ins` enforces `latest_ief_score = 0.0`, `latest_risk_tier = 'LOW'`, `scoring_evidence_sha256 IS NULL` (`ERR_CLAIM_INITIAL_SCORE_STATE_INVALID`), and `siu_referred = 0` (`ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO`).<br>2. `trg_claims_score_upd` computes the Stage S3–S5 deduplicated base score $S_{\text{base}}(c)$ and the §9.4-S7 hard-collusion eligibility predicate directly inside SQLite from `fraud_indicators`, enforcing `0.0` when `IND_COUNT = 0` (`ERR_SCORE_ZERO_INDICATORS_NONZERO_FORBIDDEN`), $[\text{round}(0.15 S_{\text{base}} - 0.005, 2), \text{round}(S_{\text{base}} + 0.005, 2)]$ when non-eligible (`ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS`), and $[\max(65.0, \text{round}(S_{\text{base}} - 0.005, 2)), \min(100.0, \max(65.0, \text{round}(S_{\text{base}} + 20.0 + 0.005, 2)))]$ when hard-collusion eligible.<br>3. Reconciled the §6.6 `IND-03 (35.0) + IND-14 (12.0)` vector to $S_{\text{base}} = 24.42$ (`LOW`, digest `b00249984688081e409d3da5dd98a735147fa3b3803cb4d8c936581b92496227`) and proved `30.76` is rejected.<br>4. Documented the exact trust boundary of `ST-SCORE-V1` in §6.6. | `NEW-1a`, `NEW-1b`, `NEW-1c`, `NEW-1d`, `NEW-1e`, `NEW-1f`, `C-6g`, `C-6h`, `C-6i`, `C-7-sql` | `PASS — EXECUTED` |
| **NEW-2** | **HIGH** | `claims.siu_referred` is neither irreversible (`1 -> 0` succeeds) nor constrained to SIU workflow (`0 -> 1` on `INSERT` or `UPDATE` without `SIU_HOLD` / `CLOSED_CONFIRMED_FRAUD` succeeds) | **YES** (both bypasses reproduced) | 1. `trg_claims_validate_ins` blocks `INSERT` with `siu_referred != 0` (`ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO`).<br>2. `trg_claims_fsm_upd` blocks `OLD.siu_referred = 1 AND NEW.siu_referred = 0` (`ERR_CLAIM_SIU_REFERRED_IRREVERSIBLE`) and blocks `OLD.siu_referred = 0 AND NEW.siu_referred = 1` unless `NEW.claim_status = 'SIU_HOLD'` or a `CLOSED_CONFIRMED_FRAUD` investigation exists (`ERR_CLAIM_SIU_REFERRAL_REQUIRES_HOLD_OR_CONFIRMED_FRAUD`).<br>3. Added dedicated test (`C-6j-invg`) on a fresh claim (`CLM-2026-000002`, `siu_referred = 0`) proving `trg_investigations_siu_ref_au` flips `0 -> 1` on `CLOSED_CONFIRMED_FRAUD`. | `NEW-2a`, `NEW-2b`, `NEW-2c`, `C-6j-hold`, `C-6j-invg` | `PASS — EXECUTED` |
| **NEW-3** | **CRITICAL** | `archive/verify-0101/test_delta.py` prints `[FAIL]` without tracking failures or exiting non-zero | **YES** (verified by inspection & mutation) | Replaced passive print helpers with a fail-closed `TestRunner` (`archive/verify-0102/test_delta_0102.py` & `archive/verify-0101/test_delta.py`) that records every positive/negative check, requires exact expected `sqlite3.IntegrityError` codes, exits `1` on any failure, and includes a `--mutate-self-test` mode verified to exit `1`. Also made `verify_digest_0102.py` and `verify_math.py` fail-closed. | `SELF-00` (`--mutate-self-test` subprocess check) + all `76` assertions | `PASS — EXECUTED` |
| **NEW-4** | **MEDIUM** | `trg_edges_flow_upd` has unreachable dead code after `ELSE` and permits `last_observed_utc` regression when `is_active` is unchanged | **YES** (`2026-01-05` -> `1999-01-01` succeeded) | Moved `WHEN NEW.last_observed_utc < OLD.last_observed_utc THEN RAISE(ABORT, 'ERR_EDGE_OBSERVED_TIME_REGRESSION')` ahead of the `is_active` branches, added explicit `WHEN NEW.is_active = 0 AND OLD.is_active = 1 THEN NULL` after the `RELATIONSHIP_EDGE_DEACTIVATED` event check, and removed all unreachable `WHEN` clauses after `ELSE`. | `NEW-4a`, `NEW-4b`, `C-6b-self`, `C-6b-order`, `C-6b-strength`, `C-6b-endpoint`, `C-6c`, `C-6c-ok`, `C-6d`, `C-6e` | `PASS — EXECUTED` |
| **NEW-5** | **HIGH** | Incremental clawback (`REVERSED_CLAWBACK -> REVERSED_CLAWBACK`) lacks fresh event check; `SIU_HOLD` cannot exit cleanly for benign partially-paid or fully-paid claims | **YES** (eventless incremental clawback succeeded; benign `SIU_HOLD -> PARTIALLY_PAID` blocked) | 1. Added `MAX(sequence_no)` latest-event checks to all payment event gates in `trg_payments_validate_upd`, including the incremental `OLD.payment_status = 'REVERSED_CLAWBACK' AND NEW.payment_status = 'REVERSED_CLAWBACK'` branch (`ERR_CLAWBACK_REQUIRES_EVENT`).<br>2. Extended `SIU_HOLD` exit targets in `trg_claims_fsm_upd` to `{'UNDER_REVIEW', 'APPROVED', 'PARTIALLY_PAID', 'PAID', 'DENIED', 'CLOSED_NO_PAY'}`, strictly partitioned by live financial balances (`approved_amount_cents`, `reserved_authorized_cents`, `net_paid_cents`). | `NEW-5a`, `NEW-5b`, `NEW-5c`, `NEW-5d`, `NEW-5e`, `A-2f-block`, `A-2f-part1`, `A-2f-state` | `PASS — EXECUTED` |
| **NEW-6** | **MEDIUM** | `is_canonical_json` accepts `NaN`/`Infinity` and does not enforce integer-only event payloads vs. float-permitting indicator snapshots | **YES** (`{"a":NaN}` returned `1`; float `420000.5` in event payload succeeded) | 1. Hardened `is_canonical_json` with `parse_constant` trap + `allow_nan=False` to reject `NaN`, `Infinity`, `-Infinity`, duplicate keys, and non-object roots while allowing finite canonical floats in `fraud_indicators.feature_snapshot_json`.<br>2. Added `WHEN EXISTS (SELECT 1 FROM json_tree(NEW.payload_json) WHERE type = 'real') THEN RAISE(ABORT, 'ERR_EVENT_PAYLOAD_FLOAT_FORBIDDEN')` to `trg_events_chain_insert`. | `NEW-6a`, `NEW-6b`, `NEW-6c`, `NEW-6d` | `PASS — EXECUTED` |
| **NEW-7** | **LOW** | `PAYMENT_CANCELLED` sample digest and `VH-1..VH-7` operational chain not verified in `verify_math.py` | **YES** (verified and reconciled) | Standardized the `PAYMENT_CANCELLED` sample payload digests (`874c6a8e6bb78a0855806688c6f882ca1f4de9dfd1d965fcc15a0f9b7d08ce83` for `PAY-2026-000002` `150000` and `14b3a52b35a0d83eab9e483fbe017c39fe173609589a627e084b632fc0024efe` for `PAY-2026-000002` `170000`) and added fail-closed `VH-1..VH-7` and `PAYMENT_CANCELLED` assertions to `archive/audit-harness/verify_math.py` and `test_delta_0102.py`. | `NEW-7a`, `VH-1..VH-7` in `verify_math.py` | `PASS — EXECUTED` |
| **NEW-8** | **MEDIUM** | Runtime mismatch (`Python 3.13.5 / SQLite 3.49.1` vs pinned `Python 3.10.12 / SQLite 3.40.1`) | **YES** (`010.1` reported `3.49.1`) | Executed all SQLite DDL, trigger, schema digest, and mathematical verification suites directly on **Python `3.10.12` / SQLite `3.40.1`** and recorded all outputs in `VERIFICATION_REPORT_0102.md`. | All harnesses (`verify_digest_0102.py`, `test_delta_0102.py`, `verify_math.py`, `verify_sql.py`) | `PASS — EXECUTED` |
| **NEW-9** | **LOW** | Working tree hygiene (`.playwright-cli/`, `bun.lock`) | **YES** | Verified clean working tree (`git status`) with no untracked browser or package lock artifacts before committing `fix/arch-st-010-2`. | `git status --short` | `PASS — EXECUTED` |

---

## Detailed Finding-by-Finding Reproduction & Resolution

### 1. `NEW-1` — Score Manipulation and `claims` `INSERT` Bypass (`CRITICAL`)

#### Exact Reproduction Against `ARCH-ST-010.1` (`ops_0101.sql` + `trigs_0101.sql` on SQLite `3.40.1`)
1. **`INSERT` bypass (`NEW-1a`/`NEW-1b`):**
   Executing `INSERT INTO claims (..., latest_ief_score, latest_risk_tier, scoring_evidence_sha256, siu_referred) VALUES (..., 99.99, 'CRITICAL', NULL, 1)` against `ARCH-ST-010.1` **succeeded** because `trg_claims_validate_ins` only checked `approved_amount_cents = 0` and `claim_status IN ('SUBMITTED','UNDER_REVIEW')`, and `trg_claims_score_upd` only fired on `BEFORE UPDATE`.
2. **Zero-indicator score fabrication (`NEW-1c`):**
   Executing `UPDATE claims SET latest_ief_score = 99.99, latest_risk_tier = 'CRITICAL', scoring_evidence_sha256 = sha256_hex('ST-SCORE-V1|CLM-2026-000001|IND_COUNT:0|IEF:99.99')` on a claim with **zero** `fraud_indicators` rows **succeeded** in `ARCH-ST-010.1`.
3. **Out-of-bounds score inflation (`NEW-1e`):**
   With `IND-03 (35.0, FINANCIAL)` and `IND-14 (12.0, BEHAVIORAL)` on `CLM-2026-000001`, the §9.4 Stage S4–S5 base score is:
   $$P_{\text{FIN}} = \frac{100 \times 35}{55} = 63.636364,\quad P_{\text{BEH}} = \frac{100 \times 12}{45} = 26.666667$$
   $$S_{\text{base}} = 0.30 \times 63.636364 + 0.20 \times 26.666667 = 19.090909 + 5.333333 = \mathbf{24.424242} \to \mathbf{24.42}\text{ (LOW)}$$
   Yet `ARCH-ST-010.1` §6.6 and `test_delta.py` (`C-6g`) wrote `30.76` (`MEDIUM`, which is the `IND-01 (20.0) + IND-03 (35.0)` base score from §9.6!) and `trg_claims_score_upd` **accepted** `30.76` (and even accepted `99.99`!) as long as the self-referential `|IEF:<score>` string was hashed into `scoring_evidence_sha256`.

#### Correction Implemented in `ARCH-ST-010.2`
1. **`trg_claims_validate_ins` (`trigs_0102.sql`):**
   Added mandatory initial-state checks:
   ```sql
   WHEN NEW.latest_ief_score != 0.0
        OR NEW.latest_risk_tier != 'LOW'
        OR NEW.scoring_evidence_sha256 IS NOT NULL
       THEN RAISE(ABORT, 'ERR_CLAIM_INITIAL_SCORE_STATE_INVALID')
   WHEN NEW.siu_referred != 0
       THEN RAISE(ABORT, 'ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO')
   ```
2. **`trg_claims_score_upd` (`trigs_0102.sql`):**
   Added database-side computation of the Stage S3–S5 deduplicated base score $S_{\text{base}}(c)$ (`GROUP BY pillar, indicator_code, canonical_evidence_token` taking `MAX(raw_points)`, normalized by pillar caps `60/55/45/40` and weighted by `0.35/0.30/0.20/0.15`) and the §9.4-S7 hard-collusion eligibility predicate (`EXISTS` another claim sharing both an `IND-01` token and an `IND-03` token):
   - When `IND_COUNT = 0` and `NEW.latest_ief_score != 0.0` $\to$ `RAISE(ABORT, 'ERR_SCORE_ZERO_INDICATORS_NONZERO_FORBIDDEN')`.
   - When `IND_COUNT > 0` and not hard-collusion eligible: enforces `NEW.latest_ief_score BETWEEN round(0.15 * S_base - 0.005, 2) AND round(S_base + 0.005, 2)` (`ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS`).
   - When `IND_COUNT > 0` and hard-collusion eligible: enforces `NEW.latest_ief_score BETWEEN MAX(65.0, round(S_base - 0.005, 2)) AND MIN(100.0, MAX(65.0, round(S_base + 20.0 + 0.005, 2)))` (`ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS`).
3. **Reconciled §6.6 Reference Vector:**
   Updated `ARCH-ST-010.2.md` §6.6 to use the true reconciled score `24.42` (`LOW`, digest `b00249984688081e409d3da5dd98a735147fa3b3803cb4d8c936581b92496227`) for `IND-03 (35.0) + IND-14 (12.0)`, while explicitly proving in test `NEW-1e` that `30.76` is rejected with `ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS`, and proving in test `C-7-sql` that `65.00` (`HIGH`) is accepted when the shared `(IND-01, IND-03)` hard-collusion pair is present.

---

### 2. `NEW-2` — `claims.siu_referred` Irreversibility and Workflow Gating (`HIGH`)

#### Exact Reproduction Against `ARCH-ST-010.1`
- Executing `UPDATE claims SET siu_referred = 0 WHERE claim_id = 'CLM-2026-000001'` after `SIU_HOLD` entry **succeeded** in `ARCH-ST-010.1` (`siu_referred` became `0`).
- Executing `UPDATE claims SET siu_referred = 1` on a normal `SUBMITTED` claim with no `SIU_HOLD` and no `CLOSED_CONFIRMED_FRAUD` investigation **succeeded** in `ARCH-ST-010.1`.
- Furthermore, in `ARCH-ST-010.1`'s `test_delta.py`, the investigation test ran on `CLM-2026-000001` whose `siu_referred` was *already* `1` from the earlier `SIU_HOLD` test, so `trg_investigations_siu_ref_au` was never tested on a claim with `siu_referred = 0`.

#### Correction Implemented in `ARCH-ST-010.2`
- `trg_claims_validate_ins` blocks `INSERT` with `NEW.siu_referred != 0` (`ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO`).
- `trg_claims_fsm_upd` blocks `OLD.siu_referred = 1 AND NEW.siu_referred = 0` (`ERR_CLAIM_SIU_REFERRED_IRREVERSIBLE`) and blocks `OLD.siu_referred = 0 AND NEW.siu_referred = 1` unless `NEW.claim_status = 'SIU_HOLD'` or `EXISTS (SELECT 1 FROM investigations i WHERE i.primary_claim_id = NEW.claim_id AND i.investigation_status = 'CLOSED_CONFIRMED_FRAUD')` (`ERR_CLAIM_SIU_REFERRAL_REQUIRES_HOLD_OR_CONFIRMED_FRAUD`).
- `test_delta_0102.py` (`C-6j-invg`) tests `trg_investigations_siu_ref_au` on a fresh second claim (`CLM-2026-000002`, `siu_referred = 0`) and verifies it flips `0 -> 1` when `INVG-2026-000001` closes as `CLOSED_CONFIRMED_FRAUD`.

---

### 3. `NEW-3` — False-Positive Test Reporting in `test_delta.py` (`CRITICAL`)

#### Exact Reproduction Against `ARCH-ST-010.1`
- In `archive/verify-0101/baseline_0101/test_delta.py`, `run_ok()` and `run_err()` printed `[FAIL]` on mismatch and returned `False`, but callers discarded the return value and the script ended without `sys.exit(1)`—exiting `0` even when tests failed.

#### Correction Implemented in `ARCH-ST-010.2`
- Replaced the passive functions with `TestRunner` in `archive/verify-0102/test_delta_0102.py` (and `archive/verify-0101/test_delta.py`):
  - Every `run_ok`, `run_err`, and `check_eq` increments `self.passed` or `self.failed`.
  - `run_err` requires a specific expected error substring (never bare `except Exception: pass`).
  - `finish()` exits with code `1` if `self.failed > 0`.
  - Added `--mutate-self-test` mode which deliberately executes 4 broken assertions (a failing positive test, an unblocked negative test, a wrong-error-code negative test, and a state mismatch) and verifies that `test_delta_0102.py --mutate-self-test` exits with code `1` (`SELF-00`).
  - Remarkably, running this fail-closed harness immediately caught a latent bug in `trg_edges_flow_upd` (`C-6c-ok` / `C-6d`) where valid edge deactivation fell through to `ELSE RAISE(ABORT, 'ERR_EDGE_MUTATION_INVALID')`, which we fixed in `trigs_0102.sql`!

---

### 4. `NEW-4` — `trg_edges_flow_upd` Dead Code and Timestamp Regression (`MEDIUM`)

#### Exact Reproduction Against `ARCH-ST-010.1`
- Executing `UPDATE relationship_edges SET last_observed_utc = '1999-01-01T00:00:00Z' WHERE edge_id = 'EDGE-2026-000001'` (when `first_observed_utc = '2026-01-05T09:00:00Z'` and `is_active = 1` remained unchanged) **succeeded** in `ARCH-ST-010.1` because `WHEN NEW.is_active = OLD.is_active THEN NULL` appeared *before* `WHEN NEW.last_observed_utc < OLD.last_observed_utc` (which was placed in unreachable dead code after `ELSE RAISE(ABORT, 'ERR_EDGE_MUTATION_INVALID')`).

#### Correction Implemented in `ARCH-ST-010.2`
- Reordered `trg_edges_flow_upd` (`trigs_0102.sql` lines 663–707) so `WHEN NEW.last_observed_utc < OLD.last_observed_utc THEN RAISE(ABORT, 'ERR_EDGE_OBSERVED_TIME_REGRESSION')` executes immediately after core-field immutability checks and before any `is_active` branch, added `WHEN NEW.is_active = 0 AND OLD.is_active = 1 THEN NULL` after the `RELATIONSHIP_EDGE_DEACTIVATED` event check, and removed all unreachable clauses after `ELSE`.

---

### 5. `NEW-5` — Incremental Clawback Event Gate & `SIU_HOLD` Benign Exit for Paid Claims (`HIGH`)

#### Exact Reproduction Against `ARCH-ST-010.1`
1. **Incremental clawback bypass:** After an initial partial clawback (`200000 -> 100000`) with a valid event, executing a second update `UPDATE payments SET clawed_back_cents = 200000, net_paid_cents = 0, reversed_at_utc = '2026-01-13T00:00:00Z'` (`REVERSED_CLAWBACK -> REVERSED_CLAWBACK`) with **no new event** **succeeded** in `ARCH-ST-010.1` because the `OLD.payment_status = 'REVERSED_CLAWBACK' AND NEW.payment_status = 'REVERSED_CLAWBACK'` branch had no `immutable_events` check.
2. **Benign `SIU_HOLD` exit deadlock for partially/fully paid claims:** A claim that entered `SIU_HOLD` while `PARTIALLY_PAID` (`net_paid_cents = 200000 > 0, approved_amount_cents = 370000`) and was cleared as benign could neither transition to `PARTIALLY_PAID` (`ERR_CLAIM_INVALID_FSM_TRANSITION` because `OLD.claim_status = 'SIU_HOLD'` only allowed `{'APPROVED','DENIED','CLOSED_NO_PAY'}`) nor transition to `APPROVED` (`ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH` because `net_paid_cents != 0`).

#### Correction Implemented in `ARCH-ST-010.2`
1. **Incremental clawback & latest-event enforcement (`trg_payments_validate_upd`):**
   - Added `e.sequence_no = (SELECT MAX(e2.sequence_no) FROM immutable_events e2 WHERE e2.entity_type = 'Payment' AND e2.entity_id = NEW.payment_id)` to every payment event gate (`AUTHORIZED -> DISBURSED`, `AUTHORIZED -> CANCELLED`, `DISBURSED -> REVERSED_CLAWBACK`, and `REVERSED_CLAWBACK -> REVERSED_CLAWBACK`).
   - Added the full `PAYMENT_CLAWBACK_REVERSED` payload digest check (`ERR_CLAWBACK_REQUIRES_EVENT`) to the incremental `OLD.payment_status = 'REVERSED_CLAWBACK' AND NEW.payment_status = 'REVERSED_CLAWBACK'` branch.
2. **Balance-partitioned `SIU_HOLD` exit (`trg_claims_fsm_upd`):**
   - Extended `OLD.claim_status = 'SIU_HOLD'` allowed target states to `('UNDER_REVIEW','APPROVED','PARTIALLY_PAID','PAID','DENIED','CLOSED_NO_PAY')`. Since `trg_claims_fsm_upd` enforces exact status-to-balance invariants on every target state (`UNDER_REVIEW` requires `approved=0, reserved=0, net=0`; `APPROVED` requires `approved>0, net=0`; `PARTIALLY_PAID` requires `0 < net < approved`; `PAID` requires `approved>0, net=approved, reserved=0`), each benign held claim transitions back to the unique workflow state matching its actual financial balances.

---

### 6. `NEW-6` — `is_canonical_json` Hardening & Split Numeric Policy (`MEDIUM`)

#### Exact Reproduction Against `ARCH-ST-010.1`
- `is_canonical_json('{"a":NaN}')` and `is_canonical_json('{"a":Infinity}')` returned `1` in `ARCH-ST-010.1` because Python's `json.loads` and `json.dumps` default to `allow_nan=True`.
- `is_canonical_json('{"amount_cents":420000.5}')` returned `1` and was accepted into `immutable_events.payload_json` despite §6.5 stating event payloads are integers only.

#### Correction Implemented in `ARCH-ST-010.2`
- Updated `is_canonical_json` in `ARCH-ST-010.2.md` (§6.5), `verify_digest_0102.py`, `test_delta_0102.py`, and `verify_math.py` with `parse_constant=_reject_constants` and `allow_nan=False`, plus `object_pairs_hook=_reject_duplicates` and `isinstance(obj, dict)`.
- Added `WHEN EXISTS (SELECT 1 FROM json_tree(NEW.payload_json) WHERE type = 'real') THEN RAISE(ABORT, 'ERR_EVENT_PAYLOAD_FLOAT_FORBIDDEN')` to `trg_events_chain_insert` (`trigs_0102.sql`), enforcing integer-only numbers in `immutable_events.payload_json` inside SQLite while preserving finite canonical float support in `fraud_indicators.feature_snapshot_json`.

---

### 7. `NEW-7` — `PAYMENT_CANCELLED` Digest & `VH-1..VH-7` Verification (`LOW`)

#### Exact Reproduction & Resolution in `ARCH-ST-010.2`
- Added full verification of all 7 operational history vectors (`VH-1..VH-7`, both `payload_sha256` and `event_hash`) and both `PAYMENT_CANCELLED` sample payloads (`170000` -> `14b3a52b35a0d83eab9e483fbe017c39fe173609589a627e084b632fc0024efe`, `150000` -> `874c6a8e6bb78a0855806688c6f882ca1f4de9dfd1d965fcc15a0f9b7d08ce83`) to `archive/audit-harness/verify_math.py` and `archive/verify-0102/test_delta_0102.py` (`NEW-7a`).

---

### 8. `NEW-8` & `NEW-9` — Pinned Runtime Execution & Working Tree Hygiene (`MEDIUM` / `LOW`)

- Executed all verification scripts on **Python `3.10.12` / SQLite `3.40.1`** (`VERIFICATION_REPORT_0102.md`).
- Cleaned working tree so no `.playwright-cli/` or `bun.lock` artifacts exist (`git status`).

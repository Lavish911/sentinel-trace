# VERIFICATION REPORT — `SENTINEL//TRACE` `ARCH-ST-010.2`

- **Repository:** `Lavish911/sentinel-trace`
- **Branch:** `fix/arch-st-010-2` (branched from `audit/arch-st-010` at commit `44f5b67`)
- **Primary Specification:** `ARCH-ST-010.2.md`
- **Execution Date (UTC):** `2026-11-01`

---

## 1. Executed Runtime Environment (`NEW-8` Verified on Exact Pin)

All verification suites were executed directly on the pinned runtime required by `ARCH-ST-010.2.md` §2.1:

```text
$ python3 -c "import sys, sqlite3, platform; print('Python:', sys.version); print('SQLite:', sqlite3.sqlite_version); print('Platform:', platform.platform())"
Python: 3.10.12 (main, Mar  3 2026, 11:56:32) [GCC 11.4.0]
SQLite: 3.40.1
Platform: Linux-6.6.137+-x86_64-with-glibc2.35
```

- **Registered SQLite UDFs (`deterministic=True`):** `sha256_hex(s: str) -> str`, `is_canonical_json(s: str) -> int`
- **Connection Pragmas:** `PRAGMA foreign_keys = ON; PRAGMA recursive_triggers = ON; PRAGMA trusted_schema = ON;`

---

## 2. Summary of Executed Verification Suites

| Suite / Command | Scope | Pass / Fail / Total | Exit Code | Status |
|---|---|---:|---:|---|
| `python3 archive/verify-0102/verify_digest_0102.py` | `ST-SCHEMA-V1` digest (`26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a`), 12 tables + 24 triggers (`36` objects), forward/reverse DDL order independence, SQLite↔Python serializer mirror | **4 / 0 / 4** | `0` | `PASS — EXECUTED` |
| `python3 archive/verify-0102/verify_digest_0102.py --mutate-self-test` | Deliberate digest mismatch fail-closed check | **1 / 0 / 1** | `1` (expected) | `PASS — EXECUTED` |
| `python3 archive/verify-0102/test_delta_0102.py` | Full fail-closed acceptance & adversarial SQL/trigger/UDF/scoring test suite (`C-1..C-7`, `A-1..A-5`, `NEW-1..NEW-8`, plus `SELF-00` subprocess mutation check) | **77 / 0 / 77** | `0` | `PASS — EXECUTED` |
| `python3 archive/verify-0102/test_delta_0102.py --mutate-self-test` | Deliberate 4-case positive/negative/error-code/state mutation fail-closed check | **4 failures caught** | `1` (expected) | `PASS — EXECUTED` |
| `python3 archive/audit-harness/verify_math.py` | `KAV-1..7` payload & event hashes, `VH-1..VH-7` operational chain hashes, `PAYMENT_CANCELLED` (`170000` & `150000`) hashes, `FP-1`, 8-node PageRank ($t=78$, $\widetilde{\text{PR}}$), 10-stage Clean-Room scoring (`[65.0, 65.0, 0.0, 0.67]`) | **30 / 0 / 30** | `0` | `PASS — EXECUTED` |
| `python3 archive/audit-harness/verify_sql.py` | Legacy `ARCH-ST-010` 16-trigger baseline regression suite (`TEST A` .. `TEST N`) | **30 / 0 / 30** | `0` | `PASS — EXECUTED` |

---

## 3. Exact Output of `verify_digest_0102.py`

```text
$ python3 archive/verify-0102/verify_digest_0102.py
objects: tables=12 triggers=24 (expected 12 + 24: OK)
computed digest       : 26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a
order-independent     : True
matches §6.3 constant : True (26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a)
python mirror matches : True | rows serialized: 36
[PASS] All 4 digest verification checks passed (fail-closed).
```

---

## 4. Complete Assertion Ledger of `test_delta_0102.py` (77/77 Executed on Python `3.10.12` / SQLite `3.40.1`)

| # | Test ID | Description | Expected Outcome / Error Code | Result |
|---:|---|---|---|---|
| 1 | `SELF-00` | Subprocess `--mutate-self-test` fail-closed verification | Exits with code `1` on 4 deliberate mutations | `PASS` |
| 2 | `V-00` | SQL fences in `ARCH-ST-010.2.md` (§5.1, §5.2) match `ops_0102.sql` and `trigs_0102.sql` byte-for-byte | `(5, True, True)` | `PASS` |
| 3 | `V-01` | Operational schema builds 12 `STRICT` tables and 24 triggers | `(12, 24)` | `PASS` |
| 4 | `SEED-01` | Insert claimant `CLMT-000001` | Accepted | `PASS` |
| 5 | `SEED-02` | Insert claimant `CLMT-000002` | Accepted | `PASS` |
| 6 | `SEED-03` | Insert provider `PRV-000001` | Accepted | `PASS` |
| 7 | `SEED-04` | Insert policy `POL-2026-000001` | Accepted | `PASS` |
| 8 | `SEED-05` | Insert policy `POL-2026-000002` | Accepted | `PASS` |
| 9 | `SEED-06` | Insert incident `INC-2026-000001` | Accepted | `PASS` |
| 10 | `NEW-1a` | Reject claim `INSERT` with pre-populated nonzero score / `CRITICAL` tier | `ERR_CLAIM_INITIAL_SCORE_STATE_INVALID` | `PASS` |
| 11 | `NEW-1b` | Reject claim `INSERT` with pre-populated `scoring_evidence_sha256` | `ERR_CLAIM_INITIAL_SCORE_STATE_INVALID` | `PASS` |
| 12 | `NEW-2a` | Reject claim `INSERT` with initial `siu_referred = 1` | `ERR_CLAIM_INITIAL_SIU_REFERRED_MUST_BE_ZERO` | `PASS` |
| 13 | `SEED-07` | Insert valid claim `CLM-2026-000001` | Accepted | `PASS` |
| 14 | `SEED-08` | Insert valid invoice `INV-PRV-PRV-000001-000001` | Accepted | `PASS` |
| 15 | `C-1a` | Approve invoice at `370000` while claim is `SUBMITTED` | Accepted | `PASS` |
| 16 | `C-1a-state` | Claim cascades to `APPROVED` with `370000` `approved_amount_cents` and `historical_approved_cents` | `('APPROVED', 370000, 370000, 0)` | `PASS` |
| 17 | `SEED-09` | Insert second claim `CLM-2026-000002` | Accepted | `PASS` |
| 18 | `C-1b` | Block direct claim `APPROVED` update without approved invoice | `ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH` | `PASS` |
| 19 | `PAY-01` | Authorize `PAY-2026-000001` (`200000`) | Accepted | `PASS` |
| 20 | `PAY-02` | Authorize `PAY-2026-000002` (`170000`) | Accepted | `PASS` |
| 21 | `A-2a` | Block disbursement of `PAY-2026-000001` without `PAYMENT_AUTHORIZED` event | `ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT` | `PASS` |
| 22 | `EV-1` | Emit `PAYMENT_AUTHORIZED` event (`seq=1`) | Accepted | `PASS` |
| 23 | `A-2b` | Disburse `PAY-2026-000001` with matching `PAYMENT_AUTHORIZED` event | Accepted | `PASS` |
| 24 | `A-2b-state` | Claim transitions to `PARTIALLY_PAID` with `net_paid=200000`, `reserved=170000` | `('PARTIALLY_PAID', 200000, 170000)` | `PASS` |
| 25 | `A-1a` | Place `PARTIALLY_PAID` claim `CLM-2026-000001` onto `SIU_HOLD` | Accepted | `PASS` |
| 26 | `C-6j-hold` | Entering `SIU_HOLD` automatically flips `claims.siu_referred` from `0` to `1` | `('SIU_HOLD', 1, 170000)` | `PASS` |
| 27 | `NEW-2b` | Block resetting `claims.siu_referred` from `1` back to `0` | `ERR_CLAIM_SIU_REFERRED_IRREVERSIBLE` | `PASS` |
| 28 | `A-2c` | Block disbursement of `PAY-2026-000002` while claim is on `SIU_HOLD` | `ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL` | `PASS` |
| 29 | `A-2d-reason` | Block payment cancellation without `cancel_reason` | `ERR_PAYMENT_CANCELLATION_REQUIRES_REASON` | `PASS` |
| 30 | `A-2d-event` | Block payment cancellation without `PAYMENT_CANCELLED` event | `ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT` | `PASS` |
| 31 | `NEW-7a` | `PAYMENT_CANCELLED` (`170000`) payload digest matches `14b3a52b35a0d83eab9e483fbe017c39fe173609589a627e084b632fc0024efe` | Exact match | `PASS` |
| 32 | `EV-2` | Emit `PAYMENT_CANCELLED` event (`seq=2`) | Accepted | `PASS` |
| 33 | `A-2e` | Cancel `PAY-2026-000002` with matching `PAYMENT_CANCELLED` event and `cancel_reason` | Accepted | `PASS` |
| 34 | `A-2e-state` | Cancellation releases reservation (`reserved_authorized_cents=0, net_paid_cents=200000`) | `('SIU_HOLD', 0, 200000, 1)` | `PASS` |
| 35 | `NEW-5a` | Block `SIU_HOLD -> APPROVED` when `net_paid_cents > 0` | `ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH` | `PASS` |
| 36 | `NEW-5b` | Allow `SIU_HOLD -> PARTIALLY_PAID` when partially-paid claim is cleared as benign without clawback | Accepted | `PASS` |
| 37 | `NEW-5c` | Return `CLM-2026-000001` to `SIU_HOLD` for confirmed-fraud clawback test | Accepted | `PASS` |
| 38 | `A-2f-block` | Block initial clawback on `PAY-2026-000001` without `PAYMENT_CLAWBACK_REVERSED` event | `ERR_CLAWBACK_REQUIRES_EVENT` | `PASS` |
| 39 | `EV-3` | Emit partial `PAYMENT_CLAWBACK_REVERSED` event (`100000`, `seq=3`) | Accepted | `PASS` |
| 40 | `A-2f-part1` | Execute partial clawback (`100000`) with matching `PAYMENT_CLAWBACK_REVERSED` event | Accepted | `PASS` |
| 41 | `NEW-5d` | Block incremental clawback (`REVERSED_CLAWBACK -> REVERSED_CLAWBACK`) without fresh event | `ERR_CLAWBACK_REQUIRES_EVENT` | `PASS` |
| 42 | `EV-4` | Emit full `PAYMENT_CLAWBACK_REVERSED` event (`200000`, `seq=4`) | Accepted | `PASS` |
| 43 | `NEW-5e` | Execute incremental clawback to `200000` with fresh `PAYMENT_CLAWBACK_REVERSED` event | Accepted | `PASS` |
| 44 | `A-2f-state` | Post-clawback claim balances preserve `historical_approved_cents=370000` with `net_paid_cents=0` | `('SIU_HOLD', 0, 0, 370000)` | `PASS` |
| 45 | `C-6b-self` | Reject self-edge where `canonical_src_key == canonical_dst_key` | `CHECK constraint failed: canonical_src_key < canonical_dst_key` | `PASS` |
| 46 | `C-6b-order` | Reject reversed edge where `canonical_src_key > canonical_dst_key` | `CHECK constraint failed: canonical_src_key < canonical_dst_key` | `PASS` |
| 47 | `SEED-10` | Insert valid relationship edge `EDGE-2026-000001` | Accepted | `PASS` |
| 48 | `C-6b-strength` | Reject edge `strength_weight` mutation | `ERR_EDGE_CORE_FIELDS_IMMUTABLE` | `PASS` |
| 49 | `C-6b-endpoint` | Reject edge endpoint/key mutation | `ERR_EDGE_CORE_FIELDS_IMMUTABLE` | `PASS` |
| 50 | `NEW-4a` | Reject edge `last_observed_utc` regression while `is_active` remains unchanged | `ERR_EDGE_OBSERVED_TIME_REGRESSION` | `PASS` |
| 51 | `NEW-4b` | Allow valid edge `last_observed_utc` advancement while `is_active` remains unchanged | Accepted | `PASS` |
| 52 | `C-6c` | Reject silent edge deactivation without `RELATIONSHIP_EDGE_DEACTIVATED` event | `ERR_EDGE_DEACTIVATION_REQUIRES_EVENT` | `PASS` |
| 53 | `EV-5` | Emit `RELATIONSHIP_EDGE_DEACTIVATED` event (`seq=5`) | Accepted | `PASS` |
| 54 | `C-6c-ok` | Deactivate `EDGE-2026-000001` with matching `RELATIONSHIP_EDGE_DEACTIVATED` event | Accepted | `PASS` |
| 55 | `C-6d` | Reject edge reactivation (`is_active 0 -> 1`) | `ERR_EDGE_REACTIVATION_FORBIDDEN` | `PASS` |
| 56 | `C-6e` | Reject `DELETE FROM relationship_edges` | `ERR_EDGE_DELETE_FORBIDDEN` | `PASS` |
| 57 | `SEED-11` | Insert indicator `FIND-2026-000001` (`IND-03`, `35.0`) on `CLM-2026-000001` | Accepted | `PASS` |
| 58 | `C-6f-upd` | Reject `UPDATE` on `fraud_indicators` | `ERR_FRAUD_INDICATOR_MUTATION_FORBIDDEN` | `PASS` |
| 59 | `C-6f-del` | Reject `DELETE` on `fraud_indicators` | `ERR_FRAUD_INDICATOR_DELETE_FORBIDDEN` | `PASS` |
| 60 | `NEW-6a` | Insert indicator `FIND-2026-000002` (`IND-14`, `12.0`) with finite canonical float in `feature_snapshot_json` | Accepted | `PASS` |
| 61 | `NEW-6b` | `is_canonical_json` rejects `NaN`, `Infinity`, `-Infinity`, duplicate keys, unsorted keys, whitespace, ASCII-escaped UTF-8, non-dict root | `[0, 0, 0, 0, 0, 0, 0, 0, 0]` | `PASS` |
| 62 | `NEW-6c` | `is_canonical_json` accepts canonical integer, finite float, and raw UTF-8 Unicode objects | `[1, 1, 1]` | `PASS` |
| 63 | `NEW-6d` | Reject float numeric value inside `immutable_events.payload_json` | `ERR_EVENT_PAYLOAD_FLOAT_FORBIDDEN` | `PASS` |
| 64 | `NEW-2c` | Block direct fabrication of `siu_referred=1` on fresh claim `CLM-2026-000002` | `ERR_CLAIM_SIU_REFERRAL_REQUIRES_HOLD_OR_CONFIRMED_FRAUD` | `PASS` |
| 65 | `SEED-12` | Insert investigation `INVG-2026-000001` on fresh claim `CLM-2026-000002` (`siu_referred=0`) | Accepted | `PASS` |
| 66 | `C-6a-del` | Reject `DELETE FROM investigations` | `ERR_INVESTIGATION_DELETE_FORBIDDEN` | `PASS` |
| 67 | `INVG-01` | Advance investigation to `EVIDENCE_COLLECTION` | Accepted | `PASS` |
| 68 | `INVG-02` | Advance investigation to `SIU_FIELD_REVIEW` | Accepted | `PASS` |
| 69 | `INVG-03` | Close investigation as `CLOSED_CONFIRMED_FRAUD` | Accepted | `PASS` |
| 70 | `C-6j-invg` | Closing investigation as `CLOSED_CONFIRMED_FRAUD` flips fresh claim `CLM-2026-000002` `siu_referred` `0 -> 1` | `1` | `PASS` |
| 71 | `C-6a-closed` | Reject mutation of closed investigation | `ERR_CLOSED_INVESTIGATION_IMMUTABLE` | `PASS` |
| 72 | `NEW-1c` | Block assigning nonzero score (`99.99`) to claim with `0` `fraud_indicators` | `ERR_SCORE_ZERO_INDICATORS_NONZERO_FORBIDDEN` | `PASS` |
| 73 | `NEW-1d` | Accept `0.00` `LOW` score with valid `ST-SCORE-V1` digest on `0`-indicator claim | Accepted | `PASS` |
| 74 | `NEW-1e` | Block out-of-bounds score `30.76` on `CLM-2026-000001` (`IND-03 + IND-14` has max $S_{\text{base}} = 24.42$) | `ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS` | `PASS` |
| 75 | `NEW-1f` | Block zeroing score (`0.00`) on `CLM-2026-000001` when indicators are present | `ERR_SCORE_OUTSIDE_INDICATOR_BOUNDS` | `PASS` |
| 76 | `C-6g..i` / `C-7-sql` | Accept reconciled score `24.42` (`LOW`) with digest `b0024998…`; reject wrong tier (`ERR_SCORE_TIER_MISMATCH`) & wrong digest (`ERR_SCORE_EVIDENCE_DIGEST_MISMATCH`); accept hard-collusion floor `65.00` (`HIGH`) with shared `(IND-01, IND-03)` pair | Accepted / Blocked as specified | `PASS` |

---

## 5. Unexecuted Application & Seed-Generator Items (Honest Disclosure)

- **`T-01..T-20` (Full `seed=42` 5,000-claim dataset generation and FastAPI/React endpoints):** Remain **`SPECIFIED — NOT EXECUTED`** because this task is strictly scoped to the `ARCH-ST-010.2` architecture specification, SQLite schema/trigger baseline, and verification harnesses.

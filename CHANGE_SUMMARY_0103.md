# CHANGE SUMMARY — ARCH-ST-010.3 / ARCH-ST-010.5 REMEDIATION

**Document ID:** `CHANGE-SUMMARY-0103`
**Branch:** `fix/arch-st-010-5-remediation` (base commit `2c8cc40a36e770da9d63f1ebf14c25158dc1d7f3` = verified `fix/arch-st-010-3` upstream commit; `main` untouched, no merge/deploy).
**Scope:** all confirmed defects `D-1..D-10`, `DEF-01..DEF-03`, and `CRITICAL-01`, `HIGH-01`, `HIGH-02`, `MEDIUM-01`, `MEDIUM-02`, `LOW-01`.

---

## 1. SQL changes (shipped, schema digest recomputed)

| Change | File | Effect |
|---|---|---|
| **D-1 / DEF-01 / HIGH-02**: cycle-aware benign-exit gate inside `trg_claims_fsm_upd` + `trg_claims_siu_referred_au` | `archive/verify-0103/trigs_0103.sql` | `trg_claims_siu_referred_au` increments `siu_referred` to `MAX(OLD.siu_referred, 1, COUNT(CLOSED_CLEARED_BENIGN) + 1)` on each `SIU_HOLD` entry. `SIU_HOLD -> UNDER_REVIEW/APPROVED/PARTIALLY_PAID/PAID` requires `COUNT(CLOSED_CLEARED_BENIGN) >= MAX(1, NEW.siu_referred)`, zero open or `CLOSED_CONFIRMED_FRAUD` investigations on the claim, and the latest closed investigation (`ORDER BY closed_at_utc DESC, updated_at_utc DESC, investigation_id DESC`) being `CLOSED_CLEARED_BENIGN`. |
| **DEF-02 / HIGH-02**: investigation timestamp & state hardening | `archive/verify-0103/ops_0103.sql`, `archive/verify-0103/trigs_0103.sql` | `investigations` `CHECK` enforces 1-to-1 `investigation_status <-> ruling_outcome` and `closed_at_utc >= updated_at_utc`. `trg_investigations_validate_ins` enforces `OPEN` initial status, zero initial clawback, and anti-backdating against existing investigations on the claim. `trg_investigations_fsm_upd` enforces core-field immutability, `closed_at_utc = updated_at_utc` on closure, and anti-backdating against other investigations on the same claim. |
| **DEF-03**: post-approval policy lapse scope | `archive/verify-0103/trigs_0103.sql` | `trg_invoices_fsm_upd` scopes the `policy_status = 'ACTIVE'` check to initial invoice approval (`SUBMITTED/UNDER_REVIEW -> APPROVED`) and approved-amount adjustments, allowing payment disbursement/clawback sync on already-approved invoices if the policy later lapses. |
| **D-6**: two `ingestion_exceptions` append-only triggers | `archive/verify-0103/trigs_0103.sql` | `trg_ingestion_exceptions_block_upd` (`ERR_INGESTION_EXCEPTION_IMMUTABLE`) and `trg_ingestion_exceptions_block_del` (`ERR_INGESTION_EXCEPTION_DELETE_FORBIDDEN`). |
| Trigger count | — | 24 (010.2) → 26 (010.3 base) → **27** (with `trg_investigations_validate_ins`); 12 tables unchanged (39 schema objects). |
| **`ST-SCHEMA-V1` schema digest (§6.3, recomputed)** | both files | **`7d2b5f6874ef3e0458bd13b3909d9832a8248c6799d945fc7ab209e7beb25e0c`** (forward == reverse DDL order == Python mirror; 39 objects). |

## 2. Database Engine, Seed Generator & Test Suite (`db/`)

| Asset | Change |
|---|---|
| `db/engine.py` | Connection factory enforcing `PRAGMA foreign_keys=ON; trusted_schema=ON; recursive_triggers=ON`, registering `sha256_hex` and `is_canonical_json` UDFs, and verifying `EXPECTED_SCHEMA_DIGEST = 7d2b5f6874ef3e0458bd13b3909d9832a8248c6799d945fc7ab209e7beb25e0c`. |
| `db/seed.py` | Deterministic seed generator (`seed=42` and arbitrary seeds). **`CRITICAL-01`**: implements standalone `derive_operational_indicators_and_scores(conn)` operating solely on `operational.db` with zero `RING-2026-*` tokens, zero orphan `BANK:`/`DUP_FP:` tokens, and varied operational scores across ring claims. **`HIGH-01`**: all 25 `YF-NEG-3` claims (`751..775`) have cross-claim, cross-claimant `REJECTED_DUPLICATE` invoices. **`MEDIUM-01`**: emits `22` `INVESTIGATION_STATUS_CHANGED`, `30` `INVESTIGATION_CLOSED`, and `8` post-hold `CLAIM_APPROVED` release events (`19,675` total events across 15 buckets). |
| `db/test_suite.py` | 20-check acceptance test suite (`T-01..T-20`) verifying schema digest, FK integrity, physical & logical ground-truth isolation (`CRITICAL-01`), entity counts, multi-seed determinism, 15-bucket event reconciliation (`19,675` events, `MEDIUM-01`), full `ST-EVT-V2` hash chain, penny-level financial reconciliation, `YF-NEG-1..5`, `BL-1..5`, `EC-1..3`, cross-claimant duplicate invoices (`HIGH-01`), and `SIU_HOLD`/investigation lifecycle guards (`DEF-01..03`, `HIGH-02`). |

## 3. Verification assets (`archive/verify-0103/`)

| Asset | Change |
|---|---|
| `test_delta_0103.py` | **149/0/149 ordinary + 3/0 integration + 1 subprocess check**; removed dead `if False else None` line (`LOW-01`); added `HIGH-02` regression checks (`HIGH-02-bopen`, `HIGH-02-bclose1`, `HIGH-02-bclose2`, `HIGH-02-cycle-ref`, `HIGH-02-cycle-reuse`, `HIGH-02-cycle-open-blk`, `HIGH-02-cycle-ok`, `HIGH-02-c3-ref`, `HIGH-02-c3-blk`, `HIGH-02-c3-ok`). |
| `verify_digest_0103.py` | 6 fail-closed checks verifying `7d2b5f6874ef3e0458bd13b3909d9832a8248c6799d945fc7ab209e7beb25e0c` across 12 tables + 27 triggers (39 objects); `--mutate-self-test` exit `1`. |

## 4. File SHA-256 (at commit)

| File | SHA-256 |
|---|---|
| `ARCH-ST-010.3.md` | `a2dc53ffbbb8b880343de631d5a6857d6447d169d71f28629ca40a505807cb76` |
| `archive/verify-0103/ops_0103.sql` | `a9d17b261908e039d2189225f211f9d08bbb20c8789854486eafc1a6a3ec2c4f` |
| `archive/verify-0103/trigs_0103.sql` | `f200a0b81e21d98845249cbad7d351a7891e604cb0936d822252fb20bb398d0a` |
| `archive/verify-0103/test_delta_0103.py` | `fcf58c828d638bc2e2707417fddb435a57ec985ccf4012562fd0e41b63c67a75` |
| `archive/verify-0103/verify_digest_0103.py` | `53a158fbfc52bc4dec8623fdb35f7f7b65eb9a60a2e5fce958925e1a24633020` |
| `archive/verify-0103/README.md` | `e647886a8895aa2d579000c639772c283a9ce579a558e3569119a133a0240e78` |
| `db/engine.py` | `dac314e2e2137c5b8df3371f5232686322ccf49fc38c3b0f1d8bf4f3e3ee32f9` |
| `db/seed.py` | `0fa0bfc026c81f9839d0754a5c33e8f3ccbf224ddae50f42144fecc53319d121` |
| `db/test_suite.py` | `16477c5def1e296990a7f9d498923431e2b2cd9b17aea20125a1d72f66a73ad2` |


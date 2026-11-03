# VERIFICATION REPORT — ARCH-ST-010.3 / ARCH-ST-010.5 REMEDIATION

**Document ID:** `VERIFICATION-REPORT-0103`
**Candidate:** `ARCH-ST-010.5` remediation on `ARCH-ST-010.3` baseline (`D-1..D-10`, `DEF-01..DEF-03`, `CRITICAL-01`, `HIGH-01`, `HIGH-02`, `MEDIUM-01`, `MEDIUM-02`, `LOW-01`)
**Branch:** `fix/arch-st-010-5-remediation` — branched from verified upstream `fix/arch-st-010-3` commit `2c8cc40a36e770da9d63f1ebf14c25158dc1d7f3` (which descends from `main` tip `8e513348e25a923183414f6fd7b3a9844cb91f7f`). `main` and `fix/arch-st-010-3` untouched. No merge / no deploy.

---

## 1. Executed environment (honest disclosure)

| Role | Python | SQLite (`sqlite3.sqlite_version`) | Source of truth |
|---|---|---|---|
| Primary | `3.10.11` | `3.40.1` | machine probe (`sys.version`, `sqlite3.sqlite_version`) |
| Cross-version control | `3.13.5` | `3.49.1` | machine probe — identical assertion counts required and observed |

All databases are freshly built per run: `PRAGMA foreign_keys=ON; recursive_triggers=ON; trusted_schema=ON`, UDFs `sha256_hex` / `is_canonical_json` registered per spec §2.1.

## 2. Executed results (counts taken only from runner output)

### 2.1 Delta harness — `archive/verify-0103/test_delta_0103.py`

| Category | Primary (3.10.11 / 3.40.1) | Cross (3.13.5 / 3.49.1) | Exit code |
|---|---|---|---|
| Ordinary assertions | **149 passed / 0 failed / 149 total** | identical (149/0/149) | `0` |
| Trigger-mutation / integration checks (`MUT-NEW5-ctrl2`, `MUT-NEW5-strip`, `MUT-NEW5-a`) | **3 passed / 0 failed** | identical (3/0) | (same run) |
| Subprocess checks | **1** (`SELF-00`: fresh-interpreter `--mutate-self-test` must exit non-zero — observed exit `1`) | identical | (same run) |
| `--mutate-self-test` (fail-closed proof) | deliberate mutation mode → **exit `1`** | identical | `1` |
| Runner fail-closed self-test | 4 deliberate mutations (`MUT-1..MUT-4`) printed as `[FAIL]` — verified **caught** (internal runner self-test counts: passed=0 / failed=4); the runner cannot accidentally accept them | identical | (part of exit `0`) |

Schema/fence baseline asserts (category: ordinary):
- `V-00`: `ARCH-ST-010.3.md` contains exactly **5** SQL fences; fence[1] == `ops_0103.sql` and fence[2] == `trigs_0103.sql` byte-for-byte (scope: §2.1 / §5.1 / §5.2 convention) → `(5, True, True)`.
- `V-01`: operational build creates **12 STRICT tables and 27 triggers** (39 objects).
- `V-02`: `ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE` present in shipped `trigs_0103.sql` **and** in the spec §5.2 fence.

### 2.2 Trust-boundary demonstration (`D-2`) — classified as BOUNDARY, not a security pass

`TRB-1..TRB-3` demonstrate that an authorized raw-SQL writer can plant the hard-collusion pair (`IND-01`/`IND-03` shared tokens) and write a self-consistent `65.00 HIGH` score — **accepted, by design**. This acceptance is a documented boundary demonstration (~§6.6): `ST-SCORE-V1` is an unkeyed consistency digest, not provenance authentication.

### 2.3 Schema digest — `archive/verify-0103/verify_digest_0103.py`

```
objects: tables=12 triggers=27 (expected 12 + 27: OK)
computed digest       : 7d2b5f6874ef3e0458bd13b3909d9832a8248c6799d945fc7ab209e7beb25e0c
order-independent     : True
matches §6.3 constant : True
D-1 gate published    : True | stripped clause removes all gate occurrences: True
python mirror matches : True | rows serialized: 39
[PASS] All 6 digest verification checks passed (fail-closed).
```

| Check | Primary | Cross |
|---|---|---|
| 6 digest checks (shape, fence identity, order-independence forward↔reverse DDL, §6.3 constant, publication, Python mirror) | `PASS` (exit `0`) | `PASS` (exit `0`) |
| `--mutate-self-test` | exit `1` | exit `1` |

`ST-SCHEMA-V1` operational digest: **`7d2b5f6874ef3e0458bd13b3909d9832a8248c6799d945fc7ab209e7beb25e0c`** (39 objects = 12 tables + 27 triggers).

### 2.4 Engine / math — `archive/audit-harness/verify_math.py`

`[PASS] All mathematical vectors (KAV-1..7, VH-1..7, PAYMENT_CANCELLED, FP-1, PageRank, 10-Stage Scoring) verified (33/33 checks passed).`

### 2.5 Full-Seed Database Generation & Acceptance Suite (`db/seed.py` & `db/test_suite.py`)

- `python3 -m db.seed 42` → exit `0`:
  - `ST-SCHEMA-V1 digest` : `7d2b5f6874ef3e0458bd13b3909d9832a8248c6799d945fc7ab209e7beb25e0c`
  - `operational.db SHA256`: `40fd524918534b930b1b572dcc78990fb031ae53d9100f382ed7c0f7a0c50065`
  - `ground_truth.db SHA256`: `6c6429cc43d680cf3f4695d8c8b1121be40621dd1b4471369250757a841c6d61`
  - Exact entity counts: `claimants=2,000`, `policies=2,200`, `incidents=3,800`, `claims=5,000`, `providers=500`, `invoices=7,500`, `payments=4,200`, `relationship_edges=8,000`, `fraud_indicators=4,120`, `investigations=45`, `immutable_events=19,675`, `ingestion_exceptions=25`, `ground_truth_rings=20`, `ground_truth_claim_labels=5,000`, `ground_truth_entity_labels=2,500`, `ground_truth_missing_edges=25`.
- `python3 -m db.test_suite` → exit `0` (**20 passed, 0 failed out of 20**, `T-01..T-20`).

### 2.6 Historical SQL integrity suites

`archive/audit-harness/verify_sql.py` and `verify_sql2.py` — `ALL DONE` (010 / 010.2 lineage fully intact).

### 2.7 Key digest vectors re-derived (D-3 / D-4)

| Vector | Value | Derivation |
|---|---|---|
| `PAYMENT_CANCELLED` canonical payload (170000, `SIU_HOLD_RESERVATION_CLEARED`) | `14b3a52b35a0d83eab9e483fbe017c39fe173609589a627e084b632fc0024efe` | recomputed by generator AND harness (`NEW-7a`) |
| `PAYMENT_CANCELLED` 150000 payload (correction evidence) | `e586f6b192e8322a58b80f66335b64b6c37cfb03672124ef245f89814de44911` | recomputed (`NEW-7b`; retracted `874c6a8e…` asserted not derivable) |
| `ST-SCORE-V1` normative reference preimage (both norms `1.000`) | `2632d91521dda9907a3a3fd475396372f5a348769d8b69b597c041dd6e179718` | recomputed (`D-4b`; retracted `b0024998…` asserted nowhere) |
| `ST-SCORE-V1` live DB-state preimage (norm rendered `0.750`) | `4a8b6c91ae02a168d2999144c561801bc0a1b6a30f1ab92c2adfa0ab58ce1efc` | recomputed (`D-4a`; equals the digest accepted in `C-6g`) |

## 3. Fail-closed properties demonstrated

1. Any assertion failure → harness exit non-zero (`SELF-00` proves mutation mode exits `1` from a fresh interpreter).
2. `--mutate-self-test` on both `test_delta_0103.py` and `verify_digest_0103.py` exits `1`.
3. The D-1 causality proof: removing the gate clause from the trigger text makes the previously-blocked exit succeed (`MUT-NEW5-a`).
4. Physical and logical ground-truth isolation (`CRITICAL-01`): zero `ground_truth_*` tables, zero `RING-2026-*` strings, zero orphan `BANK:`/`DUP_FP:` tokens in `operational.db`, and standalone `derive_operational_indicators_and_scores(conn)` operating solely on `operational.db`.

## 4. Deliverable integrity (SHA-256, recomputed at commit staging)

| File | Role |
|---|---|
| `ARCH-ST-010.3.md` | candidate specification (5 fences byte-identical to shipped SQL; §11 populated from executed results) |
| `archive/verify-0103/ops_0103.sql` | operational schema (12 STRICT tables) |
| `archive/verify-0103/trigs_0103.sql` | trigger suite (27 triggers; D-1 / DEF-01 / HIGH-02 gate + D-6 immutability + DEF-02 / HIGH-02 investigation guards) |
| `archive/verify-0103/test_delta_0103.py` | fail-closed delta harness (149 ordinary + 3 integration + 1 subprocess) |
| `archive/verify-0103/verify_digest_0103.py` | digest/fence/publication verification (6 checks) |
| `archive/verify-0103/README.md` | reproduction instructions |
| `db/engine.py`, `db/seed.py`, `db/test_suite.py` | database engine, deterministic seed generator, and 20-check acceptance test suite |
| `CORRECTION_TRACEABILITY_0103.md` / `VERIFICATION_REPORT_0103.md` / `CHANGE_SUMMARY_0103.md` | audit deliverables |

Per-file SHA-256 values are listed in `CHANGE_SUMMARY_0103.md` (computed at commit time) and bound by the commit on branch `fix/arch-st-010-5-remediation`.


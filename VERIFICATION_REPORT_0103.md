# VERIFICATION REPORT — ARCH-ST-010.3

**Document ID:** `VERIFICATION-REPORT-0103`
**Candidate:** `ARCH-ST-010.3` (corrections `D-1..D-10` from the Argon re-audit of `ARCH-ST-010.2`)
**Branch:** `fix/arch-st-010-3` — branched from the `main` tip at commit `8e513348e25a923183414f6fd7b3a9844cb91f7f`. `ARCH-ST-010.2` history preserved; `main` untouched. Candidate commit SHA: recorded in this branch's git log (see `CHANGE_SUMMARY_0103.md` provenance record). No merge / no deploy.

---

## 1. Executed environment (honest disclosure)

| Role | Python | SQLite (`sqlite3.sqlite_version`) | Source of truth |
|---|---|---|---|
| Primary | `3.10.11` | `3.40.1` | machine probe (`sys.version`, `sqlite3.sqlite_version`) |
| Cross-version control | `3.13.5` | `3.49.1` | machine probe — identical assertion counts required and observed |

All databases are in-memory (`:memory:`) and freshly built per run: `PRAGMA foreign_keys=ON; recursive_triggers=ON; trusted_schema=ON`, UDFs `sha256_hex` / `is_canonical_json` registered per spec §2.1. Cross-version capture was performed per-runtime (both interpreters executed the full harness, digest script, and engine/math suites).

## 2. Executed results (counts taken only from runner output)

### 2.1 Delta harness — `archive/verify-0103/test_delta_0103.py`

| Category | Primary (3.10.11 / 3.40.1) | Cross (3.13.5 / 3.49.1) | Exit code |
|---|---|---|---|
| Ordinary assertions | **132 passed / 0 failed / 132 total** | identical (132/0/132) | `0` |
| Trigger-mutation / integration checks (`MUT-NEW5-ctrl2`, `MUT-NEW5-strip`, `MUT-NEW5-a`) | **3 passed / 0 failed** | identical (3/0) | (same run) |
| Subprocess checks | **1** (`SELF-00`: fresh-interpreter `--mutate-self-test` must exit non-zero — observed exit `1`) | identical | (same run) |
| `--mutate-self-test` (fail-closed proof) | deliberate mutation mode → **exit `1`** | identical | `1` |
| Runner fail-closed self-test | 4 deliberate mutations (`MUT-1..MUT-4`) printed as `[FAIL]` — verified **caught** (internal runner self-test counts: passed=0 / failed=4); the runner cannot accidentally accept them | identical | (part of exit `0`) |

The idle `[FAIL]` lines at the top of the output are the deliberate runner self-test mutations — they are the proof that the runner fails closed, not suite failures. Suite status comes exclusively from the `== SUMMARY ==` lines above.

Schema/fence baseline asserts (category: ordinary):
- `V-00`: `ARCH-ST-010.3.md` contains exactly **5** SQL fences; fence[1] == `ops_0103.sql` and fence[2] == `trigs_0103.sql` byte-for-byte (scope: §2.1 / §5.1 / §5.2 convention) → `(5, True, True)`.
- `V-01`: operational build creates **12 STRICT tables and 26 triggers**.
- `V-02`: `ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE` present in shipped `trigs_0103.sql` **and** in the spec §5.2 fence.

### 2.2 Trust-boundary demonstration (`D-2`) — classified as BOUNDARY, not a security pass

`TRB-1..TRB-3` demonstrate that an authorized raw-SQL writer can plant the hard-collusion pair (`IND-01`/`IND-03` shared tokens) and write a self-consistent `65.00 HIGH` score — **accepted, by design**. This acceptance is a documented boundary demonstration (~§6.6): `ST-SCORE-V1` is an unkeyed consistency digest, not provenance authentication. §10.2 labels these rows BOUNDARY and §11 reports them outside the green-pass framing.

### 2.3 Schema digest — `archive/verify-0103/verify_digest_0103.py`

```
objects: tables=12 triggers=26 (expected 12 + 26: OK)
computed digest       : 2b606e7627a56721e541879bfdd2f48d278a1535f40884cac78f599678980215
order-independent     : True
matches §6.3 constant : True
D-1 gate published    : True | stripped clause removes all gate occurrences: True
python mirror matches : True | rows serialized: 38
[PASS] All 6 digest verification checks passed (fail-closed).
```

| Check | Primary | Cross |
|---|---|---|
| 6 digest checks (shape, fence identity, order-independence forward↔reverse DDL, §6.3 constant, publication, Python mirror) | `PASS` (exit `0`) | `PASS` (exit `0`) |
| `--mutate-self-test` | exit `1` | exit `1` |

`ARCH-ST-010.3` `ST-SCHEMA-V1` operational digest: **`2b606e7627a56721e541879bfdd2f48d278a1535f40884cac78f599678980215`** (38 objects = 12 tables + 26 triggers). Lineage values retained in §6.3: 010.2 `26e2218f…` (36 objects), 010.1 `63e74a55…`, 010 `f22c9b67…` (28 objects; recomputed green via `archive/audit-harness/verify_digest.py`).

### 2.4 Engine / math — `archive/audit-harness/verify_math.py`

`[PASS] All mathematical vectors (KAV-1..7, VH-1..7, PAYMENT_CANCELLED, FP-1, PageRank, 10-Stage Scoring) verified.` — green on both runtimes, including the new **D-5 assertions** (`CLM-2026-000003` dampening factor `BC-6` → `0.75`; `CLM-2026-000004` factor `0.25 × 0.75 = 0.1875`; dampened `c_3` = `0.75·0 = 0.0`).

### 2.5 Historical SQL integrity suites

`archive/audit-harness/verify_sql.py` and `verify_sql2.py` — `ALL DONE` on both runtimes (010 / 010.2 lineage fully intact; no regression from the D-1/D-6 additions in the 010.3 suite).

### 2.6 Key digest vectors re-derived (D-3 / D-4)

| Vector | Value | Derivation |
|---|---|---|
| `PAYMENT_CANCELLED` canonical payload (170000, `SIU_HOLD_RESERVATION_CLEARED`) | `14b3a52b35a0d83eab9e483fbe017c39fe173609589a627e084b632fc0024efe` | recomputed by generator AND harness (`NEW-7a`) |
| `PAYMENT_CANCELLED` 150000 payload (correction evidence) | `e586f6b192e8322a58b80f66335b64b6c37cfb03672124ef245f89814de44911` | recomputed (`NEW-7b`; retracted `874c6a8e…` asserted not derivable) |
| `ST-SCORE-V1` normative reference preimage (both norms `1.000`) | `2632d91521dda9907a3a3fd475396372f5a348769d8b69b597c041dd6e179718` | recomputed (`D-4b`; retracted `b0024998…` asserted nowhere) |
| `ST-SCORE-V1` live DB-state preimage (norm rendered `0.750`) | `4a8b6c91ae02a168d2999144c561801bc0a1b6a30f1ab92c2adfa0ab58ce1efc` | recomputed (`D-4a`; equals the digest accepted in `C-6g`) |

## 3. Fail-closed properties demonstrated

1. Any assertion failure → harness exit non-zero (runner is fail-closed by construction; `SELF-00` also proves the mutation mode exits `1` from a fresh interpreter).
2. `--mutate-self-test` on both `test_delta_0103.py` and `verify_digest_0103.py` exits `1` (observed on both runtimes).
3. The D-1 causality proof: removing the gate clause from the trigger text makes the previously-blocked exit succeed (`MUT-NEW5-a`) — the negative test demonstrably depends on the shipped clause.
4. Multi-runtime agreement required and observed (identical counts on SQLite 3.40.1 and 3.49.1).

## 4. Not executed (honest accounting)

- Full 5,000-claim seed generation (`seed=42`) — remains an application deliverable (`§10.1 SPECIFIED - NOT EXECUTED`).
- FastAPI / React application layer — out of scope of this baseline.
- Keyed indicator-provenance signing (D-2 future control) — documented design only.

## 5. Deliverable integrity (SHA-256, recomputed at commit staging)

Recorded for the files as committed on `fix/arch-st-010-3` in the candidate commit (see `CHANGE_SUMMARY_0103.md` for the final commit SHA; the SHA-256 values below are computed over the committed file bytes):

| File | Role |
|---|---|
| `ARCH-ST-010.3.md` | candidate specification (5 fences byte-identical to shipped SQL; §11 populated from executed results) |
| `archive/verify-0103/ops_0103.sql` | operational schema (12 STRICT tables) |
| `archive/verify-0103/trigs_0103.sql` | trigger suite (26 triggers; D-1 gate + D-6 immutability) |
| `archive/verify-0103/test_delta_0103.py` | fail-closed delta harness |
| `archive/verify-0103/verify_digest_0103.py` | digest/fence/publication verification |
| `archive/verify-0103/README.md` | reproduction instructions |
| `archive/audit-harness/verify_math.py` | engine/math harness incl. D-5 factor assertions |
| `CORRECTION_TRACEABILITY_0103.md` / `VERIFICATION_REPORT_0103.md` / `CHANGE_SUMMARY_0103.md` | audit deliverables |

Per-file SHA-256 values are listed in `CHANGE_SUMMARY_0103.md` (computed at commit time) and the binding legal identity is the candidate commit SHA on branch `fix/arch-st-010-3`.

## 6. Verdict

All ten confirmed defects (`D-1..D-10`) from the Argon re-audit are shipped, implemented in SQL (where applicable), published in the specification, and verified by executed, fail-closed tests on two runtimes. Prior corrections are regression-verified unchanged. Verification status: **GREEN (executed evidence complete for the candidate submission)** — final acceptance authority rests with the independent re-audit.

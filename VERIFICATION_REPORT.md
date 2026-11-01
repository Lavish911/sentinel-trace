# VERIFICATION_REPORT — ARCH-ST-010.1

**Revision:** `ARCH-ST-010.1` · **Executed on:** SQLite **3.49.1** (Python 3.13.5 `sqlite3`), Windows · **Harnesses:** `archive/verify-0101/`, `archive/audit-harness/`
**Status vocabulary:** `PASS — EXECUTED` · `FAIL — EXECUTED` · `SPECIFIED — NOT EXECUTED` · `NOT VERIFIED`. No reasoned expectation is reported as an executed result.
**Pinned runtime (SQLite 3.40.1 / Python 3.10.12):** all replication limited to `SPECIFIED — NOT EXECUTED` (§11.4 of the revision).

---

## 1. Correction harness — `archive/verify-0101/test_delta.py` (all `PASS — EXECUTED`)

Setup asserted: 12 `STRICT` tables + 24 triggers built; sibling SQL byte-identical to the document's §5.1/§5.2 fences.

| ID | Assertion (adversarial attempt) | Observed behavior | Status |
|---|---|---|---|
| C-1a | Invoice approved at 370000 while its claim is `SUBMITTED` | claim cascades to `APPROVED`, `approved_amount_cents=370000`, `historical_approved_cents=370000` | `PASS — EXECUTED` |
| C-1b | Direct `UPDATE claims SET claim_status='APPROVED'` with no approved invoice (fabricated aggregates) | `ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH` | `PASS — EXECUTED` |
| A-2a | `AUTHORIZED → DISBURSED` with no `PAYMENT_AUTHORIZED` event | `ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT` | `PASS — EXECUTED` |
| A-2b | Same transition with a canonical event | accepted; claim → `PARTIALLY_PAID`, rollups `net_paid=200000`, `reserved=170000` | `PASS — EXECUTED` |
| A-2c | Disbursement attempt while claim on `SIU_HOLD` | `ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL` | `PASS — EXECUTED` |
| A-2d | Cancellation without event / without `cancel_reason` | `ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT` / `ERR_PAYMENT_CANCELLATION_REQUIRES_REASON` | `PASS — EXECUTED` |
| A-2e | Cancellation with canonical `PAYMENT_CANCELLED` event | accepted; reservation released, invariants hold | `PASS — EXECUTED` |
| A-2f | Clawback without → with canonical event | `ERR_CLAWBACK_REQUIRES_EVENT`, then accepted; `historical_approved_cents` preserved | `PASS — EXECUTED` |
| C-6a | Investigation lifecycle + `DELETE FROM investigations` | FSM unchanged; delete → `ERR_INVESTIGATION_DELETE_FORBIDDEN` | `PASS — EXECUTED` |
| C-6b | Edge core-field tamper (strength, endpoints, keys) | `ERR_EDGE_CORE_FIELDS_IMMUTABLE` | `PASS — EXECUTED` |
| C-6c | Silent edge deactivation (no event) | `ERR_EDGE_DEACTIVATION_REQUIRES_EVENT` | `PASS — EXECUTED` |
| C-6d | Edge reactivation (`is_active` 0→1) | `ERR_EDGE_REACTIVATION_FORBIDDEN` | `PASS — EXECUTED` |
| C-6e | `DELETE FROM relationship_edges` | `ERR_EDGE_DELETE_FORBIDDEN` | `PASS — EXECUTED` |
| C-6f | Indicator UPDATE and DELETE | `ERR_FRAUD_INDICATOR_MUTATION_FORBIDDEN` / `ERR_FRAUD_INDICATOR_DELETE_FORBIDDEN` | `PASS — EXECUTED` |
| C-6g | Score write with correct `ST-SCORE-V1` digest + matching tier | accepted | `PASS — EXECUTED` |
| C-6h | Score write with wrong risk tier | `ERR_SCORE_TIER_MISMATCH` | `PASS — EXECUTED` |
| C-6i | Score write with wrong digest (64 zeros) | `ERR_SCORE_EVIDENCE_DIGEST_MISMATCH` | `PASS — EXECUTED` |
| C-6j | `siu_referred` on `SIU_HOLD` entry and on investigation `CLOSED_CONFIRMED_FRAUD` | flips to 1 on both paths; irreversible | `PASS — EXECUTED` |
| V-1 | Schema shape check | `tables=12 triggers=24` | `PASS — EXECUTED` |

**Score-vector executed values** (visible in the run log):
- Preimage: `ST-SCORE-V1|CLM-2026-000001|IND_COUNT:2|IND:IND-03:FINANCIAL:35.000:1.000:DUP_FP:1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465|IND:IND-14:BEHAVIORAL:12.000:1.000:VEL:CLMT-000001|IEF:30.76`
- Digest recomputed **inside SQLite by the trigger expression**: `e01d150f225e0cb85493528fa9d6868f3c4951027a7f0e08a694152ee94d5f78`
- Independent Python mirror: **identical** (`match py: True`). This is the reference vector cited in §6.6 of the document.

## 2. Digest harness — `archive/verify-0101/verify_digest_0101.py` (**`PASS — EXECUTED`**)

Runs against the document itself (extracts §5.1/§5.2/§6.3 fences from `ARCH-ST-010.1.md`):
- objects: tables=12, triggers=24 — shape OK
- computed digest: `63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93`
- order-independence (reverse DDL build, FK deferred): `True`
- matches §6.3 constant: `True`
- independent Python mirror of the digest SQL: identical, 36 rows serialized

## 3. Legacy math harness — `archive/audit-harness/` (**`PASS — EXECUTED`** on 3.49.1)

Executed against both the original `ARCH-ST-010.md` (audit phase) and the corrected sections of this revision:
- `verify_math.py`: KAV-1..7 payload + chained event hashes (incl. the `Renée|東京|🔍` collision vector), FP-1/FP-2 fingerprints, VH-1..7 chain, 8-node W/M matrices, degree vector, dangling handling, PageRank convergence at iteration **78** with ‖Δ‖₁ = **9.739882e-10** (t=77 = 1.251657e-09 > 1e-9), PR̃ = [1.054745, 1.058274, 1.170781, 0.716200], full 10-stage pipeline reproducing finals **65.00 / 65.00 / 0.00 / 0.67** with B_cluster = **14.227273** — all match the document.
- `verify_sql.py` / `verify_sql2.py`: ~27 adversarial FSM/cap/immutability/clawback/ledger tests on the operational DSM surfaces (invoice approval immutability + adjustment flow, claim/payment FSMs, historical-preservation, edges/indicators unprotected-surface discoveries that became C-6).
- `verify_digest.py`: ARCH-ST-010 lineage digest `f22c9b67…` (28 objects), order-independent, mirror-verified.

## 4. Not executed (`SPECIFIED — NOT EXECUTED`)

| Item | Reason |
|---|---|
| Full seed generation (`seed=42` row counts; `YF-NEG-*`/`BL-*` placement; `T-01..T-20`) | seed generator + application suite do not exist in this repository. |
| Pinned-runtime replication under SQLite 3.40.1 / Python 3.10.12 | pinned combination not installed in this environment; §11.4 checklist is directly runnable once available. |
| Application-layer suite | none implemented; database-level verification only. |

## 5. Release-threshold summary
- Correction acceptance tests: **21/21 PASS — EXECUTED** (C-1a..C-6j minus n/a, A-2a..f, V-1), 0 FAIL.
- Document constants re-derived from document-only harnesses: schema digest, score vector, schema-shape: **PASS — EXECUTED**.
- Verdict: **ARCH-ST-010.1 is internally verified on the executed platform; the only open items are the pinned-runtime replication and the not-yet-implemented seed/application suites.**

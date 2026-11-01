# CORRECTION_TRACEABILITY — AUD-ARCH-ST-010 → ARCH-ST-010.1

**Revision:** `ARCH-ST-010.1` · **Parent spec:** `ARCH-ST-010` (SHA-256 `3F56D163…F8118`) · **Audit:** `audits/AUDIT-ARCH-ST-010.md`
**Status vocabulary (mandated):** `PASS — EXECUTED`, `FAIL — EXECUTED`, `SPECIFIED — NOT EXECUTED`, `NOT VERIFIED`. Reasoned expectations are never reported as executed tests. Executed platform: SQLite **3.49.1** / Python 3.13.5; the pinned 3.40.1 / 3.10.12 replication is enumerated separately (§11.4 of `ARCH-ST-010.1`) and remains `SPECIFIED — NOT EXECUTED`.

---

## C findings (corrective spec defects)

### C-1 — Invoice-approval / claim-FSM dead-lock
- **Defect (audit):** the invoice FSM permitted `SUBMITTED → APPROVED` invoice approval while the claim FSM forbade `SUBMITTED → APPROVED` on the owning claim, so the normal approval path aborted.
- **Correction:** claim FSM extended: `SUBMITTED → {UNDER_REVIEW, APPROVED, SIU_HOLD, DENIED}`, where `SUBMITTED → APPROVED` is reachable **only through the atomic invoice-approval cascade** (`trg_invoices_sync_claim_au`), which writes `approved_amount_cents = SUM(invoice approved_cents) > 0` in the same statement. Direct-SQL fabrication remains blocked (`ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH`).
- **Normative location:** `ARCH-ST-010.1` §1.1, §4.1 FSM list, §4.2/§4.3 notes, §5.2 `trg_claims_fsm_upd`.
- **Acceptance criterion:** (a) approving an invoice on a `SUBMITTED` claim succeeds and cascades the claim to `APPROVED` with correct aggregates; (b) a direct `UPDATE claims SET claim_status='APPROVED'` without an approved invoice aborts with `ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH`.
- **Verification:** criterion (a) = test `C-1a`, criterion (b) = `C-1b` — both **`PASS — EXECUTED`** (`archive/verify-0101/test_delta.py`).

### C-2 — `EXPECTED_OPERATIONAL_SCHEMA_SHA256` undefined
- **Defect:** §2.1's startup step demanded digest equality against a constant that was never published.
- **Correction:** constant published: `63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93` for the corrected schema (§5.1 + §5.2 = 12 tables + 24 triggers, 36 objects). DDL-order independence verified with two differently-ordered builds; an independent Python mirror of the §6.3 digest SQL reproduces the value. The legacy ARCH-ST-010 digest `f22c9b67…` is retained as a lineage reference row.
- **Normative location:** §2.1 step 3, §6.3 (with the full derivation procedure), §5.2 fence.
- **Acceptance criterion:** running the §6.3 digest query on the exact §5.1+§5.2 schema yields the constant, independent of DDL order and implementation language.
- **Verification:** **`PASS — EXECUTED`** (`archive/verify-0101/verify_digest_0101.py` extracts the fences from the document itself; tables=12, triggers=24, dual-order equality, mirror equality). Pinned 3.40.1 run: `SPECIFIED — NOT EXECUTED`.

### C-3 — Scoring pipeline not self-contained (implicit code contract)
- **Defect:** the operative scoring semantics (graph weights, PageRank constants, boost formula, floors) existed only in `src/utils/sentinelEngine.ts`; the spec cited outcomes without definitions ("see code" defect).
- **Correction:** §9 rewritten as the complete scoring contract: §9.1 graph/edge-weight construction with normative β constants for every edge type; §9.2 M matrix + full checkpoint table (t=0..78; convergence exactly at 78,‖Δ‖₁=9.739882e-10, hard cap 200 iterations); §9.3 PR̃ definition; §9.4 the 10-stage pipeline (S1–S10) with every constant (pillar caps 60/55/45/40; weights 0.35/0.30/0.20/0.15; dampening floor 0.15; boost min(20, 0.20·max+0.10·mean+5·ρ); hard floor 65.00; tier thresholds ≥85/≥65/≥30; rounding = half-up to 2 decimals); §9.5–§9.8 per-claim worked examples; §9.9 reproduction statement.
- **Normative location:** §9 (throughout); scenario linkage §7.1/§7.2 unchanged.
- **Acceptance criterion:** the clean-room finals `65.00/65.00/0.00/0.67` and `B_cluster=14.227273` are reproducible from the document alone; the checkpoint table matches an independent reimplementation.
- **Verification:** **`PASS — EXECUTED`** (`archive/audit-harness/verify_math.py` — engineered independently of the engine source — reproduces every §9 value).

### C-4 — Event partition infeasible (1,105 INV_APP < 1,200 CLM_APP; total 19,495)
- **Defect:** with 1:1 eventing, every approved claim requires ≥1 initial invoice approval, so `INV_APP = 1,105` cannot support `CLM_APP = 1,200`; the deficit ≥ 95 was unexplainable and the bucket table did not sum to any consistent total.
- **Correction:** repartitioned: `INV_APP = 1,200` (1:1 with initial invoice approvals — one initial approval per invoice; re-approvals after clawback are state restorations and are not re-counted), and the new `PAYMENT_CANCELLED` bucket = 25 for `A-1` reservation release. New total **19,615**. A feasibility table mapping every bucket to its enforcing invariant was added.
- **Normative location:** §3 (row 11), §3.1 reconciliation, §6.5/§6.4.1 payload contract for the new event type.
- **Acceptance criterion:** bucket arithmetic sums to 19,615 and each bucket is backed by an invariant; the ≤-deficit contradiction disappears.
- **Verification:** bucket arithmetic **`PASS — EXECUTED`**; full-seed generation **`SPECIFIED — NOT EXECUTED`** (generator does not yet exist in-repo).

### C-5 — `is_canonical_json` never defined
- **Defect:** CHECK constraints and contracts relied on a function with no definition — any implementation was acceptable by the letter of the spec.
- **Correction:** §6.5 canonical JSON contract: sorted-key order, zero whitespace, minimal escaping with raw UTF-8 for non-ASCII, integer-only numeric policy for event payloads, boolean/null casing, round-trip normative definition (`parse` + `re-serialize` == input). Declares the exact Python reference behavior `json.dumps(obj, ensure_ascii=False, separators=(',',':'), sort_keys=True)`.
- **Normative location:** §6.5; referenced by §5.1 CHECKs, §6.1/§6.2/§6.2.1, §6.4.1, ST-DUMP-V1/ST-SCORE-V1/ST-SCHEMA-V1 preimages.
- **Acceptance criterion every KAV/VH fixture and trigger-reconstructed payload is canonical under §6.5; a non-canonical re-serialization is rejected.
- **Verification:** **`PASS — EXECUTED`** (fixtures re-validated in the harnesses; CHECK path exercised in `test_delta.py`).

### C-6 — Unprotected mutation/deletion surfaces (score clamp bypass, edge tamper, indicator editing, investigation DELETE, `siu_referred` orphan)
- **Defect (audit, `verify_sql2.py`):** `investigations` DELETE silently unblocked; `relationship_edges` rows could be silently flipped (`is_active`), re-activated, or have `strength_weight` edited; `fraud_indicators` could be updated/deleted after scoring; `claims.latest_ief_score` could be written detached from its evidence; `claims.siu_referred` could disagree with FSM history.
- **Correction:** 8 new triggers appended (24 total; the three event-gates of payments merged into `trg_payments_validate_upd` for deterministic error precedence): `trg_investigations_block_delete`, `trg_edges_flow_upd`, `trg_edges_block_delete`, `trg_findings_block_upd`, `trg_findings_block_delete`, `trg_claims_siu_referred_au`, `trg_investigations_siu_ref_au`, `trg_claims_score_upd`. Schema deltas: `claims.scoring_evidence_sha256`, `payments.cancel_reason` + closed enum CHECK, `immutable_events` enum += `PAYMENT_CANCELLED`, `RELATIONSHIP_EDGE_DEACTIVATED`.
- **Normative location:** §4.6 (governance matrix), §4.7 (semantics notes), §5.1/§5.2 (fences), §6.6 (`ST-SCORE-V1`).
- **Acceptance criteria:** every audited tamper surface throws its documented error; every legitimate lifecycle path succeeds. Verified individually in C-6a..C-6j.
- **Verification:** **`PASS — EXECUTED`** (all ten cases, `archive/verify-0101/test_delta.py`).

### C-7 — YF-NEG-3 ≥ 65.00 mathematically unreachable as written
- **Defect:** from IND-03 alone the max achievable score was ≈ 19.09 + boost < 65, so the scenario's ≥ 65.00 promise was false.
- **Correction (not a scorer manipulation):** scenario strengthened — planted claims share a payout account and emit `IND-01` (20.0, `k_acct=2`) + `IND-03` (35.0) with identical shared tokens, making them eligible for the **hard-collusion path already in the de-facto engine**: S_base = 30.757576, B_cluster = 14.227273 (ρ_K = 1.0), preFloor = 44.984848, hard floor → **65.00 (HIGH)**. The false promise of IND-03-alone reaching 65 is explicitly withdrawn in §7.1. Identical path independently exercised by §9's clean-room fixture.
- **Normative location:** §7.1 (rewritten scenario), §9.5–§9.9 (worked math), §9.4-S7 (eligibility definition).
- **Verification:** **`PASS — EXECUTED`** (`verify_math.py` reproduces 65.00 by the published pipeline; no fixture-specific thresholds or planted-ID shortcuts exist in any scorer).

## A findings (documentation-honesty, lifecycle, provenance)

### A-1 — SIU_HOLD entry/exit protocol, cancelled-reservation accounting undocumented
- **Correction:** §4.5 (full protocol: entry, reservation retention at hold — disbursement forbidden while held — cancellation via `PAYMENT_CANCELLED` event + `payments.cancel_reason`, re-approval, denial/clawback interaction, `siu_referred` flips). Verification: `A-2c/A-2d/A-2e` (hold blocks disbursement; cancellation requires event+reason; cancellation releases reservations) — **`PASS — EXECUTED`**; hold-entry event emission during seed generation: `SPECIFIED — NOT EXECUTED`.

### A-2 — KAV narrative conflicts with the operational FSM; cancellation event type missing
- **Correction:** KAV-1..7 reclassified as pure cryptographic hash vectors (`§6.2`, "MUST NOT be replayed as an operational history"); new FSM-valid chain VH-1..VH-7 published with full computed hashes (genesis linkage intact; `PASS — EXECUTED`, `verify_math.py`); `PAYMENT_CANCELLED` event type added with payload contract (§6.4.1) and trigger gate (all event-gates **`PASS — EXECUTED`**).

### A-3 — "Verified SQLite 3.40.1" claims unsubstantiated
- **Correction:** honest disclosure in the document header and §11: executed platform is 3.49.1/3.13.5; all pinned-version claims relabelled `SPECIFIED — NOT EXECUTED (pinned 3.40.1)`; §11.4 provides the replication checklist. Harnesses shipped so the checklist is directly runnable.

### A-4 — ARCH-ST-001..009 provenance unresolved
- **Correction:** header provenance disclosure: audit-referenced documents are placeholder stubs; those historical claims are treated as provenance assertions, not verified facts. Verified artifacts (byte-identity hash of ARCH-ST-010) documented.

### A-5 — Trigger/payment semantic notes missing
- **Correction:** §4.7 documents: same-status no-op strictness for payments, blocked-payment remediation (fresh `idempotency_key` path), the event-authorization trust model (existence-of-well-formed-event, no HMAC — disclosed as accepted for the challenge's SQLite-only model), scalar MIN/MAX floor ≥ 3.7.11, `trusted_schema` note. Execution evidence for each statement: `verify_sql.py` + `test_delta.py` results cited inline — **`PASS — EXECUTED`**.

## Cross-cutting guarantees
- **No score manipulation:** the hard-collusion floor, boost formula and dampening contexts published in §9 are the de-facto semantics extracted from `sentinelEngine.ts` (lines 224–480), not invented for passing tests; the `C-7` scenario was strengthened by planting *more legitimate evidence*, not by special-casing IDs. No planted-ID or fixture-ID hardcoding exists in any scorer or trigger (verified by reading the shipped SQL — fixtures are passed as data, never embedded).
- **No ground-truth leakage:** all territory of §2 quarantine untouched from ARCH-ST-010; corrections touched no quarantine tables.
- **Baseline preservation:** entity counts, ID formats, scenarios (`YF-NEG-*`, `BL-*`, `EC-*`), and CRITICAL-fix outcomes from ARCH-ST-010 are unchanged except where a correction was necessary (§3.1 event partition; §5 fences; new §4.5–§4.7, §6.4.1–§6.6, §9; §7.1 rewrite; §10/§11).

# INDEPENDENT ADVERSARIAL ARCHITECTURE AUDIT — ARCH-ST-010 (SENTINEL//TRACE)

**Audit ID:** AUD-ARCH-ST-010
**Auditor:** Independent adversarial reviewer (not Argon, not ChatGPT model)
**Mode:** Read-only against `ARCH-ST-010.md`; all executions ran against copied/temp working files only. No repository file was modified during this audit.
**Verification environment:** Python 3.13.5, `sqlite3` module binding SQLite 3.49.1 (Windows). The specification pins SQLite 3.40.1 — see A-3/A-5 status notes.

---

## 0. Source identity and provenance

| Item | Result |
|---|---|
| Attached file `C:\Users\HP\Downloads\ARCH-ST-010 (2).md` | **646-byte stub** (10 lines: title + 4 score lines only). All 8 Downloads copies (`ARCH-ST-010.md`…`(7).md`) are byte-identical 646-byte stubs (SHA-256 `2FAF22BF1302872BFB1BBB725CA6DCBF9825E8121D04372729A4A02353535111`). |
| Full document in `sentinel-trace-main.zip` | 1,254 lines / 95,162 bytes, SHA-256 `3F56D16365B8148C0BB7D7A225ED4DD8990AC8441C49B0C4FA234A91420F8118` |
| `https://raw.githubusercontent.com/Lavish911/sentinel-trace/main/ARCH-ST-010.md` | **Byte-identical** to the zip copy (same SHA-256). Audit is against the authoritative text. |
| ARCH-ST-001…009 | 223-byte stubs ("Superseded by ARCH-ST-010"). **No previous architecture revisions or audit reports exist in the repository** — every "resolved CRITICAL 1..8" claim in §1 is unverifiable against its predecessor. |

⚠️ Note for the record: the file attached to the audit request contained only the score header and could not be audited. The audit was performed against the authoritative document located via the repository.

## 1. Verification matrix (what was actually executed)

| Check | Method | Result |
|---|---|---|
| KAV-1…KAV-6 `payload_sha256` + chained `event_hash` per §6.1/§6.2 | Python re-derivation of ST-EVT-V2 preimages from the documented field values | ✅ **All 12 hashes reproduce exactly** (genesis-zeros chain intact) |
| KAV-7 (Unicode `USR\|Renée;東京`, NULL `claim_id`, delimiter-injection payload) | same | ✅ `c20f59e4…9a243e8dbe` reproduces; actor length 17 UTF-8 bytes confirmed |
| FP-1/FP-2 fingerprints (`AB-FRAME-101`, TRIM/UPPER normalization) | Python | ✅ `1547087d…07ff465`; FP-2 ≡ FP-1 |
| 8-node PageRank: degree vector, α, dangling-mass handling, convergence | Python (independently coded, from the engine's W) | ✅ d = [2,2,2,1,4,4.6,2.6,3]; converges at **iteration 78**, ‖v⁷⁸−v⁷⁷‖₁ = **9.7399e-10** (doc claims 9.740e-10 ✅); v⁷⁸ matches doc to 8 decimals; S_claim = 0.3592153088 (doc: 0.35921531 ✅); PR̃ = [1.054745, 1.058274, 1.170781, 0.716200] ✅ |
| 10-stage IEF scoring (pillar staging, dedup, dampening, cluster boost, floor, tiers) | Python re-implementation of engine formulas | ✅ S_base = 30.757576 / 30.757576 / 0 / 3.555556; D = 1.0 / 1.0 / 0.75 / 0.1875; B_cluster = 14.227273; final = **65.00 / 65.00 / 0.00 / 0.67**, tiers HIGH/HIGH/LOW/LOW — all match the doc headline |
| §5.1 DDL + §5.2 trigger suite (12 tables, 16 triggers) | Executed in real SQLite 3.49.1 with `sha256_hex`/`is_canonical_json` UDFs | ✅ Loads and runs clean (~27 adversarial tests below) |
| Invoice/claim/payment FSM, caps, immutability, clawback, revoke→deny | 27 targeted adversarial SQL tests | see §2 |
| ST-SCHEMA-V1 digest determinism (CRITICAL 6) | Two DBs built with **different DDL orders** (document order vs reversed), digest computed via §6.3 SQL and via an independent Python mirror | ✅ **Order-independent**: both DBs = `f22c9b679797b249ccafb718de4075d00f7eee75039f1b2c461dff951f16f319`, stable across re-runs; Python mirror matches SQL UDF digest |
| §3.1 event-partition sums | arithmetic | Sum = 19,495 ✅ but see defect **C-4** (allocation infeasibility) |
| §10 T-01…T-28 | Not executable from doc alone; statuses all `SPECIFIED — NOT YET EXECUTED`; auditor's equivalents of T-21…T-27 **were** executed (§2) but on SQLite **3.49.1**, not the pinned 3.40.1 | ⚠️ partial |

The engine code (`src/utils/sentinelEngine.ts`, `sentinelEngine.test.ts`) was inspected as the de-facto implementation of the spec's numerics; `archSt010Spec.ts` and `App.tsx` confirm the missing constants live **only in code**.

## 2. SQL trigger execution results (evidence log)

**Confirmed working as specified** (executed):

- Direct claim/invoice rollup tamper → `ERR_CLAIM_NET_PAID_AGGREGATE_TAMPERING`, `ERR_INVOICE_RESERVED_AGGREGATE_TAMPERING` ✅
- Same-status post-approval `approved_cents` change without event → `ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE` ✅; with a proper `INVOICE_APPROVAL_ADJUSTED` event whose `payload_sha256` matches the trigger-reconstructed canonical JSON → adjustment permitted, `historical_approved_cents` becomes max(370000, 400000) = 400000 ✅
- Over-authorization → `ERR_PAYMENT_EXCEEDS_APPROVED_CAP`; blocked rows insertable only as `BLOCKED_*` with `block_reason_code` ✅; `BLOCKED → AUTHORIZED` conversion impossible ✅
- Post-disbursement bank-ref/amount tamper → blocked ✅; direct `INSERT` of `DISBURSED` → blocked ✅
- Full clawback drives invoice/claim to `APPROVED` with `net_paid = 0`; revoke succeeds only at zero active exposure; cascade sets claim `SIU_HOLD`; deny preserves `historical_approved_cents = 370000` ✅ (CRITICAL 7 behavior verified)
- Immutable-event update/delete/chain-break/non-monotonic-sequence → all blocked ✅
- Duplicate line-item fingerprint invoice → `ERR_UNFLAGGED_DUPLICATE_INVOICE` ✅
- Closed investigation mutation → `ERR_CLOSED_INVESTIGATION_IMMUTABLE` ✅
- Claims/invoice/payment delete blocks ✅

## 3. Confirmed defects

### C-1 — 🔴 HIGH · Invoice FSM advertises an impossible transition (documented seam contradiction, found in execution)
- **Where:** §4.2 (line 118: `SUBMITTED -> {UNDER_REVIEW, APPROVED, …}`) vs. `trg_invoices_sync_claim_au` (line 808-863) + claim FSM in `trg_claims_fsm_upd` (line 640-648).
- **Evidence (executed):** approving the invoice while the claim is `SUBMITTED` (both states as documented) aborts with `ERR_CLAIM_INVALID_FSM_TRANSITION`; the invoice FSM permits `SUBMITTED → APPROVED` but the claim FSM forbids `SUBMITTED → APPROVED`, and the invoice-approval cascade updates the claim status atomically. The operation succeeds only after an **undocumented** manual pre-step `claim → UNDER_REVIEW` (which, additionally, has no corresponding `immutable_events` event_type anywhere in the 19,495-event reconciliation).
- **Failure scenario:** any implementation following §4.2 verbatim dead-locks on first approval of a fresh claim; seed generation of the 1,105 `INV_APP` events cannot proceed as specified.
- **Impact:** primary approval workflow unreachable as specified; FSMs mutually inconsistent.
- **Correction (precise):** either add `SUBMITTED → APPROVED` to the claim FSM (claim-side precondition check: approve requires active approval sum > 0, which the cascade guarantees) *or* delete `APPROVED` from `SUBMITTED → {…}` on the invoice FSM *and* state the mandatory precondition `claims.claim_status = 'UNDER_REVIEW'` before first invoice approval. Pick one; document it.

### C-2 — 🔴 HIGH · `EXPECTED_OPERATIONAL_SCHEMA_SHA256` value is missing (connection bootstrap unimplementable)
- **Where:** §2.1 step 3, line 44 — the only occurrence in the entire document (verified by search).
- **Evidence:** §6.3 defines the digest algorithm but no expected value; `archSt010Spec.ts` also contains no constant; nothing else in the repo defines it.
- **Failure scenario:** `app/db/engine.py` is ordered to "assert equality" against a value that does not exist; every connection open fails or the check must be skipped (silently voiding CRITICAL 6 at runtime).
- **Impact:** self-containedness claim (`Supersedes … 100% self-contained`) is false; T-26 cannot be concluded.
- **Correction:** publish the constant **and** the derivation harness. Auditor's reference value for the exact §5.1 + §5.2 schema (12 tables + 16 triggers, SQLite order-independence verified): `f22c9b679797b249ccafb718de4075d00f7eee75039f1b2c461dff951f16f319` — this must be reproduced by the author under the pinned SQLite 3.40.1 DDL text and then pinned in the document, not taken from this report.

### C-3 — 🔴 HIGH · CRITICAL 8's promised clean-room contents are absent; final scores are **not** reproducible from the document alone
- **Where:** §1 CRITICAL 8 row (line 24) vs §9 (lines 1227-1238).
- **Evidence (grep + reproduction):** §9 supplies only: vertex labels, degree vector, converged vector, S_claim, the four PR̃ values, S_base/D/B_cluster finals. It does **not** contain: the 8×8 adjacency W, the 8×8 transition M, the claimed PageRank checkpoints (t = 0,1,2,3,5,10,20,40,60,77,78), the indicator activation table per claim, α = 0.85, dangling-mass handling, the convergence criterion 10⁻⁹, the PR̃ normalization formula (PR̃(c) = 4·PR(c)/Σ_claim PR — inferable only from code), pillar caps (NETWORK 60 / FINANCIAL 55 / BEHAVIORAL 45 / DOCUMENT 40), pillar weights (0.35/0.30/0.20/0.15), dampening = product of active m-values with floor 0.15 and hard-collusion override D = 1, cluster-boost formula min(20, 0.20·max + 0.10·mean + 5·ρ_K) and its eligibility set, hard floor 65.00, or risk-tier thresholds (≥85 CRITICAL / ≥65 HIGH / ≥30 MEDIUM / else LOW). All of these exist **only** in `src/utils/sentinelEngine.ts`.
- **Failure scenario:** a third party implementing from ARCH-ST-010 alone cannot reproduce S_base = 30.757576 → T-28 fails; the "independently reproducible final scores" requirement fails.
- **Impact:** CRITICAL 5 ("graph construction, edge weights, clustering, and 10-stage scoring included directly", line 21) and CRITICAL 8 are **both misreported as resolved**. The document is not self-contained at the scoring/IEF layer, even though the engine's own numbers are correct (they do reproduce from the code).
- **Correction:** add to the document (a) W, M, α, dangling-handling, checkpoint table; (b) the 10-stage pipeline definition with formulas for S_base (pillar caps/weights), D (multiplier product, floor 0.15, override rule), B_cluster (boost formula, eligibility K, ρ_K definition), the 65.00 hard floor, and tier thresholds; (c) per-claim indicator activations for CLM-000001…000004 (IND-01 20.0 + IND-03 35.0 for c1/c2; IND-14 8.0 for c4; no IND-06 because all PR̃ ≤ 1.25).

### C-4 — 🟠 MEDIUM · Baseline event partition is infeasible: `INV_APP` (1,105) < `CLM_APP` (1,200)
- **Where:** §3.1 last bullet, line 81.
- **Evidence (arithmetic + model invariants):** every claim whose status can be `APPROVED` requires ≥ 1 child invoice in `APPROVED/PARTIALLY_PAID/PAID` with `approved_cents > 0` (`trg_claims_fsm_upd` + rollup aggregate checks); every invoice reaching those statuses must pass through `INVOICE_APPROVED` or an adjustment (counted separately, and none is budgeted). 1,200 approved claims therefore require ≥ 1,200 `INVOICE_APPROVED` events; the partition allocates 1,105. The inner sum totals 19,495 correctly, but the allocation is impossible.
- **Failure scenario:** the seed=42 fixture cannot be generated with intact event counts — either 95+ claims never became `APPROVED`, or invoices were approved without emitting the audit event the entire CRITICAL audit chain presumes.
- **Impact:** penny/event reconciliation tests (T-01 family) will fail; event-ledger completeness claim overstated.
- **Correction:** recompute the INV_APP count (≥ 1,200) and rebalance the 19,495 total; state explicitly whether invoice approvals must emit events (1:1) or not.

### C-5 — 🟠 MEDIUM · `is_canonical_json` semantics are undefined
- **Where:** used in `fraud_indicators` (line 424), `immutable_events` (475), `ingestion_exceptions` (517); never defined in the document.
- **Evidence:** KAV payloads implicitly show the intent (sorted keys, compact separators, raw unicode, plain integers) but no rule is stated. The auditor's UDF used `sort_keys=True, separators=(',',':'), ensure_ascii=False` — consistent with every fixture, but **any** alternative implementation diverges silently.
- **Failure scenario:** two conformant implementers write different `is_canonical_json`; identical payloads get accepted/rejected differently; schema digest (C-2) and event chains become non-reproducible; CHECK constraints behave differently per build.
- **Correction:** define canonicalization precisely: key ordering (lexicographic byte order), separators, integer formatting, string escaping/`ensure_ascii=False` policy, and floating-point exclusion (all numerics here are integers).

### C-6 — 🟠 MEDIUM · Unprotected mutation/deletion surfaces defeat the scoring & investigation audit story (not in any previous concern list)
- **Where/what executed:**
  - `DELETE` from `investigations` **succeeds** — there is no block-delete trigger (only `claims`/`invoices`/`payments`/`immutable_events` have them); closed-investigation immutability is update-only.
  - `UPDATE relationship_edges SET is_active=0, strength_weight=0.01` **succeeds silently** — no trigger, no requirement of an event, no restriction; yet edge selection and `is_active` feed clustering/PR̃ (`BL-4`'s exclusion rule is defined only behaviorally).
  - `UPDATE fraud_indicators SET raw_points=...` **succeeds silently** — raw_points directly determine S_base; nothing prevents re-weighting scores post-computation. (Bounds are CHECKs only; CHECKs don't stop a "legitimate" writer from re-writing.)
- **Impact:** score manipulation and audit-trail erosion with no defense in depth; scoring outputs (claims.latest_ief_score) are not reconciled against fraud_indicators by any trigger.
- **Correction:** either add block-delete/block-tamper triggers + mandatory `immutable_events` for `relationship_edges.is_active`/`fraud_indicators` changes and investigations deletion, or explicitly declare these tables append-only-by-application-policy with a compensating control (digest check) — currently the document does neither. Also: nothing anywhere defines when `claims.siu_referred` flips to 1 (column exists, never referenced).

### C-7 — 🟠 MEDIUM · YF-NEG-3 target score is unreachable under the documented (or coded) pipeline
- **Where:** §7.1 line 1192: "both claims … emitting IND-03 (35.0 pts) and scoring ≥ 65.00 (HIGH/CRITICAL)."
- **Evidence (math):** with only IND-03: pFin = 100·35/55 = 63.636, base = 0.30·63.636 = **19.09** < 65. No other indicator is specified for these claims; reaching 65.00 requires the undocumented cluster boost + hard floor (C-3), which requires `hardCollusionOverride` — a concept that appears nowhere in the document.
- **Failure scenario:** acceptance of the 5,000-claim baseline cannot validate the ≥ 65.00 bound for the 25 YF-NEG-3 claims; T-01's "negative bounds" are unauditable.
- **Correction:** document the full scoring path for YF-NEG-3 (which indicators, which contexts, eligibility for the floor) or lower/restate the bound.

## 4. Ambiguities (verified but underspecified)

- **A-1 — SIU_HOLD with outstanding payment reservations.** Executed: entering `SIU_HOLD` from `APPROVED`/`PARTIALLY_PAID` **is allowed with reservations outstanding** (reserved_authorized_cents = 150000); disbursement on hold is blocked (`ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL`); `DENIED` is blocked until reservations = 0 (sound); but re-approval from hold is blocked whenever net_paid > 0, and the only exits are documented nowhere: cancel `AUTHORIZED` payments (allowed — `AUTHORIZED → CANCELLED` bypasses claim-status checks) or claw back disbursed funds. There is also no trigger requiring a `CLAIM_SIU_HOLD_PLACED` event, so holds can be placed invisibly. **Net:** the money-side invariants hold, but the entry/exit protocol is undocumented and unlogged.
- **A-2 — KAV narrative violates the operational FSM if replayed.** KAV-3 emits `CLAIM_APPROVED` while the invoice has no approval event; KAV-4 authorizes a payment while the invoice is (by chain content) never approved — under `trg_payments_validate_ins` this payment couldn't exist. Purely as hash vectors they're fine (and they verify); as the document sells them as a "verified chain", flag the narrative mismatch. Note also there is **no `PAYMENT_CANCELLED` event_type** while `CANCELLED` is a legal payment state — cancelled reservations are permanently unloggable in the audit ledger.
- **A-3 — "Verified SQLite 3.40.1" claims for T-21…T-25.** Equivalent behavior was verified on SQLite 3.49.1 (`PRAGMA trusted_schema=ON` with `deterministic` UDFs is precisely the fragile area). The claim is plausible but unverifiable without a reproducible harness; the pinned-version evidence must be shipped as scripts, not asserted.
- **A-4 — Previous audit lineage cannot be checked.** ARCH-ST-001…009 are placeholder stubs; every "CRITICAL-n resolved" claim in §1 refers to an audit that isn't in the repository.
- **A-5 — Minor trigger-semantics notes (executed, all safe but worth stating):** `trg_payments_validate_upd`'s `ELSE` rejects same-status no-op updates on `payments` (strict but undocumented); `block_reason_code` is immutable across all updates, so a blocked payment can never be re-mediated (must absorb its idempotency key forever); the adjustment protocol's "authorization" reduces to *existence of one app-insertable event row* (no actor/role/HMAC binding) — acceptable for the pure-SQLite trust model, but the document should say so; `MIN(x,y)/MAX(x,y)` scalar forms inside triggers require SQLite ≥ 3.7.11 (satisfied by pin).

## 5. Is the document genuinely self-contained?

**Partially — exactly half.** Verified honestly:
- **Self-contained and correct (executed):** §4 FSMs/financial equations, §5 DDL + 16 triggers, §6.1 ST-EVT-V2 grammar + §6.2 KAVs, §6.3 digest algorithm (order-independence proven), §6.4 fingerprints, §7 BC/BL/YF-NEG multipliers *as constants*, §8 all 15 indicator formulas (all 15 present, each with token definition).
- **Not self-contained (C-2, C-3, C-5):** scoring pipeline, cluster boost, dampening floor, tier thresholds, PageRank internals, schema-digest constant, canonical-JSON contract. These live only in `src/utils/sentinelEngine.ts`. The header's "100% self-contained; zero external document dependencies" is therefore **false as written**, even though the code happens to resolve every number (all four final IEF scores and all 14 KAV/fingerprint digests reproduce bit-exactly from the code — the implementation matches the spec, the spec just doesn't contain its own formulas).

## 6. Verdict

### **CONDITIONALLY APPROVED — not implementable today; no redesign required.**

Rationale: the load-bearing core (DDL, all 16 triggers, event chain, financial invariants, historical accounting) is real, executable, and survived 27 adversarial SQL tests, and the numeric headline (four final IEF scores, 14 hash vectors, PageRank/IEF internals) reproduces bit-exactly from the code. But five blocking items must be fixed and re-verified **before implementation sign-off**:

**Blocking:** (1) publish `EXPECTED_OPERATIONAL_SCHEMA_SHA256`; (2) move the 10-stage pipeline equations, W/M, α, checkpoints, pillar caps/weights, dampening floor, cluster-boost formula, 65.00 floor, tier thresholds, and per-claim indicator activations into the document; (3) resolve the `SUBMITTED → APPROVED` FSM seam in one direction and document the claim-`UNDER_REVIEW` precondition; (4) fix the INV_APP/CLM_APP event allocation; (5) define `is_canonical_json`.

**Strongly recommended at the same time:** mutation/delete protection for `investigations`/`relationship_edges`/`fraud_indicators` or an explicit compensating control (C-6); SIU_HOLD entry/exit + cancellation-event policy (A-1); a `PAYMENT_CANCELLED` event type or a documented rationale; YF-NEG-3 scoring path (C-7); a shipped SQLite-3.40.1 test harness to substantiate the "verified" parentheticals (A-3); and either real ARCH-ST-001…009 content or disclosure that the lineage is stubbed (A-4).

Nothing here calls for an ARCH-ST-011 synthesis — all corrections are additive or single-clause edits to ARCH-ST-010, after which the spec would genuinely earn its "FINAL SELF-CONTAINED" label.

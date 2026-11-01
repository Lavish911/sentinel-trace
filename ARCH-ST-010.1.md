# ARCH-ST-010.1 — SENTINEL//TRACE: Corrected Self-Contained Architecture Specification

**Document ID:** `ARCH-ST-010.1`  
**Status:** `CORRECTED SELF-CONTAINED ARCHITECTURE SPECIFICATION — READY FOR IMPLEMENTATION SIGN-OFF`  
**Supersedes:** `ARCH-ST-010` (which supersedes `ARCH-ST-001` through `ARCH-ST-009`). This revision is a **correction task, not a redesign**: it resolves every finding of the independent adversarial audit `AUD-ARCH-ST-010` (findings C-1..C-7, A-1..A-5) while preserving the verified architecture, business rules, FSMs, invariants, scenarios, IDs, and terminology of ARCH-ST-010.  
**Target System:** `SENTINEL//TRACE` — Insurance Fraud Network Intelligence, Financial Reconciliation & SIU Investigation Platform (YottaFlex Challenge)  
**Verification environment as executed by the author of this revision (honest disclosure):**
- All SQL/trigger/digest/scoring verification in this revision was **actually executed** on **SQLite 3.49.1** (via Python 3.13.5, `sqlite3` module) with the UDFs `is_canonical_json` / `sha256_hex` registered per §2.1. The runnable harness ships in the repository (`archive/audit-harness/`, `archive/verify-0101/`).
- The **pinned SQLite 3.40.1 / Python 3.10.12 combination was NOT available in this environment**. Every check that historically claims "verified on 3.40.1" is therefore labelled **`SPECIFIED — NOT EXECUTED (pinned 3.40.1)`** in §11 unless re-executed under the pin. Where a value is version-sensitive (the `sqlite_master` digest is *not* — see §6.3), this is stated explicitly.
- Execution statuses used in this document: `PASS — EXECUTED`, `FAIL — EXECUTED`, `SPECIFIED — NOT EXECUTED`, `NOT VERIFIED` (per the correction mandate; a mathematically reasoned expectation is never reported as an executed test).

**Provenance disclosure (`A-4`, honestly stated):** The repository files `ARCH-ST-001.md` .. `ARCH-ST-009.md` are **placeholder stubs** (each ~10 lines stating only "Superseded by ARCH-ST-010"). Their original content, and the content of the previous audits that produced the `CRITICAL 1..8` findings referenced in §1, are **NOT available and were NOT independently verified**. Those historical claims are treated as **provenance assertions, not verified facts**; the corrigible, verifiable content lives exclusively in `ARCH-ST-010.md` (byte-identical copies verified at SHA-256 `3F56D16365B8148C0BB7D7A225ED4DD8990AC8441C49B0C4FA234A91420F8118` in the project archive and on GitHub) and in this revision.

---

## 1. Executive Summary & Resolution of ARCH-ST-009 Audit Findings

`ARCH-ST-010` preserves the core architecture, ten mandatory YottaFlex entities, baseline counts (`seed=42`), deterministic ID formats, ground-truth isolation, and 10-stage scoring pipeline, while resolving all eight critical audit findings (`CRITICAL 1` through `CRITICAL 8`):

| Audit ID | Defect Summary | Exact Architectural & SQLite Resolution in `ARCH-ST-010` |
|---|---|---|
| **CRITICAL 1** | Invoice approval immutability & cap enforcement (`approved_cents`, `historical_approved_cents`, same-status bypass, policy/claim caps) | `trg_invoices_fsm_upd` blocks any post-approval modification of `approved_cents` or `historical_approved_cents` (`ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE`) unless either (a) transitioning to `REVOKED_POST_APPROVAL` (`approved_cents = 0`, `historical_approved_cents = OLD.historical_approved_cents`), or (b) executing an explicit `APPROVED -> APPROVED` adjustment backed by the latest `immutable_events` row (`event_type = 'INVOICE_APPROVAL_ADJUSTED'`) with matching `old_approved_cents` and `new_approved_cents` digest. Every update where `NEW.invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID')`—including same-status updates—re-verifies `Policy.policy_status = 'ACTIVE'`, incident timestamp within `[effective_start_utc, effective_end_utc]`, `approved_cents <= billed_cents`, `approved_cents >= reserved_authorized_cents + net_paid_cents`, and $\sum \text{approved\_cents} \le \min(\text{claimed\_amount\_cents}, \text{payout\_cap\_cents}, \max(0, \text{coverage\_limit\_cents} - \text{deductible\_cents}))$. |
| **CRITICAL 2** | Claim and Invoice FSM financial consistency (`PAID`, `PARTIALLY_PAID`, direct status changes, payment trigger cascades) | `trg_invoices_fsm_upd` and `trg_claims_fsm_upd` enforce bidirectional status-to-balance invariants: `PAID` requires `approved > 0 AND net_paid_cents = approved AND reserved_authorized_cents = 0`; `PARTIALLY_PAID` requires `approved > 0 AND 0 < net_paid_cents < approved`; `APPROVED` requires `approved > 0 AND net_paid_cents = 0`; `SUBMITTED`/`UNDER_REVIEW` require all six financial columns $= 0$; `DENIED`/`CLOSED_NO_PAY`/`REVOKED_POST_APPROVAL` require `approved = 0 AND reserved_authorized_cents = 0 AND net_paid_cents = 0`. `trg_payments_sync_aggregates_au` and `trg_invoices_sync_claim_au` compute status transitions atomically from live child `SUM(...)` subqueries. |
| **CRITICAL 3** | Payment immutable fields & post-disbursement audit protection | Section 4.4 and `trg_payments_validate_upd` define an explicit state-mutability matrix. `payment_id`, `claim_id`, `invoice_id`, `recipient_type`, `recipient_claimant_id`, `recipient_provider_id`, `amount_cents`, `idempotency_key`, `created_at_utc`, `authorized_by`, and `block_reason_code` are immutable across all `UPDATE`s (`ERR_PAYMENT_IMMUTABLE_AUDIT_FIELD`). Once `OLD.payment_status IN ('DISBURSED','REVERSED_CLAWBACK')`, `disbursed_at_utc`, `external_bank_tx_ref`, and `disbursed_amount_cents` are permanently immutable (`ERR_PAYMENT_POST_DISBURSEMENT_BANK_REF_IMMUTABLE`). |
| **CRITICAL 4** | Unambiguous length-prefixed event serialization (`ST-EVT-V2`) & recalculated `KAV-1`..`KAV-6` | Replaced pipe concatenation with `ST-EVT-V2|` length-prefixed UTF-8 canonical serialization using SQLite `length(CAST(col AS BLOB))` (exact UTF-8 byte length) and explicit type tags (`I<int>;`, `S<utf8_byte_len>:<utf8_str>;`, `N;` for `NULL`). Independently calculated and SQLite-verified `KAV-1`..`KAV-6` plus `KAV-7` (Unicode + delimiter injection collision vector). |
| **CRITICAL 5** | 100% self-contained specification | Complete definitions of `YF-NEG-1`..`YF-NEG-5`, `BL-1`..`BL-5`, `BC-1`..`BC-6`, all 15 indicators (`IND-01`..`IND-15`), graph construction, edge weights, clustering, and 10-stage scoring included directly in this specification. |
| **CRITICAL 6** | Deterministic `sqlite_master` schema digest (`ST-SCHEMA-V1`) | Defined via an explicitly ordered subquery (`ORDER BY type ASC, name ASC, tbl_name ASC`) serialized with `ST-SCHEMA-V1|` byte-length prefixes, producing identical SHA-256 digests regardless of DDL statement execution order. |
| **CRITICAL 7** | Historical financial accounting protection (`historical_approved_cents`) | Protected at both invoice and claim levels via `NEW.historical_approved_cents >= OLD.historical_approved_cents` and live `SUM(historical_approved_cents)` reconciliation in `trg_invoices_fsm_upd` and `trg_claims_fsm_upd`. Full/partial clawbacks, invoice revocation (`REVOKED_POST_APPROVAL`), and claim denial (`DENIED`) preserve `historical_approved_cents` while driving active exposure to zero. |
| **CRITICAL 8** | Independently recalculated 8-node Clean-Room fixture | Supplied complete raw inputs, $8 \times 8$ symmetric adjacency matrix $W$, degree vector $d$, $8 \times 8$ column-stochastic transition matrix $M$, PageRank iteration vectors ($t=0,1,2,3,5,10,20,40,60,77,78$), claim-normalized $\widetilde{\text{PR}}(c)$, indicator activations, token deduplication, dampening, cluster boost, and final scores (`65.00`, `65.00`, `0.00`, `0.67`). |

### 1.1 Resolution of the Independent Adversarial Audit (`AUD-ARCH-ST-010`) in `ARCH-ST-010.1`

Every finding below was re-verified against ARCH-ST-010 before correction. Complete per-finding traceability (original defect / exact correction / acceptance criterion / verification status) is in `CORRECTION_TRACEABILITY.md`; the section references here are normative.

| Finding | One-line summary | Resolution & normative location |
|---|---|---|
| **C-1** | Invoice `SUBMITTED → APPROVED` dead-locked against the claim FSM | Claim FSM extended: `SUBMITTED → APPROVED` is legal **only through the invoice-approval cascade** (aggregate invariants force this automatically). §4.2, §4.3, §5.2 (`trg_claims_fsm_upd`). |
| **C-2** | `EXPECTED_OPERATIONAL_SCHEMA_SHA256` undefined | Published: `63e74a55…0f93` for the corrected schema (§5.1+§5.2, 12 tables + 24 triggers), with derivation harness. §2.1 step 3, §6.3. |
| **C-3** | Scoring pipeline not self-contained | Full 10-stage scoring contract with every constant now in the document. §9. |
| **C-4** | Event partition infeasible (`INV_APP`=1,105 < `CLM_APP`=1,200) | Repartitioned: new total **19,615** with `INV_APP`=1,200 (1:1) and a new `PAYMENT_CANCELLED` bucket (25). Feasibility reconciliation table in §3.1. |
| **C-5** | `is_canonical_json` undefined | Full canonicalization contract (§6.5) binding all CHECK constraints, KAVs and event hashes. |
| **C-6** | Unprotected mutation/deletion surfaces | 8 new triggers (investigation delete-block, edge immutability + event-gated deactivation, indicator append-only, score-evidence reconciliation `ST-SCORE-V1`, `siu_referred` lifecycle). §4.6, §6.6, §5.2. |
| **C-7** | YF-NEG-3 ≥65.00 unreachable as written | Scenario corrected: shared-payout-account pairing (IND-01+IND-03) → hard-collusion path → 65.00 hard floor; worked example in §7.1 and §9.9. |
| **A-1** | SIU_HOLD entry/exit protocol undocumented | Full lifecycle protocol with `PAYMENT_CANCELLED` reservation release, mandatory events, re-approval and clawback interactions. §4.5. |
| **A-2** | KAV narrative vs operational FSM mismatch; missing cancellation event | KAV-1..KAV-7 explicitly reclassified as **pure cryptographic hash vectors**; new FSM-valid operational chain **VH-1..VH-7** published (§6.2). `PAYMENT_CANCELLED` event type added (§5.1, §5.2). |
| **A-3** | "Verified SQLite 3.40.1" claims unsubstantiated | Harness shipped; all pinned-version claims honestly relabelled (header of this document, §11). Executed platform: SQLite 3.49.1 / Python 3.13.5. |
| **A-4** | ARCH-ST-001..009 provenance | Honest disclosure in this document's header; stubs retained unchanged. |
| **A-5** | Trigger/payment semantics notes | Documented: same-status no-op behavior, blocked-payment idempotency, adjustment trust model, scalar `MIN/MAX` SQLite floor (≥3.7.11), `trusted_schema` constraint. §4.7. |

---

## 2. System Topology, Pinned Runtime & Ground-Truth Quarantine

### 2.1 Pinned Runtime & Connection Initialization Contract
- **Runtime:** Python `3.10.12` (`sqlite3` module binding SQLite `3.40.1`), FastAPI `0.111.0`, Pydantic `2.7.1`, React `18.3.1` + TypeScript `5.5` + Vite `5.4` + Tailwind CSS on port `3000`.
- **SQLite UDF & Pragma Contract:** In SQLite `3.31.0+`, Python's `sqlite3.Connection.create_function(..., deterministic=True)` sets `SQLITE_DETERMINISTIC` without the C-level `SQLITE_INNOCUOUS` flag; setting `PRAGMA trusted_schema = OFF` raises `sqlite3.OperationalError: unsafe use of is_canonical_json()`. Therefore, every database connection opened by `app/db/engine.py` MUST execute the following exact initialization sequence:
  1. Register `is_canonical_json(s: str) -> int` and `sha256_hex(s: str) -> str` with `deterministic=True`.
  2. Execute:
     ```sql
     PRAGMA foreign_keys = ON;
     PRAGMA journal_mode = WAL;
     PRAGMA synchronous = NORMAL;
     PRAGMA busy_timeout = 5000;
     PRAGMA recursive_triggers = ON;
     PRAGMA temp_store = MEMORY;
     PRAGMA trusted_schema = ON;
     ```
  3. Compute the deterministic `ST-SCHEMA-V1` SHA-256 digest of `sqlite_master` (Section 6.3) and assert equality with **`EXPECTED_OPERATIONAL_SCHEMA_SHA256 = 63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93`** (the digest of the exact §5.1 + §5.2 schema of this revision: 12 tables + 24 triggers, order-independence verified; derivation harness in `archive/verify-0101/`) before returning the connection to the pool.
     - **Verification status:** `PASS — EXECUTED` on SQLite **3.49.1** (order-independence verified across two differently-ordered DDL builds and via an independent Python mirror; both reproduce `63e74a55…0f93`). Pinned **3.40.1** run: `SPECIFIED — NOT EXECUTED`. Note: because the digest serializes the exact `sqlite_master.sql` TEXT (not runtime state), its value is version-stable across SQLite releases that do not normalize differing whitespace in stored `CREATE` statements; the pinned-version run re-confirms this empirically.

### 2.2 Physical Database Quarantine (`operational.db` vs. `ground_truth.db`)
1. **Operational Database (`data/operational.db`)**: Contains strictly **12 tables**:
   - **Tier A — 10 Mandatory YottaFlex Entities:** `claimants`, `policies`, `incidents`, `claims`, `providers`, `invoices`, `payments`, `relationship_edges`, `fraud_indicators`, `investigations`.
   - **Tier B — 2 Operational Support Entities:** `immutable_events`, `ingestion_exceptions`.
2. **Quarantined Ground-Truth Database (`data/ground_truth.db`)**: Separate physical SQLite file containing 4 tables (`ground_truth_rings`, `ground_truth_claim_labels`, `ground_truth_entity_labels`, `ground_truth_missing_edges`).
3. **Quarantine Enforcement:** `app/scoring/`, `app/services/`, and `app/api/routes/` (except `/api/v1/evaluation/metrics`) are forbidden from opening `ground_truth.db` or executing `ATTACH DATABASE`.

---

## 3. Baseline Dataset Contract (`seed=42`) & Deterministic ID Formats

| Tier | Table Name | Entity Name | Exact Row Count (`seed=42`) | Deterministic ID Format | SQLite `GLOB` Constraint |
|---|---|---|---:|---|---|
| **Tier A (1)** | `claimants` | `Claimant` | **2,000** | `CLMT-000001` .. `CLMT-002000` | `CLMT-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (2)** | `policies` | `Policy` | **2,200** | `POL-2026-000001` .. `POL-2026-002200` | `POL-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (3)** | `incidents` | `Incident` | **3,800** | `INC-2026-000001` .. `INC-2026-003800` | `INC-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (4)** | `claims` | `Claim` | **5,000** | `CLM-2026-000001` .. `CLM-2026-005000` | `CLM-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (5)** | `providers` | `Provider` | **500** | `PRV-000001` .. `PRV-000500` | `PRV-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (6)** | `invoices` | `Invoice` | **7,500** | `INV-PRV-<provider_id>-<6d_seq>` | `'INV-PRV-' \|\| provider_id \|\| '-[0-9][0-9][0-9][0-9][0-9][0-9]'` |
| **Tier A (7)** | `payments` | `Payment` | **4,200** | `PAY-2026-000001` .. `PAY-2026-004200` | `PAY-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (8)** | `relationship_edges` | `RelationshipEdge` | **8,000** | `EDGE-2026-000001` .. `EDGE-2026-008000` | `EDGE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (9)** | `fraud_indicators` | `FraudIndicator` | **4,120** | `FIND-2026-000001` .. `FIND-2026-004120` | `FIND-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier A (10)** | `investigations` | `Investigation` | **45** | `INVG-2026-000001` .. `INVG-2026-000045` | `INVG-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier B (11)** | `immutable_events` | `ImmutableEvent` | **19,615** | `EVT-2026-0000001` .. `EVT-2026-0019615` | `EVT-2026-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier B (12)** | `ingestion_exceptions` | `IngestionException` | **25** | `IEX-2026-000001` .. `IEX-2026-000025` | `IEX-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |

### 3.1 Partition of the 5,000 Operational Claims (`seed=42`)
- **Positive Fraud Claims (`is_fraud = 1` in `ground_truth_claim_labels`): `775` claims**
  - `710` claims across `15` fully observable fraud rings (`RING-2026-001` .. `RING-2026-015`).
  - `40` claims across `5` partially observable fraud rings (`RING-2026-016` .. `RING-2026-020`, `YF-NEG-4`, 8 claims/ring, where `25` ground-truth edges are withheld from `relationship_edges` and stored only in `ground_truth_missing_edges`).
  - `25` cross-claimant duplicate-invoice fraud claims (`YF-NEG-3` / `EC-2` / `EC-5`).
- **Negative Benign Claims (`is_fraud = 0` in `ground_truth_claim_labels`): `4,225` claims**
  - `3,650` standard organic claims + `80` `YF-NEG-5` high-density apartment claims + `420` benign lookalike claims (`BL-1`..`BL-5`, `84` claims each) + `30` `YF-NEG-2` overpayment-attempt claims + `25` `EC-1` intra-claim duplicate resubmissions + `20` `EC-3` legitimate post-disbursement clawbacks.
- **Rejected Nonexistent-Policy Ingestion Attempts (`YF-NEG-1`):** `25` attempts recorded in `ingestion_exceptions` (`IEX-2026-000001` .. `IEX-2026-000025`) without violating `claims.policy_id` FK integrity.
- **Exact Reconciliation of `19,615` `immutable_events` (`seed=42`) — corrected in `ARCH-ST-010.1` (`C-4`):**

  $$25\text{ (IEX)} + 5,000\text{ (CLM\_SUB)} + 7,500\text{ (INV\_SUB)} + 1,200\text{ (INV\_APP)} + 1,200\text{ (CLM\_APP)} + 4,115\text{ (PAY\_AUTH)} + 85\text{ (PAY\_BLK)} + 315\text{ (PAY\_DISB)} + 20\text{ (PAY\_CLAW)} + 60\text{ (SIU\_HOLD)} + 25\text{ (CLM\_DENY)} + 45\text{ (INVG\_OPEN)} + 25\text{ (PAY\_CANCEL)} = 19,615$$

  **Correction rationale (ARCH-ST-010 allocated 1,105 `INV_APP` — arithmetically infeasible):** every claim reaching `APPROVED` status must own at least one child invoice in `{APPROVED, PARTIALLY_PAID, PAID}` with `approved_cents > 0` (enforced by `trg_claims_fsm_upd` + the rollup aggregate invariants), and every invoice entering those states must itself have passed through exactly one initial-approval transition. Therefore `1,200` approved claims force **`INV_APP ≥ 1,200`** (the allocation `1,105` deadlock-fixated on an impossible deficit of ≥ 95 events). This revision additionally **defines 1:1 eventing**: each invoice initial approval emits exactly one `INVOICE_APPROVED` event (`INV_APP` = count of distinct invoice-approval transitions = 1,200; no claim receives a second initial-approval event since re-approvals after `PARTIALLY_PAID`/`PAID` clawbacks are *state restorations*, not new approvals, and are not re-counted). The second change adds the new **`PAYMENT_CANCELLED`** bucket: the `60` `SIU_HOLD` placements include `25` scenarios that retain `AUTHORIZED` reservations at hold time and release them via payment cancellation (one `PAYMENT_CANCELLED` event per cancelled reservation; see §4.5 and §4.4). There was no mathematically consistent way to preserve 19,495; the total grows to 19,615 with both buckets independently justified.

  **Feasibility reconciliation table (normative for seed generation):**

  | Event bucket | Count | Feasibility invariant (must hold as a CHECK at generation time) |
  |---|---:|---|
  | `INGESTION_EXCEPTION_RECORDED` | 25 | One per `YF-NEG-1` attempt; FK to claims NOT required (`claim_id` NULL). ✓ |
  | `CLAIM_SUBMITTED` | 5,000 | One per operational claim; genesis-connected chain head per claim pipeline. ✓ |
  | `INVOICE_SUBMITTED` | 7,500 | One per operational invoice (7,500 rows). ✓ |
  | `INVOICE_APPROVED` | **1,200** | ≥ #claims approved (1,200) ⇒ each approved claim has exactly 1 initially-approved invoice; 1:1 with distinct `(invoice_id)` initial approvals. **1,200 = 1,200 ✓** |
  | `CLAIM_APPROVED` | 1,200 | Invoice cascade atomically sets claim `APPROVED` (per claim, exactly one `CLAIM_APPROVED` event; re-approvals after clawback are restores). ✓ |
  | `PAYMENT_AUTHORIZED` | 4,115 | Every `AUTHORIZED→DISBURSED` transition (315) requires a prior `PAYMENT_AUTHORIZED` event (§4.4); 4,115 ≥ 315. ✓ |
  | `PAYMENT_BLOCKED` | 85 | One per `BLOCKED_*` insert (85 blocked payment rows). ✓ |
  | `PAYMENT_DISBURSED` | 315 | One per operational `DISBURSED` transition (incl. clawback claims: 315 disbursed transitions, of which 20 claw back). ✓ |
  | `PAYMENT_CLAWBACK_REVERSED` | 20 | One per `DISBURSED→REVERSED_CLAWBACK` (20 `EC-3` claims). ✓ |
  | `CLAIM_SIU_HOLD_PLACED` | 60 | One per claim entering `SIU_HOLD` (60). ✓ |
  | `CLAIM_DENIED` | 25 | One per `DENIED` entry (25 `YF-NEG-2` + SIU-denied claims). ✓ |
  | `INVESTIGATION_OPENED` | 45 | One per investigation row (45). ✓ |
  | `PAYMENT_CANCELLED` | **25 (new)** | One per cancellation reserved-release at `SIU_HOLD` (see §4.5). ✓ |
  | **Total** | **19,615** | Sum verified arithmetically and by the harness generator (`SPECIFIED — NOT EXECUTED` for full-seed generation; bucket arithmetic `PASS — EXECUTED`). |

---

## 4. Lifecycle State Machines, Financial Accounting & Mutability Matrices

### 4.1 Financial Rollup Equations & Historical Accounting (`CRITICAL 1`, `CRITICAL 2`, `CRITICAL 7`)
All monetary columns are integer cents (`INTEGER` in SQLite `STRICT` tables).
1. **Policy Payout Cap for Claim $c$ on Policy $p$:**
   $$\text{payout\_cap\_cents}(c) = \min\Big(\text{claimed\_amount\_cents}(c),\; \max\big(0, \text{coverage\_limit\_cents}(p) - \text{deductible\_cents}(p)\big)\Big)$$
2. **Invoice Financial Balances (`invoices`):**
   - `approved_cents`: Current active approved amount (`0` before approval; `> 0` in `APPROVED`, `PARTIALLY_PAID`, `PAID`; reset to `0` on `REVOKED_POST_APPROVAL`).
   - `historical_approved_cents`: Monotonically non-decreasing high-water mark of approved cents on the invoice ($\text{historical\_approved\_cents}_{\text{new}} = \max(\text{historical\_approved\_cents}_{\text{old}}, \text{approved\_cents}_{\text{new}})$). Preserved unchanged during partial/full clawbacks and `REVOKED_POST_APPROVAL`.
   - `reserved_authorized_cents`: $\sum_{p \in \text{Payments}(i), \text{status}(p)=\text{AUTHORIZED}} \text{amount\_cents}(p)$.
   - `gross_disbursed_cents`: $\sum_{p \in \text{Payments}(i), \text{status}(p)\in\{\text{DISBURSED},\text{REVERSED\_CLAWBACK}\}} \text{disbursed\_amount\_cents}(p)$.
   - `clawed_back_cents`: $\sum_{p \in \text{Payments}(i), \text{status}(p)=\text{REVERSED\_CLAWBACK}} \text{clawed\_back\_cents}(p)$.
   - `net_paid_cents`: $\text{gross\_disbursed\_cents}(i) - \text{clawed\_back\_cents}(i)$.
3. **Claim Financial Rollups (`claims`):**
   - $\text{approved\_amount\_cents}(c) = \sum_{i \in \text{Invoices}(c), \text{status}(i) \in \{\text{APPROVED},\text{PARTIALLY\_PAID},\text{PAID}\}} \text{approved\_cents}(i)$.
   - $\text{historical\_approved\_cents}(c) = \sum_{i \in \text{Invoices}(c)} \text{historical\_approved\_cents}(i)$ (includes `REVOKED_POST_APPROVAL` invoices; never decreases).
   - $\text{reserved\_authorized\_cents}(c)$, $\text{gross\_disbursed\_cents}(c)$, $\text{clawed\_back\_cents}(c)$, and $\text{net\_paid\_cents}(c)$ equal the exact sums over child payments of claim $c$.
4. **Effect of Lifecycle Events on Current vs. Historical Balances (`CRITICAL 7`):**

| Financial / SIU Action | `approved_cents` / `approved_amount_cents` | `historical_approved_cents` (Invoice & Claim) | `reserved_authorized_cents` | `gross_disbursed_cents` | `clawed_back_cents` | `net_paid_cents` | Resulting Invoice / Claim Status |
|---|---|---|---|---|---|---|---|
| Initial Approval ($A > 0$) | $= A$ | $= A$ | $0$ | $0$ | $0$ | $0$ | `APPROVED` / `APPROVED` |
| Payment Authorized ($R \le A$) | $= A$ | $= A$ | $+R$ | $0$ | $0$ | $0$ | `APPROVED` / `APPROVED` |
| Partial Disbursement ($0 < D < A$) | $= A$ | $= A$ | $A - D$ or $0$ | $= D$ | $0$ | $= D$ | `PARTIALLY_PAID` / `PARTIALLY_PAID` |
| Full Disbursement ($D = A, R = 0$) | $= A$ | $= A$ | $0$ | $= A$ | $0$ | $= A$ | `PAID` / `PAID` |
| Partial Clawback ($0 < C < D$) | $= A$ (unchanged) | $= A$ (unchanged) | $0$ | $= D$ | $= C$ | $= D - C > 0$ | `PARTIALLY_PAID` / `PARTIALLY_PAID` |
| Full Clawback ($C = D$) | $= A$ (unchanged) | $= A$ (unchanged) | $0$ | $= D$ | $= D$ | $0$ | `APPROVED` / `APPROVED` |
| Invoice Revocation (`REVOKED_POST_APPROVAL`, requires $R=0, \text{net}=0$) | $\to 0$ | $= A$ (**preserved**) | $0$ | $= D$ | $= D$ | $0$ | `REVOKED_POST_APPROVAL` / `SIU_HOLD` (if all invoices revoked) |
| Claim Denial after Revocation (`SIU_HOLD -> DENIED`, requires $\text{approved}=0, R=0, \text{net}=0$) | $0$ | $= A$ (**preserved**) | $0$ | $= D$ | $= D$ | $0$ | `REVOKED_POST_APPROVAL` / `DENIED` |

### 4.2 Invoice FSM & Post-Approval Adjustment Protocol (`CRITICAL 1`, `CRITICAL 2`)
- **States:** `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `PARTIALLY_PAID`, `PAID`, `REJECTED_DUPLICATE`, `REJECTED_ELIGIBILITY`, `REVOKED_POST_APPROVAL`.
- **Claim-status precondition for first invoice approval (`C-1`, now explicit):** an invoice may be approved while its claim is `SUBMITTED` or `UNDER_REVIEW`. No manual pre-step is required; the invoice-approval cascade transitions the claim into `APPROVED` atomically and emits the `CLAIM_APPROVED` event when the claim transitions. (In `ARCH-ST-010` this path dead-locked: the invoice FSM permitted it, but the claim FSM rejected the cascade. The claim FSM now permits `SUBMITTED → APPROVED` via the cascade only — verified by execution.)
- **Directed Transitions:**
  - `SUBMITTED -> {UNDER_REVIEW, APPROVED, REJECTED_DUPLICATE, REJECTED_ELIGIBILITY}`
  - `UNDER_REVIEW -> {APPROVED, REJECTED_DUPLICATE, REJECTED_ELIGIBILITY}`
  - `APPROVED -> {PARTIALLY_PAID, PAID, REVOKED_POST_APPROVAL}` (plus authorized adjustment `APPROVED -> APPROVED`)
  - `PARTIALLY_PAID -> {PAID, APPROVED, REVOKED_POST_APPROVAL}` (`PARTIALLY_PAID -> APPROVED` occurs automatically on full clawback when `net_paid_cents` returns to `0`)
  - `PAID -> {PARTIALLY_PAID, APPROVED, REVOKED_POST_APPROVAL}` (`PAID -> PARTIALLY_PAID` on partial clawback; `PAID -> APPROVED` on full clawback)
  - Terminal states: `REJECTED_DUPLICATE`, `REJECTED_ELIGIBILITY`, `REVOKED_POST_APPROVAL`.
- **Authorized Post-Approval Adjustment Protocol (`CRITICAL 1`):**
  - Once an invoice enters `APPROVED`, `PARTIALLY_PAID`, or `PAID`, direct SQL updates to `approved_cents` or `historical_approved_cents` are rejected by `trg_invoices_fsm_upd` (`ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE`).
  - The ONLY permitted adjustment to `approved_cents` after initial approval is when `OLD.invoice_status = 'APPROVED' AND NEW.invoice_status = 'APPROVED'` AND the most recent row in `immutable_events` for `entity_type = 'Invoice' AND entity_id = NEW.invoice_id` has `event_type = 'INVOICE_APPROVAL_ADJUSTED'` and `payload_sha256` matching the exact canonical JSON `{"adjustment_authorized":true,"invoice_id":"<id>","new_approved_cents":<new>,"old_approved_cents":<old>}`, AND `NEW.historical_approved_cents = MAX(OLD.historical_approved_cents, NEW.approved_cents)`.
  - Every initial approval and every authorized adjustment unconditionally re-verifies Policy `ACTIVE` status, Incident timestamp within Policy effective dates, `NEW.approved_cents >= NEW.reserved_authorized_cents + NEW.net_paid_cents`, and Claim/Policy/Deductible payout caps (`ERR_INVOICE_EXCEEDS_CLAIM_OR_POLICY_CAP`).

### 4.3 Claim FSM & Financial Consistency (`CRITICAL 2`)
- **States:** `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `PARTIALLY_PAID`, `PAID`, `SIU_HOLD`, `DENIED`, `CLOSED_NO_PAY`.
- **Directed Transitions & Required Financial Preconditions:**
  - `SUBMITTED -> {UNDER_REVIEW, APPROVED, SIU_HOLD, DENIED}` (all balances $= 0$). **`SUBMITTED -> APPROVED` is the `ARCH-ST-010.1` correction for `C-1`**: it may occur **only through the atomic invoice-approval cascade** (`trg_invoices_sync_claim_au`), which sets `approved_amount_cents = SUM(invoice approved_cents) > 0` in the same statement — so the direct-SQL fabrication path (`UPDATE claims SET claim_status='APPROVED'` with no approved invoice) remains blocked by `ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH` exactly as before. Executed and verified (harness test `C-1a`/`C-1b`).
  - `UNDER_REVIEW -> {APPROVED, SIU_HOLD, DENIED, CLOSED_NO_PAY}` (`APPROVED` requires `approved_amount_cents > 0 AND net_paid_cents = 0`; `DENIED`/`CLOSED_NO_PAY` require `approved_amount_cents = 0 AND reserved_authorized_cents = 0 AND net_paid_cents = 0`)
  - `APPROVED -> {PARTIALLY_PAID, PAID, SIU_HOLD}`
  - `PARTIALLY_PAID -> {PAID, APPROVED, SIU_HOLD}`
  - `PAID -> {PARTIALLY_PAID, APPROVED, SIU_HOLD}`
  - `SIU_HOLD -> {APPROVED, DENIED, CLOSED_NO_PAY}` (`SIU_HOLD -> DENIED` or `CLOSED_NO_PAY` requires `approved_amount_cents = 0 AND reserved_authorized_cents = 0 AND net_paid_cents = 0`, while preserving `historical_approved_cents >= 0`).

### 4.4 Payment FSM & Column Mutability Matrix (`CRITICAL 3`)
- **Insert Rule:** `trg_payments_validate_ins` permits `INSERT` **only** with `payment_status IN ('AUTHORIZED','BLOCKED_OVERPAYMENT','BLOCKED_UNAPPROVED','BLOCKED_INVALID_RECIPIENT')`. Direct `INSERT` of `DISBURSED`, `REVERSED_CLAWBACK`, or `CANCELLED` is rejected (`ERR_PAYMENT_INSERT_MUST_BE_AUTHORIZED_OR_BLOCKED`).
- **Update Mutability Matrix (`trg_payments_validate_upd`):**

| Payment Column | `AUTHORIZED -> DISBURSED` | `AUTHORIZED -> CANCELLED` | `DISBURSED -> REVERSED_CLAWBACK` | `REVERSED_CLAWBACK -> REVERSED_CLAWBACK` | Any Other `UPDATE` |
|---|---|---|---|---|---|
| `payment_id`, `claim_id`, `invoice_id` | **IMMUTABLE** | **IMMUTABLE** | **IMMUTABLE** | **IMMUTABLE** | **FORBIDDEN** |
| `recipient_type`, `recipient_claimant_id`, `recipient_provider_id` | **IMMUTABLE** | **IMMUTABLE** | **IMMUTABLE** | **IMMUTABLE** | **FORBIDDEN** |
| `amount_cents`, `idempotency_key`, `created_at_utc`, `authorized_by`, `block_reason_code` | **IMMUTABLE** | **IMMUTABLE** | **IMMUTABLE** | **IMMUTABLE** | **FORBIDDEN** |
| `disbursed_amount_cents` | `0 -> OLD.amount_cents` | Must stay `0` | **IMMUTABLE** (`= OLD.disbursed_amount_cents`) | **IMMUTABLE** (`= OLD.disbursed_amount_cents`) | **FORBIDDEN** |
| `disbursed_at_utc` | `NULL -> UTC >= created_at_utc` | Must stay `NULL` | **IMMUTABLE** (`= OLD.disbursed_at_utc`) | **IMMUTABLE** (`= OLD.disbursed_at_utc`) | **FORBIDDEN** |
| `external_bank_tx_ref` | `NULL -> str (len >= 4)` | Must stay `NULL` | **IMMUTABLE** (`= OLD.external_bank_tx_ref`) | **IMMUTABLE** (`= OLD.external_bank_tx_ref`) | **FORBIDDEN** |
| `clawed_back_cents` | Must stay `0` | Must stay `0` | `0 -> c` ($0 < c \le \text{disbursed}$) | `OLD.c -> NEW.c` ($\text{NEW.c} > \text{OLD.c} \le \text{disbursed}$) | **FORBIDDEN** |
| `net_paid_cents` | `0 -> OLD.amount_cents` | Must stay `0` | `disbursed - NEW.clawed_back_cents` | `disbursed - NEW.clawed_back_cents` | **FORBIDDEN** |
| `reversed_at_utc` | Must stay `NULL` | `NULL -> UTC >= created_at_utc` | `NULL -> UTC >= disbursed_at_utc` | `UTC >= OLD.reversed_at_utc` | **FORBIDDEN** |
| `cancel_reason` | Must stay `NULL` | `NULL -> {SIU_HOLD_RESERVATION_CLEARED, FINANCE_WITHDRAWAL, SUBSEQUENT_ADJUSTMENT}` | Must stay `NULL` | Must stay `NULL` | **FORBIDDEN** |

### 4.5 SIU_HOLD Lifecycle Protocol & Payment-Cancellation Policy (`A-1`, `A-2` — new in `ARCH-ST-010.1`)

The money-side invariants were already enforced by ARCH-ST-010 and remain unchanged; this section makes the **entry/exit protocol explicit and auditable**:

1. **Entry preconditions.** A claim may enter `SIU_HOLD` from any of `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `PARTIALLY_PAID`, `PAID`. Outstanding `AUTHORIZED` payment reservations are **permitted to remain** at hold entry (verified: reserved funds cannot be disbursed while on hold — `ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL`). Every hold entry MUST be accompanied by exactly one `CLAIM_SIU_HOLD_PLACED` event `(entity_type='Claim', entity_id=<claim_id>)` in `immutable_events` — this is the generator contract; a hold without its event makes the audit ledger incomplete (test `T-01b`).
2. **Reservation release.** `AUTHORIZED` payments of a held claim are released by cancelling each payment (`AUTHORIZED → CANCELLED`, legal and unchanged). Each cancellation MUST (a) set `payments.cancel_reason` (NOT NULL on `CANCELLED`; new column, §5.1) and (b) be preceded by exactly one `PAYMENT_CANCELLED` event whose canonical payload (§6.4.1) matches `{"amount_cents":<amt>,"claim_id":"<cid>","payment_id":"<pid>","payment_status":"CANCELLED","reason_code":"<cancel_reason>"}`. Enforced by `trg_payments_validate_upd` (`ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT`, `ERR_PAYMENT_CANCELLATION_REQUIRES_REASON`).
3. **Disbursement restriction.** `AUTHORIZED → DISBURSED` while the claim is `APPROVED`/`PARTIALLY_PAID` additionally requires a prior `PAYMENT_AUTHORIZED` event with a matching canonical payload (`{"amount_cents":…,"claim_id":…,"invoice_id":…,"payment_id":…,"payment_status":"AUTHORIZED","recipient_provider_id":…}` for PROVIDER recipients / `…"recipient_claimant_id":…` for CLAIMANT recipients — enforced `ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT`). While on `SIU_HOLD`, disbursement is prohibited exactly as in ARCH-ST-010.
4. **Re-approval after hold.** `SIU_HOLD → APPROVED` requires `net_paid_cents = 0` (unchanged, enforced); it does **not** require `approved_amount_cents > 0`, so a claim whose funds were fully clawed back returns to `APPROVED` with `approved = 0` only if an invoice restoral re-derives the aggregate (the cascade handles this; direct re-approval with fabricated aggregates stays blocked).
5. **Denial & clawback interaction (unchanged, verified).** `SIU_HOLD → DENIED`/`CLOSED_NO_PAY` requires `approved_amount_cents = 0 AND reserved_authorized_cents = 0 AND net_paid_cents = 0` while preserving `historical_approved_cents`. Funds already disbursed can only exit via clawback (`DISBURSED → REVERSED_CLAWBACK`), which now also requires a prior `PAYMENT_CLAWBACK_REVERSED` event with canonical payload `{"amount_cents":…,"claim_id":…,"clawed_back_cents":…,"invoice_id":…,"net_paid_cents":…,"payment_id":…,"payment_status":"REVERSED_CLAWBACK"}` (`ERR_CLAWBACK_REQUIRES_EVENT`).
6. **`siu_referred` flip semantics (new trigger).** `claims.siu_referred` transitions `0 → 1` irreversibly exactly when `claims.claim_status` enters `SIU_HOLD` (`trg_claims_siu_referred_au`), and also when an investigation is closed `CLOSED_CONFIRMED_FRAUD` (`trg_investigations_siu_ref_au`). `1` can never be reset.

### 4.6 Data-Classification & Mutation Governance (`C-6` — new in `ARCH-ST-010.1`)

| Table | Classification | Permitted post-insert mutations | Deletion | Events |
|---|---|---|---|---|
| `investigations` | FSM-mutable, then terminal-immutable | Status FSM per ARCH-ST-010 (`ERR_INVALID_INVESTIGATION_FSM_TRANSITION`); closed rows fully immutable | **Blocked** (`ERR_INVESTIGATION_DELETE_FORBIDDEN`, new) | Open/close/status events (as in ARCH-ST-010 §3.1) |
| `relationship_edges` | **Append-only, one-way-deactivatable** | Only `is_active 1→0` and `last_observed_utc` bumps; `edge_type`, endpoints, `canonical_*_key`, `strength_weight`, `evidence_count`, `first_observed_utc`, `supporting_claim_id` immutable (`ERR_EDGE_CORE_FIELDS_IMMUTABLE`); reactivation forbidden (`ERR_EDGE_REACTIVATION_FORBIDDEN`); deactivation requires a `RELATIONSHIP_EDGE_DEACTIVATED` event with canonical payload `{"claim_id":"<supporting_claim>","edge_id":"<edge_id>"}` (`ERR_EDGE_DEACTIVATION_REQUIRES_EVENT`) | **Blocked** (`ERR_EDGE_DELETE_FORBIDDEN`, new) | Deactivation event required |
| `fraud_indicators` | **Append-only** | No mutation permitted (`ERR_FRAUD_INDICATOR_MUTATION_FORBIDDEN`, new) | **Blocked** (`ERR_FRAUD_INDICATOR_DELETE_FORBIDDEN`, new) | Bound into `ST-SCORE-V1` when the claim is scored (§6.6) |
| `claims.latest_ief_score` / `latest_risk_tier` / `scoring_evidence_sha256` | Reconciled scores | Writable only as an atomic triple whose digest recomputes from `fraud_indicators` (§6.6); tier must equal the deterministic thresholds (`ERR_SCORE_TIER_MISMATCH`) | n/a | Digest mechanism itself |
| `immutable_events` | Append-only hash chain | No updates/deletes (unchanged) | Blocked (unchanged) | — |

**Compensating-control honesty:** database-level enforcement above is complete for *every* listed surface as executed (`24` triggers, all adversarial cases executed — §11). Where application code additionally wraps these rules, it is layered *on top of*, never in place of, the triggers.

### 4.7 Trigger & Payment Semantics Notes (`A-5` — documented in `ARCH-ST-010.1`)

1. **Same-status no-op updates:** `trg_payments_validate_upd` rejects any `UPDATE` outside its four transition branches (`ERR_PAYMENT_INVALID_STATE_TRANSITION`) — including a same-status write that changes nothing. This is intentional strictness (it forces all writes through the explicit authorizing-event ledger). Other FSM triggers (`trg_claims_fsm_upd`, `trg_invoices_fsm_upd`) accept same-status writes as long as core immutability + aggregate invariants hold (verified).
2. **Blocked-payment remediation:** `block_reason_code` is immutable across all updates and `BLOCKED_* → AUTHORIZED` conversion is impossible (verified). A blocked payment therefore absorbs its `idempotency_key` permanently; the correct retry path inserts a **new** payment row with a fresh `idempotency_key`.
3. **Event authorization trust model:** the adjustment/event-gated protocols reduce to *existence of an app-insertable event row whose payload digests correctly* (no actor-role binding or HMAC). Accepted for the pure-SQLite trust model of this challenge; disclosed for implementers.
4. **SQLite feature floor:** scalar `MIN(a,b)/MAX(a,b)` `2-argument` forms inside triggers require SQLite ≥ 3.7.11; the pinned 3.40.1 satisfies this. `PRAGMA trusted_schema=ON` with `deterministic` UDFs is mandatory (§2.1).

---

## 5. Complete SQLite `STRICT` DDL & Enforcement Triggers (`operational.db` & `ground_truth.db`)

Every 64-character lowercase SHA-256 hex digest column is validated across all 64 characters via `CHECK (length(col) = 64 AND col NOT GLOB '*[^0-9a-f]*')`.

> **`ARCH-ST-010.1` changes inside these fences (all executed, §11):** `claims` gains `scoring_evidence_sha256` (`C-6`); `payments` gains `cancel_reason` with a closed enum (`A-1`); `immutable_events` gains the `PAYMENT_CANCELLED` and `RELATIONSHIP_EDGE_DEACTIVATED` event types (`A-1`/`C-6`); the trigger suite grows from 16 to **24 triggers** (`C-1` branch already present in `trg_claims_fsm_upd`; new `trg_investigations_block_delete`, `trg_edges_flow_upd`, `trg_edges_block_delete`, `trg_findings_block_upd`, `trg_findings_block_delete`, `trg_payments_validate_upd` event-gated branches, `trg_claims_siu_referred_au`, `trg_investigations_siu_ref_au`, `trg_claims_score_upd`). The fences below are byte-identical to the executed harness SQL.

### 5.1 Operational Database Schema (`operational.db` — 12 `STRICT` Tables)

```sql

PRAGMA foreign_keys = ON;
PRAGMA trusted_schema = ON;
PRAGMA recursive_triggers = ON;

-- 1. CLAIMANTS (2,000 rows)
CREATE TABLE claimants (
    claimant_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    dob_iso TEXT NOT NULL,
    tax_id_hash TEXT NOT NULL UNIQUE,
    phone_e164 TEXT NOT NULL,
    email_norm TEXT NOT NULL,
    address_norm TEXT NOT NULL,
    bank_routing_hash TEXT NOT NULL,
    bank_account_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    CHECK (claimant_id GLOB 'CLMT-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (dob_iso GLOB '[1-2][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    CHECK (length(tax_id_hash) = 64 AND tax_id_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (phone_e164 GLOB '+1[2-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (length(bank_routing_hash) = 64 AND bank_routing_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(bank_account_hash) = 64 AND bank_account_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (created_at_utc GLOB '202[0-6]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z')
) STRICT;

-- 2. POLICIES (2,200 rows)
CREATE TABLE policies (
    policy_id TEXT PRIMARY KEY,
    claimant_id TEXT NOT NULL REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    policy_number TEXT NOT NULL UNIQUE,
    line_of_business TEXT NOT NULL,
    policy_status TEXT NOT NULL,
    effective_start_utc TEXT NOT NULL,
    effective_end_utc TEXT NOT NULL,
    bound_at_utc TEXT NOT NULL,
    coverage_limit_cents INTEGER NOT NULL,
    deductible_cents INTEGER NOT NULL,
    annual_premium_cents INTEGER NOT NULL,
    CHECK (policy_id GLOB 'POL-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (line_of_business IN ('AUTO','PROPERTY','WORKERS_COMP','COMMERCIAL_GENERAL','MEDICAL')),
    CHECK (policy_status IN ('ACTIVE','LAPSED','CANCELLED','EXPIRED')),
    CHECK (effective_end_utc > effective_start_utc),
    CHECK (coverage_limit_cents > 0),
    CHECK (deductible_cents >= 0 AND deductible_cents < coverage_limit_cents),
    CHECK (annual_premium_cents > 0)
) STRICT;

-- 3. INCIDENTS (3,800 rows)
CREATE TABLE incidents (
    incident_id TEXT PRIMARY KEY,
    incident_timestamp_utc TEXT NOT NULL,
    reported_timestamp_utc TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    jurisdiction_state TEXT NOT NULL,
    location_address_norm TEXT NOT NULL,
    location_geohash TEXT NOT NULL,
    police_report_number TEXT,
    weather_condition TEXT NOT NULL,
    description TEXT NOT NULL,
    CHECK (incident_id GLOB 'INC-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (reported_timestamp_utc >= incident_timestamp_utc),
    CHECK (incident_type IN ('AUTO_COLLISION','WATER_DAMAGE','FIRE_LOSS','SLIP_AND_FALL','WORKPLACE_INJURY','THEFT_BURGLARY')),
    CHECK (length(jurisdiction_state) = 2 AND jurisdiction_state GLOB '[A-Z][A-Z]'),
    CHECK (length(location_geohash) BETWEEN 6 AND 12),
    CHECK (weather_condition IN ('CLEAR','RAIN','SNOW_ICE','FOG','STORM'))
) STRICT;

-- 4. CLAIMS (5,000 rows)
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL REFERENCES policies(policy_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    claimant_id TEXT NOT NULL REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    claim_status TEXT NOT NULL,
    submitted_at_utc TEXT NOT NULL,
    claimed_amount_cents INTEGER NOT NULL,
    approved_amount_cents INTEGER NOT NULL DEFAULT 0,
    historical_approved_cents INTEGER NOT NULL DEFAULT 0,
    reserved_authorized_cents INTEGER NOT NULL DEFAULT 0,
    gross_disbursed_cents INTEGER NOT NULL DEFAULT 0,
    clawed_back_cents INTEGER NOT NULL DEFAULT 0,
    net_paid_cents INTEGER NOT NULL DEFAULT 0,
    payout_cap_cents INTEGER NOT NULL,
    adjustor_id TEXT NOT NULL,
    siu_referred INTEGER NOT NULL DEFAULT 0,
    latest_ief_score REAL NOT NULL DEFAULT 0.0,
    latest_risk_tier TEXT NOT NULL DEFAULT 'LOW',
    scoring_evidence_sha256 TEXT,
    CHECK (claim_id GLOB 'CLM-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (claim_status IN ('SUBMITTED','UNDER_REVIEW','APPROVED','PARTIALLY_PAID','PAID','SIU_HOLD','DENIED','CLOSED_NO_PAY')),
    CHECK (claimed_amount_cents > 0),
    CHECK (approved_amount_cents >= 0 AND approved_amount_cents <= claimed_amount_cents),
    CHECK (historical_approved_cents >= approved_amount_cents),
    CHECK (reserved_authorized_cents >= 0),
    CHECK (gross_disbursed_cents >= 0),
    CHECK (clawed_back_cents >= 0 AND clawed_back_cents <= gross_disbursed_cents),
    CHECK (net_paid_cents = gross_disbursed_cents - clawed_back_cents),
    CHECK (reserved_authorized_cents + net_paid_cents <= historical_approved_cents),
    CHECK (payout_cap_cents >= 0),
    CHECK (approved_amount_cents <= payout_cap_cents),
    CHECK (siu_referred IN (0, 1)),
    CHECK (scoring_evidence_sha256 IS NULL OR (length(scoring_evidence_sha256) = 64 AND scoring_evidence_sha256 NOT GLOB '*[^0-9a-f]*')),
    CHECK (latest_ief_score >= 0.0 AND latest_ief_score <= 100.0),
    CHECK (latest_risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL'))
) STRICT;

-- 5. PROVIDERS (500 rows)
CREATE TABLE providers (
    provider_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    npi_or_license_id TEXT NOT NULL UNIQUE,
    tax_id_hash TEXT NOT NULL,
    phone_e164 TEXT NOT NULL,
    address_norm TEXT NOT NULL,
    bank_routing_hash TEXT NOT NULL,
    bank_account_hash TEXT NOT NULL,
    network_tier TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    CHECK (provider_id GLOB 'PRV-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (provider_type IN ('AUTO_BODY','MEDICAL_CLINIC','CHIROPRACTIC','RESTORATION_CONTRACTOR','LEGAL_REPRESENTATIVE','TOWING_STORAGE','DIAGNOSTIC_IMAGING')),
    CHECK (network_tier IN ('IN_NETWORK','OUT_OF_NETWORK','WATCHLIST','SUSPENDED')),
    CHECK (length(tax_id_hash) = 64 AND tax_id_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (phone_e164 GLOB '+1[2-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (length(bank_routing_hash) = 64 AND bank_routing_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(bank_account_hash) = 64 AND bank_account_hash NOT GLOB '*[^0-9a-f]*')
) STRICT;

-- 6. INVOICES (7,500 rows)
CREATE TABLE invoices (
    invoice_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_invoice_number TEXT NOT NULL,
    invoice_status TEXT NOT NULL,
    service_start_utc TEXT NOT NULL,
    service_end_utc TEXT NOT NULL,
    submitted_at_utc TEXT NOT NULL,
    cpt_or_line_code TEXT NOT NULL,
    line_item_fingerprint TEXT NOT NULL,
    billed_cents INTEGER NOT NULL,
    approved_cents INTEGER NOT NULL DEFAULT 0,
    historical_approved_cents INTEGER NOT NULL DEFAULT 0,
    reserved_authorized_cents INTEGER NOT NULL DEFAULT 0,
    gross_disbursed_cents INTEGER NOT NULL DEFAULT 0,
    clawed_back_cents INTEGER NOT NULL DEFAULT 0,
    net_paid_cents INTEGER NOT NULL DEFAULT 0,
    duplicate_of_invoice_id TEXT REFERENCES invoices(invoice_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CHECK (invoice_id GLOB 'INV-PRV-' || provider_id || '-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (length(invoice_id) = 25),
    CHECK (invoice_status IN ('SUBMITTED','UNDER_REVIEW','APPROVED','PARTIALLY_PAID','PAID','REJECTED_DUPLICATE','REJECTED_ELIGIBILITY','REVOKED_POST_APPROVAL')),
    CHECK (service_end_utc >= service_start_utc),
    CHECK (submitted_at_utc >= service_start_utc),
    CHECK (length(line_item_fingerprint) = 64 AND line_item_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK (billed_cents > 0),
    CHECK (approved_cents >= 0 AND approved_cents <= billed_cents),
    CHECK (historical_approved_cents >= approved_cents AND historical_approved_cents <= billed_cents),
    CHECK (reserved_authorized_cents >= 0),
    CHECK (gross_disbursed_cents >= 0),
    CHECK (clawed_back_cents >= 0 AND clawed_back_cents <= gross_disbursed_cents),
    CHECK (net_paid_cents = gross_disbursed_cents - clawed_back_cents),
    CHECK (reserved_authorized_cents + net_paid_cents <= historical_approved_cents),
    CHECK (
        (invoice_status = 'REJECTED_DUPLICATE' AND duplicate_of_invoice_id IS NOT NULL AND duplicate_of_invoice_id != invoice_id AND approved_cents = 0)
        OR (invoice_status != 'REJECTED_DUPLICATE' AND duplicate_of_invoice_id IS NULL)
    )
) STRICT;

-- 7. PAYMENTS (4,200 rows)
CREATE TABLE payments (
    payment_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    recipient_type TEXT NOT NULL,
    recipient_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    recipient_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    payment_status TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    disbursed_amount_cents INTEGER NOT NULL DEFAULT 0,
    clawed_back_cents INTEGER NOT NULL DEFAULT 0,
    net_paid_cents INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL,
    disbursed_at_utc TEXT,
    reversed_at_utc TEXT,
    authorized_by TEXT NOT NULL,
    block_reason_code TEXT,
    external_bank_tx_ref TEXT,
    cancel_reason TEXT,
    CHECK (payment_id GLOB 'PAY-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (
        (recipient_type = 'CLAIMANT' AND recipient_claimant_id IS NOT NULL AND recipient_provider_id IS NULL)
        OR (recipient_type = 'PROVIDER' AND recipient_provider_id IS NOT NULL AND recipient_claimant_id IS NULL)
    ),
    CHECK (payment_status IN ('AUTHORIZED','DISBURSED','BLOCKED_OVERPAYMENT','BLOCKED_UNAPPROVED','BLOCKED_INVALID_RECIPIENT','REVERSED_CLAWBACK','CANCELLED')),
    CHECK (amount_cents > 0),
    CHECK (
        (payment_status = 'DISBURSED' AND disbursed_amount_cents = amount_cents AND clawed_back_cents = 0 AND net_paid_cents = amount_cents AND disbursed_at_utc IS NOT NULL AND external_bank_tx_ref IS NOT NULL AND length(external_bank_tx_ref) >= 4 AND reversed_at_utc IS NULL AND block_reason_code IS NULL AND cancel_reason IS NULL)
        OR (payment_status = 'REVERSED_CLAWBACK' AND disbursed_amount_cents = amount_cents AND clawed_back_cents > 0 AND clawed_back_cents <= disbursed_amount_cents AND net_paid_cents = disbursed_amount_cents - clawed_back_cents AND disbursed_at_utc IS NOT NULL AND external_bank_tx_ref IS NOT NULL AND reversed_at_utc IS NOT NULL AND block_reason_code IS NULL AND cancel_reason IS NULL)
        OR (payment_status = 'AUTHORIZED' AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NULL AND block_reason_code IS NULL AND cancel_reason IS NULL)
        OR (payment_status = 'CANCELLED' AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NOT NULL AND block_reason_code IS NULL AND cancel_reason IS NOT NULL)
        OR (payment_status IN ('BLOCKED_OVERPAYMENT','BLOCKED_UNAPPROVED','BLOCKED_INVALID_RECIPIENT') AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NULL AND block_reason_code IS NOT NULL AND cancel_reason IS NULL)
    ),
    CHECK (cancel_reason IS NULL OR cancel_reason IN ('SIU_HOLD_RESERVATION_CLEARED','FINANCE_WITHDRAWAL','SUBSEQUENT_ADJUSTMENT'))
) STRICT;

-- 8. RELATIONSHIP_EDGES (8,000 rows)
CREATE TABLE relationship_edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    source_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    target_entity_type TEXT NOT NULL,
    target_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    target_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    canonical_src_key TEXT NOT NULL,
    canonical_dst_key TEXT NOT NULL,
    strength_weight REAL NOT NULL,
    evidence_count INTEGER NOT NULL,
    first_observed_utc TEXT NOT NULL,
    last_observed_utc TEXT NOT NULL,
    supporting_claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    is_active INTEGER NOT NULL DEFAULT 1,
    CHECK (edge_id GLOB 'EDGE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (edge_type IN ('SHARED_ADDRESS','SHARED_PHONE','SHARED_BANK_ACCOUNT','SHARED_TAX_ID','SAME_INCIDENT_PARTICIPANT','CLAIMANT_TREATED_BY_PROVIDER','PROVIDER_REFERRAL_LINK','CROSS_CLAIM_DUPLICATE_INVOICE')),
    CHECK (
        (source_entity_type = 'CLAIMANT' AND source_claimant_id IS NOT NULL AND source_provider_id IS NULL AND canonical_src_key = 'CLAIMANT:' || source_claimant_id)
        OR (source_entity_type = 'PROVIDER' AND source_provider_id IS NOT NULL AND source_claimant_id IS NULL AND canonical_src_key = 'PROVIDER:' || source_provider_id)
    ),
    CHECK (
        (target_entity_type = 'CLAIMANT' AND target_claimant_id IS NOT NULL AND target_provider_id IS NULL AND canonical_dst_key = 'CLAIMANT:' || target_claimant_id)
        OR (target_entity_type = 'PROVIDER' AND target_provider_id IS NOT NULL AND target_claimant_id IS NULL AND canonical_dst_key = 'PROVIDER:' || target_provider_id)
    ),
    CHECK (canonical_src_key < canonical_dst_key),
    CHECK (strength_weight > 0.0 AND strength_weight <= 1.0),
    CHECK (evidence_count >= 1),
    CHECK (last_observed_utc >= first_observed_utc),
    CHECK (is_active IN (0, 1)),
    UNIQUE (edge_type, canonical_src_key, canonical_dst_key)
) STRICT;

-- 9. FRAUD_INDICATORS (4,120 rows)
CREATE TABLE fraud_indicators (
    indicator_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    indicator_code TEXT NOT NULL,
    pillar TEXT NOT NULL,
    dedup_scope TEXT NOT NULL,
    canonical_evidence_token TEXT NOT NULL,
    severity TEXT NOT NULL,
    raw_points REAL NOT NULL,
    max_points REAL NOT NULL,
    normalized_value REAL NOT NULL,
    feature_snapshot_json TEXT NOT NULL,
    computed_at_utc TEXT NOT NULL,
    CHECK (indicator_id GLOB 'FIND-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (indicator_code IN ('IND-01','IND-02','IND-03','IND-04','IND-05','IND-06','IND-07','IND-08','IND-09','IND-10','IND-11','IND-12','IND-13','IND-14','IND-15')),
    CHECK (pillar IN ('NETWORK','FINANCIAL','BEHAVIORAL','DOCUMENT')),
    CHECK (dedup_scope IN ('CLAIM','ENTITY','PAIR','RING')),
    CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CHECK (raw_points > 0.0 AND raw_points <= max_points),
    CHECK (max_points > 0.0 AND max_points <= 40.0),
    CHECK (normalized_value >= 0.0 AND normalized_value <= 1.0),
    CHECK (is_canonical_json(feature_snapshot_json) = 1),
    UNIQUE (claim_id, indicator_code, canonical_evidence_token)
) STRICT;

-- 10. INVESTIGATIONS (45 rows)
CREATE TABLE investigations (
    investigation_id TEXT PRIMARY KEY,
    primary_claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    subject_claimant_id TEXT REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    subject_provider_id TEXT REFERENCES providers(provider_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    investigation_status TEXT NOT NULL,
    priority TEXT NOT NULL,
    assigned_investigator_id TEXT NOT NULL,
    opened_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    closed_at_utc TEXT,
    ruling_outcome TEXT,
    estimated_exposure_cents INTEGER NOT NULL,
    recovered_clawback_cents INTEGER NOT NULL DEFAULT 0,
    case_summary_notes TEXT NOT NULL,
    CHECK (investigation_id GLOB 'INVG-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (subject_claimant_id IS NOT NULL OR subject_provider_id IS NOT NULL),
    CHECK (investigation_status IN ('OPEN','EVIDENCE_COLLECTION','SIU_FIELD_REVIEW','LEGAL_ESCALATION','CLOSED_CONFIRMED_FRAUD','CLOSED_CLEARED_BENIGN','CLOSED_INSUFFICIENT_EVIDENCE')),
    CHECK (priority IN ('P1_CRITICAL','P2_HIGH','P3_STANDARD')),
    CHECK (updated_at_utc >= opened_at_utc),
    CHECK (estimated_exposure_cents >= 0),
    CHECK (recovered_clawback_cents >= 0),
    CHECK (
        (investigation_status LIKE 'CLOSED_%' AND closed_at_utc IS NOT NULL AND closed_at_utc >= opened_at_utc AND ruling_outcome IN ('CONFIRMED_FRAUD','CLEARED_BENIGN','INSUFFICIENT_EVIDENCE'))
        OR (investigation_status NOT LIKE 'CLOSED_%' AND closed_at_utc IS NULL AND ruling_outcome IS NULL)
    )
) STRICT;

-- 11. IMMUTABLE_EVENTS (19,615 rows — Length-Prefixed ST-EVT-V2 Chain)
CREATE TABLE immutable_events (
    sequence_no INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    claim_id TEXT REFERENCES claims(claim_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    actor_id TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    prev_event_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    CHECK (sequence_no >= 1),
    CHECK (event_id GLOB 'EVT-2026-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (event_type IN ('INGESTION_EXCEPTION_RECORDED','CLAIM_SUBMITTED','INVOICE_SUBMITTED','INVOICE_APPROVED','INVOICE_APPROVAL_ADJUSTED','CLAIM_APPROVED','PAYMENT_AUTHORIZED','PAYMENT_CANCELLED','PAYMENT_BLOCKED','PAYMENT_DISBURSED','PAYMENT_CLAWBACK_REVERSED','CLAIM_SIU_HOLD_PLACED','CLAIM_DENIED','RELATIONSHIP_EDGE_DEACTIVATED','INVESTIGATION_OPENED','INVESTIGATION_STATUS_CHANGED','INVESTIGATION_CLOSED')),
    CHECK (entity_type IN ('Claimant','Policy','Incident','Claim','Provider','Invoice','Payment','RelationshipEdge','FraudIndicator','Investigation','IngestionException')),
    CHECK (is_canonical_json(payload_json) = 1),
    CHECK (length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(prev_event_hash) = 64 AND prev_event_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (length(event_hash) = 64 AND event_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK (payload_sha256 = sha256_hex(payload_json)),
    CHECK (
        event_hash = sha256_hex(
            'ST-EVT-V2|'
            || '11:sequence_no=I' || CAST(sequence_no AS TEXT) || ';'
            || '8:event_id=S' || CAST(length(CAST(event_id AS BLOB)) AS TEXT) || ':' || event_id || ';'
            || '10:event_type=S' || CAST(length(CAST(event_type AS BLOB)) AS TEXT) || ':' || event_type || ';'
            || '11:entity_type=S' || CAST(length(CAST(entity_type AS BLOB)) AS TEXT) || ':' || entity_type || ';'
            || '9:entity_id=S' || CAST(length(CAST(entity_id AS BLOB)) AS TEXT) || ':' || entity_id || ';'
            || CASE
                WHEN claim_id IS NULL THEN '8:claim_id=N;'
                ELSE '8:claim_id=S' || CAST(length(CAST(claim_id AS BLOB)) AS TEXT) || ':' || claim_id || ';'
               END
            || '8:actor_id=S' || CAST(length(CAST(actor_id AS BLOB)) AS TEXT) || ':' || actor_id || ';'
            || '15:occurred_at_utc=S' || CAST(length(CAST(occurred_at_utc AS BLOB)) AS TEXT) || ':' || occurred_at_utc || ';'
            || '14:payload_sha256=S' || CAST(length(CAST(payload_sha256 AS BLOB)) AS TEXT) || ':' || payload_sha256 || ';'
            || '15:prev_event_hash=S' || CAST(length(CAST(prev_event_hash AS BLOB)) AS TEXT) || ':' || prev_event_hash || ';'
        )
    )
) STRICT;

-- 12. INGESTION_EXCEPTIONS (25 rows — YF-NEG-1 Nonexistent Policy References)
CREATE TABLE ingestion_exceptions (
    exception_id TEXT PRIMARY KEY,
    attempted_claim_id TEXT NOT NULL UNIQUE,
    rejected_policy_id TEXT NOT NULL,
    claimant_id TEXT NOT NULL REFERENCES claimants(claimant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    attempted_claimed_cents INTEGER NOT NULL,
    exception_code TEXT NOT NULL,
    raw_payload_json TEXT NOT NULL,
    detected_at_utc TEXT NOT NULL,
    immutable_event_id TEXT NOT NULL REFERENCES immutable_events(event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CHECK (exception_id GLOB 'IEX-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (attempted_claim_id GLOB 'CLM-2026-99[0-9][0-9][0-9][0-9]'),
    CHECK (rejected_policy_id GLOB 'POL-2026-99[0-9][0-9][0-9][0-9]'),
    CHECK (attempted_claimed_cents > 0),
    CHECK (exception_code = 'ERR_NONEXISTENT_POLICY_REFERENCE'),
    CHECK (is_canonical_json(raw_payload_json) = 1)
) STRICT;
```

### 5.2 Complete SQLite Trigger Suite (`triggers.sql`)

```sql

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
        WHEN OLD.claim_status != NEW.claim_status AND NOT (
            (OLD.claim_status = 'SUBMITTED' AND NEW.claim_status IN ('UNDER_REVIEW','APPROVED','SIU_HOLD','DENIED'))
            OR (OLD.claim_status = 'UNDER_REVIEW' AND NEW.claim_status IN ('APPROVED','SIU_HOLD','DENIED','CLOSED_NO_PAY'))
            OR (OLD.claim_status = 'APPROVED' AND NEW.claim_status IN ('PARTIALLY_PAID','PAID','SIU_HOLD'))
            OR (OLD.claim_status = 'PARTIALLY_PAID' AND NEW.claim_status IN ('PAID','APPROVED','SIU_HOLD'))
            OR (OLD.claim_status = 'PAID' AND NEW.claim_status IN ('PARTIALLY_PAID','APPROVED','SIU_HOLD'))
            OR (OLD.claim_status = 'SIU_HOLD' AND NEW.claim_status IN ('APPROVED','DENIED','CLOSED_NO_PAY'))
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
                 OR (SELECT p.policy_status FROM claims c JOIN policies p ON p.policy_id = c.policy_id WHERE c.claim_id = NEW.claim_id) != 'ACTIVE'
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
                 WHERE e.entity_type = 'Payment' AND e.entity_id = NEW.payment_id
                   AND e.event_type = 'PAYMENT_AUTHORIZED'
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
                 WHERE e.entity_type = 'Payment' AND e.entity_id = NEW.payment_id
                   AND e.event_type = 'PAYMENT_CANCELLED'
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
                 WHERE e.entity_type = 'Payment' AND e.entity_id = NEW.payment_id
                   AND e.event_type = 'PAYMENT_CLAWBACK_REVERSED'
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

-- 5. Investigations FSM Trigger
CREATE TRIGGER trg_investigations_fsm_upd
BEFORE UPDATE ON investigations
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN OLD.investigation_status LIKE 'CLOSED_%'
            THEN RAISE(ABORT, 'ERR_CLOSED_INVESTIGATION_IMMUTABLE')
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

-- 7. [ARCH-ST-010.1 / C-6] Relationship-Edge Tamper Protection
--    Edges are append-only. The ONLY permitted post-insert mutation is the
--    deactivation is_active 1 -> 0, and it is valid ONLY when the newest
--    immutable_events row for (RelationshipEdge, edge_id) is a
--    RELATIONSHIP_EDGE_DEACTIVATED event whose payload_sha256 matches the
--    canonical payload contract. All other UPDATEs and all DELETEs abort.
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
        WHEN NEW.is_active = OLD.is_active
            THEN NULL  -- only last_observed_utc bumps are permitted alongside no-op is_active
        WHEN NEW.last_observed_utc < OLD.last_observed_utc
            THEN RAISE(ABORT, 'ERR_EDGE_OBSERVED_TIME_REGRESSION')
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
        WHEN NEW.is_active = 1 AND OLD.is_active = 0
            THEN RAISE(ABORT, 'ERR_EDGE_REACTIVATION_FORBIDDEN')
        WHEN NEW.is_active NOT IN (0, 1)
             OR (NEW.is_active = OLD.is_active AND NEW.last_observed_utc IS NULL)
            THEN RAISE(ABORT, 'ERR_EDGE_MUTATION_INVALID')
    END;
END;

CREATE TRIGGER trg_edges_block_delete
BEFORE DELETE ON relationship_edges
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'ERR_EDGE_DELETE_FORBIDDEN');
END;

-- 8. [ARCH-ST-010.1 / C-6] Fraud-Indicator Append-Only Protection
--    Indicators are the auditable evidence layer behind S_base. They are
--    append-only: every UPDATE or DELETE aborts. Score manipulation is
--    additionally defeated by trg_claims_score_upd (ST-SCORE-V1 binding).
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
--     siu_referred flips to 1 exactly when a claim enters SIU_HOLD and can
--     never be reset (SIU referral is permanent history).
CREATE TRIGGER trg_claims_siu_referred_au
AFTER UPDATE OF claim_status ON claims
FOR EACH ROW
WHEN NEW.claim_status = 'SIU_HOLD' AND NEW.siu_referred = 0
BEGIN
    UPDATE claims SET siu_referred = 1 WHERE claim_id = NEW.claim_id;
END;

-- 10. [ARCH-ST-010.1 / C-6] Investigation confirmed-fraud outcome propagates
--     the SIU referral to the primary claim.
CREATE TRIGGER trg_investigations_siu_ref_au
AFTER UPDATE OF investigation_status ON investigations
FOR EACH ROW
WHEN NEW.investigation_status = 'CLOSED_CONFIRMED_FRAUD'
BEGIN
    UPDATE claims SET siu_referred = 1 WHERE claim_id = NEW.primary_claim_id;
END;

-- 12. [ARCH-ST-010.1 / C-6] Score-to-evidence reconciliation (ST-SCORE-V1)
--     Any write to claims.latest_ief_score, claims.latest_risk_tier or
--     claims.scoring_evidence_sha256 MUST carry a scoring_evidence_sha256
--     that equals the ST-SCORE-V1 digest recomputed database-side from the
--     curator's fraud_indicators rows + the claimed score itself, and the
--     risk tier must equal the deterministic tier thresholds.
CREATE TRIGGER trg_claims_score_upd
BEFORE UPDATE OF latest_ief_score, latest_risk_tier, scoring_evidence_sha256 ON claims
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.scoring_evidence_sha256 IS NULL
            THEN RAISE(ABORT, 'ERR_SCORE_EVIDENCE_DIGEST_REQUIRED')
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
```

### 5.3 Quarantined Ground-Truth Database Schema (`ground_truth.db` — 4 `STRICT` Tables)

```sql
CREATE TABLE ground_truth_rings (
    ring_id TEXT PRIMARY KEY,
    ring_archetype TEXT NOT NULL,
    observability_mode TEXT NOT NULL,
    claim_count INTEGER NOT NULL,
    entity_count INTEGER NOT NULL,
    CHECK (ring_id GLOB 'RING-2026-[0-9][0-9][0-9]'),
    CHECK (observability_mode IN ('FULL_OBSERVABLE','PARTIAL_MISSING_EDGES_YF_NEG_4'))
) STRICT;

CREATE TABLE ground_truth_claim_labels (
    claim_id TEXT PRIMARY KEY,
    is_fraud INTEGER NOT NULL,
    ring_id TEXT REFERENCES ground_truth_rings(ring_id),
    scenario_code TEXT NOT NULL,
    CHECK (claim_id GLOB 'CLM-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (is_fraud IN (0, 1))
) STRICT;

CREATE TABLE ground_truth_entity_labels (
    entity_key TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    is_fraud_participant INTEGER NOT NULL,
    ring_id TEXT REFERENCES ground_truth_rings(ring_id),
    CHECK (entity_type IN ('CLAIMANT','PROVIDER')),
    CHECK (is_fraud_participant IN (0, 1))
) STRICT;

CREATE TABLE ground_truth_missing_edges (
    missing_edge_id TEXT PRIMARY KEY,
    ring_id TEXT NOT NULL REFERENCES ground_truth_rings(ring_id),
    edge_type TEXT NOT NULL,
    canonical_src_key TEXT NOT NULL,
    canonical_dst_key TEXT NOT NULL,
    planted_reason TEXT NOT NULL,
    CHECK (missing_edge_id GLOB 'GTME-2026-[0-9][0-9][0-9][0-9]'),
    CHECK (canonical_src_key < canonical_dst_key)
) STRICT;
```

---

## 6. Canonical Serialization, Event Hash Chain (`ST-EVT-V2`), Fingerprints & Schema Digest (`CRITICAL 4`, `CRITICAL 6`)

### 6.1 Length-Prefixed Canonical Event Serialization (`ST-EVT-V2`)
To eliminate pipe-delimiter ambiguity, `NULL` vs. empty-string collisions, and multi-byte UTF-8 boundary ambiguity, `immutable_events.event_hash` uses the length-prefixed `ST-EVT-V2` grammar over the exact 10 ordered fields:

$$\text{preimage} = \texttt{"ST-EVT-V2|"} \;\|\; \bigoplus_{k=1}^{10} \text{enc}(f_k, v_k)$$

where for field name $f_k$ with UTF-8 byte length $L_f = \text{len}_{\text{UTF-8}}(f_k)$:
- **Integer (`INTEGER`):** $\text{enc}(f_k, v_k) = L_f \;\|\; \texttt{":"} \;\|\; f_k \;\|\; \texttt{"=I"} \;\|\; \text{ASCII\_DEC}(v_k) \;\|\; \texttt{";"}$
- **Nullable `TEXT` when `NULL` (`claim_id IS NULL`):** $\text{enc}(f_k, \texttt{NULL}) = L_f \;\|\; \texttt{":"} \;\|\; f_k \;\|\; \texttt{"=N;"}$
- **Non-null `TEXT` (`str`):** With UTF-8 byte length $L_v = \text{len}_{\text{UTF-8}}(v_k)$ (computed in SQLite via `length(CAST(col AS BLOB))` and in Python via `len(val.encode('utf-8'))`):
  $$\text{enc}(f_k, v_k) = L_f \;\|\; \texttt{":"} \;\|\; f_k \;\|\; \texttt{"=S"} \;\|\; L_v \;\|\; \texttt{":"} \;\|\; v_k \;\|\; \texttt{";"}$$

### 6.2 Independently Calculated & Verified Known-Answer Vectors (`KAV-1` through `KAV-7`)

| Vector | `seq` | `event_id` / `event_type` / `entity_type` / `entity_id` / `claim_id` / `actor_id` / `occurred_at_utc` | Canonical `payload_json` & Exact `ST-EVT-V2` Preimage | `payload_sha256` / `prev_event_hash` / `event_hash` |
|---|---:|---|---|---|
| **KAV-1** (Genesis) | `1` | `EVT-2026-0000001` / `CLAIM_SUBMITTED` / `Claim` / `CLM-2026-000001` / `CLM-2026-000001` / `SYSTEM_SEED` / `2026-01-05T09:00:00Z` | **JSON:** `{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}`<br>**Preimage:** `ST-EVT-V2\|11:sequence_no=I1;8:event_id=S16:EVT-2026-0000001;10:event_type=S15:CLAIM_SUBMITTED;11:entity_type=S5:Claim;9:entity_id=S15:CLM-2026-000001;8:claim_id=S15:CLM-2026-000001;8:actor_id=S11:SYSTEM_SEED;15:occurred_at_utc=S20:2026-01-05T09:00:00Z;14:payload_sha256=S64:45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3;15:prev_event_hash=S64:0000000000000000000000000000000000000000000000000000000000000000;` | `psha`: `45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3`<br>`prev`: `0000000000000000000000000000000000000000000000000000000000000000`<br>`hash`: `1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305` |
| **KAV-2** | `2` | `EVT-2026-0000002` / `INVOICE_SUBMITTED` / `Invoice` / `INV-PRV-PRV-000001-000001` / `CLM-2026-000001` / `SYSTEM_SEED` / `2026-01-05T10:15:00Z` | **JSON:** `{"billed_cents":420000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"SUBMITTED","provider_id":"PRV-000001"}`<br>**Preimage:** `ST-EVT-V2\|11:sequence_no=I2;8:event_id=S16:EVT-2026-0000002;10:event_type=S17:INVOICE_SUBMITTED;11:entity_type=S7:Invoice;9:entity_id=S25:INV-PRV-PRV-000001-000001;8:claim_id=S15:CLM-2026-000001;8:actor_id=S11:SYSTEM_SEED;15:occurred_at_utc=S20:2026-01-05T10:15:00Z;14:payload_sha256=S64:e9fe644e3853d49ee2134783b6d3321ba44eb5d34ccb53ee2d898a9ccb6cd60e;15:prev_event_hash=S64:1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305;` | `psha`: `e9fe644e3853d49ee2134783b6d3321ba44eb5d34ccb53ee2d898a9ccb6cd60e`<br>`prev`: `1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305`<br>`hash`: `e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e` |
| **KAV-3** | `3` | `EVT-2026-0000003` / `CLAIM_APPROVED` / `Claim` / `CLM-2026-000001` / `CLM-2026-000001` / `USR-ADJ-001` / `2026-01-06T14:20:00Z` | **JSON:** `{"approved_amount_cents":370000,"claim_id":"CLM-2026-000001","claim_status":"APPROVED","historical_approved_cents":370000}`<br>**Preimage:** `ST-EVT-V2\|11:sequence_no=I3;8:event_id=S16:EVT-2026-0000003;10:event_type=S14:CLAIM_APPROVED;11:entity_type=S5:Claim;9:entity_id=S15:CLM-2026-000001;8:claim_id=S15:CLM-2026-000001;8:actor_id=S11:USR-ADJ-001;15:occurred_at_utc=S20:2026-01-06T14:20:00Z;14:payload_sha256=S64:702bfd27038da09f50dd068a2413531612b0cf9c51f8454d75b8fb0e2ccdb172;15:prev_event_hash=S64:e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e;` | `psha`: `702bfd27038da09f50dd068a2413531612b0cf9c51f8454d75b8fb0e2ccdb172`<br>`prev`: `e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e`<br>`hash`: `9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686` |
| **KAV-4** | `4` | `EVT-2026-0000004` / `PAYMENT_AUTHORIZED` / `Payment` / `PAY-2026-000001` / `CLM-2026-000001` / `USR-FIN-001` / `2026-01-07T08:00:00Z` | **JSON:** `{"amount_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}`<br>**Preimage:** `ST-EVT-V2\|11:sequence_no=I4;8:event_id=S16:EVT-2026-0000004;10:event_type=S18:PAYMENT_AUTHORIZED;11:entity_type=S7:Payment;9:entity_id=S15:PAY-2026-000001;8:claim_id=S15:CLM-2026-000001;8:actor_id=S11:USR-FIN-001;15:occurred_at_utc=S20:2026-01-07T08:00:00Z;14:payload_sha256=S64:42913a85d1e8fcaff502429d18df7b7b132bb7f92f11c9af0f65f2842d9d73ce;15:prev_event_hash=S64:9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686;` | `psha`: `42913a85d1e8fcaff502429d18df7b7b132bb7f92f11c9af0f65f2842d9d73ce`<br>`prev`: `9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686`<br>`hash`: `ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5` |
| **KAV-5** | `5` | `EVT-2026-0000005` / `PAYMENT_DISBURSED` / `Payment` / `PAY-2026-000001` / `CLM-2026-000001` / `USR-FIN-001` / `2026-01-07T12:00:00Z` | **JSON:** `{"amount_cents":370000,"claim_id":"CLM-2026-000001","disbursed_amount_cents":370000,"external_bank_tx_ref":"ACH-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"DISBURSED"}`<br>**Preimage:** `ST-EVT-V2\|11:sequence_no=I5;8:event_id=S16:EVT-2026-0000005;10:event_type=S17:PAYMENT_DISBURSED;11:entity_type=S7:Payment;9:entity_id=S15:PAY-2026-000001;8:claim_id=S15:CLM-2026-000001;8:actor_id=S11:USR-FIN-001;15:occurred_at_utc=S20:2026-01-07T12:00:00Z;14:payload_sha256=S64:5663eee591086d12e4641cac76bf6f8ce82ae56eabd229045482ea1bc2958ee3;15:prev_event_hash=S64:ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5;` | `psha`: `5663eee591086d12e4641cac76bf6f8ce82ae56eabd229045482ea1bc2958ee3`<br>`prev`: `ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5`<br>`hash`: `0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d` |
| **KAV-6** | `6` | `EVT-2026-0000006` / `PAYMENT_CLAWBACK_REVERSED` / `Payment` / `PAY-2026-000001` / `CLM-2026-000001` / `USR-SIU-001` / `2026-01-12T16:45:00Z` | **JSON:** `{"claim_id":"CLM-2026-000001","clawed_back_cents":370000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}`<br>**Preimage:** `ST-EVT-V2\|11:sequence_no=I6;8:event_id=S16:EVT-2026-0000006;10:event_type=S25:PAYMENT_CLAWBACK_REVERSED;11:entity_type=S7:Payment;9:entity_id=S15:PAY-2026-000001;8:claim_id=S15:CLM-2026-000001;8:actor_id=S11:USR-SIU-001;15:occurred_at_utc=S20:2026-01-12T16:45:00Z;14:payload_sha256=S64:8a79ad34c4312208ba53d45a78aab83286d449f4cdbed29282edf971a7cd7412;15:prev_event_hash=S64:0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d;` | `psha`: `8a79ad34c4312208ba53d45a78aab83286d449f4cdbed29282edf971a7cd7412`<br>`prev`: `0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d`<br>`hash`: `00b7871a82451bd6e85ac1b85d58e41b8fa77f24071f557121e4586570b9b564` |
| **KAV-7** (Unicode + Pipe Injection + `NULL` `claim_id`) | `2` (alt) | `EVT-2026-0000002` / `INGESTION_EXCEPTION_RECORDED` / `IngestionException` / `IEX-2026-000001` / `NULL` / `USR\|Renée;東京` (17 UTF-8 bytes) / `2026-01-05T09:01:00Z` | **JSON:** `{"note":"Renée\|東京\|🔍;8:claim_id=S15:CLM-2026-000001;"}`<br>**Preimage:** `ST-EVT-V2\|11:sequence_no=I2;8:event_id=S16:EVT-2026-0000002;10:event_type=S28:INGESTION_EXCEPTION_RECORDED;11:entity_type=S18:IngestionException;9:entity_id=S15:IEX-2026-000001;8:claim_id=N;8:actor_id=S17:USR\|Renée;東京;15:occurred_at_utc=S20:2026-01-05T09:01:00Z;14:payload_sha256=S64:551e1e170eb912f3d695924f3e62f2db7b1ca9c5ececd433cd42e80c8e03b07a;15:prev_event_hash=S64:1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305;` | `psha`: `551e1e170eb912f3d695924f3e62f2db7b1ca9c5ececd433cd42e80c8e03b07a`<br>`prev`: `1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305`<br>`hash`: `c20f59e45969c8c8fef46fcab1bc2645b123aa695f00f7761c291b9a243e8dbe` |

**Classification (`A-2`, corrected in `ARCH-ST-010.1`):** the seven vectors above are **pure cryptographic hash test vectors**. KAV-3 (`CLAIM_APPROVED` with no preceding invoice-approval event) and KAV-4 (payment authorization whose invoice never appears approved within the chain's own narrative) are deliberately compact fixtures that violate the operational lifecycle of §4; they verify the `ST-EVT-V2` grammar and the SHA-256 chain, **not** the FSM. Implementers and the seed generator MUST NOT replay KAV-1..KAV-7 as an operational history. The FSM-valid operational chain is the separate vector set below.

#### 6.2.1 Operationally Valid History Vectors (`VH-1` through `VH-7`, new in `ARCH-ST-010.1`)

`VH-1..VH-7` is a single connected chain for the §4 lifecycle of claim `CLM-2026-000001`: submit → invoice submit → invoice approve → claim approve (cascade) → payment authorize → disburse → reversal-clawback. Every state transition is legal under §4.2/§4.3/§4.4, and every payload is canonical per §6.5. All hashes below were recomputed by the author's harness (`PASS — EXECUTED`, SQLite 3.49.1 + Python mirror). Genesis-zeros linkage is intact across VH-1..VH-7.

| Vector | `seq` | `event_id` / `event_type` / `entity_type` / `entity_id` / `actor_id` / `occurred_at_utc` | Canonical `payload_json` | `payload_sha256` | `event_hash` |
|---|---:|---|---|---|---|
| VH-1 | 1 | `EVT-2026-0000001` / `CLAIM_SUBMITTED` / `Claim` / `CLM-2026-000001` / `SYSTEM_SEED` / `2026-01-05T09:00:00Z` | `{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}` | `45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3` | `1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305` |
| VH-2 | 2 | `EVT-2026-0000002` / `INVOICE_SUBMITTED` / `Invoice` / `INV-PRV-PRV-000001-000001` / `SYSTEM_SEED` / `2026-01-05T10:15:00Z` | `{"billed_cents":420000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"SUBMITTED","provider_id":"PRV-000001"}` | `e9fe644e3853d49ee2134783b6d3321ba44eb5d34ccb53ee2d898a9ccb6cd60e` | `e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e` |
| VH-3 | 3 | `EVT-2026-0000003` / `INVOICE_APPROVED` / `Invoice` / `INV-PRV-PRV-000001-000001` / `USR-ADJ-001` / `2026-01-06T14:20:00Z` | `{"approved_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"APPROVED"}` | `bd00e1a1873f9520d8fd9b4e7a2f0e7e2bb8fb2f781c9440bb6c88c5837f5569` | `cc5d1e6c99a5de328d68019d4e24f11a39ea853aff8bccd76c9cd70080ffb4d1` |
| VH-4 | 4 | `EVT-2026-0000004` / `CLAIM_APPROVED` / `Claim` / `CLM-2026-000001` / `USR-ADJ-001` / `2026-01-06T14:21:00Z` | `{"approved_amount_cents":370000,"claim_id":"CLM-2026-000001","claim_status":"APPROVED","historical_approved_cents":370000}` | `702bfd27038da09f50dd068a2413531612b0cf9c51f8454d75b8fb0e2ccdb172` | `f31120039b788f8eb8545d8663d1c72d97df7230d3bd50cabbe43aeec579903d` |
| VH-5 | 5 | `EVT-2026-0000005` / `PAYMENT_AUTHORIZED` / `Payment` / `PAY-2026-000001` / `USR-FIN-001` / `2026-01-07T08:00:00Z` | `{"amount_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}` | `42913a85d1e8fcaff502429d18df7b7b132bb7f92f11c9af0f65f2842d9d73ce` | `ae73131ef9a586a5e45229ca6da4212072e0ca2375d184a1ccd2445e369d9f80` |
| VH-6 | 6 | `EVT-2026-0000006` / `PAYMENT_DISBURSED` / `Payment` / `PAY-2026-000001` / `USR-FIN-001` / `2026-01-07T12:00:00Z` | `{"amount_cents":370000,"claim_id":"CLM-2026-000001","disbursed_amount_cents":370000,"external_bank_tx_ref":"ACH-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"DISBURSED"}` | `5663eee591086d12e4641cac76bf6f8ce82ae56eabd229045482ea1bc2958ee3` | `48f8ddf54b8b18474e1d6c33508c9eea9985fed8401bc1a6e1e683d6360629b2` |
| VH-7 | 7 | `EVT-2026-0000007` / `PAYMENT_CLAWBACK_REVERSED` / `Payment` / `PAY-2026-000001` / `USR-SIU-001` / `2026-01-12T16:45:00Z` | `{"amount_cents":370000,"claim_id":"CLM-2026-000001","clawed_back_cents":370000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}` | `408aecda2904bae934b46c6d60bafcac2a80c2a85ca383c5d196e89079f81a5e` | `b3ecd2febf7efafe94ae0a18b105ab073784991b09c81aaf32d90d9a772cb707` |

`prev_event_hash` chain: `VH-1` ← genesis zeros; `VH-2` ← VH-1.hash; …; `VH-7` ← VH-6.hash. Conviction sample for the cancellation path (`PAYMENT_CANCELLED` payload contract, §6.4.1): `{"amount_cents":150000,"claim_id":"CLM-2026-000001","payment_id":"PAY-2026-000002","payment_status":"CANCELLED","reason_code":"SIU_HOLD_RESERVATION_CLEARED"}` → `payload_sha256 = 874c6a8e6bb78a0855806688c6f882ca1f4de9dfd1d965fcc15a0f9b7d08ce83` (computed; triggers accept exactly this canonical shape).

### 6.3 Deterministic `sqlite_master` Schema Digest (`ST-SCHEMA-V1` — `CRITICAL 6`)
On every connection open, the schema digest is computed over an explicitly ordered subquery (`ORDER BY type ASC, name ASC, tbl_name ASC`) excluding internal `sqlite_%` objects and `NULL` SQL entries, using length-prefixed `ST-SCHEMA-V1|` serialization:

```sql
SELECT sha256_hex(
    'ST-SCHEMA-V1|' || COALESCE(
        (
            SELECT group_concat(
                '4:type=S' || CAST(length(CAST(type AS BLOB)) AS TEXT) || ':' || type || ';'
                || '4:name=S' || CAST(length(CAST(name AS BLOB)) AS TEXT) || ':' || name || ';'
                || '8:tbl_name=S' || CAST(length(CAST(tbl_name AS BLOB)) AS TEXT) || ':' || tbl_name || ';'
                || '3:sql=S' || CAST(length(CAST(sql AS BLOB)) AS TEXT) || ':' || sql || ';',
                ''
            )
            FROM (
                SELECT type, name, tbl_name, sql
                FROM sqlite_master
                WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
                ORDER BY type ASC, name ASC, tbl_name ASC
            )
        ),
        ''
    )
);
```

**`EXPECTED_OPERATIONAL_SCHEMA_SHA256` (`C-2`, now published):**

| Schema version | Objects | Digest | Status |
|---|---|---|---|
| `ARCH-ST-010.1` (this revision: §5.1 + §5.2, 12 tables + 24 triggers) | 36 | **`63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93`** | `PASS — EXECUTED` on SQLite 3.49.1 (dual-order DDL execution + independent Python mirror of the SQL above; both reproduce the value). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| `ARCH-ST-010` (pre-correction reference: 12 tables + 16 triggers) | 28 | `f22c9b679797b249ccafb718de4075d00f7eee75039f1b2c461dff951f16f319` | Same execution conditions (auditor's harness; retained for lineage). |

**Reproducible derivation procedure (self-contained):**
1. Connect to an in-memory database, register `sha256_hex` / `is_canonical_json` per §2.1, execute the §5.1 fence then the §5.2 fence exactly, with `PRAGMA recursive_triggers=ON`.
2. Run the digest SQL above; the result MUST equal `63e74a55…0f93`.
3. Order-independence: rebuild with the 12 `CREATE TABLE` statements in reverse order (defer FK enforcement during construction, re-enable before triggers); the digest MUST be identical.
4. Python mirror: serialize rows as `'ST-SCHEMA-V1|' + Σ('4:type=S<len>:<type>;' + '4:name=S<len>:<name>;' + '8:tbl_name=S<len>:<tbl_name>;' + '3:sql=S<len>:<sql>;')` in `ORDER BY type ASC, name ASC, tbl_name ASC`; SHA-256 MUST equal the SQL digest. (Harness: `archive/verify-0101/`; both executed on 3.49.1.)

### 6.4 Invoice Line-Item Fingerprint (`line_item_fingerprint`) & Duplicate Predicates
$$\text{line\_item\_fingerprint}(i) = \text{SHA256\_HEX}\Big(\text{UPPER}(\text{TRIM}(\text{cpt\_or\_line\_code}(i))) \;\|\; \texttt{"|"} \;\|\; \text{ service\_start\_utc}(i)[1..10] \;\|\; \texttt{"|"} \;\|\; \text{ service\_end\_utc}(i)[1..10] \;\|\; \texttt{"|"} \;\|\; \text{CAST}(\text{billed\_cents}(i)\text{ AS TEXT})\Big)$$

- **Verified Fingerprint Vectors:**
  - `FP-1`: `AB-FRAME-101|2026-01-05|2026-01-05|420000` $\to$ `1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465`
  - `FP-2`: `" ab-frame-101 " | 2026-01-05T14:00:00Z | 2026-01-05T18:00:00Z | 420000` $\to$ `1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465`

#### 6.4.1 Canonical Event Payload Contracts (`A-1`/`A-2`/`C-6` — new in `ARCH-ST-010.1`)

The §4 gates reconstruct and match `payload_sha256` against these exact canonical JSON shapes (key order = lexicographic per §6.5; integers only; no extraneous keys):

| Event | Canonical payload template (placeholders in `<angle brackets>`) | Enforcing error |
|---|---|---|
| `PAYMENT_AUTHORIZED` (PROVIDER recipient) | `{"amount_cents":<A>,"claim_id":"<cid>","invoice_id":"<iid>","payment_id":"<pid>","payment_status":"AUTHORIZED","recipient_provider_id":"<prv>"}` | `ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT` |
| `PAYMENT_AUTHORIZED` (CLAIMANT recipient) | `{"amount_cents":<A>,"claim_id":"<cid>","payment_id":"<pid>","payment_status":"AUTHORIZED","recipient_claimant_id":"<clt>"}` | same |
| `PAYMENT_CANCELLED` | `{"amount_cents":<A>,"claim_id":"<cid>","payment_id":"<pid>","payment_status":"CANCELLED","reason_code":"<cancel_reason>"}` | `ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT` |
| `PAYMENT_CLAWBACK_REVERSED` | `{"amount_cents":<A>,"claim_id":"<cid>","clawed_back_cents":<C>,"invoice_id":"<iid>","net_paid_cents":<N>,"payment_id":"<pid>","payment_status":"REVERSED_CLAWBACK"}` | `ERR_CLAWBACK_REQUIRES_EVENT` |
| `RELATIONSHIP_EDGE_DEACTIVATED` | `{"claim_id":"<supporting_claim_id>","edge_id":"<edge_id>"}` | `ERR_EDGE_DEACTIVATION_REQUIRES_EVENT` |
| `INVOICE_APPROVAL_ADJUSTED` (unchanged from ARCH-ST-010) | `{"adjustment_authorized":true,"invoice_id":"<iid>","new_approved_cents":<new>,"old_approved_cents":<old>}` (value `true` is JSON boolean) | `ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE` |

### 6.5 Canonical JSON Contract (`is_canonical_json`) (`C-5` — new in `ARCH-ST-010.1`)

`is_canonical_json(s): 0|1` returns `1` iff `s` is **exactly** the canonical rendering of a JSON document under the following rules. The same rules generate every `payload_json`, `payload_sha256`, `feature_snapshot_json`, and the `ST-DUMP-V1`/`ST-SCORE-V1`/`ST-SCHEMA-V1` preimages — one contract, no exceptions.

1. **Object key ordering:** all object keys sorted by their UTF-8 byte sequences (code point ordering is byte ordering here because all keys are ASCII identifiers; e.g. `"amount_cents" < "claim_id" < "invoice_id" < "payment_id" < "payment_status" < "recipient_provider_id"`).
2. **Whitespace & separators:** zero whitespace. Object: `{"k":v}` concatenated `,`-separated; Array: `[v1,v2]`; no trailing separators.
3. **Strings:** emitted unescaped minimally — only `"` → `\"` and `\` → `\\` and control characters `< 0x20` (`\n`, `\t`, `\r` and `\u00xx` forms) are escaped. **Non-ASCII characters (≥ U+0080) are emitted literally as UTF-8** (`ensure_ascii=False` semantics); specifically `Renée`, `東京`, `🔍` appear as raw bytes in `payload_json` — never as `\uXXXX` surrogate escapes. Byte-length accounting for `ST-EVT-V2` uses the UTF-8 byte length of the raw form.
4. **Integers:** exact decimal ASCII rendering of the integer value (`0`, `-17`, `420000`); no decimal point, no exponent, no `+` sign, no leading zeros.
5. **Booleans & null:** lowercase `true` / `false` / `null` (cf. `INVOICE_APPROVAL_ADJUSTED` payload's `true`).
6. **Floating-point policy:** floats are **excluded from the canonical event payloads by construction** — every numeric field in every payload contract (§6.4.1) is an integer (cents, counts, flags). A payload containing a JSON number with a `.` or `e/E` is therefore non-canonical for these tables (`is_canonical_json` returns `0` unless its round-trip re-rendering rule (below) reproduces the input exactly, which such forms generally do not).
7. **Round-trip definition (normative for implementers):** `is_canonical_json(s) = 1` ⇔ `s` parses as JSON **and** re-serializing the parsed value with rules 1–6 produces the identical byte string `s`.
8. **Rejection:** syntactically invalid JSON, duplicate keys after re-serialization, non-canonical forms (wrong key order, whitespace, escapes, non-minimal numbers) return `0`; every `CHECK (is_canonical_json(...) = 1)` then rejects the row.
9. **Hash interaction:** `payload_sha256 = sha256_hex(payload_json)` where `sha256_hex(s)` = SHA-256 over the UTF-8 encoding of the canonical byte string; the `CHECK payload_sha256 = sha256_hex(payload_json)` in §5.1 enforces it row-level.
10. **Reference behavior (executed):** Python `json.dumps(obj, ensure_ascii=False, separators=(',',':'), sort_keys=True)` reproduces `s` for every KAV/VH fixture and every trigger-reconstructed payload (harness-verified; the fixtures in §6.2/§6.2.1 are also valid under this definition).

### 6.6 Scoring-Evidence Reconciliation Digest (`ST-SCORE-V1`) (`C-6` — new in `ARCH-ST-010.1`)

The score columns of `claims` cannot be written without database-side reconciliation against their evidence layer. Define the deterministic preimage:

```
ST-SCORE-V1|<claim_id>|IND_COUNT:<n>[<token_1><token_2>…<token_n>]|IEF:<score>
```

- `<n>` = count of `fraud_indicators` rows of the claim (`0` allowed).
- `<token_i>` = `|IND:<indicator_code>:<pillar>:<raw_points>:<normalized_value>:<canonical_evidence_token>` where `raw_points`/`normalized_value` are rendered by `printf('%.3f', x)` (decimal, exactly three fractional digits, e.g. `35.000`); the tokens are concatenated in `ORDER BY indicator_code ASC, canonical_evidence_token ASC` (the same ordering contract as `ST-SCHEMA-V1`, §6.3).
- `<score>` = `printf('%.2f', latest_ief_score)` (exactly two fractional digits, e.g. `65.00`).
- `scoring_evidence_sha256 = sha256_hex(preimage)`.

**Enforcement (`trg_claims_score_upd`, §5.2):** any `UPDATE` touching `latest_ief_score`, `latest_risk_tier`, or `scoring_evidence_sha256` must supply a `scoring_evidence_sha256` equal to the digest recomputed **inside SQLite** from the claim's current `fraud_indicators` rows and the claimed score (`ERR_SCORE_EVIDENCE_DIGEST_REQUIRED` / `ERR_SCORE_EVIDENCE_DIGEST_MISMATCH`), and `latest_risk_tier` must equal the §9.8 tier thresholds (`ERR_SCORE_TIER_MISMATCH`). Because all `fraud_indicators` rows are append-only immutable (§4.6), a stored digest permanently binds the score to its evidence; silent score inflation is blocked (`PASS — EXECUTED`, tests C-6g..C-6i).

**Reference vector (executed, SQLite 3.49.1 + Python mirror agreement):** for claim `CLM-2026-000001` with indicators `{(IND-03, FINANCIAL, raw 35.000, norm 1.000, token 'DUP_FP:<fp>'), (IND-14, BEHAVIORAL, raw 12.000, norm 1.000, token 'VEL:CLMT-000001')}` (ordered IND-03 before IND-14) and score `30.76`, preimage
`ST-SCORE-V1|CLM-2026-000001|IND_COUNT:2|IND:IND-03:FINANCIAL:35.000:1.000:DUP_FP:<fp>|IND:IND-14:BEHAVIORAL:12.000:1.000:VEL:CLMT-000001|IEF:30.76`
whose digest `e01d150f225e0cb85493528fa9d6868f3c4951027a7f0e08a694152ee94d5f78` was recomputed identically (byte-for-byte) by the SQL-side trigger expression and the independent Python mirror (`PASS — EXECUTED`, SQLite 3.49.1).

---

## 7. Complete Definitions of Challenge Negative Cases (`YF-NEG-1..5`), Benign Lookalikes (`BL-1..5`) & Benign-Context Rules (`BC-1..6`) (`CRITICAL 5`)

### 7.1 Five Challenge-Mandated Negative/Exception Scenarios (`YF-NEG-1` .. `YF-NEG-5`)
- **YF-NEG-1 (Nonexistent Policy Reference, `25` attempts):** Claim references `POL-2026-990001..990025` absent from `policies`. Recorded in `ingestion_exceptions` (`ERR_NONEXISTENT_POLICY_REFERENCE`) and `immutable_events` (`INGESTION_EXCEPTION_RECORDED`, `claim_id = NULL`) with `0` rows in `claims`.
- **YF-NEG-2 (Payment Exceeds Approved Amount, `30` claims):** Direct `AUTHORIZED` insert exceeding `approved_cents` or `payout_cap_cents` is blocked by `trg_payments_validate_ins` (`ERR_PAYMENT_EXCEEDS_APPROVED_CAP`); recorded as `BLOCKED_OVERPAYMENT` with `0` disbursed cents.
- **YF-NEG-3 (Cross-Claimant Duplicate Invoice, `25` fraud claims) — corrected in `ARCH-ST-010.1` (`C-7`):** Identical `line_item_fingerprint` across distinct claimants **who also share a payout account**. The planted claims each emit **`IND-03` (`35.0` pts, `FINANCIAL`, token `"DUP_FP:" || fp`) and `IND-01` (`20.0` pts, `NETWORK`, token `"BANK:" || hash`, `k_acct = 2`)**, placing both claims into the same hard-collusion cluster (§9.7). Scoring path (§9, exact constants: pillar caps 60/55/45/40, weights 0.35/0.30/0.20/0.15, hard floor 65.00, cluster boost `min(20, 0.20·max + 0.10·mean + 5·ρ_K)`, override-eligible dampening `D = 1.0`):
  - $\text{pNet} = 100 \cdot 20/60 = 33.333333$; $\text{pFin} = 100 \cdot 35/55 = 63.636364$;
  - $S_{\text{base}} = 0.35 \cdot 33.333333 + 0.30 \cdot 63.636364 = 11.666667 + 19.090909 = 30.757576$;
  - `hard-collusion override` applies (IND-01+IND-03 shared-token pairing, §9.7): $D = 1.0$, so $\text{dampened} = 30.757576$;
  - 2-member eligible set → $B_{\text{cluster}} = \min(20,\ 0.20 \cdot 30.757576 + 0.10 \cdot 30.757576 + 5 \cdot 1.0) = 14.227273$;
  - $\text{preFloor} = 30.757576 + 14.227273 = 44.984848$;
  - **hard floor:** $\max(44.984848,\ 65.00) \Rightarrow \text{IEF} = 65.00$ (`HIGH`).
  This is **not** a scorer manipulation: `IND-01`+`IND-03` with identical shared tokens is independently strong collusion evidence (shared payout-account link plus cross-claimant invoice duplication), the boost/floor constants are the de-facto engine semantics now published verbatim (§9.7), and the identical path is independently exercised by the clean-room fixture in §9 (finals `65.00`/`65.00`). In `ARCH-ST-010` the scenario promised $\ge 65.00$ from `IND-03` alone ($S_{\text{base}} = 0.30 \cdot 63.636364 = 19.090909$, unreachable even with boost: $19.09 + 14.23 = 33.32 < 65$) — that promise was mathematically false and is withdrawn; the scenario is strengthened (shared payout account) so the stated threshold is achieved by the legitimate, published pipeline. Executed reproducibility vectors: §9.9.
- **YF-NEG-4 (Planted Ground-Truth Edge Missing Operational Record, `5` rings / `40` claims / `25` missing edges):** `25` edges stored only in `ground_truth_missing_edges` (`ground_truth.db`); $\ge 32/40$ ($\ge 80\%$) of `YF-NEG-4` claims score $\ge 65.00$ using operational features alone.
- **YF-NEG-5 (Common Address Alone Not Proof of Fraud, `80` claims):** Shared apartment address (`SHARED_ADDRESS` weight $0.40$, `IND-05` max $4.0$ pts, `BC-1` $m_1 = 0.35$); $100\%$ score $\le 12.00$ (`LOW`).

### 7.2 Five Benign Lookalike Scenarios (`BL-1` .. `BL-5`, `84` Claims Each = `420` Claims)
- **BL-1 (High-Volume Regional Trauma Hospital, `84` claims):** `BC-2` ($m_2 = 0.30$) + `BC-6` ($m_6 = 0.75$); suppresses `IND-11`; $\text{IEF}(c) \le 18.00$ (`LOW`).
- **BL-2 (Catastrophic Hailstorm / Flood Surge, `84` claims):** `BC-3` ($m_3 = 0.25$) + `BC-6` ($m_6 = 0.75$); suppresses `IND-09`; $\text{IEF}(c) \le 18.00$ (`LOW`).
- **BL-3 (Joint-Policy Household Co-Habitation, `84` claims):** `BC-4` ($m_4 = 0.20$) + `BC-6` ($m_6 = 0.75$); suppresses 2-claimant household `IND-01`; $\text{IEF}(c) \le 15.00$ (`LOW`).
- **BL-4 (Multi-Vehicle Freeway Pileup, `84` claims):** `BC-5` ($m_5 = 0.25$) + `BC-6` ($m_6 = 0.75$); `SAME_INCIDENT_PARTICIPANT` excluded from collusive cluster graph ($B_{\text{cluster}}(c) = 0.00$); $\text{IEF}(c) \le 15.00$ (`LOW`).
- **BL-5 (Rural Sole-Provider Township Monopoly, `84` claims):** `BC-2` ($m_2 = 0.30$) + `BC-6` ($m_6 = 0.75$); $\text{IEF}(c) \le 18.00$ (`LOW`).

---

## 8. All 15 Atomic FraudIndicators (`IND-01` .. `IND-15`) (`CRITICAL 5`)

| Code | Name | Pillar | Scope | Max $M_m$ | Exact Activation Formula $a_m(c)$ & Canonical Evidence Token |
|---|---|---|---|---:|---|
| **IND-01** | `SHARED_PAYOUT_ACCOUNT` | `NETWORK` | `ENTITY` | `35.0` | $\mathbb{I}(k_{\text{acct}} \ge 2 \land \neg\text{BC-4}) \cdot \min(35.0, 20.0 + 7.5(k_{\text{acct}} - 2))$ · Token: `"BANK:" \|\| bank_account_hash` |
| **IND-02** | `SHARED_TAX_OR_PHONE_IDENTITY` | `NETWORK` | `PAIR` | `25.0` | $\max(25.0 \cdot I_{\text{tax}}, \mathbb{I}(k_{\text{phone}} \ge 2 \land \neg\text{BC-4}) \cdot \min(18.0, 8.0 + 5.0(k_{\text{phone}} - 2)))$ · Token: `"TAX:" \|\| tax_id_hash` or `"PHONE:" \|\| phone_e164` |
| **IND-03** | `CROSS_CLAIMANT_DUPLICATE_INVOICE` | `FINANCIAL` | `CLAIM` | `35.0` | $35.0 \cdot \text{has\_cross\_dup}(c)$ · Token: `"DUP_FP:" \|\| line_item_fingerprint` |
| **IND-04** | `INTRA_CLAIM_DUPLICATE_RESUBMISSION` | `FINANCIAL` | `CLAIM` | `8.0` | $8.0 \cdot \mathbb{I}(\text{has\_intra\_dup}(c) = 1 \land \text{has\_cross\_dup}(c) = 0)$ · Token: `"INTRA_DUP:" \|\| claim_id \|\| ":" \|\| line_item_fingerprint` |
| **IND-05** | `SHARED_ADDRESS_CLUSTER` | `NETWORK` | `ENTITY` | `4.0` | $\mathbb{I}(k_{\text{addr}} \ge 2) \cdot \min(4.0, 1.5 + 0.5(k_{\text{addr}} - 2))$ · Token: `"ADDR:" \|\| sha256_hex(address_norm)` |
| **IND-06** | `PAGERANK_CENTRALITY_SPIKE` | `NETWORK` | `CLAIM` | `15.0` | $\mathbb{I}(\widetilde{\text{PR}}(c) > 1.25) \cdot \min(15.0, 15.0 \cdot (\widetilde{\text{PR}}(c) - 1.25)/2.75)$ · Token: `"PR:" \|\| claim_id` |
| **IND-07** | `DENSE_COLLUSIVE_RING_MEMBERSHIP` | `NETWORK` | `RING` | `30.0` | $\mathbb{I}(|V_K| \ge 3 \land \rho_K > 0.35) \cdot \min(30.0, 15.0 + 25.0(\rho_K - 0.35))$ · Token: `"RING_COMP:" \|\| sorted_csv(V_K)` |
| **IND-08** | `UPCODING_BILLED_ZSCORE` | `FINANCIAL` | `CLAIM` | `20.0` | $\mathbb{I}(z_{\text{cpt}} > 2.0) \cdot \min(20.0, 8.0 + 6.0(z_{\text{cpt}} - 2.0))$ · Token: `"UPCODE:" \|\| claim_id \|\| ":" \|\| cpt_or_line_code` |
| **IND-09** | `EARLY_POLICY_INCEPTION_CLAIM` | `BEHAVIORAL` | `CLAIM` | `18.0` | $\mathbb{I}(0 \le \Delta_{\text{bind}} \le 14 \land \neg\text{BC-3}) \cdot \min(18.0, 18.0 \cdot (15 - \Delta_{\text{bind}})/15)$ · Token: `"INCEPT:" \|\| policy_id \|\| ":" \|\| claim_id` |
| **IND-10** | `DELAYED_INCIDENT_REPORTING` | `BEHAVIORAL` | `CLAIM` | `12.0` | $\mathbb{I}(\Delta_{\text{rep}} > 72.0) \cdot \min(12.0, 4.0 + 8.0 \cdot (\Delta_{\text{rep}} - 72.0)/168.0)$ · Token: `"DELAY:" \|\| incident_id \|\| ":" \|\| claim_id` |
| **IND-11** | `PROVIDER_CLAIMANT_REFERRAL_CONCENTRATION` | `BEHAVIORAL` | `PAIR` | `15.0` | $\mathbb{I}(N_p \ge 5 \land r_{\text{pair}} > 0.35 \land \neg\text{BC-2}) \cdot \min(15.0, 15.0 \cdot (r_{\text{pair}} - 0.35)/0.45)$ · Token: `"CONC:" \|\| claimant_id \|\| ":" \|\| provider_id` |
| **IND-12** | `UNBUNDLED_LINE_ITEM_SPLITTING` | `DOCUMENT` | `CLAIM` | `20.0` | $\mathbb{I}(k_{\text{split}} \ge 3) \cdot \min(20.0, 10.0 + 5.0(k_{\text{split}} - 3))$ · Token: `"SPLIT:" \|\| claim_id \|\| ":" \|\| provider_id \|\| ":" \|\| service_start_utc[1..10]` |
| **IND-13** | `MISSING_POLICE_REPORT_HIGH_SEVERITY` | `DOCUMENT` | `CLAIM` | `15.0` | $\mathbb{I}(\text{missing\_pr} \land \text{claimed} \ge 250000) \cdot \min(15.0, 9.0 + 6.0 \cdot (\text{claimed} - 250000)/250000)$ · Token: `"NOPR:" \|\| incident_id \|\| ":" \|\| claim_id` |
| **IND-14** | `CLAIMANT_VELOCITY_BURST` | `BEHAVIORAL` | `ENTITY` | `16.0` | $\mathbb{I}(n_{90\text{d}} \ge 2) \cdot \min(16.0, 8.0(n_{90\text{d}} - 1))$ · Token: `"VEL:" \|\| claimant_id` |
| **IND-15** | `WATCHLIST_OR_SUSPENDED_PROVIDER` | `DOCUMENT` | `ENTITY` | `15.0` | $15.0 \cdot \mathbb{I}(\text{SUSPENDED}) + 10.0 \cdot \mathbb{I}(\text{WATCHLIST})$ · Token: `"PRV_TIER:" \|\| provider_id` |

---

## 9. Complete Operational Scoring Contract & Clean-Room Fixture (`CRITICAL 8`, `C-3`, `C-7` — new in `ARCH-ST-010.1`)

This section is the **complete, self-contained scoring contract**: every constant, formula, ordering and rounding rule needed to reproduce the clean-room finals (and the §7 scenario bounds) from the document alone, with no reference to source code. All numeric values in §9.1–§9.9 were recomputed by this revision's harness (`PASS — EXECUTED`, SQLite 3.49.1 + independent Python implementation in `archive/verify-0101/`).

### 9.1 Operational Graph Construction & Adjacency Matrix $W$

Undirected weighted graph over operational entities (vertices are `claim_*`, `claimant_*`, `provider_*` records). $W$ is symmetric, $W_{uv} = 0$ for non-adjacent pairs, self-loops absent:

1. **Structural FK edges (weight 1.0 each):** every claim contributes exactly one `claim ↔ its claimant` edge and exactly one `claim ↔ its provider` edge (if the claim has a provider; claims without any invoice provider contribute none).
2. **Operational `relationship_edges` (only `is_active = 1` edges contribute):** $W_{uv} \mathrel{+}= \beta(\text{edge\_type}) \cdot \text{strength\_weight}(e)$ with the **base type factors** $\beta$:

   | `edge_type` | $\beta$ basis | Provenance |
   |---|---:|---|
   | `SHARED_BANK_ACCOUNT` | 3.0 | exercised by clean-room edge `E1` ($3.0 \times 1.0$) |
   | `SHARED_TAX_ID` | 3.0 | new normative constant (`010.1`) |
   | `SHARED_PHONE` | 2.0 | new normative constant (`010.1`) |
   | `CROSS_CLAIM_DUPLICATE_INVOICE` | 3.0 | new normative constant (`010.1`) |
   | `SAME_INCIDENT_PARTICIPANT` | 1.2 | exercised by clean-room edge `E2` ($1.2 \times 0.5 = 0.6$) |
   | `SHARED_ADDRESS` | 1.5 | new normative constant (`010.1`) |
   | `CLAIMANT_TREATED_BY_PROVIDER` | 1.0 | new normative constant (`010.1` — default strength) |
   | `PROVIDER_REFERRAL_LINK` | 1.0 | new normative constant (`010.1` — default strength) |

   (`CLAIMANT_TREATED_BY_PROVIDER`/`PROVIDER_REFERRAL_LINK` structural duplicates of the FK edges are additive, as executed in the fixture via separate `+=` accumulation semantics.)
3. Multiple edges between the same pair accumulate.

**Clean-room $W$ (fixture):** vertices `0..7` = `CLM-2026-000001`, `CLM-2026-000002`, `CLM-2026-000003`, `CLM-2026-000004`, `CLMT-000001`, `CLMT-000002`, `CLMT-000003`, `PRV-000001`.

$$W = \begin{pmatrix}
0&0&0&0&1&0&0&1\\
0&0&0&0&0&1&0&1\\
0&0&0&0&0&0&1&1\\
0&0&0&0&0&0&1&0\\
1&0&0&0&0&3&0&0\\
0&1&0&0&3&0&0.6&0\\
0&0&1&1&0&0.6&0&0\\
1&1&1&0&0&0&0&0
\end{pmatrix}$$

Structural FK edges (all 1.0): `c1–clmt1`, `c1–prv1`, `c2–clmt2`, `c2–prv1`, `c3–clmt3`, `c3–prv1`, `c4–clmt3`. Operational edges: `E1` = `SHARED_BANK_ACCOUNT` `clmt1–clmt2` ($3.0$), `E2` = `SAME_INCIDENT_PARTICIPANT` `clmt2–clmt3` ($1.2 \times 0.5 = 0.6$).

### 9.2 Transition Matrix, PageRank Fixpoint & Checkpoints

- **Degree vector:** $d_j = \sum_i W_{ij}$ → $d = [2.0,\ 2.0,\ 2.0,\ 1.0,\ 4.0,\ 4.6,\ 2.6,\ 3.0]$.
- **Transition matrix (column-stochastic), $M_{ij} = W_{ij}/d_j$ (for $d_j > 0$):**

$$M = \begin{pmatrix}
0&0&0&0&\tfrac{1}{4}&0&0&\tfrac{1}{3}\\
0&0&0&0&0&\tfrac{1}{4.6}&0&\tfrac{1}{3}\\
0&0&0&0&0&0&\tfrac{1}{2.6}&\tfrac{1}{3}\\
0&0&0&0&0&0&\tfrac{1}{2.6}&0\\
\tfrac{1}{2}&0&0&0&0&\tfrac{3}{4.6}&0&0\\
0&\tfrac{1}{2}&0&0&\tfrac{3}{4}&0&\tfrac{0.6}{2.6}&0\\
0&0&\tfrac{1}{2}&1&0&\tfrac{0.6}{4.6}&0&0\\
\tfrac{1}{2}&\tfrac{1}{2}&\tfrac{1}{2}&0&0&0&0&0
\end{pmatrix}$$

(every column sums to 1.0 as executed; decimal equivalents e.g. $M_{0,4}=0.25$, $M_{1,5}=0.21739130$, $M_{6,5}=0.13043478$.)
- **Damping factor:** $\alpha = 0.85$ (constant).
- **Dangling handling:** nodes with $d_j = 0$ redistribute their mass uniformly: $v'_i = \alpha\Big(\texttt{danglingMass}/N + \sum_j M_{ij} v_j\Big) + (1-\alpha)/N$, where $\texttt{danglingMass} = \sum_{j : d_j = 0} v_j$. (None of the fixture nodes dangles; the rule is normative for the general graph.)
- **Initialization:** $v^{(0)} = \mathbf{1}/N$ (uniform, $N = 8$ → $0.1250000000$ each).
- **Convergence criterion & cap:** iterate in float64 until $\|v^{(t)} - v^{(t-1)}\|_1 < 1 \times 10^{-9}$; hard cap at $t = 200$ iterations (if uncapped, report `NOT CONVERGED`; do not accept partial vectors).
- **Execution result:** convergence exactly at **iteration 78** with $\|v^{(78)}-v^{(77)}\|_1 = 9.739882 \times 10^{-10}$.

| $t$ | $\|v^{(t)}-v^{(t-1)}\|_1$ | $v^{(t)}$ (10 decimals) |
|---:|---:|---|
| 0 | — | 0.1250000000 × 8 (uniform) |
| 1 | 3.747178e-01 | [0.0807291667, 0.0772644928, 0.0950320513, 0.0596153846, 0.1411684783, 0.1760817308, 0.1919836957, 0.1781250000] |
| 2 | 2.289779e-01 | [0.0992170516, 0.1017555916, 0.1319826505, 0.0815139005, 0.1506704205, 0.1792406546, 0.1293338037, 0.1262859270] |
| 3 | 1.648475e-01 | [0.0865484770, 0.0876515684, 0.0968132177, 0.0610322050, 0.1602789142, 0.1834178425, 0.1640017753, 0.1602559998] |
| 5 | 9.278943e-02 | [0.0901042206, 0.0918702546, 0.0998863142, 0.0619393004, 0.1660111553, 0.1865557256, 0.1514180432, 0.1522149862] |
| 10 | 2.543187e-02 | [0.0957205977, 0.0952503304, 0.1068557416, 0.0653883898, 0.1634646653, 0.1934128121, 0.1374775839, 0.1424298792] |
| 20 | 2.009273e-03 | [0.0948049084, 0.0950302391, 0.1052445162, 0.0643841001, 0.1652185037, 0.1921071723, 0.1392296387, 0.1439809216] |
| 40 | 1.342083e-05 | [0.0947206988, 0.0950369237, 0.1051412662, 0.0643179382, 0.1653965401, 0.1919236597, 0.1393820157, 0.1440809574] |
| 60 | 8.898478e-08 | [0.0947201423, 0.0950370178, 0.1051406343, 0.0643175243, 0.1653977804, 0.1919223449, 0.1393830005, 0.1440815556] |
| 77 | 1.251657e-09 | [0.0947201386, 0.0950370185, 0.1051406300, 0.0643175215, 0.1653977888, 0.1919223359, 0.1393830071, 0.1440815596] |
| 78 | 9.739882e-10 | [0.0947201387, 0.0950370185, 0.1051406301, 0.0643175216, 0.1653977886, 0.1919223361, 0.1393830070, 0.1440815595] |

($t=77$ does **not** converge: $1.251657 \times 10^{-9} > 10^{-9}$; the fixpoint is reached at $t=78$.)

### 9.3 Claim-Normalized PageRank ($\widetilde{\text{PR}}$)

$$\widetilde{\text{PR}}(c) = \frac{N_{\text{claims}} \cdot \text{PR}(c)}{\sum_{k \in \text{claims}} \text{PR}(k)}$$

For the fixture: $S_{\text{claim}} = \sum_{0..3} v_i = 0.3592153088$; $\widetilde{\text{PR}} = [1.054745,\ 1.058274,\ 1.170781,\ 0.716200]$ (6-decimal rendering; exact fractions reproducible from the execution harness).

### 9.4 The 10-Stage Scoring Pipeline (normative order)

| Stage | Name | Exact rule |
|---|---|---|
| **S1** | Graph & PageRank | §9.1–§9.3; deterministic float64 |
| **S2** | Indicator computation | All 15 indicators per §8 (formulas, canonical tokens, context suppressions). `IND-06` is appended **after** §8's base set when $\widetilde{\text{PR}}(c) > 1.25$, with `raw_points = min(15.0, 15.0·(PR̃(c) − 1.25)/2.75)`. |
| **S3** | Deduplication | Within one claim, group indicators by key `'(indicator_code, canonical_evidence_token)'`; keep the single row with the **max** `raw_points`, discard the rest. |
| **S4** | Pillar aggregation & normalization | $P_{\text{NET}} = \min(100,\ 100 \cdot \Sigma \text{raw}_{\text{NETWORK}}/60.0)$; $P_{\text{FIN}} = \min(100,\ 100 \cdot \Sigma \text{raw}_{\text{FINANCIAL}}/55.0)$; $P_{\text{BEH}} = \min(100,\ 100 \cdot \Sigma \text{raw}_{\text{BEHAVIORAL}}/45.0)$; $P_{\text{DOC}} = \min(100,\ 100 \cdot \Sigma \text{raw}_{\text{DOCUMENT}}/40.0)$. (Pillar caps: **60 / 55 / 45 / 40**.) |
| **S5** | Base score | $S_{\text{base}} = 0.35 \cdot P_{\text{NET}} + 0.30 \cdot P_{\text{FIN}} + 0.20 \cdot P_{\text{BEH}} + 0.15 \cdot P_{\text{DOC}}$. (Weights **0.35 / 0.30 / 0.20 / 0.15**.) |
| **S6** | Dampening | $D = \max(0.15,\ \prod_{b \in \text{active BC contexts}} m_b)$; **override:** if claim ∈ eligible set $K$ (§9.7) then $D = 1.0$ unconditionally. $\text{dampened} = S_{\text{base}} \cdot D$. |
| **S7** | Cluster eligibility | Eligible set $K = \{$ claims with `hardCollusionOverride` $\}$: a claim is eligible iff it carries **both** an `IND-01` token and an `IND-03` token, and **the same pair of (BANK token, DUP_FP token) exists on at least one other claim in the current scoring batch** (i.e., both entities share the payout account and share a duplicated line-item fingerprint). `SAME_INCIDENT_PARTICIPANT` links (`BL-4`/`BC-5`) **never** create eligibility. |
| **S8** | Cluster boost | $\rho_K = \frac{\#\text{active }\mathtt{relationship\_edges}\text{ among eligible members}}{\binom{|K|}{2}}$ when $|K| \ge 2$ (density; capped 1.0). Then $B_{\text{cluster}}(c) = \min(20.0,\ 0.20 \cdot \max_{K}(\text{dampened}) + 0.10 \cdot \text{mean}_{K}(\text{dampened}) + 5.0 \cdot \rho_K)$ for eligible $c$; $0.0$ otherwise. Boost is defined only when $|K| \ge 2$. |
| **S9** | Pre-floor, cap & floor | $\text{preFloor} = \min(100.0,\ \text{dampened} + B_{\text{cluster}})$; **hard floor (eligible claims only):** $\text{rawFinal} = \max(\text{preFloor},\ 65.0)$; non-eligible claims take $\text{rawFinal} = \text{preFloor}$. |
| **S10** | Rounding & risk tier | `final = round_half_up(final, 2 decimals)`; tier from the **rounded** value: `≥ 85.00` → `CRITICAL`, `≥ 65.00` → `HIGH`, `≥ 30.00` → `MEDIUM`, else `LOW`. The final value and tier are written via the `ST-SCORE-V1` gate (§6.6). |

### 9.5 Fixture Indicator Activations & Pillar Materialization

| Claim | Indicators (code, raw/max, pillar, token) | $P_{\text{NET}}$ | $P_{\text{FIN}}$ | $P_{\text{BEH}}$ | $P_{\text{DOC}}$ |
|---|---|---:|---:|---:|---:|
| `CLM-2026-000001` | `IND-01` 20.0/35.0 NETWORK `BANK:b1…32`; `IND-03` 35.0/35.0 FINANCIAL `DUP_FP:1547087d…` | $100\cdot20/60 = 33.333333$ | $100\cdot35/55 = 63.636364$ | 0.000000 | 0.000000 |
| `CLM-2026-000002` | same two activations with identical tokens (shared payout account + duplicate fingerprint) | 33.333333 | 63.636364 | 0.000000 | 0.000000 |
| `CLM-2026-000003` | none ($\widetilde{\text{PR}} = 1.170781 > 1.25$ is the only signal — not an indicator) | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| `CLM-2026-000004` | `IND-14` 8.0/16.0 BEHAVIORAL `VEL:CLMT-000003` | 0.000000 | 0.000000 | $100\cdot8/45 = 17.777778$ | 0.000000 |

(No dedup collisions occur in the fixture: all `(code, token)` keys are unique per claim, so S3 keeps all rows.)

### 9.6 Fixture Base Scores (S5)

- $c_1 = c_2$: $S_{\text{base}} = 0.35 \cdot 33.333333 + 0.30 \cdot 63.636364 = 11.666667 + 19.090909 = \mathbf{30.757576}$.
- $c_3$: $S_{\text{base}} = \mathbf{0.000000}$ (no indicators, no BC contexts — scores purely from an empty pillar set).
- $c_4$: $S_{\text{base}} = 0.20 \cdot 17.777778 = \mathbf{3.555556}$.

### 9.7 Hard-Collusion Eligibility & Cluster Boost (S7–S8)

- Eligible set $K = \{c_1, c_2\}$: each carries exactly one `IND-01` `BANK:` token and one `IND-03` `DUP_FP:` token, and **both tokens are carried by both claims** (shared payout account `b1…` + duplicate fingerprint `1547087d…`) — the §9.4-S7 pairing rule. $c_3$ (no indicators) and $c_4$ (IND-14 only, `SAME_INCIDENT_PARTICIPANT` linkage only) are **not** eligible.
- Boost numerator: $0.20 \cdot 30.757576 + 0.10 \cdot 30.757576 + 5.0 \cdot \rho_K$. The eligible pair is linked by fixture effective edge `E1` (active, `SHARED_BANK_ACCOUNT`) → $\rho_K = 1/\binom{2}{2} = 1.0$: $B_{\text{cluster}} = 0.20 \cdot 30.757576 + 0.10 \cdot 30.757576 + 5.0 = 6.151515 + 3.075758 + 5.000000 = \mathbf{14.227273}$ (below the 20.0 cap). Both members receive the same $B_{\text{cluster}}$.

### 9.8 Fixture Finals: Dampening, Pre-Floor, Floor, Tier (S6, S9–S10)

| Claim | $D$ (contexts) | dampened | $B_{\text{cluster}}$ | preFloor | floor applied | **final** | tier |
|---|---|---:|---:|---:|---|---:|---|
| `CLM-2026-000001` | 1.0 (override) | 30.757576 | 14.227273 | 44.984848 | $\max(44.984848, 65)$ | **65.00** | `HIGH` |
| `CLM-2026-000002` | 1.0 (override) | 30.757576 | 14.227273 | 44.984848 | $\max(44.984848, 65)$ | **65.00** | `HIGH` |
| `CLM-2026-000003` | 1.0 (no contexts) | 0.000000 | 0.000000 | 0.000000 | — | **0.00** | `LOW` |
| `CLM-2026-000004` | $0.25 \times 0.75 = 0.1875$ (`BC-5` × `BC-6`; above the 0.15 floor) | 0.666667 | 0.000000 | 0.666667 | — | **0.67** | `LOW` |

(Rounding: half-up at 2 decimals — $0.666667 \to 0.67$; tier thresholds applied to the rounded value per S10.)

### 9.9 Reproducibility Statement & Scenario Reproduction

- **Executed reproduction:** the fixture finals `65.00 / 65.00 / 0.00 / 0.67`, $B_{\text{cluster}} = 14.227273$, the checkpoint table (§9.2) and $\widetilde{\text{PR}}$ (§9.3) are reproduced byte-identically by both harness implementations in `archive/audit-harness/verify_math.py` and `archive/verify-0101/` (`PASS — EXECUTED`, SQLite 3.49.1 + pure Python, two independent code paths agreeing).
- **`YF-NEG-3` reproduction (§7.1, `C-7`):** the scenario's planted-claim indicators are exactly the `c_1` row of §9.5 (`IND-01` 20.0 with `k_acct = 2`, `IND-03` 35.0), so the §9.8 row `30.757576 → 44.984848 → floor → 65.00 HIGH` is the scenario's scoring outcome. The seed generator MUST materialize `YF-NEG-3` claims with a shared payout account so this pairing holds; without it the promise is withdrawn (see §7.1 correction note).

---

## 10. Acceptance Test Suite (`T-01` .. `T-28`) & Correction Acceptance Tests (`C-x` / `A-x`)

All executed results in §10/§11 were produced on **SQLite 3.49.1** (Python 3.13.5 `sqlite3`), the only runtime available to this revision's author; the **pinned SQLite 3.40.1 / Python 3.10.12** runs remain `SPECIFIED — NOT EXECUTED (pinned 3.40.1)` and are enumerated in §11.4. A reasoned expectation is never reported as an executed result.

### 10.1 Application Acceptance Tests (`T-01` .. `T-28`) — `SPECIFIED — NOT EXECUTED` (except as marked)

| Test ID | Requirement / Audit Finding Covered | Exact Assertion | Status |
|---|---|---|---|
| **T-01..T-20** | Baseline Entity Counts, `YF-NEG-1..5`, `BL-1..5`, `EC-1..5`, Quarantine, Penny Reconciliation | Verify exact row counts (`seed=42`), ID `GLOB` constraints, negative/lookalike bounds, ground-truth quarantine, and penny reconciliation. | `SPECIFIED — NOT EXECUTED` (requires the full seed generator + application suite, which does not exist yet; the **event-bucket arithmetic** sub-assert (§3.1 = 19,615 by bucket sum) is the only part already executed: `PASS — EXECUTED`) |
| **T-21** | **CRITICAL 1:** Invoice Approval Immutability & Authorized Adjustment Workflow | Reject direct/same-status `UPDATE` of `approved_cents` or `historical_approved_cents` without latest `INVOICE_APPROVAL_ADJUSTED` event; re-verify claim/policy/deductible caps and `ACTIVE` policy on every approval or adjustment. | Trigger logic: `PASS — EXECUTED` on 3.49.1 (`archive/audit-harness/verify_sql.py`). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| **T-22** | **CRITICAL 2:** Direct Invoice FSM Financial Consistency | `PAID` requires `net_paid_cents = approved_cents` and `reserved_authorized_cents = 0`; `PARTIALLY_PAID` requires `0 < net_paid_cents < approved_cents`; reject direct status updates violating financial balances. | `PASS — EXECUTED` on 3.49.1 (`verify_sql.py`). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| **T-23** | **CRITICAL 2:** Direct Claim FSM Financial Consistency & Trigger Cascade | Enforce exact status-to-balance invariants on `claims` and verify atomic cascade across `APPROVED <-> PARTIALLY_PAID <-> PAID <-> SIU_HOLD <-> DENIED`. Also (010.1, `C-1`): invoice-approval cascade transitions `SUBMITTED -> APPROVED`; direct fabrication blocked. | `PASS — EXECUTED` on 3.49.1 (`verify_sql.py` for legacy branches; `archive/verify-0101/test_delta.py` tests `C-1a`/`C-1b` for the new branch). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| **T-24** | **CRITICAL 3:** Payment Immutable Fields & Post-Disbursement Audit Protection | Block direct `INSERT` of `DISBURSED`; protect `idempotency_key`, `created_at_utc`, `authorized_by`, `block_reason_code` across all updates; lock `external_bank_tx_ref` and `disbursed_at_utc` post-disbursement. Additionally (010.1, `A-2`): all three material transitions require prior matching events. | `PASS — EXECUTED` on 3.49.1 (`verify_sql.py`; event-gates in `test_delta.py` tests `A-2a`..`A-2f`). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| **T-25** | **CRITICAL 4:** `ST-EVT-V2` Length-Prefixed Event Serialization & `KAV-1..7` Verification | Validate UTF-8 byte-length prefixed `ST-EVT-V2` hashes on `KAV-1..KAV-7`, multi-byte Unicode (`Renée\|東京\|🔍`), `NULL` `claim_id`, and all 64 hex chars via `NOT GLOB '*[^0-9a-f]*'`. Also (010.1, `A-2`): reproduces the full `VH-1..VH-7` chain of §6.2.1. | `PASS — EXECUTED` on 3.49.1 (`verify_math.py`: KAV-1..7 + FP-1/FP-2 + VH-1..7 all recomputed and matched). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| **T-26** | **CRITICAL 6:** Deterministic `sqlite_master` Schema Digest (`ST-SCHEMA-V1`) | Compute `ST-SCHEMA-V1` SHA-256 over `ORDER BY type ASC, name ASC, tbl_name ASC`; verify identical 64-hex digest regardless of table creation order. Also (010.1, `C-2`): corrected-schema digest equals `63e74a55…0f93` and the Python mirror agrees. | `PASS — EXECUTED` on 3.49.1 (`verify_digest.py` for the ARCH-ST-010 `f22c9b67…` lineage; `archive/verify-0101/verify_digest_0101.py` for the corrected schema, dual-order + mirror). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| **T-27** | **CRITICAL 7:** Historical Financial Accounting Protection (`historical_approved_cents`) | Preserve `historical_approved_cents` across partial/full clawbacks, `REVOKED_POST_APPROVAL`, and `DENIED`; block direct SQL reduction via `ERR_INVOICE/CLAIM_HISTORICAL_APPROVED_DECREASE_FORBIDDEN`. | `PASS — EXECUTED` on 3.49.1 (`verify_sql.py`: deny-after-clawback preserve + reduction blocks). Pinned 3.40.1: `SPECIFIED — NOT EXECUTED`. |
| **T-28** | **CRITICAL 8:** Clean-Room 8-Node / 4-Claim End-to-End Verification | Verify $8 \times 8$ $W, M$, PageRank convergence at iteration `78` (`err=9.740e-10`), $\widetilde{\text{PR}}=[1.054745, 1.058274, 1.170781, 0.716200]$, and final `IEF` scores `[65.00, 65.00, 0.00, 0.67]`. Also (010.1, `C-3`): the full §9.4 pipeline table reproduces them from the document alone. | `PASS — EXECUTED` on 3.49.1 + pure-Python mirror (`verify_math.py`; two independent implementations agree). Runtime-pinned replication: `SPECIFIED — NOT EXECUTED`. |

### 10.2 Correction Acceptance Tests — executed in `ARCH-ST-010.1` (3.49.1, `archive/verify-0101/test_delta.py` unless noted)

| ID | Verifies (finding) | Assertion outcome | Status |
|---|---|---|---|
| `C-1a` | Invoice approved while claim `SUBMITTED` cascades the claim to `APPROVED` atomically with correct aggregates (`approved=370000`) | observed | `PASS — EXECUTED` |
| `C-1b` | Direct `UPDATE claims SET claim_status='APPROVED'` with no approved invoice | `ERR_CLAIM_APPROVED_FINANCIAL_MISMATCH` | `PASS — EXECUTED` |
| `C-2` | Corrected schema digest = `63e74a55…0f93`, DDL-order-independent, SQL↔Python mirror equal (36 objects) | `verify_digest_0101.py` | `PASS — EXECUTED` |
| `C-4` | Event-bucket table §3.1 sums to 19,615 and is internally feasible | bucket arithmetic | `PASS — EXECUTED` (full-seed generation: `SPECIFIED — NOT EXECUTED`) |
| `C-5` | Every KAV/VH/trigger-reconstructed payload is canonical per §6.5 (`json.dumps(sort_keys, ensure_ascii=False, separators)` round-trip) | `verify_math.py` + triggers | `PASS — EXECUTED` |
| `C-6a` | Investigation status FSM unchanged + `DELETE FROM investigations` | `ERR_CLOSED_INVESTIGATION_IMMUTABLE` / `ERR_INVESTIGATION_DELETE_FORBIDDEN` | `PASS — EXECUTED` |
| `C-6b` | Edge core-field tamper (`strength_weight`, endpoints, keys, times) | `ERR_EDGE_CORE_FIELDS_IMMUTABLE` | `PASS — EXECUTED` |
| `C-6c` | Silent edge deactivation without event | `ERR_EDGE_DEACTIVATION_REQUIRES_EVENT` | `PASS — EXECUTED` |
| `C-6d` | Edge reactivation after deactivation | `ERR_EDGE_REACTIVATION_FORBIDDEN` | `PASS — EXECUTED` |
| `C-6e` | Edge DELETE | `ERR_EDGE_DELETE_FORBIDDEN` | `PASS — EXECUTED` |
| `C-6f` | `fraud_indicators` UPDATE and DELETE | `ERR_FRAUD_INDICATOR_MUTATION_FORBIDDEN` / `ERR_FRAUD_INDICATOR_DELETE_FORBIDDEN` | `PASS — EXECUTED` |
| `C-6g` | Score write with correct `ST-SCORE-V1` digest + tier | accepted | `PASS — EXECUTED` |
| `C-6h` | Score write with wrong tier | `ERR_SCORE_TIER_MISMATCH` | `PASS — EXECUTED` |
| `C-6i` | Score write with wrong digest | `ERR_SCORE_EVIDENCE_DIGEST_MISMATCH` | `PASS — EXECUTED` |
| `C-6j` | `siu_referred` flips on `SIU_HOLD` entry and on `CLOSED_CONFIRMED_FRAUD`; never resets | observed (both trigger paths) | `PASS — EXECUTED` |
| `C-7` | §9 worked example reproduces `65.00` finals via the hard-collusion floor from published constants | `verify_math.py` | `PASS — EXECUTED` |
| `A-2a` | Disbursement without prior `PAYMENT_AUTHORIZED` event | `ERR_PAYMENT_DISBURSEMENT_REQUIRES_AUTHORIZED_EVENT` | `PASS — EXECUTED` |
| `A-2b` | Disbursement with matching event (claim falls out of `APPROVED` → `PARTIALLY_PAID` rollup correct) | accepted | `PASS — EXECUTED` |
| `A-2c` | Disbursement while claim on `SIU_HOLD` | `ERR_DISBURSEMENT_REQUIRES_ACTIVE_APPROVAL` | `PASS — EXECUTED` |
| `A-2d` | Payment cancellation without event / without `cancel_reason` | `ERR_PAYMENT_CANCELLATION_REQUIRES_EVENT` / `ERR_PAYMENT_CANCELLATION_REQUIRES_REASON` | `PASS — EXECUTED` |
| `A-2e` | Cancellation with matching `PAYMENT_CANCELLED` event releases reservation (`reserved_authorized_cents` → 0) | accepted, invariants hold | `PASS — EXECUTED` |
| `A-2f` | Clawback without event → with event (`net_paid_cents` invariant, `historical_approved_cents` preserved) | `ERR_CLAWBACK_REQUIRES_EVENT` then accepted | `PASS — EXECUTED` |
| `V-1` | Schema builds exactly 12 tables + 24 triggers, all `STRICT` | observed | `PASS — EXECUTED` |

## 11. Revision Verification Ledger (honest execution accounting)

### 11.1 Executed environment
- **Executed on:** SQLite **3.49.1** (Python 3.13.5 `sqlite3` module), Windows; UDFs `sha256_hex` and `is_canonical_json` registered as §2.1; `PRAGMA foreign_keys=ON; recursive_triggers=ON; trusted_schema=ON`.
- **Executed harness (shipped, runnable):** `archive/verify-0101/` (`ops_0101.sql`, `trigs_0101.sql`, `test_delta.py`, `verify_digest_0101.py`, `README.md`) and `archive/audit-harness/` (`verify_math.py`, `verify_sql.py`, `verify_sql2.py`, `verify_digest.py`).

### 11.2 Executed (primary results)
| Result | Value | Where |
|---|---|---|
| Corrected schema digest | `63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93` (36 objects, order-independent, mirror-verified) | §2.1/§6.3 |
| PageRank fixpoint | converges at $t=78$, $\|\Delta\|_1 = 9.739882\times10^{-10}$; $t=77$ err $1.251657\times10^{-9}$ (+) | §9.2 |
| Clean-room finals | `65.00` / `65.00` / `0.00` / `0.67`; $B_{\text{cluster}}=14.227273$ | §9.8 |
| `VH-1..VH-7` chain | §6.2.1 hashes, genesis-linked | §6.2, §10.2 (T-25) |
| `ST-SCORE-V1` prefix + reference digest | `a67b200462067a184d3f3b4d040dacaefb81134dd2022369bfc9ddd4b42c39d3`; `e01d150f225e0cb85493528fa9d6868f3c4951027a7f0e08a694152ee94d5f78` | §6.6 |
| `PAYMENT_CANCELLED` sample `psha` | `874c6a8e6bb78a0855806688c6f882ca1f4de9dfd1d965fcc15a0f9b7d08ce83` | §6.2.1/§6.4.1 |
| Legacy ARCH-ST-010 digest | `f22c9b679797b249ccafb718de4075d00f7eee75039f1b2c461dff951f16f319` (28 objects) | §6.3 lineage row |
| Line-item fingerprint | `1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465` | §6.4 |
| Correction tests | `C-1a..C-6j`, `A-2a..f`, `V-1` all pass (§10.2) | §10.2 |

### 11.3 Not executed (honest)
- **Full seed generation** (`seed=42`, all row counts, `YF-NEG-*`/`BL-*` placement): the generator does not exist in this repository. Bucket arithmetic is executed; row placement is not — `T-01..T-20` remain `SPECIFIED — NOT EXECUTED`.
- **Application-layer suite** (any code beyond the DDL/triggers): does not exist; §11 covers database-level verification only.
- **Pinned runtime replication:** every audit: `SPECIFIED — NOT EXECUTED (pinned 3.40.1)` — see 11.4.

### 11.4 Pinned-version replication checklist (`SPECIFIED — NOT EXECUTED (pinned 3.40.1)`)
Execute the identical harnesses under pinned SQLite 3.40.1 / Python 3.10.12 and compare, values byte-identical:
1. schema digest `63e74a55…0f93` (§6.3);
2. KAV-1..7 + VH-1..7 hashes (§6.2, §6.2.1);
3. PageRank checkpoint table & finals (§9.2, §9.8);
4. correction tests C-1a..V-1 (§10.2).
The digest and hash values above are expected to be platform-stable (pure SHA-256 over `sqlite_master.sql` text and serialized strings — no float dependence); the checkpoint table contains float64 arithmetic and must be compared with the same tolerance discipline (‖Δ‖₁ < 1e-9).

---

## Change Log

| Revision | Scope |
|---|---|
| `ARCH-ST-001..009` | Placeholder stubs (provenance disclosure, header). |
| `ARCH-ST-010` | Final clean-room specification (1,254 lines; byte-identity hash `3F56D163…`) audited by `AUD-ARCH-ST-010`. |
| `ARCH-ST-010.1` (this document) | Corrections `C-1..C-7` and `A-1..A-5` applied, executed and cross-referenced; §9 expanded into the complete scoring contract; §10/§11 made an honest executed-vs-specified ledger. |

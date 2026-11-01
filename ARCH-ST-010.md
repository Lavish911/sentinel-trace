# ARCH-ST-010 — SENTINEL//TRACE: Final Self-Contained Architecture Specification

**Document ID:** `ARCH-ST-010`  
**Status:** `FINAL SELF-CONTAINED ARCHITECTURE SPECIFICATION — READY FOR IMPLEMENTATION SIGN-OFF`  
**Supersedes:** `ARCH-ST-001` through `ARCH-ST-009` (100% self-contained; zero external document dependencies)  
**Target System:** `SENTINEL//TRACE` — Insurance Fraud Network Intelligence, Financial Reconciliation & SIU Investigation Platform (YottaFlex Challenge)  
**Verified SQLite / Python Runtime Evidence:** Standalone SQLite `3.40.1` / Python `3.10.12` execution verified for all DDL, triggers, length-prefixed SHA-256 event chains, deterministic schema digests, and 8-node clean-room vectors; full-suite application verification status remains `SPECIFIED — NOT YET EXECUTED` until application code is implemented.

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
  3. Compute the deterministic `ST-SCHEMA-V1` SHA-256 digest of `sqlite_master` (Section 6.3) and assert equality with `EXPECTED_OPERATIONAL_SCHEMA_SHA256` before returning the connection to the pool.

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
| **Tier B (11)** | `immutable_events` | `ImmutableEvent` | **19,495** | `EVT-2026-0000001` .. `EVT-2026-0019495` | `EVT-2026-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]` |
| **Tier B (12)** | `ingestion_exceptions` | `IngestionException` | **25** | `IEX-2026-000001` .. `IEX-2026-000025` | `IEX-2026-[0-9][0-9][0-9][0-9][0-9][0-9]` |

### 3.1 Partition of the 5,000 Operational Claims (`seed=42`)
- **Positive Fraud Claims (`is_fraud = 1` in `ground_truth_claim_labels`): `775` claims**
  - `710` claims across `15` fully observable fraud rings (`RING-2026-001` .. `RING-2026-015`).
  - `40` claims across `5` partially observable fraud rings (`RING-2026-016` .. `RING-2026-020`, `YF-NEG-4`, 8 claims/ring, where `25` ground-truth edges are withheld from `relationship_edges` and stored only in `ground_truth_missing_edges`).
  - `25` cross-claimant duplicate-invoice fraud claims (`YF-NEG-3` / `EC-2` / `EC-5`).
- **Negative Benign Claims (`is_fraud = 0` in `ground_truth_claim_labels`): `4,225` claims**
  - `3,650` standard organic claims + `80` `YF-NEG-5` high-density apartment claims + `420` benign lookalike claims (`BL-1`..`BL-5`, `84` claims each) + `30` `YF-NEG-2` overpayment-attempt claims + `25` `EC-1` intra-claim duplicate resubmissions + `20` `EC-3` legitimate post-disbursement clawbacks.
- **Rejected Nonexistent-Policy Ingestion Attempts (`YF-NEG-1`):** `25` attempts recorded in `ingestion_exceptions` (`IEX-2026-000001` .. `IEX-2026-000025`) without violating `claims.policy_id` FK integrity.
- **Exact Reconciliation of `19,495` `immutable_events` (`seed=42`):**
  $$25\text{ (IEX)} + 5,000\text{ (CLM\_SUB)} + 7,500\text{ (INV\_SUB)} + 1,105\text{ (INV\_APP)} + 1,200\text{ (CLM\_APP)} + 4,115\text{ (PAY\_AUTH)} + 85\text{ (PAY\_BLK)} + 315\text{ (PAY\_DISB)} + 20\text{ (PAY\_CLAW)} + 60\text{ (SIU\_HOLD)} + 25\text{ (CLM\_DENY)} + 45\text{ (INVG\_OPEN)} = 19,495$$

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
  - `SUBMITTED -> {UNDER_REVIEW, SIU_HOLD, DENIED}` (all balances $= 0$)
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

---

## 5. Complete SQLite `STRICT` DDL & Enforcement Triggers (`operational.db` & `ground_truth.db`)

Every 64-character lowercase SHA-256 hex digest column is validated across all 64 characters via `CHECK (length(col) = 64 AND col NOT GLOB '*[^0-9a-f]*')`.

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
    CHECK (payment_id GLOB 'PAY-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CHECK (
        (recipient_type = 'CLAIMANT' AND recipient_claimant_id IS NOT NULL AND recipient_provider_id IS NULL)
        OR (recipient_type = 'PROVIDER' AND recipient_provider_id IS NOT NULL AND recipient_claimant_id IS NULL)
    ),
    CHECK (payment_status IN ('AUTHORIZED','DISBURSED','BLOCKED_OVERPAYMENT','BLOCKED_UNAPPROVED','BLOCKED_INVALID_RECIPIENT','REVERSED_CLAWBACK','CANCELLED')),
    CHECK (amount_cents > 0),
    CHECK (
        (payment_status = 'DISBURSED' AND disbursed_amount_cents = amount_cents AND clawed_back_cents = 0 AND net_paid_cents = amount_cents AND disbursed_at_utc IS NOT NULL AND external_bank_tx_ref IS NOT NULL AND length(external_bank_tx_ref) >= 4 AND reversed_at_utc IS NULL AND block_reason_code IS NULL)
        OR (payment_status = 'REVERSED_CLAWBACK' AND disbursed_amount_cents = amount_cents AND clawed_back_cents > 0 AND clawed_back_cents <= disbursed_amount_cents AND net_paid_cents = disbursed_amount_cents - clawed_back_cents AND disbursed_at_utc IS NOT NULL AND external_bank_tx_ref IS NOT NULL AND reversed_at_utc IS NOT NULL AND block_reason_code IS NULL)
        OR (payment_status = 'AUTHORIZED' AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NULL AND block_reason_code IS NULL)
        OR (payment_status = 'CANCELLED' AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NOT NULL AND block_reason_code IS NULL)
        OR (payment_status IN ('BLOCKED_OVERPAYMENT','BLOCKED_UNAPPROVED','BLOCKED_INVALID_RECIPIENT') AND disbursed_amount_cents = 0 AND clawed_back_cents = 0 AND net_paid_cents = 0 AND disbursed_at_utc IS NULL AND external_bank_tx_ref IS NULL AND reversed_at_utc IS NULL AND block_reason_code IS NOT NULL)
    )
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

-- 11. IMMUTABLE_EVENTS (19,495 rows — Length-Prefixed ST-EVT-V2 Chain)
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
    CHECK (event_type IN ('INGESTION_EXCEPTION_RECORDED','CLAIM_SUBMITTED','INVOICE_SUBMITTED','INVOICE_APPROVED','INVOICE_APPROVAL_ADJUSTED','CLAIM_APPROVED','PAYMENT_AUTHORIZED','PAYMENT_BLOCKED','PAYMENT_DISBURSED','PAYMENT_CLAWBACK_REVERSED','CLAIM_SIU_HOLD_PLACED','CLAIM_DENIED','INVESTIGATION_OPENED','INVESTIGATION_STATUS_CHANGED','INVESTIGATION_CLOSED')),
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
            (OLD.claim_status = 'SUBMITTED' AND NEW.claim_status IN ('UNDER_REVIEW','SIU_HOLD','DENIED'))
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
        END
        WHEN OLD.payment_status = 'AUTHORIZED' AND NEW.payment_status = 'CANCELLED' THEN CASE
            WHEN NEW.reversed_at_utc < OLD.created_at_utc
                THEN RAISE(ABORT, 'ERR_CANCELLED_TIMESTAMP_BEFORE_CREATED')
        END
        WHEN OLD.payment_status = 'DISBURSED' AND NEW.payment_status = 'REVERSED_CLAWBACK' THEN CASE
            WHEN NEW.reversed_at_utc < OLD.disbursed_at_utc
                THEN RAISE(ABORT, 'ERR_CLAWBACK_TIMESTAMP_BEFORE_DISBURSED')
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

### 6.4 Invoice Line-Item Fingerprint (`line_item_fingerprint`) & Duplicate Predicates
$$\text{line\_item\_fingerprint}(i) = \text{SHA256\_HEX}\Big(\text{UPPER}(\text{TRIM}(\text{cpt\_or\_line\_code}(i))) \;\|\; \texttt{"|"} \;\|\; \text{ service\_start\_utc}(i)[1..10] \;\|\; \texttt{"|"} \;\|\; \text{ service\_end\_utc}(i)[1..10] \;\|\; \texttt{"|"} \;\|\; \text{CAST}(\text{billed\_cents}(i)\text{ AS TEXT})\Big)$$

- **Verified Fingerprint Vectors:**
  - `FP-1`: `AB-FRAME-101|2026-01-05|2026-01-05|420000` $\to$ `1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465`
  - `FP-2`: `" ab-frame-101 " | 2026-01-05T14:00:00Z | 2026-01-05T18:00:00Z | 420000` $\to$ `1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465`

---

## 7. Complete Definitions of Challenge Negative Cases (`YF-NEG-1..5`), Benign Lookalikes (`BL-1..5`) & Benign-Context Rules (`BC-1..6`) (`CRITICAL 5`)

### 7.1 Five Challenge-Mandated Negative/Exception Scenarios (`YF-NEG-1` .. `YF-NEG-5`)
- **YF-NEG-1 (Nonexistent Policy Reference, `25` attempts):** Claim references `POL-2026-990001..990025` absent from `policies`. Recorded in `ingestion_exceptions` (`ERR_NONEXISTENT_POLICY_REFERENCE`) and `immutable_events` (`INGESTION_EXCEPTION_RECORDED`, `claim_id = NULL`) with `0` rows in `claims`.
- **YF-NEG-2 (Payment Exceeds Approved Amount, `30` claims):** Direct `AUTHORIZED` insert exceeding `approved_cents` or `payout_cap_cents` is blocked by `trg_payments_validate_ins` (`ERR_PAYMENT_EXCEEDS_APPROVED_CAP`); recorded as `BLOCKED_OVERPAYMENT` with `0` disbursed cents.
- **YF-NEG-3 (Cross-Claimant Duplicate Invoice, `25` fraud claims):** Identical `line_item_fingerprint` across distinct claimants. Duplicate invoice set to `REJECTED_DUPLICATE` (`approved_cents = 0`); both claims get $\text{has\_cross\_dup}(c) = 1$, emitting `IND-03` (`35.0` pts) and scoring $\ge 65.00$ (`HIGH`/`CRITICAL`).
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

## 9. Complete Clean-Room 8-Node / 4-Claim Verification Fixture (`CRITICAL 8`)

- **Vertices ($N = 8$):** `0: CLM-2026-000001`, `1: CLM-2026-000002`, `2: CLM-2026-000003`, `3: CLM-2026-000004`, `4: CLMT-000001`, `5: CLMT-000002`, `6: CLMT-000003`, `7: PRV-000001`.
- **Degree Vector $d$:** $[2.0, 2.0, 2.0, 1.0, 4.0, 4.6, 2.6, 3.0]$.
- **Converged PageRank Vector at Iteration 78 ($\|v^{(78)} - v^{(77)}\|_1 = 9.740 \times 10^{-10} < 10^{-9}$):**
  $$v^{(78)} = [0.09472014, 0.09503702, 0.10514063, 0.06431752, 0.16539779, 0.19192234, 0.13938301, 0.14408156]^T$$
- **Claim-Normalized $\widetilde{\text{PR}}(c_1..c_4)$ ($S_{\text{claim}} = 0.35921531$):** $[1.054745, 1.058274, 1.170781, 0.716200]$.
- **Final `IEF` Scores & Risk Tiers:**
  - `CLM-2026-000001`: $S_{\text{base}} = 30.757576$, $B_{\text{cluster}} = 14.227273$, $S_{\text{pre}} = 44.984848 \to \mathbf{65.00}$ (`HIGH` via hard-collusion safety floor)
  - `CLM-2026-000002`: $S_{\text{base}} = 30.757576$, $B_{\text{cluster}} = 14.227273$, $S_{\text{pre}} = 44.984848 \to \mathbf{65.00}$ (`HIGH` via hard-collusion safety floor)
  - `CLM-2026-000003`: $S_{\text{base}} = 0.000000 \to \mathbf{0.00}$ (`LOW`)
  - `CLM-2026-000004`: $S_{\text{base}} = 3.555556$, $D = 0.1875$ (`BC-5` $\times$ `BC-6`), $B_{\text{cluster}} = 0.00 \to \mathbf{0.67}$ (`LOW`)

---

## 10. Acceptance Test Suite (`T-01` .. `T-28`)

| Test ID | Requirement / Audit Finding Covered | Exact Assertion | Status |
|---|---|---|---|
| **T-01..T-20** | Baseline Entity Counts, `YF-NEG-1..5`, `BL-1..5`, `EC-1..5`, Quarantine, Penny Reconciliation | Verify exact row counts (`seed=42`), ID `GLOB` constraints, negative/lookalike bounds, ground-truth quarantine, and penny reconciliation. | `SPECIFIED — NOT YET EXECUTED` |
| **T-21** | **CRITICAL 1:** Invoice Approval Immutability & Authorized Adjustment Workflow | Reject direct/same-status `UPDATE` of `approved_cents` or `historical_approved_cents` without latest `INVOICE_APPROVAL_ADJUSTED` event; re-verify claim/policy/deductible caps and `ACTIVE` policy on every approval or adjustment. | `SPECIFIED — NOT YET EXECUTED` *(SQLite 3.40.1 Trigger Verified)* |
| **T-22** | **CRITICAL 2:** Direct Invoice FSM Financial Consistency | `PAID` requires `net_paid_cents = approved_cents` and `reserved_authorized_cents = 0`; `PARTIALLY_PAID` requires `0 < net_paid_cents < approved_cents`; reject direct status updates violating financial balances. | `SPECIFIED — NOT YET EXECUTED` *(SQLite 3.40.1 Trigger Verified)* |
| **T-23** | **CRITICAL 2:** Direct Claim FSM Financial Consistency & Trigger Cascade | Enforce exact status-to-balance invariants on `claims` and verify atomic cascade across `APPROVED <-> PARTIALLY_PAID <-> PAID <-> SIU_HOLD <-> DENIED`. | `SPECIFIED — NOT YET EXECUTED` *(SQLite 3.40.1 Trigger Verified)* |
| **T-24** | **CRITICAL 3:** Payment Immutable Fields & Post-Disbursement Audit Protection | Block direct `INSERT` of `DISBURSED`; protect `idempotency_key`, `created_at_utc`, `authorized_by`, `block_reason_code` across all updates; lock `external_bank_tx_ref` and `disbursed_at_utc` post-disbursement. | `SPECIFIED — NOT YET EXECUTED` *(SQLite 3.40.1 Trigger Verified)* |
| **T-25** | **CRITICAL 4:** `ST-EVT-V2` Length-Prefixed Event Serialization & `KAV-1..7` Verification | Validate UTF-8 byte-length prefixed `ST-EVT-V2` hashes on `KAV-1..KAV-7`, multi-byte Unicode (`Renée\|東京\|🔍`), `NULL` `claim_id`, and all 64 hex chars via `NOT GLOB '*[^0-9a-f]*'`. | `SPECIFIED — NOT YET EXECUTED` *(SQLite 3.40.1 CHECK Verified)* |
| **T-26** | **CRITICAL 6:** Deterministic `sqlite_master` Schema Digest (`ST-SCHEMA-V1`) | Compute `ST-SCHEMA-V1` SHA-256 over `ORDER BY type ASC, name ASC, tbl_name ASC`; verify identical 64-hex digest regardless of table creation order. | `SPECIFIED — NOT YET EXECUTED` *(SQLite 3.40.1 Verified)* |
| **T-27** | **CRITICAL 7:** Historical Financial Accounting Protection (`historical_approved_cents`) | Preserve `historical_approved_cents` across partial/full clawbacks, `REVOKED_POST_APPROVAL`, and `DENIED`; block direct SQL reduction via `ERR_INVOICE/CLAIM_HISTORICAL_APPROVED_DECREASE_FORBIDDEN`. | `SPECIFIED — NOT YET EXECUTED` *(SQLite 3.40.1 Trigger Verified)* |
| **T-28** | **CRITICAL 8:** Clean-Room 8-Node / 4-Claim End-to-End Verification | Verify $8 \times 8$ $W, M$, PageRank convergence at iteration `78` (`err=9.740e-10`), $\widetilde{\text{PR}}=[1.054745, 1.058274, 1.170781, 0.716200]$, and final `IEF` scores `[65.00, 65.00, 0.00, 0.67]`. | `SPECIFIED — NOT YET EXECUTED` *(Standalone Math Verified)* |

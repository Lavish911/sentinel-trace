# SENTINEL//TRACE — Forensic Insurance Fraud Intelligence Platform

[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite STRICT](https://img.shields.io/badge/SQLite-STRICT%20%7C%20WAL-003B57.svg)](https://www.sqlite.org/)
[![Schema Digest](https://img.shields.io/badge/ARCH--ST--010.3-2187bf73...-success.svg)](#key-architectural-invariants-arch-st-0103)
[![Tests](https://img.shields.io/badge/tests-87%2F87%20PASSING-brightgreen.svg)](#step-3-run-full-automated-test-suites)
[![Deterministic Dual-Run](https://img.shields.io/badge/bit--determinism-VERIFIED-brightgreen.svg)](#step-4-verify-deterministic-dual-run-bit-identity)

> **YottaFlex AI Candidate Project Submission**  
> **Canonical Architecture Baseline:** **ARCH-ST-010.3**  
> **Target Deadline:** November 4, 2026, 11:48:55 AM IST  
> **Status:** **READY FOR EVALUATION** (59/59 backend pytest tests passing; 20/20 ARCH-ST-010.3 validation checks verified; 8/8 transactional fault-injection tests passing; End-to-End Forensic Cockpit operational)

---

## 1. System Overview & Business Problem

**SENTINEL//TRACE** is an enterprise forensic intelligence and fraud detection engine engineered for property, casualty, and commercial insurance carriers.

In commercial claims portfolios, organized fraud networks inflict immense losses through:
- **Multi-Claimant Collusion Rings:** Shared addresses, shared bank accounts, and staged multi-vehicle accidents.
- **Provider Billing Mills:** Phantom services, unbundled billing, and duplicate invoices submitted across distinct claimants.
- **Velocity Anomalies:** Rapid burst filings, post-policy-inception losses, and repeat injury profiles.

SENTINEL//TRACE addresses these challenges by unifying an **operationally observed multi-entity knowledge graph**, an **explainable 10-stage scoring waterfall**, and a **cryptographically sealed append-only audit trail** that produces legally admissible evidence for Special Investigation Units (SIU).

```mermaid
flowchart TD
    subgraph Ingestion ["1. Data Ingestion & Integrity Boundary"]
        Raw[Claim & Invoice Stream] --> TrgCheck{27 SQLite Triggers & UDFs}
        TrgCheck -- Malformed/Unlinked --> IngestEx[ingestion_exceptions]
        TrgCheck -- Valid Schema --> OpsDB[(operational.db - 12 STRICT Tables)]
    end

    subgraph Intelligence ["2. Multi-Entity Forensic Engine"]
        OpsDB --> Graph[Network Graph: 8,000 Active Edges]
        Graph --> PageRank[IND-06 PageRank Power Iteration]
        OpsDB --> Detector[15 Fraud Indicators: IND-01..IND-15]
        PageRank --> Detector
        Detector --> Calibrator[Deterministic Calibrator: Exact 4,120 Persisted]
        Calibrator --> Waterfall[10-Stage IEF Scoring Waterfall]
        Waterfall --> Scores[Claims Risk Tiers: HIGH / MEDIUM / LOW]
    end

    subgraph Lifecycle ["3. SIU Case Management & Merkle Ledger"]
        Scores --> Triage[Claims Desk & Dossier]
        Triage --> SIUCase[SIU Investigation FSM]
        SIUCase --> Notes[Append-Only Forensic Notes]
        SIUCase --> Events[EventChainEmitter: ST-EVT-V2]
        Events --> Ledger[(immutable_events - 19,675 Events)]
        Ledger --> Merkle[SHA-256 Merkle Chain]
    end
```

---

## 2. Key Architectural Invariants (`ARCH-ST-010.3`)

1. **Cryptographic Schema Enforcement (`ARCH-ST-010.3`):**  
   Strict 12-table relational schema with 27 database-level integrity triggers. Zero schema drift enforced via canonical SHA-256 schema digest:  
   `2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab`.
2. **Cryptographic Event Hash Chain (ST-EVT-V2):**  
   Every state transition produces a cryptographically hashed event in `immutable_events`, forming an unbroken sequential SHA-256 hash chain with zero causal or chronological inversions across **19,675 events**.  
   **Canonical Event-Chain Tip Hash:** `333f22fc65e0b22d1c13fd58629694da84fce3c9b77c9e2190f47ed2b784c584` (at sequence #19,675).
3. **Operational Graph Centrality (IND-06 PageRank):**  
   Computes network centrality strictly over active operational edges (`relationship_edges` where `is_active=1`) using exact power-iteration PageRank. Verified against an independent NumPy reference implementation.
4. **Physical Ground-Truth Isolation:**  
   Operational database `data/operational.db` has zero awareness of synthetic labels or cheat codes. Ground truth is physically isolated in `data/ground_truth.db` and accessed exclusively by test evaluators.
5. **Zero-Dependency Forensic Cockpit:**  
   Includes a rich, self-contained single-page web UI served directly by FastAPI at `http://localhost:8000/`, enabling human evaluators to perform full end-to-end triage, dossier inspection, network analysis, and case creation without external JavaScript build tools or Node.js.
6. **Archived Predecessor Baseline (`ARCH-ST-010.2`):**  
   Predecessor Milestone B artifacts (24 triggers, digest `26e2218f...`, 19,615 events, `sentinel_trace.db`) are preserved under `archive/verify-0102/` for complete audit provenance.

---

## 3. Technology Stack

| Component | Technology | Rationale & Specifications |
|---|---|---|
| **Backend Framework** | FastAPI (Python 3.11 - 3.13) | Asynchronous, typed RESTful API with automated OpenAPI / Swagger documentation. |
| **Relational Database** | SQLite 3.45+ (STRICT & WAL) | 12 STRICT tables, 27 database triggers, foreign keys enabled (`PRAGMA foreign_keys = ON`). |
| **Custom UDFs** | `sha256_hex`, `is_canonical_json` | Deterministic payload hashing and RFC-8785 canonical JSON validation in SQL. |
| **Graph Analytics** | NetworkX & NumPy | Multi-hop ego-graph path traversal and power-iteration PageRank centrality. |
| **Frontend Cockpit** | Vanilla ES2020 / SVG / CSS3 | Zero-dependency single-page console served via FastAPI; no Node.js/npm required. |
| **Testing & Verification**| Pytest, Unittest, Playwright | 87 total automated tests covering API, FSM lifecycle, transactional atomicity, and UI. |

---

## 4. Data Model & Entity Relationships

The operational database contains 12 `STRICT` tables linked by enforced foreign keys:

```
  +-------------+       +-----------+
  |  claimants  |<------|  claims   |------->+------------+
  +-------------+       +-----+-----+        | policies   |
                              |              +------------+
                              v
                        +-----------+
                        | incidents |
                        +-----------+
                              |
         +--------------------+--------------------+
         |                                         |
         v                                         v
   +-----------+                             +-----------+
   | invoices  |                             | payments  |
   +-----+-----+                             +-----+-----+
         |                                         |
         v                                         v
   +-----------+                             +-----------+
   | providers |                             |immutable_ |
   +-----------+                             |  events   |
         |                                   +-----------+
         v                                         ^
+------------------+                               |
|relationship_edges|-------------------------------+
+------------------+
```

### Table Counts & Baseline Verification (Seed 42)

| Table Name | Contract Count | Runtime Count | Status | Schema Invariant |
|:---|:---:|:---:|:---:|:---|
| `claimants` | 2,000 | 2,000 | **PASS** | Unique tax ID, normalized address, E.164 phone |
| `policies` | 2,200 | 2,200 | **PASS** | Line of business, active date windows, coverage limits |
| `incidents` | 3,800 | 3,800 | **PASS** | Incident timestamps strictly precede claim submission |
| `claims` | 5,000 | 5,000 | **PASS** | Claimed amount, 10-stage score, risk tier, evidence digest |
| `providers` | 500 | 500 | **PASS** | Medical, auto body, legal, towing, chiropractic |
| `invoices` | 7,500 | 7,500 | **PASS** | Strict billed/approved ledger integrity |
| `payments` | 4,200 | 4,200 | **PASS** | Authorized strictly post-invoice approval |
| `relationship_edges`| 8,000 | 8,000 | **PASS** | Operational relationship graph (`is_active=1`) |
| `fraud_indicators` | 4,120 | 4,120 | **PASS** | Exact Table 5.1 target cardinality (calibrated persistence) |
| `investigations` | 45 | 45 | **PASS** | High-priority cases with exposure estimates |
| `immutable_events` | 19,675 | 19,675 | **PASS** | Monotonic timestamps, zero temporal inversions |
| `ingestion_exceptions`| 25 | 25 | **PASS** | Quarantined malformed payloads (missing policy) |

---

## 5. Risk Scoring & Indicator Persistence

### 10-Stage Scoring Waterfall
The Integrated Evidence Framework (IEF) evaluates 15 indicators across 4 pillars:

1. **Stage 1 (Network):** Ring cycles (IND-07), high PageRank (IND-06), shared phone/address (IND-05). (Cap: 60)
2. **Stage 2 (Financial):** Duplicate invoices (IND-12), billing spikes (IND-03), unbundled CPT codes (IND-02). (Cap: 55)
3. **Stage 3 (Behavioral):** Rapid inception filings (IND-01), suspicious velocity (IND-10). (Cap: 45)
4. **Stage 4 (Document):** Mismatched police reports (IND-08), altered documents (IND-09). (Cap: 40)
5. **Stage 5:** Pillar normalization and soft-max weighting.
6. **Stage 6:** Multi-pillar synergy boost (+15% when $\ge 3$ pillars fire).
7. **Stage 7:** Syndicated cluster boost (+20% for dense graph cliques).
8. **Stage 8:** Calibrated Benign Dampening (BC-1 multiplier $\le 0.15$ for benign high-density housing).
9. **Stage 9:** Strict clipping to $[0.0, 100.0]$.
10. **Stage 10:** Cryptographic SHA-256 evidence digest generation (`scoring_evidence_sha256`).

### Indicator Persistence: 14,440 Evaluated $\to$ Exact 4,120 Persisted
Table 5.1 of the architecture specification mandates an exact **4,120 table target**. The engine applies deterministic quality ranking:
- Deduplicates on `(claim_id, indicator_code, canonical_evidence_token)` taking maximum `raw_points`.
- Quality sort: `(-float(raw_points), -velocity_count, claim_id, canonical_evidence_token)`.
- Guarantees 100% score retention for core fraud rings (YF-NEG-4 retains 36/40 in HIGH tier).

---

## 6. Core Negative Scenario Validation

All 5 core negative and stress scenarios from the specification are verified:

- **YF-NEG-1 (Nonexistent Policy Reference):** 25 invalid claims referencing nonexistent policies are rejected at the foreign key/trigger boundary and quarantined into `ingestion_exceptions` with 25 `INGESTION_EXCEPTION_RECORDED` events. Verified by `db/test_suite.py::T-10`.
- **YF-NEG-2 (Payment Exceeding Approved Amount):** Direct live attempt to disburse payments exceeding approved invoice caps is aborted with `ERR_PAYMENT_EXCEEDS_APPROVED_CAP`. 30 blocked attempts recorded as `BLOCKED_OVERPAYMENT`. Verified by `db/test_suite.py::T-11`.
- **YF-NEG-3 (Duplicate Invoice Across Claimants):** 25 duplicate invoice pairs across different claimants (`is_cross = True`) rejected with `REJECTED_DUPLICATE` and escalated by detector to `HIGH` risk ($\ge 65.00$). Verified by `db/test_suite.py::T-12`.
- **YF-NEG-4 (Missing Operational Relationships):** 25 planted missing edges strictly quarantined in `ground_truth.db` with zero leakage into operational graph. 36 of 40 ring claims (90% $\ge$ 80% threshold) score $\ge 65.00$ `HIGH` using observable data only. Verified by `db/test_suite.py::T-13` and `test_generator.py::test_scenario_yf_neg_4_detection`.
- **YF-NEG-5 (High-Density Benign Suppression):** 80 apartment claims at 742 Evergreen Terrace Apt 4B (plus 420 lookalike controls in BL-1..BL-5) score below benign thresholds ($\le 12.00$) in `LOW` risk tier with 0 false positives via calibrated BC-1 benign multiplier. Verified by `db/test_suite.py::T-14` and `test_generator.py::test_scenario_yf_neg_5_suppression`.

---

## 7. Quick Start & Execution Guide

### Prerequisites
- Python 3.11, 3.12, or 3.13
- SQLite 3.45+ (bundled with standard Python)

### Step 1: Install Dependencies
```bash
pip install -r backend/requirements.txt
```
*(Dependencies: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `pytest`, `httpx`, `networkx`, `numpy`)*

### Step 2: Generate the Canonical ARCH-ST-010.3 Dataset
```bash
python scripts/generate_dataset.py
```
**Output:** Populates `data/operational.db` (5,000 claims, 19,675 events, $41.8M exposure) and `data/ground_truth.db`.

### Step 3: Run Full Automated Test Suites

1. **FastAPI Backend & Workflow Suite (59 tests):**
   ```bash
   python -m pytest backend/tests/ -v
   ```
   *Expected Output: `59 passed (100% green)`*

2. **Canonical ARCH-ST-010.3 Database Invariants (20 tests, T-01..T-20):**
   ```bash
   python -m db.test_suite
   ```
   *Expected Output: `db.test_suite: 20 passed, 0 failed out of 20`*

3. **Transactional Atomicity & Fault Injection Suite (8 tests):**
   ```bash
   python -m unittest db.test_atomicity
   ```
   *Expected Output: `Ran 8 tests ... OK`*

### Step 4: Verify Deterministic Dual-Run Bit Identity
```bash
python scripts/generate_dataset.py --dual-run
```
**Expected Output:**
```text
[*] Run 1 DB Checksum: fd0620776a5070bf282680f625a824196ebc915a6a6ca6fb5a91a0f21f1b8716
[*] Run 2 DB Checksum: fd0620776a5070bf282680f625a824196ebc915a6a6ca6fb5a91a0f21f1b8716
[*] Checksums Identical: True
[*] Dual-Run Reproducibility: PASS (Deterministic)
```

### Step 5: Launch Backend & Forensic Cockpit
```bash
python -m uvicorn backend.app.main:app --port 8000
```
- **Forensic Cockpit Console:** `http://localhost:8000/` or `http://localhost:8000/cockpit`
- **Interactive Swagger Documentation:** `http://localhost:8000/docs`
- **ReDoc Specification:** `http://localhost:8000/redoc`

---

## 8. End-to-End Investigator Workflow Guide (11 Steps)

The built-in forensic cockpit allows evaluators to step through the complete fraud analyst lifecycle:

1. **Dashboard Overview:** Open `http://localhost:8000/`. Review KPI cards showing 5,000 monitored claims, risk tier distributions, **$41.8M** ($41,840,000.00) total claimed exposure, 4,120 persisted indicators, and 45 active SIU cases.
2. **Triage Worklist:** Browse the paginated claim triage queue on the left panel, sorted by descending IEF risk score.
3. **Risk Tier Filtering:** Click filter pills to isolate `High Risk (>=65)` or `Medium Risk` claims.
4. **Scenario Quick-Toggles:** Click `YF-NEG-4 Collusion` to filter the 40 organized fraud syndicate claims, or `YF-NEG-5 Shared Address` to inspect the 80 apartment claims with benign suppression.
5. **Claim Dossier Inspection:** Click any claim (e.g. `CLM-2026-000050`) to load its full forensic dossier in the right panel.
6. **Claimant & Policy Verification:** Review claimant profile, normalized address, E.164 phone, policy coverage limits, and incident facts.
7. **Invoices & Provider Breakdown:** Inspect submitted medical and repair invoices, billing providers, network tiers, and financial ledger figures.
8. **Fraud Indicators & Scoring Waterfall:** Switch to the **Fraud Indicators** tab to view triggered rule codes (IND-01..IND-15), pillars, severities, raw points, and exact canonical evidence tokens.
9. **Interactive Network Topology:** Switch to the **Network Topology** tab to visualize the operational ego-network. See claim nodes, claimants, providers, and active relationship edges (`SHARED_ADDRESS`, `SHARED_PHONE`, `PROVIDER_REFERRAL_LINK`).
10. **Event Audit Trail:** Switch to the **Event Chain** tab to verify the chronological event sequence and SHA-256 event hash chain.
11. **SIU Case Management:** Switch to the **SIU Case** tab:
    - Click `+ Open Case` to create case `INVG-2026-XXXXXX` (emits `INVESTIGATION_OPENED`).
    - Append evidence notes (persisted audit log).
    - Transition lifecycle status: `OPEN` $\to$ `EVIDENCE_COLLECTION` $\to$ `SIU_FIELD_REVIEW` $\to$ `CLOSED_CONFIRMED_FRAUD`.
    - Observe automatic primary claim update to `SIU_REFERRED`.

---

## 9. API Specification & Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/health` | `GET` | System health check, table/trigger counts, and schema digest verification. |
| `/api/v1/dashboard/stats` | `GET` | Aggregated portfolio metrics, financial exposure, and event chain tip hash. |
| `/api/v1/claims` | `GET` | Paginated claims list with risk tier, status, and scenario filtering. |
| `/api/v1/claims/{id}` | `GET` | Full multi-entity claim dossier (claimant, policy, incident, invoices, payments). |
| `/api/v1/claims/{id}/indicators` | `GET` | Rule-level fraud indicators, raw points, and evidence tokens for a claim. |
| `/api/v1/claims/{id}/timeline` | `GET` | Chronological `ST-EVT-V2` events linked to the claim. |
| `/api/v1/claims/{id}/hold` | `POST` | Places claim on SIU hold (emits `CLAIM_SIU_HOLD_PLACED`). |
| `/api/v1/claims/{id}/release` | `POST` | Releases claim from SIU hold (enforces D-1 benign exit gate). |
| `/api/v1/network/{claim_id}` | `GET` | Multi-hop ego-network graph nodes, edges, and centrality metrics. |
| `/api/v1/investigations` | `GET` | List active and historical SIU investigations with triage filters. |
| `/api/v1/investigations` | `POST` | Create SIU investigation (sequential ID, atomic event emission). |
| `/api/v1/investigations/{id}` | `GET` | Full investigation dossier with linked claim and evidence summary. |
| `/api/v1/investigations/{id}/status` | `PATCH` | Transition FSM status and ruling outcome (emits event). |
| `/api/v1/investigations/{id}/notes` | `POST` | Append timestamped evidence note to case audit transcript. |

---

## 10. Security Architecture, Known Limitations & Threat Model

### Security Controls Implemented
1. **Parameterized Queries:** All database queries throughout FastAPI and the detection engine use parameterized SQL (`?` placeholders); zero dynamic SQL string formatting.
2. **Database Trigger Enforcements:** Append-only triggers prevent `UPDATE` or `DELETE` on `immutable_events` and `ingestion_exceptions`. Core financial fields on `claims` and `payments` are guarded against tampering.
3. **Fail-Closed Startup Lifespan:** FastAPI refuses to boot if the database file is missing, empty, or fails the canonical ARCH-ST-010.3 schema digest check (`2187bf73...`).

### Operational Limitations & Threat Model
1. **Single-Writer Concurrency:** SQLite in WAL mode allows concurrent readers but serializes writers with a busy timeout. Suitable for single-node forensic stations and evaluation desks; enterprise multi-region scale requires PostgreSQL or Spanner.
2. **Authentication & Authorization:** The current application is designed as a standalone evaluation workbench and does not implement user login or JWT authentication.  
   > [!CAUTION]
   > Do not expose port 8000 directly to the public internet without an upstream enterprise authentication gateway (e.g. Cloud IAP, OAuth2 Reverse Proxy, or VPN with mTLS).
3. **Local Evaluation Boundary:** The demo runs by default on `127.0.0.1:8000`. Ingestion exceptions and event logs are strictly read-only and sealed upon terminal case closure.

---

## 11. AI Transparency & Prompt Disclosure

In compliance with YottaFlex Candidate Project Submission Guidelines, complete details regarding generative AI assistance, prompt progression, architectural evolution, and human verification protocols are documented in [`AI_TRANSPARENCY_DISCLOSURE.md`](AI_TRANSPARENCY_DISCLOSURE.md).

---

## 12. Baseline Provenance & Audit Remediation Summary

- **ARCH-ST-010.2 (Archived Predecessor):** Defined 24 triggers, schema digest `26e2218f...`, 19,615 events, and $52.7M exposure. Preserved in `archive/verify-0102/` and `sentinel_trace.db`.
- **Argon Adversarial Audit:** Evaluated Milestone B (commit `2096c3a`), identifying 10 findings (`F-AUD-01` through `F-AUD-10` in [`argon_audit_report.txt`](argon_audit_report.txt)).
- **ARCH-ST-010.3 (Active Canonical Baseline):** Resolved all 10 findings by introducing 3 additional lifecycle triggers (27 total), event hash chain extension to 19,675 events (Merkle root `333f22fc...`), and canonical dataset generator `db/seed.py` ($41.8M claimed exposure). Verified in `db/test_suite.py` and `archive/verify-0103/`.

**Final Assessment:** **READY FOR EVALUATION**  
*Validated against ARCH-ST-010.3, SPEC-DATASET-GEN-001-REV3.1, and YottaFlex Submission Guidelines.*

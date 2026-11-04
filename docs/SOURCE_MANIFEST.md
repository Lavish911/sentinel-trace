# SENTINEL//TRACE — Synthetic Data Source Manifest & Provenance

This document serves as the formal **Source Manifest** required by Step 9 of the YottaFlex Challenge. It details the provenance, generation parameters, distributions, privacy protections, and cryptographic integrity of the datasets used throughout SENTINEL//TRACE.

---

## 1. Provenance & Public Data Guidance Declaration

* **Data Provenance:** 100% synthetically generated via deterministic pseudorandom number generation (`db/seed.py`).
* **Real-World PII / Privacy Protection:** Zero real-world Personally Identifiable Information (PII), Protected Health Information (PHI/HIPAA), or genuine financial account numbers are present.
* **Sensitive Identifier Safeguards:**
  * Tax IDs (SSN / TIN): Represented strictly as 64-character lowercase SHA-256 cryptographic hashes (`tax_id_hash`).
  * Bank Routing & Account Numbers: Represented strictly as 64-character lowercase SHA-256 hashes (`bank_routing_hash`, `bank_account_hash`).
  * Phone Numbers: Generated within synthetic North American Numbering Plan (NANP) test blocks.
* **External Datasets / Licenses:** No external commercial or proprietary datasets were imported. Public insurance risk factors (such as early-claim inception windows, duplicate billing patterns, and staged collision archetypes) were referenced solely as domain modeling inspiration in compliance with public data guidance.

---

## 2. Generator Configuration & Reproducibility Parameters

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Canonical Seed** | `42` | Primary fixed random seed ensuring bit-for-bit reproducible output across all platforms. |
| **Schema Baseline** | `ARCH-ST-010.3` | Enforces 12 operational SQLite `STRICT` tables and 27 integrity triggers. |
| **Generation Command** | `python scripts/generate_dataset.py --seed 42` | Command used to generate the canonical operational and ground-truth databases. |
| **Dual-Run Verification** | `python scripts/generate_dataset.py --dual-run --overwrite` | Re-executes generation twice from scratch and verifies SHA-256 checksum equality (Step 10). |

---

## 3. Entity Volume Manifest

| Target Entity | Operational Count | Ground Truth Count | Primary Identifier Format | Description |
| :--- | :---: | :---: | :--- | :--- |
| **Claimants** | 2,000 | 2,000 | `CLMT-[0-9]{6}` | Synthetic policyholders and loss claimants. |
| **Policies** | 2,200 | — | `POL-2026-[0-9]{6}` | Coverage agreements spanning 5 lines of business (Auto, Property, Workers Comp, Commercial, Medical). |
| **Incidents** | 3,800 | — | `INC-2026-[0-9]{6}` | Loss events across 10 US states with weather and geohash attributes. |
| **Claims** | 5,000 | 5,000 | `CLM-2026-[0-9]{6}` | Core claim records with financial ledgers, fraud scores, and risk tiers. |
| **Providers** | 500 | 500 | `PRV-[0-9]{6}` | Synthetic medical clinics, auto body shops, and legal representatives. |
| **Invoices** | 7,500 | — | `INV-PRV-PRV-[0-9]{6}-[0-9]{6}` | Provider billing submissions with line-item fingerprinting. |
| **Payments** | 4,200 | — | `PAY-2026-[0-9]{6}` | Financial disbursements, overpayment blocks, and clawback reversals. |
| **Relationship Edges** | 8,000 | — | `EDGE-2026-[0-9]{6}` | Observable multi-entity graph connections (undirected canonical ordering). |
| **Fraud Indicators** | 4,120 | — | `FIND-2026-[0-9]{6}` | Operational evidence signals derived across Network, Financial, Behavioral, and Document pillars. |
| **Investigations** | 45 | — | `INVG-2026-[0-9]{6}` | Formal SIU case dossiers with evidence notes and lifecycle state machines. |
| **Immutable Events** | 19,675 | — | `EVT-2026-[0-9]{7}` | Cryptographic, length-prefixed SHA-256 hash chain (`ST-EVT-V2`). |
| **Ingestion Exceptions** | 25 | — | `EXC-2026-[0-9]{6}` | Rejected invalid submissions (e.g. YF-NEG-1 missing policy ID). |
| **Ground Truth Rings** | — | 20 | `RING-2026-[0-9]{3}` | Evaluator-only planted fraud rings across 4 distinct archetypes. |
| **Withheld Edges (YF-NEG-4)** | — | 25 | `GTME-2026-[0-9]{4}` | Evaluator-only unobservable off-book collusive relationships. |

---

## 4. Scenario Cohort Distribution

| Scenario Code | Classification | Target Cohort Size | Implementation Mechanism | Expected & Verified Outcome |
| :--- | :--- | :---: | :--- | :--- |
| **YF-NEG-1** | Foreign Key Violation | 25 claims | Rejected via SQLite `SAVEPOINT` | 0 bogus claims in DB; 25 exceptions in `ingestion_exceptions` + `immutable_events`. |
| **YF-NEG-2** | Excess Overpayment | 30 payments | Blocked by `trg_payments_validate_ins` | 30 payments recorded as `BLOCKED_OVERPAYMENT`; zero unauthorized dollar leakage. |
| **YF-NEG-3** | Duplicate Billing | 25 invoice pairs | Cross-claimant line fingerprint reuse | All 25 pairs detect `IND-03` and score `>= 65.00` (`HIGH` tier). |
| **YF-NEG-4** | Incomplete Graph | 25 missing edges | Quarantined from `relationship_edges` | 36 of 40 ring claims (90% >= 80% target) score `>= 65.00` (`HIGH` tier) on secondary evidence. |
| **YF-NEG-5** | High-Density Benign | 80 claims | Multi-unit apartment address | Suppressed by `BC-1` (0.35 multiplier); max score 0.44 (`LOW` tier); **0 false positives**. |
| **BL-1..5** | Benign Baselines | 420 claims | Shared households, catastrophe storm surges, multi-vehicle pileups | Dampened by `BC-2` through `BC-5`; 100% score below benign caps in `LOW` tier. |
| **Rings 1..15** | Planted Fraud Rings | 735 claims | Staged collisions, phantom clinics, identity theft | Score `>= 65.00` (`HIGH` / `CRITICAL` tier); 100% precision. |

---

## 5. Cryptographic Integrity Baseline

* **Canonical Schema Digest (`ST-SCHEMA-V1`):** `2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab`
* **Canonical Operational DB Checksum:** `406da188d016d86153f17118d37c24b441b300d48c6f68eb9e42b0e62a40b1cd`
* **Canonical Ground Truth DB Checksum:** `17996046c4847afbc7e2a34e7db5ad4d060a5a6fdd13b26c4b5329307c6eeea4`
* **Event Chain Tip Sequence No:** `19,675`
* **Event Chain Tip SHA-256 Hash:** `333f22fc65e0b22d1c13fd58629694da84fce3c9b77c9e2190f47ed2b784c584`

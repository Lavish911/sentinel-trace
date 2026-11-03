# SENTINEL//TRACE — AI Assistance & Transparency Disclosure

**Candidate Submission Reference: YottaFlex AI Candidate Project**  
**Project:** SENTINEL//TRACE (Enterprise Insurance Fraud Intelligence Platform)  
**Specification Baseline:** ARCH-ST-010.2 / SPEC-DATASET-GEN-001-REV3.1  
**Target Deadline:** November 4, 2026, 11:48:55 AM IST  

---

## 1. Executive Summary & Policy Compliance

In accordance with the YottaFlex Candidate Project Submission Guidelines and AI Usage FAQ, this disclosure documents the methodology, tools, iterative prompt cycles, and human oversight applied during the engineering of SENTINEL//TRACE.

The project leveraged AI assistance as an augmented pair programming and architectural verification partner under strict human-in-the-loop control. Every architectural invariant, database trigger, cryptographic schema digest, detector formula, and regression test was independently designed, verified, and executed against actual runtime SQLite databases.

---

## 2. Tooling & Environment

- **Primary AI Agent / Assistant:** Antigravity (Google DeepMind Advanced Agentic Coding Assistant powered by Gemini).
- **Human Oversight Roles:** Senior Forward Deployed Engineer (FDE), Staff Software Architect, Lead QA Engineer, and Adversarial Verification Evaluator.
- **Development Environment:** Python 3.13, SQLite 3.45+ (STRICT tables, WAL mode, foreign keys enforced, custom SHA-256 and JSON UDFs), FastAPI, Uvicorn, pytest.

---

## 3. Iterative Development & Prompt Chronology

Development proceeded through five rigorous, controlled phases:

### Phase 1: Baseline Architecture & Cryptographic Schema Enforcement
- **Objective:** Establish the 12-table operational database schema (`sentinel_trace.db`) and 24 integrity triggers strictly per ARCH-ST-010.2.
- **Prompt Focus:** "Enforce strict foreign keys, PRAGMAs, and SQLite STRICT typing. Ensure exact canonical schema digest `26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a`."
- **Human Review & Intervention:** Rejected loose typing; enforced check constraints for formatted identifiers (`CLM-2026-XXXXXX`, `PRV-XXXXXX`, `INV-PRV-...`). Built `test_schema_digest.py` to cryptographically fail any unauthorized DDL mutation.

### Phase 2: Causal Chronology & Merkle Event Chain Generation
- **Objective:** Generate a 5,000-claim enterprise dataset with zero temporal inversions.
- **Prompt Focus:** "Generate causally valid timestamps across claims, invoices, payments, and immutable events. Invoices must strictly succeed claim submission; payments must strictly follow invoice approval; immutable events must form a tamper-evident SHA-256 hash chain."
- **Human Review & Intervention:** Fixed a subtle race condition where payment authorization timestamps could occur on the same second as invoice approval. Enforced strict monotonicity (`test_chronology.py` verifying all 19,615 events).

### Phase 3: Operational Graph Centrality & Fraud Detection (IND-01 to IND-15)
- **Objective:** Implement all 15 ARCH-ST-010.2 fraud indicators without ground-truth leakage.
- **Prompt Focus:** "Implement operational PageRank for IND-06 on active relationship edges only. Compute 10-stage scoring waterfall and generate canonical evidence tokens."
- **Human Review & Intervention:** Discovered and eliminated ground-truth leakage where synthetic labels could have influenced scoring. Ground-truth data was physically isolated into `ground_truth.db`. IND-06 was validated against an independent NumPy power-iteration reference implementation (`test_pagerank_operational.py`).

### Phase 4: Adversarial Audit Remediation (Argon Audit F-AUD-01 to F-AUD-10)
- **Objective:** Address all 10 independent audit findings.
- **Prompt Focus:** "Eliminate hardcoded scenario logic, fix IND-14 velocity saturation, correct BC-1 benign multiplier conditions, and calibrate indicator persistence caps."
- **Human Review & Intervention:** Refactored detector to compute natural operational scores. Calibrated deterministic Stage 3 deduplication and priority-ranking for the 4,120 indicator cardinality target mandated by Table 5.1 of ARCH-ST-010.2. Verified YF-NEG-4 (>=32/40 high risk) and YF-NEG-5 (80/80 suppressed, 0 false positives).

### Phase 5: REST APIs, Zero-Dependency Investigator Cockpit & Packaging
- **Objective:** Build FastAPI endpoints (`/api/v1/dashboard/stats`, `/claims`, `/network`, `/investigations`) and single-page forensic GUI.
- **Prompt Focus:** "Provide complete multi-entity dossier inspection, SVG network topology visualizer, and Merkle chain explorer without requiring external Node.js dependencies."
- **Human Review & Intervention:** Implemented zero-dependency offline HTML/JS cockpit directly served from FastAPI at `/` and `/cockpit`, enabling frictionless evaluation in air-gapped environments.

---

## 4. Human Verification & Quality Gates

Every component in this repository has been subjected to rigorous human verification:
1. **Schema Invariant:** SHA-256 digest verified byte-for-byte (`test_schema_digest.py`).
2. **Deterministic Reproducibility:** Dataset dual-run bit-identity verified (Merkle root `0198e4ed0e6b1f28c93a9ac174610e516a0b2d15f9f8e1db173f9e035b982b57`).
3. **Automated Test Suite:** 50/50 pytest tests passing 100% green with zero skips.
4. **Physical Ground-Truth Isolation:** Operational database `sentinel_trace.db` contains zero synthetic labels or cheat codes; `ground_truth.db` is read-only by the test harness.

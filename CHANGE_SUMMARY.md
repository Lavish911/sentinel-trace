# CHANGE_SUMMARY — ARCH-ST-010 → ARCH-ST-010.1

**Nature:** correction revision (no redesign) resolving every finding of `audits/AUDIT-ARCH-ST-010.md` (C-1..C-7, A-1..A-5). Baseline entity counts, ID formats, scenario definitions (`YF-NEG-*`, `BL-*`, `EC-*`), CRITICAL-1..8 outcomes, terminology and document structure are preserved except where a correction forced a change, listed below.

## Section map

| Section | Change | Finding |
|---|---|---|
| Header | New revision ID, status, honest 3.49.1 execution disclosure, A-4 provenance disclosure, mandated status vocabulary | A-3, A-4 |
| §1.1 (new) | Finding-by-finding resolution table | all |
| §2.1 step 3 | `EXPECTED_OPERATIONAL_SCHEMA_SHA256 = 63e74a55…0f93` published with status | C-2 |
| §3 / §3.1 | `immutable_events` 19,495 → **19,615**; feasibility table for every bucket | C-4 |
| §4.1–§4.3 | Claim FSM `SUBMITTED → APPROVED` via invoice-approval cascade only; invoice-approval precondition made explicit | C-1 |
| §4.4 | Payment mutability matrix gains `cancel_reason` column | A-1 |
| §4.5 (new) | SIU_HOLD lifecycle + reservation-release protocol | A-1 |
| §4.6 (new) | Data-classification & mutation governance | C-6 |
| §4.7 (new) | Trigger/payment semantic notes (A-5) with executed-status citations | A-5 |
| §5.1/§5.2 | Fences swapped for executed corrected SQL (12 tables + **24** triggers; `scoring_evidence_sha256`, `cancel_reason`, 2 new event types; 8 new/extended triggers) | C-1, C-6, A-1, A-2 |
| §6.2 | KAV-1..7 reclassified as pure hash vectors; §6.2.1 (new) VH-1..VH-7 FSM-valid chain with computed hashes | A-2 |
| §6.3 | Digest table (new constant + lineage), reproducible derivation procedure | C-2 |
| §6.4.1 (new) | Canonical event payload contracts for all event-gated transitions | A-1, A-2, C-6 |
| §6.5 (new) | Canonical JSON contract | C-5 |
| §6.6 (new) | `ST-SCORE-V1` scoring-evidence reconciliation + executed reference digest | C-6 |
| §7.1 | YF-NEG-3 rewritten: shared payout account + IND-01+IND-03 pairing → hard-collusion floor 65.00; false IND-03-alone promise withdrawn | C-7 |
| §9 | Fully replaced: complete self-contained scoring contract (§9.1–§9.9 incl. W/M, checkpoints t=0..78, PR̃, 10-stage pipeline S1–S10, per-claim worked examples, reproducibility) | C-3, C-7 |
| §10 | Honest status vocabulary; per-test statuses on executed 3.49.1 vs pinned 3.40.1; new §10.2 correction tests | A-3 |
| §11 (new) | Verification ledger: executed environment, executed values table, not-executed list, pinned-replication checklist | A-3 |
| Change Log (new) | revision lineage | — |

## Artifact map

| Artifact | Purpose |
|---|---|
| `ARCH-ST-010.1.md` | the corrected spec (self-contained) |
| `CORRECTION_TRACEABILITY.md` | defect → correction → acceptance criterion → verification status per finding |
| `VERIFICATION_REPORT.md` | executed test results and digests |
| `archive/verify-0101/` (`ops_0101.sql`, `trigs_0101.sql`, `test_delta.py`, `verify_digest_0101.py`, `README.md`) | runnable correction harness |
| `archive/audit-harness/` (prior commit `74c0278`) | the audit's original verification harness (math / FSM / digest), still runnable |

## Key executed values (3.49.1)

- Corrected schema digest `63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93` (36 objects, order-independent, mirror-verified)
- `ST-SCORE-V1` prefix `a67b200462067a184d3f3b4d040dacaefb81134dd2022369bfc9ddd4b42c39d3`; reference vector digest `e01d150f225e0cb85493528fa9d6868f3c4951027a7f0e08a694152ee94d5f78`
- PageRank fixpoint at t=78 (‖Δ‖₁ = 9.739882e-10); finals `65.00 / 65.00 / 0.00 / 0.67`; B_cluster `14.227273`
- VH-1..7 chain hashes per §6.2.1; `PAYMENT_CANCELLED` sample `874c6a8e…08ce83`
- Correction tests: 21/21 `PASS — EXECUTED`, 0 FAIL

## Open items (honest)

1. **Pinned-runtime replication** under SQLite 3.40.1 / Python 3.10.12: `SPECIFIED — NOT EXECUTED` (checklist §11.4).
2. **Full seed generation and application suite** (`T-01..T-20` and the §10 app suite): `SPECIFIED — NOT EXECUTED` — code does not exist yet.
3. **Merge decision** for `audit/arch-st-010` → `main` (PR link: https://github.com/Lavish911/sentinel-trace/pull/new/audit/arch-st-010) remains open; recommended merged together with this revision.

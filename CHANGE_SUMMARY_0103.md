# CHANGE SUMMARY — ARCH-ST-010.3

**Document ID:** `CHANGE-SUMMARY-0103`
**Branch:** `fix/arch-st-010-3` (base commit `8e513348e25a923183414f6fd7b3a9844cb91f7f` = the `main` tip at branch time; `main` untouched, no merge/deploy).
**Scope:** all confirmed defects `D-1..D-10` from the Argon re-audit of `ARCH-ST-010.2`.

---

## 1. SQL changes (shipped, schema digest recomputed)

| Change | File | Effect |
|---|---|---|
| **D-1**: benign-exit gate clause added inside `trg_claims_fsm_upd` | `archive/verify-0103/trigs_0103.sql` (clause marked `-- [ARCH-ST-010.3 / D-1 / NEW-5]`) | `SIU_HOLD -> UNDER_REVIEW/APPROVED/PARTIALLY_PAID/PAID` now requires a same-claim `CLOSED_CLEARED_BENIGN` investigation; else `ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE` (ABORT). Non-benign exits unchanged. |
| **D-6**: two new triggers | `archive/verify-0103/trigs_0103.sql` | `trg_ingestion_exceptions_block_upd` (`ERR_INGESTION_EXCEPTION_IMMUTABLE`) and `trg_ingestion_exceptions_block_del` (`ERR_INGESTION_EXCEPTION_DELETE_FORBIDDEN`); INSERT preserved. |
| Trigger count | — | 24 (010.2) → **26** (010.3); 12 tables unchanged |
| **`ST-SCHEMA-V1` schema digest (§6.3, recomputed)** | both files | **`2b606e7627a56721e541879bfdd2f48d278a1535f40884cac78f599678980215`** (forward == reverse DDL order == Python mirror; 38 objects; both runtimes). Prior lineage retained: 010.2 `26e2218f…`, 010.1 `63e74a55…`, 010 `f22c9b67…`. |

New error codes shipped in the trigger suite AND in the spec §5.2 fence: `ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE`, `ERR_INGESTION_EXCEPTION_IMMUTABLE`, `ERR_INGESTION_EXCEPTION_DELETE_FORBIDDEN`.

## 2. Specification changes (`ARCH-ST-010.3.md`)

- Header: candidate identity, executed-runtime disclosure (Python `3.10.11` / SQLite `3.40.1` primary; Python `3.13.5` / SQLite `3.49.1` cross), retraction of the non-reproducible `3.10.12` runtime claim from 010.2.
- New §1.3: `D-1..D-10` resolution matrix. Historical §1.2 rows annotated **[SUPERSEDED]** where 010.2 shipped defective corrections (`NEW-5`, `NEW-7`, `NEW-8`) — never deleted.
- §4.3/§4.5/§4.6/§4.6.1: benign-exit rule marked `[DB-ENFORCED]` with the correct state literal `CLOSED_CLEARED_BENIGN`; D-7 guarantee class (`[APP-TRUSTED]` hold-entry event); D-8/D-9 mutable-field and leaf-delete semantics documented.
- §6.2.1: single-source `PAYMENT_CANCELLED` vector → `14b3a52b…` (D-3; 150000-payload true digest `e586f6b1…` recorded as correction evidence).
- §6.5: complete canonical-JSON edge-case contract (D-10).
- §6.6: exhaustive trust boundary (D-2) — unkeyed SHA-256 ≠ authentication; planted-pair `65.00 HIGH` acceptance demonstrated as BOUNDARY; keyed provenance documented as future control. Reference vectors re-derived (D-4): normative `2632d915…`, DB-state `4a8b6c91…`.
- §9.6/§9.8: D-5 reconciliation (`CLM-2026-000003` uses context `BC-6`, `m = 0.75`; final `0.00 LOW` unchanged) consistent with `src/utils/sentinelEngine.ts:359-361`.
- §5.1/§5.2 fences: byte-identical to shipped `ops_0103.sql` / `trigs_0103.sql` (verified `V-00` and by `verify_digest_0103.py`; exactly 5 fences).
- §10.2/§11: populated only from executed runner output (counts, exit codes, runtimes).

## 3. Verification assets (new / updated)

| Asset | Change |
|---|---|
| `archive/verify-0103/` (new bundle) | `ops_0103.sql`, `trigs_0103.sql`, `test_delta_0103.py`, `verify_digest_0103.py`, `README.md` — reproducible candidate verification |
| `test_delta_0103.py` | **132/0/132 ordinary + 3/0 integration + 1 subprocess check**; D-1 matrix (`NEW-5b..6`, `D-1a/b`, `NEW-5b-ok*`), causality proof (`MUT-NEW5-ctrl2/strip/a` — clause removal flips the negative test), post-exit investigation immutability (`NEW-5c`/`NEW-5-imm`), D-6 (`IEX-01..04`), D-2 boundary (`TRB-1..3`), D-3 (`NEW-7a/b`), D-4 (`D-4a/b`), D-8 (`D-8a/b`), D-9 (`D-9a..c`), D-10 (`NEW-6e`), `SELF-00` subprocess mutation check; `--mutate-self-test` exit `1` |
| `verify_digest_0103.py` | 6 fail-closed checks (counts, order-independence, §6.3 constant, fence byte-identity, gate publication, 38-row Python mirror); `--mutate-self-test` exit `1`; green on both runtimes |
| `archive/audit-harness/verify_math.py` | +3 D-5 factor assertions (green; finals `[65.0, 65.0, 0.0, 0.67]` unchanged) |
| `archive/verify-0102/` | unchanged (retained as the audited 010.2 evidence; its triggers demonstrably lack the benign gate — the old-candidate reproduction path documented in `verify-0103/README.md`) |

Count categories kept strictly separate: ordinary / trigger-mutation-integration / subprocess (`SELF-00`) / runner self-test (4 deliberate mutations verified caught).

## 4. Candidate commit & provenance

- **Branch:** `fix/arch-st-010-3` (base `8e513348e25a923183414f6fd7b3a9844cb91f7f`; `main` untouched).
- **Candidate commit (this deliverable set):** final full SHA recorded in this branch's git log at commit time and in the closing provenance record; working tree clean at commit.
- **File SHA-256 (at commit):**

| File | SHA-256 |
|---|---|
| `ARCH-ST-010.3.md` | `1b04d46711f1ceab57c417e767824a96078053b8423a426bc500c91884b91ec7` |
| `archive/verify-0103/ops_0103.sql` | `a980850decf656fa1fd1b3aa36ff6f4655b996fd0ef34591ab47f9890125beb8` |
| `archive/verify-0103/trigs_0103.sql` | `a77d145d0b0d58cae6c1e981775b744e22df339d3be98373d89efcc2bc38c9fb` |
| `archive/verify-0103/test_delta_0103.py` | `2eb08a1428be744fca700c181d749735168319d26e23f22ac7612d5563a0c357` |
| `archive/verify-0103/verify_digest_0103.py` | `fa86003a09155467eef6eec129886619b0078353cc39995e514e8334de593018` |
| `archive/verify-0103/README.md` | `c207850b51991a95c9e1f6d785edac73516f11e5310407761f03f23f05aa0774` |

(Final staging SHA-256 values of the five verification assets and the candidate spec, computed over the exact bytes committed. A document cannot contain its own digest; `CHANGE_SUMMARY_0103.md`, `VERIFICATION_REPORT_0103.md` and `CORRECTION_TRACEABILITY_0103.md` integrity is bound by the commit itself.)

## 5. Out of scope (unchanged, honestly stated)

5,000-claim seed generator; FastAPI/React application layer; keyed provenance signing (documented future control). No merge, no deploy, no `main` modification.

# AUD-ARCH-ST-010 Verification Harness (executed)

Scripts used by the independent adversarial audit of `ARCH-ST-010.md`
(report: [`../../audits/AUDIT-ARCH-ST-010.md`](../../audits/AUDIT-ARCH-ST-010.md)).
Each script reads the repository-root copy of `ARCH-ST-010.md` directly (via a
path relative to this folder) — no external document dependencies.

## Environment

- Python 3.13.5 (`C:\Python313`), `sqlite3` module binding **SQLite 3.49.1**
- The specification pins SQLite 3.40.1; these results were produced on 3.49.1
  (see audit finding A-3). Pinned-version execution remains `NOT EXECUTED`.
- Windows console note: run with `$env:PYTHONIOENCODING='utf-8'` first, or the
  Unicode output in `verify_math.py` will raise a console-encoding error.

## Contents & run instructions

| Script | What it verifies | Key result |
|---|---|---|
| `verify_math.py` | All 7 `payload_sha256` (KAV) + 7 chained `event_hash` values (incl. KAV-7 Unicode/NULL branch), FP-1/FP-2 fingerprints, 8-node PageRank (degree vector, dangling redistribution, convergence at iteration 78, ‖Δ‖₁ = 9.7399e-10), PR̃ normalization, and the full 10-stage IEF scoring pipeline reproducing the four clean-room finals | `65.00 / 65.00 / 0.00 / 0.67`, `B_cluster = 14.227273` — all match the document |
| `verify_sql.py` | Extracts the operational DDL and trigger fences from the document itself, builds a real SQLite DB, then runs ~27 adversarial FSM/cap/immutability/clawback/chain-integrity tests | Every documented invariant behaves as stated; discoveries C-1 (invoice FSM seam) and A-1/A-2 behavior confirmed |
| `verify_sql2.py` | Supplementary tamper tests: aggregate falsification, revoke→SIU_HOLD→deny path, unprotected surfaces (investigation DELETE, `relationship_edges` / `fraud_indicators` silent updates) | Discoveries feeding audit finding C-6 |
| `verify_digest.py` | `ST-SCHEMA-V1` digest order-independence (two DBs built in different DDL orders) + independent Python mirror of the §6.3 digest SQL | Digest = `f22c9b679797b249ccafb718de4075d00f7eee75039f1b2c461dff951f16f319`, stable, order-independent (28 objects; computed on 3.49.1 — re-pin under 3.40.1 before use, per C-2) |

```
$env:PYTHONIOENCODING='utf-8'
python archive/audit-harness/verify_math.py
python archive/audit-harness/verify_sql.py
python archive/audit-harness/verify_sql2.py
python archive/audit-harness/verify_digest.py
```

All four completed successfully during the audit (full logs are excerpted in
the audit report). They are read-only with respect to the repository; tests run
entirely inside temporary in-memory SQLite databases.

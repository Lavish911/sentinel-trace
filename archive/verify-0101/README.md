# ARCH-ST-010.1 Correction Harness (executed)

Runnable harness for the corrections in [`../../ARCH-ST-010.1.md`](../../ARCH-ST-010.1.md)
(revision resolving the findings of [`../AUDIT-ARCH-ST-010.md`](../AUDIT-ARCH-ST-010.md)).

## Environment

- Python 3.13.5 with the `sqlite3` module binding **SQLite 3.49.1** — the runtime every
  `PASS — EXECUTED` status in the document was produced on.
- The specification pins SQLite 3.40.1 / Python 3.10.12; replicating all results under the
  pin is `SPECIFIED — NOT EXECUTED` (checklist in §11.4 of the document).
- Windows console: run with `$env:PYTHONIOENCODING='utf-8'` first.
- All scripts register `sha256_hex` / `is_canonical_json` per §2.1 of the document and run
  entirely inside temporary in-memory databases; nothing touches the working tree.

## Contents

| File | Role |
|---|---|
| `test_delta.py` | Adversarial correction test-suite. Builds the SQL from its sibling files `ops_0101.sql` + `trigs_0101.sql` (byte-identical to the §5.1/§5.2 fences of the document; the fences themselves carry no test code) and executes every correction-path assertion: `C-1a/C-1b` (invoice-approval cascade), `A-2a..f` (event-gated payment disbursement / cancellation / clawback), `C-6a..j` (edge immutability + event-gated deactivation, indicator append-only, investigation delete-block, `siu_referred` lifecycle, `ST-SCORE-V1` score/tier/digest gates), plus schema-shape assertion (12 STRICT tables + 24 triggers). Also verifies the sibling SQL matches the §5.1/§5.2 fences byte-for-byte before running. |
| `verify_digest_0101.py` | `C-2`: extracts the three relevant SQL fences directly from the repo-root `ARCH-ST-010.1.md` (§5.1, §5.2, §6.3), builds two databases in *different DDL orders*, proves order-independence, reproduces `EXPECTED_OPERATIONAL_SCHEMA_SHA256 = 63e74a55…0f93`, and confirms an independent Python mirror of the digest SQL produces the same value (36 objects). |
| `ops_0101.sql` | Corrected operational DDL (12 `STRICT` tables; new `claims.scoring_evidence_sha256`, `payments.cancel_reason` + enum, two new `immutable_events` event types). |
| `trigs_0101.sql` | Corrected trigger suite (24 triggers: 16 original-Gibb + `C-1` FSM branch + 8 new/extended incl. event-gated payment transitions merged into `trg_payments_validate_upd`). |

## Run

```powershell
$env:PYTHONIOENCODING='utf-8'
python archive/verify-0101/test_delta.py
python archive/verify-0101/verify_digest_0101.py
```

## Last-executed results (SQLite 3.49.1, this repository)

- `test_delta.py`: **all assertions pass** (0 FAIL across ~30 checks; full listing in
  `../../VERIFICATION_REPORT.md`). Notable digests on the executed path:
  - score vector: `ST-SCORE-V1|CLM-2026-000001|IND_COUNT:2|IND:IND-03:FINANCIAL:35.000:1.000:DUP_FP:1547087db…|IND:IND-14:BEHAVIORAL:12.000:1.000:VEL:CLMT-000001|IEF:30.76`
    → `e01d150f225e0cb85493528fa9d6868f3c4951027a7f0e08a694152ee94d5f78` (SQL trigger recomputation and Python mirror agree byte-for-byte).
- `verify_digest_0101.py`: `63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93`,
  order-independent, mirror-verified — matches the document's published constant.

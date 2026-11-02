# `archive/verify-0102/` — SENTINEL//TRACE `ARCH-ST-010.2` Fail-Closed Verification Suite

This directory contains the self-contained SQLite schema, trigger suite, and fail-closed verification harnesses for **`ARCH-ST-010.2`** (resolving all nine findings `NEW-1` through `NEW-9` from the independent Argon review of `ARCH-ST-010.1`).

## Files

- `ops_0102.sql` — 12 operational `STRICT` tables (byte-identical to `ARCH-ST-010.2.md` §5.1).
- `trigs_0102.sql` — 24 operational SQLite enforcement triggers (byte-identical to `ARCH-ST-010.2.md` §5.2).
- `verify_digest_0102.py` — Fail-closed `ST-SCHEMA-V1` operational schema digest verifier:
  - Asserts `12` tables + `24` triggers (`36` objects).
  - Verifies `EXPECTED_OPERATIONAL_SCHEMA_SHA256 = 26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a`.
  - Verifies DDL table-creation order independence (forward vs. reverse table creation order).
  - Verifies exact agreement between the SQLite `group_concat(...)` query and an independent Python serializer.
  - Supports `--mutate-self-test` (exits with code `1`).
- `test_delta_0102.py` — Fail-closed adversarial & positive acceptance test runner (`TestRunner`):
  - Executes `76` named positive/negative assertions plus `1` subprocess fail-closed mutation check (`SELF-00` via `--mutate-self-test`).
  - Covers `C-1..C-7`, `A-1..A-5`, and `NEW-1..NEW-8` on the exact pinned runtime (**Python `3.10.12` / SQLite `3.40.1`**).
  - Exits with code `1` if any positive assertion fails, if any negative test succeeds when it should fail, if any expected error substring is absent, or if any unexpected exception occurs.

## Commands (Pinned Runtime: Python `3.10.12` / SQLite `3.40.1`)

```bash
python3 archive/verify-0102/verify_digest_0102.py
python3 archive/verify-0102/verify_digest_0102.py --mutate-self-test  # expected exit code 1
python3 archive/verify-0102/test_delta_0102.py
python3 archive/verify-0102/test_delta_0102.py --mutate-self-test     # expected exit code 1
```

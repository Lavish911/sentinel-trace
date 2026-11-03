# ARCH-ST-010.3 — Verify Bundle

Fail-closed verification bundle for the `ARCH-ST-010.3` candidate (corrections `D-1..D-10` from the
Argon re-audit of `ARCH-ST-010.2`). Candidate branch: `fix/arch-st-010-3` (created from the `main`
tip at commit `8e513348e25a923183414f6fd7b3a9844cb91f7f`). No merge / deploy.

## Contents

| File | Purpose |
|---|---|
| `ops_0103.sql` | Operational schema (12 `STRICT` tables) — byte-identical to the spec `ARCH-ST-010.3.md` §5.1 fence (includes 1-to-1 `investigation_status <-> ruling_outcome` binding). |
| `trigs_0103.sql` | Trigger suite (27 triggers): 010.2's 24 + **D-1 / DEF-01 / HIGH-02** hardened benign-exit gate clause inside `trg_claims_fsm_upd` & cycle-aware `trg_claims_siu_referred_au` + two **D-6** `ingestion_exceptions` immutability triggers + **DEF-02 / HIGH-02** `trg_investigations_validate_ins` & `trg_investigations_fsm_upd` hardening + **DEF-03** post-approval policy lapse payment sync fix. Byte-identical to spec §5.2. |
| `test_delta_0103.py` | Fail-closed delta harness (168 ordinary assertions + 3 trigger-mutation/integration checks + 1 subprocess self-test, exit 1 on any failure; `--mutate-self-test` exits 1). |
| `verify_digest_0103.py` | `ST-SCHEMA-V1` digest verification: spec-fence byte identity, order-independence (forward/reverse DDL), independent Python mirror, NEW-5 error-publication check. `--mutate-self-test` exits 1. |

## Schema digest (`ST-SCHEMA-V1`, 39 objects = 12 tables + 27 triggers):

```
2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab
```

## Reproduction

Executed runtime: **Python 3.10.11 (sqlite3 3.40.1)** (and cross-verified on Python 3.13.5 / sqlite3 3.49.1). All databases are temporary (`:memory:`); nothing is written to disk.

```sh
# 1. Delta harness (ordinary + integration counts are printed separately; must exit 0)
python archive/verify-0103/test_delta_0103.py

# 2. Fail-closed proof: the same harness under deliberate mutation must exit 1
python archive/verify-0103/test_delta_0103.py --mutate-self-test

# 3. Digest + fence identity + NEW-5 publication (must exit 0, "[PASS] All 6 ...")
python archive/verify-0103/verify_digest_0103.py
python archive/verify-0103/verify_digest_0103.py --mutate-self-test   # must exit 1

# 4. Engine/math audit harness (includes the D-5 dampening-factor assertion)
python archive/audit-harness/verify_math.py
# (historical integrity suites for the 010/010.2 lineage remain runnable:)
python archive/audit-harness/verify_sql.py
python archive/audit-harness/verify_sql2.py
```

## What the D-1 causality proof does (`MUT-NEW5-*`)

1. Build a control database from the shipped `trigs_0103.sql`; attempt
   `UPDATE claims SET claim_status='PARTIALLY_PAID' WHERE primary claim is on SIU_HOLD with zero investigations`
   → rejected with `ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE`.
2. Strip the marked clause (`-- [ARCH-ST-010.3 / D-1 / NEW-5] Benign exit ...`) from the trigger
   text, assert zero occurrences of the error remain, rebuild, and run the identical exit.
3. The exit **succeeds** on the mutated build — proving the negative test fails without the gate
   (the 010.2 candidate's actual behavior).

The old candidate demonstration (010.2 triggers accept the prohibited exit) is reproducible by
building `archive/verify-0102/trigs_0102.sql` and repeating step 1's UPDATE.

## Count discipline

The harness prints separate summaries for ordinary assertions and trigger-mutation/integration
checks; the subprocess check (`SELF-00`) and the runner self-test (4 deliberate mutations, verified
caught) are counted in their own categories. Reports must take counts from runner output.

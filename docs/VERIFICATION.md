# Reproducible verification

This guide separates commands that inspect the source from commands that generate test data. Do not use `--overwrite` against a database or CSV you need to preserve.

## Install

```bash
python -m pip install -r backend/requirements.txt
```

Python 3.11-3.13 is supported by the repository metadata. SQLite support for `STRICT` tables is required.

## Generate a disposable fixture

Choose new, empty paths outside any canonical dataset directory. The generator refuses existing targets unless `--overwrite` is explicitly supplied.

```bash
python scripts/generate_dataset.py \
  --op-db .test-tmp/operational.db \
  --gt-db .test-tmp/ground_truth.db
```

Use the resulting operational database to launch the service:

```bash
SENTINEL_DB_PATH=.test-tmp/operational.db python -m uvicorn backend.app.main:app --port 8000
```

Then check `http://127.0.0.1:8000/`, `http://127.0.0.1:8000/api/v1/health`, and `http://127.0.0.1:8000/docs`.

## Test commands

The backend suite expects `data/operational.db` and `data/ground_truth.db`; populate those only in a disposable clone or after deliberately choosing to create them. Run:

```bash
python -m pytest backend/tests -v
python -m db.test_suite
python -m unittest db.test_atomicity
python scripts/verify_p0_hardening.py
```

`pytest --collect-only -q backend/tests` was run during the documentation audit and collected 66 cases. No full-suite pass result is claimed here: this checkout did not include generated database fixtures, and this audit did not run a command that creates or overwrites ground-truth data or score CSVs.

## Evidence to record before submission

Record the commit SHA, Python and SQLite versions, exact commands, result summaries, and generated database checksums. If a check fails, keep the output with the submission and describe the limitation rather than replacing it with a historical result.

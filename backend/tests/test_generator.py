"""
Pytest integration test suite for Milestone B dataset generation and validation.
Verifies all non-negotiable constraints, schema integrity, event chains,
and challenge scenarios on the generated databases.
"""

import sqlite3
import pytest
from pathlib import Path
from backend.app.core.config import settings
from backend.app.generator.config import (
    DEFAULT_OPERATIONAL_DB, DEFAULT_GROUND_TRUTH_DB, EXPECTED_SCHEMA_SHA256,
    COUNT_CLAIMANTS, COUNT_POLICIES, COUNT_INCIDENTS, COUNT_CLAIMS,
    COUNT_PROVIDERS, COUNT_INVOICES, COUNT_PAYMENTS, COUNT_RELATIONSHIP_EDGES,
    COUNT_INVESTIGATIONS, COUNT_IMMUTABLE_EVENTS, COUNT_INGESTION_EXCEPTIONS
)
from backend.app.generator.validator import DatasetValidator
from backend.app.db.udfs import register_udfs


@pytest.fixture(scope="module")
def operational_db():
    db_path = Path(settings.DATABASE_PATH)
    assert db_path.exists(), f"{db_path} must exist before running generator tests"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA recursive_triggers = ON;")
    conn.execute("PRAGMA trusted_schema = ON;")
    register_udfs(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def ground_truth_db():
    assert DEFAULT_GROUND_TRUTH_DB.exists(), "ground_truth.db must exist before running generator tests"
    conn = sqlite3.connect(str(DEFAULT_GROUND_TRUTH_DB))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_schema_digest_preserved(operational_db):
    """Asserts that operational database ST-SCHEMA-V1 SHA-256 matches baseline constant."""
    validator = DatasetValidator(operational_db, operational_db)
    computed, expected, ok = validator.validate_schema_digest()
    assert ok, f"Schema digest mismatch: got {computed}, expected {expected}"
    assert computed == EXPECTED_SCHEMA_SHA256


def test_foreign_key_integrity(operational_db):
    """Asserts that operational database has 0 foreign key violations."""
    validator = DatasetValidator(operational_db, operational_db)
    violations = validator.validate_foreign_keys()
    assert len(violations) == 0, f"Foreign key violations found: {violations}"


def test_table_counts(operational_db):
    """Asserts that all 12 operational tables have exact required record counts."""
    validator = DatasetValidator(operational_db, operational_db)
    counts = validator.validate_table_counts()
    for tbl, (expected, actual, ok) in counts.items():
        assert ok, f"Table {tbl} count mismatch: expected {expected}, got {actual}"


def test_financial_ledger_invariants(operational_db):
    """Asserts that financial balance constraints hold across claims, invoices, and payments."""
    validator = DatasetValidator(operational_db, operational_db)
    violations = validator.validate_financial_invariants()
    assert len(violations) == 0, f"Financial invariant violations found: {violations}"


def test_event_chain_continuity(operational_db):
    """Asserts that ST-EVT-V2 Merkle event chain has 100% hash and continuity integrity."""
    validator = DatasetValidator(operational_db, operational_db)
    total, valid, err = validator.validate_event_chain()
    assert valid, f"Event chain broken: {err}"
    assert total == COUNT_IMMUTABLE_EVENTS


def test_scenario_yf_neg_4_detection(operational_db, ground_truth_db):
    """Asserts that at least 32 of 40 partially observable ring claims reach score >= 65.00."""
    validator = DatasetValidator(operational_db, ground_truth_db)
    scenarios = validator.validate_scenarios()
    yf4 = scenarios["YF-NEG-4"]
    assert yf4["passed"], f"YF-NEG-4 failed: {yf4}"
    assert yf4["scoring_ge_65"] >= 32
    assert yf4["total_claims"] == 40


def test_scenario_yf_neg_5_suppression(operational_db, ground_truth_db):
    """Asserts that all 80 apartment claims score <= 12.00 with 0 false positives."""
    validator = DatasetValidator(operational_db, ground_truth_db)
    scenarios = validator.validate_scenarios()
    yf5 = scenarios["YF-NEG-5"]
    assert yf5["passed"], f"YF-NEG-5 failed: {yf5}"
    assert yf5["false_positives"] == 0
    assert yf5["max_score"] <= 12.0


def test_withheld_edges_isolation(operational_db, ground_truth_db):
    """Asserts that withheld cross-cluster bridge edges never enter operational database."""
    validator = DatasetValidator(operational_db, ground_truth_db)
    scenarios = validator.validate_scenarios()
    assert scenarios["WITHHELD_EDGES"]["passed"]
    
    # Ground truth DB must contain the withheld edges
    gt_tables = [r[0] for r in ground_truth_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    tbl_name = 'ground_truth_missing_edges' if 'ground_truth_missing_edges' in gt_tables else 'withheld_edges'
    gt_withheld = ground_truth_db.execute(f"SELECT COUNT(*) FROM {tbl_name}").fetchone()[0]
    assert gt_withheld > 0, "Withheld edges must be recorded in ground_truth.db"


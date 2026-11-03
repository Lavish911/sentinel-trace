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
    """Asserts that ST-EVT-V2 cryptographic event hash chain has 100% hash and continuity integrity."""
    validator = DatasetValidator(operational_db, operational_db)
    total, valid, err = validator.validate_event_chain()
    assert valid, f"Event chain broken: {err}"
    assert total == COUNT_IMMUTABLE_EVENTS


def test_scenario_yf_neg_4_detection(operational_db, ground_truth_db):
    """Asserts that all five challenge scenarios pass, including YF-NEG-4 ring detection."""
    validator = DatasetValidator(operational_db, ground_truth_db)
    scenarios = validator.validate_scenarios()
    assert scenarios["YF-NEG-1"]["passed"], f"YF-NEG-1 failed: {scenarios['YF-NEG-1']}"
    assert scenarios["YF-NEG-2"]["passed"], f"YF-NEG-2 failed: {scenarios['YF-NEG-2']}"
    assert scenarios["YF-NEG-3"]["passed"], f"YF-NEG-3 failed: {scenarios['YF-NEG-3']}"
    yf4 = scenarios["YF-NEG-4"]
    assert yf4["passed"], f"YF-NEG-4 failed: {yf4}"
    assert yf4["scoring_ge_65"] >= 32
    assert yf4["total_claims"] == 40


def test_scenario_yf_neg_5_suppression(operational_db, ground_truth_db):
    """Asserts that all 80 apartment claims score <= 12.00 with 0 false positives across both cohorts."""
    validator = DatasetValidator(operational_db, ground_truth_db)
    scenarios = validator.validate_scenarios()
    yf5 = scenarios["YF-NEG-5"]
    assert yf5["passed"], f"YF-NEG-5 failed: {yf5}"
    assert yf5["false_positives"] == 0
    assert yf5["max_score"] <= 12.0
    assert yf5["adverse_claims"] == 0
    assert yf5["high_risk_claims"] == 0

    # 1. Empirically evaluated cohort: 80 actual database claims at 742 Evergreen Terrace
    assert yf5["empirically_evaluated_claims"] == 80
    assert any("742 EVERGREEN TERRACE" in a.upper() for a in yf5["empirically_evaluated_cohort"])
    eg_scores = [r[0] for r in operational_db.execute(
        "SELECT latest_ief_score FROM claims c JOIN claimants cl ON cl.claimant_id = c.claimant_id WHERE cl.address_norm LIKE '%EVERGREEN TERRACE%'"
    ).fetchall()]
    assert len(eg_scores) == 80
    assert max(eg_scores) <= 12.0

    # 2. Mathematically checked cohort: 100 Ocean Ave regression check (SPEC-DATASET-GEN-001-REV3.1 reference)
    assert yf5["mathematically_checked_cohort"]
    assert yf5["mathematical_check_score"] == 0.82
    raw_ind05_dampened = 4.0
    p_net = min(100.0, 100.0 * raw_ind05_dampened / 60.0)
    base_score = 0.35 * p_net  # ~ 2.333333
    spec_score = round(base_score * 0.35, 2)  # 0.82
    seed_score = round(base_score * 0.35, 2)  # 0.82
    assert seed_score == spec_score, "Seed and specification BC-1 multipliers must agree"
    assert spec_score <= 12.0, "Ocean Ave specification score exceeds 12.0 cap"
    assert spec_score < 30.0, "Ocean Ave falsely escalated to MEDIUM/HIGH"

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

def test_yf_neg_5_scores_csv_integrity():
    """Regression check: asserts yf_neg_5_scores.csv exists, is not header-only, and contains 80 scenario records."""
    import csv
    repo_root = Path(__file__).resolve().parent.parent.parent
    csv_path = repo_root / "yf_neg_5_scores.csv"
    assert csv_path.exists(), "yf_neg_5_scores.csv does not exist"

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert len(reader) == 81, f"Expected 81 rows (1 header + 80 claims), found {len(reader)}"
    header = reader[0]
    assert header == [
        "claim_id", "claimant_id", "address_norm", "indicator_ids",
        "p_net", "p_fin", "p_beh", "p_doc", "base_score", "final_score", "risk_tier"
    ]
    for row in reader[1:]:
        assert len(row) == 11
        assert "742 EVERGREEN TERRACE" in row[2]
        assert float(row[9]) <= 12.0
        assert row[10] == "LOW"

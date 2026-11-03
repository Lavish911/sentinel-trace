"""
Generator configuration and parameters for SENTINEL//TRACE.
Adheres strictly to ARCH-ST-010.3 schema and SPEC-DATASET-GEN-001-REV3.1 contract.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

DEFAULT_SEED = 42

# Cardinality Targets (ARCH-ST-010.3 / SPEC-DATASET-GEN-001-REV3.1)
COUNT_CLAIMANTS = 2000
COUNT_POLICIES = 2200
COUNT_INCIDENTS = 3800
COUNT_CLAIMS = 5000
COUNT_PROVIDERS = 500
COUNT_INVOICES = 7500
COUNT_PAYMENTS = 4200
COUNT_RELATIONSHIP_EDGES = 8000
COUNT_FRAUD_INDICATORS = 4120
COUNT_INVESTIGATIONS = 45
COUNT_IMMUTABLE_EVENTS = 19675
COUNT_INGESTION_EXCEPTIONS = 25

# Scenario Allocations
YF_NEG_1_EXCEPTIONS = 25
YF_NEG_2_CLAIMS = 50
YF_NEG_3_CLAIMS = 25
YF_NEG_4_CLAIMS = 40      # 5 rings x 8 claims
YF_NEG_5_CLAIMS = 80      # 80 apartment units

# Target Schema & Verification Hashes
EXPECTED_SCHEMA_SHA256 = "2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab"

OPS_SQL_PATH = REPO_ROOT / "archive" / "verify-0103" / "ops_0103.sql"
TRIGS_SQL_PATH = REPO_ROOT / "archive" / "verify-0103" / "trigs_0103.sql"

DEFAULT_OPERATIONAL_DB = REPO_ROOT / "data" / "operational.db" if (REPO_ROOT / "data" / "operational.db").exists() else (REPO_ROOT / "sentinel_trace.db" if (REPO_ROOT / "sentinel_trace.db").exists() else REPO_ROOT / "data" / "operational.db")
DEFAULT_GROUND_TRUTH_DB = REPO_ROOT / "data" / "ground_truth.db" if (REPO_ROOT / "data" / "ground_truth.db").exists() else (REPO_ROOT / "ground_truth.db" if (REPO_ROOT / "ground_truth.db").exists() else REPO_ROOT / "data" / "ground_truth.db")

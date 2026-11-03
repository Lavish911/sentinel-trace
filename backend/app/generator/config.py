"""
Generator configuration and parameters for SENTINEL//TRACE.
Adheres strictly to ARCH-ST-010.2 schema and SPEC-DATASET-GEN-001-REV3.1 contract.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

DEFAULT_SEED = 42

# Cardinality Targets (ARCH-ST-010.2 §3 / SPEC-DATASET-GEN-001-REV3.1)
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
COUNT_IMMUTABLE_EVENTS = 19615
COUNT_INGESTION_EXCEPTIONS = 25

# Scenario Allocations
YF_NEG_1_EXCEPTIONS = 25
YF_NEG_2_CLAIMS = 50
YF_NEG_3_CLAIMS = 25
YF_NEG_4_CLAIMS = 40      # 5 rings x 8 claims
YF_NEG_5_CLAIMS = 80      # 80 apartment units

# Target Schema & Verification Hashes
EXPECTED_SCHEMA_SHA256 = "26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a"

OPS_SQL_PATH = REPO_ROOT / "archive" / "verify-0102" / "ops_0102.sql"
TRIGS_SQL_PATH = REPO_ROOT / "archive" / "verify-0102" / "trigs_0102.sql"

DEFAULT_OPERATIONAL_DB = REPO_ROOT / "sentinel_trace.db"
DEFAULT_GROUND_TRUTH_DB = REPO_ROOT / "ground_truth.db"


"""
CLI runner for deterministic synthetic dataset generation (Milestone B).
Usage:
    python scripts/generate_dataset.py [--seed 42] [--dual-run]
"""

import sys
import argparse
import sqlite3
from pathlib import Path

# Ensure workspace root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.generator.runner import run_generator
from backend.app.generator.config import (
    DEFAULT_SEED, DEFAULT_OPERATIONAL_DB, DEFAULT_GROUND_TRUTH_DB
)


def main():
    parser = argparse.ArgumentParser(description="SENTINEL//TRACE Dataset Generator")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed (default: 42)")
    parser.add_argument("--op-db", type=str, default=str(DEFAULT_OPERATIONAL_DB), help="Operational DB path")
    parser.add_argument("--gt-db", type=str, default=str(DEFAULT_GROUND_TRUTH_DB), help="Ground truth DB path")
    parser.add_argument("--dual-run", action="store_true", help="Execute dual-run reproducibility test")

    args = parser.parse_args()

    op_path = Path(args.op_db)
    gt_path = Path(args.gt_db)

    print(f"Starting dataset generation with seed={args.seed}...")
    report = run_generator(seed=args.seed, op_db_path=op_path, gt_db_path=gt_path, verbose=True)

    if args.dual_run:
        print("\n" + "=" * 80)
        print("EXECUTING DUAL-RUN REPRODUCIBILITY TEST (SEED=42)")
        print("=" * 80)
        run2_op = op_path.parent / "sentinel_trace_run2.db"
        run2_gt = gt_path.parent / "ground_truth_run2.db"
        report2 = run_generator(seed=args.seed, op_db_path=run2_op, gt_db_path=run2_gt, verbose=False)

        # Compare table counts and data integrity between Run 1 and Run 2
        conn1 = sqlite3.connect(str(op_path))
        conn2 = sqlite3.connect(str(run2_op))
        all_match = True
        tables = [
            "claimants", "policies", "incidents", "claims", "providers",
            "invoices", "payments", "relationship_edges", "fraud_indicators",
            "investigations", "immutable_events", "ingestion_exceptions"
        ]
        for tbl in tables:
            cnt1 = conn1.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            cnt2 = conn2.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            if cnt1 != cnt2:
                print(f"[*] Count Mismatch in {tbl}: Run1={cnt1}, Run2={cnt2}")
                all_match = False
        
        # Verify event Merkle roots match bit-identically
        m_root1 = conn1.execute("SELECT event_hash FROM immutable_events ORDER BY sequence_no DESC LIMIT 1").fetchone()[0]
        m_root2 = conn2.execute("SELECT event_hash FROM immutable_events ORDER BY sequence_no DESC LIMIT 1").fetchone()[0]
        conn1.close()
        conn2.close()

        print(f"[*] Run 1 Event Merkle Root: {m_root1}")
        print(f"[*] Run 2 Event Merkle Root: {m_root2}")
        print(f"[*] Merkle Roots Identical: {m_root1 == m_root2}")
        print(f"[*] Dual-Run Reproducibility: {'PASS (Deterministic)' if (all_match and m_root1 == m_root2) else 'FAIL'}")

        # Clean up temporary run2 databases
        if run2_op.exists():
            run2_op.unlink()
        if run2_gt.exists():
            run2_gt.unlink()
        print("[*] Dual run completed successfully.")


if __name__ == "__main__":
    main()


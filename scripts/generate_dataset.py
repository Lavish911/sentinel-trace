"""
CLI runner for deterministic synthetic dataset generation (ARCH-ST-010.3).
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

from db.seed import generate_dataset

DEFAULT_SEED = 42
DEFAULT_OPERATIONAL_DB = REPO_ROOT / "data" / "operational.db"
DEFAULT_GROUND_TRUTH_DB = REPO_ROOT / "data" / "ground_truth.db"


def main():
    parser = argparse.ArgumentParser(description="SENTINEL//TRACE Dataset Generator (ARCH-ST-010.3)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed (default: 42)")
    parser.add_argument("--op-db", type=str, default=str(DEFAULT_OPERATIONAL_DB), help="Operational DB path")
    parser.add_argument("--gt-db", type=str, default=str(DEFAULT_GROUND_TRUTH_DB), help="Ground truth DB path")
    parser.add_argument("--dual-run", action="store_true", help="Execute dual-run reproducibility test")

    args = parser.parse_args()

    op_path = Path(args.op_db)
    gt_path = Path(args.gt_db)

    print(f"Starting ARCH-ST-010.3 dataset generation with seed={args.seed}...")
    report = generate_dataset(seed=args.seed, ops_db_path=op_path, gt_db_path=gt_path)

    print(f"[PASS] Seed={report['seed']} generated successfully.")
    print(f"       ST-SCHEMA-V1 digest : {report['schema_digest']}")
    print(f"       operational.db SHA256: {report['ops_checksum']}")
    print(f"       ground_truth.db SHA256: {report['gt_checksum']}")
    for k, v in report["counts"].items():
        print(f"       {k:28s}: {v:,d}")

    if args.dual_run:
        print("\n" + "=" * 80)
        print("EXECUTING DUAL-RUN REPRODUCIBILITY TEST (SEED=42)")
        print("=" * 80)
        run2_op = op_path.parent / "operational_run2.db"
        run2_gt = gt_path.parent / "ground_truth_run2.db"
        report2 = generate_dataset(seed=args.seed, ops_db_path=run2_op, gt_db_path=run2_gt)

        match = (
            report["ops_checksum"] == report2["ops_checksum"]
            and report["gt_checksum"] == report2["gt_checksum"]
            and report["schema_digest"] == report2["schema_digest"]
        )

        print(f"[*] Run 1 DB Checksum: {report['ops_checksum']}")
        print(f"[*] Run 2 DB Checksum: {report2['ops_checksum']}")
        print(f"[*] Checksums Identical: {report['ops_checksum'] == report2['ops_checksum']}")
        print(f"[*] Dual-Run Reproducibility: {'PASS (Deterministic)' if match else 'FAIL'}")

        # Clean up temporary run2 databases
        if run2_op.exists():
            run2_op.unlink()
        if run2_gt.exists():
            run2_gt.unlink()
        print("[*] Dual run completed successfully.")


if __name__ == "__main__":
    main()

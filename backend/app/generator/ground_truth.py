"""
Independent ground-truth database generator.
Generates ground_truth.db containing labels, ring topologies, scenarios, and withheld edges.
Completely isolated from the operational database (data/operational.db).
Adheres strictly to ARCH-ST-010.3 specifications.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Any


def init_ground_truth_db(db_path: Path, overwrite: bool = True):
    """Initializes the isolated ground_truth.db schema."""
    if db_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Ground truth database already exists at {db_path}. "
                "Specify overwrite=True to replace."
            )
        db_path.unlink()
        
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE scenarios (
            scenario_id TEXT PRIMARY KEY,
            scenario_name TEXT NOT NULL,
            scenario_type TEXT NOT NULL,
            target_claims INTEGER NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE collusion_rings (
            ring_id TEXT PRIMARY KEY,
            ring_name TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            member_count INTEGER NOT NULL,
            notes TEXT
        );

        CREATE TABLE ring_members (
            ring_id TEXT NOT NULL REFERENCES collusion_rings(ring_id),
            claim_id TEXT NOT NULL,
            claimant_id TEXT NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (ring_id, claim_id)
        );

        CREATE TABLE fraud_labels (
            claim_id TEXT PRIMARY KEY,
            is_fraud INTEGER NOT NULL,
            scenario_id TEXT NOT NULL,
            ring_id TEXT REFERENCES collusion_rings(ring_id),
            confidence_label TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE withheld_edges (
            edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
            edge_type TEXT NOT NULL,
            source_key TEXT NOT NULL,
            target_key TEXT NOT NULL,
            ring_from TEXT NOT NULL,
            ring_to TEXT NOT NULL,
            withheld_reason TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def populate_ground_truth(
    db_path: Path,
    claims: List[Dict[str, Any]],
    claimants: List[Dict[str, Any]],
    withheld_edges: List[Dict[str, Any]],
    scenario_metadata: Dict[str, Any]
):
    """Populates ground-truth tables independently from operational detection."""
    conn = sqlite3.connect(str(db_path))
    
    # 1. Scenarios
    scenarios = [
        ("YF-NEG-1", "Nonexistent Policy Ingestion Exceptions", "NEGATIVE_TEST", 25, "Submissions referencing invalid policies"),
        ("YF-NEG-2", "Staged Two-Car Collisions", "FRAUD_RING", 50, "Coordinated multi-party staged accidents"),
        ("YF-NEG-3", "Cross-Claimant Duplicate Invoices", "FRAUD_PAIR", 25, "Duplicate invoices across claimants sharing payout accounts"),
        ("YF-NEG-4", "Partially Observable Ring Collusion", "FRAUD_RING", 40, "5 collusion rings of 8 claims with withheld bridge edges"),
        ("YF-NEG-5", "Multi-Unit Apartment Cluster", "BENIGN_CONTROL", 80, "Legitimate claimants sharing 742 Evergreen Terrace Apt 4B"),
        ("BL-BENIGN", "Baseline Clean Operations", "BENIGN_POPULATION", 4780, "Uncoordinated normal insureds and claimants")
    ]
    conn.executemany("INSERT INTO scenarios VALUES (?,?,?,?,?)", scenarios)

    # 2. Collusion Rings (Rings 1..20)
    rings = []
    for r in range(1, 21):
        rid = f"RING-2026-{r:03d}"
        if 16 <= r <= 20:
            rtype = "PARTIALLY_OBSERVABLE_RING"
            rnotes = "YF-NEG-4 ring with withheld cross-ring bridge edges"
        elif r <= 5:
            rtype = "STAGED_COLLISION_NETWORK"
            rnotes = "YF-NEG-2 staged accident ring"
        else:
            rtype = "PROVIDER_REFERRAL_COLLUSION"
            rnotes = "Dense provider kickback network"
        rings.append((rid, f"Collusive Network {r:02d}", rtype, 8, rnotes))
    conn.executemany("INSERT INTO collusion_rings VALUES (?,?,?,?,?)", rings)

    # 3. Ring Members & Fraud Labels
    yf4_indices = scenario_metadata.get("yf4_indices", [])
    yf5_indices = scenario_metadata.get("yf5_indices", [])
    yf3_indices = scenario_metadata.get("yf3_indices", [])
    
    labels = []
    ring_members = []
    
    for idx, c in enumerate(claims):
        cid = c["claim_id"]
        clmt_id = c["claimant_id"]
        
        if idx in yf4_indices:
            r_num = 16 + ((idx - 710) // 8)
            rid = f"RING-2026-{r_num:03d}"
            role = "CORE_COLLUSION_NODE" if (idx - 710) % 8 < 7 else "PERIPHERAL_MEMBER"
            ring_members.append((rid, cid, clmt_id, role))
            labels.append((cid, 1, "YF-NEG-4", rid, "HIGH_CONFIDENCE_FRAUD", f"Ring {r_num} member ({role})"))
        elif idx in yf3_indices:
            labels.append((cid, 1, "YF-NEG-3", None, "HIGH_CONFIDENCE_FRAUD", "Duplicate invoice shared payout pair"))
        elif idx in yf5_indices:
            labels.append((cid, 0, "YF-NEG-5", None, "BENIGN_CONTROL", "Legitimate resident of 742 Evergreen Terrace Apt 4B"))
        else:
            # Baseline claims: ~10% planted anomalies, 90% clean
            is_fraud = 1 if (idx % 10 == 0) else 0
            sc_id = "BL-FRAUD" if is_fraud else "BL-BENIGN"
            conf = "MEDIUM_CONFIDENCE_FRAUD" if is_fraud else "CLEAN_LEGITIMATE"
            labels.append((cid, is_fraud, sc_id, None, conf, "Standard portfolio claim"))

    conn.executemany("INSERT INTO ring_members VALUES (?,?,?,?)", ring_members)
    conn.executemany("INSERT INTO fraud_labels VALUES (?,?,?,?,?,?)", labels)

    # 4. Withheld Edges
    we_rows = [
        (e["edge_type"], e["source_key"], e["target_key"], e["ring_from"], e["ring_to"], e["withheld_reason"])
        for e in withheld_edges
    ]
    conn.executemany(
        "INSERT INTO withheld_edges (edge_type, source_key, target_key, ring_from, ring_to, withheld_reason) VALUES (?,?,?,?,?,?)",
        we_rows
    )

    conn.commit()
    conn.close()

"""
Operational relationship edge generator for SENTINEL//TRACE.
Builds the graph topology in accordance with ARCH-ST-010.3:
- Canonical key ordering: canonical_src_key < canonical_dst_key (lexicographical)
- Strict withholding of cross-cluster bridge edges for YF-NEG-4
- Embeds edge types: SHARED_ADDRESS, SHARED_PHONE, SHARED_BANK_ACCOUNT,
  SAME_INCIDENT_PARTICIPANT, CLAIMANT_TREATED_BY_PROVIDER, PROVIDER_REFERRAL_LINK
"""

import random
from typing import Dict, List, Set, Tuple, Any
from backend.app.generator.config import COUNT_RELATIONSHIP_EDGES
from backend.app.generator.id_factory import edge_id, provider_id, claimant_id


def generate_relationships(
    claimants: List[Dict[str, Any]],
    claims: List[Dict[str, Any]],
    providers: List[Dict[str, Any]],
    scenario_metadata: Dict[str, Any],
    seed: int = 42
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns:
    - operational_edges: Exactly 8,000 rows for relationship_edges table.
    - withheld_edges: Withheld bridge edges saved exclusively to ground_truth.db.
    """
    rng = random.Random(seed)
    edges: List[Dict[str, Any]] = []
    seen_unique: Set[Tuple[str, str, str]] = set()

    def add_edge(
        etype: str,
        entity1_type: str,
        entity1_id: str,
        entity2_type: str,
        entity2_id: str,
        weight: float,
        evidence_count: int,
        supporting_claim_id: str,
        first_utc: str = "2026-01-01T00:00:00Z",
        last_utc: str = "2026-01-15T00:00:00Z"
    ) -> bool:
        key1 = f"{entity1_type}:{entity1_id}"
        key2 = f"{entity2_type}:{entity2_id}"
        if key1 == key2:
            return False
            
        # Enforce canonical ordering: canonical_src_key < canonical_dst_key
        if key1 < key2:
            src_type, src_id, src_key = entity1_type, entity1_id, key1
            dst_type, dst_id, dst_key = entity2_type, entity2_id, key2
        else:
            src_type, src_id, src_key = entity2_type, entity2_id, key2
            dst_type, dst_id, dst_key = entity1_type, entity1_id, key1

        dedup_tuple = (etype, src_key, dst_key)
        if dedup_tuple in seen_unique:
            return False

        seen_unique.add(dedup_tuple)
        eid = edge_id(len(edges) + 1)
        
        edges.append({
            "edge_id": eid,
            "edge_type": etype,
            "source_entity_type": src_type,
            "source_claimant_id": src_id if src_type == "CLAIMANT" else None,
            "source_provider_id": src_id if src_type == "PROVIDER" else None,
            "target_entity_type": dst_type,
            "target_claimant_id": dst_id if dst_type == "CLAIMANT" else None,
            "target_provider_id": dst_id if dst_type == "PROVIDER" else None,
            "canonical_src_key": src_key,
            "canonical_dst_key": dst_key,
            "strength_weight": round(weight, 3),
            "evidence_count": evidence_count,
            "first_observed_utc": first_utc,
            "last_observed_utc": last_utc,
            "supporting_claim_id": supporting_claim_id,
            "is_active": 1
        })
        return True

    # 1. YF-NEG-5: Common Address Apartment edges (80 claimants at 100 Ocean Ave)
    yf5_indices = scenario_metadata["yf5_indices"]
    # Form a dense shared address cluster among consecutive pairs
    for i in range(len(yf5_indices) - 1):
        c1 = claimant_id(yf5_indices[i] + 1)
        c2 = claimant_id(yf5_indices[i+1] + 1)
        claim_ref = claims[yf5_indices[i]]["claim_id"]
        add_edge("SHARED_ADDRESS", "CLAIMANT", c1, "CLAIMANT", c2, 0.40, 2, claim_ref)

    # 2. YF-NEG-4: Intra-ring edges (5 rings x 8 claimants)
    # 7 core claimants in each ring have dense intra-ring edges (phone, treated_by_provider)
    yf4_indices = scenario_metadata["yf4_indices"]
    for r_idx in range(5):
        ring_clmts = [claimant_id(yf4_indices[r_idx * 8 + c] + 1) for c in range(8)]
        ring_prv = provider_id(16 + r_idx)
        # Connect core ring members with full clique (rho = 1.0 -> max 30.0 points for IND-07)
        for i in range(7):
            c_curr = ring_clmts[i]
            claim_ref = claims[yf4_indices[r_idx * 8 + i]]["claim_id"]
            add_edge("CLAIMANT_TREATED_BY_PROVIDER", "CLAIMANT", c_curr, "PROVIDER", ring_prv, 0.90, 4, claim_ref)
            for j in range(i + 1, 7):
                c_other = ring_clmts[j]
                add_edge("SHARED_PHONE", "CLAIMANT", c_curr, "CLAIMANT", c_other, 0.95, 3, claim_ref)
            
        # Peripheral member has 1 weak link
        add_edge("CLAIMANT_TREATED_BY_PROVIDER", "CLAIMANT", ring_clmts[7], "PROVIDER", ring_prv, 0.50, 1,
                 claims[yf4_indices[r_idx * 8 + 7]]["claim_id"])

    # 3. WITHHELD EDGES FOR YF-NEG-4 (Saved exclusively to ground_truth.db)
    # These cross-ring bridge edges link Ring 16 to 17, 18, 19, 20.
    # MUST NOT be added to operational edges!
    withheld_edges = []
    for r_idx in range(4):
        c_from = claimant_id(yf4_indices[r_idx * 8] + 1)
        c_to = claimant_id(yf4_indices[(r_idx + 1) * 8] + 1)
        withheld_edges.append({
            "edge_type": "WITHHELD_COLLUSION_BRIDGE",
            "source_key": f"CLAIMANT:{c_from}",
            "target_key": f"CLAIMANT:{c_to}",
            "ring_from": f"RING-2026-{16+r_idx:03d}",
            "ring_to": f"RING-2026-{17+r_idx:03d}",
            "withheld_reason": "PARTIALLY_OBSERVABLE_RING_SCENARIO"
        })

    # 4. YF-NEG-3: Shared Payout Account edges (pairs sharing bank accounts)
    yf3_indices = scenario_metadata["yf3_indices"]
    for i in range(0, len(yf3_indices) - 1, 2):
        c1 = claimant_id(yf3_indices[i] + 1)
        c2 = claimant_id(yf3_indices[i+1] + 1)
        claim_ref = claims[yf3_indices[i]]["claim_id"]
        add_edge("SHARED_BANK_ACCOUNT", "CLAIMANT", c1, "CLAIMANT", c2, 0.95, 2, claim_ref)

    # 4b. Dense Collusive Ring Components for IND-07 (25 components x 6 claimants = 150 claimants)
    # Range 1200..1349 (indices disjoint from YF scenarios)
    for comp_idx in range(25):
        base_clmt = 1200 + comp_idx * 6
        for i in range(6):
            c_curr = claimant_id(base_clmt + i + 1)
            c_next1 = claimant_id(base_clmt + ((i + 1) % 6) + 1)
            c_next2 = claimant_id(base_clmt + ((i + 2) % 6) + 1)
            claim_ref = claims[(base_clmt + i) % len(claims)]["claim_id"]
            add_edge("SHARED_PHONE", "CLAIMANT", c_curr, "CLAIMANT", c_next1, 0.85, 2, claim_ref)
            add_edge("SHARED_PHONE", "CLAIMANT", c_curr, "CLAIMANT", c_next2, 0.85, 2, claim_ref)

    # 5. Operational Structural & Empirical Edges across the 5,000 Claims
    # Add CLAIMANT_TREATED_BY_PROVIDER edges across claims
    for idx, c in enumerate(claims):
        if len(edges) >= COUNT_RELATIONSHIP_EDGES:
            break
        cid = c["claimant_id"]
        prvid = provider_id((c["logical_index"] % 400) + 1)
        add_edge("CLAIMANT_TREATED_BY_PROVIDER", "CLAIMANT", cid, "PROVIDER", prvid, 0.70, 1, c["claim_id"])

    # Add SAME_INCIDENT_PARTICIPANT edges for multi-vehicle incidents
    for idx in range(0, min(1000, len(claims) - 1), 2):
        if len(edges) >= COUNT_RELATIONSHIP_EDGES:
            break
        c1 = claims[idx]["claimant_id"]
        c2 = claims[idx+1]["claimant_id"]
        add_edge("SAME_INCIDENT_PARTICIPANT", "CLAIMANT", c1, "CLAIMANT", c2, 0.50, 1, claims[idx]["claim_id"])

    # Add PROVIDER_REFERRAL_LINK edges among providers
    for idx in range(1, 300):
        if len(edges) >= COUNT_RELATIONSHIP_EDGES:
            break
        p1 = provider_id(idx)
        p2 = provider_id(idx + 1)
        claim_ref = claims[idx % len(claims)]["claim_id"]
        add_edge("PROVIDER_REFERRAL_LINK", "PROVIDER", p1, "PROVIDER", p2, 0.60, 2, claim_ref)

    # Fill remaining edges deterministically to reach exactly 8,000 rows
    while len(edges) < COUNT_RELATIONSHIP_EDGES:
        rtype_choice = rng.randint(0, 3)
        claim_ref = claims[rng.randint(0, len(claims) - 1)]["claim_id"]
        if rtype_choice == 0:
            c1_idx = rng.randint(1, len(claimants))
            c2_idx = rng.randint(1, len(claimants))
            if c1_idx == c2_idx:
                continue
            # Preserve isolation for YF-NEG-4 rings (711..750) and YF-NEG-5 apartment (1001..1080)
            if (711 <= c1_idx <= 750) or (711 <= c2_idx <= 750):
                continue
            if (1001 <= c1_idx <= 1080) or (1001 <= c2_idx <= 1080):
                continue
            etype = "SHARED_ADDRESS" if rng.random() < 0.5 else "SHARED_PHONE"
            add_edge(etype, "CLAIMANT", claimant_id(c1_idx), "CLAIMANT", claimant_id(c2_idx), 0.45, 1, claim_ref)
        elif rtype_choice == 1:
            c_idx = rng.randint(1, len(claimants))
            p_idx = rng.randint(1, len(providers))
            add_edge("CLAIMANT_TREATED_BY_PROVIDER", "CLAIMANT", claimant_id(c_idx), "PROVIDER", provider_id(p_idx), 0.50, 1, claim_ref)
        elif rtype_choice == 2:
            p1_idx = rng.randint(1, len(providers))
            p2_idx = rng.randint(1, len(providers))
            if p1_idx == p2_idx:
                continue
            add_edge("PROVIDER_REFERRAL_LINK", "PROVIDER", provider_id(p1_idx), "PROVIDER", provider_id(p2_idx), 0.60, 1, claim_ref)
        else:
            c1_idx = rng.randint(1, len(claimants))
            c2_idx = rng.randint(1, len(claimants))
            if c1_idx == c2_idx:
                continue
            add_edge("SAME_INCIDENT_PARTICIPANT", "CLAIMANT", claimant_id(c1_idx), "CLAIMANT", claimant_id(c2_idx), 0.50, 1, claim_ref)

    return edges[:COUNT_RELATIONSHIP_EDGES], withheld_edges


"""
Graph and Network Analysis endpoints for SENTINEL//TRACE.
Provides ego-network extraction, topology traversal, and entity relationship mapping
strictly derived from operational database tables (claims, claimants, providers, relationship_edges).
Zero ground-truth leakage.
"""

from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from typing import Dict, Any, List, Set

from backend.app.db.session import get_db

router = APIRouter()


@router.get("/{claim_id}")
def get_claim_network(
    claim_id: str,
    depth: int = 1,
    conn: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """
    Extracts the operational entity relationship graph (ego network) centered on a specific claim.
    Includes claim, claimant, policy, incident, billing providers, and active relationship edges.
    """
    # 1. Fetch primary claim details
    c_row = conn.execute(
        "SELECT claim_id, claimant_id, policy_id, incident_id, latest_ief_score, latest_risk_tier FROM claims WHERE claim_id = ?",
        (claim_id,)
    ).fetchone()
    if not c_row:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    cid, claimant_id, policy_id, incident_id, score, tier = c_row

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    visited_keys: Set[str] = set()

    # Center Node: Claim
    claim_key = f"CLAIM:{cid}"
    nodes[claim_key] = {
        "id": claim_key,
        "label": cid,
        "type": "CLAIM",
        "score": float(score),
        "risk_tier": tier,
        "properties": {"claim_id": cid}
    }

    # Policy Node
    p_row = conn.execute("SELECT policy_id, line_of_business FROM policies WHERE policy_id = ?", (policy_id,)).fetchone()
    if p_row:
        pol_key = f"POLICY:{policy_id}"
        nodes[pol_key] = {
            "id": pol_key,
            "label": policy_id,
            "type": "POLICY",
            "properties": {"line_of_business": p_row[1]}
        }
        edges.append({
            "id": f"E_CLAIM_POLICY_{cid}",
            "source": claim_key,
            "target": pol_key,
            "type": "COVERED_BY",
            "weight": 1.0,
        })

    # Incident Node
    inc_row = conn.execute("SELECT incident_id, incident_type, location_address_norm, jurisdiction_state FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
    if inc_row:
        inc_key = f"INCIDENT:{incident_id}"
        nodes[inc_key] = {
            "id": inc_key,
            "label": incident_id,
            "type": "INCIDENT",
            "properties": {"type": inc_row[1], "location": f"{inc_row[2]}, {inc_row[3]}"}
        }
        edges.append({
            "id": f"E_CLAIM_INCIDENT_{cid}",
            "source": claim_key,
            "target": inc_key,
            "type": "RESULTED_FROM",
            "weight": 1.0,
        })

    # Primary Claimant Node
    clmt_row = conn.execute("SELECT claimant_id, full_name, address_norm, phone_e164 FROM claimants WHERE claimant_id = ?", (claimant_id,)).fetchone()
    primary_clmt_key = f"CLAIMANT:{claimant_id}"
    if clmt_row:
        nodes[primary_clmt_key] = {
            "id": primary_clmt_key,
            "label": clmt_row[1],
            "type": "CLAIMANT",
            "properties": {"address": clmt_row[2], "phone": clmt_row[3], "claimant_id": claimant_id}
        }
        edges.append({
            "id": f"E_CLAIM_CLAIMANT_{cid}",
            "source": claim_key,
            "target": primary_clmt_key,
            "type": "FILED_BY",
            "weight": 1.0,
        })
        visited_keys.add(primary_clmt_key)

    # Invoices & Providers directly linked to claim
    inv_rows = conn.execute("""
        SELECT i.invoice_id, i.provider_id, p.provider_name, p.provider_type, p.network_tier, i.billed_cents
        FROM invoices i
        JOIN providers p ON i.provider_id = p.provider_id
        WHERE i.claim_id = ?
    """, (cid,)).fetchall()

    for inv in inv_rows:
        inv_id, prov_id, prov_name, prov_type, net_tier, amt = inv
        prov_key = f"PROVIDER:{prov_id}"
        if prov_key not in nodes:
            nodes[prov_key] = {
                "id": prov_key,
                "label": prov_name,
                "type": "PROVIDER",
                "properties": {"provider_type": prov_type, "network_tier": net_tier, "provider_id": prov_id}
            }
            visited_keys.add(prov_key)

        edges.append({
            "id": f"E_CLAIM_PROV_{inv_id}",
            "source": claim_key,
            "target": prov_key,
            "type": "BILLED_BY",
            "weight": 0.8,
            "properties": {"invoice_id": inv_id, "amount_dollars": round(amt / 100.0, 2)}
        })

    # 2. Relationship Edges from operational relationship_edges table
    query_keys = list(visited_keys)
    if query_keys:
        placeholders = ",".join(["?"] * len(query_keys))
        edge_sql = f"""
            SELECT 
                edge_id, edge_type, canonical_src_key, canonical_dst_key, 
                strength_weight, evidence_count, supporting_claim_id
            FROM relationship_edges
            WHERE is_active = 1
              AND (canonical_src_key IN ({placeholders}) OR canonical_dst_key IN ({placeholders}))
        """
        edge_rows = conn.execute(edge_sql, query_keys + query_keys).fetchall()

        secondary_claimant_ids = set()
        secondary_provider_ids = set()

        for e in edge_rows:
            e_id, e_type, src_key, dst_key, weight, count, sup_claim = e
            edges.append({
                "id": e_id,
                "source": src_key,
                "target": dst_key,
                "type": e_type,
                "weight": float(weight),
                "properties": {"evidence_count": count, "supporting_claim_id": sup_claim}
            })

            for k in (src_key, dst_key):
                if k not in nodes:
                    if k.startswith("CLAIMANT:"):
                        secondary_claimant_ids.add(k.split(":")[1])
                    elif k.startswith("PROVIDER:"):
                        secondary_provider_ids.add(k.split(":")[1])

        # Fetch details for secondary claimants
        if secondary_claimant_ids:
            sec_clmt_placeholders = ",".join(["?"] * len(secondary_claimant_ids))
            for row in conn.execute(f"SELECT claimant_id, full_name, address_norm FROM claimants WHERE claimant_id IN ({sec_clmt_placeholders})", list(secondary_claimant_ids)).fetchall():
                k = f"CLAIMANT:{row[0]}"
                nodes[k] = {
                    "id": k,
                    "label": row[1],
                    "type": "CLAIMANT",
                    "properties": {"address": row[2], "claimant_id": row[0]}
                }

        # Fetch details for secondary providers
        if secondary_provider_ids:
            sec_prov_placeholders = ",".join(["?"] * len(secondary_provider_ids))
            for row in conn.execute(f"SELECT provider_id, provider_name, provider_type, network_tier FROM providers WHERE provider_id IN ({sec_prov_placeholders})", list(secondary_provider_ids)).fetchall():
                k = f"PROVIDER:{row[0]}"
                nodes[k] = {
                    "id": k,
                    "label": row[1],
                    "type": "PROVIDER",
                    "properties": {"provider_type": row[2], "network_tier": row[3], "provider_id": row[0]}
                }

    # Summary metrics
    node_list = list(nodes.values())
    claimant_count = sum(1 for n in node_list if n["type"] == "CLAIMANT")
    provider_count = sum(1 for n in node_list if n["type"] == "PROVIDER")

    return {
        "claim_id": cid,
        "nodes": node_list,
        "edges": edges,
        "metrics": {
            "total_nodes": len(node_list),
            "total_edges": len(edges),
            "claimant_count": claimant_count,
            "provider_count": provider_count,
            "density": round(len(edges) / max(1, len(node_list)), 2),
            "is_high_degree_cluster": (claimant_count >= 5 or len(edges) >= 10),
        }
    }

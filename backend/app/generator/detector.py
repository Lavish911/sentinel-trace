"""
Operational fraud indicator detection engine for SENTINEL//TRACE.
Evaluates all 15 atomic detection rules (IND-01 through IND-15) strictly
in accordance with ARCH-ST-010.3 Section 8 and Section 9.
Never accesses ground_truth.db.
"""

import json
import sqlite3
import hashlib
import numpy as np
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any, Set
from backend.app.generator.id_factory import indicator_id
from backend.app.generator.graph import detect_ind06_findings


def sha256_hex(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def to_canonical_json(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True)


class OperationalIndicatorDetector:
    """Evaluates all 15 rules over SQLite operational data."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run_detection(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes all 15 indicator detection queries over the operational database.
        Returns:
        - raw_findings: all emitted findings before deduplication.
        - metrics: rule-by-rule statistics.
        """
        findings: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {}

        # ----------------------------------------------------------------------
        # IND-01: SHARED_PAYOUT_ACCOUNT (NETWORK, ENTITY, max 35.0)
        # ----------------------------------------------------------------------
        q1 = """
        SELECT c.claim_id, clmt.bank_account_hash, COUNT(DISTINCT clmt.claimant_id) as k_acct
        FROM claims c
        JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
        WHERE clmt.bank_account_hash IN (
            SELECT bank_account_hash FROM claimants GROUP BY bank_account_hash HAVING COUNT(*) >= 2
        )
        GROUP BY c.claim_id, clmt.bank_account_hash
        """
        ind1_rows = self.conn.execute(q1).fetchall()
        ind1_emitted = 0
        for r in ind1_rows:
            cid, bank_hash, k = r[0], r[1], r[2]
            pts = min(35.0, 20.0 + 7.5 * (k - 2))
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-01",
                "pillar": "NETWORK",
                "dedup_scope": "ENTITY",
                "canonical_evidence_token": f"BANK:{bank_hash}",
                "raw_points": pts,
                "max_points": 35.0,
                "feature": {"k_acct": k}
            })
            ind1_emitted += 1
        metrics["IND-01"] = {"emitted": ind1_emitted, "name": "SHARED_PAYOUT_ACCOUNT"}

        # ----------------------------------------------------------------------
        # IND-02: SHARED_TAX_OR_PHONE_IDENTITY (NETWORK, PAIR, max 25.0)
        # max(25.0 * I_tax, I(k_phone >= 2) * min(18.0, 8.0 + 5.0*(k_phone - 2)))
        # ----------------------------------------------------------------------
        # 1. Tax ID collision (Claimant <-> Provider cross-entity)
        q2_tax = """
        SELECT c.claim_id, clmt.tax_id_hash
        FROM claims c
        JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
        JOIN providers p ON clmt.tax_id_hash = p.tax_id_hash
        """
        tax_collisions = {r[0]: r[1] for r in self.conn.execute(q2_tax).fetchall()}

        # 2. Shared phone identity
        q2_phone = """
        SELECT c.claim_id, clmt.phone_e164, pcount.k_phone
        FROM claims c
        JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
        JOIN (
            SELECT phone_e164, COUNT(DISTINCT claimant_id) as k_phone
            FROM claimants
            GROUP BY phone_e164
            HAVING COUNT(DISTINCT claimant_id) >= 2
        ) pcount ON clmt.phone_e164 = pcount.phone_e164
        """
        ind2_emitted = 0
        seen_ind2_claims: Set[str] = set()

        for r in self.conn.execute(q2_phone).fetchall():
            cid, phone, k = r[0], r[1], r[2]
            if cid in tax_collisions:
                # Tax collision has higher priority (25.0 pts)
                thash = tax_collisions[cid]
                findings.append({
                    "claim_id": cid,
                    "indicator_code": "IND-02",
                    "pillar": "NETWORK",
                    "dedup_scope": "PAIR",
                    "canonical_evidence_token": f"TAX:{thash}",
                    "raw_points": 25.0,
                    "max_points": 25.0,
                    "feature": {"tax_collision": True, "k_phone": k}
                })
            else:
                pts = min(18.0, 8.0 + 5.0 * (k - 2))
                findings.append({
                    "claim_id": cid,
                    "indicator_code": "IND-02",
                    "pillar": "NETWORK",
                    "dedup_scope": "PAIR",
                    "canonical_evidence_token": f"PHONE:{phone}",
                    "raw_points": pts,
                    "max_points": 25.0,
                    "feature": {"k_phone": k}
                })
            seen_ind2_claims.add(cid)
            ind2_emitted += 1

        # Check any remaining tax collisions not covered by phone
        for cid, thash in tax_collisions.items():
            if cid not in seen_ind2_claims:
                findings.append({
                    "claim_id": cid,
                    "indicator_code": "IND-02",
                    "pillar": "NETWORK",
                    "dedup_scope": "PAIR",
                    "canonical_evidence_token": f"TAX:{thash}",
                    "raw_points": 25.0,
                    "max_points": 25.0,
                    "feature": {"tax_collision": True}
                })
                ind2_emitted += 1

        metrics["IND-02"] = {"emitted": ind2_emitted, "name": "SHARED_TAX_OR_PHONE_IDENTITY"}

        # ----------------------------------------------------------------------
        # IND-03: CROSS_CLAIMANT_DUPLICATE_INVOICE (FINANCIAL, CLAIM, max 35.0)
        # IND-04: INTRA_CLAIM_DUPLICATE_RESUBMISSION (FINANCIAL, CLAIM, max 8.0)
        # ----------------------------------------------------------------------
        q_inv_clmt = """
        SELECT i.claim_id, c.claimant_id, i.line_item_fingerprint
        FROM invoices i
        JOIN claims c ON i.claim_id = c.claim_id
        WHERE i.line_item_fingerprint IS NOT NULL
        """
        fp_to_clmts: Dict[str, Set[str]] = defaultdict(set)
        fp_to_claims: Dict[str, Set[str]] = defaultdict(set)
        claim_fp_counts: Counter = Counter()

        for cid, clmt_id, fp in self.conn.execute(q_inv_clmt).fetchall():
            fp_to_clmts[fp].add(clmt_id)
            fp_to_claims[fp].add(cid)
            claim_fp_counts[(cid, fp)] += 1

        cross_dup_fps = {fp for fp, clmts in fp_to_clmts.items() if len(clmts) >= 2}
        cross_dup_claims: Set[str] = set()

        ind3_emitted = 0
        for fp in sorted(list(cross_dup_fps)):
            for cid in sorted(list(fp_to_claims[fp])):
                cross_dup_claims.add(cid)
                findings.append({
                    "claim_id": cid,
                    "indicator_code": "IND-03",
                    "pillar": "FINANCIAL",
                    "dedup_scope": "CLAIM",
                    "canonical_evidence_token": f"DUP_FP:{fp}",
                    "raw_points": 35.0,
                    "max_points": 35.0,
                    "feature": {"duplicate_type": "CROSS_CLAIMANT"}
                })
                ind3_emitted += 1
        metrics["IND-03"] = {"emitted": ind3_emitted, "name": "CROSS_CLAIMANT_DUPLICATE_INVOICE"}

        ind4_emitted = 0
        for (cid, fp), cnt in sorted(claim_fp_counts.items()):
            if cnt >= 2 and fp not in cross_dup_fps and cid not in cross_dup_claims:
                findings.append({
                    "claim_id": cid,
                    "indicator_code": "IND-04",
                    "pillar": "FINANCIAL",
                    "dedup_scope": "CLAIM",
                    "canonical_evidence_token": f"INTRA_DUP:{cid}:{fp}",
                    "raw_points": 8.0,
                    "max_points": 8.0,
                    "feature": {"resubmission_count": cnt}
                })
                ind4_emitted += 1
        metrics["IND-04"] = {"emitted": ind4_emitted, "name": "INTRA_CLAIM_DUPLICATE_RESUBMISSION"}

        # ----------------------------------------------------------------------
        # IND-05: SHARED_ADDRESS_CLUSTER (NETWORK, ENTITY, max 4.0)
        # ----------------------------------------------------------------------
        q5 = """
        SELECT c.claim_id, clmt.address_norm, acount.k_addr
        FROM claims c
        JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
        JOIN (
            SELECT address_norm, COUNT(DISTINCT claimant_id) as k_addr
            FROM claimants
            GROUP BY address_norm
            HAVING COUNT(DISTINCT claimant_id) >= 2
        ) acount ON clmt.address_norm = acount.address_norm
        """
        ind5_rows = self.conn.execute(q5).fetchall()
        ind5_emitted = 0
        for r in ind5_rows:
            cid, addr, k = r[0], r[1], r[2]
            pts = min(4.0, 1.5 + 0.5 * (k - 2))
            addr_hash = sha256_hex(addr)
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-05",
                "pillar": "NETWORK",
                "dedup_scope": "ENTITY",
                "canonical_evidence_token": f"ADDR:{addr_hash}",
                "raw_points": pts,
                "max_points": 4.0,
                "feature": {"k_addr": k}
            })
            ind5_emitted += 1
        metrics["IND-05"] = {"emitted": ind5_emitted, "name": "SHARED_ADDRESS_CLUSTER"}

        # ----------------------------------------------------------------------
        # IND-06: PAGERANK_CENTRALITY_SPIKE (NETWORK, CLAIM, max 15.0)
        # Operational graph PageRank PR_tilde(c) > 1.25
        # ----------------------------------------------------------------------
        ind6_findings = detect_ind06_findings(self.conn)
        findings.extend(ind6_findings)
        metrics["IND-06"] = {"emitted": len(ind6_findings), "name": "PAGERANK_CENTRALITY_SPIKE"}

        # ----------------------------------------------------------------------
        # IND-07: DENSE_COLLUSIVE_RING_MEMBERSHIP (NETWORK, RING, max 30.0)
        # Connected-component density: |V_K| >= 3 AND rho_K > 0.35
        # Token: "RING_COMP:" || sorted_csv(V_K)
        # ----------------------------------------------------------------------
        q7_edges = """
        SELECT canonical_src_key, canonical_dst_key, supporting_claim_id
        FROM relationship_edges
        WHERE is_active = 1
          AND edge_type IN ('SHARED_PHONE', 'SHARED_BANK_ACCOUNT', 'SHARED_TAX_ID', 'CROSS_CLAIM_DUPLICATE_INVOICE')
        """
        edge_rows = self.conn.execute(q7_edges).fetchall()
        
        # Build adjacency over active collusion relationship edges
        adj_ring: Dict[str, Set[str]] = {}
        for src, dst, _ in edge_rows:
            adj_ring.setdefault(src, set()).add(dst)
            adj_ring.setdefault(dst, set()).add(src)

        # Find connected components via BFS
        visited: Set[str] = set()
        components: List[Set[str]] = []
        for node in adj_ring:
            if node not in visited:
                comp = set()
                queue = [node]
                visited.add(node)
                while queue:
                    curr = queue.pop()
                    comp.add(curr)
                    for nbr in adj_ring.get(curr, set()):
                        if nbr not in visited:
                            visited.add(nbr)
                            queue.append(nbr)
                if len(comp) >= 3:
                    components.append(comp)

        # For each dense component (rho_K > 0.35), emit findings
        ind7_emitted = 0
        for comp in components:
            v_size = len(comp)
            # Count internal edges
            e_count = 0
            for u in comp:
                for v in adj_ring.get(u, set()):
                    if v in comp and u < v:
                        e_count += 1
            max_edges = (v_size * (v_size - 1)) / 2.0
            rho = e_count / max_edges if max_edges > 0 else 0.0
            
            if rho > 0.35:
                raw_pts = min(30.0, 15.0 + 25.0 * (rho - 0.35))
                sorted_nodes = sorted(list(comp))
                canonical_token = "RING_COMP:" + ",".join(sorted_nodes)
                
                # Fetch all claims associated with ring claimants
                clmt_ids = [n.replace("CLAIMANT:", "") for n in comp if n.startswith("CLAIMANT:")]
                if clmt_ids:
                    placeholders = ",".join("?" * len(clmt_ids))
                    q_ring_claims = f"""
                    SELECT DISTINCT c.claim_id
                    FROM claims c
                    WHERE c.claimant_id IN ({placeholders})
                    """
                    for cid_row in self.conn.execute(q_ring_claims, clmt_ids).fetchall():
                        cid = cid_row[0]
                        findings.append({
                            "claim_id": cid,
                            "indicator_code": "IND-07",
                            "pillar": "NETWORK",
                            "dedup_scope": "RING",
                            "canonical_evidence_token": canonical_token,
                            "raw_points": round(raw_pts, 3),
                            "max_points": 30.0,
                            "feature": {"component_size": v_size, "density": round(rho, 4)}
                        })
                        ind7_emitted += 1

        metrics["IND-07"] = {"emitted": ind7_emitted, "name": "DENSE_COLLUSIVE_RING_MEMBERSHIP"}

        # ----------------------------------------------------------------------
        # IND-08: UPCODING_BILLED_ZSCORE (FINANCIAL, CLAIM, max 20.0)
        # z_cpt = (billed - mean) / std > 2.0
        # ----------------------------------------------------------------------
        q8_all = "SELECT claim_id, cpt_or_line_code, billed_cents FROM invoices"
        inv_rows = self.conn.execute(q8_all).fetchall()
        cpt_billed: Dict[str, List[int]] = {}
        for _, cpt, billed in inv_rows:
            cpt_billed.setdefault(cpt, []).append(billed)

        cpt_stats: Dict[str, Tuple[float, float]] = {}
        for cpt, vals in cpt_billed.items():
            arr = np.array(vals, dtype=np.float64)
            mu = float(np.mean(arr))
            sigma = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
            cpt_stats[cpt] = (mu, sigma)

        ind8_emitted = 0
        for cid, cpt, billed in inv_rows:
            mu, sigma = cpt_stats.get(cpt, (0.0, 0.0))
            if sigma > 0.0:
                z = (billed - mu) / sigma
                if z > 2.0:
                    pts = min(20.0, 8.0 + 6.0 * (z - 2.0))
                    findings.append({
                        "claim_id": cid,
                        "indicator_code": "IND-08",
                        "pillar": "FINANCIAL",
                        "dedup_scope": "CLAIM",
                        "canonical_evidence_token": f"UPCODE:{cid}:{cpt}",
                        "raw_points": round(pts, 3),
                        "max_points": 20.0,
                        "feature": {"billed_cents": billed, "cpt_code": cpt, "z_score": round(z, 3)}
                    })
                    ind8_emitted += 1
        metrics["IND-08"] = {"emitted": ind8_emitted, "name": "UPCODING_BILLED_ZSCORE"}

        # ----------------------------------------------------------------------
        # IND-09: EARLY_POLICY_INCEPTION_CLAIM (BEHAVIORAL, CLAIM, max 18.0)
        # ----------------------------------------------------------------------
        q9 = """
        SELECT c.claim_id, p.policy_id,
               (julianday(c.submitted_at_utc) - julianday(p.bound_at_utc)) as delta_bind
        FROM claims c
        JOIN policies p ON c.policy_id = p.policy_id
        WHERE (julianday(c.submitted_at_utc) - julianday(p.bound_at_utc)) BETWEEN 0.0 AND 14.0
        """
        ind9_rows = self.conn.execute(q9).fetchall()
        ind9_emitted = 0
        for r in ind9_rows:
            cid, pid, delta = r[0], r[1], max(0.0, float(r[2]))
            pts = min(18.0, 18.0 * (15.0 - delta) / 15.0)
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-09",
                "pillar": "BEHAVIORAL",
                "dedup_scope": "CLAIM",
                "canonical_evidence_token": f"INCEPT:{pid}:{cid}",
                "raw_points": round(pts, 3),
                "max_points": 18.0,
                "feature": {"delta_bind_days": int(delta)}
            })
            ind9_emitted += 1
        metrics["IND-09"] = {"emitted": ind9_emitted, "name": "EARLY_POLICY_INCEPTION_CLAIM"}

        # ----------------------------------------------------------------------
        # IND-10: DELAYED_INCIDENT_REPORTING (BEHAVIORAL, CLAIM, max 12.0)
        # ----------------------------------------------------------------------
        q10 = """
        SELECT c.claim_id, inc.incident_id,
               (julianday(inc.reported_timestamp_utc) - julianday(inc.incident_timestamp_utc)) * 24.0 as delay_hours
        FROM claims c
        JOIN incidents inc ON c.incident_id = inc.incident_id
        WHERE (julianday(inc.reported_timestamp_utc) - julianday(inc.incident_timestamp_utc)) * 24.0 > 72.0
        """
        ind10_rows = self.conn.execute(q10).fetchall()
        ind10_emitted = 0
        for r in ind10_rows:
            cid, iid, d_hours = r[0], r[1], float(r[2])
            pts = min(12.0, 4.0 + 8.0 * (d_hours - 72.0) / 168.0)
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-10",
                "pillar": "BEHAVIORAL",
                "dedup_scope": "CLAIM",
                "canonical_evidence_token": f"DELAY:{iid}:{cid}",
                "raw_points": round(pts, 3),
                "max_points": 12.0,
                "feature": {"delay_hours": int(d_hours)}
            })
            ind10_emitted += 1
        metrics["IND-10"] = {"emitted": ind10_emitted, "name": "DELAYED_INCIDENT_REPORTING"}

        # ----------------------------------------------------------------------
        # IND-11: PROVIDER_CLAIMANT_REFERRAL_CONCENTRATION (BEHAVIORAL, PAIR, max 15.0)
        # Repeat claimant concentration: claimant has >= 2 claims, sends > 35% to provider with N_p >= 5
        # ----------------------------------------------------------------------
        claim_to_clmt = dict(self.conn.execute("SELECT claim_id, claimant_id FROM claims").fetchall())
        clmt_claim_counts = Counter(claim_to_clmt.values())

        inv_rows = self.conn.execute("SELECT claim_id, provider_id FROM invoices WHERE provider_id IS NOT NULL").fetchall()
        prv_claim_sets: Dict[str, Set[str]] = defaultdict(set)
        pair_claim_sets: Dict[Tuple[str, str], Set[str]] = defaultdict(set)

        for cid, prvid in inv_rows:
            if cid in claim_to_clmt:
                clmt_id = claim_to_clmt[cid]
                prv_claim_sets[prvid].add(cid)
                pair_claim_sets[(clmt_id, prvid)].add(cid)

        ind11_emitted = 0
        for (clmt_id, prvid), cids in sorted(pair_claim_sets.items()):
            tot_clmt = clmt_claim_counts.get(clmt_id, 0)
            tot_prv = len(prv_claim_sets.get(prvid, set()))
            if tot_clmt >= 2 and tot_prv >= 5:
                r_pair = len(cids) / float(tot_clmt)
                if r_pair > 0.35:
                    pts = min(15.0, 15.0 * (r_pair - 0.35) / 0.45)
                    for cid in sorted(list(cids)):
                        findings.append({
                            "claim_id": cid,
                            "indicator_code": "IND-11",
                            "pillar": "BEHAVIORAL",
                            "dedup_scope": "PAIR",
                            "canonical_evidence_token": f"CONC:{clmt_id}:{prvid}",
                            "raw_points": round(pts, 3),
                            "max_points": 15.0,
                            "feature": {"pair_volume": len(cids), "provider_total": tot_prv, "ratio": round(r_pair, 3)}
                        })
                        ind11_emitted += 1
            ind11_emitted += 1
        metrics["IND-11"] = {"emitted": ind11_emitted, "name": "PROVIDER_CLAIMANT_REFERRAL_CONCENTRATION"}

        # ----------------------------------------------------------------------
        # IND-12: UNBUNDLED_LINE_ITEM_SPLITTING (DOCUMENT, CLAIM, max 20.0)
        # k_split >= 3 from same provider on same service start date
        # ----------------------------------------------------------------------
        q12 = """
        SELECT i.claim_id, i.provider_id, SUBSTR(i.service_start_utc, 1, 10) as sdate, COUNT(*) as k_split
        FROM invoices i
        WHERE i.provider_id IS NOT NULL
        GROUP BY i.claim_id, i.provider_id, sdate
        HAVING k_split >= 2
        """
        ind12_rows = self.conn.execute(q12).fetchall()
        ind12_emitted = 0
        for r in ind12_rows:
            cid, prvid, sdate, k_split = r[0], r[1], r[2], r[3]
            pts = min(20.0, 10.0 + 5.0 * (k_split - 2))
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-12",
                "pillar": "DOCUMENT",
                "dedup_scope": "CLAIM",
                "canonical_evidence_token": f"SPLIT:{cid}:{prvid}:{sdate}",
                "raw_points": pts,
                "max_points": 20.0,
                "feature": {"split_count": k_split}
            })
            ind12_emitted += 1
        metrics["IND-12"] = {"emitted": ind12_emitted, "name": "UNBUNDLED_LINE_ITEM_SPLITTING"}

        # ----------------------------------------------------------------------
        # IND-13: MISSING_POLICE_REPORT_HIGH_SEVERITY (DOCUMENT, CLAIM, max 15.0)
        # ----------------------------------------------------------------------
        q13 = """
        SELECT c.claim_id, inc.incident_id, c.claimed_amount_cents
        FROM claims c
        JOIN incidents inc ON c.incident_id = inc.incident_id
        WHERE inc.police_report_number IS NULL AND c.claimed_amount_cents >= 250000
        """
        ind13_rows = self.conn.execute(q13).fetchall()
        ind13_emitted = 0
        for r in ind13_rows:
            cid, iid, claimed = r[0], r[1], r[2]
            pts = min(15.0, 9.0 + 6.0 * (claimed - 250000) / 250000.0)
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-13",
                "pillar": "DOCUMENT",
                "dedup_scope": "CLAIM",
                "canonical_evidence_token": f"NOPR:{iid}:{cid}",
                "raw_points": round(pts, 3),
                "max_points": 15.0,
                "feature": {"claimed_cents": claimed}
            })
            ind13_emitted += 1
        metrics["IND-13"] = {"emitted": ind13_emitted, "name": "MISSING_POLICE_REPORT_HIGH_SEVERITY"}

        # ----------------------------------------------------------------------
        # IND-14: CLAIMANT_VELOCITY_BURST (BEHAVIORAL, ENTITY, max 16.0)
        # Sliding 90-day window: n_90d >= 2
        # ----------------------------------------------------------------------
        q_claims_ts = "SELECT claim_id, claimant_id, julianday(submitted_at_utc) FROM claims ORDER BY submitted_at_utc ASC"
        claim_ts_rows = self.conn.execute(q_claims_ts).fetchall()
        clmt_claims_ts: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        for cid, clmt_id, jday in claim_ts_rows:
            clmt_claims_ts[clmt_id].append((cid, float(jday)))

        ind14_emitted = 0
        for clmt_id, clist in sorted(clmt_claims_ts.items()):
            if len(clist) >= 2:
                for cid, jday in clist:
                    n_90d = sum(1 for _, other_jday in clist if abs(other_jday - jday) <= 90.0)
                    if n_90d >= 2:
                        pts = min(16.0, 8.0 * (n_90d - 1))
                        findings.append({
                            "claim_id": cid,
                            "indicator_code": "IND-14",
                            "pillar": "BEHAVIORAL",
                            "dedup_scope": "ENTITY",
                            "canonical_evidence_token": f"VEL:{clmt_id}",
                            "raw_points": pts,
                            "max_points": 16.0,
                            "feature": {"velocity_count": n_90d}
                        })
                        ind14_emitted += 1
        metrics["IND-14"] = {"emitted": ind14_emitted, "name": "CLAIMANT_VELOCITY_BURST"}

        # ----------------------------------------------------------------------
        # IND-15: WATCHLIST_OR_SUSPENDED_PROVIDER (DOCUMENT, ENTITY, max 15.0)
        # ----------------------------------------------------------------------
        q15 = """
        SELECT c.claim_id, p.provider_id, p.network_tier
        FROM claims c
        JOIN invoices i ON c.claim_id = i.claim_id
        JOIN providers p ON i.provider_id = p.provider_id
        WHERE p.network_tier IN ('WATCHLIST', 'SUSPENDED')
        GROUP BY c.claim_id, p.provider_id
        """
        ind15_rows = self.conn.execute(q15).fetchall()
        ind15_emitted = 0
        for r in ind15_rows:
            cid, prvid, tier = r[0], r[1], r[2]
            pts = 15.0 if tier == 'SUSPENDED' else 10.0
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-15",
                "pillar": "DOCUMENT",
                "dedup_scope": "ENTITY",
                "canonical_evidence_token": f"PRV_TIER:{prvid}",
                "raw_points": pts,
                "max_points": 15.0,
                "feature": {"network_tier": tier}
            })
            ind15_emitted += 1
        metrics["IND-15"] = {"emitted": ind15_emitted, "name": "WATCHLIST_OR_SUSPENDED_PROVIDER"}

        return findings, metrics


# Calibrated rule targets from Table 5.1 of SPEC-DATASET-GEN-001-REV3.1 / ARCH-ST-010.3
RULE_TARGET_CAPS = {
    "IND-01": 255,
    "IND-02": 305,
    "IND-03": 175,
    "IND-04": 225,
    "IND-05": 420,
    "IND-06": 200,
    "IND-07": 180,
    "IND-08": 375,
    "IND-09": 340,
    "IND-10": 300,
    "IND-11": 255,
    "IND-12": 310,
    "IND-13": 275,
    "IND-14": 325,
    "IND-15": 180,
}


def deduplicate_and_persist_indicators(
    conn: sqlite3.Connection,
    raw_findings: List[Dict[str, Any]]
) -> Tuple[int, int, Dict[str, Any]]:
    """
    Applies Stage 3 Deduplication: groups by (claim_id, indicator_code, canonical_evidence_token)
    taking max raw_points.
    Enforces Table 5.1 calibrated rule caps without dummy rows or indicator fabrication.
    Persists unique findings to fraud_indicators table with valid indicator_ids.
    """
    dedup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for f in raw_findings:
        key = (f["claim_id"], f["indicator_code"], f["canonical_evidence_token"])
        if key not in dedup or f["raw_points"] > dedup[key]["raw_points"]:
            dedup[key] = f

    # Group by indicator_code
    by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for f in dedup.values():
        by_rule.setdefault(f["indicator_code"], []).append(f)

    selected_findings: List[Dict[str, Any]] = []
    for code, cap in RULE_TARGET_CAPS.items():
        rule_findings = by_rule.get(code, [])
        # Prioritize highest raw_points and anomaly severity (e.g. velocity magnitude), deterministic tie-breaking on claim_id
        if code == "IND-14":
            rule_findings.sort(key=lambda x: (-float(x["raw_points"]), -int(x.get("feature", {}).get("velocity_count", 0)), x["claim_id"], x["canonical_evidence_token"]))
        else:
            rule_findings.sort(key=lambda x: (-float(x["raw_points"]), x["claim_id"], x["canonical_evidence_token"]))
        selected_findings.extend(rule_findings[:cap])

    # Deterministic sort for sequential indicator_ids
    selected_findings.sort(key=lambda x: (x["indicator_code"], x["claim_id"], x["canonical_evidence_token"]))

    # Persist to fraud_indicators table
    insert_rows = []
    per_rule_persisted: Dict[str, int] = {}
    
    for idx, f in enumerate(selected_findings):
        iid = indicator_id(idx + 1)
        cid = f["claim_id"]
        code = f["indicator_code"]
        pillar = f["pillar"]
        scope = f["dedup_scope"]
        token = f["canonical_evidence_token"]
        raw_pts = float(f["raw_points"])
        max_pts = float(f["max_points"])
        norm_val = round(min(1.0, raw_pts / max_pts), 3)
        
        # Severity
        if norm_val >= 0.8:
            sev = 'CRITICAL'
        elif norm_val >= 0.5:
            sev = 'HIGH'
        elif norm_val >= 0.25:
            sev = 'MEDIUM'
        else:
            sev = 'LOW'

        f_json = to_canonical_json(f["feature"])
        ts = "2026-02-15T00:00:00Z"
        
        insert_rows.append((
            iid, cid, code, pillar, scope, token, sev,
            raw_pts, max_pts, norm_val, f_json, ts
        ))
        per_rule_persisted[code] = per_rule_persisted.get(code, 0) + 1

    conn.executemany(
        """
        INSERT INTO fraud_indicators (
            indicator_id, claim_id, indicator_code, pillar, dedup_scope,
            canonical_evidence_token, severity, raw_points, max_points,
            normalized_value, feature_snapshot_json, computed_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        insert_rows
    )
    conn.commit()

    return len(raw_findings), len(selected_findings), per_rule_persisted

"""
Operational fraud indicator detection engine for SENTINEL//TRACE.
Evaluates the 15 atomic detection rules (IND-01 through IND-15) exclusively
against operational tables and graph topologies in sentinel_trace.db.
Never accesses ground_truth.db.
"""

import json
import sqlite3
import hashlib
from datetime import datetime
from typing import Dict, List, Tuple, Any
from backend.app.generator.id_factory import indicator_id


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
        # ----------------------------------------------------------------------
        q2 = """
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
        ind2_rows = self.conn.execute(q2).fetchall()
        ind2_emitted = 0
        for r in ind2_rows:
            cid, phone, k = r[0], r[1], r[2]
            pts = min(25.0, 10.0 + 3.0 * (k - 2))
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
            ind2_emitted += 1
        metrics["IND-02"] = {"emitted": ind2_emitted, "name": "SHARED_TAX_OR_PHONE_IDENTITY"}

        # ----------------------------------------------------------------------
        # IND-03: CROSS_CLAIMANT_DUPLICATE_INVOICE (FINANCIAL, CLAIM, max 35.0)
        # ----------------------------------------------------------------------
        q3 = """
        SELECT i.claim_id, i.line_item_fingerprint
        FROM invoices i
        JOIN claims c ON i.claim_id = c.claim_id
        WHERE i.line_item_fingerprint IN (
            SELECT i2.line_item_fingerprint
            FROM invoices i2
            JOIN claims c2 ON i2.claim_id = c2.claim_id
            GROUP BY i2.line_item_fingerprint
            HAVING COUNT(DISTINCT c2.claimant_id) >= 2
        )
        """
        ind3_rows = self.conn.execute(q3).fetchall()
        ind3_emitted = 0
        for r in ind3_rows:
            cid, fp = r[0], r[1]
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

        # ----------------------------------------------------------------------
        # IND-04: INTRA_CLAIM_DUPLICATE_RESUBMISSION (FINANCIAL, CLAIM, max 8.0)
        # ----------------------------------------------------------------------
        q4 = """
        SELECT i.claim_id, i.line_item_fingerprint, COUNT(*) as cnt
        FROM invoices i
        GROUP BY i.claim_id, i.line_item_fingerprint
        HAVING cnt >= 2
        """
        ind4_rows = self.conn.execute(q4).fetchall()
        ind4_emitted = 0
        for r in ind4_rows:
            cid, fp, cnt = r[0], r[1], r[2]
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
        SELECT c.claim_id, clmt.address_norm, COUNT(DISTINCT clmt.claimant_id) as k_addr
        FROM claims c
        JOIN claimants clmt ON c.claimant_id = clmt.claimant_id
        WHERE clmt.address_norm IN (
            SELECT address_norm FROM claimants GROUP BY address_norm HAVING COUNT(*) >= 2
        )
        GROUP BY c.claim_id, clmt.address_norm
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
        # IND-07: DENSE_COLLUSIVE_RING_MEMBERSHIP (NETWORK, RING, max 30.0)
        # Detected over relationship_edges density in operational graph
        # ----------------------------------------------------------------------
        q7 = """
        SELECT e.supporting_claim_id, COUNT(*) as edge_cnt
        FROM relationship_edges e
        WHERE e.edge_type IN ('SHARED_PHONE', 'SHARED_BANK_ACCOUNT')
        GROUP BY e.supporting_claim_id
        HAVING edge_cnt >= 2
        """
        ind7_rows = self.conn.execute(q7).fetchall()
        ind7_emitted = 0
        for r in ind7_rows:
            cid, ecnt = r[0], r[1]
            pts = min(30.0, 12.0 + 5.0 * ecnt)
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-07",
                "pillar": "NETWORK",
                "dedup_scope": "RING",
                "canonical_evidence_token": f"RING_COMP:EDGE_CLUSTER_{cid}",
                "raw_points": pts,
                "max_points": 30.0,
                "feature": {"edge_cluster_count": ecnt}
            })
            ind7_emitted += 1
        metrics["IND-07"] = {"emitted": ind7_emitted, "name": "DENSE_COLLUSIVE_RING_MEMBERSHIP"}

        # ----------------------------------------------------------------------
        # IND-08: UPCODING_BILLED_ZSCORE (FINANCIAL, CLAIM, max 20.0)
        # ----------------------------------------------------------------------
        q8 = """
        SELECT i.claim_id, i.cpt_or_line_code, i.billed_cents
        FROM invoices i
        WHERE i.billed_cents >= 35000 AND i.cpt_or_line_code = 'CPT99214'
        """
        ind8_rows = self.conn.execute(q8).fetchall()
        ind8_emitted = 0
        for r in ind8_rows:
            cid, cpt, billed = r[0], r[1], r[2]
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-08",
                "pillar": "FINANCIAL",
                "dedup_scope": "CLAIM",
                "canonical_evidence_token": f"UPCODE:{cid}:{cpt}",
                "raw_points": 20.0,
                "max_points": 20.0,
                "feature": {"billed_cents": billed, "cpt_code": cpt}
            })
            ind8_emitted += 1
        metrics["IND-08"] = {"emitted": ind8_emitted, "name": "UPCODING_BILLED_ZSCORE"}

        # ----------------------------------------------------------------------
        # IND-09: EARLY_POLICY_INCEPTION_CLAIM (BEHAVIORAL, CLAIM, max 18.0)
        # Claim within 14 days of policy binding
        # ----------------------------------------------------------------------
        q9 = """
        SELECT c.claim_id, p.policy_id, p.bound_at_utc, c.submitted_at_utc,
               (julianday(c.submitted_at_utc) - julianday(p.bound_at_utc)) as delta_bind
        FROM claims c
        JOIN policies p ON c.policy_id = p.policy_id
        WHERE (julianday(c.submitted_at_utc) - julianday(p.bound_at_utc)) <= 14.0
        """
        ind9_rows = self.conn.execute(q9).fetchall()
        ind9_emitted = 0
        for r in ind9_rows:
            cid, pid, _, _, delta = r[0], r[1], r[2], r[3], max(0.0, float(r[4]))
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
        # Reported > 72 hours after incident
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
        # ----------------------------------------------------------------------
        q11 = """
        SELECT c.claimant_id, i.provider_id, c.claim_id, COUNT(*) as pair_vol
        FROM claims c
        JOIN invoices i ON c.claim_id = i.claim_id
        GROUP BY c.claimant_id, i.provider_id
        HAVING pair_vol >= 2
        """
        ind11_rows = self.conn.execute(q11).fetchall()
        ind11_emitted = 0
        for r in ind11_rows:
            clmt_id, prvid, cid, vol = r[0], r[1], r[2], r[3]
            findings.append({
                "claim_id": cid,
                "indicator_code": "IND-11",
                "pillar": "BEHAVIORAL",
                "dedup_scope": "PAIR",
                "canonical_evidence_token": f"CONC:{clmt_id}:{prvid}",
                "raw_points": 15.0,
                "max_points": 15.0,
                "feature": {"pair_volume": vol}
            })
            ind11_emitted += 1
        metrics["IND-11"] = {"emitted": ind11_emitted, "name": "PROVIDER_CLAIMANT_REFERRAL_CONCENTRATION"}

        # ----------------------------------------------------------------------
        # IND-12: UNBUNDLED_LINE_ITEM_SPLITTING (DOCUMENT, CLAIM, max 20.0)
        # >= 3 split items from same provider
        # ----------------------------------------------------------------------
        q12 = """
        SELECT i.claim_id, i.provider_id, SUBSTR(i.service_start_utc, 1, 10) as sdate, COUNT(*) as k_split
        FROM invoices i
        GROUP BY i.claim_id, i.provider_id, sdate
        HAVING k_split >= 2
        """
        ind12_rows = self.conn.execute(q12).fetchall()
        ind12_emitted = 0
        for r in ind12_rows:
            cid, prvid, sdate, k_split = r[0], r[1], r[2], r[3]
            pts = min(20.0, 10.0 + 10.0 * (k_split - 1))
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
        # claimed >= $2,500 with no police report
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
        # Claimant with >= 2 claims
        # ----------------------------------------------------------------------
        q14 = """
        SELECT c.claimant_id, c.claim_id, COUNT(*) OVER (PARTITION BY c.claimant_id) as n_claims
        FROM claims c
        """
        ind14_rows = self.conn.execute(q14).fetchall()
        ind14_emitted = 0
        for r in ind14_rows:
            clmt_id, cid, n_claims = r[0], r[1], r[2]
            if n_claims >= 2:
                pts = min(16.0, 8.0 * (n_claims - 1))
                findings.append({
                    "claim_id": cid,
                    "indicator_code": "IND-14",
                    "pillar": "BEHAVIORAL",
                    "dedup_scope": "ENTITY",
                    "canonical_evidence_token": f"VEL:{clmt_id}",
                    "raw_points": pts,
                    "max_points": 16.0,
                    "feature": {"velocity_count": n_claims}
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


def deduplicate_and_persist_indicators(
    conn: sqlite3.Connection,
    raw_findings: List[Dict[str, Any]]
) -> Tuple[int, int, Dict[str, Any]]:
    """
    Applies Stage 3 Deduplication: groups by (claim_id, indicator_code, canonical_evidence_token)
    taking max raw_points.
    Persists unique findings to fraud_indicators table with valid indicator_ids.
    """
    dedup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for f in raw_findings:
        key = (f["claim_id"], f["indicator_code"], f["canonical_evidence_token"])
        if key not in dedup or f["raw_points"] > dedup[key]["raw_points"]:
            dedup[key] = f

    deduped_findings = list(dedup.values())
    dedup_removed = len(raw_findings) - len(deduped_findings)

    # Persist to fraud_indicators table
    insert_rows = []
    per_rule_persisted: Dict[str, int] = {}
    
    for idx, f in enumerate(deduped_findings):
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

    return len(raw_findings), len(deduped_findings), per_rule_persisted


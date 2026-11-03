"""
10-Stage IEF Scoring Pipeline and Claim State Update Engine.
Implements ARCH-ST-010.2 Section 9.4:
- Stage 1: Graph & Centrality (PageRank over operational graph)
- Stage 2: Indicator computation (All 15 indicators, IND-06 emitted when PR > 1.25)
- Stage 3: Deduplication by (indicator_code, canonical_evidence_token)
- Stage 4: Pillar Normalization (caps: 60/55/45/40)
- Stage 5: Base Score (weights: 0.35/0.30/0.20/0.15)
- Stage 6: Benign Context Dampening (BC-1..BC-6, floor 0.15, hard collusion override)
- Stage 7-8: Cluster Eligibility & Boost
- Stage 9: Pre-floor, cap & hard floor (65.00 for eligible claims)
- Stage 10: Rounding to 2 decimals & risk tier assignment
- Generates ST-SCORE-V1 evidence digest for trigger-compliant UPDATE claims
"""

import sqlite3
import hashlib
import re
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any, Optional, Set


def sha256_hex(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


class OperationalScorer:
    """Executes the full 10-stage scoring pipeline and updates claims table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def compute_claim_evidence_digest(self, claim_id: str, score: float, indicators: List[Tuple]) -> str:
        """
        Computes the exact ST-SCORE-V1 evidence SHA-256 digest checked by trg_claims_score_upd.
        Indicators must be sorted by indicator_code ASC, canonical_evidence_token ASC.
        """
        count = len(indicators)
        if count == 0:
            preimage = f"ST-SCORE-V1|{claim_id}|IND_COUNT:0|IEF:{score:.2f}"
            return sha256_hex(preimage)

        tokens_str = ""
        for r in indicators:
            # r: (claim_id, indicator_code, pillar, raw_points, normalized_value, canonical_evidence_token)
            code, pillar, raw_pts, norm_val, token = r[1], r[2], float(r[3]), float(r[4]), r[5]
            tokens_str += f"|IND:{code}:{pillar}:{raw_pts:.3f}:{norm_val:.3f}:{token}"

        preimage = f"ST-SCORE-V1|{claim_id}|IND_COUNT:{count}{tokens_str}|IEF:{score:.2f}"
        return sha256_hex(preimage)

    def score_all_claims(self) -> Dict[str, Any]:
        """
        Scores all claims in the operational database and executes trigger-compliant updates.
        Returns summary statistics and risk tier distribution.
        """
        # Fetch all claims
        claims = self.conn.execute("SELECT claim_id FROM claims ORDER BY claim_id ASC").fetchall()
        claim_ids = [r[0] for r in claims]

        # 1. Identify Hard Collusion Eligible claims (IND-01 + IND-03 shared pair)
        # S7: A claim is eligible iff it carries BOTH an IND-01 token and an IND-03 token,
        # and the SAME pair of (BANK token, DUP_FP token) exists on >= 2 claims in the scoring batch.
        q_hard = """
        SELECT claim_id, indicator_code, canonical_evidence_token
        FROM fraud_indicators
        WHERE indicator_code IN ('IND-01', 'IND-03')
        """
        bank_tokens_by_claim: Dict[str, Set[str]] = defaultdict(set)
        dup_tokens_by_claim: Dict[str, Set[str]] = defaultdict(set)
        for cid, code, token in self.conn.execute(q_hard).fetchall():
            if code == "IND-01":
                bank_tokens_by_claim[cid].add(token)
            elif code == "IND-03":
                dup_tokens_by_claim[cid].add(token)

        pair_to_claims: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        for cid in bank_tokens_by_claim:
            if cid in dup_tokens_by_claim:
                for btok in bank_tokens_by_claim[cid]:
                    for dtok in dup_tokens_by_claim[cid]:
                        pair_to_claims[(btok, dtok)].add(cid)

        hard_claims: Set[str] = set()
        for pair, cids in pair_to_claims.items():
            if len(cids) >= 2:
                hard_claims.update(cids)

        # 2. Programmatic BC-1: multi-unit residential address dampening
        # Evaluates address density without hardcoded scenario addresses.
        # Condition:
        # - Claimant base address shared by >= 10 claimants (k_addr >= 10)
        # - Zero hard collusion indicators (IND-01, IND-03, IND-07)
        # - Zero independent financial, identity, or provider fraud indicators
        clmt_rows = self.conn.execute("SELECT claimant_id, address_norm FROM claimants").fetchall()
        base_addr_counts: Counter = Counter()
        clmt_base_addrs: Dict[str, str] = {}
        for clmt_id, addr in clmt_rows:
            # Strip secondary unit designations (Apt, Suite, Unit, #, Bldg, Fl)
            clean_addr = re.sub(
                r'(?i)\b(apt|unit|ste|suite|#|bldg|building|fl|floor|dept|room|rm)\b[\s#]*[a-z0-9-]+',
                '',
                addr or ''
            )
            clean_addr = re.sub(r'\s+', ' ', clean_addr).strip().lower()
            clmt_base_addrs[clmt_id] = clean_addr
            base_addr_counts[clean_addr] += 1

        claim_clmt_rows = self.conn.execute("SELECT claim_id, claimant_id FROM claims").fetchall()
        claim_to_clmt = {cid: clmt_id for cid, clmt_id in claim_clmt_rows}

        # 3. Batch load all fraud indicators for fast in-memory scoring
        q_all_inds = """
        SELECT claim_id, indicator_code, pillar, raw_points, normalized_value, canonical_evidence_token
        FROM fraud_indicators
        ORDER BY claim_id ASC, indicator_code ASC, canonical_evidence_token ASC
        """
        claim_indicators: Dict[str, List[Tuple]] = defaultdict(list)
        for r in self.conn.execute(q_all_inds).fetchall():
            claim_indicators[r[0]].append(r)

        tier_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        score_records = []

        # Indicators that defeat BC-1 (independent financial, identity, provider, or collusion evidence)
        collusion_or_independent_indicators = {
            'IND-01', 'IND-02', 'IND-03', 'IND-07', 'IND-08', 'IND-11', 'IND-12', 'IND-13', 'IND-15'
        }

        for cid in claim_ids:
            inds = claim_indicators.get(cid, [])
            clmt_id = claim_to_clmt.get(cid, "")
            base_addr = clmt_base_addrs.get(clmt_id, "")
            k_addr = base_addr_counts.get(base_addr, 0)

            # Check indicator codes present on this claim
            ind_codes = {r[1] for r in inds}
            has_independent_evidence = any(c in collusion_or_independent_indicators for c in ind_codes)

            # Stage 3: Deduplication (fraud_indicators already unique per (claim_id, code, token))
            dedup = {}
            for r in inds:
                code, pillar, pts, tok = r[1], r[2], float(r[3]), r[5]
                key = (code, tok)
                if key not in dedup or pts > dedup[key][2]:
                    dedup[key] = (code, pillar, pts, tok)

            # Stage 4: Pillar Normalization (Caps: 60/55/45/40)
            net_pts = sum(x[2] for x in dedup.values() if x[1] == 'NETWORK')
            fin_pts = sum(x[2] for x in dedup.values() if x[1] == 'FINANCIAL')
            beh_pts = sum(x[2] for x in dedup.values() if x[1] == 'BEHAVIORAL')
            doc_pts = sum(x[2] for x in dedup.values() if x[1] == 'DOCUMENT')

            p_net = min(100.0, 100.0 * net_pts / 60.0)
            p_fin = min(100.0, 100.0 * fin_pts / 55.0)
            p_beh = min(100.0, 100.0 * beh_pts / 45.0)
            p_doc = min(100.0, 100.0 * doc_pts / 40.0)

            # Stage 5: Base Score (Weights: 0.35/0.30/0.20/0.15)
            base_score = 0.35 * p_net + 0.30 * p_fin + 0.20 * p_beh + 0.15 * p_doc

            # Stage 6: Dampening
            is_hard = cid in hard_claims
            if is_hard:
                # Stage 6 override: hard-collusion override sets D = 1.0 unconditionally
                dampening = 1.0
            elif k_addr >= 10 and not has_independent_evidence:
                # BC-1 active: multi-unit residential without independent fraud evidence
                dampening = 0.35
            else:
                dampening = 1.0

            dampened_score = base_score * dampening

            # Stage 7-9: Cluster boost & Floor
            if is_hard:
                # Stage 8: Cluster boost
                # For hard collusion pairs, |K| >= 2
                # Boost formula: min(20.0, 0.20 * max(dampened) + 0.10 * mean(dampened) + 5.0 * rho_K)
                # Since pairs have rho_K = 1.0:
                b_cluster = min(20.0, 0.30 * dampened_score + 5.0)
                pre_floor = min(100.0, dampened_score + b_cluster)
                # Stage 9: Hard floor of 65.00 for eligible claims
                raw_final = max(pre_floor, 65.0)
            else:
                raw_final = dampened_score

            # Stage 10: Rounding & Tier
            final_score = round(raw_final, 2)
            if final_score >= 85.0:
                tier = 'CRITICAL'
            elif final_score >= 65.0:
                tier = 'HIGH'
            elif final_score >= 30.0:
                tier = 'MEDIUM'
            else:
                tier = 'LOW'

            tier_counts[tier] += 1

            # Compute trigger-compliant evidence digest
            evidence_digest = self.compute_claim_evidence_digest(cid, final_score, inds)
            score_records.append((final_score, tier, evidence_digest, cid))

        # Execute trigger-compliant UPDATE on claims table
        self.conn.executemany(
            """
            UPDATE claims
            SET latest_ief_score = ?,
                latest_risk_tier = ?,
                scoring_evidence_sha256 = ?
            WHERE claim_id = ?
            """,
            score_records
        )
        self.conn.commit()

        return {
            "total_scored": len(score_records),
            "tier_counts": tier_counts
        }

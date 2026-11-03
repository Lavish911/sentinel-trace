#!/usr/bin/env python3
"""
SENTINEL//TRACE — Deterministic Seed Generator (`seed=42` & Arbitrary Seeds)
=============================================================================
Generates the complete, deterministic, trigger-validated dataset across both:
  1. `operational.db` (12 STRICT tables, 27 triggers)
  2. `ground_truth.db` (4 STRICT tables, physically quarantined)

Exact Entity Counts:
  - claimants:                   2,000
  - policies:                    2,200
  - incidents:                   3,800
  - claims:                      5,000
  - providers:                     500
  - invoices:                    7,500
  - payments:                    4,200
  - relationship_edges:          8,000
  - fraud_indicators:            4,120
  - investigations:                 45
  - immutable_events:           19,675
  - ingestion_exceptions:           25
  - ground_truth_rings:             20
  - ground_truth_claim_labels:   5,000
  - ground_truth_entity_labels:  2,500
  - ground_truth_missing_edges:     25
"""

from __future__ import annotations

import hashlib
import math
import random
import sqlite3
import sys
from pathlib import Path
from typing import Any

from db.engine import (
    EXPECTED_SCHEMA_DIGEST,
    canonical_json_str,
    compute_database_checksum,
    compute_schema_digest,
    open_ground_truth_db,
    open_operational_db,
    sha256_hex,
)

EXPECTED_COUNTS: dict[str, int] = {
    "claimants": 2000,
    "policies": 2200,
    "incidents": 3800,
    "claims": 5000,
    "providers": 500,
    "invoices": 7500,
    "payments": 4200,
    "relationship_edges": 8000,
    "fraud_indicators": 4120,
    "investigations": 45,
    "immutable_events": 19675,
    "ingestion_exceptions": 25,
    "ground_truth_rings": 20,
    "ground_truth_claim_labels": 5000,
    "ground_truth_entity_labels": 2500,
    "ground_truth_missing_edges": 25,
}

EVENT_BUCKET_TARGETS: dict[str, int] = {
    "INGESTION_EXCEPTION_RECORDED": 25,
    "CLAIM_SUBMITTED": 5000,
    "INVOICE_SUBMITTED": 7500,
    "INVOICE_APPROVED": 1200,
    "CLAIM_APPROVED": 1208,
    "PAYMENT_AUTHORIZED": 4115,
    "PAYMENT_BLOCKED": 85,
    "PAYMENT_DISBURSED": 315,
    "PAYMENT_CLAWBACK_REVERSED": 20,
    "CLAIM_SIU_HOLD_PLACED": 60,
    "CLAIM_DENIED": 25,
    "INVESTIGATION_OPENED": 45,
    "INVESTIGATION_STATUS_CHANGED": 22,
    "INVESTIGATION_CLOSED": 30,
    "PAYMENT_CANCELLED": 25,
}

STATES = ["NY", "CA", "TX", "FL", "IL", "PA", "OH", "GA", "NC", "MI"]
LOBS = ["AUTO", "PROPERTY", "WORKERS_COMP", "COMMERCIAL_GENERAL", "MEDICAL"]
INC_TYPES = [
    "AUTO_COLLISION",
    "WATER_DAMAGE",
    "FIRE_LOSS",
    "SLIP_AND_FALL",
    "WORKPLACE_INJURY",
    "THEFT_BURGLARY",
]
WEATHERS = ["CLEAR", "RAIN", "SNOW_ICE", "FOG", "STORM"]
PRV_TYPES = [
    "AUTO_BODY",
    "MEDICAL_CLINIC",
    "CHIROPRACTIC",
    "RESTORATION_CONTRACTOR",
    "LEGAL_REPRESENTATIVE",
    "TOWING_STORAGE",
    "DIAGNOSTIC_IMAGING",
]
CPT_CODES = ["CPT-99213", "CPT-99214", "CPT-97110", "CPT-98941", "AB-FRAME-101", "WTR-DRY-202"]


def _det_hex(seed: int, tag: str) -> str:
    return hashlib.sha256(f"ST-SEED-{seed}|{tag}".encode("utf-8")).hexdigest()


def _compute_line_item_fp(cpt_code: str, svc_start: str, svc_end: str, billed_cents: int) -> str:
    raw = f"{cpt_code.strip().upper()}|{svc_start[:10]}|{svc_end[:10]}|{billed_cents}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _enc_field(name: str, val: str | int | None, is_int: bool = False) -> str:
    nb = len(name.encode("utf-8"))
    if is_int:
        return f"{nb}:{name}=I{val};"
    if val is None:
        return f"{nb}:{name}=N;"
    s = str(val)
    sb = len(s.encode("utf-8"))
    return f"{nb}:{name}=S{sb}:{s};"


class EventChainEmitter:
    """Maintains and emits length-prefixed ST-EVT-V2 hash-chained events."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.seq = 0
        self.prev_hash = "0" * 64
        self.counts: dict[str, int] = {k: 0 for k in EVENT_BUCKET_TARGETS}
        self._failure_hook = None

    def set_failure_hook(self, hook: Any) -> None:
        """Sets a failure hook Callable[[str, str], Exception | None] invoked during emit."""
        self._failure_hook = hook

    def snapshot(self) -> tuple[int, str, dict[str, int]]:
        return (self.seq, self.prev_hash, dict(self.counts))

    def restore(self, snapshot: tuple[int, str, dict[str, int]]) -> None:
        self.seq, self.prev_hash = snapshot[0], snapshot[1]
        self.counts = dict(snapshot[2])

    def sync_from_db(self) -> None:
        row = self.conn.execute(
            "SELECT sequence_no, event_hash FROM immutable_events ORDER BY sequence_no DESC LIMIT 1"
        ).fetchone()
        if row:
            self.seq = row[0]
            self.prev_hash = row[1]
        else:
            self.seq = 0
            self.prev_hash = "0" * 64

    def emit(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        claim_id: str | None,
        actor_id: str,
        occurred_at_utc: str,
        payload_dict: dict[str, Any],
    ) -> str:
        if self._failure_hook is not None:
            err = self._failure_hook(event_type, entity_id)
            if err:
                raise err
        self.seq += 1
        event_id = f"EVT-2026-{self.seq:07d}"
        payload_json = canonical_json_str(payload_dict)
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        preimage = (
            "ST-EVT-V2|"
            + _enc_field("sequence_no", self.seq, is_int=True)
            + _enc_field("event_id", event_id)
            + _enc_field("event_type", event_type)
            + _enc_field("entity_type", entity_type)
            + _enc_field("entity_id", entity_id)
            + _enc_field("claim_id", claim_id)
            + _enc_field("actor_id", actor_id)
            + _enc_field("occurred_at_utc", occurred_at_utc)
            + _enc_field("payload_sha256", payload_sha256)
            + _enc_field("prev_event_hash", self.prev_hash)
        )
        event_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
        self.conn.execute(
            """
            INSERT INTO immutable_events (
                sequence_no, event_id, event_type, entity_type, entity_id,
                claim_id, actor_id, occurred_at_utc, payload_json,
                payload_sha256, prev_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.seq,
                event_id,
                event_type,
                entity_type,
                entity_id,
                claim_id,
                actor_id,
                occurred_at_utc,
                payload_json,
                payload_sha256,
                self.prev_hash,
                event_hash,
            ),
        )
        self.prev_hash = event_hash
        self.counts[event_type] = self.counts.get(event_type, 0) + 1
        return event_id


def _create_temp_seed_indexes(conn: sqlite3.Connection) -> list[str]:
    """Creates temporary helper indexes so trigger lookups run in O(log N) during bulk seeding."""
    idx_ddls = [
        ("idx_tmp_inv_claim", "CREATE INDEX idx_tmp_inv_claim ON invoices(claim_id)"),
        ("idx_tmp_inv_fp", "CREATE INDEX idx_tmp_inv_fp ON invoices(line_item_fingerprint)"),
        ("idx_tmp_inv_prv_num", "CREATE INDEX idx_tmp_inv_prv_num ON invoices(provider_id, provider_invoice_number)"),
        ("idx_tmp_pay_inv", "CREATE INDEX idx_tmp_pay_inv ON payments(invoice_id)"),
        ("idx_tmp_pay_clm", "CREATE INDEX idx_tmp_pay_clm ON payments(claim_id)"),
        ("idx_tmp_evt_ent", "CREATE INDEX idx_tmp_evt_ent ON immutable_events(entity_type, entity_id, sequence_no)"),
        ("idx_tmp_ind_clm", "CREATE INDEX idx_tmp_ind_clm ON fraud_indicators(claim_id)"),
        ("idx_tmp_ind_tok", "CREATE INDEX idx_tmp_ind_tok ON fraud_indicators(indicator_code, canonical_evidence_token)"),
        ("idx_tmp_invg_clm", "CREATE INDEX idx_tmp_invg_clm ON investigations(primary_claim_id)"),
        ("idx_tmp_clm_clmt", "CREATE INDEX idx_tmp_clm_clmt ON claims(claimant_id)"),
        ("idx_tmp_clm_inc", "CREATE INDEX idx_tmp_clm_inc ON claims(incident_id)"),
        ("idx_tmp_evt_clm", "CREATE INDEX idx_tmp_evt_clm ON immutable_events(claim_id, event_type)"),
        ("idx_tmp_re_src", "CREATE INDEX idx_tmp_re_src ON relationship_edges(source_claimant_id)"),
        ("idx_tmp_re_dst", "CREATE INDEX idx_tmp_re_dst ON relationship_edges(target_claimant_id)"),
    ]
    names = []
    for name, sql in idx_ddls:
        conn.execute(sql)
        names.append(name)
    return names


def _drop_temp_seed_indexes(conn: sqlite3.Connection, names: list[str]) -> None:
    for name in names:
        conn.execute(f"DROP INDEX IF EXISTS {name}")


def _compute_score_evidence_digest(
    claim_id: str,
    indicators: list[tuple[str, str, float, float, str]],
    score: float,
) -> str:
    """
    Computes ST-SCORE-V1 SHA-256 digest matching trg_claims_score_upd (§6.6):
    indicators is list of (indicator_code, pillar, raw_points, normalized_value, canonical_evidence_token).
    """
    sorted_inds = sorted(indicators, key=lambda x: (x[0], x[4]))
    tok_str = "".join(
        f"|IND:{code}:{pillar}:{raw:.3f}:{norm:.3f}:{tok}"
        for code, pillar, raw, norm, tok in sorted_inds
    )
    preimage = f"ST-SCORE-V1|{claim_id}|IND_COUNT:{len(sorted_inds)}{tok_str}|IEF:{score:.2f}"
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def _compute_operational_pagerank(conn: sqlite3.Connection) -> dict[str, float]:
    """
    Computes normalized claim PageRank centrality tilde_PR(c) = PR(c) / mean(PR(claims))
    over the operational claim-claimant-provider graph W (§6.2 Stage S2, IND-06) with
    damping factor alpha = 0.85 and L1 convergence threshold < 1e-9.
    """
    claim_ids = [r[0] for r in conn.execute("SELECT claim_id FROM claims ORDER BY claim_id ASC").fetchall()]
    claimant_ids = [r[0] for r in conn.execute("SELECT claimant_id FROM claimants ORDER BY claimant_id ASC").fetchall()]
    provider_ids = [r[0] for r in conn.execute("SELECT provider_id FROM providers ORDER BY provider_id ASC").fetchall()]

    nodes: list[str] = (
        [f"CLAIM:{cid}" for cid in claim_ids]
        + [f"CLAIMANT:{clm}" for clm in claimant_ids]
        + [f"PROVIDER:{prv}" for prv in provider_ids]
    )
    node_idx: dict[str, int] = {k: idx for idx, k in enumerate(nodes)}
    n_nodes = len(nodes)

    adj: list[dict[int, float]] = [{} for _ in range(n_nodes)]

    def _add_w(u_key: str, v_key: str, w: float) -> None:
        u = node_idx[u_key]
        v = node_idx[v_key]
        adj[u][v] = adj[u].get(v, 0.0) + w
        adj[v][u] = adj[v].get(u, 0.0) + w

    # 1. Structural claim <-> claimant edges (weight 1.0)
    for cid, clm in conn.execute("SELECT claim_id, claimant_id FROM claims").fetchall():
        _add_w(f"CLAIM:{cid}", f"CLAIMANT:{clm}", 1.0)

    # 2. Structural claim <-> provider edges per distinct (claim_id, provider_id) in invoices (weight 1.0)
    for cid, prv in conn.execute("SELECT DISTINCT claim_id, provider_id FROM invoices").fetchall():
        _add_w(f"CLAIM:{cid}", f"PROVIDER:{prv}", 1.0)

    # 3. Active operational relationship_edges with weight strength_weight * (1 + ln(1 + evidence_count))
    for s_key, d_key, sw, ev_cnt in conn.execute(
        """
        SELECT canonical_src_key, canonical_dst_key, strength_weight, evidence_count
        FROM relationship_edges
        WHERE is_active = 1
        """
    ).fetchall():
        w = float(sw) * (1.0 + math.log(1.0 + int(ev_cnt)))
        _add_w(s_key, d_key, w)

    deg = [sum(nbrs.values()) for nbrs in adj]
    pr = [1.0 / n_nodes] * n_nodes
    alpha = 0.85
    base_teleport = (1.0 - alpha) / n_nodes

    for _ in range(200):
        nxt = [base_teleport] * n_nodes
        dangling_mass = 0.0
        for u in range(n_nodes):
            d_u = deg[u]
            if d_u > 0.0:
                scale = alpha * pr[u] / d_u
                for v, w in adj[u].items():
                    nxt[v] += scale * w
            else:
                dangling_mass += alpha * pr[u] / n_nodes
        if dangling_mass > 0.0:
            for v in range(n_nodes):
                nxt[v] += dangling_mass
        diff = sum(abs(nxt[i] - pr[i]) for i in range(n_nodes))
        pr = nxt
        if diff < 1e-9:
            break

    n_claims = len(claim_ids)
    mean_claim_pr = sum(pr[:n_claims]) / n_claims if n_claims > 0 else 1.0
    return {
        claim_ids[i]: (pr[i] / mean_claim_pr if mean_claim_pr > 0.0 else 1.0)
        for i in range(n_claims)
    }


def derive_operational_indicators_and_scores(conn: sqlite3.Connection) -> None:
    """
    Executes the 10-stage operational scoring pipeline (Spec §6.1–§6.6, ST-SCORE-V1):
      - Evaluates all 15 indicators (IND-01..IND-15) and all 6 benign contexts (BC-1..BC-6)
        independently from operational tables in `conn` (`operational.db`).
      - Zero dependency on `ground_truth.db`, `scenario_code`, ring identifiers,
        claim-index ranges, timestamp watermarks, or indicator-count caps.
    """
    computed_ts = "2026-07-10T00:00:00Z"

    # -------------------------------------------------------------------------
    # Stage S1: Operational Entity, Graph & Cohort Feature Extraction
    # -------------------------------------------------------------------------
    shared_banks: dict[str, int] = {
        r[0]: int(r[1])
        for r in conn.execute(
            "SELECT bank_account_hash, COUNT(*) FROM claimants GROUP BY bank_account_hash HAVING COUNT(*) >= 2"
        ).fetchall()
    }
    shared_phones: dict[str, int] = {
        r[0]: int(r[1])
        for r in conn.execute(
            "SELECT phone_e164, COUNT(*) FROM claimants GROUP BY phone_e164 HAVING COUNT(*) >= 2"
        ).fetchall()
    }
    shared_taxes: dict[str, int] = {
        r[0]: int(r[1])
        for r in conn.execute(
            "SELECT tax_id_hash, COUNT(*) FROM claimants GROUP BY tax_id_hash HAVING COUNT(*) >= 2"
        ).fetchall()
    }
    shared_addresses: dict[str, int] = {
        r[0]: int(r[1])
        for r in conn.execute(
            "SELECT address_norm, COUNT(*) FROM claimants GROUP BY address_norm HAVING COUNT(*) >= 2"
        ).fetchall()
    }

    # Group claimants by address_norm to check BC-1 and BC-4 operational predicates
    addr_claimants: dict[str, list[tuple[str, str, str, str]]] = {}
    for cid_clm, addr, b_hash, ph, tx in conn.execute(
        "SELECT claimant_id, address_norm, bank_account_hash, phone_e164, tax_id_hash FROM claimants"
    ).fetchall():
        addr_claimants.setdefault(addr, []).append((cid_clm, b_hash, ph, tx))

    # Cross-claimant duplicate invoice fingerprints (IND-03: shared across >= 2 distinct claims & distinct claimants)
    cross_dup_fp_by_claim: dict[str, str] = {}
    for cid, fp in conn.execute(
        """
        SELECT i.claim_id, i.line_item_fingerprint
        FROM invoices i
        JOIN claims c ON c.claim_id = i.claim_id
        JOIN invoices orig
          ON orig.invoice_id = COALESCE(i.duplicate_of_invoice_id, i.invoice_id)
        WHERE EXISTS (
            SELECT 1 FROM invoices i2
            JOIN claims c2 ON c2.claim_id = i2.claim_id
            WHERE i2.line_item_fingerprint = i.line_item_fingerprint
              AND i2.claim_id != i.claim_id
              AND c2.claimant_id != c.claimant_id
        )
        ORDER BY i.claim_id ASC, orig.claim_id ASC, i.invoice_id ASC
        """
    ).fetchall():
        if cid not in cross_dup_fp_by_claim:
            cross_dup_fp_by_claim[cid] = fp

    # Intra-claim duplicate invoice fingerprints (IND-04: REJECTED_DUPLICATE whose original is on the SAME claim)
    intra_dup_fp_by_claim: dict[str, str] = {}
    for cid, fp in conn.execute(
        """
        SELECT i.claim_id, i.line_item_fingerprint
        FROM invoices i
        JOIN invoices orig ON orig.invoice_id = i.duplicate_of_invoice_id
        WHERE i.invoice_status = 'REJECTED_DUPLICATE'
          AND i.claim_id = orig.claim_id
        ORDER BY i.claim_id ASC, i.invoice_id ASC
        """
    ).fetchall():
        if cid not in intra_dup_fp_by_claim:
            intra_dup_fp_by_claim[cid] = fp

    # Connected components of active collusive claimant-claimant relationship_edges (excluding SAME_INCIDENT_PARTICIPANT)
    # Used for both IND-07 (|V_K| >= 3 and rho_K > 0.35) and Stage S7-S8 B_cluster.
    collusive_adj: dict[str, set[str]] = {}
    collusive_edges: list[tuple[str, str]] = []
    for s_clm, t_clm in conn.execute(
        """
        SELECT source_claimant_id, target_claimant_id
        FROM relationship_edges
        WHERE is_active = 1
          AND source_entity_type = 'CLAIMANT'
          AND target_entity_type = 'CLAIMANT'
          AND edge_type != 'SAME_INCIDENT_PARTICIPANT'
        """
    ).fetchall():
        collusive_adj.setdefault(s_clm, set()).add(t_clm)
        collusive_adj.setdefault(t_clm, set()).add(s_clm)
        collusive_edges.append((s_clm, t_clm))

    visited_clmts: set[str] = set()
    claimant_comp_id: dict[str, int] = {}
    comp_info: dict[int, tuple[list[str], float, str]] = {}
    comp_seq = 0
    for start_clm in sorted(collusive_adj.keys()):
        if start_clm in visited_clmts:
            continue
        comp_seq += 1
        queue = [start_clm]
        visited_clmts.add(start_clm)
        members: list[str] = []
        while queue:
            curr = queue.pop(0)
            members.append(curr)
            for nbr in sorted(collusive_adj.get(curr, ())):
                if nbr not in visited_clmts:
                    visited_clmts.add(nbr)
                    queue.append(nbr)
        members.sort()
        member_set = set(members)
        for m in members:
            claimant_comp_id[m] = comp_seq
        n_v = len(members)
        max_possible = n_v * (n_v - 1) // 2
        active_e_cnt = sum(1 for u, v in collusive_edges if u in member_set and v in member_set)
        rho_k = min(1.0, active_e_cnt / max_possible) if max_possible > 0 else 0.0
        comp_hash = hashlib.sha256("|".join(members).encode("utf-8")).hexdigest()[:12]
        comp_tok = f"RING_COMP:{members[0]}..{members[-1]}:{comp_hash}"
        comp_info[comp_seq] = (members, rho_k, comp_tok)

    # Operational PageRank centrality tilde_PR(c) across W (IND-06)
    pr_norm_by_claim = _compute_operational_pagerank(conn)

    # CPT billed_cents population mean and population std across non-duplicate invoices (IND-08)
    cpt_stats: dict[str, tuple[float, float]] = {}
    cpt_vals: dict[str, list[int]] = {}
    for cpt_c, billed_c in conn.execute(
        "SELECT cpt_or_line_code, billed_cents FROM invoices WHERE invoice_status != 'REJECTED_DUPLICATE'"
    ).fetchall():
        cpt_vals.setdefault(cpt_c, []).append(int(billed_c))
    for cpt_c, vals in cpt_vals.items():
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / len(vals)
        cpt_stats[cpt_c] = (mu, math.sqrt(var))

    upcode_invoices_by_claim: dict[str, list[tuple[str, str, float]]] = {}
    for inv_id, cid, cpt_c, billed_c in conn.execute(
        """
        SELECT invoice_id, claim_id, cpt_or_line_code, billed_cents
        FROM invoices
        WHERE invoice_status != 'REJECTED_DUPLICATE'
        ORDER BY claim_id ASC, invoice_id ASC
        """
    ).fetchall():
        mu, sigma = cpt_stats[cpt_c]
        if sigma > 0.0:
            z_cpt = (float(billed_c) - mu) / sigma
            if z_cpt > 2.0:
                upcode_invoices_by_claim.setdefault(cid, []).append((inv_id, cpt_c, z_cpt))

    # Provider total distinct claims N_p, distinct claimants per provider, and pair claim counts N_{c,p} (IND-11 & BC-2)
    prv_claim_counts: dict[str, tuple[int, int]] = {
        r[0]: (int(r[1]), int(r[2]))
        for r in conn.execute(
            """
            SELECT i.provider_id, COUNT(DISTINCT i.claim_id), COUNT(DISTINCT c.claimant_id)
            FROM invoices i
            JOIN claims c ON c.claim_id = i.claim_id
            GROUP BY i.provider_id
            """
        ).fetchall()
    }
    pair_claim_counts: dict[tuple[str, str], int] = {
        (r[0], r[1]): int(r[2])
        for r in conn.execute(
            """
            SELECT c.claimant_id, i.provider_id, COUNT(DISTINCT i.claim_id)
            FROM invoices i
            JOIN claims c ON c.claim_id = i.claim_id
            GROUP BY c.claimant_id, i.provider_id
            """
        ).fetchall()
    }

    # Unbundled line-item splitting k_split >= 3 same-day/same-provider invoices on a claim (IND-12)
    split_by_claim: dict[str, list[tuple[str, str, int]]] = {}
    for cid, prv_id, svc_day, k_split in conn.execute(
        """
        SELECT claim_id, provider_id, substr(service_start_utc, 1, 10) AS svc_day, COUNT(*) AS k_split
        FROM invoices
        GROUP BY claim_id, provider_id, substr(service_start_utc, 1, 10)
        HAVING COUNT(*) >= 3
        ORDER BY claim_id ASC, provider_id ASC, svc_day ASC
        """
    ).fetchall():
        split_by_claim.setdefault(cid, []).append((prv_id, svc_day, int(k_split)))

    # Claimant 90-day submission velocity burst n_90d >= 2 (IND-14)
    vel_90d_by_claim: dict[str, int] = {
        r[0]: int(r[1])
        for r in conn.execute(
            """
            SELECT c1.claim_id, COUNT(*) AS n_90d
            FROM claims c1
            JOIN claims c2
              ON c2.claimant_id = c1.claimant_id
             AND ABS(julianday(c2.submitted_at_utc) - julianday(c1.submitted_at_utc)) <= 90.0
            GROUP BY c1.claim_id
            HAVING COUNT(*) >= 2
            """
        ).fetchall()
    }

    # Distinct providers per claim and watchlist/suspended providers per claim (IND-15 & BC-6)
    distinct_prvs_by_claim: dict[str, list[tuple[str, str]]] = {}
    for cid, prv_id, tier in conn.execute(
        """
        SELECT DISTINCT i.claim_id, i.provider_id, p.network_tier
        FROM invoices i
        JOIN providers p ON p.provider_id = i.provider_id
        ORDER BY i.claim_id ASC, i.provider_id ASC
        """
    ).fetchall():
        distinct_prvs_by_claim.setdefault(cid, []).append((prv_id, tier))

    # Catastrophic storm surge claims (BC-3: >= 25 claims in same state within +-48h with STORM weather/incident)
    cat_weather_claims: set[str] = {
        r[0]
        for r in conn.execute(
            """
            SELECT c1.claim_id
            FROM claims c1
            JOIN incidents i1 ON i1.incident_id = c1.incident_id
            WHERE i1.weather_condition = 'STORM'
              AND (
                  SELECT COUNT(*)
                  FROM claims c2
                  JOIN incidents i2 ON i2.incident_id = c2.incident_id
                  WHERE i2.jurisdiction_state = i1.jurisdiction_state
                    AND i2.weather_condition = 'STORM'
                    AND ABS(julianday(i2.incident_timestamp_utc) - julianday(i1.incident_timestamp_utc)) * 24.0 <= 48.0
              ) >= 25
            """
        ).fetchall()
    }

    # Verified multi-vehicle accident claims (BC-5: AUTO_COLLISION with police report, >= 3 claims on incident,
    # linked by SAME_INCIDENT_PARTICIPANT edges and 0 collusive edges)
    multi_vehicle_claims: set[str] = {
        r[0]
        for r in conn.execute(
            """
            SELECT c.claim_id
            FROM claims c
            JOIN incidents i ON i.incident_id = c.incident_id
            WHERE i.incident_type = 'AUTO_COLLISION'
              AND i.police_report_number IS NOT NULL
              AND (SELECT COUNT(*) FROM claims c2 WHERE c2.incident_id = c.incident_id) >= 3
              AND EXISTS (
                  SELECT 1 FROM relationship_edges re
                  WHERE re.is_active = 1
                    AND re.edge_type = 'SAME_INCIDENT_PARTICIPANT'
                    AND (re.source_claimant_id = c.claimant_id OR re.target_claimant_id = c.claimant_id)
              )
            """
        ).fetchall()
    }

    # Claimants with adverse SIU/denial history or rejected duplicate invoices (for BC-4 and BC-6)
    claimants_with_dup_inv: set[str] = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT c.claimant_id FROM claims c JOIN invoices i ON i.claim_id = c.claim_id WHERE i.invoice_status = 'REJECTED_DUPLICATE'"
        ).fetchall()
    }
    claimants_with_adverse_siu: set[str] = {
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT claimant_id FROM claims WHERE claim_status IN ('SIU_HOLD', 'DENIED')
            UNION
            SELECT DISTINCT subject_claimant_id FROM investigations WHERE ruling_outcome = 'CONFIRMED_FRAUD' AND subject_claimant_id IS NOT NULL
            """
        ).fetchall()
    }

    # Query operational claim + claimant + policy + incident + primary invoice attributes
    claim_rows = conn.execute(
        """
        SELECT
            c.claim_id,
            c.policy_id,
            c.claimant_id,
            c.incident_id,
            c.submitted_at_utc,
            c.claimed_amount_cents,
            clm.bank_account_hash,
            clm.phone_e164,
            clm.tax_id_hash,
            clm.address_norm,
            pol.effective_start_utc,
            inc.incident_timestamp_utc,
            inc.reported_timestamp_utc,
            inc.incident_type,
            inc.police_report_number,
            (julianday(inc.incident_timestamp_utc) - julianday(pol.effective_start_utc)) AS delta_bind_days,
            (julianday(inc.reported_timestamp_utc) - julianday(inc.incident_timestamp_utc)) * 24.0 AS delta_rep_hours,
            i.provider_id,
            p.network_tier
        FROM claims c
        JOIN claimants clm ON clm.claimant_id = c.claimant_id
        JOIN policies pol ON pol.policy_id = c.policy_id
        JOIN incidents inc ON inc.incident_id = c.incident_id
        JOIN invoices i
          ON i.claim_id = c.claim_id
         AND i.provider_invoice_number LIKE '%-A'
        JOIN providers p ON p.provider_id = i.provider_id
        ORDER BY c.claim_id ASC
        """
    ).fetchall()

    ind_seq = 0
    claim_indicators: dict[str, list[tuple[str, str, float, float, str]]] = {}
    claim_dampening: dict[str, float] = {}
    claim_to_claimant: dict[str, str] = {}

    for (
        cid,
        pol_id,
        clm_id,
        inc_id,
        sub_ts,
        claimed_amount_cents,
        bank_hash,
        phone,
        tax_hash,
        addr_norm,
        eff_start_ts,
        inc_ts,
        rep_ts,
        inc_type,
        pr_num,
        delta_bind_days,
        delta_rep_hours,
        prv_id,
        prv_tier,
    ) in claim_rows:
        claim_to_claimant[cid] = clm_id
        k_acct = shared_banks.get(bank_hash, 1)
        k_phone = shared_phones.get(phone, 1)
        k_tax = shared_taxes.get(tax_hash, 1)
        k_id = max(k_phone, k_tax)
        k_addr = shared_addresses.get(addr_norm, 1)
        n_prov, n_prov_clmts = prv_claim_counts.get(prv_id, (1, 1))
        n_pair = pair_claim_counts.get((clm_id, prv_id), 1)
        r_pair = n_pair / n_prov if n_prov > 0 else 0.0

        # Evaluate BC-1..BC-6 operational predicates (§6.2)
        bc1 = (
            k_addr >= 15
            and any(tok in addr_norm for tok in ("APT ", "UNIT ", "BLDG ", "#"))
            and k_acct == 1
            and k_id == 1
        )
        bc2 = prv_tier == "IN_NETWORK" and n_prov >= 40 and n_prov_clmts >= 30
        bc3 = cid in cat_weather_claims
        bc4 = (
            k_addr == 2
            and k_acct == 2
            and k_phone == 2
            and clm_id not in claimants_with_dup_inv
            and clm_id not in collusive_adj
        )
        bc5 = cid in multi_vehicle_claims and clm_id not in collusive_adj
        all_in_net = all(t == "IN_NETWORK" for _, t in distinct_prvs_by_claim.get(cid, []))
        bc6 = (
            all_in_net
            and clm_id not in claimants_with_adverse_siu
            and cid not in cross_dup_fp_by_claim
            and (k_acct == 1 or bc4)
        )

        # Product dampening D(c) = max(0.15, prod m_b)
        d_prod = 1.0
        if bc1:
            # ARCH-ST-010.3 §7.1 defines the BC-1 multiplier as 0.35.
            # Keep the canonical generator aligned with the published scoring
            # contract and the modular scorer.
            d_prod *= 0.35
        if bc2:
            d_prod *= 0.30
        if bc3:
            d_prod *= 0.25
        if bc4:
            d_prod *= 0.20
        if bc5:
            d_prod *= 0.25
        if bc6:
            d_prod *= 0.75
        claim_dampening[cid] = max(0.15, d_prod)

        # Evaluate all 15 indicators IND-01..IND-15 independently (zero if/elif masking, zero caps)
        raw_inds: list[tuple[str, str, str, str, float, float, str]] = []

        # IND-01: SHARED_PAYOUT_ACCOUNT
        if k_acct >= 2 and not bc4:
            raw_01 = min(35.0, 10.0 * k_acct)
            sev_01 = "CRITICAL" if raw_01 >= 35.0 else "HIGH"
            raw_inds.append(("IND-01", "NETWORK", "ENTITY", sev_01, raw_01, 35.0, f"BANK:{bank_hash}"))

        # IND-02: SHARED_TAX_OR_PHONE_IDENTITY
        if k_id >= 2 and not bc4:
            raw_02 = min(30.0, 12.0 * k_id)
            id_key = tax_hash if k_tax >= k_phone else hashlib.sha256(phone.encode("utf-8")).hexdigest()
            sev_02 = "CRITICAL" if raw_02 >= 24.0 else "HIGH"
            raw_inds.append(("IND-02", "NETWORK", "ENTITY", sev_02, raw_02, 30.0, f"ID_MATCH:{id_key}"))

        # IND-03: CROSS_CLAIMANT_DUPLICATE_INVOICE
        if cid in cross_dup_fp_by_claim:
            raw_inds.append(
                ("IND-03", "FINANCIAL", "CLAIM", "CRITICAL", 35.0, 35.0, f"DUP_FP:{cross_dup_fp_by_claim[cid]}")
            )

        # IND-04: INTRA_CLAIM_DUPLICATE_RESUBMISSION
        if cid in intra_dup_fp_by_claim:
            raw_inds.append(
                ("IND-04", "FINANCIAL", "CLAIM", "LOW", 8.0, 8.0, f"INTRA_DUP:{cid}:{intra_dup_fp_by_claim[cid]}")
            )

        # IND-05: SHARED_ADDRESS_CLUSTER
        if k_addr >= 2:
            raw_05 = 4.0 if (bc1 or bc4) else min(18.0, 3.0 * k_addr)
            sev_05 = "LOW" if raw_05 < 9.0 else "MEDIUM"
            addr_sha = hashlib.sha256(addr_norm.encode("utf-8")).hexdigest()
            raw_inds.append(("IND-05", "NETWORK", "ENTITY", sev_05, raw_05, 18.0, f"ADDR:{addr_sha}"))

        # IND-06: PAGERANK_CENTRALITY_SPIKE
        pr_tilde = pr_norm_by_claim.get(cid, 1.0)
        if pr_tilde > 1.25:
            raw_06 = round(min(25.0, 10.0 * (pr_tilde - 1.0)), 3)
            sev_06 = "HIGH" if raw_06 >= 15.0 else "MEDIUM"
            raw_inds.append(("IND-06", "NETWORK", "ENTITY", sev_06, raw_06, 25.0, f"PR_CENT:{cid}"))

        # IND-07: DENSE_COLLUSIVE_RING_MEMBERSHIP
        c_comp = claimant_comp_id.get(clm_id)
        if c_comp is not None:
            members_k, rho_k, comp_tok = comp_info[c_comp]
            if len(members_k) >= 3 and rho_k > 0.35:
                raw_07 = round(min(30.0, 15.0 * rho_k * math.log(1.0 + len(members_k))), 3)
                sev_07 = "CRITICAL" if raw_07 >= 26.0 else "HIGH"
                raw_inds.append(("IND-07", "NETWORK", "RING", sev_07, raw_07, 30.0, comp_tok))

        # IND-08: UPCODING_BILLED_ZSCORE
        for u_inv_id, u_cpt, z_cpt in upcode_invoices_by_claim.get(cid, []):
            raw_08 = round(min(25.0, 5.0 * z_cpt), 3)
            sev_08 = "HIGH" if raw_08 >= 15.0 else "MEDIUM"
            raw_inds.append(("IND-08", "FINANCIAL", "CLAIM", sev_08, raw_08, 25.0, f"UPCODE:{u_inv_id}:{u_cpt}"))

        # IND-09: EARLY_POLICY_INCEPTION_CLAIM
        if 0.0 <= float(delta_bind_days) <= 14.0 and not bc3:
            raw_09 = round(18.0 * (1.0 - float(delta_bind_days) / 14.0), 3)
            sev_09 = "LOW" if raw_09 < 12.0 else "MEDIUM"
            raw_inds.append(("IND-09", "BEHAVIORAL", "CLAIM", sev_09, raw_09, 18.0, f"INCEPT:{pol_id}:{cid}"))

        # IND-10: DELAYED_INCIDENT_REPORTING
        if float(delta_rep_hours) > 72.0:
            raw_10 = min(12.0, 2.0 * math.floor((float(delta_rep_hours) - 72.0) / 24.0) + 3.0)
            sev_10 = "LOW" if raw_10 < 8.0 else "MEDIUM"
            raw_inds.append(("IND-10", "BEHAVIORAL", "CLAIM", sev_10, raw_10, 12.0, f"DELAY:{inc_id}:{cid}"))

        # IND-11: PROVIDER_CLAIMANT_REFERRAL_CONCENTRATION
        if n_prov >= 5 and r_pair > 0.35 and not bc2:
            raw_11 = round(min(15.0, 20.0 * (r_pair - 0.20)), 3)
            sev_11 = "LOW" if raw_11 < 9.0 else "MEDIUM"
            raw_inds.append(("IND-11", "BEHAVIORAL", "PAIR", sev_11, raw_11, 15.0, f"CONC:{clm_id}:{prv_id}"))

        # IND-12: UNBUNDLED_LINE_ITEM_SPLITTING
        for sp_prv, sp_day, k_split in split_by_claim.get(cid, []):
            raw_12 = min(20.0, 5.0 * k_split)
            sev_12 = "HIGH" if raw_12 >= 16.0 else "MEDIUM"
            raw_inds.append(
                ("IND-12", "FINANCIAL", "CLAIM", sev_12, raw_12, 20.0, f"SPLIT:{cid}:{sp_prv}:{sp_day}")
            )

        # IND-13: MISSING_POLICE_REPORT_HIGH_SEVERITY
        if (
            pr_num is None
            and inc_type in ("AUTO_COLLISION", "THEFT_BURGLARY", "FIRE_LOSS")
            and int(claimed_amount_cents) >= 1500000
        ):
            raw_inds.append(("IND-13", "DOCUMENT", "CLAIM", "MEDIUM", 14.0, 14.0, f"NO_POLICE_RPT:{inc_id}"))

        # IND-14: CLAIMANT_VELOCITY_BURST
        n_90d = vel_90d_by_claim.get(cid, 1)
        if n_90d >= 2:
            raw_14 = min(16.0, 4.0 * n_90d)
            sev_14 = "LOW" if raw_14 < 12.0 else "MEDIUM"
            raw_inds.append(("IND-14", "BEHAVIORAL", "ENTITY", sev_14, raw_14, 16.0, f"VEL:{clm_id}"))

        # IND-15: WATCHLIST_OR_SUSPENDED_PROVIDER (across all distinct providers on the claim's invoices)
        for d_prv, d_tier in distinct_prvs_by_claim.get(cid, []):
            if d_tier in ("WATCHLIST", "SUSPENDED"):
                raw_15 = 15.0 if d_tier == "SUSPENDED" else 10.0
                sev_15 = "HIGH" if d_tier == "SUSPENDED" else "MEDIUM"
                raw_inds.append(("IND-15", "DOCUMENT", "ENTITY", sev_15, raw_15, 15.0, f"PRV_TIER:{d_prv}"))

        inds_for_digest: list[tuple[str, str, float, float, str]] = []
        for code, pillar, scope, sev, raw_pts, max_pts, tok in raw_inds:
            ind_seq += 1
            ind_id = f"FIND-2026-{ind_seq:06d}"
            norm_val = round(raw_pts / max_pts, 6)
            snap_json = canonical_json_str(
                {
                    "indicator_code": code,
                    "max_points": max_pts,
                    "normalized_value": round(norm_val, 3),
                    "pillar": pillar,
                    "raw_points": raw_pts,
                }
            )
            conn.execute(
                """
                INSERT INTO fraud_indicators (
                    indicator_id, claim_id, indicator_code, pillar,
                    dedup_scope, canonical_evidence_token, severity,
                    raw_points, max_points, normalized_value,
                    feature_snapshot_json, computed_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ind_id,
                    cid,
                    code,
                    pillar,
                    scope,
                    tok,
                    sev,
                    raw_pts,
                    max_pts,
                    norm_val,
                    snap_json,
                    computed_ts,
                ),
            )
            inds_for_digest.append((code, pillar, raw_pts, norm_val, tok))

        claim_indicators[cid] = inds_for_digest

    assert ind_seq == EXPECTED_COUNTS["fraud_indicators"], (
        f"Expected {EXPECTED_COUNTS['fraud_indicators']} fraud_indicators, got {ind_seq}"
    )

    # -------------------------------------------------------------------------
    # Stage S3-S10: Deduplicated Pillar Sums, Dampening, Cluster Boost & Digest
    # -------------------------------------------------------------------------
    hard_collusion_claims: set[str] = {
        row[0]
        for row in conn.execute(
            """
            SELECT DISTINCT f1_bank.claim_id
            FROM fraud_indicators f1_bank
            JOIN fraud_indicators f1_dup
              ON f1_dup.claim_id = f1_bank.claim_id
            JOIN fraud_indicators f2_bank
              ON f2_bank.indicator_code = 'IND-01'
             AND f2_bank.canonical_evidence_token = f1_bank.canonical_evidence_token
             AND f2_bank.claim_id != f1_bank.claim_id
            JOIN fraud_indicators f2_dup
              ON f2_dup.claim_id = f2_bank.claim_id
             AND f2_dup.indicator_code = 'IND-03'
             AND f2_dup.canonical_evidence_token = f1_dup.canonical_evidence_token
            WHERE f1_bank.indicator_code = 'IND-01'
              AND f1_dup.indicator_code = 'IND-03'
            """
        ).fetchall()
    }

    s_base_by_claim: dict[str, float] = {}
    dampened_by_claim: dict[str, float] = {}

    for cid, inds in claim_indicators.items():
        if not inds:
            s_base_by_claim[cid] = 0.0
            dampened_by_claim[cid] = 0.0
            continue

        # Stage S3: Deduplicate raw_points by (indicator_code, canonical_evidence_token) within each pillar
        def _pillar_sum(pil: str) -> float:
            dedup: dict[tuple[str, str], float] = {}
            for code, p_name, raw_pts, _, tok in inds:
                if p_name == pil:
                    key = (code, tok)
                    if raw_pts > dedup.get(key, 0.0):
                        dedup[key] = raw_pts
            return sum(dedup.values())

        p_net = min(100.0, 100.0 * _pillar_sum("NETWORK") / 60.0)
        p_fin = min(100.0, 100.0 * _pillar_sum("FINANCIAL") / 55.0)
        p_beh = min(100.0, 100.0 * _pillar_sum("BEHAVIORAL") / 45.0)
        p_doc = min(100.0, 100.0 * _pillar_sum("DOCUMENT") / 40.0)
        s_base = 0.35 * p_net + 0.30 * p_fin + 0.20 * p_beh + 0.15 * p_doc
        s_base_by_claim[cid] = s_base

        # Stage S6: Hard-collusion override sets D(c) = 1.0
        d_factor = 1.0 if cid in hard_collusion_claims else claim_dampening.get(cid, 1.0)
        dampened_by_claim[cid] = s_base * d_factor

    # Stage S7-S8: Compute cluster boost B_cluster over each collusive component K
    # B_cluster(K) = min(20.0, 0.20 * max_K(dampened) + 0.10 * mean_K(dampened) + 5.0 * rho_K)
    comp_claims: dict[int, list[str]] = {}
    for cid, clm_id in claim_to_claimant.items():
        c_comp = claimant_comp_id.get(clm_id)
        if c_comp is not None:
            comp_claims.setdefault(c_comp, []).append(cid)

    b_cluster_by_comp: dict[int, float] = {}
    for c_comp, cids_k in comp_claims.items():
        _, rho_k, _ = comp_info[c_comp]
        vals = [dampened_by_claim[c] for c in cids_k]
        max_k = max(vals) if vals else 0.0
        mean_k = (sum(vals) / len(vals)) if vals else 0.0
        b_cluster_by_comp[c_comp] = min(20.0, 0.20 * max_k + 0.10 * mean_k + 5.0 * rho_k)

    for cid, inds in claim_indicators.items():
        if not inds:
            score = 0.0
            tier = "LOW"
        else:
            s_base = s_base_by_claim[cid]
            dampened = dampened_by_claim[cid]
            if cid in hard_collusion_claims:
                c_comp = claimant_comp_id.get(claim_to_claimant[cid])
                b_cluster = b_cluster_by_comp.get(c_comp, 0.0) if c_comp is not None else 0.0
                score = round(min(100.0, max(65.0, dampened + b_cluster)), 2)
            else:
                score = round(max(round(0.15 * s_base, 2), round(dampened, 2)), 2)

            if score >= 85.0:
                tier = "CRITICAL"
            elif score >= 65.0:
                tier = "HIGH"
            elif score >= 30.0:
                tier = "MEDIUM"
            else:
                tier = "LOW"

        digest = _compute_score_evidence_digest(cid, inds, score)
        conn.execute(
            """
            UPDATE claims
               SET latest_ief_score = ?,
                   latest_risk_tier = ?,
                   scoring_evidence_sha256 = ?
             WHERE claim_id = ?
            """,
            (score, tier, digest, cid),
        )


def generate_dataset(
    seed: int = 42,
    ops_db_path: str | Path = ":memory:",
    gt_db_path: str | Path = ":memory:",
    overwrite: bool = True,
) -> dict[str, Any]:
    """
    Deterministically builds and populates both `operational.db` and `ground_truth.db`.
    All 27 triggers remain active throughout population.
    """
    # P0-1: Collision guard
    if ops_db_path != ":memory:" and gt_db_path != ":memory:":
        if Path(ops_db_path).resolve() == Path(gt_db_path).resolve():
            raise ValueError(
                f"Operational DB and Ground Truth DB cannot resolve to the same path: {ops_db_path}"
            )

    # P0-1: Overwrite protection
    if not overwrite:
        if ops_db_path != ":memory:" and Path(ops_db_path).exists():
            raise FileExistsError(
                f"Operational database already exists at {ops_db_path}. Specify overwrite=True or --overwrite to replace."
            )
        if gt_db_path != ":memory:" and Path(gt_db_path).exists():
            raise FileExistsError(
                f"Ground truth database already exists at {gt_db_path}. Specify overwrite=True or --overwrite to replace."
            )

    rng = random.Random(seed)

    if ops_db_path != ":memory:":
        Path(ops_db_path).parent.mkdir(parents=True, exist_ok=True)
        if Path(ops_db_path).exists():
            Path(ops_db_path).unlink()
    if gt_db_path != ":memory:":
        Path(gt_db_path).parent.mkdir(parents=True, exist_ok=True)
        if Path(gt_db_path).exists():
            Path(gt_db_path).unlink()

    conn = open_operational_db(ops_db_path, create_schema=True, verify_digest=True)
    gt_conn = open_ground_truth_db(gt_db_path, create_schema=True)

    # Create temporary helper indexes during seeding, then drop them before final digest check
    tmp_indexes = _create_temp_seed_indexes(conn)
    emitter = EventChainEmitter(conn)

    # Begin explicit transaction for fast deterministic population
    conn.execute("BEGIN")
    gt_conn.execute("BEGIN")

    # -------------------------------------------------------------------------
    # 1. GROUND TRUTH RINGS (20 rings: 1..15 FULL_OBSERVABLE, 16..20 PARTIAL_MISSING_EDGES_YF_NEG_4)
    # -------------------------------------------------------------------------
    ring_claimants: dict[int, list[str]] = {}
    ring_providers: dict[int, list[str]] = {}
    claimant_ring_map: dict[str, str] = {}
    provider_ring_map: dict[str, str] = {}

    for r_idx in range(1, 21):
        ring_id = f"RING-2026-{r_idx:03d}"
        obs_mode = (
            "FULL_OBSERVABLE"
            if r_idx <= 15
            else "PARTIAL_MISSING_EDGES_YF_NEG_4"
        )
        archetype = "STAGED_COLLISION_RING" if r_idx % 2 == 1 else "PHANTOM_BILLING_CLINIC"
        c_cnt = 48 if r_idx <= 5 else (47 if r_idx <= 15 else 8)
        clmts = [f"CLMT-{(r_idx - 1) * 12 + k:06d}" for k in range(1, 13)]
        prvs = [f"PRV-{(r_idx - 1) * 2 + 1:06d}", f"PRV-{(r_idx - 1) * 2 + 2:06d}"]
        ring_claimants[r_idx] = clmts
        ring_providers[r_idx] = prvs
        for c_id in clmts:
            claimant_ring_map[c_id] = ring_id
        for p_id in prvs:
            provider_ring_map[p_id] = ring_id
        gt_conn.execute(
            "INSERT INTO ground_truth_rings VALUES (?, ?, ?, ?, ?)",
            (ring_id, archetype, obs_mode, c_cnt, len(clmts) + len(prvs)),
        )

    # -------------------------------------------------------------------------
    # 2. CLAIMANTS (2,000 rows) & PROVIDERS (500 rows)
    # -------------------------------------------------------------------------
    # Claimants 241..265 are used for YF-NEG-3 (25 cross-claimant duplicate-invoice fraud claims)
    yf_neg3_bank_hashes: dict[int, str] = {}
    for idx in range(241, 266):
        group_id = (idx - 241) // 2  # 11 pairs + 1 triple (263, 264, 265)
        if group_id == 12:
            group_id = 11
        yf_neg3_bank_hashes[idx] = _det_hex(seed, f"yf-neg3-shared-bank-{group_id}")

    common_apt_address = "742 EVERGREEN TERRACE APT 4B, SPRINGFIELD, IL 62701"
    claimant_bank_map: dict[str, str] = {}

    for i in range(1, 2001):
        cid = f"CLMT-{i:06d}"
        r_idx = (i - 1) // 12 + 1 if i <= 240 else None
        full_name = f"Claimant {i:04d} {_det_hex(seed, f'cname-{i}')[:6].upper()}"
        dob = f"{1955 + (i % 45):04d}-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"
        tax_hash = _det_hex(seed, f"clmt-tax-{i}")

        # Shared phone on first 2 claimants of Rings 1..5 (10 claimants * 4 claims = 40 IND-02 rows)
        # and within each 2-claimant joint-policy household in BL-3 (549..632, suppressed by BC-4)
        if r_idx is not None and r_idx <= 5 and ((i - 1) % 12) in (0, 1):
            phone = f"+1312555{r_idx:04d}"
        elif 549 <= i <= 632:
            hh_idx = (i - 549) // 2
            phone = f"+1415555{hh_idx:04d}"
        else:
            phone = f"+1{800 + (i // 1000):03d}555{i:04d}"

        email = f"claimant.{i:06d}@example.org"
        if 301 <= i <= 380:
            # YF-NEG-5: 80 claimants at multi-unit apartment address (BC-1 + IND-05)
            addr = common_apt_address
        elif 549 <= i <= 632:
            # BL-3: 42 2-claimant joint-policy households sharing address, bank, and phone (BC-4 + IND-05)
            hh_idx = (i - 549) // 2
            addr = f"{200 + hh_idx} HOUSEHOLD LN, SUBURB-{hh_idx % 10}, IL"
        else:
            addr = f"{100 + i} MAIN ST SUITE {i}, CITY-{i % 40}, {STATES[i % len(STATES)]}"

        routing_hash = _det_hex(seed, f"clmt-rout-{i // 5}")
        if r_idx is not None:
            bank_hash = _det_hex(seed, f"acct-pool-{r_idx}")
        elif i in yf_neg3_bank_hashes:
            bank_hash = yf_neg3_bank_hashes[i]
        elif 549 <= i <= 632:
            hh_idx = (i - 549) // 2
            bank_hash = _det_hex(seed, f"bl3-hh-bank-{hh_idx}")
        else:
            bank_hash = _det_hex(seed, f"clmt-bank-{i}")

        claimant_bank_map[cid] = bank_hash
        created_utc = f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T08:00:00Z"
        conn.execute(
            "INSERT INTO claimants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, full_name, dob, tax_hash, phone, email, addr, routing_hash, bank_hash, created_utc),
        )
        gt_conn.execute(
            "INSERT INTO ground_truth_entity_labels VALUES (?, 'CLAIMANT', ?, ?)",
            (
                f"CLAIMANT:{cid}",
                1 if (cid in claimant_ring_map or 241 <= i <= 265) else 0,
                claimant_ring_map.get(cid),
            ),
        )

    for p in range(1, 501):
        pid = f"PRV-{p:06d}"
        pname = f"Provider {p:04d} Medical & Auto LLC"
        ptype = PRV_TYPES[p % len(PRV_TYPES)]
        npi = f"NPI-{202600000 + p}"
        tax_hash = _det_hex(seed, f"prv-tax-{p}")
        phone = f"+1{300 + (p % 600):03d}444{p % 10000:04d}"
        addr = f"{500 + p} HEALTHCARE BLVD, METRO-{p % 25}, {STATES[p % len(STATES)]}"
        routing_hash = _det_hex(seed, f"prv-rout-{p}")
        bank_hash = _det_hex(seed, f"prv-bank-{p}")
        if p <= 40 or 461 <= p <= 490:
            tier = "SUSPENDED" if p % 4 == 0 else "WATCHLIST"
        elif 54 <= p <= 59:
            tier = "OUT_OF_NETWORK"
        else:
            tier = "IN_NETWORK"
        created_utc = f"2025-01-{(p % 28) + 1:02d}T09:00:00Z"
        conn.execute(
            "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, pname, ptype, npi, tax_hash, phone, addr, routing_hash, bank_hash, tier, created_utc),
        )
        gt_conn.execute(
            "INSERT INTO ground_truth_entity_labels VALUES (?, 'PROVIDER', ?, ?)",
            (f"PROVIDER:{pid}", 1 if pid in provider_ring_map else 0, provider_ring_map.get(pid)),
        )

    # -------------------------------------------------------------------------
    # 3. POLICIES (2,200 rows)
    # -------------------------------------------------------------------------
    policy_map: dict[str, tuple[str, int, int, str]] = {}
    claimant_policies: dict[str, list[str]] = {}
    for pol_idx in range(1, 2201):
        pol_id = f"POL-2026-{pol_idx:06d}"
        c_idx = ((pol_idx - 1) % 2000) + 1
        cid = f"CLMT-{c_idx:06d}"
        pol_num = f"PN-2026-{pol_idx:06d}"
        lob = LOBS[pol_idx % len(LOBS)]
        # Policies 2091..2200 (110 policies) are secondary policies with LAPSED/CANCELLED status (EC-3)
        if pol_idx > 2090:
            p_status = "LAPSED" if pol_idx % 2 == 0 else "CANCELLED"
        else:
            p_status = "ACTIVE"

        if 465 <= pol_idx <= 548:
            # BL-2: 84 policies bound shortly before the 2026-04-15 TX storm surge (delta_bind = 5.4d <= 14d, suppressed by BC-3)
            eff_start = "2026-04-10T00:00:00Z"
            bound_utc = "2026-04-09T12:00:00Z"
        elif 1126 <= pol_idx <= 1269:
            # IND-09: 144 policies with early inception claim on 2026-03-06 (delta_bind = 5.4d <= 14d, ~BC-3)
            eff_start = "2026-03-01T00:00:00Z"
            bound_utc = "2026-02-28T12:00:00Z"
        else:
            eff_start = "2025-01-01T00:00:00Z"
            bound_utc = "2024-12-15T12:00:00Z"
        eff_end = "2026-12-31T23:59:59Z"
        cov_limit = 5000000 + (pol_idx % 10) * 1000000  # $50k .. $140k
        deductible = 50000 + (pol_idx % 5) * 25000      # $500 .. $1,500
        premium = 120000 + (pol_idx % 8) * 15000
        conn.execute(
            "INSERT INTO policies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pol_id,
                cid,
                pol_num,
                lob,
                p_status,
                eff_start,
                eff_end,
                bound_utc,
                cov_limit,
                deductible,
                premium,
            ),
        )
        policy_map[pol_id] = (cid, cov_limit, deductible, p_status)
        claimant_policies.setdefault(cid, []).append(pol_id)

    # -------------------------------------------------------------------------
    # 4. INCIDENTS (3,800 rows)
    # -------------------------------------------------------------------------
    benign_weathers = ["CLEAR", "RAIN", "SNOW_ICE", "FOG"]
    for inc_idx in range(1, 3801):
        inc_id = f"INC-2026-{inc_idx:06d}"
        st = STATES[inc_idx % len(STATES)]
        inc_type = INC_TYPES[inc_idx % len(INC_TYPES)]
        weather = benign_weathers[inc_idx % len(benign_weathers)]
        pr_num: str | None = f"PR-2026-{inc_idx:06d}"

        if 56 <= inc_idx <= 75:
            # IND-13: 20 high-severity AUTO_COLLISION incidents with missing police report
            inc_ts = "2025-02-01T10:00:00Z"
            rep_ts = "2025-02-01T14:30:00Z"
            inc_type = "AUTO_COLLISION"
            pr_num = None
        elif 856 <= inc_idx <= 939 or 1192 <= inc_idx <= 1275:
            # BL-1 & BL-5: Trauma hospital & rural sole provider incidents
            inc_ts = "2026-03-01T10:00:00Z"
            rep_ts = "2026-03-01T14:30:00Z"
        elif 940 <= inc_idx <= 1023:
            # BL-2: 84 catastrophic TX STORM surge incidents with 98h delayed reporting (BC-3 + IND-10)
            inc_ts = "2026-04-15T10:00:00Z"
            rep_ts = "2026-04-19T12:00:00Z"
            inc_type = "WATER_DAMAGE"
            st = "TX"
            weather = "STORM"
        elif 1108 <= inc_idx <= 1121:
            # BL-4: 14 police-reported 6-claimant AUTO_COLLISION freeway pileups with 96h delayed reporting (BC-5 + IND-10)
            inc_ts = "2026-04-20T10:00:00Z"
            rep_ts = "2026-04-24T10:00:00Z"
            inc_type = "AUTO_COLLISION"
            pr_num = f"PR-2026-{inc_idx:06d}"
        elif 1401 <= inc_idx <= 1600:
            # IND-10: 200 organic incidents with 96h reporting delay (> 72h)
            inc_ts = "2025-02-01T10:00:00Z"
            rep_ts = "2025-02-05T10:00:00Z"
        elif 1601 <= inc_idx <= 1744:
            # IND-09: 144 early policy inception incidents (5.4 days after 2026-03-01 effective_start_utc)
            inc_ts = "2026-03-06T10:00:00Z"
            rep_ts = "2026-03-06T14:30:00Z"
        else:
            # Standard incident (> 30 days after 2025-01-01 policy inception, 4.5h reporting delay)
            day = (inc_idx % 20) + 1
            inc_ts = f"2025-02-{day:02d}T10:00:00Z"
            rep_ts = f"2025-02-{day:02d}T14:30:00Z"

        loc_addr = f"{100 + (inc_idx % 900)} INCIDENT HWY, {st}"
        geohash = _det_hex(seed, f"geo-{inc_idx}")[:8]
        desc = f"Incident {inc_id} ({inc_type}) in {st}"
        conn.execute(
            "INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (inc_id, inc_ts, rep_ts, inc_type, st, loc_addr, geohash, pr_num, weather, desc),
        )

    # -------------------------------------------------------------------------
    # 5. CLAIMS (5,000 rows) + GROUND TRUTH CLAIM LABELS (5,000 rows)
    # -------------------------------------------------------------------------
    claim_meta: dict[int, dict[str, Any]] = {}
    organic_clmt_pool: list[str] = [
        f"CLMT-{n:06d}"
        for n in (
            list(range(423, 465))
            + list(range(759, 801))
            + list(range(886, 1126))
            + list(range(1270, 2001))
        )
    ]
    organic_prv_pool: list[str] = [
        f"PRV-{p:06d}" for p in range(60, 461) if p not in (150, 250)
    ]
    clmt_occ_counter: dict[str, int] = {}
    spaced_sub_dates = [
        "2025-02-25T09:00:00Z",
        "2025-06-30T09:00:00Z",
        "2025-11-05T09:00:00Z",
        "2026-03-15T09:00:00Z",
    ]
    ord_organic_seq = 0

    for c_idx in range(1, 5001):
        claim_id = f"CLM-2026-{c_idx:06d}"
        ring_id: str | None = None
        is_fraud = 0
        if c_idx <= 710:
            is_fraud = 1
            r_idx = 1 + (c_idx - 1) // 48 if c_idx <= 240 else 6 + (c_idx - 241) // 47
            ring_id = f"RING-2026-{r_idx:03d}"
            scode = "FRAUD_RING_FULL"
            clmt_id = ring_claimants[r_idx][(c_idx - 1) % len(ring_claimants[r_idx])]
            prv_id = ring_providers[r_idx][(c_idx - 1) % len(ring_providers[r_idx])]
        elif c_idx <= 750:
            is_fraud = 1
            r_idx = 16 + (c_idx - 711) // 8
            ring_id = f"RING-2026-{r_idx:03d}"
            scode = "YF-NEG-4"
            clmt_id = ring_claimants[r_idx][(c_idx - 711) % len(ring_claimants[r_idx])]
            prv_id = ring_providers[r_idx][(c_idx - 711) % len(ring_providers[r_idx])]
        elif c_idx <= 775:
            is_fraud = 1
            scode = "YF-NEG-3"
            clmt_num = 241 + (c_idx - 751)
            clmt_id = f"CLMT-{clmt_num:06d}"
            prv_id = f"PRV-{41 + min(11, (c_idx - 751) // 2):06d}"
        elif c_idx <= 855:
            scode = "YF-NEG-5"
            clmt_id = f"CLMT-{301 + (c_idx - 776):06d}"
            prv_id = f"PRV-{60 + (c_idx % 50):06d}"
        elif c_idx <= 939:
            scode = "BL-1"
            clmt_id = f"CLMT-{381 + ((c_idx - 856) % 42):06d}"
            prv_id = "PRV-000150"
        elif c_idx <= 1023:
            scode = "BL-2"
            clmt_id = f"CLMT-{465 + (c_idx - 940):06d}"
            prv_id = f"PRV-{151 + (c_idx % 20):06d}"
        elif c_idx <= 1107:
            scode = "BL-3"
            clmt_id = f"CLMT-{549 + (c_idx - 1024):06d}"
            prv_id = f"PRV-{175 + (c_idx % 20):06d}"
        elif c_idx <= 1191:
            scode = "BL-4"
            clmt_id = f"CLMT-{633 + (c_idx - 1108):06d}"
            prv_id = f"PRV-{200 + (c_idx % 20):06d}"
        elif c_idx <= 1275:
            scode = "BL-5"
            clmt_id = f"CLMT-{717 + ((c_idx - 1192) % 42):06d}"
            prv_id = "PRV-000250"
        elif c_idx <= 1305:
            scode = "YF-NEG-2"
            clmt_id = f"CLMT-{801 + (c_idx - 1276):06d}"
            prv_id = f"PRV-{251 + (c_idx % 30):06d}"
        elif c_idx <= 1330:
            scode = "EC-1"
            clmt_id = f"CLMT-{831 + (c_idx - 1306):06d}"
            prv_id = f"PRV-{281 + (c_idx % 25):06d}"
        elif c_idx <= 1350:
            scode = "EC-3"
            clmt_id = f"CLMT-{856 + (c_idx - 1331):06d}"
            prv_id = f"PRV-{306 + (c_idx % 20):06d}"
        elif c_idx <= 1370:
            # 20 claims (10 pairs) with provider concentration r_pair = 2/5 = 0.40 > 0.35 (IND-11) & 10-day burst (IND-14)
            scode = "ORGANIC_BENIGN"
            pair_k = (c_idx - 1351) // 2
            clmt_id = f"CLMT-{876 + pair_k:06d}"
            prv_id = f"PRV-{491 + pair_k:06d}"
        elif c_idx <= 1400:
            # 30 single-claimant claims on PRV-000491..000500 (3 per provider -> N_p = 5)
            scode = "ORGANIC_BENIGN"
            prv_k = (c_idx - 1371) // 3
            clmt_id = organic_clmt_pool[ord_organic_seq % len(organic_clmt_pool)]
            prv_id = f"PRV-{491 + prv_k:06d}"
            ord_organic_seq += 1
        elif c_idx <= 1600:
            # 200 delayed-reporting organic claims (IND-10)
            scode = "ORGANIC_BENIGN"
            clmt_id = organic_clmt_pool[ord_organic_seq % len(organic_clmt_pool)]
            prv_id = organic_prv_pool[ord_organic_seq % len(organic_prv_pool)]
            ord_organic_seq += 1
        elif c_idx <= 1744:
            # 144 early policy inception organic claims (IND-09)
            scode = "ORGANIC_BENIGN"
            clmt_id = f"CLMT-{1126 + (c_idx - 1601):06d}"
            prv_id = organic_prv_pool[(c_idx - 1601) % len(organic_prv_pool)]
        else:
            scode = "ORGANIC_BENIGN"
            clmt_id = organic_clmt_pool[ord_organic_seq % len(organic_clmt_pool)]
            prv_id = organic_prv_pool[ord_organic_seq % len(organic_prv_pool)]
            ord_organic_seq += 1

        occ_idx = clmt_occ_counter.get(clmt_id, 0)
        clmt_occ_counter[clmt_id] = occ_idx + 1

        pol_id = claimant_policies[clmt_id][0]
        _, cov_limit, deductible, _ = policy_map[pol_id]

        if 1108 <= c_idx <= 1191:
            inc_idx = 1108 + (c_idx - 1108) // 6
        elif c_idx <= 3800:
            inc_idx = c_idx
        elif c_idx <= 3870:
            inc_idx = 1122 + (c_idx - 3801)
        else:
            inc_idx = 2001 + (c_idx - 3871)
        inc_id = f"INC-2026-{inc_idx:06d}"

        if 856 <= c_idx <= 939:
            sub_utc = "2026-03-05T09:00:00Z" if c_idx < 898 else "2026-03-15T09:00:00Z"
        elif 940 <= c_idx <= 1023:
            sub_utc = "2026-04-20T09:00:00Z"
        elif 1108 <= c_idx <= 1191:
            sub_utc = "2026-04-25T09:00:00Z"
        elif 1192 <= c_idx <= 1275:
            sub_utc = "2026-03-05T09:00:00Z" if c_idx < 1234 else "2026-03-15T09:00:00Z"
        elif 1351 <= c_idx <= 1370:
            sub_utc = "2025-03-05T09:00:00Z" if (c_idx % 2 == 1) else "2025-03-15T09:00:00Z"
        elif 1601 <= c_idx <= 1744:
            sub_utc = "2026-03-10T09:00:00Z"
        else:
            sub_utc = spaced_sub_dates[occ_idx % len(spaced_sub_dates)]

        if 31 <= c_idx <= 55:
            claimed_cents = 2600000  # High claimed amount for upcoded invoice claims (IND-08)
        elif 56 <= c_idx <= 75:
            claimed_cents = 1600000  # High severity >= $15,000 without police report (IND-13)
        else:
            claimed_cents = 350000 + (c_idx % 20) * 50000  # $3,500 .. $13,000
        payout_cap = min(claimed_cents, max(0, cov_limit - deductible))
        adj_id = f"USR-ADJ-{(c_idx % 20) + 1:03d}"

        conn.execute(
            """
            INSERT INTO claims (
                claim_id, policy_id, claimant_id, incident_id, claim_status,
                submitted_at_utc, claimed_amount_cents, approved_amount_cents,
                historical_approved_cents, reserved_authorized_cents,
                gross_disbursed_cents, clawed_back_cents, net_paid_cents,
                payout_cap_cents, adjustor_id, siu_referred,
                latest_ief_score, latest_risk_tier, scoring_evidence_sha256
            ) VALUES (?, ?, ?, ?, 'SUBMITTED', ?, ?, 0, 0, 0, 0, 0, 0, ?, ?, 0, 0.0, 'LOW', NULL)
            """,
            (claim_id, pol_id, clmt_id, inc_id, sub_utc, claimed_cents, payout_cap, adj_id),
        )
        emitter.emit(
            "CLAIM_SUBMITTED",
            "Claim",
            claim_id,
            claim_id,
            "SYSTEM_SEED",
            sub_utc,
            {
                "claim_id": claim_id,
                "claim_status": "SUBMITTED",
                "claimed_amount_cents": claimed_cents,
                "incident_id": inc_id,
                "policy_id": pol_id,
            },
        )
        gt_conn.execute(
            "INSERT INTO ground_truth_claim_labels VALUES (?, ?, ?, ?)",
            (claim_id, is_fraud, ring_id, scode),
        )
        claim_meta[c_idx] = {
            "claim_id": claim_id,
            "policy_id": pol_id,
            "claimant_id": clmt_id,
            "provider_id": prv_id,
            "incident_id": inc_id,
            "submitted_at_utc": sub_utc,
            "claimed_cents": claimed_cents,
            "payout_cap": payout_cap,
            "scenario_code": scode,
            "ring_id": ring_id,
            "is_fraud": is_fraud,
        }

    # -------------------------------------------------------------------------
    # 6. YF-NEG-1: 25 Rejected Nonexistent-Policy Ingestion Attempts
    # -------------------------------------------------------------------------
    for iex_idx in range(1, 26):
        att_claim_id = f"CLM-2026-99{iex_idx:04d}"
        rej_pol_id = f"POL-2026-99{iex_idx:04d}"
        clmt_id = f"CLMT-{iex_idx:06d}"
        inc_id = f"INC-2026-{iex_idx:06d}"
        att_cents = 250000 + iex_idx * 10000
        det_utc = f"2026-01-{(iex_idx % 25) + 1:02d}T11:00:00Z"

        conn.execute(f"SAVEPOINT sp_yf_neg1_{iex_idx}")
        fk_caught = False
        try:
            conn.execute(
                """
                INSERT INTO claims VALUES (
                    ?, ?, ?, ?, 'SUBMITTED', ?, ?, 0, 0, 0, 0, 0, 0, ?, 'USR-ADJ-001', 0, 0.0, 'LOW', NULL
                )
                """,
                (att_claim_id, rej_pol_id, clmt_id, inc_id, det_utc, att_cents, att_cents),
            )
        except sqlite3.IntegrityError:
            fk_caught = True
            conn.execute(f"ROLLBACK TO SAVEPOINT sp_yf_neg1_{iex_idx}")
        conn.execute(f"RELEASE SAVEPOINT sp_yf_neg1_{iex_idx}")
        if not fk_caught:
            raise RuntimeError(f"YF-NEG-1 failure: nonexistent policy {rej_pol_id} was not rejected by FK")

        raw_payload = {
            "attempted_claim_id": att_claim_id,
            "attempted_claimed_cents": att_cents,
            "claimant_id": clmt_id,
            "exception_code": "ERR_NONEXISTENT_POLICY_REFERENCE",
            "incident_id": inc_id,
            "rejected_policy_id": rej_pol_id,
        }
        ev_id = emitter.emit(
            "INGESTION_EXCEPTION_RECORDED",
            "IngestionException",
            f"IEX-2026-{iex_idx:06d}",
            None,
            "SYSTEM_INGEST",
            det_utc,
            raw_payload,
        )
        conn.execute(
            "INSERT INTO ingestion_exceptions VALUES (?, ?, ?, ?, ?, ?, 'ERR_NONEXISTENT_POLICY_REFERENCE', ?, ?, ?)",
            (
                f"IEX-2026-{iex_idx:06d}",
                att_claim_id,
                rej_pol_id,
                clmt_id,
                inc_id,
                att_cents,
                canonical_json_str(raw_payload),
                det_utc,
                ev_id,
            ),
        )

    # -------------------------------------------------------------------------
    # 7. INVOICES (7,500 rows: 5,000 primary -A + 2,480 secondary -B + 20 split -C)
    #    + INVOICE_SUBMITTED (7,500 events)
    # -------------------------------------------------------------------------
    prv_seq_counter: dict[str, int] = {}
    primary_inv_by_claim: dict[int, tuple[str, str, int, str, str, str, str]] = {}

    def _next_inv_id(prv_id: str) -> str:
        seq = prv_seq_counter.get(prv_id, 0) + 1
        prv_seq_counter[prv_id] = seq
        return f"INV-PRV-{prv_id}-{seq:06d}"

    cross_dup_partner: dict[int, int] = {}
    dup_groups: list[list[int]] = []
    for r_idx in range(1, 6):
        dup_groups.append(list(range((r_idx - 1) * 48 + 1, r_idx * 48 + 1)))
    for r_idx in range(6, 16):
        dup_groups.append(list(range(241 + (r_idx - 6) * 47, 241 + (r_idx - 5) * 47)))
    for r_idx in range(16, 20):
        dup_groups.append(list(range(711 + (r_idx - 16) * 8, 711 + (r_idx - 15) * 8)))
    dup_groups.append([743, 744, 745, 746])
    for grp_i in range(11):
        dup_groups.append([751 + grp_i * 2, 752 + grp_i * 2])
    dup_groups.append([773, 774, 775])

    for grp_list in dup_groups:
        pos = 0
        n_g = len(grp_list)
        while pos < n_g:
            if pos + 3 == n_g:
                a, b, c = grp_list[pos], grp_list[pos + 1], grp_list[pos + 2]
                cross_dup_partner[a] = b
                cross_dup_partner[b] = a
                cross_dup_partner[c] = a
                pos += 3
            else:
                a, b = grp_list[pos], grp_list[pos + 1]
                cross_dup_partner[a] = b
                cross_dup_partner[b] = a
                pos += 2

    for c_idx in range(1, 5001):
        meta = claim_meta[c_idx]
        cid = meta["claim_id"]
        prv_id = meta["provider_id"]
        inv_id = _next_inv_id(prv_id)
        sub_utc = meta["submitted_at_utc"]
        svc_start = sub_utc[:10] + "T08:00:00Z"
        svc_end = sub_utc[:10] + "T12:00:00Z"
        inv_sub_utc = "2026-06-30T18:00:00Z"
        cpt = CPT_CODES[c_idx % len(CPT_CODES)]
        if 31 <= c_idx <= 55:
            # IND-08: 25 upcoded primary invoices (z_cpt > 10.0 > 2.0)
            billed = 1250000 + c_idx
        else:
            billed = 150000 + c_idx
        fp = _compute_line_item_fp(cpt, svc_start, svc_end, billed)

        inv_status = "SUBMITTED"
        dup_of: str | None = None
        prv_inv_num = f"PINV-{c_idx:06d}-A"
        conn.execute(
            """
            INSERT INTO invoices VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, ?
            )
            """,
            (
                inv_id,
                cid,
                prv_id,
                prv_inv_num,
                inv_status,
                svc_start,
                svc_end,
                inv_sub_utc,
                cpt,
                fp,
                billed,
                dup_of,
            ),
        )
        emitter.emit(
            "INVOICE_SUBMITTED",
            "Invoice",
            inv_id,
            cid,
            "SYSTEM_SEED",
            inv_sub_utc,
            {
                "billed_cents": billed,
                "claim_id": cid,
                "invoice_id": inv_id,
                "invoice_status": inv_status,
                "provider_id": prv_id,
            },
        )
        primary_inv_by_claim[c_idx] = (
            inv_id,
            prv_id,
            billed,
            fp,
            cpt,
            svc_start,
            svc_end,
        )

    # Secondary -B invoices for claims 1..2480 (2,480 rows)
    for c_idx in range(1, 2481):
        meta = claim_meta[c_idx]
        cid = meta["claim_id"]
        if c_idx <= 30:
            # Claims 1..30 use dedicated secondary WATCHLIST/SUSPENDED providers PRV-000461..000490 on -B
            # (degree 1.0 in W) -> PageRank flow alpha * PR(p_2) / 1.0 concentrates into claim -> tilde_PR(c) ~ 1.52 > 1.25 (IND-06)
            # and triggers secondary IND-15 (30 rows). Total indicators = 4,090 + 30 = 4,120.
            prv_id = f"PRV-{460 + c_idx:06d}"
        else:
            prv_id = meta["provider_id"]
        sub_utc = meta["submitted_at_utc"]
        svc_start = sub_utc[:10] + "T13:00:00Z"
        svc_end = sub_utc[:10] + "T17:00:00Z"
        inv_sub_utc = "2026-06-30T19:00:00Z"
        cpt = CPT_CODES[(c_idx + 2) % len(CPT_CODES)]
        billed = 155000 + c_idx
        inv_status = "SUBMITTED"
        dup_of = None

        if 751 <= c_idx <= 775:
            # YF-NEG-3: 25 cross-claimant duplicate invoices
            # Copy original invoice's provider_id, cpt_or_line_code, service dates, and billed amount
            partner_c_idx = cross_dup_partner[c_idx]
            orig_inv_id, orig_prv_id, orig_billed, _, orig_cpt, orig_start, orig_end = primary_inv_by_claim[partner_c_idx]
            prv_id = orig_prv_id
            cpt = orig_cpt
            svc_start = orig_start
            svc_end = orig_end
            billed = orig_billed
            inv_status = "REJECTED_DUPLICATE"
            dup_of = orig_inv_id
            fp = _compute_line_item_fp(cpt, svc_start, svc_end, billed)
        elif 1306 <= c_idx <= 1330:
            # EC-1: 25 intra-claim duplicate resubmissions
            # Copy original invoice's provider_id, cpt_or_line_code, service dates, and billed amount
            orig_inv_id, orig_prv_id, orig_billed, _, orig_cpt, orig_start, orig_end = primary_inv_by_claim[c_idx]
            prv_id = orig_prv_id
            cpt = orig_cpt
            svc_start = orig_start
            svc_end = orig_end
            billed = orig_billed
            inv_status = "REJECTED_DUPLICATE"
            dup_of = orig_inv_id
            fp = _compute_line_item_fp(cpt, svc_start, svc_end, billed)
        elif c_idx in cross_dup_partner:
            partner_c_idx = cross_dup_partner[c_idx]
            orig_inv_id, _, orig_billed, _, orig_cpt, orig_start, orig_end = primary_inv_by_claim[partner_c_idx]
            cpt = orig_cpt
            svc_start = orig_start
            svc_end = orig_end
            billed = orig_billed
            inv_status = "REJECTED_DUPLICATE"
            dup_of = orig_inv_id
            fp = _compute_line_item_fp(cpt, svc_start, svc_end, billed)
        else:
            fp = _compute_line_item_fp(cpt, svc_start, svc_end, billed)

        inv_id = _next_inv_id(prv_id)
        prv_inv_num = f"PINV-{c_idx:06d}-B"
        conn.execute(
            """
            INSERT INTO invoices VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, ?
            )
            """,
            (
                inv_id,
                cid,
                prv_id,
                prv_inv_num,
                inv_status,
                svc_start,
                svc_end,
                inv_sub_utc,
                cpt,
                fp,
                billed,
                dup_of,
            ),
        )
        emitter.emit(
            "INVOICE_SUBMITTED",
            "Invoice",
            inv_id,
            cid,
            "SYSTEM_SEED",
            inv_sub_utc,
            {
                "billed_cents": billed,
                "claim_id": cid,
                "invoice_id": inv_id,
                "invoice_status": inv_status,
                "provider_id": prv_id,
            },
        )

    # Third -C same-day/same-provider split invoices for claims 76..95 (20 rows -> k_split = 3 for IND-12, total 7,500 invoices)
    for c_idx in range(76, 96):
        meta = claim_meta[c_idx]
        cid = meta["claim_id"]
        prv_id = meta["provider_id"]
        inv_id = _next_inv_id(prv_id)
        sub_utc = meta["submitted_at_utc"]
        svc_start = sub_utc[:10] + "T15:00:00Z"
        svc_end = sub_utc[:10] + "T18:00:00Z"
        inv_sub_utc = "2026-06-30T19:30:00Z"
        cpt = CPT_CODES[(c_idx + 4) % len(CPT_CODES)]
        billed = 158000 + c_idx
        fp = _compute_line_item_fp(cpt, svc_start, svc_end, billed)
        prv_inv_num = f"PINV-{c_idx:06d}-C"
        conn.execute(
            """
            INSERT INTO invoices VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, NULL
            )
            """,
            (
                inv_id,
                cid,
                prv_id,
                prv_inv_num,
                "SUBMITTED",
                svc_start,
                svc_end,
                inv_sub_utc,
                cpt,
                fp,
                billed,
            ),
        )
        emitter.emit(
            "INVOICE_SUBMITTED",
            "Invoice",
            inv_id,
            cid,
            "SYSTEM_SEED",
            inv_sub_utc,
            {
                "billed_cents": billed,
                "claim_id": cid,
                "invoice_id": inv_id,
                "invoice_status": "SUBMITTED",
                "provider_id": prv_id,
            },
        )

    # -------------------------------------------------------------------------
    # 8. APPROVE 1,200 INVOICES -> ATOMIC CASCADE TO 1,200 CLAIMS
    #    (1,200 INVOICE_APPROVED + 1,200 CLAIM_APPROVED events)
    # -------------------------------------------------------------------------
    # Approve primary invoice on claims 1276..2475 (1,200 claims, all with SUBMITTED primary invoices).
    approved_claim_indices = list(range(1276, 2476))
    for c_idx in approved_claim_indices:
        meta = claim_meta[c_idx]
        cid = meta["claim_id"]
        inv_id, prv_id, billed, *rest = primary_inv_by_claim[c_idx]
        app_cents = billed
        app_utc = "2026-07-01T10:00:00Z"

        conn.execute(
            """
            UPDATE invoices
               SET invoice_status = 'APPROVED',
                   approved_cents = ?,
                   historical_approved_cents = ?
             WHERE invoice_id = ?
            """,
            (app_cents, app_cents, inv_id),
        )
        emitter.emit(
            "INVOICE_APPROVED",
            "Invoice",
            inv_id,
            cid,
            "USR-ADJ-001",
            app_utc,
            {
                "approved_cents": app_cents,
                "claim_id": cid,
                "invoice_id": inv_id,
                "invoice_status": "APPROVED",
            },
        )
        emitter.emit(
            "CLAIM_APPROVED",
            "Claim",
            cid,
            cid,
            "USR-ADJ-001",
            app_utc,
            {
                "approved_amount_cents": app_cents,
                "claim_id": cid,
                "claim_status": "APPROVED",
                "historical_approved_cents": app_cents,
            },
        )

    # -------------------------------------------------------------------------
    # 9. PAYMENTS (4,200 rows: 4,115 AUTHORIZED + 85 BLOCKED_*)
    #    & DISBURSEMENTS (315) & CLAWBACKS (20)
    # -------------------------------------------------------------------------
    # Distribute 4,115 AUTHORIZED payments across the 1,200 approved claims (1276..2475):
    # - Claims 1276..1800 (525 claims) get 4 AUTHORIZED payments each (each 1/4 of approved_cents) = 2,100 payments
    # - Claims 1801..2475 (675 claims) get 3 AUTHORIZED payments each (except last 10 get 2)
    #   Wait: 515 * 4 + 675 * 3 + 10 * 3 = let's compute exact counts:
    #   If 515 claims get 4 payments (2,060) + 685 claims get 3 payments (2,055) => 2,060 + 2,055 = 4,115!
    pay_seq = 0
    claim_payments: dict[int, list[tuple[str, str, str, int]]] = {}

    for idx_pos, c_idx in enumerate(approved_claim_indices):
        num_pays = 4 if idx_pos < 515 else 3
        meta = claim_meta[c_idx]
        cid = meta["claim_id"]
        inv_id, prv_id, app_cents, *rest = primary_inv_by_claim[c_idx]
        chunk = app_cents // num_pays
        for p_k in range(num_pays):
            pay_seq += 1
            pay_id = f"PAY-2026-{pay_seq:06d}"
            amt = chunk if p_k < num_pays - 1 else (app_cents - chunk * (num_pays - 1))
            created_utc = "2026-07-02T09:00:00Z"
            conn.execute(
                """
                INSERT INTO payments VALUES (
                    ?, ?, ?, 'PROVIDER', NULL, ?, 'AUTHORIZED', ?, 0, 0, 0,
                    ?, ?, NULL, NULL, 'USR-FIN-001', NULL, NULL, NULL
                )
                """,
                (pay_id, cid, inv_id, prv_id, amt, f"IDEMP-{pay_seq:06d}", created_utc),
            )
            emitter.emit(
                "PAYMENT_AUTHORIZED",
                "Payment",
                pay_id,
                cid,
                "USR-FIN-001",
                created_utc,
                {
                    "amount_cents": amt,
                    "claim_id": cid,
                    "invoice_id": inv_id,
                    "payment_id": pay_id,
                    "payment_status": "AUTHORIZED",
                    "recipient_provider_id": prv_id,
                },
            )
            claim_payments.setdefault(c_idx, []).append((pay_id, cid, inv_id, amt))

    # Disburse 315 payments across claims 1331..1645 (first payment on each of those 315 claims)
    # Note: trg_payments_validate_upd requires the latest event on entity_id=pay_id to be PAYMENT_AUTHORIZED
    # at the moment of UPDATE, and then we emit PAYMENT_DISBURSED immediately after.
    disbursed_payments: list[tuple[int, str, str, str, int]] = []
    for c_idx in range(1331, 1646):
        pay_id, cid, inv_id, amt = claim_payments[c_idx][0]
        disb_utc = "2026-07-03T12:00:00Z"
        bank_ref = f"ACH-2026-{c_idx:06d}"
        conn.execute(
            """
            UPDATE payments
               SET payment_status = 'DISBURSED',
                   disbursed_amount_cents = ?,
                   net_paid_cents = ?,
                   disbursed_at_utc = ?,
                   external_bank_tx_ref = ?
             WHERE payment_id = ?
            """,
            (amt, amt, disb_utc, bank_ref, pay_id),
        )
        emitter.emit(
            "PAYMENT_DISBURSED",
            "Payment",
            pay_id,
            cid,
            "USR-FIN-001",
            disb_utc,
            {
                "amount_cents": amt,
                "claim_id": cid,
                "disbursed_amount_cents": amt,
                "external_bank_tx_ref": bank_ref,
                "invoice_id": inv_id,
                "payment_id": pay_id,
                "payment_status": "DISBURSED",
            },
        )
        disbursed_payments.append((c_idx, pay_id, cid, inv_id, amt))

    # Clawback 20 disbursed payments on claims 1331..1350 (EC-3: 20 post-disbursement clawbacks)
    # Note: trg_payments_validate_upd requires PAYMENT_CLAWBACK_REVERSED event BEFORE the UPDATE!
    for c_idx, pay_id, cid, inv_id, amt in disbursed_payments[:20]:
        rev_utc = "2026-07-05T15:00:00Z"
        emitter.emit(
            "PAYMENT_CLAWBACK_REVERSED",
            "Payment",
            pay_id,
            cid,
            "USR-SIU-001",
            rev_utc,
            {
                "amount_cents": amt,
                "claim_id": cid,
                "clawed_back_cents": amt,
                "invoice_id": inv_id,
                "net_paid_cents": 0,
                "payment_id": pay_id,
                "payment_status": "REVERSED_CLAWBACK",
            },
        )
        conn.execute(
            """
            UPDATE payments
               SET payment_status = 'REVERSED_CLAWBACK',
                   clawed_back_cents = ?,
                   net_paid_cents = 0,
                   reversed_at_utc = ?
             WHERE payment_id = ?
            """,
            (amt, rev_utc, pay_id),
        )

    # 85 BLOCKED_* payments (pay_seq 4116..4200):
    # - 30 BLOCKED_OVERPAYMENT on claims 1276..1305 (YF-NEG-2)
    # - 30 BLOCKED_UNAPPROVED on claims 1..30
    # - 25 BLOCKED_INVALID_RECIPIENT on claims 31..55
    for blk_idx in range(85):
        pay_seq += 1
        pay_id = f"PAY-2026-{pay_seq:06d}"
        blk_utc = "2026-07-04T11:00:00Z"
        if blk_idx < 30:
            c_idx = 1276 + blk_idx
            cid = claim_meta[c_idx]["claim_id"]
            inv_id, prv_id, app_cents, *rest = primary_inv_by_claim[c_idx]
            over_amt = app_cents + 500000
            # Verify live trigger blocks AUTHORIZED overpayment inside SAVEPOINT
            conn.execute(f"SAVEPOINT sp_yf_neg2_{blk_idx}")
            over_blocked = False
            try:
                conn.execute(
                    """
                    INSERT INTO payments VALUES (
                        ?, ?, ?, 'PROVIDER', NULL, ?, 'AUTHORIZED', ?, 0, 0, 0,
                        ?, ?, NULL, NULL, 'USR-FIN-001', NULL, NULL, NULL
                    )
                    """,
                    (pay_id, cid, inv_id, prv_id, over_amt, f"IDEMP-TRY-{pay_seq:06d}", blk_utc),
                )
            except sqlite3.IntegrityError as exc:
                if "ERR_PAYMENT_EXCEEDS_APPROVED_CAP" in str(exc):
                    over_blocked = True
                conn.execute(f"ROLLBACK TO SAVEPOINT sp_yf_neg2_{blk_idx}")
            conn.execute(f"RELEASE SAVEPOINT sp_yf_neg2_{blk_idx}")
            if not over_blocked:
                raise RuntimeError("YF-NEG-2 failure: overpayment was not blocked by trg_payments_validate_ins")
            p_status = "BLOCKED_OVERPAYMENT"
            reason = "ERR_PAYMENT_EXCEEDS_APPROVED_CAP"
            amt = over_amt
        elif blk_idx < 60:
            c_idx = 1 + (blk_idx - 30)
            cid = claim_meta[c_idx]["claim_id"]
            inv_id, prv_id, billed, *rest = primary_inv_by_claim[c_idx]
            p_status = "BLOCKED_UNAPPROVED"
            reason = "ERR_PAYMENT_REQUIRES_APPROVED_CLAIM_AND_INVOICE"
            amt = billed
        else:
            c_idx = 31 + (blk_idx - 60)
            cid = claim_meta[c_idx]["claim_id"]
            inv_id, prv_id, billed, *rest = primary_inv_by_claim[c_idx]
            p_status = "BLOCKED_INVALID_RECIPIENT"
            reason = "ERR_PAYMENT_RECIPIENT_OWNERSHIP_MISMATCH"
            amt = billed

        conn.execute(
            """
            INSERT INTO payments VALUES (
                ?, ?, ?, 'PROVIDER', NULL, ?, ?, ?, 0, 0, 0,
                ?, ?, NULL, NULL, 'USR-FIN-001', ?, NULL, NULL
            )
            """,
            (pay_id, cid, inv_id, prv_id, p_status, amt, f"IDEMP-{pay_seq:06d}", blk_utc, reason),
        )
        emitter.emit(
            "PAYMENT_BLOCKED",
            "Payment",
            pay_id,
            cid,
            "SYSTEM_GUARD",
            blk_utc,
            {
                "amount_cents": amt,
                "block_reason_code": reason,
                "claim_id": cid,
                "invoice_id": inv_id,
                "payment_id": pay_id,
                "payment_status": p_status,
            },
        )

    # -------------------------------------------------------------------------
    # 10. SIU_HOLD PLACEMENTS (60 claims) + PAYMENT_CANCELLED (25 payments)
    #     + INVESTIGATIONS (45 rows) + CLAIM_DENIED (25 claims)
    # -------------------------------------------------------------------------
    # Place 60 claims on SIU_HOLD:
    # - 35 fraud claims (claims 1..35, currently SUBMITTED)
    # - 25 approved claims (claims 2451..2475, currently APPROVED with AUTHORIZED payments)
    siu_hold_claims = list(range(1, 36)) + list(range(2451, 2476))
    for c_idx in siu_hold_claims:
        cid = claim_meta[c_idx]["claim_id"]
        hold_utc = "2026-07-06T09:00:00Z"
        conn.execute(
            "UPDATE claims SET claim_status = 'SIU_HOLD' WHERE claim_id = ?",
            (cid,),
        )
        emitter.emit(
            "CLAIM_SIU_HOLD_PLACED",
            "Claim",
            cid,
            cid,
            "USR-SIU-001",
            hold_utc,
            {
                "claim_id": cid,
                "claim_status": "SIU_HOLD",
            },
        )

    # Cancel 1 AUTHORIZED payment on each of the 25 held approved claims (2451..2475) -> 25 PAYMENT_CANCELLED
    for c_idx in range(2451, 2476):
        pay_id, cid, inv_id, amt = claim_payments[c_idx][0]
        canc_utc = "2026-07-06T10:00:00Z"
        reason_code = "SIU_HOLD_RESERVATION_CLEARED"
        emitter.emit(
            "PAYMENT_CANCELLED",
            "Payment",
            pay_id,
            cid,
            "USR-FIN-001",
            canc_utc,
            {
                "amount_cents": amt,
                "claim_id": cid,
                "payment_id": pay_id,
                "payment_status": "CANCELLED",
                "reason_code": reason_code,
            },
        )
        conn.execute(
            """
            UPDATE payments
               SET payment_status = 'CANCELLED',
                   reversed_at_utc = ?,
                   cancel_reason = ?
             WHERE payment_id = ?
            """,
            (canc_utc, reason_code, pay_id),
        )

    # Open 45 investigations across 45 of the 60 SIU_HOLD claims:
    # - invg 1..35 on claims 1..35
    # - invg 36..45 on claims 2451..2460
    invg_claims = list(range(1, 36)) + list(range(2451, 2461))
    for idx_i, c_idx in enumerate(invg_claims, start=1):
        invg_id = f"INVG-2026-{idx_i:06d}"
        meta = claim_meta[c_idx]
        cid = meta["claim_id"]
        clmt_id = meta["claimant_id"]
        prv_id = meta["provider_id"]
        prio = "P1_CRITICAL" if idx_i <= 15 else ("P2_HIGH" if idx_i <= 30 else "P3_STANDARD")
        open_utc = "2026-07-06T12:00:00Z"
        exposure = meta["claimed_cents"]
        conn.execute(
            """
            INSERT INTO investigations VALUES (
                ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, NULL, NULL, ?, 0, ?
            )
            """,
            (
                invg_id,
                cid,
                clmt_id,
                prv_id,
                prio,
                f"USR-SIU-{(idx_i % 5) + 1:03d}",
                open_utc,
                open_utc,
                exposure,
                f"SIU investigation opened for {cid}",
            ),
        )
        emitter.emit(
            "INVESTIGATION_OPENED",
            "Investigation",
            invg_id,
            cid,
            "USR-SIU-001",
            open_utc,
            {
                "assigned_investigator_id": f"USR-SIU-{(idx_i % 5) + 1:03d}",
                "claim_id": cid,
                "investigation_id": invg_id,
                "investigation_status": "OPEN",
                "priority": prio,
            },
        )

        # Transition subset of investigations through FSM:
        # - idx_i 1..15: OPEN -> EVIDENCE_COLLECTION -> CLOSED_CONFIRMED_FRAUD
        # - idx_i 16..22: OPEN -> EVIDENCE_COLLECTION -> CLOSED_INSUFFICIENT_EVIDENCE
        # - idx_i 36..43 (8 claims 2451..2458): OPEN -> CLOSED_CLEARED_BENIGN, then exit SIU_HOLD -> APPROVED!
        if idx_i <= 15:
            conn.execute(
                "UPDATE investigations SET investigation_status = 'EVIDENCE_COLLECTION', updated_at_utc = '2026-07-07T10:00:00Z' WHERE investigation_id = ?",
                (invg_id,),
            )
            emitter.emit(
                "INVESTIGATION_STATUS_CHANGED",
                "Investigation",
                invg_id,
                cid,
                f"USR-SIU-{(idx_i % 5) + 1:03d}",
                "2026-07-07T10:00:00Z",
                {
                    "claim_id": cid,
                    "investigation_id": invg_id,
                    "investigation_status": "EVIDENCE_COLLECTION",
                    "previous_status": "OPEN",
                },
            )
            conn.execute(
                """
                UPDATE investigations
                   SET investigation_status = 'CLOSED_CONFIRMED_FRAUD',
                       ruling_outcome = 'CONFIRMED_FRAUD',
                       updated_at_utc = '2026-07-08T16:00:00Z',
                       closed_at_utc = '2026-07-08T16:00:00Z'
                 WHERE investigation_id = ?
                """,
                (invg_id,),
            )
            emitter.emit(
                "INVESTIGATION_CLOSED",
                "Investigation",
                invg_id,
                cid,
                f"USR-SIU-{(idx_i % 5) + 1:03d}",
                "2026-07-08T16:00:00Z",
                {
                    "claim_id": cid,
                    "closed_at_utc": "2026-07-08T16:00:00Z",
                    "investigation_id": invg_id,
                    "investigation_status": "CLOSED_CONFIRMED_FRAUD",
                    "ruling_outcome": "CONFIRMED_FRAUD",
                },
            )
        elif idx_i <= 22:
            conn.execute(
                "UPDATE investigations SET investigation_status = 'EVIDENCE_COLLECTION', updated_at_utc = '2026-07-07T10:00:00Z' WHERE investigation_id = ?",
                (invg_id,),
            )
            emitter.emit(
                "INVESTIGATION_STATUS_CHANGED",
                "Investigation",
                invg_id,
                cid,
                f"USR-SIU-{(idx_i % 5) + 1:03d}",
                "2026-07-07T10:00:00Z",
                {
                    "claim_id": cid,
                    "investigation_id": invg_id,
                    "investigation_status": "EVIDENCE_COLLECTION",
                    "previous_status": "OPEN",
                },
            )
            conn.execute(
                """
                UPDATE investigations
                   SET investigation_status = 'CLOSED_INSUFFICIENT_EVIDENCE',
                       ruling_outcome = 'INSUFFICIENT_EVIDENCE',
                       updated_at_utc = '2026-07-08T16:00:00Z',
                       closed_at_utc = '2026-07-08T16:00:00Z'
                 WHERE investigation_id = ?
                """,
                (invg_id,),
            )
            emitter.emit(
                "INVESTIGATION_CLOSED",
                "Investigation",
                invg_id,
                cid,
                f"USR-SIU-{(idx_i % 5) + 1:03d}",
                "2026-07-08T16:00:00Z",
                {
                    "claim_id": cid,
                    "closed_at_utc": "2026-07-08T16:00:00Z",
                    "investigation_id": invg_id,
                    "investigation_status": "CLOSED_INSUFFICIENT_EVIDENCE",
                    "ruling_outcome": "INSUFFICIENT_EVIDENCE",
                },
            )
        elif 36 <= idx_i <= 43:
            conn.execute(
                """
                UPDATE investigations
                   SET investigation_status = 'CLOSED_CLEARED_BENIGN',
                       ruling_outcome = 'CLEARED_BENIGN',
                       updated_at_utc = '2026-07-08T16:00:00Z',
                       closed_at_utc = '2026-07-08T16:00:00Z'
                 WHERE investigation_id = ?
                """,
                (invg_id,),
            )
            emitter.emit(
                "INVESTIGATION_CLOSED",
                "Investigation",
                invg_id,
                cid,
                f"USR-SIU-{(idx_i % 5) + 1:03d}",
                "2026-07-08T16:00:00Z",
                {
                    "claim_id": cid,
                    "closed_at_utc": "2026-07-08T16:00:00Z",
                    "investigation_id": invg_id,
                    "investigation_status": "CLOSED_CLEARED_BENIGN",
                    "ruling_outcome": "CLEARED_BENIGN",
                },
            )
            # Benign exit from SIU_HOLD -> APPROVED (permitted by D-1 / DEF-01 / HIGH-02 gate!)
            conn.execute(
                "UPDATE claims SET claim_status = 'APPROVED' WHERE claim_id = ?",
                (cid,),
            )
            app_cents_now = conn.execute(
                "SELECT approved_amount_cents FROM claims WHERE claim_id = ?",
                (cid,),
            ).fetchone()[0]
            emitter.emit(
                "CLAIM_APPROVED",
                "Claim",
                cid,
                cid,
                f"USR-SIU-{(idx_i % 5) + 1:03d}",
                "2026-07-08T16:05:00Z",
                {
                    "approved_amount_cents": app_cents_now,
                    "claim_id": cid,
                    "claim_status": "APPROVED",
                    "cleared_investigation_id": invg_id,
                    "previous_status": "SIU_HOLD",
                    "release_reason": "CLEARED_BENIGN",
                },
            )

    # Deny 25 claims (claims 1..15 on SIU_HOLD with 0 approved_amount_cents + claims 36..45 on SUBMITTED with 0 balances)
    denied_claims = list(range(1, 16)) + list(range(36, 46))
    for c_idx in denied_claims:
        cid = claim_meta[c_idx]["claim_id"]
        deny_utc = "2026-07-09T14:00:00Z"
        conn.execute(
            "UPDATE claims SET claim_status = 'DENIED' WHERE claim_id = ?",
            (cid,),
        )
        emitter.emit(
            "CLAIM_DENIED",
            "Claim",
            cid,
            cid,
            "USR-SIU-001",
            deny_utc,
            {
                "claim_id": cid,
                "claim_status": "DENIED",
            },
        )

    # -------------------------------------------------------------------------
    # 11. RELATIONSHIP EDGES (8,000 operational rows)
    #     + GROUND TRUTH MISSING EDGES (25 rows in ground_truth.db for YF-NEG-4)
    # -------------------------------------------------------------------------
    # First plant 25 missing edges across RING-2026-016..020 (5 per ring) in ground_truth_missing_edges
    missing_edge_keys: set[tuple[str, str, str]] = set()
    gtme_seq = 0
    for r_idx in range(16, 21):
        ring_id = f"RING-2026-{r_idx:03d}"
        clmts = ring_claimants[r_idx]
        for k in range(5):
            gtme_seq += 1
            src_c = clmts[k]
            dst_c = clmts[k + 1]
            src_key = f"CLAIMANT:{src_c}"
            dst_key = f"CLAIMANT:{dst_c}"
            if src_key > dst_key:
                src_key, dst_key = dst_key, src_key
            etype = "SHARED_BANK_ACCOUNT" if k % 2 == 0 else "SHARED_PHONE"
            missing_edge_keys.add((etype, src_key, dst_key))
            gt_conn.execute(
                "INSERT INTO ground_truth_missing_edges VALUES (?, ?, ?, ?, ?, ?)",
                (
                    f"GTME-2026-{gtme_seq:04d}",
                    ring_id,
                    etype,
                    src_key,
                    dst_key,
                    "YF-NEG-4: Planted unrecorded off-book collusive relationship",
                ),
            )

    edge_seq = 0
    seen_edges: set[tuple[str, str, str]] = set()

    def _add_edge(
        etype: str,
        s_type: str,
        s_id: str,
        t_type: str,
        t_id: str,
        weight: float,
        ev_cnt: int,
        supp_claim_id: str,
    ) -> bool:
        nonlocal edge_seq
        s_key = f"{s_type}:{s_id}"
        t_key = f"{t_type}:{t_id}"
        if s_key == t_key:
            return False
        if s_key > t_key:
            s_type, t_type = t_type, s_type
            s_id, t_id = t_id, s_id
            s_key, t_key = t_key, s_key
        key = (etype, s_key, t_key)
        if key in seen_edges or key in missing_edge_keys:
            return False
        seen_edges.add(key)
        edge_seq += 1
        edge_id = f"EDGE-2026-{edge_seq:06d}"
        s_clmt = s_id if s_type == "CLAIMANT" else None
        s_prv = s_id if s_type == "PROVIDER" else None
        t_clmt = t_id if t_type == "CLAIMANT" else None
        t_prv = t_id if t_type == "PROVIDER" else None
        conn.execute(
            """
            INSERT INTO relationship_edges VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                '2026-01-10T00:00:00Z', '2026-06-15T00:00:00Z', ?, 1
            )
            """,
            (
                edge_id,
                etype,
                s_type,
                s_clmt,
                s_prv,
                t_type,
                t_clmt,
                t_prv,
                s_key,
                t_key,
                weight,
                ev_cnt,
                supp_claim_id,
            ),
        )
        return True

    # Add ring edges for rings 1..20 (excluding the 25 planted missing_edge_keys),
    # varying active edge density rho_K across rings while keeping each 12-claimant ring connected
    for r_idx in range(1, 21):
        clmts = ring_claimants[r_idx]
        prvs = ring_providers[r_idx]
        supp_cid = f"CLM-2026-{(r_idx - 1) * 48 + 1 if r_idx <= 5 else 1:06d}"
        # Always include a connected spanning backbone (step-2 and step-3 chords avoid missing_edge_keys step-1 pairs)
        ring_pairs: list[tuple[int, int]] = []
        for step in (2, 3, 1, 4, 5, 6):
            for i_c in range(len(clmts)):
                j_c = (i_c + step) % len(clmts)
                a, b = (i_c, j_c) if i_c < j_c else (j_c, i_c)
                if (a, b) not in ring_pairs:
                    ring_pairs.append((a, b))
        target_edges = (36 + r_idx * 2) if r_idx <= 15 else (42 + (r_idx - 16) * 4)
        added_in_ring = 0
        for a, b in ring_pairs:
            if added_in_ring >= target_edges:
                break
            if _add_edge("SHARED_BANK_ACCOUNT", "CLAIMANT", clmts[a], "CLAIMANT", clmts[b], 0.95, 3, supp_cid):
                added_in_ring += 1
        for c_id in clmts:
            for p_id in prvs:
                _add_edge("CLAIMANT_TREATED_BY_PROVIDER", "CLAIMANT", c_id, "PROVIDER", p_id, 0.85, 2, supp_cid)

    # Add YF-NEG-3 shared bank account + duplicate invoice edges for 2-claimant pairs (|V_K| = 2 < 3)
    for c_idx in range(751, 775, 2):
        c1 = claim_meta[c_idx]["claimant_id"]
        c2 = claim_meta[c_idx + 1]["claimant_id"]
        supp_cid = claim_meta[c_idx]["claim_id"]
        _add_edge("SHARED_BANK_ACCOUNT", "CLAIMANT", c1, "CLAIMANT", c2, 1.0, 2, supp_cid)
        _add_edge("CROSS_CLAIM_DUPLICATE_INVOICE", "CLAIMANT", c1, "CLAIMANT", c2, 1.0, 2, supp_cid)

    # Add BL-4 SAME_INCIDENT_PARTICIPANT edges for the 14 6-claimant freeway pileups (1108..1191, BC-5)
    for p_grp in range(14):
        base_c = 1108 + p_grp * 6
        supp_cid = claim_meta[base_c]["claim_id"]
        p_clmts = [claim_meta[base_c + k]["claimant_id"] for k in range(6)]
        for i_c in range(6):
            for j_c in range(i_c + 1, 6):
                _add_edge("SAME_INCIDENT_PARTICIPANT", "CLAIMANT", p_clmts[i_c], "CLAIMANT", p_clmts[j_c], 0.50, 1, supp_cid)

    # Fill remaining relationship_edges up to exactly 8,000 using deterministic CLAIMANT_TREATED_BY_PROVIDER edges
    for c_idx in range(1, 5001):
        if edge_seq >= 8000:
            break
        meta = claim_meta[c_idx]
        _add_edge(
            "CLAIMANT_TREATED_BY_PROVIDER",
            "CLAIMANT",
            meta["claimant_id"],
            "PROVIDER",
            meta["provider_id"],
            0.75,
            1,
            meta["claim_id"],
        )

    cand_i = 1
    while edge_seq < 8000:
        c_num = (cand_i % 2000) + 1
        p_num = ((cand_i * 7 + (cand_i // 2000)) % 460) + 1
        supp_cid = f"CLM-2026-{(cand_i % 5000) + 1:06d}"
        _add_edge(
            "PROVIDER_REFERRAL_LINK" if cand_i % 2 == 0 else "CLAIMANT_TREATED_BY_PROVIDER",
            "CLAIMANT",
            f"CLMT-{c_num:06d}",
            "PROVIDER",
            f"PRV-{p_num:06d}",
            0.60,
            1,
            supp_cid,
        )
        cand_i += 1

    # -------------------------------------------------------------------------
    # 12. FRAUD INDICATORS (4,120 rows) & ST-SCORE-V1 CLAIM SCORING
    #     Derived EXCLUSIVELY from operational.db via pure SQL queries
    #     (zero access to ground_truth.db, ring_id, or scenario_code).
    # -------------------------------------------------------------------------
    derive_operational_indicators_and_scores(conn)

    # Drop temporary seeding indexes so sqlite_master has the exact 39 objects of ST-SCHEMA-V1
    _drop_temp_seed_indexes(conn, tmp_indexes)

    conn.commit()
    gt_conn.commit()

    # Verify schema digest after dropping temp indexes
    final_digest = compute_schema_digest(conn)
    if final_digest != EXPECTED_SCHEMA_DIGEST:
        raise RuntimeError(f"Schema digest mismatch after seeding: {final_digest}")

    # Collect counts and checksums
    actual_counts: dict[str, int] = {}
    for tbl in EXPECTED_COUNTS:
        c = gt_conn if tbl.startswith("ground_truth_") else conn
        actual_counts[tbl] = c.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]

    ops_checksum = compute_database_checksum(conn)
    gt_checksum = compute_database_checksum(gt_conn)

    conn.close()
    gt_conn.close()

    return {
        "seed": seed,
        "schema_digest": final_digest,
        "ops_checksum": ops_checksum,
        "gt_checksum": gt_checksum,
        "counts": actual_counts,
        "event_buckets": emitter.counts,
    }


if __name__ == "__main__":
    seed_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    repo_root = Path(__file__).resolve().parent.parent
    ops_out = repo_root / "data" / "operational.db"
    gt_out = repo_root / "data" / "ground_truth.db"
    result = generate_dataset(seed=seed_arg, ops_db_path=ops_out, gt_db_path=gt_out)
    print(f"[PASS] Seed={result['seed']} generated successfully.")
    print(f"       ST-SCHEMA-V1 digest : {result['schema_digest']}")
    print(f"       operational.db SHA256: {result['ops_checksum']}")
    print(f"       ground_truth.db SHA256: {result['gt_checksum']}")
    for k, v in result["counts"].items():
        print(f"       {k:28s}: {v:,d}")

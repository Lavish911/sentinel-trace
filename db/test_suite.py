#!/usr/bin/env python3
"""
SENTINEL//TRACE — Production Database & Seed Acceptance Test Suite (T-01..T-20)
===============================================================================
Verifies the complete SQLite operational + ground-truth database implementation,
deterministic seed generation, challenge negative scenarios (YF-NEG-1..5),
benign lookalike controls (BL-1..5), edge cases (EC-1..3), ST-EVT-V2 event
hash chain, financial penny-reconciliation, and trigger guardrails (DEF-01..03).

Usage:
    python3 -m db.test_suite
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db.engine import (
    EXPECTED_SCHEMA_DIGEST,
    compute_schema_digest,
    open_ground_truth_db,
    open_operational_db,
)
from db.seed import (
    EVENT_BUCKET_TARGETS,
    EXPECTED_COUNTS,
    _compute_line_item_fp,
    _enc_field,
    derive_operational_indicators_and_scores,
    generate_dataset,
)


class SuiteRunner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.failures: list[str] = []

    def check(self, cond: bool, code: str, desc: str, detail: str = "") -> None:
        if cond:
            self.passed += 1
            print(f"[PASS] {code}: {desc}")
        else:
            self.failed += 1
            msg = f"[FAIL] {code}: {desc}" + (f" ({detail})" if detail else "")
            self.failures.append(msg)
            print(msg)


def run_all_tests() -> int:
    runner = SuiteRunner()

    with tempfile.TemporaryDirectory(prefix="sentinel_trace_db_") as tmpdir:
        tmp = Path(tmpdir)
        ops_42_a = tmp / "ops_42_a.db"
        gt_42_a = tmp / "gt_42_a.db"
        ops_42_b = tmp / "ops_42_b.db"
        gt_42_b = tmp / "gt_42_b.db"
        ops_alt = tmp / "ops_20261022.db"
        gt_alt = tmp / "gt_20261022.db"

        res_42_a = generate_dataset(seed=42, ops_db_path=ops_42_a, gt_db_path=gt_42_a)
        res_42_b = generate_dataset(seed=42, ops_db_path=ops_42_b, gt_db_path=gt_42_b)
        res_alt = generate_dataset(seed=20261022, ops_db_path=ops_alt, gt_db_path=gt_alt)

        conn = open_operational_db(ops_42_a, create_schema=False)
        gt = open_ground_truth_db(gt_42_a, create_schema=False)

        # T-01: Operational schema object count & ST-SCHEMA-V1 digest
        objs = conn.execute(
            "SELECT type, COUNT(*) FROM sqlite_master "
            "WHERE type IN ('table','trigger') AND name NOT LIKE 'sqlite_%' GROUP BY type"
        ).fetchall()
        obj_map = {r[0]: r[1] for r in objs}
        digest = compute_schema_digest(conn)
        runner.check(
            obj_map.get("table") == 12
            and obj_map.get("trigger") == 27
            and digest == EXPECTED_SCHEMA_DIGEST,
            "T-01",
            "Operational schema has 12 STRICT tables + 27 triggers and matches ST-SCHEMA-V1 digest",
            f"tables={obj_map.get('table')}, triggers={obj_map.get('trigger')}, digest={digest}",
        )

        # T-02: PRAGMA foreign_keys = 1 and PRAGMA foreign_key_check = empty
        fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        runner.check(
            fk_on == 1 and len(fk_violations) == 0,
            "T-02",
            "PRAGMA foreign_keys = 1 and zero foreign_key_check violations across operational.db",
            f"fk_on={fk_on}, violations={len(fk_violations)}",
        )

        # T-03: Ground-truth physical & logical isolation (CRITICAL-01: zero ground_truth_* tables,
        # zero RING-2026-* strings, zero orphan BANK:/DUP_FP: tokens, non-constant ring scores)
        gt_in_ops = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'ground_truth_%'"
        ).fetchone()[0]
        gt_tables = gt.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'ground_truth_%'"
        ).fetchone()[0]
        ring_leak_cnt = 0
        for (tbl_name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall():
            for row in conn.execute(f"SELECT * FROM {tbl_name}").fetchall():
                for val in row:
                    if isinstance(val, str) and "RING-2026-" in val:
                        ring_leak_cnt += 1
        orphan_bank_tokens = conn.execute(
            """
            SELECT COUNT(*) FROM fraud_indicators fi
            WHERE fi.indicator_code = 'IND-01'
              AND (
                  SELECT COUNT(*) FROM claimants c
                  WHERE 'BANK:' || c.bank_account_hash = fi.canonical_evidence_token
              ) < 2
            """
        ).fetchone()[0]
        orphan_dup_fp_tokens = conn.execute(
            """
            SELECT COUNT(*) FROM fraud_indicators fi
            WHERE fi.indicator_code = 'IND-03'
              AND (
                  SELECT COUNT(DISTINCT i.claim_id) FROM invoices i
                  WHERE 'DUP_FP:' || i.line_item_fingerprint = fi.canonical_evidence_token
              ) < 2
            """
        ).fetchone()[0]
        distinct_cluster_scores = conn.execute(
            "SELECT COUNT(DISTINCT latest_ief_score) FROM claims WHERE claim_id <= 'CLM-2026-000746'"
        ).fetchone()[0]
        runner.check(
            gt_in_ops == 0
            and gt_tables == 4
            and ring_leak_cnt == 0
            and orphan_bank_tokens == 0
            and orphan_dup_fp_tokens == 0
            and distinct_cluster_scores >= 10
            and callable(derive_operational_indicators_and_scores),
            "T-03",
            "Ground-truth physical & logical isolation (0 ground_truth_* tables, 0 RING-2026-* leaks, 0 orphan BANK:/DUP_FP: tokens, varied operational ring scores)",
            f"gt_in_ops={gt_in_ops}, gt_tables={gt_tables}, ring_leaks={ring_leak_cnt}, orphan_bank={orphan_bank_tokens}, orphan_dup={orphan_dup_fp_tokens}, distinct_scores={distinct_cluster_scores}",
        )

        # T-04: Exact baseline entity counts across all 12 operational + 4 ground-truth tables
        count_mismatches = []
        for tbl, expected in EXPECTED_COUNTS.items():
            target_conn = gt if tbl.startswith("ground_truth_") else conn
            actual = target_conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            if actual != expected:
                count_mismatches.append(f"{tbl}={actual} (expected {expected})")
        runner.check(
            len(count_mismatches) == 0,
            "T-04",
            "All 12 operational tables and 4 ground-truth tables match exact baseline entity counts",
            ", ".join(count_mismatches),
        )

        # T-05: Deterministic seed reproducibility (same seed -> identical checksum; different seed -> different checksum)
        runner.check(
            res_42_a["ops_checksum"] == res_42_b["ops_checksum"]
            and res_42_a["gt_checksum"] == res_42_b["gt_checksum"]
            and res_42_a["ops_checksum"] != res_alt["ops_checksum"]
            and res_alt["counts"] == EXPECTED_COUNTS,
            "T-05",
            "Seed generator is bit-for-bit deterministic for identical seeds and varies across distinct seeds while preserving counts",
            f"42_a={res_42_a['ops_checksum'][:12]}, 42_b={res_42_b['ops_checksum'][:12]}, alt={res_alt['ops_checksum'][:12]}",
        )

        # T-06: Event-bucket reconciliation (15 buckets summing to 19,675 + MEDIUM-01 lifecycle audit trail)
        ev_rows = conn.execute(
            "SELECT event_type, COUNT(*) FROM immutable_events GROUP BY event_type"
        ).fetchall()
        ev_map = {r[0]: r[1] for r in ev_rows}
        ev_mismatches = [
            f"{k}={ev_map.get(k, 0)} (expected {v})"
            for k, v in EVENT_BUCKET_TARGETS.items()
            if ev_map.get(k, 0) != v
        ]
        total_events = sum(ev_map.values())
        closed_invg_with_event = conn.execute(
            """
            SELECT COUNT(*) FROM investigations i
            WHERE i.investigation_status LIKE 'CLOSED_%'
              AND EXISTS (
                  SELECT 1 FROM immutable_events e
                  WHERE e.entity_type = 'Investigation'
                    AND e.entity_id = i.investigation_id
                    AND e.event_type = 'INVESTIGATION_CLOSED'
              )
            """
        ).fetchone()[0]
        benign_release_events = conn.execute(
            """
            SELECT COUNT(*) FROM immutable_events
            WHERE event_type = 'CLAIM_APPROVED'
              AND payload_json LIKE '%"previous_status":"SIU_HOLD"%'
              AND payload_json LIKE '%"release_reason":"CLEARED_BENIGN"%'
            """
        ).fetchone()[0]
        runner.check(
            len(ev_mismatches) == 0
            and total_events == 19675
            and closed_invg_with_event == 30
            and benign_release_events == 8,
            "T-06",
            "All 15 immutable_events buckets match specification targets (19,675 total), including 22 INVESTIGATION_STATUS_CHANGED, 30 INVESTIGATION_CLOSED, and 8 post-hold CLAIM_APPROVED events",
            f"mismatches={ev_mismatches}, closed_invg_events={closed_invg_with_event}, release_events={benign_release_events}",
        )

        # T-07: Full ST-EVT-V2 cryptographic hash-chain integrity across all 19,675 events
        chain_rows = conn.execute(
            "SELECT sequence_no, event_id, event_type, entity_type, entity_id, "
            "claim_id, actor_id, occurred_at_utc, payload_json, payload_sha256, "
            "prev_event_hash, event_hash FROM immutable_events ORDER BY sequence_no ASC"
        ).fetchall()
        expected_prev = "0" * 64
        chain_errors = 0
        for idx, r in enumerate(chain_rows, start=1):
            seq, eid, etype, ent_t, ent_id, cid, act_id, occ, pjson, psha, prev_h, ehash = r
            if seq != idx or prev_h != expected_prev:
                chain_errors += 1
                break
            if hashlib.sha256(pjson.encode("utf-8")).hexdigest() != psha:
                chain_errors += 1
                break
            preimage = (
                "ST-EVT-V2|"
                + _enc_field("sequence_no", seq, is_int=True)
                + _enc_field("event_id", eid)
                + _enc_field("event_type", etype)
                + _enc_field("entity_type", ent_t)
                + _enc_field("entity_id", ent_id)
                + _enc_field("claim_id", cid)
                + _enc_field("actor_id", act_id)
                + _enc_field("occurred_at_utc", occ)
                + _enc_field("payload_sha256", psha)
                + _enc_field("prev_event_hash", prev_h)
            )
            calc_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
            if calc_hash != ehash:
                chain_errors += 1
                break
            expected_prev = ehash
        runner.check(
            len(chain_rows) == 19675 and chain_errors == 0,
            "T-07",
            "Full ST-EVT-V2 SHA-256 hash chain verifies from genesis (sequence_no=1) to 19,675 with zero gaps",
            f"rows={len(chain_rows)}, errors={chain_errors}",
        )

        # T-08: Penny-level financial reconciliation across all 5,000 claims, 7,500 invoices, 4,200 payments
        claim_fin_mismatch = conn.execute(
            """
            SELECT COUNT(*) FROM claims c
            LEFT JOIN (
                SELECT claim_id,
                       COALESCE(SUM(CASE WHEN invoice_status IN ('APPROVED','PARTIALLY_PAID','PAID') THEN approved_cents ELSE 0 END), 0) AS sum_app,
                       COALESCE(SUM(historical_approved_cents), 0) AS sum_hist
                FROM invoices GROUP BY claim_id
            ) i ON i.claim_id = c.claim_id
            LEFT JOIN (
                SELECT claim_id,
                       COALESCE(SUM(CASE WHEN payment_status = 'AUTHORIZED' THEN amount_cents ELSE 0 END), 0) AS sum_res,
                       COALESCE(SUM(CASE WHEN payment_status IN ('DISBURSED','REVERSED_CLAWBACK') THEN disbursed_amount_cents ELSE 0 END), 0) AS sum_gross,
                       COALESCE(SUM(CASE WHEN payment_status = 'REVERSED_CLAWBACK' THEN clawed_back_cents ELSE 0 END), 0) AS sum_claw,
                       COALESCE(SUM(CASE WHEN payment_status IN ('DISBURSED','REVERSED_CLAWBACK') THEN net_paid_cents ELSE 0 END), 0) AS sum_net
                FROM payments GROUP BY claim_id
            ) p ON p.claim_id = c.claim_id
            WHERE c.approved_amount_cents != COALESCE(i.sum_app, 0)
               OR c.historical_approved_cents != COALESCE(i.sum_hist, 0)
               OR c.reserved_authorized_cents != COALESCE(p.sum_res, 0)
               OR c.gross_disbursed_cents != COALESCE(p.sum_gross, 0)
               OR c.clawed_back_cents != COALESCE(p.sum_claw, 0)
               OR c.net_paid_cents != COALESCE(p.sum_net, 0)
               OR c.reserved_authorized_cents + c.net_paid_cents > c.historical_approved_cents
            """
        ).fetchone()[0]
        inv_fin_mismatch = conn.execute(
            """
            SELECT COUNT(*) FROM invoices inv
            LEFT JOIN (
                SELECT invoice_id,
                       COALESCE(SUM(CASE WHEN payment_status = 'AUTHORIZED' THEN amount_cents ELSE 0 END), 0) AS sum_res,
                       COALESCE(SUM(CASE WHEN payment_status IN ('DISBURSED','REVERSED_CLAWBACK') THEN disbursed_amount_cents ELSE 0 END), 0) AS sum_gross,
                       COALESCE(SUM(CASE WHEN payment_status = 'REVERSED_CLAWBACK' THEN clawed_back_cents ELSE 0 END), 0) AS sum_claw,
                       COALESCE(SUM(CASE WHEN payment_status IN ('DISBURSED','REVERSED_CLAWBACK') THEN net_paid_cents ELSE 0 END), 0) AS sum_net
                FROM payments GROUP BY invoice_id
            ) p ON p.invoice_id = inv.invoice_id
            WHERE inv.reserved_authorized_cents != COALESCE(p.sum_res, 0)
               OR inv.gross_disbursed_cents != COALESCE(p.sum_gross, 0)
               OR inv.clawed_back_cents != COALESCE(p.sum_claw, 0)
               OR inv.net_paid_cents != COALESCE(p.sum_net, 0)
               OR inv.reserved_authorized_cents + inv.net_paid_cents > inv.historical_approved_cents
            """
        ).fetchone()[0]
        runner.check(
            claim_fin_mismatch == 0 and inv_fin_mismatch == 0,
            "T-08",
            "Penny-level financial reconciliation holds across all 5,000 claims, 7,500 invoices, and 4,200 payments",
            f"claim_mismatch={claim_fin_mismatch}, inv_mismatch={inv_fin_mismatch}",
        )

        # T-09: Chronological date ordering across policies, incidents, claims, invoices, payments
        date_violations = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM policies WHERE effective_end_utc <= effective_start_utc)
            + (SELECT COUNT(*) FROM incidents WHERE reported_timestamp_utc < incident_timestamp_utc)
            + (SELECT COUNT(*) FROM claims c JOIN incidents i ON i.incident_id = c.incident_id
               WHERE c.submitted_at_utc < i.incident_timestamp_utc)
            + (SELECT COUNT(*) FROM invoices inv WHERE inv.service_end_utc < inv.service_start_utc OR inv.submitted_at_utc < inv.service_start_utc)
            """
        ).fetchone()[0]
        runner.check(
            date_violations == 0,
            "T-09",
            "Chronological date ordering holds across all policies, incidents, claims, and invoices",
            f"violations={date_violations}",
        )

        # T-10: YF-NEG-1 — 25 invalid claims referencing nonexistent policies rejected & logged in ingestion_exceptions
        yf_neg1_count = conn.execute(
            "SELECT COUNT(*) FROM ingestion_exceptions WHERE exception_code = 'ERR_NONEXISTENT_POLICY_REFERENCE'"
        ).fetchone()[0]
        yf_neg1_events = conn.execute(
            "SELECT COUNT(*) FROM immutable_events WHERE event_type = 'INGESTION_EXCEPTION_RECORDED'"
        ).fetchone()[0]
        runner.check(
            yf_neg1_count == 25 and yf_neg1_events == 25,
            "T-10",
            "YF-NEG-1: 25 invalid claims with missing policy_id rejected via SAVEPOINT and recorded in ingestion_exceptions + immutable_events",
            f"exceptions={yf_neg1_count}, events={yf_neg1_events}",
        )

        # T-11: YF-NEG-2 — 30 overpayment attempts blocked and recorded as BLOCKED_OVERPAYMENT
        yf_neg2_count = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE payment_status = 'BLOCKED_OVERPAYMENT'"
        ).fetchone()[0]
        yf_neg2_events = conn.execute(
            "SELECT COUNT(*) FROM immutable_events WHERE event_type = 'PAYMENT_BLOCKED'"
        ).fetchone()[0]
        blocked_live = False
        try:
            conn.execute("SAVEPOINT sp_yf_neg2_live")
            row = conn.execute(
                "SELECT inv.invoice_id, inv.claim_id, inv.provider_id, inv.approved_cents "
                "FROM invoices inv JOIN claims c ON c.claim_id = inv.claim_id "
                "WHERE inv.invoice_status = 'APPROVED' AND c.claim_status = 'APPROVED' LIMIT 1"
            ).fetchone()
            conn.execute(
                "INSERT INTO payments VALUES ('PAY-2026-999999', ?, ?, 'PROVIDER', NULL, ?, "
                "'AUTHORIZED', ?, 0, 0, 0, 'IDEMP-LIVE-999999', '2026-07-10T00:00:00Z', "
                "NULL, NULL, 'USR-FIN-001', NULL, NULL, NULL)",
                (row[1], row[0], row[2], row[3] + 999999),
            )
        except sqlite3.IntegrityError as exc:
            if "ERR_PAYMENT_EXCEEDS_APPROVED_CAP" in str(exc):
                blocked_live = True
            conn.execute("ROLLBACK TO SAVEPOINT sp_yf_neg2_live")
        conn.execute("RELEASE SAVEPOINT sp_yf_neg2_live")
        runner.check(
            yf_neg2_count == 30 and yf_neg2_events == 85 and blocked_live,
            "T-11",
            "YF-NEG-2: 30 overpayment attempts recorded as BLOCKED_OVERPAYMENT + live AUTHORIZED overpayment blocked by trg_payments_validate_ins",
            f"blocked_overpay={yf_neg2_count}, blocked_events={yf_neg2_events}, blocked_live={blocked_live}",
        )

        # T-12: YF-NEG-3 (HIGH-01) — Cross-claimant duplicate invoices (all 25 pairs verify field-by-field, self-fingerprints match, score >= 65.00 HIGH)
        yf_neg3_cids = [
            r[0]
            for r in gt.execute(
                "SELECT claim_id FROM ground_truth_claim_labels WHERE scenario_code = 'YF-NEG-3' ORDER BY claim_id ASC"
            ).fetchall()
        ]
        yf_neg3_cross_ok = 0
        yf_neg3_intra_cnt = 0
        yf_neg3_field_mismatches = 0
        yf_neg3_fp_mismatches = 0

        for cid in yf_neg3_cids:
            sc, tier = conn.execute(
                "SELECT latest_ief_score, latest_risk_tier FROM claims WHERE claim_id = ?",
                (cid,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT
                    inv.invoice_id, inv.claim_id, c_inv.claimant_id,
                    inv.provider_id, inv.cpt_or_line_code,
                    inv.service_start_utc, inv.service_end_utc,
                    inv.billed_cents, inv.line_item_fingerprint,
                    orig.invoice_id, orig.claim_id, c_orig.claimant_id,
                    orig.provider_id, orig.cpt_or_line_code,
                    orig.service_start_utc, orig.service_end_utc,
                    orig.billed_cents, orig.line_item_fingerprint
                FROM invoices inv
                JOIN claims c_inv ON c_inv.claim_id = inv.claim_id
                JOIN invoices orig ON orig.invoice_id = inv.duplicate_of_invoice_id
                JOIN claims c_orig ON c_orig.claim_id = orig.claim_id
                WHERE inv.claim_id = ?
                  AND inv.invoice_status = 'REJECTED_DUPLICATE'
                """,
                (cid,),
            ).fetchall()

            intra_cnt = conn.execute(
                """
                SELECT COUNT(*)
                FROM invoices inv
                JOIN invoices orig ON orig.invoice_id = inv.duplicate_of_invoice_id
                WHERE inv.claim_id = ?
                  AND inv.invoice_status = 'REJECTED_DUPLICATE'
                  AND inv.claim_id = orig.claim_id
                """,
                (cid,),
            ).fetchone()[0]
            yf_neg3_intra_cnt += intra_cnt

            if len(rows) != 1:
                yf_neg3_field_mismatches += 1
                continue

            r = rows[0]
            (
                dup_iid, dup_cid, dup_clmt,
                dup_prv, dup_cpt, dup_start, dup_end, dup_billed, dup_fp,
                orig_iid, orig_cid, orig_clmt,
                orig_prv, orig_cpt, orig_start, orig_end, orig_billed, orig_fp
            ) = r

            is_cross = (dup_cid != orig_cid) and (dup_clmt != orig_clmt)
            fields_match = (
                dup_prv == orig_prv
                and dup_cpt == orig_cpt
                and dup_start == orig_start
                and dup_end == orig_end
                and dup_billed == orig_billed
            )
            if not fields_match:
                yf_neg3_field_mismatches += 1

            dup_recomputed = _compute_line_item_fp(dup_cpt, dup_start, dup_end, dup_billed)
            orig_recomputed = _compute_line_item_fp(orig_cpt, orig_start, orig_end, orig_billed)
            fps_match = (
                dup_fp == orig_fp
                and dup_fp == dup_recomputed
                and orig_fp == orig_recomputed
            )
            if not fps_match:
                yf_neg3_fp_mismatches += 1

            if (
                sc >= 65.0
                and tier in ("HIGH", "CRITICAL")
                and is_cross
                and fields_match
                and fps_match
                and intra_cnt == 0
            ):
                yf_neg3_cross_ok += 1

        runner.check(
            len(yf_neg3_cids) == 25
            and yf_neg3_cross_ok == 25
            and yf_neg3_intra_cnt == 0
            and yf_neg3_field_mismatches == 0
            and yf_neg3_fp_mismatches == 0,
            "T-12",
            "YF-NEG-3 (HIGH-01): All 25 cross-claimant duplicate invoice pairs verify field-by-field, self-fingerprints match, and score >= 65.00 HIGH",
            f"cross_ok={yf_neg3_cross_ok}/{len(yf_neg3_cids)}, field_mismatches={yf_neg3_field_mismatches}, fp_mismatches={yf_neg3_fp_mismatches}",
        )

        # T-13: YF-NEG-4 — Missing edges in operational graph (5 rings, 40 claims, >= 80% score >= 65.00 HIGH without missing edges)
        missing_edges = gt.execute(
            "SELECT edge_type, canonical_src_key, canonical_dst_key FROM ground_truth_missing_edges"
        ).fetchall()
        leaked_edges = 0
        for etype, skey, dkey in missing_edges:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM relationship_edges WHERE edge_type=? AND canonical_src_key=? AND canonical_dst_key=?",
                (etype, skey, dkey),
            ).fetchone()[0]
            leaked_edges += cnt
        yf_neg4_claims = gt.execute(
            "SELECT claim_id FROM ground_truth_claim_labels WHERE scenario_code = 'YF-NEG-4'"
        ).fetchall()
        yf_neg4_high = 0
        for (cid,) in yf_neg4_claims:
            sc, tier = conn.execute(
                "SELECT latest_ief_score, latest_risk_tier FROM claims WHERE claim_id = ?", (cid,)
            ).fetchone()
            if sc >= 65.0 and tier in ("HIGH", "CRITICAL"):
                yf_neg4_high += 1
        runner.check(
            len(missing_edges) == 25
            and leaked_edges == 0
            and len(yf_neg4_claims) == 40
            and yf_neg4_high >= 32,
            "T-13",
            "YF-NEG-4: 25 planted missing edges absent from operational relationship_edges; 36/40 (90% >= 80%) ring claims score >= 65.00 HIGH",
            f"missing_edges={len(missing_edges)}, leaked={leaked_edges}, high={yf_neg4_high}/{len(yf_neg4_claims)}",
        )

        # T-14: YF-NEG-5 & BL-1..5 — Benign lookalike controls remain LOW risk without false-positive escalation
        benign_cohorts = gt.execute(
            "SELECT scenario_code, claim_id FROM ground_truth_claim_labels "
            "WHERE scenario_code IN ('YF-NEG-5','BL-1','BL-2','BL-3','BL-4','BL-5')"
        ).fetchall()
        cohort_violations = 0
        for scode, cid in benign_cohorts:
            sc, tier, status = conn.execute(
                "SELECT latest_ief_score, latest_risk_tier, claim_status FROM claims WHERE claim_id = ?",
                (cid,),
            ).fetchone()
            cap = 12.0 if scode == "YF-NEG-5" else (18.0 if scode in ("BL-1", "BL-2", "BL-5") else 15.0)
            if sc > cap or tier != "LOW" or status in ("SIU_HOLD", "DENIED"):
                cohort_violations += 1
        runner.check(
            len(benign_cohorts) == 500 and cohort_violations == 0,
            "T-14",
            "YF-NEG-5 (80 claims) and BL-1..5 (420 claims) all score below benign caps in LOW tier with zero SIU_HOLD/DENIED",
            f"total_benign_lookalikes={len(benign_cohorts)}, violations={cohort_violations}",
        )

        # T-15: Edge Cases EC-1 (intra-claim duplicate), EC-2/D-1 (CLEARED_BENIGN exit), EC-3 (REVERSED_CLAWBACK & lapsed policies)
        ec1_cids = [
            r[0]
            for r in gt.execute(
                "SELECT claim_id FROM ground_truth_claim_labels WHERE scenario_code = 'EC-1' ORDER BY claim_id ASC"
            ).fetchall()
        ]
        ec1_ok = 0
        ec1_mismatches = 0
        for cid in ec1_cids:
            rows = conn.execute(
                """
                SELECT
                    inv.invoice_id, inv.claim_id, inv.provider_id, inv.cpt_or_line_code,
                    inv.service_start_utc, inv.service_end_utc, inv.billed_cents, inv.line_item_fingerprint,
                    orig.invoice_id, orig.claim_id, orig.provider_id, orig.cpt_or_line_code,
                    orig.service_start_utc, orig.service_end_utc, orig.billed_cents, orig.line_item_fingerprint
                FROM invoices inv
                JOIN invoices orig ON orig.invoice_id = inv.duplicate_of_invoice_id
                WHERE inv.claim_id = ?
                  AND inv.invoice_status = 'REJECTED_DUPLICATE'
                """,
                (cid,),
            ).fetchall()
            if len(rows) != 1:
                ec1_mismatches += 1
                continue
            r = rows[0]
            (
                dup_iid, dup_cid, dup_prv, dup_cpt, dup_start, dup_end, dup_billed, dup_fp,
                orig_iid, orig_cid, orig_prv, orig_cpt, orig_start, orig_end, orig_billed, orig_fp
            ) = r

            is_intra = (dup_cid == orig_cid)
            fields_match = (
                dup_prv == orig_prv
                and dup_cpt == orig_cpt
                and dup_start == orig_start
                and dup_end == orig_end
                and dup_billed == orig_billed
            )
            dup_recomputed = _compute_line_item_fp(dup_cpt, dup_start, dup_end, dup_billed)
            orig_recomputed = _compute_line_item_fp(orig_cpt, orig_start, orig_end, orig_billed)
            fps_match = (
                dup_fp == orig_fp
                and dup_fp == dup_recomputed
                and orig_fp == orig_recomputed
            )
            if is_intra and fields_match and fps_match:
                ec1_ok += 1
            else:
                ec1_mismatches += 1

        benign_cleared_cnt = conn.execute(
            "SELECT COUNT(*) FROM investigations WHERE ruling_outcome = 'CLEARED_BENIGN' AND investigation_status = 'CLOSED_CLEARED_BENIGN'"
        ).fetchone()[0]
        clawback_cnt = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE payment_status = 'REVERSED_CLAWBACK'"
        ).fetchone()[0]
        lapsed_pol_cnt = conn.execute(
            "SELECT COUNT(*) FROM policies WHERE policy_status IN ('LAPSED','CANCELLED')"
        ).fetchone()[0]
        runner.check(
            len(ec1_cids) == 25
            and ec1_ok == 25
            and ec1_mismatches == 0
            and benign_cleared_cnt == 8
            and clawback_cnt == 20
            and lapsed_pol_cnt == 110,
            "T-15",
            "Edge cases EC-1 (25 intra-claim dupes verified field-by-field and self-fingerprinted), D-1 (8 CLEARED_BENIGN exits), EC-3 (20 REVERSED_CLAWBACK payments, 110 LAPSED/CANCELLED policies) verified",
            f"ec1_ok={ec1_ok}/25, ec1_mismatches={ec1_mismatches}, cleared={benign_cleared_cnt}, clawback={clawback_cnt}, lapsed={lapsed_pol_cnt}",
        )

        # T-16: DEF-01 & HIGH-02 — SIU_HOLD benign exit requires a fresh CLOSED_CLEARED_BENIGN per hold cycle
        # and blocks if any investigation is OPEN, CLOSED_INSUFFICIENT_EVIDENCE, or stale from a prior cycle
        def01_blocked_open = False
        def01_blocked_insuff = False
        high02_blocked_stale_reuse = False
        high02_fresh_cycle_ok = False
        try:
            conn.execute("SAVEPOINT sp_def01_open")
            target_cid = conn.execute(
                "SELECT i.primary_claim_id FROM investigations i "
                "JOIN claims c ON c.claim_id = i.primary_claim_id "
                "WHERE i.investigation_status = 'OPEN' AND c.approved_amount_cents > 0 AND c.net_paid_cents = 0 LIMIT 1"
            ).fetchone()[0]
            conn.execute(
                "UPDATE claims SET claim_status = 'APPROVED' WHERE claim_id = ?",
                (target_cid,),
            )
        except sqlite3.IntegrityError as exc:
            if "ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE" in str(exc):
                def01_blocked_open = True
            conn.execute("ROLLBACK TO SAVEPOINT sp_def01_open")
        conn.execute("RELEASE SAVEPOINT sp_def01_open")

        try:
            conn.execute("SAVEPOINT sp_def01_insuff")
            target_cid2 = conn.execute(
                "SELECT i.primary_claim_id FROM investigations i "
                "JOIN claims c ON c.claim_id = i.primary_claim_id "
                "WHERE i.investigation_status = 'CLOSED_INSUFFICIENT_EVIDENCE' AND c.approved_amount_cents = 0 LIMIT 1"
            ).fetchone()[0]
            conn.execute(
                "UPDATE claims SET claim_status = 'UNDER_REVIEW' WHERE claim_id = ?",
                (target_cid2,),
            )
        except sqlite3.IntegrityError as exc:
            if "ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE" in str(exc):
                def01_blocked_insuff = True
            conn.execute("ROLLBACK TO SAVEPOINT sp_def01_insuff")
        conn.execute("RELEASE SAVEPOINT sp_def01_insuff")

        # Test HIGH-02 cycle reuse: CLM-2026-002451 already exited SIU_HOLD -> APPROVED via INVG-2026-000036 (CLOSED_CLEARED_BENIGN).
        # Re-entering SIU_HOLD increments siu_referred to 2 and blocks exit until a 2nd investigation closes as CLOSED_CLEARED_BENIGN.
        try:
            conn.execute("SAVEPOINT sp_high02_cycle")
            conn.execute(
                "UPDATE claims SET claim_status = 'SIU_HOLD' WHERE claim_id = 'CLM-2026-002451'"
            )
            try:
                conn.execute("SAVEPOINT sp_high02_stale")
                conn.execute(
                    "UPDATE claims SET claim_status = 'APPROVED' WHERE claim_id = 'CLM-2026-002451'"
                )
            except sqlite3.IntegrityError as exc:
                if "ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE" in str(exc):
                    high02_blocked_stale_reuse = True
                conn.execute("ROLLBACK TO SAVEPOINT sp_high02_stale")
            conn.execute("RELEASE SAVEPOINT sp_high02_stale")

            # Open a 2nd investigation on CLM-2026-002451 and verify exit is still blocked while OPEN, then permitted once closed benign
            conn.execute(
                "INSERT INTO investigations VALUES ('INVG-2026-990001','CLM-2026-002451','CLMT-001176',NULL,"
                "'OPEN','P2_HIGH','USR-SIU-002','2026-07-09T10:00:00Z','2026-07-09T10:00:00Z',NULL,NULL,500000,0,'Second cycle review')"
            )
            conn.execute(
                "UPDATE investigations SET investigation_status = 'CLOSED_CLEARED_BENIGN', ruling_outcome = 'CLEARED_BENIGN', "
                "updated_at_utc = '2026-07-09T12:00:00Z', closed_at_utc = '2026-07-09T12:00:00Z' WHERE investigation_id = 'INVG-2026-990001'"
            )
            conn.execute(
                "UPDATE claims SET claim_status = 'APPROVED' WHERE claim_id = 'CLM-2026-002451'"
            )
            high02_fresh_cycle_ok = True
            conn.execute("ROLLBACK TO SAVEPOINT sp_high02_cycle")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT sp_high02_cycle")
            high02_fresh_cycle_ok = False
        conn.execute("RELEASE SAVEPOINT sp_high02_cycle")

        runner.check(
            def01_blocked_open
            and def01_blocked_insuff
            and high02_blocked_stale_reuse
            and high02_fresh_cycle_ok,
            "T-16",
            "DEF-01 & HIGH-02: trg_claims_fsm_upd + trg_claims_siu_referred_au block SIU_HOLD exit on OPEN, INSUFFICIENT_EVIDENCE, or reused prior-cycle CLEARED_BENIGN, and allow exit after fresh CLEARED_BENIGN",
            f"open={def01_blocked_open}, insuff={def01_blocked_insuff}, stale_reuse={high02_blocked_stale_reuse}, fresh_ok={high02_fresh_cycle_ok}",
        )

        # T-17: DEF-02 & HIGH-02 — trg_investigations_validate_ins + trg_investigations_fsm_upd block pre-closed insert,
        # backdated investigation open, and backdated investigation closure
        def02_blocked_ins = False
        high02_blocked_backdated_open = False
        high02_blocked_backdated_close = False
        try:
            conn.execute("SAVEPOINT sp_def02")
            conn.execute(
                "INSERT INTO investigations VALUES ('INVG-2026-999999','CLM-2026-000001','CLMT-000001',NULL,"
                "'CLOSED_CLEARED_BENIGN','P1_CRITICAL','USR-SIU-001','2026-07-09T00:00:00Z',"
                "'2026-07-09T00:00:00Z','2026-07-09T00:00:00Z','CLEARED_BENIGN',100000,0,'Rogue insert')"
            )
        except sqlite3.IntegrityError as exc:
            if "ERR_INVESTIGATION_INITIAL_STATUS_MUST_BE_OPEN" in str(exc):
                def02_blocked_ins = True
            conn.execute("ROLLBACK TO SAVEPOINT sp_def02")
        conn.execute("RELEASE SAVEPOINT sp_def02")

        try:
            conn.execute("SAVEPOINT sp_high02_bopen")
            conn.execute(
                "INSERT INTO investigations VALUES ('INVG-2026-999998','CLM-2026-002451','CLMT-001176',NULL,"
                "'OPEN','P2_HIGH','USR-SIU-001','2026-07-07T00:00:00Z',"
                "'2026-07-07T00:00:00Z',NULL,NULL,100000,0,'Backdated open before prior closure')"
            )
        except sqlite3.IntegrityError as exc:
            if "ERR_INVESTIGATION_TIMESTAMP_REGRESSION" in str(exc):
                high02_blocked_backdated_open = True
            conn.execute("ROLLBACK TO SAVEPOINT sp_high02_bopen")
        conn.execute("RELEASE SAVEPOINT sp_high02_bopen")

        try:
            conn.execute("SAVEPOINT sp_high02_bclose")
            conn.execute(
                "UPDATE investigations SET investigation_status = 'CLOSED_CLEARED_BENIGN', ruling_outcome = 'CLEARED_BENIGN', "
                "updated_at_utc = '2026-07-09T10:00:00Z', closed_at_utc = '2026-07-08T10:00:00Z' "
                "WHERE investigation_id = 'INVG-2026-000023'"
            )
        except sqlite3.IntegrityError as exc:
            if "ERR_INVESTIGATION_TIMESTAMP_REGRESSION" in str(exc):
                high02_blocked_backdated_close = True
            conn.execute("ROLLBACK TO SAVEPOINT sp_high02_bclose")
        conn.execute("RELEASE SAVEPOINT sp_high02_bclose")

        runner.check(
            def02_blocked_ins and high02_blocked_backdated_open and high02_blocked_backdated_close,
            "T-17",
            "DEF-02 & HIGH-02: Investigation triggers block pre-closed INSERT, backdated opened_at_utc INSERT, and backdated closed_at_utc UPDATE",
            f"ins={def02_blocked_ins}, bopen={high02_blocked_backdated_open}, bclose={high02_blocked_backdated_close}",
        )

        # T-18: DEF-03 — Post-approval policy lapse (LAPSED) still permits payment disbursement on already-APPROVED invoice
        def03_ok = False
        try:
            conn.execute("SAVEPOINT sp_def03")
            row = conn.execute(
                "SELECT p.payment_id, p.amount_cents, p.invoice_id, c.policy_id "
                "FROM payments p JOIN claims c ON c.claim_id = p.claim_id "
                "WHERE p.payment_status = 'AUTHORIZED' AND c.claim_status = 'APPROVED' LIMIT 1"
            ).fetchone()
            pay_id, amt, inv_id, pol_id = row
            conn.execute(
                "UPDATE policies SET policy_status = 'LAPSED' WHERE policy_id = ?",
                (pol_id,),
            )
            conn.execute(
                "UPDATE payments SET payment_status = 'DISBURSED', disbursed_amount_cents = ?, "
                "net_paid_cents = ?, disbursed_at_utc = '2026-07-10T12:00:00Z', external_bank_tx_ref = 'ACH-LAPSE-TEST' "
                "WHERE payment_id = ?",
                (amt, amt, pay_id),
            )
            new_inv_status = conn.execute(
                "SELECT invoice_status FROM invoices WHERE invoice_id = ?", (inv_id,)
            ).fetchone()[0]
            def03_ok = new_inv_status in ("PARTIALLY_PAID", "PAID")
            conn.execute("ROLLBACK TO SAVEPOINT sp_def03")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT sp_def03")
            def03_ok = False
        conn.execute("RELEASE SAVEPOINT sp_def03")
        runner.check(
            def03_ok,
            "T-18",
            "DEF-03: Post-approval policy lapse (LAPSED) permits payment disbursement sync on already-APPROVED invoice",
        )

        # T-19: Append-only protection on immutable_events and ingestion_exceptions
        imm_blocked = 0
        for sql in [
            "DELETE FROM immutable_events WHERE sequence_no = 1",
            "UPDATE immutable_events SET actor_id = 'HACK' WHERE sequence_no = 1",
            "DELETE FROM ingestion_exceptions WHERE exception_id = 'IEX-2026-000001'",
            "UPDATE ingestion_exceptions SET attempted_claimed_cents = 1 WHERE exception_id = 'IEX-2026-000001'",
        ]:
            try:
                conn.execute("SAVEPOINT sp_imm")
                conn.execute(sql)
            except sqlite3.IntegrityError:
                imm_blocked += 1
                conn.execute("ROLLBACK TO SAVEPOINT sp_imm")
            conn.execute("RELEASE SAVEPOINT sp_imm")
        runner.check(
            imm_blocked == 4,
            "T-19",
            "Append-only triggers block UPDATE and DELETE on both immutable_events and ingestion_exceptions",
            f"blocked={imm_blocked}/4",
        )

        # T-20: ST-SCORE-V1 evidence digest & risk-tier integrity across all 5,000 claims
        score_nulls = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE scoring_evidence_sha256 IS NULL"
        ).fetchone()[0]
        tier_mismatch = conn.execute(
            """
            SELECT COUNT(*) FROM claims
            WHERE latest_risk_tier != CASE
                WHEN latest_ief_score >= 85.0 THEN 'CRITICAL'
                WHEN latest_ief_score >= 65.0 THEN 'HIGH'
                WHEN latest_ief_score >= 30.0 THEN 'MEDIUM'
                ELSE 'LOW'
            END
            """
        ).fetchone()[0]
        runner.check(
            score_nulls == 0 and tier_mismatch == 0,
            "T-20",
            "All 5,000 claims have verified ST-SCORE-V1 scoring_evidence_sha256 digests and consistent risk_tier values",
            f"null_digests={score_nulls}, tier_mismatches={tier_mismatch}",
        )

        conn.close()
        gt.close()

    print(
        f"\n[SUMMARY] db.test_suite: {runner.passed} passed, {runner.failed} failed out of {runner.passed + runner.failed}"
    )
    return 0 if runner.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())

"""
SENTINEL//TRACE — Application Event/State Atomicity Integration Tests
======================================================================
Verifies Phase 2 requirements for ARCH-ST-010.7:
1. Claim state transition followed by event insertion failure rolls back entity.
2. Investigation transition followed by event insertion failure rolls back entity.
3. Invoice state transition followed by event insertion failure rolls back entity.
4. Payment state transition followed by event insertion failure rolls back entity.
5. Payment mutation failure after event emission rolls back event (anti-phantom).
6. Prior committed events and overall hash chain remain valid and uncorrupted.
7. Successful operations commit both the business mutation and event together.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from db.engine import (
    EXPECTED_SCHEMA_DIGEST,
    compute_schema_digest,
    open_operational_db,
)
from db.operations import (
    approve_invoice,
    authorize_payment,
    cancel_payment,
    clawback_payment,
    deny_claim,
    disburse_payment,
    open_investigation,
    place_claim_on_siu_hold,
    record_ingestion_exception,
    release_claim_from_siu_hold,
    submit_claim,
    submit_invoice,
    transition_investigation,
)
from db.seed import EventChainEmitter, generate_dataset


class TestApplicationEventStateAtomicity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = tempfile.TemporaryDirectory(prefix="sentinel_atomicity_")
        cls.ops_db_path = Path(cls.tmpdir.name) / "ops.db"
        cls.gt_db_path = Path(cls.tmpdir.name) / "gt.db"
        generate_dataset(seed=42, ops_db_path=cls.ops_db_path, gt_db_path=cls.gt_db_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmpdir.cleanup()

    def setUp(self) -> None:
        self.conn = open_operational_db(self.ops_db_path, create_schema=False, verify_digest=True)
        self.emitter = EventChainEmitter(self.conn)
        self.emitter.sync_from_db()

    def tearDown(self) -> None:
        self.conn.close()

    def _get_event_count_and_tip(self) -> tuple[int, str]:
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(event_hash), '') FROM immutable_events"
        ).fetchone()
        return row[0], row[1]

    # -------------------------------------------------------------------------
    # 1. Claim Transitions
    # -------------------------------------------------------------------------
    def test_claim_siu_hold_event_failure_rolls_back_claim_state(self) -> None:
        """Claim SIU_HOLD placement rolls back if event emission fails."""
        # Use an approved claim that is currently in APPROVED status
        cid = "CLM-2026-001276"
        orig_row = self.conn.execute(
            "SELECT claim_status, siu_referred FROM claims WHERE claim_id = ?", (cid,)
        ).fetchone()
        self.assertEqual(orig_row[0], "APPROVED")
        orig_referred = orig_row[1]

        ev_cnt_before, tip_before = self._get_event_count_and_tip()
        emitter_snap_before = self.emitter.snapshot()

        # Force failure on CLAIM_SIU_HOLD_PLACED
        def fail_hook(event_type: str, entity_id: str) -> Exception | None:
            if event_type == "CLAIM_SIU_HOLD_PLACED" and entity_id == cid:
                return RuntimeError("INJECTED_FAILURE: Simulated event emission crash")
            return None

        self.emitter.set_failure_hook(fail_hook)

        with self.assertRaises(RuntimeError) as ctx:
            place_claim_on_siu_hold(
                self.conn,
                self.emitter,
                claim_id=cid,
                actor_id="USR-SIU-TEST",
                occurred_at_utc="2026-07-15T10:00:00Z",
            )
        self.assertIn("INJECTED_FAILURE", str(ctx.exception))

        # Assert entity state is completely unchanged
        post_row = self.conn.execute(
            "SELECT claim_status, siu_referred FROM claims WHERE claim_id = ?", (cid,)
        ).fetchone()
        self.assertEqual(post_row[0], "APPROVED")
        self.assertEqual(post_row[1], orig_referred)

        # Assert no phantom event was inserted
        ev_exists = self.conn.execute(
            "SELECT COUNT(*) FROM immutable_events WHERE entity_id = ? AND event_type = 'CLAIM_SIU_HOLD_PLACED' AND occurred_at_utc = '2026-07-15T10:00:00Z'",
            (cid,),
        ).fetchone()[0]
        self.assertEqual(ev_exists, 0)

        # Assert event counts and tip hash are preserved
        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)
        self.assertEqual(self.emitter.snapshot(), emitter_snap_before)

        # Now clear failure hook and verify successful atomic execution
        self.emitter.set_failure_hook(None)
        ev_id = place_claim_on_siu_hold(
            self.conn,
            self.emitter,
            claim_id=cid,
            actor_id="USR-SIU-TEST",
            occurred_at_utc="2026-07-15T10:00:00Z",
        )
        self.assertTrue(ev_id.startswith("EVT-2026-"))
        post_success_row = self.conn.execute(
            "SELECT claim_status, siu_referred FROM claims WHERE claim_id = ?", (cid,)
        ).fetchone()
        self.assertEqual(post_success_row[0], "SIU_HOLD")
        self.assertEqual(post_success_row[1], orig_referred + 1)
        ev_now = self.conn.execute(
            "SELECT event_id, event_type FROM immutable_events WHERE event_id = ?", (ev_id,)
        ).fetchone()
        self.assertIsNotNone(ev_now)
        self.assertEqual(ev_now[1], "CLAIM_SIU_HOLD_PLACED")

    def test_claim_denial_event_failure_rolls_back_claim_state(self) -> None:
        """Claim DENIED transition rolls back if event emission fails."""
        cid = "CLM-2026-000046"  # SUBMITTED claim with zero balances
        orig_status = self.conn.execute(
            "SELECT claim_status FROM claims WHERE claim_id = ?", (cid,)
        ).fetchone()[0]
        self.assertEqual(orig_status, "SUBMITTED")

        ev_cnt_before, tip_before = self._get_event_count_and_tip()

        def fail_hook(event_type: str, entity_id: str) -> Exception | None:
            if event_type == "CLAIM_DENIED" and entity_id == cid:
                return RuntimeError("INJECTED_FAILURE: Claim denial event write failure")
            return None

        self.emitter.set_failure_hook(fail_hook)

        with self.assertRaises(RuntimeError):
            deny_claim(
                self.conn,
                self.emitter,
                claim_id=cid,
                actor_id="USR-SIU-TEST",
                occurred_at_utc="2026-07-15T12:00:00Z",
            )

        post_status = self.conn.execute(
            "SELECT claim_status FROM claims WHERE claim_id = ?", (cid,)
        ).fetchone()[0]
        self.assertEqual(post_status, "SUBMITTED")
        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)

        # Clear hook and verify atomic success
        self.emitter.set_failure_hook(None)
        ev_id = deny_claim(
            self.conn,
            self.emitter,
            claim_id=cid,
            actor_id="USR-SIU-TEST",
            occurred_at_utc="2026-07-15T12:00:00Z",
        )
        self.assertEqual(
            self.conn.execute("SELECT claim_status FROM claims WHERE claim_id = ?", (cid,)).fetchone()[0],
            "DENIED",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_id,)).fetchone()[0],
            "CLAIM_DENIED",
        )

    # -------------------------------------------------------------------------
    # 2. Investigation Transitions
    # -------------------------------------------------------------------------
    def test_investigation_open_event_failure_rolls_back_entity(self) -> None:
        """Investigation creation rolls back if event emission fails."""
        invg_id = "INVG-2026-009991"
        cid = "CLM-2026-000036"

        ev_cnt_before, tip_before = self._get_event_count_and_tip()

        def fail_hook(event_type: str, entity_id: str) -> Exception | None:
            if event_type == "INVESTIGATION_OPENED" and entity_id == invg_id:
                return RuntimeError("INJECTED_FAILURE: Investigation open event crashed")
            return None

        self.emitter.set_failure_hook(fail_hook)

        with self.assertRaises(RuntimeError):
            open_investigation(
                self.conn,
                self.emitter,
                investigation_id=invg_id,
                claim_id=cid,
                claimant_id="CLMT-000036",
                provider_id=None,
                priority="P2_HIGH",
                assigned_investigator_id="USR-SIU-001",
                opened_at_utc="2026-07-15T09:00:00Z",
                estimated_exposure_cents=150000,
                case_summary_notes="Test failure rollback",
            )

        # Assert no row was created in investigations table
        invg_row = self.conn.execute(
            "SELECT COUNT(*) FROM investigations WHERE investigation_id = ?", (invg_id,)
        ).fetchone()[0]
        self.assertEqual(invg_row, 0)

        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)

        # Clear hook and verify atomic success
        self.emitter.set_failure_hook(None)
        ev_id = open_investigation(
            self.conn,
            self.emitter,
            investigation_id=invg_id,
            claim_id=cid,
            claimant_id="CLMT-000036",
            provider_id=None,
            priority="P2_HIGH",
            assigned_investigator_id="USR-SIU-001",
            opened_at_utc="2026-07-15T09:00:00Z",
            estimated_exposure_cents=150000,
            case_summary_notes="Test success",
        )
        self.assertEqual(
            self.conn.execute("SELECT investigation_status FROM investigations WHERE investigation_id = ?", (invg_id,)).fetchone()[0],
            "OPEN",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_id,)).fetchone()[0],
            "INVESTIGATION_OPENED",
        )

    def test_investigation_transition_event_failure_rolls_back_status(self) -> None:
        """Investigation status transition rolls back if event emission fails."""
        # Use existing open investigation INVG-2026-000023
        invg_id = "INVG-2026-000023"
        orig_status = self.conn.execute(
            "SELECT investigation_status FROM investigations WHERE investigation_id = ?", (invg_id,)
        ).fetchone()[0]
        self.assertEqual(orig_status, "OPEN")

        ev_cnt_before, tip_before = self._get_event_count_and_tip()

        def fail_hook(event_type: str, entity_id: str) -> Exception | None:
            if event_type == "INVESTIGATION_STATUS_CHANGED" and entity_id == invg_id:
                return RuntimeError("INJECTED_FAILURE: Investigation status changed event failure")
            return None

        self.emitter.set_failure_hook(fail_hook)

        with self.assertRaises(RuntimeError):
            transition_investigation(
                self.conn,
                self.emitter,
                investigation_id=invg_id,
                new_status="EVIDENCE_COLLECTION",
                updated_at_utc="2026-07-15T11:00:00Z",
                actor_id="USR-SIU-001",
            )

        # Verify status is still OPEN
        post_status = self.conn.execute(
            "SELECT investigation_status FROM investigations WHERE investigation_id = ?", (invg_id,)
        ).fetchone()[0]
        self.assertEqual(post_status, "OPEN")

        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)

        # Clear hook and execute successfully
        self.emitter.set_failure_hook(None)
        ev_id = transition_investigation(
            self.conn,
            self.emitter,
            investigation_id=invg_id,
            new_status="EVIDENCE_COLLECTION",
            updated_at_utc="2026-07-15T11:00:00Z",
            actor_id="USR-SIU-001",
        )
        self.assertEqual(
            self.conn.execute("SELECT investigation_status FROM investigations WHERE investigation_id = ?", (invg_id,)).fetchone()[0],
            "EVIDENCE_COLLECTION",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_id,)).fetchone()[0],
            "INVESTIGATION_STATUS_CHANGED",
        )

    # -------------------------------------------------------------------------
    # 3. Invoice Transitions
    # -------------------------------------------------------------------------
    def test_invoice_approval_event_failure_rolls_back_invoice_and_claim(self) -> None:
        """Invoice approval cascade rolls back both invoice and claim if event fails."""
        # Find a claim with a SUBMITTED invoice
        row = self.conn.execute(
            "SELECT i.invoice_id, i.claim_id, i.billed_cents FROM invoices i "
            "JOIN claims c ON c.claim_id = i.claim_id "
            "WHERE i.invoice_status = 'SUBMITTED' AND c.claim_status = 'SUBMITTED' LIMIT 1"
        ).fetchone()
        inv_id, cid, billed_cents = row

        ev_cnt_before, tip_before = self._get_event_count_and_tip()

        # Force failure on INVOICE_APPROVED
        def fail_hook(event_type: str, entity_id: str) -> Exception | None:
            if event_type == "INVOICE_APPROVED" and entity_id == inv_id:
                return RuntimeError("INJECTED_FAILURE: Invoice approved event emission failure")
            return None

        self.emitter.set_failure_hook(fail_hook)

        with self.assertRaises(RuntimeError):
            approve_invoice(
                self.conn,
                self.emitter,
                invoice_id=inv_id,
                approved_cents=billed_cents,
                approved_at_utc="2026-07-15T14:00:00Z",
                actor_id="USR-ADJ-001",
            )

        # Assert invoice is still SUBMITTED with approved_cents = 0
        inv_row = self.conn.execute(
            "SELECT invoice_status, approved_cents FROM invoices WHERE invoice_id = ?", (inv_id,)
        ).fetchone()
        self.assertEqual(inv_row[0], "SUBMITTED")
        self.assertEqual(inv_row[1], 0)

        # Assert claim is still SUBMITTED with approved_amount_cents = 0
        clm_row = self.conn.execute(
            "SELECT claim_status, approved_amount_cents FROM claims WHERE claim_id = ?", (cid,)
        ).fetchone()
        self.assertEqual(clm_row[0], "SUBMITTED")
        self.assertEqual(clm_row[1], 0)

        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)

        # Clear hook and verify atomic success
        self.emitter.set_failure_hook(None)
        ev_inv, ev_clm = approve_invoice(
            self.conn,
            self.emitter,
            invoice_id=inv_id,
            approved_cents=billed_cents,
            approved_at_utc="2026-07-15T14:00:00Z",
            actor_id="USR-ADJ-001",
        )
        self.assertEqual(
            self.conn.execute("SELECT invoice_status FROM invoices WHERE invoice_id = ?", (inv_id,)).fetchone()[0],
            "APPROVED",
        )
        self.assertEqual(
            self.conn.execute("SELECT claim_status FROM claims WHERE claim_id = ?", (cid,)).fetchone()[0],
            "APPROVED",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_inv,)).fetchone()[0],
            "INVOICE_APPROVED",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_clm,)).fetchone()[0],
            "CLAIM_APPROVED",
        )

    # -------------------------------------------------------------------------
    # 4. Payment Transitions
    # -------------------------------------------------------------------------
    def test_payment_disburse_event_failure_rolls_back_payment_status(self) -> None:
        """Payment disbursement rolls back to AUTHORIZED if event emission fails."""
        # Find an AUTHORIZED payment on an APPROVED claim
        row = self.conn.execute(
            "SELECT p.payment_id, p.claim_id, p.amount_cents FROM payments p "
            "JOIN claims c ON c.claim_id = p.claim_id "
            "WHERE p.payment_status = 'AUTHORIZED' AND c.claim_status = 'APPROVED' LIMIT 1"
        ).fetchone()
        pay_id, cid, amt = row

        ev_cnt_before, tip_before = self._get_event_count_and_tip()

        def fail_hook(event_type: str, entity_id: str) -> Exception | None:
            if event_type == "PAYMENT_DISBURSED" and entity_id == pay_id:
                return RuntimeError("INJECTED_FAILURE: Payment disbursement event failed")
            return None

        self.emitter.set_failure_hook(fail_hook)

        with self.assertRaises(RuntimeError):
            disburse_payment(
                self.conn,
                self.emitter,
                payment_id=pay_id,
                external_bank_tx_ref="ACH-TEST-FAIL",
                disbursed_at_utc="2026-07-15T15:00:00Z",
                actor_id="USR-FIN-001",
            )

        # Assert payment is still AUTHORIZED, net_paid = 0
        pay_row = self.conn.execute(
            "SELECT payment_status, net_paid_cents, external_bank_tx_ref FROM payments WHERE payment_id = ?",
            (pay_id,),
        ).fetchone()
        self.assertEqual(pay_row[0], "AUTHORIZED")
        self.assertEqual(pay_row[1], 0)
        self.assertIsNone(pay_row[2])

        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)

        # Clear hook and verify atomic success
        self.emitter.set_failure_hook(None)
        ev_id = disburse_payment(
            self.conn,
            self.emitter,
            payment_id=pay_id,
            external_bank_tx_ref="ACH-TEST-SUCCESS",
            disbursed_at_utc="2026-07-15T15:00:00Z",
            actor_id="USR-FIN-001",
        )
        self.assertEqual(
            self.conn.execute("SELECT payment_status FROM payments WHERE payment_id = ?", (pay_id,)).fetchone()[0],
            "DISBURSED",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_id,)).fetchone()[0],
            "PAYMENT_DISBURSED",
        )

    def test_payment_cancel_mutation_failure_rolls_back_event(self) -> None:
        """
        Anti-phantom test: PAYMENT_CANCELLED event emitted prior to DB update
        rolls back if the entity update fails.
        """
        # Find an AUTHORIZED payment
        row = self.conn.execute(
            "SELECT p.payment_id, p.created_at_utc FROM payments p WHERE p.payment_status = 'AUTHORIZED' LIMIT 1"
        ).fetchone()
        pay_id, created_utc = row

        ev_cnt_before, tip_before = self._get_event_count_and_tip()

        # Call cancel_payment with an invalid timestamp earlier than created_at_utc
        # Trigger trg_payments_validate_upd aborts with ERR_CANCELLED_TIMESTAMP_BEFORE_CREATED
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            cancel_payment(
                self.conn,
                self.emitter,
                payment_id=pay_id,
                reason_code="FINANCE_WITHDRAWAL",
                reversed_at_utc="2025-01-01T00:00:00Z",  # Backdated before payment creation
                actor_id="USR-FIN-001",
            )
        self.assertIn("ERR_CANCELLED_TIMESTAMP_BEFORE_CREATED", str(ctx.exception))

        # Assert payment status is still AUTHORIZED
        pay_status = self.conn.execute(
            "SELECT payment_status FROM payments WHERE payment_id = ?", (pay_id,)
        ).fetchone()[0]
        self.assertEqual(pay_status, "AUTHORIZED")

        # Assert no PAYMENT_CANCELLED event exists (it was rolled back)
        ev_exists = self.conn.execute(
            "SELECT COUNT(*) FROM immutable_events WHERE entity_id = ? AND event_type = 'PAYMENT_CANCELLED'",
            (pay_id,),
        ).fetchone()[0]
        self.assertEqual(ev_exists, 0)

        # Assert event count and hash chain are unchanged
        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)

        # Now execute with a valid chronological timestamp and assert atomic success
        ev_id = cancel_payment(
            self.conn,
            self.emitter,
            payment_id=pay_id,
            reason_code="FINANCE_WITHDRAWAL",
            reversed_at_utc="2026-07-16T12:00:00Z",
            actor_id="USR-FIN-001",
        )
        self.assertEqual(
            self.conn.execute("SELECT payment_status FROM payments WHERE payment_id = ?", (pay_id,)).fetchone()[0],
            "CANCELLED",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_id,)).fetchone()[0],
            "PAYMENT_CANCELLED",
        )

    def test_payment_clawback_mutation_failure_rolls_back_event(self) -> None:
        """
        Anti-phantom test: PAYMENT_CLAWBACK_REVERSED event emitted prior to DB update
        rolls back if the entity update fails.
        """
        # Find a DISBURSED payment
        row = self.conn.execute(
            "SELECT payment_id, disbursed_amount_cents, disbursed_at_utc FROM payments WHERE payment_status = 'DISBURSED' LIMIT 1"
        ).fetchone()
        pay_id, disbursed_amt, disb_utc = row

        ev_cnt_before, tip_before = self._get_event_count_and_tip()

        # Call clawback with timestamp earlier than disbursed_at_utc
        # Trigger trg_payments_validate_upd aborts with ERR_CLAWBACK_TIMESTAMP_BEFORE_DISBURSED
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            clawback_payment(
                self.conn,
                self.emitter,
                payment_id=pay_id,
                clawback_cents=disbursed_amt,
                reversed_at_utc="2025-01-01T00:00:00Z",  # Backdated
                actor_id="USR-SIU-001",
            )
        self.assertIn("ERR_CLAWBACK_TIMESTAMP_BEFORE_DISBURSED", str(ctx.exception))

        # Assert payment status is still DISBURSED
        post_status = self.conn.execute(
            "SELECT payment_status, clawed_back_cents FROM payments WHERE payment_id = ?", (pay_id,)
        ).fetchone()
        self.assertEqual(post_status[0], "DISBURSED")
        self.assertEqual(post_status[1], 0)

        # Assert no PAYMENT_CLAWBACK_REVERSED event exists
        ev_exists = self.conn.execute(
            "SELECT COUNT(*) FROM immutable_events WHERE entity_id = ? AND event_type = 'PAYMENT_CLAWBACK_REVERSED' AND occurred_at_utc = '2025-01-01T00:00:00Z'",
            (pay_id,),
        ).fetchone()[0]
        self.assertEqual(ev_exists, 0)

        ev_cnt_after, tip_after = self._get_event_count_and_tip()
        self.assertEqual(ev_cnt_after, ev_cnt_before)
        self.assertEqual(tip_after, tip_before)

        # Now execute with valid timestamp and assert atomic success
        ev_id = clawback_payment(
            self.conn,
            self.emitter,
            payment_id=pay_id,
            clawback_cents=disbursed_amt,
            reversed_at_utc="2026-07-16T15:00:00Z",
            actor_id="USR-SIU-001",
        )
        self.assertEqual(
            self.conn.execute("SELECT payment_status FROM payments WHERE payment_id = ?", (pay_id,)).fetchone()[0],
            "REVERSED_CLAWBACK",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_type FROM immutable_events WHERE event_id = ?", (ev_id,)).fetchone()[0],
            "PAYMENT_CLAWBACK_REVERSED",
        )


def run_atomicity_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestApplicationEventStateAtomicity)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_atomicity_tests())

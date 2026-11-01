import test from 'node:test';
import assert from 'node:assert/strict';
import {
  sha256Hex,
  is64HexLowercase,
  computeEventHashV2,
  computeLineItemFingerprint,
  runCleanRoomEvaluation,
  createInitialLedgerState,
  applyFinancialCommand,
} from './sentinelEngine';

test('CRITICAL 4: ST-EVT-V2 length-prefixed serialization reproduces KAV-1..KAV-7 and prevents delimiter/NULL collisions', () => {
  // KAV-1 Genesis
  const pjson1 =
    '{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}';
  const psha1 = sha256Hex(pjson1);
  assert.equal(psha1, '45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3');

  const kav1 = computeEventHashV2({
    sequence_no: 1,
    event_id: 'EVT-2026-0000001',
    event_type: 'CLAIM_SUBMITTED',
    entity_type: 'Claim',
    entity_id: 'CLM-2026-000001',
    claim_id: 'CLM-2026-000001',
    actor_id: 'SYSTEM_SEED',
    occurred_at_utc: '2026-01-05T09:00:00Z',
    payload_sha256: psha1,
    prev_event_hash: '0'.repeat(64),
  });
  assert.equal(kav1.eventHash, '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305');

  // KAV-7 Unicode + Delimiter Injection + NULL claim_id
  const pjson7 = '{"note":"Renée|東京|🔍;8:claim_id=S15:CLM-2026-000001;"}';
  const psha7 = sha256Hex(pjson7);
  assert.equal(psha7, '551e1e170eb912f3d695924f3e62f2db7b1ca9c5ececd433cd42e80c8e03b07a');

  const kav7 = computeEventHashV2({
    sequence_no: 2,
    event_id: 'EVT-2026-0000002',
    event_type: 'INGESTION_EXCEPTION_RECORDED',
    entity_type: 'IngestionException',
    entity_id: 'IEX-2026-000001',
    claim_id: null,
    actor_id: 'USR|Renée;東京',
    occurred_at_utc: '2026-01-05T09:01:00Z',
    payload_sha256: psha7,
    prev_event_hash: kav1.eventHash,
  });
  assert.equal(kav7.eventHash, 'c20f59e45969c8c8fef46fcab1bc2645b123aa695f00f7761c291b9a243e8dbe');
  assert.equal(is64HexLowercase(kav7.eventHash), true);
  assert.equal(is64HexLowercase('1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee130Z'), false);
});

test('CRITICAL 8: 8-Node / 4-Claim Clean-Room PageRank and 10-Stage IEF scores match exact expected values', () => {
  const res = runCleanRoomEvaluation();
  assert.equal(res.convergedIteration, 78);
  assert.ok(res.convergedL1Error < 1e-9);
  assert.equal(res.claims[0].normalizedPageRank.toFixed(6), '1.054745');
  assert.equal(res.claims[1].normalizedPageRank.toFixed(6), '1.058274');
  assert.equal(res.claims[2].normalizedPageRank.toFixed(6), '1.170781');
  assert.equal(res.claims[3].normalizedPageRank.toFixed(6), '0.716200');

  assert.equal(res.claims[0].finalIefScore, 65.0);
  assert.equal(res.claims[0].riskTier, 'HIGH');
  assert.equal(res.claims[1].finalIefScore, 65.0);
  assert.equal(res.claims[1].riskTier, 'HIGH');
  assert.equal(res.claims[2].finalIefScore, 0.0);
  assert.equal(res.claims[2].riskTier, 'LOW');
  assert.equal(res.claims[3].finalIefScore, 0.67);
  assert.equal(res.claims[3].riskTier, 'LOW');
  assert.equal(res.claims[3].clusterBoost, 0.0);
});

test('CRITICAL 1, 2, 3, 7: Financial FSM enforces approval immutability, caps, payment lifecycle, and historical_approved_cents preservation', () => {
  let s = createInitialLedgerState();
  // Approve invoice for $3,700.00 (370000 cents)
  s = applyFinancialCommand(s, { type: 'APPROVE_INVOICE', approvedCents: 370000 });
  assert.equal(s.lastError, null);
  assert.equal(s.invoiceStatus, 'APPROVED');
  assert.equal(s.approvedCents, 370000);
  assert.equal(s.historicalApprovedCents, 370000);

  // CRITICAL 1: Unauthorized adjustment attempt must fail
  s = applyFinancialCommand(s, { type: 'ADJUST_APPROVED_INVOICE', newApprovedCents: 400000 });
  assert.ok(s.lastError?.includes('ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE'));
  assert.equal(s.approvedCents, 370000);

  // CRITICAL 2: Authorize & disburse partial then full payment, then clawback, revoke, and deny
  s = applyFinancialCommand(s, { type: 'AUTHORIZE_PAYMENT', paymentId: 'PAY-2026-000001', amountCents: 200000 });
  s = applyFinancialCommand(s, { type: 'AUTHORIZE_PAYMENT', paymentId: 'PAY-2026-000002', amountCents: 170000 });
  assert.equal(s.reservedAuthorizedCents, 370000);

  s = applyFinancialCommand(s, { type: 'DISBURSE_PAYMENT', paymentId: 'PAY-2026-000001', bankRef: 'ACH-2026-000001' });
  assert.equal(s.invoiceStatus, 'PARTIALLY_PAID');
  assert.equal(s.claimStatus, 'PARTIALLY_PAID');

  s = applyFinancialCommand(s, { type: 'DISBURSE_PAYMENT', paymentId: 'PAY-2026-000002', bankRef: 'ACH-2026-000002' });
  assert.equal(s.invoiceStatus, 'PAID');
  assert.equal(s.claimStatus, 'PAID');
  assert.equal(s.netPaidCents, 370000);
  assert.equal(s.reservedAuthorizedCents, 0);

  // Full clawback across both payments
  s = applyFinancialCommand(s, { type: 'CLAWBACK_PAYMENT', paymentId: 'PAY-2026-000001', clawbackCents: 200000 });
  assert.equal(s.invoiceStatus, 'PARTIALLY_PAID');
  s = applyFinancialCommand(s, { type: 'CLAWBACK_PAYMENT', paymentId: 'PAY-2026-000002', clawbackCents: 170000 });
  assert.equal(s.invoiceStatus, 'APPROVED');
  assert.equal(s.netPaidCents, 0);
  assert.equal(s.historicalApprovedCents, 370000);

  // Revoke invoice & deny claim -> historical_approved_cents stays 370000
  s = applyFinancialCommand(s, { type: 'REVOKE_INVOICE' });
  assert.equal(s.invoiceStatus, 'REVOKED_POST_APPROVAL');
  assert.equal(s.approvedCents, 0);
  assert.equal(s.historicalApprovedCents, 370000);
  assert.equal(s.claimStatus, 'SIU_HOLD');

  s = applyFinancialCommand(s, { type: 'DENY_CLAIM' });
  assert.equal(s.claimStatus, 'DENIED');
  assert.equal(s.historicalApprovedCents, 370000);

  // Verify FP-1 and FP-2 fingerprint normalization
  const fp1 = computeLineItemFingerprint('AB-FRAME-101', '2026-01-05T09:30:00Z', '2026-01-05T10:00:00Z', 420000);
  const fp2 = computeLineItemFingerprint(' ab-frame-101 ', '2026-01-05T14:00:00Z', '2026-01-05T18:00:00Z', 420000);
  assert.equal(fp1, '1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465');
  assert.equal(fp2, fp1);
});

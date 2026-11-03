import React, { useMemo, useState } from 'react';
import {
  runCleanRoomEvaluation,
  createInitialLedgerState,
  applyFinancialCommand,
  computeEventHashV2,
  sha256Hex,
  utf8ByteLength,
  type FinancialCommand,
} from './utils/sentinelEngine';
import {
  TEN_MANDATORY_AND_SUPPORT_ENTITIES,
  KAV_VECTORS,
  SCENARIO_CATALOG,
  FIFTEEN_INDICATORS,
  ACCEPTANCE_TESTS_T21_T28,
} from './data/archSt010Spec';

type ActiveSection = 'clean-room' | 'financial-fsm' | 'event-chain' | 'entities-indicators';

export default function App() {
  const [activeSection, setActiveSection] = useState<ActiveSection>('clean-room');
  const [addressAblation, setAddressAblation] = useState(false);
  const [selectedClaimId, setSelectedClaimId] = useState('CLM-2026-000001');

  // Financial FSM state
  const [ledger, setLedger] = useState(() => createInitialLedgerState());

  // Event Chain KAV state
  const [selectedKavIndex, setSelectedKavIndex] = useState(0);
  const [customActorId, setCustomActorId] = useState('USR|Renée;東京');
  const [customClaimIdNull, setCustomClaimIdNull] = useState(true);

  // Indicator filter state
  const [pillarFilter, setPillarFilter] = useState<'ALL' | 'NETWORK' | 'FINANCIAL' | 'BEHAVIORAL' | 'DOCUMENT'>('ALL');
  const [scenarioFilter, setScenarioFilter] = useState<'ALL' | 'YF-NEG' | 'BL'>('ALL');

  const cleanRoom = useMemo(() => runCleanRoomEvaluation({ addressAblation }), [addressAblation]);
  const selectedClaim =
    cleanRoom.claims.find((c) => c.claimId === selectedClaimId) ?? cleanRoom.claims[0];

  const selectedKav = KAV_VECTORS[selectedKavIndex] ?? KAV_VECTORS[0];
  const computedKav = useMemo(() => {
    const actor = selectedKavIndex === 6 ? customActorId : selectedKav.actorId;
    const claimId = selectedKavIndex === 6 ? (customClaimIdNull ? null : 'CLM-2026-000001') : selectedKav.claimId;
    const payloadSha = sha256Hex(selectedKav.payloadJson);
    const res = computeEventHashV2({
      sequence_no: selectedKav.sequenceNo,
      event_id: selectedKav.eventId,
      event_type: selectedKav.eventType,
      entity_type: selectedKav.entityType,
      entity_id: selectedKav.entityId,
      claim_id: claimId,
      actor_id: actor,
      occurred_at_utc: selectedKav.occurredAtUtc,
      payload_sha256: payloadSha,
      prev_event_hash: selectedKav.prevEventHash,
    });
    return {
      ...res,
      payloadSha,
      actor,
      actorBytes: utf8ByteLength(actor),
      claimId,
    };
  }, [selectedKav, selectedKavIndex, customActorId, customClaimIdNull]);

  const dispatchLedger = (cmd: FinancialCommand) => {
    setLedger((prev) => applyFinancialCommand(prev, cmd));
  };

  const resetLedger = () => {
    setLedger(createInitialLedgerState());
  };

  const runFullLifecycleDemo = () => {
    let s = createInitialLedgerState();
    s = applyFinancialCommand(s, { type: 'APPROVE_INVOICE', approvedCents: 370000 });
    s = applyFinancialCommand(s, { type: 'AUTHORIZE_PAYMENT', paymentId: 'PAY-2026-000001', amountCents: 200000 });
    s = applyFinancialCommand(s, { type: 'AUTHORIZE_PAYMENT', paymentId: 'PAY-2026-000002', amountCents: 170000 });
    s = applyFinancialCommand(s, { type: 'DISBURSE_PAYMENT', paymentId: 'PAY-2026-000001', bankRef: 'ACH-2026-000001' });
    s = applyFinancialCommand(s, { type: 'DISBURSE_PAYMENT', paymentId: 'PAY-2026-000002', bankRef: 'ACH-2026-000002' });
    s = applyFinancialCommand(s, { type: 'CLAWBACK_PAYMENT', paymentId: 'PAY-2026-000001', clawbackCents: 200000 });
    s = applyFinancialCommand(s, { type: 'CLAWBACK_PAYMENT', paymentId: 'PAY-2026-000002', clawbackCents: 170000 });
    s = applyFinancialCommand(s, { type: 'REVOKE_INVOICE' });
    s = applyFinancialCommand(s, { type: 'DENY_CLAIM' });
    setLedger(s);
  };

  const downloadArchSpec = () => {
    const lines = [
      '# ARCH-ST-010 — SENTINEL//TRACE: Final Self-Contained Architecture Specification',
      '',
      'Status: FINAL SELF-CONTAINED ARCHITECTURE SPECIFICATION',
      'Verified SQLite 3.40.1 / Python 3.10.12 Triggers, ST-EVT-V2 Digests, and 8-Node Clean-Room Vectors.',
      '',
      '## Clean-Room 4-Claim Expected Scores',
      ...cleanRoom.claims.map(
        (c) =>
          `- ${c.claimId}: PR_tilde=${c.normalizedPageRank.toFixed(6)}, S_base=${c.baseScore.toFixed(6)}, B_cluster=${c.clusterBoost.toFixed(6)}, IEF=${c.finalIefScore.toFixed(2)} (${c.riskTier})`
      ),
    ].join('\n');
    const blob = new Blob([lines], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ARCH-ST-010.md';
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredIndicators = FIFTEEN_INDICATORS.filter(
    (ind) => pillarFilter === 'ALL' || ind.pillar === pillarFilter
  );

  const filteredScenarios = SCENARIO_CATALOG.filter(
    (sc) => scenarioFilter === 'ALL' || sc.category === scenarioFilter
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Archival Prototype Disclaimer */}
      <div className="bg-amber-950 text-amber-200 border-b border-amber-600/50 px-4 py-2 text-xs font-mono text-center">
        ARCHIVAL / NON-OPERATIONAL PROTOTYPE (ARCH-ST-010.1): This React interface is an early static specification harness. The operational production application is the zero-dependency FastAPI Forensic Cockpit at <a href="http://localhost:8000/" className="underline font-bold text-amber-100">http://localhost:8000/</a> connected to data/operational.db.
      </div>
      {/* Strict 3-Zone Top Bar Contract */}
      <header className="flex items-center justify-between gap-8 px-6 py-4 border-b border-slate-800 bg-slate-950/95 sticky top-0 z-20">
        <a
          href="#top"
          onClick={(e) => {
            e.preventDefault();
            setActiveSection('clean-room');
          }}
          className="text-lg font-bold tracking-tight text-slate-100 whitespace-nowrap shrink-0"
        >
          Sentinel Trace
        </a>

        <nav aria-label="Primary Workspace Sections" className="flex items-center gap-6 text-sm font-medium text-slate-400 overflow-x-auto">
          <button
            type="button"
            onClick={() => setActiveSection('clean-room')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'clean-room'
                ? 'text-slate-100 border-sky-400'
                : 'border-transparent hover:text-slate-200'
            }`}
          >
            Clean-Room Scoring
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('financial-fsm')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'financial-fsm'
                ? 'text-slate-100 border-sky-400'
                : 'border-transparent hover:text-slate-200'
            }`}
          >
            Financial Ledger FSM
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('event-chain')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'event-chain'
                ? 'text-slate-100 border-sky-400'
                : 'border-transparent hover:text-slate-200'
            }`}
          >
            Event Hash Chain
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('entities-indicators')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'entities-indicators'
                ? 'text-slate-100 border-sky-400'
                : 'border-transparent hover:text-slate-200'
            }`}
          >
            Entities &amp; Indicators
          </button>
        </nav>

        <div className="flex items-center shrink-0">
          <button
            type="button"
            onClick={downloadArchSpec}
            className="px-4 py-2 text-xs font-semibold text-slate-950 bg-sky-400 rounded-lg hover:bg-sky-300 transition-colors whitespace-nowrap shrink-0"
          >
            Download ARCH-ST-010.md
          </button>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="flex-1 max-w-[1360px] w-full mx-auto px-6 py-8 space-y-8">
        {/* Top Summary Context Strip (Unboxed metadata with subtle separators) */}
        <section className="border-b border-slate-800 pb-6 flex flex-col lg:flex-row lg:items-end justify-between gap-6">
          <div className="space-y-2 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 font-mono tabular-nums">
              <span>Specification ARCH-ST-010</span>
              <span aria-hidden="true">·</span>
              <span>YottaFlex 10 Mandatory Entities</span>
              <span aria-hidden="true">·</span>
              <span>Seed 42 Baseline (5,000 Claims · 2,000 Claimants · 500 Providers · 8,000 Edges)</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100">
              Insurance Fraud Network Intelligence &amp; SIU Verification Workbench
            </h1>
            <p className="text-sm text-slate-400 leading-relaxed">
              Self-contained verification environment for CRITICAL 1 through CRITICAL 8: length-prefixed UTF-8 event
              hash chains (<code className="text-slate-200">ST-EVT-V2</code>), deterministic schema digests (
              <code className="text-slate-200">ST-SCHEMA-V1</code>), penny-exact invoice/claim FSM triggers, and the
              8-node clean-room PageRank and 10-stage IEF scoring pipeline.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-800/80 text-right font-mono tabular-nums shrink-0">
            <div>
              <div className="text-xs text-slate-400 whitespace-nowrap">Operational Claims</div>
              <div className="text-lg font-semibold text-slate-100">5,000</div>
              <div className="text-xs text-slate-500 whitespace-nowrap">775 Fraud · 4,225 Benign</div>
            </div>
            <div>
              <div className="text-xs text-slate-400 whitespace-nowrap">Relationship Edges</div>
              <div className="text-lg font-semibold text-slate-100">8,000</div>
              <div className="text-xs text-slate-500 whitespace-nowrap">+25 Quarantined GT</div>
            </div>
            <div>
              <div className="text-xs text-slate-400 whitespace-nowrap">Immutable Events</div>
              <div className="text-lg font-semibold text-slate-100">19,495</div>
              <div className="text-xs text-slate-500 whitespace-nowrap">ST-EVT-V2 Verified</div>
            </div>
            <div>
              <div className="text-xs text-slate-400 whitespace-nowrap">PageRank Convergence</div>
              <div className="text-lg font-semibold text-sky-400">Iter 78</div>
              <div className="text-xs text-slate-500 whitespace-nowrap">L1 9.74e-10 &lt; 1e-9</div>
            </div>
          </div>
        </section>

        {/* SECTION 1: CLEAN-ROOM 8-NODE / 4-CLAIM SCORING WORKBENCH */}
        {activeSection === 'clean-room' && (
          <div className="space-y-8">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-100">
                  01. Clean-Room 8-Node Graph, PageRank &amp; 10-Stage IEF Scoring (CRITICAL 8)
                </h2>
                <p className="text-sm text-slate-400">
                  Select any claim in the 4-claim fixture to inspect its exact PageRank centrality, emitted indicators,
                  benign-context dampening, collusive cluster boost, and safety floor.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setAddressAblation((v) => !v)}
                  className={`px-4 py-2 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap shrink-0 ${
                    addressAblation
                      ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                      : 'bg-slate-900 border-slate-700 text-slate-200 hover:border-slate-500'
                  }`}
                >
                  {addressAblation ? 'Address Ablation: Active (w=0.00)' : 'Toggle Address Ablation (SHARED_ADDRESS=0)'}
                </button>
              </div>
            </div>

            {/* 4-Claim Interactive Table */}
            <div className="border border-slate-800 rounded-lg overflow-x-auto bg-slate-900/40">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-xs text-slate-400">
                    <th className="py-3 px-4 font-medium">Claim ID</th>
                    <th className="py-3 px-4 font-medium">Claimant · Provider</th>
                    <th className="py-3 px-4 font-medium text-right">Raw PR v(78)</th>
                    <th className="py-3 px-4 font-medium text-right">Scaled PR_tilde</th>
                    <th className="py-3 px-4 font-medium text-right">Stage 4 Base</th>
                    <th className="py-3 px-4 font-medium text-right">Dampening D(c)</th>
                    <th className="py-3 px-4 font-medium text-right">Cluster Boost</th>
                    <th className="py-3 px-4 font-medium text-right">Pre-Floor</th>
                    <th className="py-3 px-4 font-medium text-right">Final IEF Score</th>
                    <th className="py-3 px-4 font-medium">Risk Tier</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70 font-mono tabular-nums">
                  {cleanRoom.claims.map((c) => {
                    const isSelected = c.claimId === selectedClaim.claimId;
                    return (
                      <tr
                        key={c.claimId}
                        onClick={() => setSelectedClaimId(c.claimId)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-sky-500/10' : 'hover:bg-slate-900/80'
                        }`}
                      >
                        <td className="py-3 px-4 font-semibold text-slate-100">
                          <button
                            type="button"
                            onClick={() => setSelectedClaimId(c.claimId)}
                            className="text-left underline decoration-slate-600 hover:decoration-sky-400 whitespace-nowrap"
                          >
                            {c.claimId}
                          </button>
                        </td>
                        <td className="py-3 px-4 text-xs text-slate-300 font-sans whitespace-nowrap">
                          {c.claimantId} <span aria-hidden="true">·</span> {c.providerId}
                        </td>
                        <td className="py-3 px-4 text-right text-slate-300">{c.rawPageRank.toFixed(8)}</td>
                        <td className="py-3 px-4 text-right text-slate-300">{c.normalizedPageRank.toFixed(6)}</td>
                        <td className="py-3 px-4 text-right text-slate-300">{c.baseScore.toFixed(6)}</td>
                        <td className="py-3 px-4 text-right text-slate-300">{c.dampeningFactor.toFixed(4)}</td>
                        <td className="py-3 px-4 text-right text-slate-300">{c.clusterBoost.toFixed(6)}</td>
                        <td className="py-3 px-4 text-right text-slate-300">{c.preFloorScore.toFixed(6)}</td>
                        <td className="py-3 px-4 text-right font-bold text-slate-100">{c.finalIefScore.toFixed(2)}</td>
                        <td className="py-3 px-4 font-sans text-xs">
                          <span
                            className={
                              c.riskTier === 'HIGH' || c.riskTier === 'CRITICAL'
                                ? 'text-amber-300 font-semibold'
                                : 'text-emerald-300 font-medium'
                            }
                          >
                            {c.riskTier}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Selected Claim 10-Stage Breakdown + PageRank Iteration Convergence Table */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="border border-slate-800 rounded-lg p-6 bg-slate-900/40 space-y-4">
                <div className="flex items-center justify-between gap-4 border-b border-slate-800 pb-3">
                  <div>
                    <h3 className="text-base font-semibold text-slate-100">
                      10-Stage IEF Trace: {selectedClaim.claimId}
                    </h3>
                    <p className="text-xs text-slate-400">
                      Claimant {selectedClaim.claimantId} · Provider {selectedClaim.providerId} · Hard Collusion:{' '}
                      {selectedClaim.hardCollusionOverride ? 'TRUE (1)' : 'FALSE (0)'}
                    </p>
                  </div>
                  <div className="text-right font-mono tabular-nums shrink-0">
                    <div className="text-xs text-slate-400 whitespace-nowrap">Final IEF</div>
                    <div className="text-xl font-bold text-sky-400 whitespace-nowrap">
                      {selectedClaim.finalIefScore.toFixed(2)} · {selectedClaim.riskTier}
                    </div>
                  </div>
                </div>

                <div className="space-y-3 text-xs">
                  <div className="font-medium text-slate-300">Emitted Atomic Indicators (Stages 1–2):</div>
                  {selectedClaim.emittedIndicators.length === 0 ? (
                    <div className="text-slate-400 py-2">
                      Zero indicators emitted (all 15 atomic functions evaluate to 0.00 points).
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-800 border border-slate-800 rounded">
                      {selectedClaim.emittedIndicators.map((ind) => (
                        <div key={ind.code} className="p-3 flex items-center justify-between gap-4">
                          <div className="min-w-0">
                            <div className="font-semibold text-slate-200">
                              {ind.code} · {ind.name} ({ind.pillar})
                            </div>
                            <div className="font-mono text-slate-400 truncate">Token: {ind.token}</div>
                          </div>
                          <div className="font-mono tabular-nums text-right shrink-0 text-slate-100">
                            {ind.rawPoints.toFixed(2)} / {ind.maxPoints.toFixed(1)} pts
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 font-mono tabular-nums">
                    <div className="p-3 border border-slate-800 rounded">
                      <div className="text-slate-400">P_NET (/60)</div>
                      <div className="text-sm font-semibold text-slate-100">
                        {selectedClaim.pillarScores.NETWORK.toFixed(4)}
                      </div>
                    </div>
                    <div className="p-3 border border-slate-800 rounded">
                      <div className="text-slate-400">P_FIN (/55)</div>
                      <div className="text-sm font-semibold text-slate-100">
                        {selectedClaim.pillarScores.FINANCIAL.toFixed(4)}
                      </div>
                    </div>
                    <div className="p-3 border border-slate-800 rounded">
                      <div className="text-slate-400">P_BEH (/45)</div>
                      <div className="text-sm font-semibold text-slate-100">
                        {selectedClaim.pillarScores.BEHAVIORAL.toFixed(4)}
                      </div>
                    </div>
                    <div className="p-3 border border-slate-800 rounded">
                      <div className="text-slate-400">P_DOC (/40)</div>
                      <div className="text-sm font-semibold text-slate-100">
                        {selectedClaim.pillarScores.DOCUMENT.toFixed(4)}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-1.5 pt-2 font-mono tabular-nums text-slate-300 border-t border-slate-800">
                    <div>
                      Stage 4 Base Score S_base = {selectedClaim.baseScore.toFixed(6)}
                    </div>
                    <div>
                      Stage 5 Dampening D(c) = {selectedClaim.dampeningFactor.toFixed(4)} → S_damp ={' '}
                      {selectedClaim.dampenedScore.toFixed(6)}
                    </div>
                    <div>
                      Stage 6–7 Cluster Boost B_cluster = {selectedClaim.clusterBoost.toFixed(6)} (Eligible:{' '}
                      {selectedClaim.clusterEligible ? 'YES' : 'NO'})
                    </div>
                    <div>
                      Stage 8–9 Pre-Floor S_pre = {selectedClaim.preFloorScore.toFixed(6)} → Safety Floor Applied ={' '}
                      {selectedClaim.finalIefScore.toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>

              {/* PageRank Convergence Table */}
              <div className="border border-slate-800 rounded-lg p-6 bg-slate-900/40 space-y-4 overflow-x-auto">
                <div className="border-b border-slate-800 pb-3">
                  <h3 className="text-base font-semibold text-slate-100">
                    8-Node Power-Iteration PageRank Checkpoints (α = 0.85, ε = 1e-9)
                  </h3>
                  <p className="text-xs text-slate-400">
                    Degree Vector d = [{cleanRoom.degreeVector.map((x) => x.toFixed(1)).join(', ')}] · Claim Sum S_claim ={' '}
                    {cleanRoom.claimPageRankSum.toFixed(8)}
                  </p>
                </div>

                <table className="w-full text-left border-collapse text-xs font-mono tabular-nums">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-2 pr-3">Iter</th>
                      <th className="py-2 px-2 text-right">L1 Error</th>
                      <th className="py-2 px-2 text-right">CLM-1</th>
                      <th className="py-2 px-2 text-right">CLM-2</th>
                      <th className="py-2 px-2 text-right">CLM-3</th>
                      <th className="py-2 pl-2 text-right">CLM-4</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {cleanRoom.checkpoints.map((cp) => (
                      <tr key={cp.iteration}>
                        <td className="py-1.5 pr-3 font-semibold text-slate-200">t={cp.iteration}</td>
                        <td className="py-1.5 px-2 text-right text-slate-400">
                          {cp.iteration === 0 ? '—' : cp.l1Error.toExponential(3)}
                        </td>
                        <td className="py-1.5 px-2 text-right text-slate-300">{cp.vector[0].toFixed(6)}</td>
                        <td className="py-1.5 px-2 text-right text-slate-300">{cp.vector[1].toFixed(6)}</td>
                        <td className="py-1.5 px-2 text-right text-slate-300">{cp.vector[2].toFixed(6)}</td>
                        <td className="py-1.5 pl-2 text-right text-slate-300">{cp.vector[3].toFixed(6)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 2: FINANCIAL LEDGER FSM & HISTORICAL ACCOUNTING SANDBOX */}
        {activeSection === 'financial-fsm' && (
          <div className="space-y-8">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-100">
                  02. Financial Ledger FSM, Cap Enforcement &amp; Historical Balance Sandbox (CRITICAL 1, 2, 3, 7)
                </h2>
                <p className="text-sm text-slate-400">
                  Execute valid lifecycle steps or trigger adversarial direct-SQL attacks to verify SQLite trigger
                  enforcement (<code className="text-slate-200">trg_invoices_fsm_upd</code>,{' '}
                  <code className="text-slate-200">trg_claims_fsm_upd</code>,{' '}
                  <code className="text-slate-200">trg_payments_validate_upd</code>).
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={runFullLifecycleDemo}
                  className="px-4 py-2 text-xs font-semibold text-slate-950 bg-sky-400 rounded-lg hover:bg-sky-300 transition-colors whitespace-nowrap shrink-0"
                >
                  Run Full Clawback &amp; Denial Sequence
                </button>
                <button
                  type="button"
                  onClick={resetLedger}
                  className="px-4 py-2 text-xs font-medium text-slate-200 bg-slate-900 border border-slate-700 rounded-lg hover:border-slate-500 transition-colors whitespace-nowrap shrink-0"
                >
                  Reset Ledger
                </button>
              </div>
            </div>

            {/* Live Financial Balances Strip (2x4 Spacious Grid to Prevent Status Overflow) */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 p-6 border border-slate-800 rounded-lg bg-slate-900/40 font-mono tabular-nums">
              <div className="min-w-0">
                <div className="text-xs text-slate-400">Claim Status</div>
                <div className="text-sm font-bold text-sky-400 mt-1 truncate">{ledger.claimStatus}</div>
              </div>
              <div className="min-w-0">
                <div className="text-xs text-slate-400">Invoice Status</div>
                <div className="text-sm font-bold text-sky-400 mt-1 truncate">{ledger.invoiceStatus}</div>
              </div>
              <div className="min-w-0">
                <div className="text-xs text-slate-400">Policy Payout Cap</div>
                <div className="text-sm font-semibold text-slate-100 mt-1">
                  ${(ledger.payoutCapCents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="min-w-0">
                <div className="text-xs text-slate-400">Active Approved</div>
                <div className="text-sm font-semibold text-slate-100 mt-1">
                  ${(ledger.approvedCents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="min-w-0 pt-3 border-t border-slate-800/80">
                <div className="text-xs text-slate-400">Historical Approved</div>
                <div className="text-sm font-bold text-emerald-400 mt-1">
                  ${(ledger.historicalApprovedCents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="min-w-0 pt-3 border-t border-slate-800/80">
                <div className="text-xs text-slate-400">Reserved Authorized</div>
                <div className="text-sm font-semibold text-slate-100 mt-1">
                  ${(ledger.reservedAuthorizedCents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="min-w-0 pt-3 border-t border-slate-800/80">
                <div className="text-xs text-slate-400">Gross Disbursed</div>
                <div className="text-sm font-semibold text-slate-100 mt-1">
                  ${(ledger.grossDisbursedCents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="min-w-0 pt-3 border-t border-slate-800/80">
                <div className="text-xs text-slate-400">Net Paid (Post-Clawback)</div>
                <div className="text-sm font-semibold text-slate-100 mt-1">
                  ${(ledger.netPaidCents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            {/* Action Feedback Banner */}
            <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/70 space-y-2 text-xs font-mono">
              <div className="text-slate-300">
                <span className="text-slate-400">Last State Update:</span> {ledger.lastActionNote}
              </div>
              {ledger.lastError && (
                <div role="alert" className="text-rose-300 font-semibold pt-1">
                  SQLite Trigger Aborted Transaction: {ledger.lastError}
                </div>
              )}
            </div>

            {/* Interactive Controls Grid: Valid Workflow vs Adversarial SQL Tampering */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="border border-slate-800 rounded-lg p-6 bg-slate-900/40 space-y-4">
                <h3 className="text-base font-semibold text-slate-100">
                  Authorized Operational Lifecycle Transitions
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'APPROVE_INVOICE', approvedCents: 370000 })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    1. Approve Invoice ($3,700.00)
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'RECORD_ADJUSTMENT_EVENT', newApprovedCents: 400000 })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    2a. Log Adjustment Event
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'ADJUST_APPROVED_INVOICE', newApprovedCents: 400000 })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    2b. Adjust Approval ($4,000.00)
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      dispatchLedger({ type: 'AUTHORIZE_PAYMENT', paymentId: 'PAY-2026-000001', amountCents: 200000 })
                    }
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    3. Authorize PAY-000001 ($2,000.00)
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      dispatchLedger({
                        type: 'DISBURSE_PAYMENT',
                        paymentId: 'PAY-2026-000001',
                        bankRef: 'ACH-2026-000001',
                      })
                    }
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    4. Disburse PAY-000001
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      dispatchLedger({
                        type: 'CLAWBACK_PAYMENT',
                        paymentId: 'PAY-2026-000001',
                        clawbackCents: 200000,
                      })
                    }
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    5. Full Clawback ($2,000.00)
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'REVOKE_INVOICE' })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    6. Revoke Invoice Post-Approval
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'DENY_CLAIM' })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-slate-700 rounded hover:border-sky-400 transition-colors whitespace-nowrap truncate"
                  >
                    7. Deny Claim (Keep Historical)
                  </button>
                </div>
              </div>

              <div className="border border-slate-800 rounded-lg p-6 bg-slate-900/40 space-y-4">
                <h3 className="text-base font-semibold text-slate-100">
                  Adversarial Direct-SQL Trigger Tests (T-21, T-22, T-23, T-24, T-27)
                </h3>
                <div className="grid grid-cols-1 gap-3">
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'APPROVE_INVOICE', approvedCents: 460000 })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-rose-800/70 text-rose-200 rounded hover:border-rose-500 transition-colors"
                  >
                    Test CRITICAL 1: Approve $4,600.00 Exceeding Policy/Claim Payout Cap ($4,200.00)
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'ADVERSARIAL_DIRECT_PAID_STATUS' })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-rose-800/70 text-rose-200 rounded hover:border-rose-500 transition-colors"
                  >
                    Test CRITICAL 2: Force Status = PAID While Reserved &gt; 0 or Net Paid &lt; Approved
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'ADVERSARIAL_DIRECT_DISBURSED_INSERT' })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-rose-800/70 text-rose-200 rounded hover:border-rose-500 transition-colors"
                  >
                    Test CRITICAL 3a: Direct SQL INSERT of Payment with status = DISBURSED
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'ADVERSARIAL_TAMPER_BANK_REF' })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-rose-800/70 text-rose-200 rounded hover:border-rose-500 transition-colors"
                  >
                    Test CRITICAL 3b: Overwrite external_bank_tx_ref Post-Disbursement
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchLedger({ type: 'ADVERSARIAL_ZERO_HISTORICAL_APPROVED' })}
                    className="px-3 py-2.5 text-xs font-medium text-left bg-slate-900 border border-rose-800/70 text-rose-200 rounded hover:border-rose-500 transition-colors"
                  >
                    Test CRITICAL 7: Direct SQL UPDATE historical_approved_cents = 0 After Revocation
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 3: LENGTH-PREFIXED EVENT HASH CHAIN (ST-EVT-V2) & KAV-1..7 */}
        {activeSection === 'event-chain' && (
          <div className="space-y-8">
            <div>
              <h2 className="text-xl font-semibold text-slate-100">
                03. Length-Prefixed Canonical Event Serialization (ST-EVT-V2) &amp; KAV-1..7 Verifier (CRITICAL 4)
              </h2>
              <p className="text-sm text-slate-400">
                Inspect the 7 SQLite-verified Known-Answer Vectors (<code className="text-slate-200">KAV-1</code>{' '}
                through <code className="text-slate-200">KAV-7</code>) and test multi-byte UTF-8 and pipe/semicolon
                delimiter injection collision resistance.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {KAV_VECTORS.map((kv, idx) => (
                <button
                  key={kv.id}
                  type="button"
                  onClick={() => setSelectedKavIndex(idx)}
                  className={`px-3 py-1.5 text-xs font-mono rounded border transition-colors whitespace-nowrap shrink-0 ${
                    selectedKavIndex === idx
                      ? 'bg-sky-400 text-slate-950 font-semibold border-sky-400'
                      : 'bg-slate-900 text-slate-300 border-slate-800 hover:border-slate-600'
                  }`}
                >
                  {kv.id}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="border border-slate-800 rounded-lg p-6 bg-slate-900/40 space-y-4">
                <h3 className="text-base font-semibold text-slate-100">
                  Vector Input Fields: {selectedKav.id}
                </h3>
                <div className="space-y-2 text-xs font-mono tabular-nums text-slate-300">
                  <div>1. sequence_no (INTEGER): {selectedKav.sequenceNo}</div>
                  <div>2. event_id (TEXT): {selectedKav.eventId}</div>
                  <div>3. event_type (TEXT): {selectedKav.eventType}</div>
                  <div>4. entity_type (TEXT): {selectedKav.entityType}</div>
                  <div>5. entity_id (TEXT): {selectedKav.entityId}</div>
                  <div>
                    6. claim_id (NULL | TEXT):{' '}
                    {computedKav.claimId === null ? 'NULL (encoded as 8:claim_id=N;)' : computedKav.claimId}
                  </div>
                  <div>
                    7. actor_id (TEXT, {computedKav.actorBytes} UTF-8 bytes): {computedKav.actor}
                  </div>
                  <div>8. occurred_at_utc (TEXT): {selectedKav.occurredAtUtc}</div>
                  <div className="break-all">9. payload_json (RFC-8785): {selectedKav.payloadJson}</div>
                </div>

                {selectedKavIndex === 6 && (
                  <div className="pt-4 border-t border-slate-800 space-y-3">
                    <label className="block text-xs text-slate-300">
                      Test Live Unicode / Pipe Delimiter Injection in <code className="text-sky-300">actor_id</code>:
                      <input
                        type="text"
                        value={customActorId}
                        onChange={(e) => setCustomActorId(e.target.value)}
                        className="mt-1.5 w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-700 rounded text-slate-100"
                      />
                    </label>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => setCustomClaimIdNull((v) => !v)}
                        className="px-3 py-1.5 text-xs font-mono bg-slate-900 border border-slate-700 rounded text-slate-200 hover:border-slate-500"
                      >
                        Toggle claim_id: {customClaimIdNull ? 'NULL (8:claim_id=N;)' : 'CLM-2026-000001'}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="border border-slate-800 rounded-lg p-6 bg-slate-900/40 space-y-4 font-mono text-xs">
                <h3 className="text-base font-sans font-semibold text-slate-100">
                  Computed ST-EVT-V2 Preimage &amp; 64-Hex SHA-256 Digest
                </h3>
                <div>
                  <div className="text-slate-400 mb-1">Exact Length-Prefixed ST-EVT-V2 Preimage:</div>
                  <div className="p-3 bg-slate-950 border border-slate-800 rounded break-all text-slate-200 leading-relaxed">
                    {computedKav.preimage}
                  </div>
                </div>
                <div className="space-y-2 tabular-nums">
                  <div className="break-all">
                    <span className="text-slate-400">payload_sha256: </span>
                    <span className="text-slate-200">{computedKav.payloadSha}</span>
                  </div>
                  <div className="break-all">
                    <span className="text-slate-400">prev_event_hash: </span>
                    <span className="text-slate-200">{selectedKav.prevEventHash}</span>
                  </div>
                  <div className="break-all">
                    <span className="text-slate-400">Computed event_hash: </span>
                    <span className="text-sky-400 font-semibold">{computedKav.eventHash}</span>
                  </div>
                  <div className="break-all">
                    <span className="text-slate-400">Expected KAV Digest: </span>
                    <span className="text-emerald-400">{selectedKav.expectedEventHash}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 4: 10 MANDATORY ENTITIES, SCENARIOS, 15 INDICATORS & T-21..T-28 */}
        {activeSection === 'entities-indicators' && (
          <div className="space-y-10">
            {/* 12 Operational Tables */}
            <div className="space-y-4">
              <h2 className="text-xl font-semibold text-slate-100">
                04. YottaFlex 10 Mandatory Entities &amp; Operational Support Tables (seed=42)
              </h2>
              <div className="border border-slate-800 rounded-lg overflow-x-auto bg-slate-900/40">
                <table className="w-full text-left border-collapse text-xs font-mono tabular-nums">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 font-sans">
                      <th className="py-2.5 px-4">Tier</th>
                      <th className="py-2.5 px-4">Table Name</th>
                      <th className="py-2.5 px-4">Entity</th>
                      <th className="py-2.5 px-4 text-right">Seed=42 Count</th>
                      <th className="py-2.5 px-4">Deterministic ID Range</th>
                      <th className="py-2.5 px-4">SQLite GLOB Constraint</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {TEN_MANDATORY_AND_SUPPORT_ENTITIES.map((row) => (
                      <tr key={row.tableName}>
                        <td className="py-2 px-4 text-slate-400">{row.tier}</td>
                        <td className="py-2 px-4 font-semibold text-slate-100">{row.tableName}</td>
                        <td className="py-2 px-4 text-slate-200 font-sans">{row.entityName}</td>
                        <td className="py-2 px-4 text-right font-semibold text-sky-400">
                          {row.seed42Count.toLocaleString()}
                        </td>
                        <td className="py-2 px-4 text-slate-300">{row.idFormat}</td>
                        <td className="py-2 px-4 text-slate-400">{row.globPattern}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 15 Atomic Indicators with Filter */}
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <h3 className="text-lg font-semibold text-slate-100">
                  All 15 Atomic FraudIndicators (IND-01 .. IND-15)
                </h3>
                <div className="flex items-center gap-1 p-1 bg-slate-900 border border-slate-800 rounded-lg">
                  {(['ALL', 'NETWORK', 'FINANCIAL', 'BEHAVIORAL', 'DOCUMENT'] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setPillarFilter(p)}
                      className={`px-3 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 ${
                        pillarFilter === p
                          ? 'bg-sky-400 text-slate-950 font-semibold'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div className="border border-slate-800 rounded-lg overflow-x-auto bg-slate-900/40">
                <table className="w-full text-left border-collapse text-xs font-mono tabular-nums">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 font-sans">
                      <th className="py-2.5 px-4">Code</th>
                      <th className="py-2.5 px-4">Indicator Name</th>
                      <th className="py-2.5 px-4">Pillar · Scope</th>
                      <th className="py-2.5 px-4 text-right">Max Pts</th>
                      <th className="py-2.5 px-4">Exact Activation Formula a_m(c)</th>
                      <th className="py-2.5 px-4">Canonical Evidence Token</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredIndicators.map((ind) => (
                      <tr key={ind.code}>
                        <td className="py-2 px-4 font-semibold text-sky-400">{ind.code}</td>
                        <td className="py-2 px-4 text-slate-100">{ind.name}</td>
                        <td className="py-2 px-4 text-slate-400 font-sans">
                          {ind.pillar} · {ind.scope}
                        </td>
                        <td className="py-2 px-4 text-right font-semibold text-slate-200">
                          {ind.maxPoints.toFixed(1)}
                        </td>
                        <td className="py-2 px-4 text-slate-300">{ind.formula}</td>
                        <td className="py-2 px-4 text-slate-400">{ind.tokenFormat}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* YF-NEG-1..5 & BL-1..5 Scenarios + T-21..T-28 Acceptance Matrix */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-semibold text-slate-100">
                    Challenge Scenarios (YF-NEG-1..5 &amp; BL-1..5)
                  </h3>
                  <div className="flex items-center gap-1 p-1 bg-slate-900 border border-slate-800 rounded-lg">
                    {(['ALL', 'YF-NEG', 'BL'] as const).map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => setScenarioFilter(cat)}
                        className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                          scenarioFilter === cat ? 'bg-sky-400 text-slate-950 font-semibold' : 'text-slate-400'
                        }`}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg bg-slate-900/40">
                  {filteredScenarios.map((sc) => (
                    <div key={sc.code} className="p-4 space-y-1 text-xs">
                      <div className="flex items-center justify-between font-mono">
                        <span className="font-semibold text-sky-400">
                          {sc.code} · {sc.title}
                        </span>
                        <span className="text-slate-400">{sc.countOrMultiplier}</span>
                      </div>
                      <p className="text-slate-300">{sc.ruleSummary}</p>
                      <div className="text-emerald-400 font-mono">Expected: {sc.expectedOutcome}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="text-base font-semibold text-slate-100">
                  ARCH-ST-010 Critical Audit Tests (T-21 .. T-28)
                </h3>
                <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg bg-slate-900/40">
                  {ACCEPTANCE_TESTS_T21_T28.map((t) => (
                    <div key={t.testId} className="p-4 space-y-1 text-xs">
                      <div className="flex items-center justify-between font-mono">
                        <span className="font-semibold text-slate-100">
                          {t.testId} · {t.criticalRef}
                        </span>
                        <span className="text-amber-300">{t.status}</span>
                      </div>
                      <div className="font-medium text-slate-200">{t.scope}</div>
                      <p className="text-slate-400">{t.sqliteAssertion}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-slate-900 px-6 py-4 text-xs text-slate-500 flex items-center justify-between max-w-[1360px] w-full mx-auto">
        <span>Sentinel Trace Architecture Specification ARCH-ST-010</span>
        <span className="font-mono tabular-nums">YottaFlex Challenge · Seed 42 Baseline</span>
      </footer>
    </div>
  );
}

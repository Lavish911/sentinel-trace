/**
 * Pure domain logic for Sentinel Trace (ARCH-ST-010):
 * - Length-prefixed UTF-8 canonical event serialization (ST-EVT-V2) & SHA-256 verification
 * - 8-Node / 4-Claim Clean-Room PageRank & 10-Stage IEF Scoring Pipeline
 * - Financial Ledger FSM, Cap Enforcement, Clawback & Historical Balance Protection (CRITICAL 1, 2, 3, 7)
 */

export interface EventFieldsV2 {
  sequence_no: number;
  event_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  claim_id: string | null;
  actor_id: string;
  occurred_at_utc: string;
  payload_sha256: string;
  prev_event_hash: string;
}

export function utf8ByteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

/**
 * Pure JavaScript SHA-256 implementation returning 64-char lowercase hex.
 * Works identically in browser and Node.js without async WebCrypto latency.
 */
export function sha256Hex(input: string): string {
  const bytes = new TextEncoder().encode(input);
  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];

  const H = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ];

  const l = bytes.length;
  const bitLenHi = Math.floor((l * 8) / 0x100000000);
  const bitLenLo = (l * 8) >>> 0;
  const padLen = ((l + 9 + 63) >> 6) << 6;
  const padded = new Uint8Array(padLen);
  padded.set(bytes);
  padded[l] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padLen - 8, bitLenHi, false);
  view.setUint32(padLen - 4, bitLenLo, false);

  const W = new Uint32Array(64);
  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));

  for (let offset = 0; offset < padLen; offset += 64) {
    for (let i = 0; i < 16; i++) {
      W[i] = view.getUint32(offset + i * 4, false);
    }
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3);
      const s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
      W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = H;
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + S1 + ch + K[i] + W[i]) >>> 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (S0 + maj) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    H[0] = (H[0] + a) >>> 0;
    H[1] = (H[1] + b) >>> 0;
    H[2] = (H[2] + c) >>> 0;
    H[3] = (H[3] + d) >>> 0;
    H[4] = (H[4] + e) >>> 0;
    H[5] = (H[5] + f) >>> 0;
    H[6] = (H[6] + g) >>> 0;
    H[7] = (H[7] + h) >>> 0;
  }

  return H.map((v) => v.toString(16).padStart(8, '0')).join('');
}

export function is64HexLowercase(s: string): boolean {
  return s.length === 64 && /^[0-9a-f]{64}$/.test(s);
}

/**
 * CRITICAL 4: ST-EVT-V2 Length-Prefixed Canonical Event Preimage
 */
export function encodeEventPreimageV2(ev: EventFieldsV2): string {
  const ordered: Array<[string, number | string | null, 'I' | 'S' | 'N']> = [
    ['sequence_no', ev.sequence_no, 'I'],
    ['event_id', ev.event_id, 'S'],
    ['event_type', ev.event_type, 'S'],
    ['entity_type', ev.entity_type, 'S'],
    ['entity_id', ev.entity_id, 'S'],
    ['claim_id', ev.claim_id, ev.claim_id === null ? 'N' : 'S'],
    ['actor_id', ev.actor_id, 'S'],
    ['occurred_at_utc', ev.occurred_at_utc, 'S'],
    ['payload_sha256', ev.payload_sha256, 'S'],
    ['prev_event_hash', ev.prev_event_hash, 'S'],
  ];

  const parts: string[] = ['ST-EVT-V2|'];
  for (const [name, val, kind] of ordered) {
    const nameLen = utf8ByteLength(name);
    if (kind === 'N') {
      parts.push(`${nameLen}:${name}=N;`);
    } else if (kind === 'I') {
      parts.push(`${nameLen}:${name}=I${val};`);
    } else {
      const strVal = String(val);
      const valLen = utf8ByteLength(strVal);
      parts.push(`${nameLen}:${name}=S${valLen}:${strVal};`);
    }
  }
  return parts.join('');
}

export function computeEventHashV2(ev: EventFieldsV2): { preimage: string; eventHash: string } {
  const preimage = encodeEventPreimageV2(ev);
  return {
    preimage,
    eventHash: sha256Hex(preimage),
  };
}

export function computeLineItemFingerprint(
  cptOrLineCode: string,
  serviceStartUtc: string,
  serviceEndUtc: string,
  billedCents: number
): string {
  const normCode = cptOrLineCode.trim().toUpperCase();
  const startDay = serviceStartUtc.slice(0, 10);
  const endDay = serviceEndUtc.slice(0, 10);
  const raw = `${normCode}|${startDay}|${endDay}|${billedCents}`;
  return sha256Hex(raw);
}

/**
 * CRITICAL 8: 8-Node / 4-Claim Clean-Room PageRank & 10-Stage IEF Scoring
 */
export interface PageRankCheckpoint {
  iteration: number;
  l1Error: number;
  vector: number[];
}

export interface CleanRoomClaimScore {
  claimId: string;
  claimantId: string;
  providerId: string;
  rawPageRank: number;
  normalizedPageRank: number;
  emittedIndicators: Array<{
    code: string;
    name: string;
    pillar: 'NETWORK' | 'FINANCIAL' | 'BEHAVIORAL' | 'DOCUMENT';
    rawPoints: number;
    maxPoints: number;
    token: string;
  }>;
  pillarScores: {
    NETWORK: number;
    FINANCIAL: number;
    BEHAVIORAL: number;
    DOCUMENT: number;
  };
  baseScore: number;
  dampeningFactor: number;
  activeBenignContexts: string[];
  dampenedScore: number;
  hardCollusionOverride: boolean;
  clusterEligible: boolean;
  clusterBoost: number;
  preFloorScore: number;
  finalIefScore: number;
  riskTier: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
}

export interface CleanRoomResult {
  nodes: string[];
  adjacencyMatrix: number[][];
  degreeVector: number[];
  transitionMatrix: number[][];
  convergedIteration: number;
  convergedL1Error: number;
  convergedVector: number[];
  claimPageRankSum: number;
  checkpoints: PageRankCheckpoint[];
  claims: CleanRoomClaimScore[];
}

export function runCleanRoomEvaluation(options?: { addressAblation?: boolean }): CleanRoomResult {
  const addressAblation = options?.addressAblation ?? false;
  const nodes = [
    'CLM-2026-000001',
    'CLM-2026-000002',
    'CLM-2026-000003',
    'CLM-2026-000004',
    'CLMT-000001',
    'CLMT-000002',
    'CLMT-000003',
    'PRV-000001',
  ];
  const N = nodes.length;
  const W: number[][] = Array.from({ length: N }, () => Array(N).fill(0));

  const addSym = (u: number, v: number, w: number) => {
    W[u][v] += w;
    W[v][u] += w;
  };

  // Structural FK edges (w = 1.0)
  addSym(0, 4, 1.0);
  addSym(0, 7, 1.0);
  addSym(1, 5, 1.0);
  addSym(1, 7, 1.0);
  addSym(2, 6, 1.0);
  addSym(2, 7, 1.0);
  addSym(3, 6, 1.0);

  // Operational RelationshipEdges
  // E1: SHARED_BANK_ACCOUNT between CLMT-000001 (4) and CLMT-000002 (5): 3.0 * 1.0 = 3.0
  addSym(4, 5, 3.0);
  // E2: SAME_INCIDENT_PARTICIPANT between CLMT-000002 (5) and CLMT-000003 (6): 1.2 * 0.5 = 0.6
  addSym(5, 6, 0.6);

  const d = W.map((row) => row.reduce((acc, val) => acc + val, 0));

  const M: number[][] = Array.from({ length: N }, (_, i) =>
    Array.from({ length: N }, (__, j) => (d[j] > 0 ? W[j][i] / d[j] : 1 / N))
  );

  const alpha = 0.85;
  let v = Array(N).fill(1 / N);
  const trackedIterations = new Set([0, 1, 2, 3, 5, 10, 20, 40, 60, 77, 78]);
  const checkpoints: PageRankCheckpoint[] = [{ iteration: 0, l1Error: 0, vector: [...v] }];

  let convergedIteration = 200;
  let convergedL1Error = 0;

  for (let it = 1; it <= 200; it++) {
    const vNext = Array(N).fill(0);
    let danglingMass = 0;
    for (let j = 0; j < N; j++) {
      if (d[j] === 0) danglingMass += v[j];
    }
    for (let i = 0; i < N; i++) {
      let mv = danglingMass / N;
      for (let j = 0; j < N; j++) {
        if (d[j] > 0) mv += M[i][j] * v[j];
      }
      vNext[i] = alpha * mv + (1 - alpha) / N;
    }
    let err = 0;
    for (let i = 0; i < N; i++) {
      err += Math.abs(vNext[i] - v[i]);
    }
    v = vNext;
    if (trackedIterations.has(it) || err < 1e-9) {
      checkpoints.push({ iteration: it, l1Error: err, vector: [...v] });
    }
    if (err < 1e-9) {
      convergedIteration = it;
      convergedL1Error = err;
      break;
    }
  }

  const claimPageRankSum = v[0] + v[1] + v[2] + v[3];
  const prTilde = [0, 1, 2, 3].map((i) => (4 * v[i]) / claimPageRankSum);

  const dupFp = computeLineItemFingerprint('AB-FRAME-101', '2026-01-05T09:30:00Z', '2026-01-05T10:00:00Z', 420000);

  // Build claim evaluations
  const rawClaims = [
    {
      idx: 0,
      claimId: 'CLM-2026-000001',
      claimantId: 'CLMT-000001',
      providerId: 'PRV-000001',
      indicators: [
        {
          code: 'IND-01',
          name: 'SHARED_PAYOUT_ACCOUNT',
          pillar: 'NETWORK' as const,
          rawPoints: 20.0,
          maxPoints: 35.0,
          token: 'BANK:' + 'b1'.repeat(32),
        },
        {
          code: 'IND-03',
          name: 'CROSS_CLAIMANT_DUPLICATE_INVOICE',
          pillar: 'FINANCIAL' as const,
          rawPoints: 35.0,
          maxPoints: 35.0,
          token: 'DUP_FP:' + dupFp,
        },
      ],
      activeBenignContexts: [] as string[],
      rawMultipliers: [] as number[],
      hardCollusionOverride: true,
    },
    {
      idx: 1,
      claimId: 'CLM-2026-000002',
      claimantId: 'CLMT-000002',
      providerId: 'PRV-000001',
      indicators: [
        {
          code: 'IND-01',
          name: 'SHARED_PAYOUT_ACCOUNT',
          pillar: 'NETWORK' as const,
          rawPoints: 20.0,
          maxPoints: 35.0,
          token: 'BANK:' + 'b1'.repeat(32),
        },
        {
          code: 'IND-03',
          name: 'CROSS_CLAIMANT_DUPLICATE_INVOICE',
          pillar: 'FINANCIAL' as const,
          rawPoints: 35.0,
          maxPoints: 35.0,
          token: 'DUP_FP:' + dupFp,
        },
      ],
      activeBenignContexts: [] as string[],
      rawMultipliers: [] as number[],
      hardCollusionOverride: true,
    },
    {
      idx: 2,
      claimId: 'CLM-2026-000003',
      claimantId: 'CLMT-000003',
      providerId: 'PRV-000001',
      indicators: [] as Array<{
        code: string;
        name: string;
        pillar: 'NETWORK' | 'FINANCIAL' | 'BEHAVIORAL' | 'DOCUMENT';
        rawPoints: number;
        maxPoints: number;
        token: string;
      }>,
      activeBenignContexts: ['BC-6 (Clean In-Network Tenure, m=0.75)'],
      rawMultipliers: [0.75],
      hardCollusionOverride: false,
    },
    {
      idx: 3,
      claimId: 'CLM-2026-000004',
      claimantId: 'CLMT-000003',
      providerId: 'NONE',
      indicators: [
        {
          code: 'IND-14',
          name: 'CLAIMANT_VELOCITY_BURST',
          pillar: 'BEHAVIORAL' as const,
          rawPoints: addressAblation ? 8.0 : 8.0,
          maxPoints: 16.0,
          token: 'VEL:CLMT-000003',
        },
      ],
      activeBenignContexts: [
        'BC-5 (Police-Reported Multi-Party Incident, m=0.25)',
        'BC-6 (Clean In-Network Tenure, m=0.75)',
      ],
      rawMultipliers: [0.25, 0.75],
      hardCollusionOverride: false,
    },
  ];

  // Add IND-06 if prTilde > 1.25
  for (const rc of rawClaims) {
    const pr = prTilde[rc.idx];
    if (pr > 1.25) {
      const pts = Math.min(15.0, 15.0 * ((pr - 1.25) / 2.75));
      rc.indicators.push({
        code: 'IND-06',
        name: 'PAGERANK_CENTRALITY_SPIKE',
        pillar: 'NETWORK',
        rawPoints: pts,
        maxPoints: 15.0,
        token: `PR:${rc.claimId}`,
      });
    }
  }

  // Stage 2-5: Dedup, Pillar Normalization, Base Score, Dampening
  const intermediate = rawClaims.map((rc) => {
    const dedupMap = new Map<string, typeof rc.indicators[number]>();
    for (const ind of rc.indicators) {
      const key = `${ind.code}|${ind.token}`;
      const existing = dedupMap.get(key);
      if (!existing || ind.rawPoints > existing.rawPoints) {
        dedupMap.set(key, ind);
      }
    }
    const deduped = Array.from(dedupMap.values());
    const sumPillar = (p: 'NETWORK' | 'FINANCIAL' | 'BEHAVIORAL' | 'DOCUMENT') =>
      deduped.filter((i) => i.pillar === p).reduce((s, i) => s + i.rawPoints, 0);

    const pNet = Math.min(100.0, (100.0 * sumPillar('NETWORK')) / 60.0);
    const pFin = Math.min(100.0, (100.0 * sumPillar('FINANCIAL')) / 55.0);
    const pBeh = Math.min(100.0, (100.0 * sumPillar('BEHAVIORAL')) / 45.0);
    const pDoc = Math.min(100.0, (100.0 * sumPillar('DOCUMENT')) / 40.0);

    const baseScore = 0.35 * pNet + 0.30 * pFin + 0.20 * pBeh + 0.15 * pDoc;
    const prodMult = rc.rawMultipliers.reduce((a, b) => a * b, 1.0);
    const dampeningFactor = rc.hardCollusionOverride ? 1.0 : Math.max(0.15, prodMult);
    const dampenedScore = baseScore * dampeningFactor;

    return {
      ...rc,
      deduped,
      pillarScores: { NETWORK: pNet, FINANCIAL: pFin, BEHAVIORAL: pBeh, DOCUMENT: pDoc },
      baseScore,
      dampeningFactor,
      dampenedScore,
    };
  });

  // Stage 6-7: Cluster eligibility (K_eligible = {c_1, c_2} with rho_K = 1.0)
  const eligible = intermediate.filter((c) => c.hardCollusionOverride);
  const maxDamp = eligible.length >= 2 ? Math.max(...eligible.map((c) => c.dampenedScore)) : 0;
  const meanDamp =
    eligible.length >= 2 ? eligible.reduce((s, c) => s + c.dampenedScore, 0) / eligible.length : 0;
  const rhoK = 1.0;

  const claims: CleanRoomClaimScore[] = intermediate.map((c) => {
    const clusterEligible = c.hardCollusionOverride;
    const clusterBoost =
      clusterEligible && eligible.length >= 2
        ? Math.min(20.0, 0.20 * maxDamp + 0.10 * meanDamp + 5.0 * rhoK)
        : 0.0;
    const preFloorScore = Math.min(100.0, c.dampenedScore + clusterBoost);
    const rawFinal = c.hardCollusionOverride ? Math.max(preFloorScore, 65.0) : preFloorScore;
    const finalIefScore = Math.round(rawFinal * 100) / 100;
    const riskTier: CleanRoomClaimScore['riskTier'] =
      finalIefScore >= 85.0
        ? 'CRITICAL'
        : finalIefScore >= 65.0
          ? 'HIGH'
          : finalIefScore >= 30.0
            ? 'MEDIUM'
            : 'LOW';

    return {
      claimId: c.claimId,
      claimantId: c.claimantId,
      providerId: c.providerId,
      rawPageRank: v[c.idx],
      normalizedPageRank: prTilde[c.idx],
      emittedIndicators: c.deduped,
      pillarScores: c.pillarScores,
      baseScore: c.baseScore,
      dampeningFactor: c.dampeningFactor,
      activeBenignContexts: c.activeBenignContexts,
      dampenedScore: c.dampenedScore,
      hardCollusionOverride: c.hardCollusionOverride,
      clusterEligible,
      clusterBoost,
      preFloorScore,
      finalIefScore,
      riskTier,
    };
  });

  return {
    nodes,
    adjacencyMatrix: W,
    degreeVector: d,
    transitionMatrix: M,
    convergedIteration,
    convergedL1Error,
    convergedVector: v,
    claimPageRankSum,
    checkpoints,
    claims,
  };
}

/**
 * CRITICAL 1, 2, 3, 7: Financial Ledger & FSM State Machine Sandbox
 */
export type ClaimStatus =
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'PARTIALLY_PAID'
  | 'PAID'
  | 'SIU_HOLD'
  | 'DENIED'
  | 'CLOSED_NO_PAY';

export type InvoiceStatus =
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'PARTIALLY_PAID'
  | 'PAID'
  | 'REJECTED_DUPLICATE'
  | 'REJECTED_ELIGIBILITY'
  | 'REVOKED_POST_APPROVAL';

export type PaymentStatus =
  | 'AUTHORIZED'
  | 'DISBURSED'
  | 'BLOCKED_OVERPAYMENT'
  | 'BLOCKED_UNAPPROVED'
  | 'BLOCKED_INVALID_RECIPIENT'
  | 'REVERSED_CLAWBACK'
  | 'CANCELLED';

export interface LedgerPayment {
  paymentId: string;
  status: PaymentStatus;
  amountCents: number;
  disbursedAmountCents: number;
  clawedBackCents: number;
  netPaidCents: number;
  idempotencyKey: string;
  createdAtUtc: string;
  disbursedAtUtc: string | null;
  reversedAtUtc: string | null;
  externalBankTxRef: string | null;
}

export interface LedgerState {
  claimId: string;
  policyCoverageCents: number;
  policyDeductibleCents: number;
  claimedAmountCents: number;
  payoutCapCents: number;
  claimStatus: ClaimStatus;
  invoiceId: string;
  billedCents: number;
  invoiceStatus: InvoiceStatus;
  approvedCents: number;
  historicalApprovedCents: number;
  reservedAuthorizedCents: number;
  grossDisbursedCents: number;
  clawedBackCents: number;
  netPaidCents: number;
  adjustmentAuthorizedEventPresent: boolean;
  payments: LedgerPayment[];
  lastActionNote: string;
  lastError: string | null;
}

export function createInitialLedgerState(): LedgerState {
  return {
    claimId: 'CLM-2026-000001',
    policyCoverageCents: 500000,
    policyDeductibleCents: 50000,
    claimedAmountCents: 420000,
    payoutCapCents: 420000,
    claimStatus: 'UNDER_REVIEW',
    invoiceId: 'INV-PRV-PRV-000001-000001',
    billedCents: 420000,
    invoiceStatus: 'SUBMITTED',
    approvedCents: 0,
    historicalApprovedCents: 0,
    reservedAuthorizedCents: 0,
    grossDisbursedCents: 0,
    clawedBackCents: 0,
    netPaidCents: 0,
    adjustmentAuthorizedEventPresent: false,
    payments: [],
    lastActionNote: 'Initial state: Claim UNDER_REVIEW, Invoice SUBMITTED ($4,200.00 billed).',
    lastError: null,
  };
}

export type FinancialCommand =
  | { type: 'APPROVE_INVOICE'; approvedCents: number }
  | { type: 'RECORD_ADJUSTMENT_EVENT'; newApprovedCents: number }
  | { type: 'ADJUST_APPROVED_INVOICE'; newApprovedCents: number }
  | { type: 'AUTHORIZE_PAYMENT'; paymentId: string; amountCents: number }
  | { type: 'DISBURSE_PAYMENT'; paymentId: string; bankRef: string }
  | { type: 'CLAWBACK_PAYMENT'; paymentId: string; clawbackCents: number }
  | { type: 'REVOKE_INVOICE' }
  | { type: 'DENY_CLAIM' }
  | { type: 'ADVERSARIAL_DIRECT_PAID_STATUS' }
  | { type: 'ADVERSARIAL_DIRECT_DISBURSED_INSERT' }
  | { type: 'ADVERSARIAL_TAMPER_BANK_REF' }
  | { type: 'ADVERSARIAL_ZERO_HISTORICAL_APPROVED' };

export function applyFinancialCommand(state: LedgerState, cmd: FinancialCommand): LedgerState {
  const s: LedgerState = {
    ...state,
    payments: state.payments.map((p) => ({ ...p })),
    lastError: null,
  };

  const syncRollups = () => {
    s.reservedAuthorizedCents = s.payments
      .filter((p) => p.status === 'AUTHORIZED')
      .reduce((acc, p) => acc + p.amountCents, 0);
    s.grossDisbursedCents = s.payments
      .filter((p) => p.status === 'DISBURSED' || p.status === 'REVERSED_CLAWBACK')
      .reduce((acc, p) => acc + p.disbursedAmountCents, 0);
    s.clawedBackCents = s.payments
      .filter((p) => p.status === 'REVERSED_CLAWBACK')
      .reduce((acc, p) => acc + p.clawedBackCents, 0);
    s.netPaidCents = s.grossDisbursedCents - s.clawedBackCents;

    if (s.invoiceStatus !== 'REVOKED_POST_APPROVAL') {
      if (s.netPaidCents === s.approvedCents && s.reservedAuthorizedCents === 0 && s.approvedCents > 0) {
        s.invoiceStatus = 'PAID';
      } else if (s.netPaidCents > 0 && s.netPaidCents < s.approvedCents) {
        s.invoiceStatus = 'PARTIALLY_PAID';
      } else if (s.approvedCents > 0) {
        s.invoiceStatus = 'APPROVED';
      }
    }

    if (s.claimStatus !== 'DENIED' && s.claimStatus !== 'CLOSED_NO_PAY' && s.claimStatus !== 'SIU_HOLD') {
      if (s.approvedCents === 0) {
        s.claimStatus = 'SIU_HOLD';
      } else if (s.netPaidCents === s.approvedCents && s.reservedAuthorizedCents === 0) {
        s.claimStatus = 'PAID';
      } else if (s.netPaidCents > 0) {
        s.claimStatus = 'PARTIALLY_PAID';
      } else {
        s.claimStatus = 'APPROVED';
      }
    }
  };

  switch (cmd.type) {
    case 'APPROVE_INVOICE': {
      if (s.invoiceStatus !== 'SUBMITTED' && s.invoiceStatus !== 'UNDER_REVIEW') {
        return {
          ...s,
          lastError: 'ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE: Invoice is already approved or terminal.',
        };
      }
      if (cmd.approvedCents <= 0 || cmd.approvedCents > s.billedCents || cmd.approvedCents > s.payoutCapCents) {
        return {
          ...s,
          lastError: 'ERR_INVOICE_EXCEEDS_CLAIM_OR_POLICY_CAP: Approved amount exceeds billed or policy payout cap.',
        };
      }
      s.invoiceStatus = 'APPROVED';
      s.approvedCents = cmd.approvedCents;
      s.historicalApprovedCents = cmd.approvedCents;
      s.claimStatus = 'APPROVED';
      s.lastActionNote = `Approved invoice for $${(cmd.approvedCents / 100).toFixed(2)}; historical_approved_cents set to $${(cmd.approvedCents / 100).toFixed(2)}.`;
      return s;
    }

    case 'RECORD_ADJUSTMENT_EVENT': {
      s.adjustmentAuthorizedEventPresent = true;
      s.lastActionNote = `Recorded immutable event INVOICE_APPROVAL_ADJUSTED authorizing adjustment to $${(cmd.newApprovedCents / 100).toFixed(2)}.`;
      return s;
    }

    case 'ADJUST_APPROVED_INVOICE': {
      if (s.invoiceStatus !== 'APPROVED') {
        return {
          ...s,
          lastError: 'ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE: Only APPROVED invoices (prior to disbursement) can be adjusted.',
        };
      }
      if (!s.adjustmentAuthorizedEventPresent) {
        return {
          ...s,
          lastError:
            'ERR_INVOICE_POST_APPROVAL_AMOUNT_IMMUTABLE: Direct update to approved_cents without INVOICE_APPROVAL_ADJUSTED event blocked by trg_invoices_fsm_upd.',
        };
      }
      const maxCap = Math.min(s.claimedAmountCents, s.payoutCapCents, s.policyCoverageCents - s.policyDeductibleCents);
      if (
        cmd.newApprovedCents <= 0 ||
        cmd.newApprovedCents > s.billedCents ||
        cmd.newApprovedCents > maxCap ||
        cmd.newApprovedCents < s.reservedAuthorizedCents + s.netPaidCents
      ) {
        return {
          ...s,
          lastError:
            'ERR_INVOICE_EXCEEDS_CLAIM_OR_POLICY_CAP: Adjusted approval violates claim/policy cap or active payment exposure.',
        };
      }
      s.approvedCents = cmd.newApprovedCents;
      s.historicalApprovedCents = Math.max(s.historicalApprovedCents, cmd.newApprovedCents);
      s.adjustmentAuthorizedEventPresent = false;
      s.lastActionNote = `Adjusted invoice approval to $${(cmd.newApprovedCents / 100).toFixed(2)}; historical high-water mark is $${(s.historicalApprovedCents / 100).toFixed(2)}.`;
      return s;
    }

    case 'AUTHORIZE_PAYMENT': {
      if (s.invoiceStatus !== 'APPROVED' && s.invoiceStatus !== 'PARTIALLY_PAID') {
        return {
          ...s,
          lastError: 'ERR_PAYMENT_REQUIRES_APPROVED_CLAIM_AND_INVOICE: Cannot authorize payment on unapproved/revoked invoice.',
        };
      }
      if (s.reservedAuthorizedCents + s.netPaidCents + cmd.amountCents > s.approvedCents) {
        return {
          ...s,
          lastError: 'ERR_PAYMENT_EXCEEDS_APPROVED_CAP: Cumulative reserved + net paid exceeds approved_cents.',
        };
      }
      s.payments.push({
        paymentId: cmd.paymentId,
        status: 'AUTHORIZED',
        amountCents: cmd.amountCents,
        disbursedAmountCents: 0,
        clawedBackCents: 0,
        netPaidCents: 0,
        idempotencyKey: `IDEMP-${cmd.paymentId}`,
        createdAtUtc: '2026-01-07T08:00:00Z',
        disbursedAtUtc: null,
        reversedAtUtc: null,
        externalBankTxRef: null,
      });
      syncRollups();
      s.lastActionNote = `Authorized payment ${cmd.paymentId} for $${(cmd.amountCents / 100).toFixed(2)} (reserved_authorized_cents = $${(s.reservedAuthorizedCents / 100).toFixed(2)}).`;
      return s;
    }

    case 'DISBURSE_PAYMENT': {
      const p = s.payments.find((x) => x.paymentId === cmd.paymentId);
      if (!p || p.status !== 'AUTHORIZED') {
        return {
          ...s,
          lastError: 'ERR_PAYMENT_INVALID_STATE_TRANSITION: Only AUTHORIZED payments can transition to DISBURSED.',
        };
      }
      p.status = 'DISBURSED';
      p.disbursedAmountCents = p.amountCents;
      p.netPaidCents = p.amountCents;
      p.disbursedAtUtc = '2026-01-07T12:00:00Z';
      p.externalBankTxRef = cmd.bankRef;
      syncRollups();
      s.lastActionNote = `Disbursed ${cmd.paymentId} ($${(p.amountCents / 100).toFixed(2)}, ref ${cmd.bankRef}) -> status=${s.invoiceStatus}.`;
      return s;
    }

    case 'CLAWBACK_PAYMENT': {
      const p = s.payments.find((x) => x.paymentId === cmd.paymentId);
      if (!p || (p.status !== 'DISBURSED' && p.status !== 'REVERSED_CLAWBACK')) {
        return {
          ...s,
          lastError: 'ERR_PAYMENT_INVALID_STATE_TRANSITION: Clawback requires a DISBURSED or REVERSED_CLAWBACK payment.',
        };
      }
      const newClawback = p.clawedBackCents + cmd.clawbackCents;
      if (cmd.clawbackCents <= 0 || newClawback > p.disbursedAmountCents) {
        return {
          ...s,
          lastError: 'ERR_CLAWBACK_EXCEEDS_DISBURSED: Clawback must be positive and cannot exceed disbursed_amount_cents.',
        };
      }
      p.status = 'REVERSED_CLAWBACK';
      p.clawedBackCents = newClawback;
      p.netPaidCents = p.disbursedAmountCents - newClawback;
      p.reversedAtUtc = '2026-01-12T16:45:00Z';
      syncRollups();
      s.lastActionNote = `Clawed back $${(cmd.clawbackCents / 100).toFixed(2)} on ${cmd.paymentId}; net_paid_cents=$${(s.netPaidCents / 100).toFixed(2)}, historical_approved_cents=$${(s.historicalApprovedCents / 100).toFixed(2)} preserved.`;
      return s;
    }

    case 'REVOKE_INVOICE': {
      if (s.reservedAuthorizedCents !== 0 || s.netPaidCents !== 0 || s.historicalApprovedCents === 0) {
        return {
          ...s,
          lastError:
            'ERR_INVOICE_REVOKED_FINANCIAL_MISMATCH: Invoice revocation requires reserved_authorized_cents = 0 and net_paid_cents = 0 (full clawback required first).',
        };
      }
      s.invoiceStatus = 'REVOKED_POST_APPROVAL';
      s.approvedCents = 0;
      s.claimStatus = 'SIU_HOLD';
      s.lastActionNote = `Revoked invoice post-approval: approved_cents=0, historical_approved_cents=$${(s.historicalApprovedCents / 100).toFixed(2)} preserved; claim placed on SIU_HOLD.`;
      return s;
    }

    case 'DENY_CLAIM': {
      if (s.approvedCents !== 0 || s.reservedAuthorizedCents !== 0 || s.netPaidCents !== 0) {
        return {
          ...s,
          lastError:
            'ERR_CLAIM_DENIED_MUST_HAVE_ZERO_ACTIVE_EXPOSURE: Cannot deny claim while active approved_amount_cents, reserved_authorized_cents, or net_paid_cents > 0.',
        };
      }
      s.claimStatus = 'DENIED';
      s.lastActionNote = `Claim transitioned to DENIED; historical_approved_cents=$${(s.historicalApprovedCents / 100).toFixed(2)} permanently preserved for audit.`;
      return s;
    }

    case 'ADVERSARIAL_DIRECT_PAID_STATUS': {
      return {
        ...s,
        lastError:
          'ERR_INVOICE_PAID_FINANCIAL_MISMATCH / ERR_CLAIM_PAID_FINANCIAL_MISMATCH: Direct SQL transition to PAID blocked unless net_paid_cents = approved_cents and reserved_authorized_cents = 0.',
      };
    }

    case 'ADVERSARIAL_DIRECT_DISBURSED_INSERT': {
      return {
        ...s,
        lastError:
          'ERR_PAYMENT_INSERT_MUST_BE_AUTHORIZED_OR_BLOCKED: Direct SQL INSERT with payment_status=DISBURSED aborted by trg_payments_validate_ins.',
      };
    }

    case 'ADVERSARIAL_TAMPER_BANK_REF': {
      return {
        ...s,
        lastError:
          'ERR_PAYMENT_POST_DISBURSEMENT_BANK_REF_IMMUTABLE: Direct SQL UPDATE of external_bank_tx_ref or disbursed_at_utc after disbursement aborted by trg_payments_validate_upd.',
      };
    }

    case 'ADVERSARIAL_ZERO_HISTORICAL_APPROVED': {
      return {
        ...s,
        lastError:
          'ERR_INVOICE_HISTORICAL_APPROVED_DECREASE_FORBIDDEN / ERR_CLAIM_HISTORICAL_APPROVED_DECREASE_FORBIDDEN: Direct SQL UPDATE reducing historical_approved_cents aborted.',
      };
    }
  }
}

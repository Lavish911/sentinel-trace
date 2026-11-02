# SENTINEL//TRACE — FRONTEND REDESIGN SPECIFICATION & WORKFLOW ARCHITECTURE

**Document ID:** `SPEC-FE-REDESIGN-001`  
**Target Platform:** SENTINEL//TRACE Forensic Insurance Fraud Intelligence  
**Design Role:** Lead UX Architect & Principal Frontend Engineer  
**Status:** PROPOSED & APPROVED FOR IMPLEMENTATION (Milestones F & G)  

---

## 1. Product Identity & Design System

### 1.1 Aesthetic Foundation
* **Visual Atmosphere:** High-density, restrained, technical, forensic intelligence environment. Designed for Special Investigation Unit (SIU) detectives and fraud analysts who process complex evidence networks.
* **Palette:**
  * **Primary Background:** Dark Charcoal (`#090d12` deep void, `#0f141c` panel background).
  * **Surface / Cards:** Muted slate-zinc (`#161d27` card, `#1f2937` elevated border).
  * **Accent / Intent:** Forensic Amber (`#d97706` amber-600, `#f59e0b` amber-500) representing alert states, investigative focus, and highlights.
  * **Evidence Provenance & Verification:** Emerald (`#10b981` / `#059669`) for verified cryptographic digests and compliant chains.
  * **High-Risk Anomalies:** Crimson (`#ef4444` / `#dc2626`) reserved strictly for confirmed collusive rings, blocked overpayments, and critical risk tiers.
  * **Typography:**
    * Monospace (Tabular Numerics, IDs, Hashes): `JetBrains Mono`, `Fira Code`, or `ui-monospace`.
    * Clean Interface Font: `Inter` or `system-ui`.
* **Explicit Anti-Patterns (Banned):**
  * ❌ No neon purple/cyan glowing borders or generic "futuristic AI" gradient bloat.
  * ❌ No fake sparklines, fake live activity tickers, or simulated CPU/memory gauges.
  * ❌ No massive card padding with low information density.

---

## 2. Investigator Information Architecture & Workspace Layout

The redesigned application transitions from a single-page speculative prototype (`src/App.tsx`) to a 4-panel coordinated investigator cockpit:

```text
+----------------------------------------------------------------------------------------------------+
| SENTINEL//TRACE | Case: INVG-2026-000001 (OPEN) | Filter: All Lines of Business | Investigator: Det. Vance |
+----------------------------------------------------------------------------------------------------+
| 1. QUEUE & TRIAGE     | 2. NETWORK & TOPOLOGY          | 3. DOSSIER & EVIDENCE WATERFALL             |
| Search: [ CLM-2026- ] | (Cytoscape / Canvas Explorer)  | Claim: CLM-2026-000001                      |
|                       |                                | Final IEF Score: 65.00 [HIGH]               |
| [Triage Table]        | (Claimants, Policies, Phones,  | ------------------------------------------- |
| • CLM-001  65.0  HIGH |  Providers, Bank Accounts)     | • Base Score (S_base):   30.76 pts          |
| • CLM-002  65.0  HIGH |                                | • Dampening Factor:       1.00 (No benign)  |
| • CLM-003   0.0   LOW | [Cluster: Ring-04 (Collusion)] | • Cluster Boost:         +14.23 pts         |
| • CLM-004   0.67  LOW | 4 Claims · 2 Providers         | • Hard Floor Override:    65.00 [ACTIVE]    |
|                       |                                | ------------------------------------------- |
| [Filters]             | [Edge Provenance]              | 4. FINANCIAL LEDGER & AUDIT TRAIL           |
| Risk Tier: [All/High] | Shared Bank Acc (ACH-004)      | Billed:   $4,200.00 | Approved: $3,700.00   |
| Status:    [All/Hold] | Shared Cell (+1-555-0199)      | Reserved:     $0.00 | Net Paid:     $0.00   |
| Ring:      [Ring-04 ] | Duplicate Repair Estimate      | History:  $3,700.00 | Clawback: $3,700.00   |
|                       |                                | ------------------------------------------- |
|                       |                                | [ST-EVT-V2 Merkle Chain: 7/7 Verified]      |
+----------------------------------------------------------------------------------------------------+
| 5. SIU ACTION & CASE MANAGEMENT BAR: [Hold Claim] [Authorize Clawback] [Export Referral Packet]     |
+----------------------------------------------------------------------------------------------------+
```

### 2.1 Workspace Panels
1. **Queue & Triage Panel (Left, 22% width):**
   * Filterable tabular view of claims and investigations.
   * Sort by risk score, loss amount, submission date, or ring cluster.
   * Multi-select triage actions (bulk hold, assign to investigator).
2. **Network Topology Canvas (Center, 48% width):**
   * Interactive multimodal graph: Claimants (circles), Providers (squares), Policies (diamonds), Shared Attributes (triangles).
   * Visual edge styling: Shared Phone (dashed amber), Shared Bank Account (solid red), Shared Address (dotted blue).
   * Ego-network filtering: 1-hop, 2-hop neighborhood expansion around selected suspect.
3. **Forensic Dossier & Score Waterfall (Right, 30% width):**
   * Transparent 10-stage scoring explanation:
     * *Stage 1–3:* Base indicator points per pillar (Network, Financial, Behavioral, Document).
     * *Stage 4:* Pillar caps and weighted sum.
     * *Stage 5:* Benign context dampening multipliers.
     * *Stage 6–7:* Collusive cluster boost and hard-collusion floor (65.00 pts).
     * *Stage 8–10:* Final tier calibration and safety bounding.
4. **Penny-Exact Financial Ledger & Audit Strip (Lower Dock):**
   * Real-time accounting balances: Billed, Current Approved, Historical High-Water Mark, Outstanding Reservations, Gross Disbursed, Clawed Back, and Net Paid.
   * Cryptographic verification badges for each transaction in the length-prefixed `ST-EVT-V2` Merkle chain.
5. **SIU Case Management Drawer (Collapsible):**
   * Formal note-taking, evidence pinning, and one-click PDF/Markdown export for prosecution referral.

---

## 3. Component Architecture & State Management

### 3.1 Directory Structure Plan
```text
src/
├── components/
│   ├── layout/
│   │   ├── TopNavigation.tsx
│   │   ├── WorkspaceShell.tsx
│   │   └── StatusBar.tsx
│   ├── triage/
│   │   ├── ClaimQueueTable.tsx
│   │   ├── FilterBar.tsx
│   │   └── RiskBadge.tsx
│   ├── network/
│   │   ├── NetworkGraphCanvas.tsx
│   │   ├── NodeDetailPopover.tsx
│   │   └── GraphControls.tsx
│   ├── dossier/
│   │   ├── ClaimDossier.tsx
│   │   ├── ScoreWaterfall.tsx
│   │   ├── IndicatorList.tsx
│   │   └── EvidenceInspector.tsx
│   ├── ledger/
│   │   ├── FinancialLedgerTable.tsx
│   │   ├── EventHashChainViewer.tsx
│   │   └── BalanceSummaryCards.tsx
│   └── common/
│       ├── Button.tsx
│       ├── Table.tsx
│       ├── Tabs.tsx
│       └── Modal.tsx
├── hooks/
│   ├── useClaimsQuery.ts
│   ├── useNetworkGraph.ts
│   ├── useClaimDossier.ts
│   └── useInvestigationActions.ts
├── services/
│   ├── api.ts                     (Fetch client targeting /api/v1)
│   └── websocket.ts               (SSE or live polling for triage events)
└── utils/
    ├── sentinelEngine.ts          (Pure domain logic preserved from ARCH-ST-010.2)
    └── formatters.ts              (Currency in cents -> $X,XXX.XX, ISO timestamps)
```

### 3.2 Preservation of Domain Logic
* All core cryptographic math, `ST-EVT-V2` event hashing, and 10-stage scoring formulas currently residing in `src/utils/sentinelEngine.ts` will be **strictly preserved**.
* Domain logic will be treated as pure business functions, decoupled from React UI components, enabling seamless synchronization with the Python backend detection engine.


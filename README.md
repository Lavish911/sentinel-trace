# SENTINEL//TRACE

**Forensic insurance-fraud intelligence for claim triage, evidence review, network analysis, and SIU case management.**

SENTINEL//TRACE is a local FastAPI evaluation workbench. It connects claims, claimants, policies, incidents, providers, invoices, payments, operational relationships, fraud indicators, investigations, and an append-only event ledger. The live application is a self-contained forensic cockpit served at `http://127.0.0.1:8000/`.

> **Canonical baseline:** `ARCH-ST-010.3` · **Dataset:** deterministic seed 42 · **App entry point:** `backend.app.main:app`

## What a reviewer should know in 30 seconds

- **What it solves:** follows a suspicious claim through its related evidence, entities, payments, network, and investigation record.
- **How it detects risk:** 15 explainable indicators are derived from operational facts and scored across four pillars.
- **How it is investigated:** the cockpit offers a claim queue, dossier, indicators, network topology, event timeline, and case workflow.
- **How it avoids label leakage:** `data/operational.db` contains no ground-truth tables or labels. Synthetic labels and withheld edges are physically isolated in `data/ground_truth.db` and used only by evaluators.
- **What is actually shipped:** FastAPI plus a zero-build HTML/CSS/SVG cockpit. The React/Vite code in `src/` is an archival prototype, not the runtime UI.

## Reviewer fast path

`Install → Generate → Verify → Run → Investigate`

```bash
python -m pip install -r backend/requirements.txt
python scripts/generate_dataset.py
python -m pytest backend/tests/ -v
python -m uvicorn backend.app.main:app --port 8000
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and select a high-risk claim such as `CLM-2026-000050`. The generated SQLite files live in `data/` and are intentionally ignored by Git; generation must occur before running the app or database-backed tests.

## Runtime architecture

```mermaid
flowchart LR
    Browser[Investigator browser] --> Cockpit[FastAPI cockpit\nbackend.app.main:app]
    Cockpit --> API[/api/v1]
    API --> Ops[(data/operational.db\n12 STRICT tables · 27 triggers)]
    Ops --> Graph[Operational relationship graph]
    Graph --> Score[15 explainable indicators\nIEF scoring]
    Score --> Cases[SIU investigations]
    Cases --> Ledger[immutable_events\nST-EVT-V2 hash chain]
    GT[(data/ground_truth.db\nquarantined evaluator data)] -. no runtime access .-> API
```

### Operational boundaries

| Component | Role | Runtime status |
|---|---|---|
| `backend/app/main.py` | FastAPI entry point and cockpit delivery | Active |
| `backend/app/templates/cockpit.html` | Investigator UI | Active |
| `data/operational.db` | Operational claims, relationships, scores, cases, audit events | Generated locally |
| `data/ground_truth.db` | Withheld labels and negative-scenario evaluation data | Generated locally; evaluator-only |
| `db/seed.py` | Canonical deterministic dataset generator | Active |
| `archive/verify-0103/` | Shipped ARCH-ST-010.3 schema SQL and verification evidence | Protected / runtime-referenced |
| `src/`, `vite.config.ts` | Earlier React/Vite prototype | Archival only |

## Data and evidence model

The operational database contains 12 strict tables: `claimants`, `policies`, `incidents`, `claims`, `providers`, `invoices`, `payments`, `relationship_edges`, `fraud_indicators`, `investigations`, `immutable_events`, and `ingestion_exceptions`.

The seed-42 baseline has 5,000 claims, 8,000 active relationship edges, 4,120 persisted findings, 45 investigations, and 19,675 immutable events. Startup verifies the canonical schema before serving traffic: 12 tables, 27 triggers, and schema digest `2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab`.

### Audit trail guarantee and boundary

`immutable_events` is an append-only sequential SHA-256 chain using `ST-EVT-V2` serialization. It detects post-hoc insertion, reordering, truncation, or modification of ledger history.

This is an **unkeyed integrity check**, not proof of authorship or non-repudiation. A production deployment would add authenticated writer identity and signed or HMAC-protected event provenance.

## Explainable scoring

The generator evaluates 15 observable indicators over four pillars:

| Pillar | Indicators |
|---|---|
| Network | `IND-01`, `IND-02`, `IND-05`, `IND-06`, `IND-07` |
| Financial | `IND-03`, `IND-04`, `IND-08`, `IND-12` |
| Behavioral | `IND-09`, `IND-10`, `IND-11`, `IND-14` |
| Document | `IND-13`, `IND-15` |

The pipeline builds the active graph and PageRank, derives indicators from operational facts, deduplicates a claim's `(indicator_code, canonical_evidence_token)` rows, normalizes pillar totals with caps of 60/55/45/40, and applies weights of 0.35/0.30/0.20/0.15.

Benign contexts use `D = max(0.15, product(m_b))`; eligible hard-collusion pairs receive `D = 1.0`, a component boost, and a 65-point floor. The final score, tier, and SHA-256 evidence digest are persisted together.

## Negative scenarios and isolation

| Scenario | Control verified by the repository |
|---|---|
| YF-NEG-1 | 25 nonexistent-policy attempts are quarantined in `ingestion_exceptions`. |
| YF-NEG-2 | Over-cap payments are blocked by `ERR_PAYMENT_EXCEEDS_APPROVED_CAP`. |
| YF-NEG-3 | Cross-claimant duplicate invoices are linked to observable fraud evidence. |
| YF-NEG-4 | 25 withheld edges remain outside the operational graph; 36/40 ring claims score `HIGH` from observable facts. |
| YF-NEG-5 | 80 high-density benign-address claims remain `LOW`; seed-42 empirical maximum is 0.44 with no false positives. |

The operational API intentionally rejects `yf_neg_4` filtering: that scenario is ground-truth-only. It supports a bounded `yf_neg_5` operational address view without exposing labels.

## Three-minute reviewer walkthrough

1. **Dashboard:** open `/` and confirm the dataset baseline, risk distribution, entity counts, and audit-chain tip.
2. **Triage:** open **Claims**, choose `HIGH` or `CRITICAL`, and select a claim.
3. **Dossier:** review claimant, policy, incident, provider invoices, payment history, score, and evidence digest together.
4. **Why it is suspicious:** select **Fraud Indicators** to inspect codes, raw points, pillar, and canonical evidence tokens.
5. **Who is connected:** select **Network Topology** to inspect the operational ego network and active edges.
6. **What happened:** select **Event Chain** to inspect chronological `ST-EVT-V2` events.
7. **Case handling:** open or inspect the related SIU investigation, append an evidence note, and follow the allowed status transitions.

Existing reference captures are available in [`docs/screenshots/`](docs/screenshots/), from dashboard overview through the event-chain view and error handling.

## API surface

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Schema, trigger, and health status |
| `GET /api/v1/dashboard/stats` | Portfolio, entities, findings, and audit-chain summary |
| `GET /api/v1/claims` | Filterable, paginated triage queue |
| `GET /api/v1/claims/{id}` | Multi-entity claim dossier |
| `GET /api/v1/claims/{id}/indicators` | Explainable findings |
| `GET /api/v1/claims/{id}/timeline` | Claim-linked immutable events |
| `GET /api/v1/network/{claim_id}` | Operational ego network |
| `POST /api/v1/claims/{id}/hold` | Place an eligible claim on SIU hold |
| `POST /api/v1/claims/{id}/release` | Release through the benign-closure gate |
| `GET/POST /api/v1/investigations` | List or open investigations |
| `GET/PATCH /api/v1/investigations/{id}` | Review or transition an investigation |
| `POST /api/v1/investigations/{id}/notes` | Append forensic evidence notes |

Interactive OpenAPI documentation is available at `/docs`; ReDoc is at `/redoc`.

## Verification commands

```bash
# FastAPI, workflow, isolation, scoring, and trigger tests (66 tests)
python -m pytest backend/tests/ -v

# Canonical database acceptance checks (T-01 through T-20)
python -m db.test_suite

# Atomic event-and-state rollback checks (8 tests)
python -m unittest db.test_atomicity

# Path safety, negative cases, BC-1, isolation, and digest checks (8 checks)
python scripts/verify_p0_hardening.py

# Deterministic dual-run check
python scripts/generate_dataset.py --dual-run
```

Normal application startup is deliberately fail-closed: it will not create or silently seed a missing database.

## Security and deployment notes

- SQLite is appropriate here for a local evaluator or single-node workstation; concurrent writers are serialized.
- The demo has no end-user authentication or authorization. Do not expose port 8000 publicly without an upstream identity and network control.
- SQL parameters and database triggers protect the documented runtime paths, but a privileged raw-SQL writer is outside the provenance trust boundary described above.
- `.env.example` is a template only. Do not commit populated environment files, credentials, or generated data files.

## AI transparency and provenance

The project’s AI-development disclosure is maintained in [`AI_TRANSPARENCY_DISCLOSURE.md`](AI_TRANSPARENCY_DISCLOSURE.md). It records the actual development context and should be updated only with authentic contribution history; do not manufacture prompts, tool output, or provenance.

Architecture lineage, corrective evidence, and verification records are preserved rather than deleted:

- [`ARCH-ST-010.3.md`](ARCH-ST-010.3.md) — active baseline specification
- [`VERIFICATION_REPORT_0103.md`](VERIFICATION_REPORT_0103.md) — verification report
- [`CORRECTION_TRACEABILITY_0103.md`](CORRECTION_TRACEABILITY_0103.md) — remediation traceability
- [`archive/verify-0103/`](archive/verify-0103/) — shipped schema/digest verification assets

---

SENTINEL//TRACE is designed to make the investigation path reviewable: **claim → connected entities → explainable evidence → operational network → auditable SIU decision**.

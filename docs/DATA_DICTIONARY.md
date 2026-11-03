# Operational data dictionary

The source of truth for this dictionary is `archive/verify-0103/ops_0103.sql`. All tables are SQLite `STRICT` tables; foreign keys and additional trigger rules are defined in the shipped SQL files.

| Table | Purpose | Key columns |
| --- | --- | --- |
| `claimants` | Synthetic people and payment identity attributes. | `claimant_id` (PK); name, DOB, normalized contact/address fields; hashed tax, routing, and account identifiers; `created_at_utc`. |
| `policies` | Policy coverage for a claimant. | `policy_id` (PK); `claimant_id` (FK); policy number, line/status, coverage dates, coverage, deductible, premium cents. |
| `incidents` | Reported loss events. | `incident_id` (PK); incident/report timestamps, type, state, normalized location, geohash, optional police report, weather, description. |
| `claims` | Core claim record and current score. | `claim_id` (PK); policy, claimant, incident FKs; lifecycle status; monetary ledger fields in cents; SIU flag; `latest_ief_score`, `latest_risk_tier`, and evidence digest. |
| `providers` | Synthetic service providers. | `provider_id` (PK); identity/type/licence; hashed tax and banking fields; contact/address; network tier; creation time. |
| `invoices` | Provider invoice tied to a claim. | `invoice_id` (PK); claim and provider FKs; service/submission times; line item fingerprint; billed/approved/payment ledger fields; optional duplicate-of FK. |
| `payments` | Authorized, blocked, disbursed, reversed, or cancelled payments. | `payment_id` (PK); claim/invoice FKs; recipient references; status; amount/payment ledger fields; idempotency key; timestamps and reason fields. |
| `relationship_edges` | Operational graph edges only. | `edge_id` (PK); typed source/target references and canonical keys; strength, evidence count, observed period, supporting claim, active flag. |
| `fraud_indicators` | Derived, explainable claim indicators. | `indicator_id` (PK); claim FK; code, pillar, scope, evidence token, severity, raw/max points, normalized value, canonical feature JSON, computation time. |
| `investigations` | SIU case lifecycle. | `investigation_id` (PK); primary claim and subject references; status, priority, investigator, case timestamps/outcome, exposure and recovery cents, notes. |
| `immutable_events` | Append-only event-chain records. | `sequence_no` (PK); event ID/type/entity/claim; actor and timestamp; canonical payload, payload hash, previous hash, event hash. |
| `ingestion_exceptions` | Rejected input attempts. | `exception_id` (PK); attempted claim/policy, claimant/incident FKs, attempted amount, exception code, canonical raw payload, time, event FK. |

## Conventions

- Monetary values ending in `_cents` are integer cents, not decimal currency.
- UTC timestamps are ISO-like text values ending in `Z`.
- Hash columns are lowercase SHA-256 hex strings where enforced by the schema.
- `fraud_indicators` are operationally derived signals, not ground-truth labels.
- Ground-truth-only tables live in a separate database and are described in `docs/DATA_PROVENANCE.md`.

For allowed values, exact checks, and all foreign keys, consult the SQL source rather than inferring from this summary.

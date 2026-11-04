# SENTINEL//TRACE — Operational Data Dictionary & Entity Specifications

The authoritative source of truth for this schema is [`archive/verify-0103/ops_0103.sql`](../archive/verify-0103/ops_0103.sql) and [`archive/verify-0103/trigs_0103.sql`](../archive/verify-0103/trigs_0103.sql). All tables are SQLite `STRICT` tables with active foreign key enforcement (`PRAGMA foreign_keys = ON;`) and recursive triggers (`PRAGMA recursive_triggers = ON;`).

---

## 1. Entity Cardinality & Relationship Matrix

| Source Entity | Target Entity | Cardinality | Implementation / Bridge Table | Foreign Key Column | Delete / Update Action |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `claimants` | `policies` | 1:N | Direct Foreign Key | `policies.claimant_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `claimants` | `claims` | 1:N | Direct Foreign Key | `claims.claimant_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `policies` | `claims` | 1:N | Direct Foreign Key | `claims.policy_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `incidents` | `claims` | 1:N | Direct Foreign Key | `claims.incident_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `claims` | `invoices` | 1:N | Direct Foreign Key | `invoices.claim_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `providers` | `invoices` | 1:N | Direct Foreign Key | `invoices.provider_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `claims` | `payments` | 1:N | Direct Foreign Key | `payments.claim_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `invoices` | `payments` | 1:N | Direct Foreign Key | `payments.invoice_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `claims` | `fraud_indicators` | 1:N | Direct Foreign Key | `fraud_indicators.claim_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `claims` | `investigations` | 1:N | Direct Foreign Key | `investigations.primary_claim_id` | `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| `claimants` | `providers` | N:M | Bridge Table: `relationship_edges` | `canonical_src_key`, `canonical_dst_key` | Evaluated from shared banking, address, phone |
| `claimants` | `claimants` | N:M | Bridge Table: `relationship_edges` | `canonical_src_key`, `canonical_dst_key` | Evaluated from shared address, phone, bank, incident |
| `providers` | `providers` | N:M | Bridge Table: `relationship_edges` | `canonical_src_key`, `canonical_dst_key` | Evaluated from cross-billing and referral links |

---

## 2. Entity Lifecycle States

| Entity | Permitted Status Values | Initial State | Terminal States | State Transition Rules |
| :--- | :--- | :--- | :--- | :--- |
| **Claim** | `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `PARTIALLY_PAID`, `PAID`, `SIU_HOLD`, `DENIED`, `CLOSED_NO_PAY` | `SUBMITTED` | `PAID`, `DENIED`, `CLOSED_NO_PAY` | Enforced by `trg_claims_fsm_upd`. Claims under `SIU_HOLD` cannot exit to `APPROVED` or `PAID` without an explicit `CLOSED_CLEARED_BENIGN` investigation ruling. |
| **Policy** | `ACTIVE`, `LAPSED`, `CANCELLED`, `EXPIRED` | `ACTIVE` | `CANCELLED`, `EXPIRED` | Lapsed policies block new claim submissions but permit pending payment sync on already approved claims. |
| **Invoice** | `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `PARTIALLY_PAID`, `PAID`, `REJECTED_DUPLICATE`, `REJECTED_ELIGIBILITY`, `REVOKED_POST_APPROVAL` | `SUBMITTED` | `PAID`, `REJECTED_DUPLICATE`, `REJECTED_ELIGIBILITY` | Invoices marked `REJECTED_DUPLICATE` must reference `duplicate_of_invoice_id` and have `approved_cents = 0`. |
| **Payment** | `AUTHORIZED`, `DISBURSED`, `BLOCKED_OVERPAYMENT`, `BLOCKED_UNAPPROVED`, `BLOCKED_INVALID_RECIPIENT`, `REVERSED_CLAWBACK`, `CANCELLED` | `AUTHORIZED` | `DISBURSED`, `REVERSED_CLAWBACK`, `CANCELLED` | `DISBURSED` requires bank ref and timestamp. `BLOCKED_*` requires `block_reason_code`. `CANCELLED` requires `cancel_reason`. |
| **Investigation** | `OPEN`, `EVIDENCE_COLLECTION`, `SIU_FIELD_REVIEW`, `LEGAL_ESCALATION`, `CLOSED_CONFIRMED_FRAUD`, `CLOSED_CLEARED_BENIGN`, `CLOSED_INSUFFICIENT_EVIDENCE` | `OPEN` | `CLOSED_*` | Enforced by `trg_investigations_closed_immutable`. Once closed, an investigation record is immutable and sealed. |

---

## 3. Granular Field-by-Field Specifications

### 3.1 Claimant (`claimants`) — 2,000 Rows
Represents synthetic individuals, policyholders, and claimants.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `claimant_id` | `TEXT` | Required | `CLMT-[0-9]{6}` | ID | PK (Unique) | `CHECK (claimant_id GLOB 'CLMT-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `full_name` | `TEXT` | Required | Standardized Name String | — | Non-unique | `NOT NULL` |
| `dob_iso` | `TEXT` | Required | `YYYY-MM-DD` | Date | Non-unique | `CHECK (dob_iso GLOB '[1-2][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]')` |
| `tax_id_hash` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Unique | `CHECK (length(tax_id_hash) = 64 AND tax_id_hash NOT GLOB '*[^0-9a-f]*')` |
| `phone_e164` | `TEXT` | Required | `+1[2-9][0-9]{9}` | Phone | Non-unique | `CHECK (phone_e164 GLOB '+1[2-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `email_norm` | `TEXT` | Required | Lowercase normalized email | Email | Non-unique | `NOT NULL` |
| `address_norm` | `TEXT` | Required | Normalized uppercase address | Address | Non-unique | `NOT NULL` |
| `bank_routing_hash` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | `CHECK (length(bank_routing_hash) = 64 AND bank_routing_hash NOT GLOB '*[^0-9a-f]*')` |
| `bank_account_hash` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | `CHECK (length(bank_account_hash) = 64 AND bank_account_hash NOT GLOB '*[^0-9a-f]*')` |
| `created_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `CHECK (created_at_utc GLOB '202[0-6]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z')` |

---

### 3.2 Policy (`policies`) — 2,200 Rows
Represents insurance coverage agreements linked to claimants.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `policy_id` | `TEXT` | Required | `POL-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (policy_id GLOB 'POL-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `claimant_id` | `TEXT` | Required | `CLMT-[0-9]{6}` | FK | Non-unique | References `claimants(claimant_id)` |
| `policy_number` | `TEXT` | Required | Policy identifier string | String | Unique | `UNIQUE NOT NULL` |
| `line_of_business` | `TEXT` | Required | `AUTO`, `PROPERTY`, `WORKERS_COMP`, `COMMERCIAL_GENERAL`, `MEDICAL` | Enum | Non-unique | `CHECK (line_of_business IN ('AUTO','PROPERTY','WORKERS_COMP','COMMERCIAL_GENERAL','MEDICAL'))` |
| `policy_status` | `TEXT` | Required | `ACTIVE`, `LAPSED`, `CANCELLED`, `EXPIRED` | Enum | Non-unique | `CHECK (policy_status IN ('ACTIVE','LAPSED','CANCELLED','EXPIRED'))` |
| `effective_start_utc`| `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `effective_end_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `CHECK (effective_end_utc > effective_start_utc)` |
| `bound_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `coverage_limit_cents`| `INTEGER`| Required | `> 0` | Cents ($) | Non-unique | `CHECK (coverage_limit_cents > 0)` |
| `deductible_cents` | `INTEGER`| Required | `>= 0` and `< coverage_limit_cents` | Cents ($) | Non-unique | `CHECK (deductible_cents >= 0 AND deductible_cents < coverage_limit_cents)` |
| `annual_premium_cents`| `INTEGER`| Required| `> 0` | Cents ($) | Non-unique | `CHECK (annual_premium_cents > 0)` |

---

### 3.3 Incident (`incidents`) — 3,800 Rows
Represents loss events and accident reports.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `incident_id` | `TEXT` | Required | `INC-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (incident_id GLOB 'INC-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `incident_timestamp_utc`| `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `reported_timestamp_utc`| `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `CHECK (reported_timestamp_utc >= incident_timestamp_utc)` |
| `incident_type` | `TEXT` | Required | `AUTO_COLLISION`, `WATER_DAMAGE`, `FIRE_LOSS`, `SLIP_AND_FALL`, `WORKPLACE_INJURY`, `THEFT_BURGLARY` | Enum | Non-unique | `CHECK (incident_type IN (...))` |
| `jurisdiction_state` | `TEXT` | Required | 2-letter uppercase postal code (`[A-Z]{2}`) | Code | Non-unique | `CHECK (length(jurisdiction_state) = 2 AND jurisdiction_state GLOB '[A-Z][A-Z]')` |
| `location_address_norm`| `TEXT` | Required | Normalized address string | Address | Non-unique | `NOT NULL` |
| `location_geohash` | `TEXT` | Required | 6 to 12 alphanumeric characters | Geohash | Non-unique | `CHECK (length(location_geohash) BETWEEN 6 AND 12)` |
| `police_report_number` | `TEXT` | Optional | Precinct report ID | String | Non-unique | Nullable |
| `weather_condition` | `TEXT` | Required | `CLEAR`, `RAIN`, `SNOW_ICE`, `FOG`, `STORM` | Enum | Non-unique | `CHECK (weather_condition IN ('CLEAR','RAIN','SNOW_ICE','FOG','STORM'))` |
| `description` | `TEXT` | Required | Loss narrative description | Text | Non-unique | `NOT NULL` |

---

### 3.4 Claim (`claims`) — 5,000 Rows
The central operational insurance claim ledger and risk assessment entity.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `claim_id` | `TEXT` | Required | `CLM-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (claim_id GLOB 'CLM-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `policy_id` | `TEXT` | Required | `POL-2026-[0-9]{6}` | FK | Non-unique | References `policies(policy_id)` |
| `claimant_id` | `TEXT` | Required | `CLMT-[0-9]{6}` | FK | Non-unique | References `claimants(claimant_id)` |
| `incident_id` | `TEXT` | Required | `INC-2026-[0-9]{6}` | FK | Non-unique | References `incidents(incident_id)` |
| `claim_status` | `TEXT` | Required | `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `PARTIALLY_PAID`, `PAID`, `SIU_HOLD`, `DENIED`, `CLOSED_NO_PAY` | Enum | Non-unique | Enforced by FSM triggers and checks |
| `submitted_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `claimed_amount_cents` | `INTEGER` | Required | `> 0` | Cents ($) | Non-unique | `CHECK (claimed_amount_cents > 0)` |
| `approved_amount_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (approved_amount_cents >= 0 AND approved_amount_cents <= claimed_amount_cents)` |
| `historical_approved_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (historical_approved_cents >= approved_amount_cents)` |
| `reserved_authorized_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (reserved_authorized_cents >= 0)` |
| `gross_disbursed_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (gross_disbursed_cents >= 0)` |
| `clawed_back_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (clawed_back_cents >= 0 AND clawed_back_cents <= gross_disbursed_cents)` |
| `net_paid_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (net_paid_cents = gross_disbursed_cents - clawed_back_cents)` |
| `payout_cap_cents` | `INTEGER` | Required | `>= 0` | Cents ($) | Non-unique | `CHECK (approved_amount_cents <= payout_cap_cents)` |
| `adjustor_id` | `TEXT` | Required | Adjustor staff ID | ID | Non-unique | `NOT NULL` |
| `siu_referred` | `INTEGER` | Required | `0` or `1` | Flag | Non-unique | `CHECK (siu_referred >= 0)` |
| `latest_ief_score` | `REAL` | Required | `0.0` to `100.0` | Score | Non-unique | `CHECK (latest_ief_score >= 0.0 AND latest_ief_score <= 100.0)` |
| `latest_risk_tier` | `TEXT` | Required | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | Enum | Non-unique | `CHECK (latest_risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL'))` |
| `scoring_evidence_sha256` | `TEXT` | Optional | 64-char lowercase hex string | SHA-256 | Non-unique | Canonical feature input digest (`ST-SCORE-V1`) |

---

### 3.5 Provider (`providers`) — 500 Rows
Represents synthetic third-party healthcare clinics, repair facilities, and service vendors.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `provider_id` | `TEXT` | Required | `PRV-[0-9]{6}` | ID | PK (Unique) | `CHECK (provider_id GLOB 'PRV-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `provider_name` | `TEXT` | Required | Business name string | String | Non-unique | `NOT NULL` |
| `provider_type` | `TEXT` | Required | `AUTO_BODY`, `MEDICAL_CLINIC`, `CHIROPRACTIC`, `RESTORATION_CONTRACTOR`, `LEGAL_REPRESENTATIVE`, `TOWING_STORAGE`, `DIAGNOSTIC_IMAGING` | Enum | Non-unique | `CHECK (provider_type IN (...))` |
| `npi_or_license_id`| `TEXT` | Required | License string | ID | Unique | `UNIQUE NOT NULL` |
| `tax_id_hash` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | `CHECK (length(tax_id_hash) = 64 AND tax_id_hash NOT GLOB '*[^0-9a-f]*')` |
| `phone_e164` | `TEXT` | Required | `+1[2-9][0-9]{9}` | Phone | Non-unique | `CHECK (phone_e164 GLOB '+1[2-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `address_norm` | `TEXT` | Required | Normalized uppercase address | Address | Non-unique | `NOT NULL` |
| `bank_routing_hash`| `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | `CHECK (length(bank_routing_hash) = 64 AND bank_routing_hash NOT GLOB '*[^0-9a-f]*')` |
| `bank_account_hash`| `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | `CHECK (length(bank_account_hash) = 64 AND bank_account_hash NOT GLOB '*[^0-9a-f]*')` |
| `network_tier` | `TEXT` | Required | `IN_NETWORK`, `OUT_OF_NETWORK`, `WATCHLIST`, `SUSPENDED` | Enum | Non-unique | `CHECK (network_tier IN ('IN_NETWORK','OUT_OF_NETWORK','WATCHLIST','SUSPENDED'))` |
| `created_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |

---

### 3.6 Invoice (`invoices`) — 7,500 Rows
Represents billed service invoices submitted by providers for claims.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `invoice_id` | `TEXT` | Required | `INV-PRV-` \|\| provider_id \|\| `-[0-9]{6}` | ID | PK (Unique) | Exact length 25 characters; matches provider prefix |
| `claim_id` | `TEXT` | Required | `CLM-2026-[0-9]{6}` | FK | Non-unique | References `claims(claim_id)` |
| `provider_id` | `TEXT` | Required | `PRV-[0-9]{6}` | FK | Non-unique | References `providers(provider_id)` |
| `provider_invoice_number` | `TEXT` | Required | Internal invoice reference | String | Non-unique | `NOT NULL` |
| `invoice_status` | `TEXT` | Required | `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `PARTIALLY_PAID`, `PAID`, `REJECTED_DUPLICATE`, `REJECTED_ELIGIBILITY`, `REVOKED_POST_APPROVAL` | Enum | Non-unique | `CHECK (invoice_status IN (...))` |
| `service_start_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `service_end_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `CHECK (service_end_utc >= service_start_utc)` |
| `submitted_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `CHECK (submitted_at_utc >= service_start_utc)` |
| `cpt_or_line_code` | `TEXT` | Required | CPT / collision procedure code | Code | Non-unique | `NOT NULL` |
| `line_item_fingerprint` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | `CHECK (length(line_item_fingerprint) = 64 AND line_item_fingerprint NOT GLOB '*[^0-9a-f]*')` |
| `billed_cents` | `INTEGER` | Required | `> 0` | Cents ($) | Non-unique | `CHECK (billed_cents > 0)` |
| `approved_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (approved_cents >= 0 AND approved_cents <= billed_cents)` |
| `historical_approved_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (historical_approved_cents >= approved_cents AND historical_approved_cents <= billed_cents)` |
| `reserved_authorized_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (reserved_authorized_cents >= 0)` |
| `gross_disbursed_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (gross_disbursed_cents >= 0)` |
| `clawed_back_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (clawed_back_cents >= 0 AND clawed_back_cents <= gross_disbursed_cents)` |
| `net_paid_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (net_paid_cents = gross_disbursed_cents - clawed_back_cents)` |
| `duplicate_of_invoice_id` | `TEXT` | Optional | `INV-PRV-...` | FK | Non-unique | References `invoices(invoice_id)`. Required if status is `REJECTED_DUPLICATE`. |

---

### 3.7 Payment (`payments`) — 4,200 Rows
Represents financial payment events (authorized, disbursed, reversed, or blocked).

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `payment_id` | `TEXT` | Required | `PAY-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (payment_id GLOB 'PAY-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `claim_id` | `TEXT` | Required | `CLM-2026-[0-9]{6}` | FK | Non-unique | References `claims(claim_id)` |
| `invoice_id` | `TEXT` | Required | `INV-PRV-...` | FK | Non-unique | References `invoices(invoice_id)` |
| `recipient_type` | `TEXT` | Required | `CLAIMANT`, `PROVIDER` | Enum | Non-unique | Exactly one recipient FK must be populated |
| `recipient_claimant_id` | `TEXT` | Optional | `CLMT-[0-9]{6}` | FK | Non-unique | References `claimants(claimant_id)` |
| `recipient_provider_id` | `TEXT` | Optional | `PRV-[0-9]{6}` | FK | Non-unique | References `providers(provider_id)` |
| `payment_status` | `TEXT` | Required | `AUTHORIZED`, `DISBURSED`, `BLOCKED_OVERPAYMENT`, `BLOCKED_UNAPPROVED`, `BLOCKED_INVALID_RECIPIENT`, `REVERSED_CLAWBACK`, `CANCELLED` | Enum | Non-unique | Strict state-specific balance invariants |
| `amount_cents` | `INTEGER` | Required | `> 0` | Cents ($) | Non-unique | `CHECK (amount_cents > 0)` |
| `disbursed_amount_cents`| `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | Equals `amount_cents` when `DISBURSED` or `REVERSED_CLAWBACK` |
| `clawed_back_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `> 0` only when `REVERSED_CLAWBACK` |
| `net_paid_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `= disbursed_amount_cents - clawed_back_cents` |
| `idempotency_key` | `TEXT` | Required | UUID / Unique Hash | Key | Unique | `UNIQUE NOT NULL` prevents replay attacks |
| `created_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `disbursed_at_utc` | `TEXT` | Optional | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | Populated upon physical disbursement |
| `reversed_at_utc` | `TEXT` | Optional | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | Populated upon clawback or cancellation |
| `authorized_by` | `TEXT` | Required | Authorization Officer ID | ID | Non-unique | `NOT NULL` |
| `block_reason_code` | `TEXT` | Optional | E.g. `PAYMENT_EXCEEDS_APPROVED_AMOUNT` | Code | Non-unique | Mandatory for `BLOCKED_*` payments |
| `external_bank_tx_ref` | `TEXT` | Optional | External banking ref code | Ref | Non-unique | Mandatory for `DISBURSED` payments |
| `cancel_reason` | `TEXT` | Optional | `SIU_HOLD_RESERVATION_CLEARED`, `FINANCE_WITHDRAWAL`, `SUBSEQUENT_ADJUSTMENT` | Enum | Non-unique | Mandatory for `CANCELLED` payments |

---

### 3.8 RelationshipEdge (`relationship_edges`) — 8,000 Rows
Represents observable network graph connections between entities.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `edge_id` | `TEXT` | Required | `EDGE-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (edge_id GLOB 'EDGE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `edge_type` | `TEXT` | Required | `SHARED_ADDRESS`, `SHARED_PHONE`, `SHARED_BANK_ACCOUNT`, `SHARED_TAX_ID`, `SAME_INCIDENT_PARTICIPANT`, `CLAIMANT_TREATED_BY_PROVIDER`, `PROVIDER_REFERRAL_LINK`, `CROSS_CLAIM_DUPLICATE_INVOICE` | Enum | Non-unique | `CHECK (edge_type IN (...))` |
| `source_entity_type` | `TEXT` | Required | `CLAIMANT`, `PROVIDER` | Enum | Non-unique | `CHECK (source_entity_type IN ('CLAIMANT','PROVIDER'))` |
| `source_claimant_id` | `TEXT` | Optional | `CLMT-[0-9]{6}` | FK | Non-unique | Populated if source is `CLAIMANT` |
| `source_provider_id` | `TEXT` | Optional | `PRV-[0-9]{6}` | FK | Non-unique | Populated if source is `PROVIDER` |
| `target_entity_type` | `TEXT` | Required | `CLAIMANT`, `PROVIDER` | Enum | Non-unique | `CHECK (target_entity_type IN ('CLAIMANT','PROVIDER'))` |
| `target_claimant_id` | `TEXT` | Optional | `CLMT-[0-9]{6}` | FK | Non-unique | Populated if target is `CLAIMANT` |
| `target_provider_id` | `TEXT` | Optional | `PRV-[0-9]{6}` | FK | Non-unique | Populated if target is `PROVIDER` |
| `canonical_src_key` | `TEXT` | Required | `CLAIMANT:CLMT-...` or `PROVIDER:PRV-...` | Key | Non-unique | Lexicographical prefix key |
| `canonical_dst_key` | `TEXT` | Required | `CLAIMANT:CLMT-...` or `PROVIDER:PRV-...` | Key | Non-unique | Validation: `CHECK (canonical_src_key < canonical_dst_key)` |
| `strength_weight` | `REAL` | Required | `> 0.0` and `<= 1.0` | Weight | Non-unique | `CHECK (strength_weight > 0.0 AND strength_weight <= 1.0)` |
| `evidence_count` | `INTEGER` | Required | `>= 1` | Count | Non-unique | `CHECK (evidence_count >= 1)` |
| `first_observed_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `last_observed_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `CHECK (last_observed_utc >= first_observed_utc)` |
| `supporting_claim_id` | `TEXT` | Required | `CLM-2026-[0-9]{6}` | FK | Non-unique | References `claims(claim_id)` |
| `is_active` | `INTEGER` | Required | `0` or `1` | Flag | Non-unique | `CHECK (is_active IN (0, 1))` |
| — | — | — | Composite Unique | — | Unique | `UNIQUE (edge_type, canonical_src_key, canonical_dst_key)` |

---

### 3.9 FraudIndicator (`fraud_indicators`) — 4,120 Rows
Derived, explainable fraud evidence signals tied to claims.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `indicator_id` | `TEXT` | Required | `FIND-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (indicator_id GLOB 'FIND-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `claim_id` | `TEXT` | Required | `CLM-2026-[0-9]{6}` | FK | Non-unique | References `claims(claim_id)` |
| `indicator_code` | `TEXT` | Required | `IND-01` through `IND-15` | Code | Non-unique | `CHECK (indicator_code IN ('IND-01', ... ,'IND-15'))` |
| `pillar` | `TEXT` | Required | `NETWORK`, `FINANCIAL`, `BEHAVIORAL`, `DOCUMENT` | Enum | Non-unique | `CHECK (pillar IN ('NETWORK','FINANCIAL','BEHAVIORAL','DOCUMENT'))` |
| `dedup_scope` | `TEXT` | Required | `CLAIM`, `ENTITY`, `PAIR`, `RING` | Enum | Non-unique | `CHECK (dedup_scope IN ('CLAIM','ENTITY','PAIR','RING'))` |
| `canonical_evidence_token` | `TEXT` | Required | Deterministic evidence token | Token | Non-unique | E.g. `BANK:<hash>`, `DUP_FP:<fingerprint>` |
| `severity` | `TEXT` | Required | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | Enum | Non-unique | `CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL'))` |
| `raw_points` | `REAL` | Required | `> 0.0` and `<= max_points` | Points | Non-unique | `CHECK (raw_points > 0.0 AND raw_points <= max_points)` |
| `max_points` | `REAL` | Required | `> 0.0` and `<= 40.0` | Points | Non-unique | `CHECK (max_points > 0.0 AND max_points <= 40.0)` |
| `normalized_value` | `REAL` | Required | `0.0` to `1.0` | Ratio | Non-unique | `CHECK (normalized_value >= 0.0 AND normalized_value <= 1.0)` |
| `feature_snapshot_json` | `TEXT` | Required | Canonical JSON payload | JSON | Non-unique | `CHECK (is_canonical_json(feature_snapshot_json) = 1)` |
| `computed_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| — | — | — | Composite Unique | — | Unique | `UNIQUE (claim_id, indicator_code, canonical_evidence_token)` |

---

### 3.10 Investigation (`investigations`) — 45 Rows
Special Investigation Unit (SIU) case management and lifecycle records.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `investigation_id` | `TEXT` | Required | `INVG-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (investigation_id GLOB 'INVG-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `primary_claim_id` | `TEXT` | Required | `CLM-2026-[0-9]{6}` | FK | Non-unique | References `claims(claim_id)` |
| `subject_claimant_id` | `TEXT` | Optional | `CLMT-[0-9]{6}` | FK | Non-unique | References `claimants(claimant_id)` |
| `subject_provider_id` | `TEXT` | Optional | `PRV-[0-9]{6}` | FK | Non-unique | References `providers(provider_id)` |
| `investigation_status`| `TEXT` | Required | `OPEN`, `EVIDENCE_COLLECTION`, `SIU_FIELD_REVIEW`, `LEGAL_ESCALATION`, `CLOSED_CONFIRMED_FRAUD`, `CLOSED_CLEARED_BENIGN`, `CLOSED_INSUFFICIENT_EVIDENCE` | Enum | Non-unique | Validated by FSM triggers |
| `priority` | `TEXT` | Required | `P1_CRITICAL`, `P2_HIGH`, `P3_STANDARD` | Enum | Non-unique | `CHECK (priority IN ('P1_CRITICAL','P2_HIGH','P3_STANDARD'))` |
| `assigned_investigator_id`| `TEXT` | Required | Investigator staff ID | ID | Non-unique | `NOT NULL` |
| `opened_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `updated_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `CHECK (updated_at_utc >= opened_at_utc)` |
| `closed_at_utc` | `TEXT` | Optional | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | Populated only when status is `CLOSED_*` |
| `ruling_outcome` | `TEXT` | Optional | `CONFIRMED_FRAUD`, `CLEARED_BENIGN`, `INSUFFICIENT_EVIDENCE` | Enum | Non-unique | Populated only when status is `CLOSED_*` |
| `estimated_exposure_cents` | `INTEGER` | Required | `>= 0` | Cents ($) | Non-unique | `CHECK (estimated_exposure_cents >= 0)` |
| `recovered_clawback_cents` | `INTEGER` | Required | Default `0` | Cents ($) | Non-unique | `CHECK (recovered_clawback_cents >= 0)` |
| `case_summary_notes` | `TEXT` | Required | Case narrative and findings | Text | Non-unique | `NOT NULL` |

---

## 4. Auxiliary & Audit Event Tables

### 4.1 Immutable Event Chain (`immutable_events`) — 19,675 Rows
Append-only, SHA-256 length-prefixed Merkle hash chain (`ST-EVT-V2`). Triggers forbid `UPDATE` and `DELETE`.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `sequence_no` | `INTEGER` | Required | `>= 1` | Seq | PK (Unique) | Monotonically increasing sequence number |
| `event_id` | `TEXT` | Required | `EVT-2026-[0-9]{7}` | ID | Unique | `CHECK (event_id GLOB 'EVT-2026-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `event_type` | `TEXT` | Required | 15 monitored domain lifecycle event types | Enum | Non-unique | Matches `EVENT_BUCKET_TARGETS` |
| `aggregate_type` | `TEXT` | Required | `CLAIM`, `POLICY`, `INVOICE`, `PAYMENT`, `INVESTIGATION`, etc. | Enum | Non-unique | `NOT NULL` |
| `entity_id` | `TEXT` | Required | Primary key of target entity | ID | Non-unique | `NOT NULL` |
| `claim_id` | `TEXT` | Optional | `CLM-2026-[0-9]{6}` | FK | Non-unique | Nullable |
| `actor_id` | `TEXT` | Required | User/Service principal ID | ID | Non-unique | `NOT NULL` |
| `actor_role` | `TEXT` | Required | `SYSTEM`, `ANALYST`, `INVESTIGATOR`, `ADMINISTRATOR` | Enum | Non-unique | `CHECK (actor_role IN ('SYSTEM','ANALYST','INVESTIGATOR','ADMINISTRATOR'))` |
| `timestamp_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `payload_json` | `TEXT` | Required | Canonical JSON string | JSON | Non-unique | `CHECK (is_canonical_json(payload_json) = 1)` |
| `payload_sha256` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | Computed over `payload_json` |
| `prev_event_hash` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | Genesis: `0000000000000000000000000000000000000000000000000000000000000000` |
| `event_hash` | `TEXT` | Required | 64-char lowercase hex string | SHA-256 | Non-unique | Computed as `SHA256(prev_event_hash \|\| payload_sha256 \|\| sequence_no)` |

---

### 4.2 Ingestion Exceptions (`ingestion_exceptions`) — 25 Rows
Records rejected invalid incoming submissions (e.g. YF-NEG-1 missing policy ID). Triggers forbid `UPDATE` and `DELETE`.

| Field Name | Type | Req/Opt | Allowed Values / Format | Units | Uniqueness | Validation Rule & Constraints |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `exception_id` | `TEXT` | Required | `EXC-2026-[0-9]{6}` | ID | PK (Unique) | `CHECK (exception_id GLOB 'EXC-2026-[0-9][0-9][0-9][0-9][0-9][0-9]')` |
| `attempted_claim_id` | `TEXT` | Required | `CLM-2026-[0-9]{6}` | ID | Non-unique | Attempted claim identifier |
| `attempted_policy_id`| `TEXT` | Optional | E.g. `POL-MISSING-000001` | ID | Non-unique | Invalid reference rejected by foreign key |
| `claimant_id` | `TEXT` | Required | `CLMT-[0-9]{6}` | FK | Non-unique | References `claimants(claimant_id)` |
| `incident_id` | `TEXT` | Required | `INC-2026-[0-9]{6}` | FK | Non-unique | References `incidents(incident_id)` |
| `attempted_claimed_amount_cents` | `INTEGER` | Required | `> 0` | Cents ($) | Non-unique | `CHECK (attempted_claimed_amount_cents > 0)` |
| `exception_code` | `TEXT` | Required | `FOREIGN_KEY_VIOLATION_POLICY_ID`, etc. | Code | Non-unique | `NOT NULL` |
| `raw_payload_json` | `TEXT` | Required | Canonical JSON representation of rejected input | JSON | Non-unique | `CHECK (is_canonical_json(raw_payload_json) = 1)` |
| `created_at_utc` | `TEXT` | Required | `YYYY-MM-DDTHH:MM:SSZ` | Timestamp | Non-unique | `NOT NULL` |
| `recorded_event_id` | `TEXT` | Required | `EVT-2026-[0-9]{7}` | FK | Non-unique | References `immutable_events(event_id)` |

"""
Entity generation logic for claimants, policies, incidents, claims, and providers.
Embeds operational source facts for official challenge scenarios:
- YF-NEG-1: Ingestion exceptions with nonexistent policies
- YF-NEG-2: Staged collisions (shared phone, delayed reporting, multi-party accidents)
- YF-NEG-3: Cross-claimant duplicate invoice pairs sharing payout account
- YF-NEG-4: 5 partially observable collusion rings (8 claims/ring) with intra-ring facts
- YF-NEG-5: 80 multi-unit apartment claimants (100 Ocean Ave, Apts 101-180)
- BL-1..BL-5: Legitimate benchmark scenarios (single claimant, business, household, fleet)
"""

import hashlib
import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
from backend.app.generator.config import (
    COUNT_CLAIMANTS, COUNT_POLICIES, COUNT_INCIDENTS, COUNT_CLAIMS, COUNT_PROVIDERS,
    YF_NEG_2_CLAIMS, YF_NEG_3_CLAIMS, YF_NEG_4_CLAIMS, YF_NEG_5_CLAIMS
)
from backend.app.generator.id_factory import (
    claimant_id, policy_id, incident_id, provider_id, ClaimIdFactory
)


def sha256_hex(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Sharon"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"
]

STREETS = [
    "Main St", "Oak Ave", "Maple St", "Cedar Ln", "Elm St", "Washington Blvd",
    "Lakeview Dr", "Sunset Blvd", "Broadway", "Pine St", "Highland Ave", "Spring St"
]

CITIES = [
    ("Los Angeles", "CA", "90001", "9q5c"),
    ("San Francisco", "CA", "94102", "9q8y"),
    ("Houston", "TX", "77001", "9vk1"),
    ("Dallas", "TX", "75201", "9vg4"),
    ("Miami", "FL", "33101", "dhwf"),
    ("Chicago", "IL", "60601", "dp3w"),
    ("New York", "NY", "10001", "dr5r"),
    ("Phoenix", "AZ", "85001", "9tbq")
]


def generate_entities(seed: int = 42) -> Tuple[
    List[Dict[str, Any]],  # claimants
    List[Dict[str, Any]],  # policies
    List[Dict[str, Any]],  # incidents
    List[Dict[str, Any]],  # claims
    List[Dict[str, Any]],  # providers
    ClaimIdFactory,
    Dict[str, Any]         # metadata for scenarios
]:
    rng = random.Random(seed)
    claim_factory = ClaimIdFactory(seed=seed, total_claims=COUNT_CLAIMS)

    # --------------------------------------------------------------------------
    # 1. GENERATE CLAIMANTS (2,000)
    # --------------------------------------------------------------------------
    claimants = []
    
    # Pre-allocate scenario identities
    # YF-NEG-5: Indices 1000..1079 (80 claimants) share 100 Ocean Ave, Apts 101-180
    yf5_claimant_indices = set(range(1000, 1080))
    
    # YF-NEG-4: 5 rings x 8 claimants = 40 claimants (indices 710..749)
    yf4_claimant_indices = set(range(710, 750))
    
    # YF-NEG-3: 25 claims across distinct claimants sharing payout accounts (indices 600..624)
    yf3_claimant_indices = set(range(600, 625))

    for idx in range(COUNT_CLAIMANTS):
        cid = claimant_id(idx + 1)
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        full_name = f"{fn} {ln}"
        
        # DOB: 1950-01-01 to 2004-12-31
        birth_year = rng.randint(1955, 2002)
        birth_month = rng.randint(1, 12)
        birth_day = rng.randint(1, 28)
        dob_iso = f"{birth_year:04d}-{birth_month:02d}-{birth_day:02d}"
        
        # Tax ID Hash: 64 lowercase hex (strictly unique per claimant)
        tax_id_hash = sha256_hex(f"SSN-{idx:06d}-{seed}")
        
        # Address & Phone
        if idx in yf5_claimant_indices:
            # YF-NEG-5: Common apartment building at 100 Ocean Ave
            address_norm = "100 Ocean Ave, Los Angeles, CA 90001"
            city, state, zip_code, _ = CITIES[0]
            phone_e164 = f"+1213555{idx:04d}"
        elif idx in yf4_claimant_indices:
            # YF-NEG-4: Collusion rings (5 rings of 8 claimants)
            ring_num = 16 + ((idx - 710) // 8)
            member_num = (idx - 710) % 8 + 1
            city, state, zip_code, _ = CITIES[ring_num % len(CITIES)]
            address_norm = f"{rng.randint(100, 9999)} {rng.choice(STREETS)}, {city}, {state} {zip_code}"
            # Intra-ring shared phone
            phone_e164 = f"+1555099{ring_num:04d}"
        elif idx in yf3_claimant_indices:
            # YF-NEG-3: Shared payout account pair
            city, state, zip_code, _ = CITIES[idx % len(CITIES)]
            address_norm = f"{rng.randint(100, 9999)} {rng.choice(STREETS)}, {city}, {state} {zip_code}"
            phone_e164 = f"+1213555{idx:04d}"
        elif 100 <= idx < 500:
            # Address clusters for IND-05 (groups of 3-4 claimants living at same address)
            cluster_id = (idx - 100) // 3
            city, state, zip_code, _ = CITIES[cluster_id % len(CITIES)]
            address_norm = f"{1000 + cluster_id * 10} Oak St, {city}, {state} {zip_code}"
            phone_e164 = f"+1{rng.randint(200, 999)}{rng.randint(100, 999)}{rng.randint(1000, 9999)}"
        elif 1500 <= idx < 1850:
            # Shared phones for IND-02 (groups of 2-3 claimants sharing phone)
            phone_group = (idx - 1500) // 2
            city, state, zip_code, _ = CITIES[idx % len(CITIES)]
            address_norm = f"{rng.randint(100, 9999)} {rng.choice(STREETS)}, {city}, {state} {zip_code}"
            phone_e164 = f"+1555088{phone_group:04d}"
        else:
            city, state, zip_code, _ = CITIES[idx % len(CITIES)]
            address_norm = f"{rng.randint(100, 9999)} {rng.choice(STREETS)}, {city}, {state} {zip_code}"
            phone_e164 = f"+1{rng.randint(200, 999)}{rng.randint(100, 999)}{rng.randint(1000, 9999)}"

        email_norm = f"{fn.lower()}.{ln.lower()}{idx}@example.com"
        
        # Bank accounts
        if idx in yf3_claimant_indices:
            # Pairs share bank account
            pair_group = (idx - 600) // 2
            bank_account_hash = sha256_hex(f"BANK-SHARED-YF3-{pair_group:04d}")
        elif 1200 <= idx < 1480:
            # Shared bank account pairs for IND-01
            pair_group = (idx - 1200) // 2
            bank_account_hash = sha256_hex(f"BANK-SHARED-IND1-{pair_group:04d}")
        else:
            bank_account_hash = sha256_hex(f"BANK-ACCT-{idx:06d}-{seed}")
            
        bank_routing_hash = sha256_hex(f"ROUTING-{idx % 50:04d}")
        created_at_utc = "2025-06-01T00:00:00Z"

        claimants.append({
            "claimant_id": cid,
            "full_name": full_name,
            "dob_iso": dob_iso,
            "tax_id_hash": tax_id_hash,
            "phone_e164": phone_e164,
            "email_norm": email_norm,
            "address_norm": address_norm,
            "bank_routing_hash": bank_routing_hash,
            "bank_account_hash": bank_account_hash,
            "created_at_utc": created_at_utc
        })

    # --------------------------------------------------------------------------
    # 2. GENERATE POLICIES (2,200)
    # --------------------------------------------------------------------------
    policies = []
    lob_choices = ['AUTO', 'PROPERTY', 'WORKERS_COMP', 'COMMERCIAL_GENERAL', 'MEDICAL']
    
    for idx in range(COUNT_POLICIES):
        pid = policy_id(idx + 1)
        # First 2,000 policies map 1:1 to claimants; remaining 200 represent multi-policy claimants
        cid = claimant_id((idx % COUNT_CLAIMANTS) + 1)
        pol_num = f"POL-NUM-{idx+1:06d}"
        lob = lob_choices[idx % len(lob_choices)]
        
        # Inception dates: policies bound late 2025
        bound_date = datetime(2025, 7, 1) + timedelta(days=idx % 170)
        # Early inception claims (IND-09) bound late Dec 2025 (target ~360)
        if idx % 6 == 0:
            bound_date = datetime(2025, 12, 23) + timedelta(days=idx % 7)
        bound_at_utc = bound_date.strftime("%Y-%m-%dT00:00:00Z")
        start_date = bound_date
        effective_start_utc = start_date.strftime("%Y-%m-%dT00:00:00Z")
        end_date = start_date + timedelta(days=365)
        effective_end_utc = end_date.strftime("%Y-%m-%dT00:00:00Z")
        
        cov_limit = rng.choice([2500000, 5000000, 10000000, 25000000]) # $25k to $250k
        deductible = rng.choice([25000, 50000, 100000])                  # $250 to $1000
        premium = rng.choice([120000, 180000, 240000, 360000])           # $1.2k to $3.6k

        policies.append({
            "policy_id": pid,
            "claimant_id": cid,
            "policy_number": pol_num,
            "line_of_business": lob,
            "policy_status": "ACTIVE",
            "effective_start_utc": effective_start_utc,
            "effective_end_utc": effective_end_utc,
            "bound_at_utc": bound_at_utc,
            "coverage_limit_cents": cov_limit,
            "deductible_cents": deductible,
            "annual_premium_cents": premium
        })

    # --------------------------------------------------------------------------
    # 3. GENERATE PROVIDERS (500)
    # --------------------------------------------------------------------------
    providers = []
    prv_types = [
        'AUTO_BODY', 'MEDICAL_CLINIC', 'CHIROPRACTIC',
        'RESTORATION_CONTRACTOR', 'LEGAL_REPRESENTATIVE',
        'TOWING_STORAGE', 'DIAGNOSTIC_IMAGING'
    ]
    tiers = ['IN_NETWORK', 'IN_NETWORK', 'OUT_OF_NETWORK', 'WATCHLIST', 'SUSPENDED']
    
    for idx in range(COUNT_PROVIDERS):
        prvid = provider_id(idx + 1)
        ptype = prv_types[idx % len(prv_types)]
        # Ring providers 16..20 (indices 15..19) are suspended corrupt facilities (IND-15)
        if 15 <= idx < 20:
            tier = 'SUSPENDED'
        else:
            tier = tiers[idx % len(tiers)]
        pname = f"Apex {ptype.replace('_', ' ').title()} Group {idx+1}"
        npi = f"NPI-{idx+1:08d}"
        thash = sha256_hex(f"PRV-TAX-{idx:05d}")
        phone = f"+1213555{9000+idx:04d}" if idx < 1000 else f"+1800555{idx:04d}"
        city, state, zip_code, _ = CITIES[idx % len(CITIES)]
        addr = f"{rng.randint(100, 9999)} Commercial Blvd, {city}, {state} {zip_code}"
        b_route = sha256_hex(f"PRV-ROUTING-{idx % 30:04d}")
        b_acct = sha256_hex(f"PRV-ACCT-{idx:05d}")
        
        # Scenarios: PRV-000016..PRV-000020 are ring collusion providers (SUSPENDED / OUT_OF_NETWORK)
        if 16 <= (idx + 1) <= 20:
            tier = 'SUSPENDED'
        elif idx in (50, 100, 150, 200):
            tier = 'WATCHLIST'
        else:
            tier = 'IN_NETWORK' if idx % 2 == 0 else 'OUT_OF_NETWORK'

        providers.append({
            "provider_id": prvid,
            "provider_name": pname,
            "provider_type": ptype,
            "npi_or_license_id": npi,
            "tax_id_hash": thash,
            "phone_e164": phone,
            "address_norm": addr,
            "bank_routing_hash": b_route,
            "bank_account_hash": b_acct,
            "network_tier": tier,
            "created_at_utc": "2025-01-01T00:00:00Z"
        })

    # --------------------------------------------------------------------------
    # 4. GENERATE INCIDENTS (3,800)
    # --------------------------------------------------------------------------
    incidents = []
    inc_types = ['AUTO_COLLISION', 'WATER_DAMAGE', 'FIRE_LOSS', 'SLIP_AND_FALL', 'WORKPLACE_INJURY', 'THEFT_BURGLARY']
    weathers = ['CLEAR', 'RAIN', 'SNOW_ICE', 'FOG', 'STORM']
    
    for idx in range(COUNT_INCIDENTS):
        iid = incident_id(idx + 1)
        inc_date = datetime(2026, 1, 1) + timedelta(days=idx % 60, hours=rng.randint(0, 23))
        inc_ts = inc_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Reporting delay: 0 to 120 hours
        # Delayed incident reporting for IND-10 (> 72h, target ~310)
        delay_hours = 96 if (idx % 8 == 0) else rng.randint(1, 48)
        rep_date = inc_date + timedelta(hours=delay_hours)
        rep_ts = rep_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        itype = inc_types[idx % len(inc_types)]
        city, state, zip_code, geohash = CITIES[idx % len(CITIES)]
        loc_addr = f"{rng.randint(100, 9999)} {rng.choice(STREETS)}, {city}, {state} {zip_code}"
        loc_geo = f"{geohash}{idx:04d}"[:8]
        
        # Police report present on 70% of incidents
        prn = f"RPT-2026-{idx+1:06d}" if (idx % 10 < 7) else None
        weather = weathers[idx % len(weathers)]
        desc = f"Investigation report for {itype.replace('_', ' ').lower()} incident in {city}."

        incidents.append({
            "incident_id": iid,
            "incident_timestamp_utc": inc_ts,
            "reported_timestamp_utc": rep_ts,
            "incident_type": itype,
            "jurisdiction_state": state,
            "location_address_norm": loc_addr,
            "location_geohash": loc_geo,
            "police_report_number": prn,
            "weather_condition": weather,
            "description": desc
        })

    # --------------------------------------------------------------------------
    # 5. GENERATE CLAIMS (5,000)
    # --------------------------------------------------------------------------
    claims = []
    yf4_core_claimants = [710 + r * 8 + c for r in range(5) for c in range(7)]
    yf4_repeat_indices = list(range(2710, 2745)) + list(range(3710, 3745)) + list(range(4710, 4745))
    
    for log_idx in range(COUNT_CLAIMS):
        phys_claim_id = claim_factory.get_physical_id(log_idx)
        
        # Determine claimant and policy mapping
        # Scenarios map to specific logical indices
        if 710 <= log_idx < 750:
            # YF-NEG-4 primary ring claims (40 claims)
            clmt_idx = log_idx
        elif 2710 <= log_idx < 2745:
            # YF-NEG-4 core repeat claim 1 (burst velocity & provider referral concentration)
            clmt_idx = yf4_core_claimants[log_idx - 2710]
        elif 3710 <= log_idx < 3745:
            # YF-NEG-4 core repeat claim 2
            clmt_idx = yf4_core_claimants[log_idx - 3710]
        elif 4710 <= log_idx < 4745:
            # YF-NEG-4 core repeat claim 3
            clmt_idx = yf4_core_claimants[log_idx - 4710]
        elif 1000 <= log_idx < 1080:
            # YF-NEG-5
            clmt_idx = log_idx
        elif 600 <= log_idx < 625:
            # YF-NEG-3
            clmt_idx = log_idx
        else:
            clmt_idx = log_idx % COUNT_CLAIMANTS
            if 1000 <= clmt_idx < 1080:
                # Displace out of YF-NEG-5 so YF-NEG-5 claimants have strictly 1 claim each (80 claims total)
                clmt_idx = 1080 + (clmt_idx - 1000)
            elif 710 <= clmt_idx < 750:
                clmt_idx = 750 + (clmt_idx - 710)
            elif 600 <= clmt_idx < 625:
                clmt_idx = 625 + (clmt_idx - 600)
            
        cid = claimant_id(clmt_idx + 1)
        # Choose policy that strictly belongs to this claimant
        pol = policies[clmt_idx]
        pid = pol["policy_id"]
        iid = incident_id((log_idx % COUNT_INCIDENTS) + 1)
        
        # Chronology: Claims submitted between Jan 5, 2026 and Jan 9, 2026
        # Strictly monotonic with log_idx to eliminate any possibility of event sequence inversion
        sub_date = datetime(2026, 1, 5, 0, 0, 0) + timedelta(seconds=int(log_idx * 86.4))
        sub_ts = sub_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Ensure incident precedes claim submission causally and follows policy effective_start
        # Delayed incident reporting for IND-10 (> 72h, target 300)
        delay_hours = 96 if (log_idx % 10 == 0) else (12 + (log_idx % 36))
        inc_date = sub_date - timedelta(hours=delay_hours + 1)
        rep_date = inc_date + timedelta(hours=delay_hours)
        inc_rec = incidents[log_idx % COUNT_INCIDENTS]
        if log_idx < COUNT_INCIDENTS:
            inc_rec["incident_timestamp_utc"] = inc_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            inc_rec["reported_timestamp_utc"] = rep_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        if 600 <= log_idx < 625:
            # YF-NEG-3 duplicate invoice claims claim $4,200
            claimed_cents = 420000
        elif 710 <= log_idx < 750:
            # YF-NEG-4 collusion ring claims
            if (log_idx - 710) % 8 < 7:
                claimed_cents = 500000
                inc_rec["police_report_number"] = None
                pol["bound_at_utc"] = (sub_date - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
                pol["effective_start_utc"] = (sub_date - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")
                pol["effective_end_utc"] = (sub_date + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
                inc_rec["incident_timestamp_utc"] = (sub_date - timedelta(hours=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
                inc_rec["reported_timestamp_utc"] = (sub_date - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                claimed_cents = 250000
                inc_rec["police_report_number"] = None
                inc_rec["incident_timestamp_utc"] = (sub_date - timedelta(hours=98)).strftime("%Y-%m-%dT%H:%M:%SZ")
                inc_rec["reported_timestamp_utc"] = (sub_date - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            claimed_cents = rng.choice([150000, 280000, 420000, 750000, 1200000, 3500000])
        # ARCH-ST-010.3 trigger requirement:
        # payout_cap_cents == MIN(claimed_amount_cents, MAX(0, coverage_limit_cents - deductible_cents))
        net_coverage = max(0, pol["coverage_limit_cents"] - pol["deductible_cents"])
        payout_cap = min(claimed_cents, net_coverage)
        adj_id = f"ADJ-{(log_idx % 50) + 1:03d}"
        
        # All claims initially inserted in SUBMITTED state with 0 scores (trigger requirement)
        claims.append({
            "claim_id": phys_claim_id,
            "logical_index": log_idx,
            "policy_id": pid,
            "claimant_id": cid,
            "incident_id": iid,
            "claim_status": "SUBMITTED",
            "submitted_at_utc": sub_ts,
            "claimed_amount_cents": claimed_cents,
            "approved_amount_cents": 0,
            "historical_approved_cents": 0,
            "reserved_authorized_cents": 0,
            "gross_disbursed_cents": 0,
            "clawed_back_cents": 0,
            "net_paid_cents": 0,
            "payout_cap_cents": payout_cap,
            "adjustor_id": adj_id,
            "siu_referred": 0,
            "latest_ief_score": 0.0,
            "latest_risk_tier": "LOW",
            "scoring_evidence_sha256": None
        })

    scenario_metadata = {
        "yf4_indices": list(range(710, 750)),
        "yf4_core_claimants": yf4_core_claimants,
        "yf4_repeat_indices": yf4_repeat_indices,
        "yf5_indices": list(range(1000, 1080)),
        "yf3_indices": list(range(600, 625)),
    }

    return claimants, policies, incidents, claims, providers, claim_factory, scenario_metadata

"""
Deterministic ID allocation factory for all entities in SENTINEL//TRACE.
Enforces GLOB constraints and schema formats from ARCH-ST-010.3.
"""

import random
from typing import Dict, List


def claimant_id(seq: int) -> str:
    """Format: CLMT-[0-9]{6}"""
    return f"CLMT-{seq:06d}"


def policy_id(seq: int) -> str:
    """Format: POL-2026-[0-9]{6}"""
    return f"POL-2026-{seq:06d}"


def incident_id(seq: int) -> str:
    """Format: INC-2026-[0-9]{6}"""
    return f"INC-2026-{seq:06d}"


def provider_id(seq: int) -> str:
    """Format: PRV-[0-9]{6}"""
    return f"PRV-{seq:06d}"


def invoice_id(provider_id_str: str, seq: int) -> str:
    """Format: INV-PRV-PRV-[0-9]{6}-[0-9]{6} (Length: 25)"""
    return f"INV-PRV-{provider_id_str}-{seq:06d}"


def payment_id(seq: int) -> str:
    """Format: PAY-2026-[0-9]{6}"""
    return f"PAY-2026-{seq:06d}"


def edge_id(seq: int) -> str:
    """Format: EDGE-2026-[0-9]{6}"""
    return f"EDGE-2026-{seq:06d}"


def indicator_id(seq: int) -> str:
    """Format: FIND-2026-[0-9]{6}"""
    return f"FIND-2026-{seq:06d}"


def investigation_id(seq: int) -> str:
    """Format: INVG-2026-[0-9]{6}"""
    return f"INVG-2026-{seq:06d}"


def event_id(seq: int) -> str:
    """Format: EVT-2026-[0-9]{7} (7 digits)"""
    return f"EVT-2026-{seq:07d}"


def exception_id(seq: int) -> str:
    """Format: IEX-2026-[0-9]{6}"""
    return f"IEX-2026-{seq:06d}"


class ClaimIdFactory:
    """
    Deterministic random permutation ID factory for claims.
    Maps logical claim indices to permuted physical IDs in [CLM-2026-000001, CLM-2026-005000].
    Prevents sequential ground-truth ring leakage.
    """

    def __init__(self, seed: int = 42, total_claims: int = 5000):
        self.seed = seed
        self.total_claims = total_claims
        rng = random.Random(seed)
        self.permuted_indices = rng.sample(range(1, total_claims + 1), total_claims)
        self.logical_to_physical: Dict[int, str] = {
            i: f"CLM-2026-{self.permuted_indices[i]:06d}"
            for i in range(total_claims)
        }
        self.physical_to_logical: Dict[str, int] = {
            phys: log for log, phys in self.logical_to_physical.items()
        }

    def get_physical_id(self, logical_index: int) -> str:
        if logical_index not in self.logical_to_physical:
            raise KeyError(f"Logical claim index {logical_index} out of range [0, {self.total_claims-1}]")
        return self.logical_to_physical[logical_index]

    def get_logical_index(self, physical_id: str) -> int:
        if physical_id not in self.physical_to_logical:
            raise KeyError(f"Physical claim ID {physical_id} not found in factory map")
        return self.physical_to_logical[physical_id]

    def all_physical_ids(self) -> List[str]:
        return list(self.logical_to_physical.values())


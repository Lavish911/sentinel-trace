"""
Event chain builder for immutable_events table in SENTINEL//TRACE.
Strictly complies with ST-EVT-V2 canonical encoding and Merkle chain linkage.
Enforces RFC 8259 canonical JSON without floating point numbers.
"""

import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from backend.app.generator.id_factory import event_id


def sha256_hex(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def utf8_byte_length(s: str) -> int:
    return len(s.encode("utf-8"))


def to_canonical_json(obj: Dict[str, Any]) -> str:
    """Produces sorted, whitespace-free canonical JSON without floating point numbers."""
    def check_floats(o: Any):
        if isinstance(o, float):
            raise ValueError(f"Floating point numbers forbidden in event payloads: {o}")
        elif isinstance(o, dict):
            for v in o.values():
                check_floats(v)
        elif isinstance(o, list):
            for item in o:
                check_floats(item)
    check_floats(obj)
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True)


def encode_event_preimage_v2(
    sequence_no: int,
    eid: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    claim_id: Optional[str],
    actor_id: str,
    occurred_at_utc: str,
    payload_sha256: str,
    prev_event_hash: str
) -> str:
    """Constructs the exact ST-EVT-V2 length-prefixed preimage verified by SQLite triggers."""
    def L(s: str) -> int:
        return utf8_byte_length(s)

    parts = [
        "ST-EVT-V2|",
        f"11:sequence_no=I{sequence_no};",
        f"8:event_id=S{L(eid)}:{eid};",
        f"10:event_type=S{L(event_type)}:{event_type};",
        f"11:entity_type=S{L(entity_type)}:{entity_type};",
        f"9:entity_id=S{L(entity_id)}:{entity_id};",
        "8:claim_id=N;" if claim_id is None else f"8:claim_id=S{L(claim_id)}:{claim_id};",
        f"8:actor_id=S{L(actor_id)}:{actor_id};",
        f"15:occurred_at_utc=S{L(occurred_at_utc)}:{occurred_at_utc};",
        f"14:payload_sha256=S64:{payload_sha256};",
        f"15:prev_event_hash=S64:{prev_event_hash};"
    ]
    return "".join(parts)


class EventChainBuilder:
    """Maintains sequential Merkle hash chain state for immutable_events."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.current_hash = "0" * 64

    def add_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        claim_id: Optional[str],
        actor_id: str,
        occurred_at_utc: str,
        payload_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        seq = len(self.events) + 1
        eid = event_id(seq)
        payload_json = to_canonical_json(payload_dict)
        psha = sha256_hex(payload_json)
        prev_hash = self.current_hash

        preimage = encode_event_preimage_v2(
            sequence_no=seq,
            eid=eid,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            claim_id=claim_id,
            actor_id=actor_id,
            occurred_at_utc=occurred_at_utc,
            payload_sha256=psha,
            prev_event_hash=prev_hash
        )
        eh = sha256_hex(preimage)
        self.current_hash = eh

        ev_record = {
            "sequence_no": seq,
            "event_id": eid,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "claim_id": claim_id,
            "actor_id": actor_id,
            "occurred_at_utc": occurred_at_utc,
            "payload_json": payload_json,
            "payload_sha256": psha,
            "prev_event_hash": prev_hash,
            "event_hash": eh
        }
        self.events.append(ev_record)
        return ev_record


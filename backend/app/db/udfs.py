import hashlib
import json
import sqlite3
from typing import Any


def sha256_hex(val: Any) -> str:
    """Compute 64-character lowercase hexadecimal SHA-256 digest of UTF-8 text."""
    if val is None:
        return ""
    if isinstance(val, bytes):
        val = val.decode("utf-8")
    elif not isinstance(val, str):
        val = str(val)
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def is_canonical_json(val: Any) -> int:
    """Validate canonical JSON according to ARCH-ST-010.3 specification.

    Rules:
    - Root must be a JSON object (dictionary)
    - Keys must be lexicographically sorted by UTF-8 byte order
    - Compact separators (',', ':') with zero whitespace padding
    - No duplicate keys allowed at any nesting level
    - No NaN, Infinity, or -Infinity constants
    - Raw UTF-8 strings (no escaped Unicode sequences)
    - Returns 1 if valid and identical to canonical serialization, 0 otherwise.
    """
    if not isinstance(val, str):
        return 0

    def reject_constants(constant_name: str) -> None:
        raise ValueError(f"Non-standard JSON constant forbidden: {constant_name}")

    def check_duplicate_keys(pairs: list) -> dict:
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate key detected")
        return dict(pairs)

    try:
        parsed = json.loads(
            val,
            parse_constant=reject_constants,
            object_pairs_hook=check_duplicate_keys,
        )
    except Exception:
        return 0

    if not isinstance(parsed, dict):
        return 0

    try:
        canonical_str = json.dumps(
            parsed,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return 1 if canonical_str == val else 0
    except Exception:
        return 0


def register_udfs(connection: sqlite3.Connection) -> None:
    """Register custom deterministic UDFs on an active SQLite connection."""
    connection.create_function("sha256_hex", 1, sha256_hex, deterministic=True)
    connection.create_function(
        "is_canonical_json", 1, is_canonical_json, deterministic=True
    )


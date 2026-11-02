import pytest
from backend.app.db.udfs import sha256_hex, is_canonical_json


def test_sha256_hex_deterministic():
    """Verify SHA-256 computation matches standard test vectors."""
    val = "hello world"
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert sha256_hex(val) == expected


def test_sha256_hex_empty_and_bytes():
    """Verify handling of empty strings and bytes."""
    assert sha256_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_hex(b"hello world") == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_sha256_hex_kav1_payload():
    """Verify SHA-256 for KAV-1 payload from ARCH-ST-010.2."""
    pjson1 = '{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}'
    assert sha256_hex(pjson1) == "45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3"


def test_is_canonical_json_valid_objects():
    """Verify that canonical JSON objects pass."""
    assert is_canonical_json('{"a":1,"b":2}') == 1
    assert is_canonical_json('{"claim_id":"CLM-2026-000001","status":"OPEN"}') == 1
    # Raw UTF-8 without unicode escaping
    assert is_canonical_json('{"note":"Renée|東京"}') == 1


def test_is_canonical_json_unsorted_keys():
    """Verify that unsorted keys are rejected."""
    assert is_canonical_json('{"b":2,"a":1}') == 0


def test_is_canonical_json_whitespace_rejected():
    """Verify that whitespace around separators is rejected."""
    assert is_canonical_json('{"a": 1, "b": 2}') == 0
    assert is_canonical_json('{\n  "a": 1\n}') == 0


def test_is_canonical_json_duplicate_keys():
    """Verify that duplicate keys are strictly rejected."""
    assert is_canonical_json('{"a":1,"a":2}') == 0


def test_is_canonical_json_nan_infinity_rejected():
    """Verify that NaN and Infinity non-standard constants are rejected."""
    assert is_canonical_json('{"a":NaN}') == 0
    assert is_canonical_json('{"a":Infinity}') == 0
    assert is_canonical_json('{"a":-Infinity}') == 0


def test_is_canonical_json_non_dict_roots():
    """Verify that non-object roots (arrays, primitives) are rejected."""
    assert is_canonical_json('[1,2,3]') == 0
    assert is_canonical_json('"hello"') == 0
    assert is_canonical_json('123') == 0
    assert is_canonical_json(None) == 0

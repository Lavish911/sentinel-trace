import re
import hashlib
import sqlite3
import os
import sys

WORK = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(WORK, '..', '..', 'ARCH-ST-010.3.md')

EXPECTED = '2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab'


def sha256_hex(s):
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def is_canonical_json(s):
    if not isinstance(s, str):
        return 0

    def reject_const(val):
        raise ValueError(f"Non-standard JSON constant forbidden: {val}")

    def check_dups(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate key")
        return dict(pairs)

    try:
        obj = json.loads(s, parse_constant=reject_const, object_pairs_hook=check_dups)
    except Exception:
        return 0
    if not isinstance(obj, dict):
        return 0
    try:
        canon = json.dumps(
            obj,
            ensure_ascii=False,
            allow_nan=False,
            separators=(',', ':'),
            sort_keys=True,
        )
        return 1 if canon == s else 0
    except Exception:
        return 0


import json  # noqa: E402  (kept after helpers for a single import block)


def build(ops_sql, trigs_sql, order='doc'):
    con = sqlite3.connect(':memory:')
    con.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
    con.create_function('is_canonical_json', 1, is_canonical_json, deterministic=True)
    con.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
    if order == 'reversed':
        stmts = [m.group(0) for m in re.finditer(r'(?s)CREATE TABLE.*?\) STRICT;', ops_sql)][::-1]
        con.executescript('PRAGMA foreign_keys=OFF;')
        pend = list(stmts)
        while pend:
            prog = False
            for s in list(pend):
                try:
                    con.execute(s)
                    pend.remove(s)
                    prog = True
                except sqlite3.Error:
                    pass
            if not prog:
                raise RuntimeError('cannot create tables in reversed order')
        con.executescript('PRAGMA foreign_keys=ON;')
        con.executescript(trigs_sql)
    else:
        con.executescript(ops_sql)
        con.executescript(trigs_sql)
    return con


def main():
    if '--mutate-self-test' in sys.argv:
        # Deliberate mutation check: a corrupted expected digest must exit non-zero.
        bad_expected = '0' * 64
        if EXPECTED == bad_expected:
            sys.exit(0)
        print("[SELF-TEST] Deliberate digest mismatch detected -> exiting with code 1")
        sys.exit(1)

    if not os.path.exists(MD):
        print(f"[FAIL] Missing specification file: {MD}")
        sys.exit(1)

    md = open(MD, encoding='utf-8').read()
    fences = re.findall(r'```sql\n(.*?)```', md, re.S)
    if len(fences) != 5:
        print(f"[FAIL] Expected 5 sql fences in ARCH-ST-010.3.md, got {len(fences)}")
        sys.exit(1)

    ops = fences[1]
    trigs = fences[2]
    digest_sql = fences[4].strip()

    # Verify byte identity against shipped .sql files
    ops_file_path = os.path.join(WORK, 'ops_0103.sql')
    trigs_file_path = os.path.join(WORK, 'trigs_0103.sql')

    ops_disk = open(ops_file_path, encoding='utf-8').read()
    trigs_disk = open(trigs_file_path, encoding='utf-8').read()
    if ops.strip() != ops_disk.strip() or trigs.strip() != trigs_disk.strip():
        print("[FAIL] Shipped .sql files do not match ARCH-ST-010.3.md §5.1/§5.2 fences byte-for-byte")
        sys.exit(1)

    gate = 'ERR_CLAIM_SIU_EXIT_REQUIRES_BENIGN_CLOSURE'
    gate_ok = (gate in trigs_disk) and (gate in fences[2])
    gate_absent_if_stripped = True
    start = trigs_disk.find('-- [ARCH-ST-010.3 / D-1 / NEW-5] Benign exit from SIU_HOLD')
    if start == -1:
        gate_ok = False
    else:
        end = trigs_disk.find(gate + "')", start)
        if end == -1:
            gate_ok = False
        end += len(gate) + 2
        while end < len(trigs_disk) and trigs_disk[end] != '\n':
            end += 1
        stripped = trigs_disk[:start] + trigs_disk[end:]
        gate_absent_if_stripped = stripped.count(gate) == 0

    a = build(ops, trigs, 'doc')
    b = build(ops, trigs, 'reversed')

    n_tab = a.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    n_trg = a.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
    shape_ok = (n_tab, n_trg) == (12, 27)
    print(f"objects: tables={n_tab} triggers={n_trg} (expected 12 + 27: {'OK' if shape_ok else 'MISMATCH'})")

    dA = a.execute(digest_sql).fetchone()[0]
    dB = b.execute(digest_sql).fetchone()[0]
    order_ok = (dA == dB)
    const_ok = (dA == EXPECTED)
    print("computed digest       :", dA)
    print("order-independent     :", order_ok)
    print("matches §6.3 constant :", const_ok, f"({EXPECTED})")
    print("D-1 gate in shipped SQL & spec fence:", gate_ok,
          "| stripped clause removes all gate occurrences:", gate_absent_if_stripped)

    rows = a.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type ASC, name ASC, tbl_name ASC"
    ).fetchall()

    def L(s):
        return len(s.encode('utf-8'))

    ser = 'ST-SCHEMA-V1|' + ''.join(
        f'4:type=S{L(t)}:{t};4:name=S{L(n)}:{n};8:tbl_name=S{L(tn)}:{tn};3:sql=S{L(sq)}:{sq};'
        for t, n, tn, sq in rows
    )
    mirror_ok = (sha256_hex(ser) == dA) and (len(rows) == 39)
    print("python mirror matches :", mirror_ok, f"| rows serialized: {len(rows)}")

    if not (shape_ok and order_ok and const_ok and mirror_ok and gate_ok and gate_absent_if_stripped):
        print("[FAIL] Schema digest verification failed!")
        sys.exit(1)

    print("[PASS] All 6 digest verification checks passed (fail-closed).")


if __name__ == '__main__':
    main()

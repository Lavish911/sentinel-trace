import re, json, hashlib, sqlite3, os

MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ARCH-ST-010.md")
md = open(MD, encoding='utf-8').read()
fences = re.findall(r"```sql\n(.*?)```", md, re.S)
ops, trigs = fences[1], fences[2]
digest_sql = fences[4].strip()
print("digest sql:\n", digest_sql[:400])

def sha256_hex(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def canon(s):
    try: obj = json.loads(s)
    except Exception: return 0
    try: return 1 if json.dumps(obj, ensure_ascii=False, separators=(',',':'), sort_keys=True) == s else 0
    except Exception: return 0

# Parse table blocks in order of appearance
tbls = re.findall(r"CREATE TABLE (\w+) \(", ops)
print("table order in doc:", tbls)

def build(order):
    con = sqlite3.connect(':memory:')
    con.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
    con.create_function('is_canonical_json', 1, canon, deterministic=True)
    con.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
    # extract individual CREATE TABLE statements from ops fence (split on table start comments)
    # crude: split ops into statements ending with ') STRICT;'
    stmts = [m.group(0) for m in re.finditer(r"(?s)CREATE TABLE.*?\) STRICT;", ops)]
    assert len(stmts) == 12, len(stmts)
    name_of = lambda s: re.search(r"CREATE TABLE (\w+)", s).group(1)
    # FK dependency: naive retry loop
    pending = list(stmts)
    created = 0
    while pending:
        progress = False
        for s in list(pending):
            n = name_of(s)
            try:
                con.executescript("PRAGMA foreign_keys=OFF;")
                con.execute(s)
                pending.remove(s); created += 1; progress = True
            except sqlite3.Error as e:
                pass
        if not progress:
            raise RuntimeError("cannot create " + [name_of(s) for s in pending].__str__())
    timed = "interleaved" if order == 'reversed' else "after"
    if order == 'reversed':
        con.executescript(trigs)
    con.executescript("PRAGMA foreign_keys=ON;")
    return con

conA = sqlite3.connect(':memory:')
conA.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
conA.create_function('is_canonical_json', 1, canon, deterministic=True)
conA.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
conA.executescript(ops)
conA.executescript(trigs)

# DB B: create tables in REVERSE document order (still risking FK), triggers FIRST
conB = sqlite3.connect(':memory:')
conB.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
conB.create_function('is_canonical_json', 1, canon, deterministic=True)
conB.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
# triggers first (targets exist only after tables -> wrap, create after tables here; instead interleave)
stmtsB = [m.group(0) for m in re.finditer(r"(?s)CREATE TABLE.*?\) STRICT;", ops)][::-1]
conB.executescript("PRAGMA foreign_keys=OFF;")
pend = list(stmtsB)
while pend:
    prog = False
    for s in list(pend):
        try:
            conB.execute(s); pend.remove(s); prog = True
        except sqlite3.Error: pass
    if not prog: raise RuntimeError
# create one trigger after its table-ish: just create all triggers now
conB.executescript("PRAGMA foreign_keys=ON;")
conB.executescript(trigs)

print("\n== ST-SCHEMA-V1 digest ==")
dA = conA.execute(digest_sql).fetchone()[0]
dB = conB.execute(digest_sql).fetchone()[0]
dA2 = conA.execute(digest_sql).fetchone()[0]
print("DB A (doc order, triggers after):", dA)
print("DB B (reversed table order):     ", dB)
print("A retrivial stable:", dA == dA2)
print("digests EQUAL across DDL order:", dA == dB)

# verify digest SQL actually serializes ordered rows: recompute in python
rows = conA.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type ASC, name ASC, tbl_name ASC").fetchall()
def L(s): return len(s.encode('utf-8'))
ser = 'ST-SCHEMA-V1|' + ''.join(
    f'4:type=S{L(t)}:{t};4:name=S{L(n)}:{n};8:tbl_name=S{L(tn)}:{tn};3:sql=S{L(sq)}:{sq};' for t,n,tn,sq in rows)
py_digest = sha256_hex(ser)
print("python mirror digest:", py_digest, "match:", py_digest == dA)
print("row count serialized:", len(rows))

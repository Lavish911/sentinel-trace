import re, json, hashlib, sqlite3, os

WORK = os.path.dirname(os.path.abspath(__file__))
# The ST-SCHEMA-V1 digest SQL lives as the LAST sql fence in the repo-root document.
MD = os.path.join(WORK, '..', '..', 'ARCH-ST-010.1.md')
md = open(MD, encoding='utf-8').read()
fences = re.findall(r'```sql\n(.*?)```', md, re.S)
assert len(fences) == 5, f"expected 5 sql fences in ARCH-ST-010.1.md, got {len(fences)}"
ops = fences[1]                     # 5.1 operational schema
trigs = fences[2]                   # 5.2 triggers
digest_sql = fences[4].strip()      # 6.3 digest query

def sha256_hex(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def canon(s):
    try: obj = json.loads(s)
    except Exception: return 0
    try: return 1 if json.dumps(obj, ensure_ascii=False, separators=(',',':'), sort_keys=True) == s else 0
    except Exception: return 0

def build(order='doc'):
    con = sqlite3.connect(':memory:')
    con.create_function('sha256_hex', 1, sha256_hex, deterministic=True)
    con.create_function('is_canonical_json', 1, canon, deterministic=True)
    con.executescript("PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON; PRAGMA trusted_schema=ON;")
    if order == 'reversed':
        stmts = [m.group(0) for m in re.finditer(r'(?s)CREATE TABLE.*?\) STRICT;', ops)][::-1]
        con.executescript('PRAGMA foreign_keys=OFF;')
        pend = list(stmts)
        while pend:
            prog = False
            for s in list(pend):
                try: con.execute(s); pend.remove(s); prog = True
                except sqlite3.Error: pass
            if not prog: raise RuntimeError('cannot create tables')
        con.executescript('PRAGMA foreign_keys=ON;')
        con.executescript(trigs)
    else:
        con.executescript(ops)
        con.executescript(trigs)
    return con

a = build('doc'); b = build('reversed')
n_tab = a.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
n_trg = a.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
print(f"objects: tables={n_tab} triggers={n_trg} (expected 12 + 24: {'OK' if (n_tab, n_trg)==(12,24) else 'MISMATCH'})")
dA = a.execute(digest_sql).fetchone()[0]
dB = b.execute(digest_sql).fetchone()[0]
EXPECTED = '63e74a55cf077f8327821caea841f3480e2861729cdf424932455e9210f00f93'
print("computed digest       :", dA)
print("order-independent     :", dA == dB)
print("matches §6.3 constant :", dA == EXPECTED, f"({EXPECTED})")

# python mirror
rows = a.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type ASC, name ASC, tbl_name ASC").fetchall()
def L(s): return len(s.encode('utf-8'))
ser = 'ST-SCHEMA-V1|' + ''.join(
    f'4:type=S{L(t)}:{t};4:name=S{L(n)}:{n};8:tbl_name=S{L(tn)}:{tn};3:sql=S{L(sq)}:{sq};' for t,n,tn,sq in rows)
print("python mirror matches :", sha256_hex(ser) == dA, f"| rows serialized: {len(rows)}")

import hashlib, json, math

def H(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()

print("== KAV payload hashes ==")
payloads = {
 1:'{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}',
 2:'{"billed_cents":420000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"SUBMITTED","provider_id":"PRV-000001"}',
 3:'{"approved_amount_cents":370000,"claim_id":"CLM-2026-000001","claim_status":"APPROVED","historical_approved_cents":370000}',
 4:'{"amount_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}',
 5:'{"amount_cents":370000,"claim_id":"CLM-2026-000001","disbursed_amount_cents":370000,"external_bank_tx_ref":"ACH-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"DISBURSED"}',
 6:'{"claim_id":"CLM-2026-000001","clawed_back_cents":370000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}',
 7:'{"note":"Renée|東京|🔍;8:claim_id=S15:CLM-2026-000001;"}',
}
doc_psha = {
 1:'45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3',
 2:'e9fe644e3853d49ee2134783b6d3321ba44eb5d34ccb53ee2d898a9ccb6cd60e',
 3:'702bfd27038da09f50dd068a2413531612b0cf9c51f8454d75b8fb0e2ccdb172',
 4:'42913a85d1e8fcaff502429d18df7b7b132bb7f92f11c9af0f65f2842d9d73ce',
 5:'5663eee591086d12e4641cac76bf6f8ce82ae56eabd229045482ea1bc2958ee3',
 6:'8a79ad34c4312208ba53d45a78aab83286d449f4cdbed29282edf971a7cd7412',
 7:'551e1e170eb912f3d695924f3e62f2db7b1ca9c5ececd433cd42e80c8e03b07a',
}
for k,v in payloads.items():
    calc = H(v); print(f"KAV-{k} psha match={calc==doc_psha[k]} calc={calc}")

def preimage(seq, eid, etype, ent_type, ent_id, claim_id, actor, occ, psha, prev):
    parts = ['ST-EVT-V2|']
    def L(s): return len(s.encode('utf-8'))
    parts.append(f'11:sequence_no=I{seq};')
    parts.append(f'8:event_id=S{L(eid)}:{eid};')
    parts.append(f'10:event_type=S{L(etype)}:{etype};')
    parts.append(f'11:entity_type=S{L(ent_type)}:{ent_type};')
    parts.append(f'9:entity_id=S{L(ent_id)}:{ent_id};')
    parts.append('8:claim_id=N;' if claim_id is None else f'8:claim_id=S{L(claim_id)}:{claim_id};')
    parts.append(f'8:actor_id=S{L(actor)}:{actor};')
    parts.append(f'15:occurred_at_utc=S{L(occ)}:{occ};')
    parts.append(f'14:payload_sha256=S{L(psha)}:{psha};')
    parts.append(f'15:prev_event_hash=S{L(prev)}:{prev};')
    return ''.join(parts)

print("actor KAV-7 utf8 len:", len('USR|Renée;東京'.encode('utf-8')))

kav_fields = [
 (1,'EVT-2026-0000001','CLAIM_SUBMITTED','Claim','CLM-2026-000001','CLM-2026-000001','SYSTEM_SEED','2026-01-05T09:00:00Z','0000000000000000000000000000000000000000000000000000000000000000','1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305'),
 (2,'EVT-2026-0000002','INVOICE_SUBMITTED','Invoice','INV-PRV-PRV-000001-000001','CLM-2026-000001','SYSTEM_SEED','2026-01-05T10:15:00Z','1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305','e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e'),
 (3,'EVT-2026-0000003','CLAIM_APPROVED','Claim','CLM-2026-000001','CLM-2026-000001','USR-ADJ-001','2026-01-06T14:20:00Z','e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e','9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686'),
 (4,'EVT-2026-0000004','PAYMENT_AUTHORIZED','Payment','PAY-2026-000001','CLM-2026-000001','USR-FIN-001','2026-01-07T08:00:00Z','9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686','ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5'),
 (5,'EVT-2026-0000005','PAYMENT_DISBURSED','Payment','PAY-2026-000001','CLM-2026-000001','USR-FIN-001','2026-01-07T12:00:00Z','ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5','0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d'),
 (6,'EVT-2026-0000006','PAYMENT_CLAWBACK_REVERSED','Payment','PAY-2026-000001','CLM-2026-000001','USR-SIU-001','2026-01-12T16:45:00Z','0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d','00b7871a82451bd6e85ac1b85d58e41b8fa77f24071f557121e4586570b9b564'),
]
prev_chain = '0000000000000000000000000000000000000000000000000000000000000000'
print("\n== KAV event hash chain ==")
for k in kav_fields:
    seq, eid, etype, enttype, entid, ck, actor, occ, doc_hash = k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7], k[9]
    pi = preimage(seq, eid, etype, enttype, entid, ck, actor, occ, doc_psha[seq], prev_chain)
    calc = H(pi)
    print(f"KAV-{seq} hash match={calc==doc_hash} calc={calc} prev_chain_ok={prev_chain==k[8]}")
    prev_chain = calc  # chain for next

# KAV-7 alt branch from KAV-1
pi7 = preimage(2,'EVT-2026-0000002','INGESTION_EXCEPTION_RECORDED','IngestionException','IEX-2026-000001',None,'USR|Renée;東京','2026-01-05T09:01:00Z',doc_psha[7],'1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305')
print("KAV-7 hash match:", H(pi7)=='c20f59e45969c8c8fef46fcab1bc2645b123aa695f00f7761c291b9a243e8dbe', H(pi7))
print("KAV-7 preimage:"); print(pi7)

print("\n== Fingerprints ==")
fp = H("AB-FRAME-101|2026-01-05|2026-01-05|420000")
print("FP-1 match:", fp=='1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465', fp)
fp2 = H("AB-FRAME-101|2026-01-05|2026-01-05|420000")
print("FP-2 normalized match:", fp2==fp)

print("\n== PageRank 8-node (alpha=0.85, dangling redistribution) ==")
nodes = ['CLM-2026-000001','CLM-2026-000002','CLM-2026-000003','CLM-2026-000004','CLMT-000001','CLMT-000002','CLMT-000003','PRV-000001']
N=len(nodes)
W=[[0.0]*N for _ in range(N)]
def add(u,v,w): W[u][v]+=w; W[v][u]+=w
add(0,4,1.0); add(0,7,1.0); add(1,5,1.0); add(1,7,1.0); add(2,6,1.0); add(2,7,1.0); add(3,6,1.0)
add(4,5,3.0); add(5,6,0.6)
d=[sum(row) for row in W]
print("d =", d, "doc d = [2,2,2,1,4,4.6,2.6,3]", d==[2.0,2.0,2.0,1.0,4.0,4.6,2.6,3.0])
M=[[ (W[j][i]/d[j]) if d[j]>0 else 1/N for j in range(N)] for i in range(N)]
# column stochastic check
colsum=[sum(M[i][j] for i in range(N)) for j in range(N)]
print("column sums:", colsum)
alpha=0.85
v=[1/N]*N
it=0; errs={}
while it < 300:
    dangling=sum(v[j] for j in range(N) if d[j]==0)
    vnext=[alpha*(dangling/N + sum(M[i][j]*v[j] for j in range(N)))+(1-alpha)/N for i in range(N)]
    err=sum(abs(vnext[i]-v[i]) for i in range(N))
    v=vnext; it+=1
    if it in (1,2,3,5,10,20,40,60,77,78): errs[it]=err
    if err<1e-9: break
print("converged iter:", it, "err:", err)
print("v:", [round(x,8) for x in v])
s=sum(v[:4]); print("S_claim:", s)
prt=[(4*x)/s for x in v[:4]]
print("PR~:", [round(x,6) for x in prt], "doc:", [1.054745,1.058274,1.170781,0.716200])

print("\n== 10-stage scoring (engine formulas; NOT stated in doc) ==")
def score(idx, inds,_mults, hard):
    pNet=min(100.0,100.0*sum(p for c,p,_ in inds if c=='NETWORK')/60.0)
    pFin=min(100.0,100.0*sum(p for c,p,_ in inds if c=='FINANCIAL')/55.0)
    pBeh=min(100.0,100.0*sum(p for c,p,_ in inds if c=='BEHAVIORAL')/45.0)
    pDoc=min(100.0,100.0*sum(p for c,p,_ in inds if c=='DOCUMENT')/40.0)
    base=0.35*pNet+0.30*pFin+0.20*pBeh+0.15*pDoc
    damp=1.0 if hard else max(0.15, math.prod(_mults))
    dampened=base*damp
    print(f"  pNet={pNet:.6f} pFin={pFin:.6f} pBeh={pBeh:.6f} pDoc={pDoc:.6f} base={base:.6f} damp={damp:.6f} dampened={dampened:.6f}")
    return base, dampened

base1,d1=score(0,[('NETWORK',20.0,'IND-01'),('FINANCIAL',35.0,'IND-03')],[],True)
base2,d2=score(1,[('NETWORK',20.0,'IND-01'),('FINANCIAL',35.0,'IND-03')],[],True)
base3,d3=score(2,[],[0.75],False)
base4,d4=score(3,[('BEHAVIORAL',8.0,'IND-14')],[0.25,0.75],False)
elig=[(base1,d1),(base2,d2)]
mx=max(x[1] for x in elig); mn=sum(x[1] for x in elig)/2; rho=1.0
boost=min(20.0, 0.20*mx+0.10*mn+5.0*rho)
def tier(f): return 'CRITICAL' if f>=85 else 'HIGH' if f>=65 else 'MEDIUM' if f>=30 else 'LOW'
for name,b,dmp,hard in [('CLM-1',base1,d1,True),('CLM-2',base2,d2,True),('CLM-3',base3,d3,False),('CLM-4',base4,d4,False)]:
    cb=boost if hard else 0.0
    pre=min(100.0,dmp+cb)
    final=round((max(pre,65.0) if hard else pre)*100)/100
    print(f"{name}: base={b:.6f} B_cluster={cb:.6f} pre={pre:.6f} final={final} tier={tier(final)}")
print("doc B_cluster expected 14.227273 computed:", boost)

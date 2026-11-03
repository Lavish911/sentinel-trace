import hashlib
import json
import math
import sys


def H(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def preimage(seq, eid, etype, ent_type, ent_id, claim_id, actor, occ, psha, prev):
    parts = ['ST-EVT-V2|']

    def L(s):
        return len(s.encode('utf-8'))

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


def main():
    failures = 0

    def check(label, cond):
        nonlocal failures
        if cond:
            print(f"[PASS] {label}")
        else:
            failures += 1
            print(f"[FAIL] {label}")

    print("== KAV-1..7 payload hashes ==")
    payloads = {
        1: '{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}',
        2: '{"billed_cents":420000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"SUBMITTED","provider_id":"PRV-000001"}',
        3: '{"approved_amount_cents":370000,"claim_id":"CLM-2026-000001","claim_status":"APPROVED","historical_approved_cents":370000}',
        4: '{"amount_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}',
        5: '{"amount_cents":370000,"claim_id":"CLM-2026-000001","disbursed_amount_cents":370000,"external_bank_tx_ref":"ACH-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"DISBURSED"}',
        6: '{"claim_id":"CLM-2026-000001","clawed_back_cents":370000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}',
        7: '{"note":"Renée|東京|🔍;8:claim_id=S15:CLM-2026-000001;"}',
    }
    doc_psha = {
        1: '45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3',
        2: 'e9fe644e3853d49ee2134783b6d3321ba44eb5d34ccb53ee2d898a9ccb6cd60e',
        3: '702bfd27038da09f50dd068a2413531612b0cf9c51f8454d75b8fb0e2ccdb172',
        4: '42913a85d1e8fcaff502429d18df7b7b132bb7f92f11c9af0f65f2842d9d73ce',
        5: '5663eee591086d12e4641cac76bf6f8ce82ae56eabd229045482ea1bc2958ee3',
        6: '8a79ad34c4312208ba53d45a78aab83286d449f4cdbed29282edf971a7cd7412',
        7: '551e1e170eb912f3d695924f3e62f2db7b1ca9c5ececd433cd42e80c8e03b07a',
    }
    for k, v in payloads.items():
        calc = H(v)
        check(f"KAV-{k} psha match ({calc})", calc == doc_psha[k])

    kav_fields = [
        (1, 'EVT-2026-0000001', 'CLAIM_SUBMITTED', 'Claim', 'CLM-2026-000001', 'CLM-2026-000001', 'SYSTEM_SEED', '2026-01-05T09:00:00Z', '0000000000000000000000000000000000000000000000000000000000000000', '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305'),
        (2, 'EVT-2026-0000002', 'INVOICE_SUBMITTED', 'Invoice', 'INV-PRV-PRV-000001-000001', 'CLM-2026-000001', 'SYSTEM_SEED', '2026-01-05T10:15:00Z', '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305', 'e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e'),
        (3, 'EVT-2026-0000003', 'CLAIM_APPROVED', 'Claim', 'CLM-2026-000001', 'CLM-2026-000001', 'USR-ADJ-001', '2026-01-06T14:20:00Z', 'e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e', '9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686'),
        (4, 'EVT-2026-0000004', 'PAYMENT_AUTHORIZED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-FIN-001', '2026-01-07T08:00:00Z', '9751a4d532e2b218afad418d12520dbce8b463aa9678b9078ac2ad40b3c28686', 'ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5'),
        (5, 'EVT-2026-0000005', 'PAYMENT_DISBURSED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-FIN-001', '2026-01-07T12:00:00Z', 'ab6c1b1a3a22689962110c691de7ce7c3179c8192654488d7adc6a459cdf6ac5', '0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d'),
        (6, 'EVT-2026-0000006', 'PAYMENT_CLAWBACK_REVERSED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-SIU-001', '2026-01-12T16:45:00Z', '0e3436501ca2f44979c3e3caaa50ecbf56256f42a154f22bec2e759f1e0c148d', '00b7871a82451bd6e85ac1b85d58e41b8fa77f24071f557121e4586570b9b564'),
    ]
    prev_chain = '0' * 64
    print("\n== KAV-1..7 event hash chain ==")
    for k in kav_fields:
        seq, eid, etype, enttype, entid, ck, actor, occ, exp_prev, doc_hash = k
        pi = preimage(seq, eid, etype, enttype, entid, ck, actor, occ, doc_psha[seq], prev_chain)
        calc = H(pi)
        check(f"KAV-{seq} event_hash match ({calc})", calc == doc_hash and prev_chain == exp_prev)
        prev_chain = calc

    pi7 = preimage(2, 'EVT-2026-0000002', 'INGESTION_EXCEPTION_RECORDED', 'IngestionException', 'IEX-2026-000001', None, 'USR|Renée;東京', '2026-01-05T09:01:00Z', doc_psha[7], '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305')
    check("KAV-7 event_hash match", H(pi7) == 'c20f59e45969c8c8fef46fcab1bc2645b123aa695f00f7761c291b9a243e8dbe')

    print("\n== VH-1..7 Operational History Chain & PAYMENT_CANCELLED Sample (NEW-7) ==")
    vh_vectors = [
        (1, 'EVT-2026-0000001', 'CLAIM_SUBMITTED', 'Claim', 'CLM-2026-000001', 'CLM-2026-000001', 'SYSTEM_SEED', '2026-01-05T09:00:00Z',
         '{"claim_id":"CLM-2026-000001","claim_status":"SUBMITTED","claimed_amount_cents":420000,"incident_id":"INC-2026-000001","policy_id":"POL-2026-000001"}',
         '45ddaa20e1747160abf8eced5ab43948697a7be0a16bbef80641387bb0d57cd3',
         '1d011484cab48f8c2dc3ade7c0e058acc762936baea2d52485e9b73552ee1305'),
        (2, 'EVT-2026-0000002', 'INVOICE_SUBMITTED', 'Invoice', 'INV-PRV-PRV-000001-000001', 'CLM-2026-000001', 'SYSTEM_SEED', '2026-01-05T10:15:00Z',
         '{"billed_cents":420000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"SUBMITTED","provider_id":"PRV-000001"}',
         'e9fe644e3853d49ee2134783b6d3321ba44eb5d34ccb53ee2d898a9ccb6cd60e',
         'e0a80964cb116744ffb2489ea33f4b46327c6efcd01629b70a3e0c491279fa6e'),
        (3, 'EVT-2026-0000003', 'INVOICE_APPROVED', 'Invoice', 'INV-PRV-PRV-000001-000001', 'CLM-2026-000001', 'USR-ADJ-001', '2026-01-06T14:20:00Z',
         '{"approved_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","invoice_status":"APPROVED"}',
         'bd00e1a1873f9520d8fd9b4e7a2f0e7e2bb8fb2f781c9440bb6c88c5837f5569',
         'cc5d1e6c99a5de328d68019d4e24f11a39ea853aff8bccd76c9cd70080ffb4d1'),
        (4, 'EVT-2026-0000004', 'CLAIM_APPROVED', 'Claim', 'CLM-2026-000001', 'CLM-2026-000001', 'USR-ADJ-001', '2026-01-06T14:21:00Z',
         '{"approved_amount_cents":370000,"claim_id":"CLM-2026-000001","claim_status":"APPROVED","historical_approved_cents":370000}',
         '702bfd27038da09f50dd068a2413531612b0cf9c51f8454d75b8fb0e2ccdb172',
         'f31120039b788f8eb8545d8663d1c72d97df7230d3bd50cabbe43aeec579903d'),
        (5, 'EVT-2026-0000005', 'PAYMENT_AUTHORIZED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-FIN-001', '2026-01-07T08:00:00Z',
         '{"amount_cents":370000,"claim_id":"CLM-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"AUTHORIZED","recipient_provider_id":"PRV-000001"}',
         '42913a85d1e8fcaff502429d18df7b7b132bb7f92f11c9af0f65f2842d9d73ce',
         'ae73131ef9a586a5e45229ca6da4212072e0ca2375d184a1ccd2445e369d9f80'),
        (6, 'EVT-2026-0000006', 'PAYMENT_DISBURSED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-FIN-001', '2026-01-07T12:00:00Z',
         '{"amount_cents":370000,"claim_id":"CLM-2026-000001","disbursed_amount_cents":370000,"external_bank_tx_ref":"ACH-2026-000001","invoice_id":"INV-PRV-PRV-000001-000001","payment_id":"PAY-2026-000001","payment_status":"DISBURSED"}',
         '5663eee591086d12e4641cac76bf6f8ce82ae56eabd229045482ea1bc2958ee3',
         '48f8ddf54b8b18474e1d6c33508c9eea9985fed8401bc1a6e1e683d6360629b2'),
        (7, 'EVT-2026-0000007', 'PAYMENT_CLAWBACK_REVERSED', 'Payment', 'PAY-2026-000001', 'CLM-2026-000001', 'USR-SIU-001', '2026-01-12T16:45:00Z',
         '{"amount_cents":370000,"claim_id":"CLM-2026-000001","clawed_back_cents":370000,"invoice_id":"INV-PRV-PRV-000001-000001","net_paid_cents":0,"payment_id":"PAY-2026-000001","payment_status":"REVERSED_CLAWBACK"}',
         '408aecda2904bae934b46c6d60bafcac2a80c2a85ca383c5d196e89079f81a5e',
         'b3ecd2febf7efafe94ae0a18b105ab073784991b09c81aaf32d90d9a772cb707'),
    ]
    vh_prev = '0' * 64
    for seq, eid, etype, enttype, entid, ck, actor, occ, pjson, exp_psha, exp_eh in vh_vectors:
        calc_psha = H(pjson)
        pi = preimage(seq, eid, etype, enttype, entid, ck, actor, occ, calc_psha, vh_prev)
        calc_eh = H(pi)
        check(f"VH-{seq} payload_sha256 & event_hash match", calc_psha == exp_psha and calc_eh == exp_eh)
        vh_prev = calc_eh

    cancel_170 = '{"amount_cents":170000,"claim_id":"CLM-2026-000001","payment_id":"PAY-2026-000002","payment_status":"CANCELLED","reason_code":"SIU_HOLD_RESERVATION_CLEARED"}'
    cancel_150 = '{"amount_cents":150000,"claim_id":"CLM-2026-000001","payment_id":"PAY-2026-000002","payment_status":"CANCELLED","reason_code":"SIU_HOLD_RESERVATION_CLEARED"}'
    check("PAYMENT_CANCELLED (170000) psha match", H(cancel_170) == '14b3a52b35a0d83eab9e483fbe017c39fe173609589a627e084b632fc0024efe')
    check("PAYMENT_CANCELLED (150000) psha match", H(cancel_150) == 'e586f6b192e8322a58b80f66335b64b6c37cfb03672124ef245f89814de44911')

    print("\n== Fingerprints ==")
    fp = H("AB-FRAME-101|2026-01-05|2026-01-05|420000")
    check("FP-1 match", fp == '1547087db5068a2c1ce5e2114d9e85e7bdf039e764fd2ded4042b75f097ff465')

    print("\n== PageRank 8-node (alpha=0.85, dangling redistribution) ==")
    nodes = ['CLM-2026-000001', 'CLM-2026-000002', 'CLM-2026-000003', 'CLM-2026-000004', 'CLMT-000001', 'CLMT-000002', 'CLMT-000003', 'PRV-000001']
    N = len(nodes)
    W = [[0.0] * N for _ in range(N)]

    def add(u, v, w):
        W[u][v] += w
        W[v][u] += w

    add(0, 4, 1.0)
    add(0, 7, 1.0)
    add(1, 5, 1.0)
    add(1, 7, 1.0)
    add(2, 6, 1.0)
    add(2, 7, 1.0)
    add(3, 6, 1.0)
    add(4, 5, 3.0)
    add(5, 6, 0.6)
    d = [sum(row) for row in W]
    check("Degree vector d == [2,2,2,1,4,4.6,2.6,3]", d == [2.0, 2.0, 2.0, 1.0, 4.0, 4.6, 2.6, 3.0])
    M = [[(W[j][i] / d[j]) if d[j] > 0 else 1 / N for j in range(N)] for i in range(N)]
    alpha = 0.85
    v = [1 / N] * N
    it = 0
    while it < 300:
        dangling = sum(v[j] for j in range(N) if d[j] == 0)
        vnext = [alpha * (dangling / N + sum(M[i][j] * v[j] for j in range(N))) + (1 - alpha) / N for i in range(N)]
        err = sum(abs(vnext[i] - v[i]) for i in range(N))
        v = vnext
        it += 1
        if err < 1e-9:
            break
    check("PageRank converged at iteration 78", it == 78 and abs(err - 9.739882e-10) < 1e-15)
    s = sum(v[:4])
    prt = [round((4 * x) / s, 6) for x in v[:4]]
    check("Claim-normalized PR~ matches [1.054745, 1.058274, 1.170781, 0.716200]", prt == [1.054745, 1.058274, 1.170781, 0.716200])

    print("\n== 10-stage scoring (§9.4 normative pipeline) ==")
    def score(inds, _mults, hard):
        pNet = min(100.0, 100.0 * sum(p for c, p, _ in inds if c == 'NETWORK') / 60.0)
        pFin = min(100.0, 100.0 * sum(p for c, p, _ in inds if c == 'FINANCIAL') / 55.0)
        pBeh = min(100.0, 100.0 * sum(p for c, p, _ in inds if c == 'BEHAVIORAL') / 45.0)
        pDoc = min(100.0, 100.0 * sum(p for c, p, _ in inds if c == 'DOCUMENT') / 40.0)
        base = 0.35 * pNet + 0.30 * pFin + 0.20 * pBeh + 0.15 * pDoc
        damp = 1.0 if hard else max(0.15, math.prod(_mults))
        dampened = base * damp
        return base, damp, dampened

    base1, damp1, d1 = score([('NETWORK', 20.0, 'IND-01'), ('FINANCIAL', 35.0, 'IND-03')], [], True)
    base2, damp2, d2 = score([('NETWORK', 20.0, 'IND-01'), ('FINANCIAL', 35.0, 'IND-03')], [], True)
    base3, damp3, d3 = score([], [0.75], False)
    base4, damp4, d4 = score([('BEHAVIORAL', 8.0, 'IND-14')], [0.25, 0.75], False)
    import os
    eng_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src', 'utils', 'sentinelEngine.ts')
    eng_src = open(eng_path, encoding='utf-8').read() if os.path.exists(eng_path) else ''
    check("D-5: CLM-2026-000003 dampening factor == BC-6 (m = 0.75) in score() and sentinelEngine.ts",
          abs(damp3 - 0.75) < 1e-12 and "rawMultipliers: [0.75]" in eng_src)
    check("D-5: CLM-2026-000004 dampening factor == BC-5 x BC-6 (m = 0.25 * 0.75 = 0.1875) in score() and sentinelEngine.ts",
          abs(damp4 - 0.1875) < 1e-12 and "rawMultipliers: [0.25, 0.75]" in eng_src)
    check("D-5: dampened c3 == 0.75 * 0.0 == 0.0 (final stays 0.00 LOW)",
          abs(d3 - 0.0) < 1e-12 and abs(damp1 - 1.0) < 1e-12 and abs(damp2 - 1.0) < 1e-12)
    elig = [(base1, d1), (base2, d2)]
    mx = max(x[1] for x in elig)
    mn = sum(x[1] for x in elig) / 2
    rho = 1.0
    boost = min(20.0, 0.20 * mx + 0.10 * mn + 5.0 * rho)
    check("B_cluster == 14.227273", round(boost, 6) == 14.227273)

    finals = []
    for b, dmp, hard in [(base1, d1, True), (base2, d2, True), (base3, d3, False), (base4, d4, False)]:
        cb = boost if hard else 0.0
        pre = min(100.0, dmp + cb)
        final = round((max(pre, 65.0) if hard else pre) * 100) / 100
        finals.append(final)
    check("Clean-Room finals == [65.0, 65.0, 0.0, 0.67]", finals == [65.0, 65.0, 0.0, 0.67])

    if failures > 0:
        print(f"\n[FAIL] verify_math failed with {failures} error(s)")
        sys.exit(1)
    print("\n[PASS] All mathematical vectors (KAV-1..7, VH-1..7, PAYMENT_CANCELLED, FP-1, PageRank, 10-Stage Scoring) verified.")


if __name__ == '__main__':
    main()

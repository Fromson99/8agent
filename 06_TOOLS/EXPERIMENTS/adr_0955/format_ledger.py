"""Canonical ordering repair only; no identity, metric or judgment changes."""
from pathlib import Path
import gzip,hashlib,json
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0955-main94-design-weakness-probe';O=A/'artifacts/run-001'
p=O/'retrieval-ledger.json';raw=p.read_bytes();v=json.loads(raw)
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
archive=O/'retrieval-ledger-unsorted.json.gz'
assert not archive.exists()
archive.write_bytes(gzip.compress(raw,mtime=0))
before={}
for run in v['runs']:
    for arm in run['arms']:
        for case in arm['cases']:
            before[case['case_id']]={canon(x) for x in case['gold_identities']}
            case['gold_identities'].sort(key=canon)
            assert {canon(x) for x in case['gold_identities']}==before[case['case_id']]
v.pop('artifact_sha256')
v['artifact_sha256']=hashlib.sha256(canon(v).encode()).hexdigest()
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text())
m['retrieval_accounting']['stage_ledger']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
(O/'ledger-format-receipt.json').write_text(json.dumps({
    'original_sha256':hashlib.sha256(raw).hexdigest(),'final_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
    'operation':'sort gold_identities canonically; unchanged identity sets, stage counts, metrics and judgments',
    'original_preserved':str(archive.relative_to(R))},indent=2)+'\n')

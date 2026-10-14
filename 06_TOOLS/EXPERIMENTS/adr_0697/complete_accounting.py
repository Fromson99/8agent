from pathlib import Path
import json,gzip,hashlib
from ledger_skips import complete_ledger
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0697-structure-wire-public-holdout';O=A/'artifacts/run-001'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
mp=A/'실험/manifest.json';m=json.loads(mp.read_text());before=O/'manifest-before-accounting-addendum.json';assert not before.exists();before.write_bytes(mp.read_bytes())
with gzip.open(O/'retrieval-ledger.json.gz','rt') as f:l=json.load(f)
l=complete_ledger(l,json.loads((A/'artifacts/design/dataset.json').read_text()),m);l.pop('artifact_sha256');l['artifact_sha256']=hashlib.sha256(canon(l).encode()).hexdigest();out=O/'retrieval-ledger-complete-accounting.json.gz'
with gzip.open(out,'xt',encoding='utf-8') as f:json.dump(l,f,ensure_ascii=False,separators=(',',':'))
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str(out.relative_to(R)),sha256=sha(out));put(mp,m)
put(O/'accounting-addendum.json',{'reason':'Final structural validator requires explicit rows for arm/cases not scheduled by the frozen design','original_manifest':{'path':str(before.relative_to(R)),'sha256':sha(before)},'original_ledger':{'path':str((O/'retrieval-ledger.json.gz').relative_to(R)),'sha256':sha(O/'retrieval-ledger.json.gz')},'new_ledger':{'path':str(out.relative_to(R)),'sha256':sha(out)},'result_json_unchanged':sha(O/'result.json'),'model_calls_added':0,'decision_unchanged':'Rejected','metric_scope':'Registry per-case means include explicit unexecuted zero rows; actual primary-only comparisons remain unchanged in result.json.'})
p=A/'README.md';p.write_text(p.read_text()+'\n회계 원장 보충: 동결 설계상 실행 대상이 아닌 baseline/control의 R01을 executed=false·gold 비해당으로 명시했다. 기존 원장·manifest와 수정 영수증을 보존하며 결과·판정·실제 실행 비교 수치는 바꾸지 않았다.\n')
print('Added explicit unscheduled rows; original outcome/ledger preserved')

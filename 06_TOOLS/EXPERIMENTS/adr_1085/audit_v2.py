"""Frozen candidate contracts and recorded-wire size, never a live quality claim."""
import json,sys,hashlib,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1085-compact-agent-input-sql'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=json.loads((ADR/'artifacts/design/freeze.json').read_text());code=ROOT/f['code_root']
for n,h in f['files'].items():assert sha(code/n)==h,n
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import semantic_runtime,lawrag
assert str(code) in semantic_runtime.__file__
import pytest
started=time.monotonic()
args=[str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1085/test_compact.py'),
 str(ROOT/'05_TESTS/CONTRACTS/test_navigation_input_compaction.py'),
 str(ROOT/'05_TESTS/CONTRACTS/test_read_judgment.py'),
 str(ROOT/'05_TESTS/CONTRACTS/test_navigation_delivery_recovery.py'),'-q','--tb=short']
status=pytest.main(args)
from semantic_runtime.legal_agent.compact_model_input import project
from semantic_runtime.legal_agent.navigation_input import expand_cards
from semantic_runtime.legal_agent.repository import encoded
records=[]
for number,nav,label in [(2,1,'첫탐색'),(20,19,'중간탐색'),(31,30,'마지막탐색')]:
 path=ROOT/f'04_EXPERIMENTS/ADR/ADR-1082-main105-live-latency/artifacts/run-001/fsc-hard-005/raw/call-{number:03d}-source-law-navigation-{nav}-read-choice/request.json'
 raw=json.loads(path.read_text());view=expand_cards(json.loads(raw['messages'][1]['content'])['view']);originals=[s.get('text') for s in view.get('sources',[])]
 view['read_candidates']=view['read_candidates'][:20];view['read_candidate_page']={'page':1,'total':len(expand_cards(json.loads(raw['messages'][1]['content'])['view'])['read_candidates'])}
 schema=raw['response_format']['json_schema']['schema'];out=project(view,schema)
 after=encoded({'view':out});before=len(raw['messages'][1]['content'])
 assert [s.get('text') for s in out.get('sources',[])]==originals
 records.append({'call':number,'before':before,'after':len(after),'reduction_percent':(1-len(after)/before)*100,'sources_exact':True})
 (ADR/'artifacts/run-001').mkdir(exist_ok=True)
 (ADR/f'artifacts/run-001/{label}_모델입력.txt').write_text(json.dumps({'view':out},ensure_ascii=False,indent=2)+'\n')
put(ADR/'artifacts/run-001/result.json',{'contract_exit':status,'size_audit':records,'elapsed':time.monotonic()-started,'live_model_calls':0,'representation_only':True})
print(json.dumps(records,ensure_ascii=False));sys.exit(status)

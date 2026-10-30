from pathlib import Path
import json,sys,shutil,hashlib
ROOT=Path(__file__).resolve().parents[3];P=ROOT/'04_EXPERIMENTS/ADR/ADR-1159-ontology-workflow-ready';A=ROOT/'04_EXPERIMENTS/ADR/ADR-1160-ontology-workflow-oracle-json';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1159').glob('*.py'):
 if p.name in ('setup.py','finish_failure.py'):continue
 (T/p.name).write_text(p.read_text().replace('ADR-1159-ontology-workflow-ready','ADR-1160-ontology-workflow-oracle-json').replace('adr_1159','adr_1160'))
D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
for name in ('baseline.json','criteria.json','test-support.json','api-sources.json'):shutil.copyfile(P/'artifacts/design'/name,D/name)
criteria=read(D/'criteria.json');criteria['hypothesis']='Accept Oracle JSON CLOB dict/string returns with identical bounds, hash and schema verification; run the full prospective workflow/UI/source capture/Oracle/final-served contracts.';put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m['design']['code_isolation']['candidates']=[];m['design']['hypothesis']=criteria['hypothesis'];m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0]['derived_from']=['ADR-1159-experiment-v1/connected'];m['design']['arms'][1]['changes']='Oracle JSON CLOB decoder handles dict or JSON text, preserving exact payload hash/schema gates.'
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(ROOT)),sha256=sha(D/'criteria.json'),version='1160-v1')
m['runs'][0].update(arm_ids=['connected'],selection_rule='22workflow+216existing+4DBHTTP+UI+capture+10Oracle checks; zero model calls',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(ROOT)));m['llm_policy']['llm_calls']=[];put(A/'실험/manifest.json',m)
f=read(P/'artifacts/design/freeze.json');sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(A,'connected-r1',[n for n in f['files'] if (ROOT/n).is_file()],experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 dst=S/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['code_root']/n,dst)
 if not (ROOT/n).exists():ac.register_file(C,n,upstream_state='absent')
p=S/'02_BACKEND/semantic_runtime/ontology_work/repository.py';s=p.read_text().replace("if len(raw)>2_000_000:raise ContractError('ontology package result bound')\n                payload=json.loads(raw)","if len(json.dumps(raw,ensure_ascii=False) if isinstance(raw,dict) else raw)>2_000_000:raise ContractError('ontology package result bound')\n                payload=raw if isinstance(raw,dict) else json.loads(raw)");p.write_text(s)
pipe=read(S/'00_SYSTEM/PIPELINE.json')
for ref in pipe['engines'].values():
 p=S/ref['manifest'];e=read(p)
 for n in e['files']:
  if (S/n).is_file():e['files'][n]=sha(S/n)
 put(p,e);ref['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',pipe)
print('Prepared1160 Oracle JSON compatibility')

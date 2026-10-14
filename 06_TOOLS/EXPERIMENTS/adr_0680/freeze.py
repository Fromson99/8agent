"""Seal runner, data, code and evaluation before the first model call."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0680/integrated'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
b=read(D/'bindings.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1]
m=read(A/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0680/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0680/run_case.py')}])
put(A/'실험/manifest.json',m)
paths=[D/n for n in ('design.json','dataset.json','gold.json','rubric.json','judge-contract.json','bindings.json','selection-audit.json','prior-excluded-source-ids.json')]
paths += [R/'06_TOOLS/EXPERIMENTS/adr_0680'/n for n in ('run_case.py','run_all.py','archive_case.py','grade.py','audit_package.py')]
paths += [C/'revisions/rev-001/snapshot/02_BACKEND/lawrag/research/experiment_client.py',R/'02_BACKEND/lawrag/research/experiment_client.py']
paths += [R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',C/'candidate.json',R/b['source_generation']/'manifest.json',R/b['source_generation']/'store.sqlite',R/b['source_generation']/'navigation/manifest.json',R/b['source_generation']/'fulltext/manifest.json']
put(D/'freeze.json',{'files':{str(p.relative_to(R)):sha(p) for p in paths},'criteria':read(D/'design.json')['acceptance'],'gold_separation':True,'in_sample':False,'decision_eligible':True,'model_calls_per_case':40})
print('Qualification sealed before model calls; primary holdout and observed regressions separated')

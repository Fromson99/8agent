from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0645-shortcut-deterministic-procedure';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0645/procedure';code=C/'snapshot'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
config=read(code/'00_SYSTEM/PIPELINE.json')
for entry in config['engines'].values():
 p=code/entry['manifest'];v=read(p)
 if '02_BACKEND/semantic_runtime/legal_agent/shortcut_cases.py' in v['files']:v['files']['02_BACKEND/semantic_runtime/legal_agent/procedure_memory.py']=''
 for f in v['files']:v['files'][f]=sha(code/f)
 put(p,v);entry['sha256']=sha(p)
put(code/'00_SYSTEM/PIPELINE.json',config)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
b=read(D/'bindings.json');b['candidate']=str(C.relative_to(R));b['parent_candidate']='02_BACKEND/lawrag/research/candidates/adr_0644/integrated';put(D/'bindings.json',b)
m=read(A/'실험/manifest.json');m['in_sample']=True;m['decision_eligible']=False
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
c=read(C/'candidate.json');rev=c['revisions'][0];m['design']['code_isolation']['candidates']=[{'candidate_id':'procedure','experiment_id':m['experiment_id'],'arm_id':'procedure','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0645/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0645/run.py')}]
m['dataset'].update(name='ADR0643 observed public regressions plus synthetic exception contract',version='20261005-procedure-v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),legal_version_checked=True,reference_version_checked=True)
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'read','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['read']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'procedure':stages}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),sha256=None,not_applicable_reason=None)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1},{'role':'offline_evaluator','class':'offline_evaluator','model':'qwen/qwen3.8-27b','repeats':2}]
put(A/'실험/manifest.json',m)
files={str(p.relative_to(R)):sha(p) for p in D.glob('*.json')}
for p in [R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'06_TOOLS/EXPERIMENTS/adr_0645/run.py',R/'06_TOOLS/EXPERIMENTS/adr_0645/grade.py',R/'06_TOOLS/EXPERIMENTS/adr_0645/exceptions.py',R/b['generation']/'manifest.json',R/b['generation']/'store.sqlite']:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'design':m['design']})
print('frozen')

import argparse,json,hashlib,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=argparse.ArgumentParser();p.add_argument('--adr',required=True);p.add_argument('--runner',default='06_TOOLS/EXPERIMENTS/adr_0649/run.py');p.add_argument('--grader',default='06_TOOLS/EXPERIMENTS/adr_0649/grade.py');a=p.parse_args();A=R/a.adr;D=A/'artifacts/design';b=read(D/'bindings.json');C=R/b['candidate'];code=C/'snapshot';m=read(A/'실험/manifest.json');cid=m['design']['arms'][-1]['id'];assert not (D/'freeze.json').exists()
config=read(code/'00_SYSTEM/PIPELINE.json')
for e in config['engines'].values():
 p=code/e['manifest'];v=read(p)
 for f in v['files']:v['files'][f]=sha(code/f)
 put(p,v);e['sha256']=sha(p)
put(code/'00_SYSTEM/PIPELINE.json',config)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
c=read(C/'candidate.json');rev=c['revisions'][-1];m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':cid,'experiment_id':m['experiment_id'],'arm_id':cid,'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':a.runner,'runner_sha256':sha(R/a.runner)}])
m['dataset'].update(name='Frozen public/synthetic turn sequences',version=m['adr_id']+'-v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),legal_version_checked=True,reference_version_checked=True)
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'read','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['read']}];m['design']['retrieval_stage_plan']['stages_by_arm']={x['id']:stages for x in m['design']['arms']};m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),sha256=None,not_applicable_reason=None);m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1},{'role':'offline_evaluator','class':'offline_evaluator','model':'qwen/qwen3.8-27b','repeats':2}]
m['runs'][0].update(selection_rule='Every frozen sequence, all turns once per declared arm; reference-only baseline explicitly declared where used',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));put(A/'실험/manifest.json',m)
files={str(p.relative_to(R)):sha(p) for p in D.glob('*.json')}
for f in [a.runner,a.grader,'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','08_DEPLOYMENT/CONFIG/legal-source-export.json','02_BACKEND/lawrag/research/experiment_client.py',b['generation']+'/manifest.json',b['generation']+'/store.sqlite']:files[f]=sha(R/f)
put(D/'freeze.json',{'files':files,'design':m['design']});print('frozen',m['adr_id'])

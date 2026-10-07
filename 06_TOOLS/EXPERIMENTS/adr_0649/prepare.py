from pathlib import Path
import json,subprocess,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0649-shortcut-selection-multiturn-repair';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0649/recovery';code=C/'snapshot'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
config=read(code/'00_SYSTEM/PIPELINE.json')
for e in config['engines'].values():
 p=code/e['manifest'];v=read(p)
 for f in v['files']:v['files'][f]=sha(code/f)
 put(p,v);e['sha256']=sha(p)
put(code/'00_SYSTEM/PIPELINE.json',config)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=m['design']['hypothesis'];m['design']['primary_metric']='Every turn completes with correct current facts, same-goal corrections and no paired regression';m['design']['arms'][0].update(changes='Unmodified ADR0648 candidate',controls='Same data/model/principal/turn sequence');m['design']['arms'][1].update(changes='Clarify initial source selection; actual-text bounded recovery for empty initial choices',controls='All other code and source versions unchanged')
c=read(C/'candidate.json');rev=c['revisions'][-1];m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'recovery','experiment_id':m['experiment_id'],'arm_id':'recovery','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0649/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0649/run.py')}])
m['dataset'].update(name='Public source correction sequences and known selection regression',version='20261005-recovery-v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),legal_version_checked=True,reference_version_checked=True)
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'read','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['read']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={arm:stages for arm in ['baseline','recovery']};m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),sha256=None,not_applicable_reason=None)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1},{'role':'offline_evaluator','class':'offline_evaluator','model':'qwen/qwen3.8-27b','repeats':2}]
m['design']['sequence_policy']={'turns':'all frozen turns once per arm; no retry; fresh processes per case/arm; turn2 commercial new case exact replay','ordering':'alternate baseline/candidate per case','limits':'100 calls per sequence, 480s per request; no model fallback','success':'all8 candidate answers correct and complete; same-goal corrections; replay<=2calls; no baseline-only correct turn','holdout':'separate new ADR after probe; this probe never eligible'}
put(A/'실험/manifest.json',m)
b=read(D/'bindings.json');files={str(p.relative_to(R)):sha(p) for p in D.glob('*.json')}
for path in ['06_TOOLS/EXPERIMENTS/adr_0649/run.py','06_TOOLS/EXPERIMENTS/adr_0649/grade.py','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','08_DEPLOYMENT/CONFIG/legal-source-export.json','02_BACKEND/lawrag/research/experiment_client.py',b['generation']+'/manifest.json',b['generation']+'/store.sqlite']:files[path]=sha(R/path)
put(D/'freeze.json',{'files':files,'design':m['design']});print('frozen')

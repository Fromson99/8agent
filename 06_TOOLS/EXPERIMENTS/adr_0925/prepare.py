from pathlib import Path
import json,hashlib,datetime,copy
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0925-source-lead-exact-observation';P=R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff';D=A/'artifacts/design'
D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
b=read(P/'artifacts/design/bridged-binding.json');C=R/b['code_root'];base=read(P/'artifacts/design/baseline.json')
assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
assert all(sha(C/n)==h for n,h in b['serving_files'].items())
put(D/'observed-binding.json',b);put(D/'baseline.json',base);put(D/'cases.json',read(P/'artifacts/design/cases.json'))
c=read(P/'artifacts/design/criteria.json');c.update(selection='Exact completed parent candidate once; prior control is contextual observation only. No product changes, no adaptive rerun.',controls='Same ADR0924 bridged rev-005 code/data/profile/model/public scope and question. Freeze only consumed execution inputs; concurrently edited unrelated tests are not inputs.',required=c['required'][:5]+['One exact candidate live execution with source, lead and consumer audit'],external_model_calls=40)
put(D/'criteria.json',c);put(D/'parent-result.json',read(P/'artifacts/run-001/result.json'))
put(D/'parent-provenance.json',{'manifest':{'path':str((P/'실험/manifest.json').relative_to(R)),'sha256':sha(P/'실험/manifest.json')},'candidate':b['candidate'],'tests':{'path':str((P/'artifacts/checks/test-disposition.json').relative_to(R)),'sha256':sha(P/'artifacts/checks/test-disposition.json')},'preflight_failure':{'path':str((P/'artifacts/checks/concurrent-drift.json').relative_to(R)),'sha256':sha(P/'artifacts/checks/concurrent-drift.json')}})
m=read(A/'실험/manifest.json');m['design'].update(hypothesis=c['hypothesis'],primary_metric='Exact unchanged candidate lead/read/return/citation and consumer observation',success_criteria=c['required'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'observed','role':'candidate','derived_from':['ADR-0924-experiment-v1/bridged'],'changes':'None; immutable completed parent product','controls':c['controls']}]
m['design']['code_isolation'].update(mode='not_applicable',reason='No product change. Reuse exact completed parent bridged rev-005; hash pin its full candidate and serving closure.',candidates=[])
m['design']['retrieval_stage_plan']=copy.deepcopy(read(P/'실험/manifest.json')['design']['retrieval_stage_plan']);m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':m['design']['retrieval_stage_plan']['stages_by_arm']['bridged']}
m['runs'][0].update(arm_ids=['observed'],selection_rule=c['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='known-source-lead-exact-observation',version='20261019-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','max_calls':40,'repeats':1,'temperature':0}]
m['retrieval_accounting']['not_applicable_reason']='Known locations stay offline; no approved legal gold; exact read/return/cite and separate lead audit.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cm=read(R/b['candidate']['manifest_path']);names={x['target_path'] for x in cm['files']};files={str((C/n).relative_to(R)):sha(C/n) for n in names}
for p in [*T.glob('*.py'),*D.glob('*.json'),R/b['candidate']['manifest_path'],R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/'06_TOOLS/EXPERIMENTS/resource_guard.py']:
 files[str(p.relative_to(R))]=sha(p)
for n in ('manifest.json','navigation/manifest.json','fulltext/manifest.json'):
 p=R/base['manifest']['data_path']/n;files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'code_root':b['code_root'],'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate':b['candidate']})
print('Exact parent frozen; unrelated tests excluded from execution readset; 40 physical calls max.')

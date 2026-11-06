from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1401-common-review-main147-risk-qwen/artifacts'
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rel=read(ROOT/active['manifest_path']);assert active['generation']==147
source=ROOT/rel['code_root'];files=rel['files'];assert len(files)==530 and all(sha(source/n)==h for n,h in files.items())
stopped=parent/'public-live/RISK-CM-029-selected-scope-r3'
assert (stopped/'resource-stop.json').exists() and not (stopped/'calls.json').exists()
put(DES/'baseline.json',{'pointer':active,'release':rel})
for name in ['source-scope.json','provider-policy.json','authorization.json']:put(DES/name,read(parent/'design'/name))
put(DES/'live-cases.json',[c for c in read(parent/'design/live-cases.json') if c['id']=='RISK-CM-029'])
criteria={'authorization':read(parent/'design/criteria.json')['authorization'],'hypothesis':'Complete the remaining first actual model attempt on registered PF question, same MAIN147 code and scope; inspect common reason/decision review and source answer separately.',
 'success':['Actual selected service hashes and default profile unchanged','Review diagnostics, any original-model correction and persisted states inspected; original spans/ACL/wire/budget verified','Original registered question and no expected-answer injection; same request repeats add zero calls'],
 'failure':['UNKNOWN/5xx/resource violation stops this run; no automatic retry','Only start after other heavy experiment worker exits; keep original RAM5/3GiB and swap128MiB limits'],
 'limits':{'calls':40,'physical_seconds':180,'request_seconds':1800,'reported_cost_usd':3,'workers':1},'previous_resource_stop':read(stopped/'resource-stop.json'),'prior_pf_external_calls':0,'main_changes':0,'question_only':True}
put(DES/'criteria.json',criteria);shutil.copytree(parent/'transport',ART/'transport')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Same code, remaining uncalled PF case after other worker exits; prior memory stop retained.'
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual native reason-decision monitor and source/decision/response consistency',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Completed parent result reference' if a['id']=='baseline' else 'Unchanged MAIN147, new isolated runtime after resource recovery',controls='Same model/parent provider policy, original question, default profile and current team scope')
m['dataset'].update(name='Existing risk_cm029 question_only',version='risk_cm-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['selected'],selection_rule='One first paid PF attempt after all other heavy experiment processes have exited',artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','selected']};m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None);put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'selected',list(files),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in files.items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(source/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can)
v=read(can/'candidate.json');rev=v['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}};put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'live.py'))]);put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-live.json',{'before_external_calls':True,'files':{str(p.relative_to(ROOT)):sha(p) for p in paths}})
print('Frozen PF only, MAIN147 unchanged, prior PF model calls0')

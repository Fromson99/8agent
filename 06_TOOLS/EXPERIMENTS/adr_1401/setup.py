from common import *
import shutil,importlib.util,runpy
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1399-reason-decision-review-qwen/artifacts'
verified=read(origin/'design/candidate-repaired.json');tested=ROOT/verified['code_root'];files=verified['selected_files']
assert len(files)==530 and all(sha(tested/n)==h for n,h in files.items())
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rel=read(ROOT/ptr['manifest_path']);assert ptr['generation']==146
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';binding=read(gold/'binding.json')
assert binding['engine_root']==rel['code_root'] and binding['engine_files']==rel['files']
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'gold_binding':binding,'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.json','.py','.yaml')}})
criteria={'authorization':'일단 이건 메인에 반영해보자 그리고 실제 우리 질문 몇개 선별해서 감시가 잘 작동하는지 확인해보자',
 'scope':'Exactly ADR1399 tested530 files to local MAIN147 and Gold engine binding; then three registered risk_cm question-only cases via actual selected root service. Parallel ADR1400 excluded.',
 'required':['Exact frozen530 bytes, existing640 executable SQL plans unchanged, common51 and lifecycle18 contracts before selection.','Prepared release service tests, actual default root service and Gold engine load after cutover; rollback on structural failure.','Fresh Qwen actual selected service on risk027, risk078, risk029 sequentially, no reference-answer injection, raw request/response and journal retention.','Inspect every reason-decision review, unchanged proposal cache, actual primary repair action and persistence; evaluate source-backed answer separately.'],
 'known_failures':['ADR1399 seeded ontology conflict missed','One-character diagnoses accepted','Natural EXCLUDED/used claim mismatch passed and persisted'],
 'limits':{'physical_total':120,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':3,'ram_start_gib':5,'ram_floor_gib':3,'swap_growth_mib':128,'workers':1},
 'stop':'UNKNOWN/remote5xx or resource violation stops all remaining external sends; no retry of a failed case. Known semantic failures preserved; independent next case may proceed.',
 'order':['RISK-CM-027','RISK-CM-078','RISK-CM-029'],'quality_certified':False,'rollback':ptr['manifest_path']}
put(DES/'criteria.json',criteria)
questions=read(ROOT/'01_DATA/GOLDEN/risk_cm/v1/questions.json');grant=read(tested/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
public=grant['public_document_ids'];assert len(public)==65
cases=[{'id':cid,'arms':['selected'],'document_ids':public,'steps':[{'number':1,'question':next(x['question'] for x in questions['cases'] if x['id']==cid),'mode':'외규'}]} for cid in criteria['order']]
put(DES/'live-cases.json',cases);put(DES/'source-scope.json',{'public':public,'internal':[]})
put(DES/'provider-policy.json',read(tested/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':'01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json','question_authorization_sha256':sha(ROOT/'01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json'),'documents':public,'scope':'Public document grant65 and exact original risk questions only; isolated experiment state, current validated source; no internal originals, labels or answer key in model input'})
shutil.copytree(origin/'transport',ART/'transport')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Selected service integrity; actual reason-decision mismatch detection and primary correction on three registered questions',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Preserve known semantic failures; no claim of full quality certification'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Historical MAIN146 only, not a new comparison' if a['id']=='baseline' else 'Exact completed1399 files to MAIN147; no product modifications',controls='Same stored source, default profile, budget and provider policy; labels excluded')
m['dataset'].update(name='Registered risk_cm question-only027078029; local cutover integrity',version='risk_cm-v1-existing-questions',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['selected'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'selected',list(files),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in files.items():
 p=can/'snapshot'/n
 if sha(p)!=h:shutil.copyfile(tested/n,p)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot';assert all(sha(C/n)==h for n,h in files.items())
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':files,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
spec=importlib.util.spec_from_file_location('pf',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);e,c,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':e,'files':c,'errors':errors})
def plans(root):return {k:{a:b for a,b in v.items() if a!='sources'} for k,v in runpy.run_path(str(root/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS'].items()}
assert plans(C)==plans(ROOT/rel['code_root']) and len(plans(C))==640
put(DES/'native-plan-equivalence.json',{'plans':640,'all_executable_plans_unchanged':True})
put(DES/'delta.json',{'changed':[n for n,h in files.items() if rel['files'].get(n)!=h],'removed':sorted(set(rel['files'])-set(files)),'working_untouched':True})
print('FROZEN530, engines',e,c,'public scope',len(public),'new models0')

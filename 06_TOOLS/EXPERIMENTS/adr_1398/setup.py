from common import *
import shutil,ast,importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/ptr['manifest_path'])
source=ROOT/'09_ARTIFACTS/AUDITS/20261105-multiturn-knowledge-lifecycle/checked-code'
source_pins=read(ROOT/'09_ARTIFACTS/AUDITS/20261105-multiturn-knowledge-lifecycle/checked-code-files.json')
files=list(release['files']);assert len(files)==528
assert all(sha(source/n)==source_pins[n] for n in files)
put(DES/'baseline.json',{'pointer':ptr,'release':release,'tested_source':str(source.relative_to(ROOT)),'tested_scope_result':read(ROOT/'09_ARTIFACTS/AUDITS/20261105-multiturn-knowledge-lifecycle/final-r4.json')['passed'],'working_files_not_restored':True})
put(DES/'source-code.json',{'files':{n:source_pins[n] for n in files},'reference':'Exact70-contract source; includes ontology final supervisor from1395 and lifecycle changes; concurrent common reason-review and authoring changes excluded'})
question='상법 제365조 제2항에서 연 2회 이상 결산기를 정한 회사는 언제 총회를 소집하나요?'
use_question='앞에서 축적한 정기총회 소집 시기 검토 묶음을 실제 근거 원문과 대조해 사용해서, 상법 제365조 제2항의 소집 시기를 다시 설명해 주세요.'
steps=[question,question,'그럼 임시총회는 언제 소집하나요?','상법 제369조 제1항에 따르면 주식 1주당 의결권은 몇 개인가요?','그럼 그 회사의 주식을 100주 보유한 경우에는 의결권이 몇 개인가요?','검토 다시 하기',use_question,use_question]
cases=[{'id':cid,'arms':['provider-matrix'],'document_ids':['7bbe815ff43b6635'],'steps':[{'number':i,'question':q,'mode':'외규'} for i,q in enumerate(steps,1)]} for cid in ('reka','deepinfra')]
put(DES/'live-cases.json',cases)
criteria=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1397-multiturn-knowledge-lifecycle-qwen/artifacts/design/criteria.json')
criteria.update(authorization='다시 확인해봐 제공자 달리해봐',hypothesis='With unchanged lifecycle code and a fixed validated successful prefix, another Qwen provider may complete the implicit followup and subsequent native lifecycle stages.',new_actual_Qwen_first_turn=False,replayed_provider_responses=5,independent_cells=['reka','deepinfra'],provider_order=['reka','deepinfra'],provider_precision={'reka':'fp8','deepinfra':'bf16'},replay_is_fixture_not_new_provider_inference=True)
criteria['success'][0]='T1 reconstructs the successful1397 first turn through exactly5 saved responses; original schema/source/ACL validation still executes. T2 must be model-free with same substantive answer. Neither is fresh provider inference.'
criteria['failure'][0]='UNKNOWN or remote5xx quarantines that provider/session with no further external sends for that cell. The other predeclared provider may run independently with a new session and the same fixed prefix. Resource stops abort the matrix. No resend of1397 UNKNOWN, no fallback or same-provider retry.'
criteria['limits']['physical_total']=80
criteria['comparison_limit']='One cell each, DeepInfra precision differs. Do not claim pure provider causality, stable capacity, or speed gains from the saved prefix.'
put(DES/'criteria.json',criteria)
source_design=ROOT/'04_EXPERIMENTS/ADR/ADR-1394-main146-multiturn-audit/artifacts/design'
put(DES/'source-scope.json',read(source_design/'source-scope.json'))
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1397-multiturn-knowledge-lifecycle-qwen/artifacts'
put(DES/'prefix.json',{'origin':str((parent/'public-live/conversation-verified-lifecycle').relative_to(ROOT)), 'responses':{str(i):sha(parent/f'public-live/conversation-verified-lifecycle/raw/call-{i:03}/response.json.gz') for i in range(1,6)},'unknown_replayed':False,'physical_calls':0})
endpoints=read(ART/'provider-endpoints.json')['data']['endpoints']
for cid,tag,name,precision in [('reka','reka/fp8','Reka','fp8'),('deepinfra','deepinfra/bf16','DeepInfra','bf16')]:
 assert any(e.get('tag')==tag and e.get('provider_name')==name and e.get('status')==0 for e in endpoints),(cid,[(e.get('tag'),e.get('provider_name')) for e in endpoints])
 policy={'schema_version':'qwen38-provider-routing-v1','model':'qwen/qwen3.8-27b','providers':[{'tag':tag,'name':name}],'switch_http_status':[429],'max_provider_switches':1,'model_fallback':False,'quantizations':[precision],'reasoning':{'effort':'none'},'authorization':{'source':'user_message','text':criteria['authorization'],'session_id':read(ADR/'실험/manifest.json')['reservation']['session_id']},'reason':'User-authorized independent alternate-provider cell. Single provider only, no fallback.','metadata':{'path':str((ART/'provider-endpoints.json').relative_to(ROOT)),'sha256':sha(ART/'provider-endpoints.json')}}
 put(DES/('provider-'+cid+'.json'),policy)
auth=read(source_design/'authorization.json');auth.update(user_request=criteria['authorization'],cases_sha256=sha(DES/'live-cases.json'),scope='This isolated frozen experiment; includes public first judgment, derived originals and explicit counterclaim, no operational publication')
put(DES/'authorization.json',auth)
shutil.copytree(parent/'transport',ART/'transport')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Alternate providers on unchanged1397 lifecycle source; each receives exactly5 successful saved prefix responses followed by fresh actual native followup inference'
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual goal/fact/source continuity and exact later-claim knowledge use/revalidation; report completion prefix separately',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Historical1397 Parasail result only' if a['id']=='baseline' else 'Exact tested lifecycle code, database ontology enabled with an initially empty isolated work repository',controls='Same public source/code/prefix/schema; fixed Reka FP8 or DeepInfra BF16/none, default validators. Single-provider cells, no MAIN changes.')
m['runs'][0].update(arm_ids=['provider-matrix'],selection_rule='Two independent sequential provider cells; each reconstructs saved first turn, then actual T3 onward. Unknown stops only that provider. No same-provider retry.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='Public Commercial Act alternate-provider followup probe',version='ADR1398-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','provider-matrix')};m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'provider-matrix',files,experiment_id=m['experiment_id'],arm_id='provider-matrix',run_ids=['run-001'])
for n in files:shutil.copyfile(source/n,can/'snapshot'/n)
assert all(sha(can/'snapshot'/n)==source_pins[n] for n in files)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
v=read(can/'candidate.json');rev=v['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in files},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-repaired.json',desc)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='provider-matrix',experiment_id=m['experiment_id'],arm_id='provider-matrix',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'live_public.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'live_public.py'))]);put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='freeze-public.json'},'before_model_calls':True})
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
print('Frozen',len(files),'files;',engines,count,'engine checks; no model calls')

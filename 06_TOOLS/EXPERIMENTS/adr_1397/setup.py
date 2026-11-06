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
cases=[{'id':'conversation','arms':['verified-lifecycle'],'document_ids':['7bbe815ff43b6635'],'steps':[{'number':i,'question':q,'mode':'외규'} for i,q in enumerate(steps,1)]}]
put(DES/'live-cases.json',cases)
criteria={'authorization':'ㅅqwen으로 실험해봐','hypothesis':'The exact tested lifecycle source can retain multi-turn goals/facts/current originals, accumulate grounded judgments, use an approved path in a later actual answer, and reassess after authority changes.',
 'success':['T1 real fresh Qwen source-supported answer; T2 same text/newID preserves goal/revision/answer, physical0. Same requestID has zero extra sends.','T3 implicit extraordinary meeting question retains appropriate existing goal and answers current originals; T4 voting question starts distinct goal; T5 100-share condition retains voting purpose and updates only current facts and necessary judgments.','T6 bound review targets the immediately preceding state. A completed answer need not produce another model judgment.','From the actual immutable T1 route, WIKI_PROPOSE/NORMALIZE/SOURCE_ANALYSIS/WIKI_SELECT/WIKI_PROJECT must compile a grounded draft without dropping selected statements, injecting an answer key or approving raw observations. Isolated host review can approve only after original-grounding/content review.','T7 must explicitly record package/path/nodes/claim use and quote the actual current originals; transmission is not use.','A predeclared counterclaim is compared by actual Qwen, with conflict draft/history retained and old active publication preserved. T8 is executed only if T7 actually used that publication; withdrawal must reopen same goal at ASSESS with old usage removed and valid originals retained.'],
 'failure':['After UNKNOWN/remote5xx or resource stop: no more external sends, no retry/replay of original UNKNOWNs. After HTTP failure dependent turns are not started.','If construction/approval/use fails, record exact failed proposal and unexecuted downstream phases; do not seed a prior answer or force a model action/state/claim.'],
 'limits':{'physical_total':200,'physical_per_native_request':40,'authoring_same_existing_stage_repair_budget':True,'single_physical_seconds':180,'rss_gib':5,'available_ram_start_gib':5,'available_ram_floor_gib':3,'swap_growth_mib':1024,'heavy_workers':1},
 'scripted_counterclaim':'상법 제365조 제2항은 연 2회 이상 결산기를 정한 회사도 정기총회를 2년에 한 번만 소집하면 된다고 정한다.',
 'counterclaim_is_scripted_not_an_actual_Qwen_error':True,'new_actual_Qwen_first_turn':True,'replayed_provider_responses':0,'automatic_MAIN_promotion':False,'experimental_publication_only':True,'minimum_completed_prefix_required_before_authoring':6}
put(DES/'criteria.json',criteria)
source_design=ROOT/'04_EXPERIMENTS/ADR/ADR-1394-main146-multiturn-audit/artifacts/design'
for n in ('source-scope','provider-policy'):
 put(DES/(n+'.json'),read(source_design/(n+'.json')))
auth=read(source_design/'authorization.json');auth.update(user_request=criteria['authorization'],cases_sha256=sha(DES/'live-cases.json'),scope='This isolated frozen experiment; includes public first judgment, derived originals and explicit counterclaim, no operational publication')
put(DES/'authorization.json',auth)
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1396-completed-repeat-redisplay/artifacts/transport',ART/'transport')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Fresh actual Qwen on the same70-contract lifecycle implementation; no response replay and no concurrent common-review implementation inclusion'
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual goal/fact/source continuity and exact later-claim knowledge use/revalidation; report completion prefix separately',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Historical1396 reference only' if a['id']=='baseline' else 'Exact tested lifecycle code, database ontology enabled with an initially empty isolated work repository',controls='Same selected public law source, configured Qwen FP8/none, default original/legal/ACL/budget validators. No active MAIN change.')
m['runs'][0].update(arm_ids=['verified-lifecycle'],selection_rule='One prospectively declared native conversation followed by dependent actual construction/reuse/conflict/withdrawal; no extra retries after failures',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='Public Commercial Act multi-turn/lifecycle actual Qwen probe',version='ADR1397-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','verified-lifecycle')};m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'verified-lifecycle',files,experiment_id=m['experiment_id'],arm_id='verified-lifecycle',run_ids=['run-001'])
for n in files:shutil.copyfile(source/n,can/'snapshot'/n)
assert all(sha(can/'snapshot'/n)==source_pins[n] for n in files)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
v=read(can/'candidate.json');rev=v['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in files},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-repaired.json',desc)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='verified-lifecycle',experiment_id=m['experiment_id'],arm_id='verified-lifecycle',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'live_public.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'live_public.py'))]);put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='freeze-public.json'},'before_model_calls':True})
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
print('Frozen',len(files),'files;',engines,count,'engine checks; no model calls')

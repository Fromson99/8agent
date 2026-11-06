from common import *
import shutil, importlib.util
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==152
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==532 and all(sha(C/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
questions=[
 '정기총회는 언제 소집하나요?',
 '연 2회 이상 결산기를 정한 회사는 언제 총회를 소집하나요?',
 '앞에서 본 범위에 한정하지 말고 상법 제365조 전체를 확인해서, 연 2회 이상 결산기를 정한 회사의 소집 시기를 다시 설명해줘.'
]
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
case={'id':'photo-conversation','arms':['selected'],'document_ids':public,'steps':[
 {'number':i,'question':q,'mode':'외규','purpose':'Photo exact wording' if i<=2 else 'Prospectively declared explicit scope expansion; separate diagnostic, cannot rescue turn2 grade'}
 for i,q in enumerate(questions,1)]}
put(DES/'live-cases.json',[case])
criteria={
 'authorization':'지금 여기서 멀티턴으로 테스트해볼래?',
 'hypothesis':'Current MAIN152 preserves the conversation while updating the follow-up purpose and acquiring/delivering the relevant original, without being trapped in a previous narrower reading.',
 'scope':'One fresh local actual root-service conversation, exact photo first2 questions and one predeclared explicit whole-article followup; public financial sources, no reference answer in product input.',
 'success':['Turn1 and turn2 finish with source-grounded answers to their current questions; turn2 preserves the appropriate goal and does not repeat only the old annual meeting rule.',
 'Observe actual method/task/issues/search_scope, navigation actions, acquired original spans and exact outbound final originals. Distinguish scope exclusion, premature finish, absent delivery, and model misreading.',
 'Turn3 explicitly requests whole Article365 in the same conversation; evaluate separately and never count its success as turn2 success.',
 'Source/ACL/wire mismatches0; physical calls equal reserved budget; same requestID duplicate adds0 model calls and preserves answer.'],
 'failure':['After UNKNOWN/remote5xx, source/ACL/code violation, resource stop, or non200: stop dependent turns; no replay or retry.','Missing/incorrect answer, wrong locator, user-directed source retrieval, or stale purpose/scope is recorded as failure, even if HTTP200.'],
 'limits':{'physical_total':120,'physical_per_request':40,'per_physical_seconds':180,'reported_cost_usd':2,'ram_start_gib':5,'ram_floor_gib':3,'rss_gib':5,'swap_growth_mib':128,'heavy_workers':1},
 'order':[1,2,3],'response_replay':False,'baseline_rerun':False,'automatic_promotion':False,'quality_certified':False,
 'resource_coordination':'Wait for already running ADR1412 batch and heavy worker to exit; do not interrupt or modify that run.'}
put(DES/'criteria.json',criteria)
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'photo_questions':questions[:2],
 'third_turn':'Predeclared diagnostic request authored here; reveals target scope, not an answer key.',
 'question_authorization_path':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json',
 'question_authorization_sha256':sha(ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'),
 'current_user_request_selects_photo_sequence':True,'risk_cm_selected':False,'documents':public,
 'scope':'Exact current user public-law question and diagnostic followup, public grant intersected with actual financial team. No internal sources or grading answers exported.'})
put(DES/'grading-only.json',{'product_input_forbidden':True,'source_generation':rel['data_path'],
 'document_id':'7bbe815ff43b6635','turn1':{'coordinate':'제365조 제1항','block_id':'1389','expected':'매년 1회 일정한 시기'},
 'turn2':{'coordinate':'제365조 제2항','block_id':'1390','expected':'연 2회 이상의 결산기를 정한 회사는 매기에 총회를 소집한다.'},
 'turn3':{'coordinate':'제365조 제2항','block_id':'1390','same_target_as_turn2':True}})
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport'
shutil.copytree(origin,ART/'transport')
pins=read(ART/'transport/transport-pins.json')
assert all(sha(ART/'transport'/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Two-turn exact photo reproduction: actual current purpose, scope, evidence delivery and source-grounded answer; explicit scope diagnostic separate',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','selected')}
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
for arm in m['design']['arms']:arm.update(changes='Historical1411 reference only, not rerun' if arm['id']=='baseline' else 'Current selected MAIN152 unchanged532, fresh3-turn declared sequence',controls='Same selected code/data/default profile, existing provider policy and public financial scope. One session, distinct request IDs, no forced decisions.')
m['runs'][0].update(arm_ids=['selected'],selection_rule='Fixed3-turn prefix; stop after UNKNOWN or non200; no repeated attempts',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='User photo Commercial Act multi-turn sequence',version='ADR1413-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=True)
qfile=ADR/'실험/질문-001-photo-conversation.md'
sections=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
values=['MAIN152 actual root service, Qwen3.8 FP8/none, fresh conversation; no response replay.', '\n\n'.join(f'{i}. {q}' for i,q in enumerate(questions,1)), 'artifacts/design/grading-only.json은 결과 대조 전용이다. 제품 모델에는 넣지 않는다.','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz와 source-wire-audit.json. 각 턴 원문·상태·전송 기록도 별도 보존.','artifacts/public-live/photo-conversation-selected/raw와 canonical의 정확한 원문을 참조.','generations.json, calls.json, authorized-derivations.json과 runtime 원장.','추가 judge 모델0, 로컬 원문·실제 답변·저장 기록 직접 대조.','실행 전 동결.']
qfile.write_text('# photo-conversation\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(sections,values),1))+'\n')
m['questions']=[{'number':1,'case_id':'photo-conversation','file':qfile.name,'sha256':sha(qfile)}]
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'selected',list(files),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in files.items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(C/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
desc={'code_root':str((can/'revisions'/rev['revision_id']/'snapshot').relative_to(ROOT)),'selected_files':files,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*DES.glob('*.json'),*[p for p in (ART/'transport').rglob('*') if p.is_file()]]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'before_model_calls':True})
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
print('Frozen MAIN152/532, three declared turns, physical120/cost2 upper bounds; model0')

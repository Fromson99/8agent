from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1401-common-review-main147-risk-qwen'
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==150
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==530 and all(sha(C/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
criteria={'authorization':'기존 cm질문으로 Qwen 실제 시험; 설명 먼저 마지막에 불확실성과 되묻기; 나머지 변경 금지','scope':'MAIN150 identical backend with final display only: found originals first, uncertainty and specific missing facts last. Registered CM012 then003, one independent actual Qwen run each. No main promotion.',
 'required':['Exact selected530 and source hashes throughout run','No action substitution or inaccessible required target caused by focused menu','When final answer has verified originals, source content precedes uncertainty; sealed missing user facts asked once; no internal review duplicate lists. If run stops before final response, live display success is not claimed','Original spans and authorization match actual wire, request budget matches physical calls, duplicate ID sends zero'],
 'limits':{'physical_total':80,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':2,'ram_start_gib':5,'ram_floor_gib':3,'swap_growth_mib':128,'workers':1},
 'stop':'UNKNOWN or remote5xx or resource violation stops remaining sends; no same-case automatic retries. Deterministic semantic failure may be followed by next independent case.',
 'order':['cm-012','cm-003'],'quality_certified':False,'in_sample':True}
put(DES/'criteria.json',criteria)
questions=read(ROOT/'01_DATA/review/cm_core_e2e_v3.json')
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
cases=[{'id':cid,'arms':['explanation'],'document_ids':public,'steps':[{'number':1,'question':next(x['question'] for x in questions['cases'] if x['id']==cid),'mode':'외규'}]} for cid in criteria['order']]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from_policy=None
from lawrag.core.question_execution_policy import require_local
for case in cases:require_local(ROOT,case)
put(DES/'current-question-policy.json',read(ROOT/'00_SYSTEM/QUESTION_EXECUTION_POLICY.json'))
put(DES/'live-cases.json',cases);put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','question_authorization_sha256':sha(ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'),'documents':public,'scope':'Registered question-only strings, existing public grant intersected with current financial team; no internal or answer key export'})
shutil.copytree(origin/'artifacts/transport',ART/'transport')
tpins=read(ART/'transport/transport-pins.json')
tpins['modules']['lawrag.core.question_execution_policy']='02_BACKEND/lawrag/core/question_execution_policy.py'
for n in tpins['modules'].values():
 target=ART/'transport'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,target);tpins['files'][n]=sha(target)
put(ART/'transport/transport-pins.json',tpins)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Actual execution/goal coherence and source-backed answer completion',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'explanation':stages}
for arm in m['design']['arms']:arm.update(changes='Completed1405 unchanged530; baseline not rerun',controls='Same default profile, source generation and grant; independent requests')
m['dataset'].update(name='existing CM012003 question-only input',version='existing-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['explanation'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['questions']=[]
for i,c in enumerate(cases,1):
 p=ADR/'실험'/f"질문-{i:03d}-{c['id']}.md"
 p.write_text(f"# {c['id']}\n\n## 1. 실행 메타\n\nMAIN150 동일530, actual root service, 기본 Qwen3.8 Parasail/none, 출력상한 없음.\n\n## 2. 사용자 질문 원문\n\n{c['steps'][0]['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n기존 CM 등록 기준답변은 제품 입력에서 제외. 현재 등록 원문과 실제 답변을 대조한다.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz와 source-wire-audit.json 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c['id']}-selected/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json와 물리 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n추가 채점 모델0. 실제 원문·행동·저장 기록 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 m['questions'].append({'number':i,'case_id':c['id'],'file':p.name,'sha256':sha(p)})
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'explanation',list(files),experiment_id=m['experiment_id'],arm_id='explanation',run_ids=['run-001'])
for n,h in files.items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(C/n,can/'snapshot'/n)
display='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
assert display in files
shutil.copyfile(ROOT/display,can/'snapshot'/display)
changed=[n for n,h in files.items() if sha(can/'snapshot'/n)!=h]
assert changed==[display],changed
put(DES/'changes.json',{'changed_files':changed,'backend_unchanged':True,'main_promoted':False})
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
desc={'code_root':str((can/'revisions'/rev['revision_id']/'snapshot').relative_to(ROOT)),'selected_files':{n:sha(can/'snapshot'/n) for n in files},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='explanation',experiment_id=m['experiment_id'],arm_id='explanation',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in [*Path(__file__).parent.glob('*.py'),*DES.glob('*.json'),*[p for p in (ART/'transport').rglob('*') if p.is_file()]]},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256']})
print('Frozen MAIN150 backend + one display file; CM012003 only; new model0')

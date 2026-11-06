from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1401-common-review-main147-risk-qwen'
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==152
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==532 and all(sha(C/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
criteria={'authorization':'현재 메인으로 통테 질문 돌려봐봐','scope':'Current MAIN152 actual root service, R5 external integration30 unique questions once each;50 answer rows mapped, UI10 not represented as executed. No product changes.',
 'required':['Selected532/source/code unchanged','Question answer matches frozen registered source and expected scope; questions/partial/source-only not counted as full answers','Source spans/ACL/wire integrity, physical calls equal budget, duplicate request adds0 calls'],
 'limits':{'physical_total':1200,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':10,'ram_start_gib':5,'ram_floor_gib':3,'swap_growth_mib':128,'workers':1},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, source/ACL/code/resource violation or total budget stop batch.',
 'quality_certified':False,'in_sample':True}
source_path=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261105-integration-external-r5/작성데이터.json'
table=read(source_path);unique={};rows=[];grades=[]
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
for group,items in table.items():
 for n,item in enumerate(items,1):
  rid=f'B{int(group):02d}-{n:02d}';row={'row_id':rid,'kind':item['kind'],'question':item.get('question')}
  if item['kind']=='search':
   q=item['question']
   if q not in unique:
    unique[q]={'id':rid,'arms':['selected'],'document_ids':public,'steps':[{'number':1,'question':q,'mode':'외규'}]}
    grades.append({'id':rid,'expected':item['expected'],'anchors':item['anchors'],'title':item['title']})
   row['case_id']=unique[q]['id']
  rows.append(row)
cases=list(unique.values());assert len(cases)==30 and sum(r['kind']=='search' for r in rows)==50
criteria['order']=[c['id'] for c in cases]
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'row-mapping.json',rows)
put(DES/'question-source.json',{'path':str(source_path.relative_to(ROOT)),'sha256':sha(source_path),'user_request':criteria['authorization'],'question_policy':'Latest explicit integration-test request selects R5 external questions. No risk_cm105 selected. All supplied source IDs must lie within existing public grant and actual financial team.'})
put(DES/'live-cases.json',cases);put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(source_path.relative_to(ROOT)),'question_authorization_sha256':sha(source_path),'documents':public,'scope':'Registered question-only strings, existing public grant intersected with current financial team; no internal or answer key export'})
transport=ART/'transport';transport.mkdir()
pins=read(origin/'artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Actual execution/goal coherence and source-backed answer completion',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'selected':stages}
for arm in m['design']['arms']:arm.update(changes='Selected MAIN152 unchanged532; baseline not rerun',controls='Same default profile, source generation and grant; independent requests')
m['dataset'].update(name='R5 external integration30 unique question strings',version='existing-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['selected'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['questions']=[]
for i,c in enumerate(cases,1):
 p=ADR/'실험'/f"질문-{i:03d}-{c['id']}.md"
 p.write_text(f"# {c['id']}\n\n## 1. 실행 메타\n\nMAIN152 동일532, actual root service, 기본 Qwen3.8 Parasail/none, 출력상한 없음.\n\n## 2. 사용자 질문 원문\n\n{c['steps'][0]['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\nR5 기대답변은 제품 입력에서 제외. 현재 등록 원문과 실제 답변을 대조한다.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz와 source-wire-audit.json 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c['id']}-selected/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json와 물리 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n추가 채점 모델0. 실제 원문·행동·저장 기록 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 m['questions'].append({'number':i,'case_id':c['id'],'file':p.name,'sha256':sha(p)})
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
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256']})
print('Frozen unchanged MAIN152/532, R5 question30, physical budget1200/cost10; model0')

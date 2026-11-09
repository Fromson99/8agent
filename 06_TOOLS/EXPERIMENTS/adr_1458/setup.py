"""Freeze MAIN177, nine financial CM question strings and criteria before any model call.

Subset chosen before any call from ADR-1424 (MAIN161) outcomes: eight NOT_READ questions
(required original never acquired) and one PASS control. Reference answers and evidence
coordinates go only to the grading-only file; product input is the registered question
string in the existing 외규 mode, exactly as ADR-1424.
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==177 and ptr['release_id']=='multiturn-followups-20261108-r1'
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==544 and all(sha(C/n)==h for n,h in files.items())
# Working-tree files that differ from MAIN177 because of other sessions' uncommitted edits.
# They are never swapped; live.py fails a request if one is loaded with different bytes.
parallel=['02_BACKEND/semantic_runtime/oracle_query_service.py','02_BACKEND/semantic_runtime/oracle_query_plans.py',
          '02_BACKEND/semantic_runtime/ontology_work/configuration.py']
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
qpath=ROOT/'01_DATA/review/cm_core_e2e_v3.json';rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json';apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'
auth=read(apath);assert any(f['path']=='01_DATA/review/cm_core_e2e_v3.json' and f['sha256']==sha(qpath) for f in auth['files'])
ORDER=['cm-007','cm-009','cm-016','cm-023','cm-030','cm-039','cm-041','cm-045','cm-040']
prior={r['case_id']:r for r in __import__('csv').DictReader((ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/CM51_결과.csv').open(encoding='utf-8-sig'))}
assert [prior[c]['failure_type'] or prior[c]['grade'] for c in ORDER]==['NOT_READ']*8+['PASS']
allq={q['id']:q for q in read(qpath)['cases']};questions=[allq[c] for c in ORDER]
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
assert all(registry[q['id']]['stage']=='ready' and 'local_execution_allowed' in registry[q['id']]['tags'] and 'financial' in registry[q['id']]['tags'] for q in questions)
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
criteria={'authorization':'2번하고 3번 4번 해보고 4번은 지금 20분내에 끝낼수 있게 몇개만 해봐',
 'scope':'Current MAIN177 actual root service, nine financial CM registered questions once each, run alone, 외규 mode, public grant intersected with the actual financial team (as ADR-1424). Reference answers and coordinates are grading-only. No product changes.',
 'subset_rule':'Chosen before any call from ADR-1424 outcomes: eight NOT_READ questions spread over topics (상장주선인 의무인수 2, 벤처 행사, 상장차익 증여의제, 증권신고서, 사내규정 결의기관, 상장회사 이사 수, 자기주식 소각) and one PASS control (cm-040 정관 변경 결의요건). Not a random sample; results are not a CM51 rate.',
 'required':['Selected544/source/code unchanged',
             'Primary: registered required articles acquired (law name + article on the current generation), compared per question with ADR-1424',
             'Secondary: answer matches the registered reference answer on the current stored original; questions back, partial or source-only replies are not full answers',
             'Source spans/ACL/wire integrity, physical calls equal budget, duplicate request adds0 calls'],
 'limits':{'physical_total':360,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':3,'time_box_minutes':18,'ram_start_gib':5,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'workers':1},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, source/ACL/code/resource violation, total budget or the 18-minute time box (checked before each next question) stop the batch. This session runs no tests, data loads or other model work while the batch runs.',
 'quality_certified':False,'in_sample':True,
 'prior_observation':'Known CM questions; ADR-1424 ran all 51 on MAIN161 (18 pass/5 partial/28 fail, 19 NOT_READ). The subset was chosen from those outcomes.'}
cases=[{'id':q['id'],'arms':['selected'],'document_ids':public,'steps':[{'number':1,'question':q['question'],'mode':'외규'}]} for q in questions]
assert all(c['steps'][0]['question']==registry[c['id']]['question'] for c in cases)
criteria['order']=ORDER
grades=[{'id':q['id'],'reference_answer':registry[q['id']]['reference_answer'],'as_of':registry[q['id']]['as_of'],'facets':registry[q['id']]['facets'],
         'main161':{k:prior[q['id']][k] for k in ('grade','failure_type','required_acquired','required_total','reason')},
         'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[q['id']]['targets']]} for q in questions]
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),'user_request':criteria['authorization'],'question_policy':'Local experiments use the financial cm51; risk_cm105 not selected. Question strings authorized for the external experiment model by CM_EXPORT_AUTHORIZATION_20261024.'})
put(DES/'live-cases.json',cases);put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':public,'scope':'Registered CM question strings only, existing public grant intersected with current financial team; reference answers and coordinates are never sent'})
transport=ART/'transport';transport.mkdir()
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered required articles acquired per question on the current generation, compared with ADR-1424 MAIN161',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution','A claim cites an unread connection target'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'selected':stages}
for arm in m['design']['arms']:
 if arm['id']=='baseline':arm.update(changes='Reference only: ADR-1424 MAIN161 outcomes for the same nine questions; not executed here',controls='Same question strings and grant')
 else:arm.update(changes='Selected MAIN177 unchanged544',controls='Same default profile, source generation and grant; independent requests')
m['dataset'].update(name='financial CM nine-question subset',version='cm-field-core-e2e-v3',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['selected'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for q,c in zip(m['questions'],cases):
 assert q['case_id']==c['id']
 p=ADR/'실험'/q['file']
 p.write_text(f"# {c['id']}\n\n## 1. 실행 메타\n\nMAIN177 동일544, actual root service, 기본 Qwen3.8 Parasail/none, 출력상한 없음, 외규 모드.\n\n## 2. 사용자 질문 원문\n\n{c['steps'][0]['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n등록 기준답변·근거 좌표는 design/grading-only.json에만 있고 제품 입력에서 제외. 현재 저장 원문과 실제 답변을 대조한다.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/{c['id']}-selected 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c['id']}-selected/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json와 물리 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n추가 채점 모델0. 실제 원문·행동·저장 기록 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'selected',list(files),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in files.items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(C/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot';assert all(sha(snapshot/n)==h for n,h in files.items())
desc={'code_root':str(snapshot.relative_to(ROOT)),'selected_files':files,'parallel_excluded':parallel,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-issues.json',[])
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','candidate-selected.json','grading-only.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('Frozen unchanged MAIN177/544, financial CM 9 questions, physical budget360/cost3/time box18min; model0')

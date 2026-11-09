"""Freeze MAIN161, the R5 external question30 set and criteria before any model call.

Baseline (MAIN152, ADR-1412) is a prior observation only; it is not re-executed here.
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==161 and ptr['release_id']=='unread-notes-20261106-r1'
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==533 and all(sha(C/n)==h for n,h in files.items())
parallel=read(ROOT/'09_ARTIFACTS/AUDITS/20261106-unread-notes-main161/excluded-parallel.json')['working_tree_differs_from_main160_but_excluded']
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen'
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
criteria={'authorization':'진행해봐 (직전 제안: MAIN161로 R5 30문항 재실행 — 법률명 거절7건 해소·같은 절 읽기/미확인 안내 일반화·새 회귀 확인); ADR-1422 자원 중단 뒤 같은 지시로 새 ADR',
 'scope':'Current MAIN161 actual root service, R5 external integration30 unique questions once each (R2 after ADR-1422 resource stop; B03-03 included again as a new independent request); 50 answer rows mapped, UI10 not represented as executed. No product changes. Baseline is ADR-1412 MAIN152 (same question30, same source generation), not re-executed.',
 'required':['Selected533/source/code unchanged',
             'Question answer matches frozen registered source and expected scope; questions/partial/source-only not counted as full answers',
             'Source spans/ACL/wire integrity, physical calls equal budget, duplicate request adds0 calls'],
 'secondary':['The seven ADR-1412 presentation-name rejections (B03-06/08/10/12/14/15/28) are re-observed: pass, other failure, or same rejection',
              'Same-section automatic reads and unread-connection notes/cards: count, origin/target/reason present, original shown only as not-evidence, no claim cites an unread target',
              'Per-question pass/fail change versus ADR-1412 (not causal: single run, model stochasticity)'],
 'limits':{'physical_total':1200,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':10,'ram_start_gib':5,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'load_swap_growth_mib':512,'workers':1},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, source/ACL/code/resource violation or total budget stop batch. This session runs no tests, data loads or other model work while the batch runs; the host is shared with other sessions, which the floors measure but this experiment does not control.',
 'quality_certified':False,'in_sample':True,
 'guard_change':'ADR-1422 stopped on B03-03 at host swap growth 153MiB (all 5 calls HTTP200, answer assembly in progress, worker RSS 3.08GiB vs ADR-1412 peak 2.91GiB, available 8.4GiB, other agent sessions active). R2 measures 128MiB on this worker VmSwap, host swap growth 512MiB, keeps RAM 3GiB / free-swap 1GiB floors. Frozen before the first R2 call.','prior_observation':'ADR-1412 MAIN152: 23/30 pass, 7 rejected by the removed answer-name check, 150 physical, UNKNOWN0, reported 0.1866168 USD, median 46.274s/p95 86.386s.'}
source_path=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261105-integration-external-r5/작성데이터.json'
assert sha(source_path)==read(prior/'artifacts/design/question-source.json')['sha256']
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
assert criteria['order']==read(prior/'artifacts/design/criteria.json')['order']
assert [c['steps'] for c in cases]==[c['steps'] for c in read(prior/'artifacts/design/live-cases.json')],'same question strings as ADR-1412'
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'row-mapping.json',rows)
put(DES/'question-source.json',{'path':str(source_path.relative_to(ROOT)),'sha256':sha(source_path),'user_request':criteria['authorization'],'question_policy':'Same R5 external question30 as ADR-1412. No risk_cm105 selected. Source IDs intersect the existing public grant and the actual financial team.'})
put(DES/'live-cases.json',cases);put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(source_path.relative_to(ROOT)),'question_authorization_sha256':sha(source_path),'documents':public,'scope':'Registered question-only strings, existing public grant intersected with current financial team; no internal or answer key export'})
transport=ART/'transport';transport.mkdir()
pins=read(prior/'artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered expected-content/source match per unique question',success_criteria=[*criteria['required'],*criteria['secondary']],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution','A claim cites an unread connection target'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'selected':stages}
for arm in m['design']['arms']:
 if arm['id']=='baseline':arm.update(changes='Reference only: ADR-1412 MAIN152 run, not executed here',controls='Same question strings, source generation and grant')
 else:arm.update(changes='Selected MAIN161 unchanged533; MAIN152->161 cumulative changes',controls='Same default profile, source generation and grant; independent requests')
m['dataset'].update(name='R5 external integration30 unique question strings',version='existing-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['selected'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for q,c in zip(m['questions'],cases):
 assert q['case_id']==c['id']
 p=ADR/'실험'/q['file']
 p.write_text(f"# {c['id']}\n\n## 1. 실행 메타\n\nMAIN161 동일533, actual root service, 기본 Qwen3.8 Parasail/none, 출력상한 없음.\n\n## 2. 사용자 질문 원문\n\n{c['steps'][0]['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\nR5 기대답변은 제품 입력에서 제외. 현재 등록 원문과 실제 답변을 대조한다.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz와 source-wire-audit.json 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c['id']}-selected/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json와 물리 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n추가 채점 모델0. 실제 원문·행동·저장 기록 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
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
print('Frozen unchanged MAIN161/533, R5 question30 (same as ADR-1412), physical budget1200/cost10; model0')

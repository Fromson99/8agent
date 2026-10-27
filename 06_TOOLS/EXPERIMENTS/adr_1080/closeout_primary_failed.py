"""Preserve invalid fixture failure and unexecuted secondary; no criterion edit."""
from common import *
from datetime import datetime, timezone
import re
import subprocess

out = ADR/'artifacts/run-001'
failure = read(out/'sql-first-failure.json')
freeze = read(DESIGN/'freeze.json')
assert failure['paired_cases'] == 1346
assert failure['first_failed_pair']['case']['id'] == 'source_boundary/0002'
assert all(failure['first_failed_pair'][arm]['error_type'] == 'IntegrityError' for arm in ('baseline','optimized'))
assert all(sha(ROOT/p) == h for p,h in freeze['files'].items())
assert not (ADR/'artifacts/run-002').exists()
summary = {'schema_version':'adr1080-primary-fixture-failed-v1','strict_success':False,
    'checks':{'whole1582paired_contract_complete':False,'first1345pairs_equivalent':True,
        'failed_pair_has_valid_fixture':False,'frozen_inputs_unchanged':True,'native_not_started':True},
    'status':'FAILED','reason':'source_boundary/0002 fixture duplicates a non-NULL (source_id,reference_id) composite primary key before Selection.bind in both arms.',
    'completed_equivalent_pairs':1345,'failed_fixture_pairs':1,'unstarted_pairs':236,
    'new_model_calls':0,'real_corpus_loads':0,'native_runs':0,'main_promotable':False,
    'raw_failure':bound(out/'sql-first-failure.json'),'raw_stream':bound(out/'sql-pairs.jsonl.gz'),
    'runner_failure':bound(out/'FAILED.json'),'criteria_unchanged':True,
    'scope':'Partial successes are observed support only. No whole completed arm or timing comparison claimed.'}
put(out/'result.json',summary)
put(ADR/'artifacts/run-002/result.json',{'strict_success':False,'status':'NOT_RUN',
    'checks':{'native_execution_permitted':False,'native_not_started':True},
    'reason':'Blocked by primary fixture integrity failure before any native request.',
    'new_model_calls':0,'real_corpus_loads':0,'recorded_responses_used':0})
m = read(ADR/'실험/manifest.json')
assert m['results']['status'] == 'not_run'
for run in m['runs']:
    run.update(status='failed',sha256=sha(ROOT/run['artifact_path']),success_criteria_met=False)
m['runs'][1]['execution_status'] = 'NOT_RUN_PRIMARY_GATE_FAILED'
m['decision_eligible'] = False
m['results'].update(status='failed',by_arm={arm:{'status':'failed','completed_equivalent_pairs':1345,
    'fixture_failure':'source_boundary/0002','native_status':'NOT_RUN','whole_qualification_complete':False}
    for arm in ('baseline','optimized')},comparisons=[{'pair':['baseline','optimized'],
    'completed_equivalent_pairs':1345,'invalid_fixture_pairs':1,'unstarted_pairs':236,
    'speed_improvement':None,'legal_accuracy':'NOT_MEASURED'}],
    usage={'new_product_model_calls':0,'new_evaluator_calls':0,'native_recorded_responses_used':0},
    latency={'partial_primary_wall_seconds':read(out/'FAILED.json')['wall_seconds'],'speed_claim':'NONE'},
    error_taxonomy=[{'kind':'HARNESS_FIXTURE_DUPLICATE_PRIMARY_KEY','run':'run-001','case':'source_boundary/0002',
        'product_bind_started_for_failed_case':False,'both_arms_same_sqlite_integrity_error':True}],
    main_wiring='unchanged',main_promotable=False,quality_certified=False)
put(ADR/'실험/manifest.json',m,replace=True)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Rejected'),('decision_eligible','false'),('main_wiring','unchanged')]:
    meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
sections=[
('결정 요약','전체 qualification 실패, MAIN104 유지. 합성1345쌍은 동등했으나1346번째 fixture 생성에서 중단됐다.1582쌍 완주와 native38응답 재생은 미충족이다. 후보·기준·원시 실패를 수정하지 않으며 승격 자격이 없다.'),
('문제와 변경 전 구조','같은 확보 원문을 메뉴마다 반복 검증하는2모듈 준비 후보에,4TEMP 관계 VIEW의 전체 가시참조 ID 열거를 같은 권한 VIEW의 EXISTS 단건조회로 바꾸는1줄 SQL을 합쳤다. MAIN104 대비3제품파일+31pins,420파일이다. 이전1076/1078은 실패 참고이며 완료 부모는1075/observed다.'),
('가설과 사전 판정 기준','design/criteria.json,sql-matrix.json,secondary-replay.json을 실행 전에 동결했다.1582쌍의 결과·오류·순서·권한가시성·읽기전용 상태를 전수 비교하고 native38응답/35화면/답변이 일치해야 했다. 해당 기준은 실패 후 바꾸지 않았다.'),
('실험 설계','visibility1344, source_boundary192, insertion_order12, requested_failures18, point_plans16으로 설계했다. SQL 기준은 관측1078 후보, optimized는 같은 코드+SQL1줄이다. 신규 fixture마다 두 별도 모의DB를 생성한다. 기존 캐시1318/280검사는 관측 근거로만 명시했다.'),
('데이터·모델·재현성','공식 snapshot/register/freeze를 완료했다. 각 arm은 모의 SQLite만 사용하며 실데이터·네트워크·모델 호출0이다.9,232pins와실행전420파일을 확인했다. 원문/모델/profile/prompt/menu/data/예산 변경은 없다. 동결 freeze와 실패 원시는 그대로다.'),
('결과','visibility1344쌍과 source_boundary/0001은 동등했다. source_boundary/0002는 두 arm 모두 UNIQUE constraint failed: reference_end.source_id, reference_end.reference_id로 fixture 생성에 실패했다. 나머지236조건과 모든 native실행은 미실행이다. artifacts/run-001/result.json·sql-first-failure.json·sql-pairs.jsonl.gz·FAILED.json에 전체/부분 상태를 구분했다.'),
('사례별 오류 분석','missing-source를 같은 참조R10의3개 reference_end 행에 반복 넣어 composite PK를 위반했다. 해당 case는 제품 Selection.bind 전에 실패했다. NULL source 중복은 스키마가 허용하지만 비NULL source 중복은 허용하지 않는다. 제품 SQL 출력 불일치나 권한 회귀를 관찰한 결과는 아니다. fixture만 고쳐 실패를 성공으로 덮지 않는다.'),
('비용·지연·회수 규모','신규 모델·평가0, 실데이터0. 부분 합성 감사시간은 FAILED.json에 기록했다. native0회이므로 제품 지연·view개선율·회수 품질을 측정했다고 하지 않는다. 기존1076의 완료35view시간은 사전 참조로만 남는다.'),
('해석','1345개의 관측된 성공은 해당 유한 입력의 보조 근거다. 전체1582쌍 계약이나 원본native경로 완주로 바꾸지 않는다. 잘못된 fixture는 검증기 준비 결함이며 후보의 제품 실패라고 단정할 근거도 없다.'),
('한계와 일반화 가능 범위','실행하지 않은 source경계/오류/순서/plan조건과 native완주는 미확인이다. 법률 정답률·온톨로지효과·GENOS·모델속도는 측정하지 않았다. 조회하지 않은 전역 손상JSON 예외는 처음부터 동등성 범위밖이며 적재/게시/세대 검사의 책임으로 유지한다.'),
('운영 결정·롤백 조건','Rejected, decision_eligible=false, main_promotable=false다. MAIN104와 작업 제품코드를 유지했다. 후속1081은 완료1075를 부모로 하며 이 실패는 informed_by로만 연결한다. 제품420바이트는 유지하고 불법 fixture 중복18조건만 고친 뒤 전체fixture무결성을 먼저 확인한다. 관측1345쌍은 보조, 미실행237조건은 새 사전계약으로 구분한다.'),
('재현 명령','prepare.py→freeze.py→audit.py에서 실패했다. native_replay는 실행하지 않았다. 완료 실패를 덮어쓰지 않고 후속은 새ADR에 기록한다. stable adr_structure.py validate --final 및 graph를 확인하며 전역의 기존 오류와 구분한다.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# ADR1080 — 합성 fixture 무결성 실패\n\n'+ '\n\n'.join(f'## {i}. {name}\n\n{text}' for i,(name,text) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 부분 SQL 계약과 미실행 native\n\nrun001:1345쌍 동등, 다음 fixture PK 중복으로 실패. run002:native 미실행. 전체 승격 실패와 원시기록을 유지한다.\n')
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
paragraphs=['ADR1080 run002/optimized는 계획했지만 주계약 실패로 미실행이다. run001은 별도의 합성 SQL계약이다.',
 '외국금융회사 국내지점의 총자산이 사업연도 말 이전 6개월 중 7천억원을 초과한 사실이 있으나, 이후 총 자산이 7천억원 미만으로 유지되는 경우 준법감시인이 위험관리책임자를 겸직할 수 있는지',
 '새 법률 채점과 제품 입력이 없다. 완료1075답변은 재생 비교용으로만 사전 결속했다.',
 'design/secondary-inputs.json에원래질문·요청38개·응답·35화면·답변hash를결속했으나이번제품실행은없다.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n해당없음: native가미실행이라새회수/전달원장이없다. 원래1075이력을새실행으로세지않는다.',
 '신규제품모델0, 저장응답공급0. 원래system/user/schema/응답은secondary inventory로참조하며이ADR실제요청이아니다.',
 '신규router/compiler/verifier/repair 호출0. native미실행.',
 '신규judge0. 반복판정이나법률정답채점없음.',
 '미실행. 주계약1345쌍동등후다음fixturePK중복으로실패해native를차단했다. 원래실패와기준을보존하며MAIN104유지,승격자격없음.']
(ADR/'실험/질문-001-fsc-hard-005.md').write_text('# 질문001 — fsc-hard-005\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{p}' for i,(h,p) in enumerate(zip(headings,paragraphs),1))+'\n')
subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(ADR)],cwd=ROOT,check=True)
paths=[p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
paths+=list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1080').glob('*.py'))+[ROOT/'06_TOOLS/EXPERIMENTS/adr_1080/sql-matrix.json']
put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1080','created_at':m['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
 'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs and preserved invalid-fixture failure; native not run.','contains_raw_prompts_and_outputs':False} for p in sorted(paths)]},replace=True)
print('1080 failed primary preserved; native not run; final structure ready')

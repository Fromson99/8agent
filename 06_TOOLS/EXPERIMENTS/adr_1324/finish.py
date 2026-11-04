from common import *
import re,ast

a=read(ART/'contracts-recheck/result.json');b=read(ART/'baseline-fixture-check/result.json')
p=read(ART/'provider-wire/result.json');w=read(ART/'working-api/result.json')
i=read(ART/'working-integration.json');f=read(DES/'candidate-integrated.json')
assert (a['passed'],a['failed'],b['failed'],p['passed'],p['failed'],w['passed'],w['failed'])==(166,2,2,6,0,2,0)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer']
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-assessment-root-repair';OUT.mkdir(exist_ok=True)
summary={'status':'STRUCTURAL_FIX_IN_WORKING_CODE_ONLY','product_files_changed_this_task':3,'total_files_changed_this_task':35,
 'new_contracts_passed':58,'new_contracts_failed':0,'unique_contracts_passed':172,'existing_fixture_failures':2,
 'baseline_same_fixture_failures':2,'working_api_rechecks_passed':2,'working_rechecks_overlap':True,
 'candidate_api_cases':6,'live_models':0,'live_answer_quality_certified':False,
 'candidate_working_same_files':525,'selected_main':140,'selected_main_unchanged':True,
 'native_plans':read(DES/'native-plan-equivalence.json'),'engine':i['engine_preflight'],
 'earlier1322_fixes_preserved':True,'startup1323_preserved':True,'whole_test_list_pass_claim':False,
 'receipt_version':'assessment-review-links-v3-direct','legacy_readers':['assessment-review-links-v1','assessment-review-links-v2'],
 'field_deployment':False,'mail_sent':False,
 'known_limits':['Actual model may still make semantic mistakes or inconsistent cross-row judgments; not eliminated by schema.',
                 'External429/blank stream/UNKNOWN is not repaired by this change; existing stop/no-resend preserved.',
                 'MAIN140 still selects pre1322/pre1324 assessment code. Working integration is not service deployment.'],
 'preparation_failures':['First test collection import-name collision, no tests executed; preserved contracts-final/result.json.',
                         'Integration guard initially counted filenames absent from pytest node IDs and stopped before writes; counted exact test function identities, no product change.',
                         'Initial artifact collection included a report observer directory; corrected is_file filtering, no product or test result changes.']}
put(RUN/'result.json',summary);put(OUT/'검증요약.json',summary)
texts=[
'통테에서 어려운 질문을 빼는 작업과 별개로, 최종 답변을 막는 내부 구조를 수정했다. 모델이 작성하던 검토용 연결번호와 별도 연결표를 없애고 주장·근거를 각 판단에 직접 지정하게 했다. 명시된 동일 연결을 저장용으로 묶는 일은 서버가 맡는다. 작업 코드에 통합했으며 현재 선택 서비스 MAIN140와 현장 배포는 변경하지 않았다.',
'원인 1 — 생성 시 제약 손실: 기존 assessment_links는 USE/CONDITIONAL에 실제 claim_refs가 필요하다는 개수 제약을 link_ref 문자열의 설명으로 바꾸었다. 따라서 모델이 공유 연결에 빈 주장 배열을 쓰고 USE 행에서 참조하는 조합이 생성 스키마를 통과한 뒤 원래 스키마 복원에서 거절될 수 있었다. 앞선1322는 이 오류 위치와 수정 방향을 알려주는 보완이었다. 이번에는 별도 모델 연결표를 없애 원래 주장·근거 제약이 생성 단계에 그대로 남도록 했다.',
'원인 2 — 범위 상태의 허용 조합: scope_reviews의 USE/EXCLUDE/OPEN은 생성 스키마에서 같은 필드를 모두 허용했고 실제 검증 때만 상태별로 거절했다. USE는 주장 연결이 있고 gap이 없게, EXCLUDE는 주장·gap 연결을 비우게, OPEN은 주장 대신 미확인 gap을 연결하게 생성 계약을 맞췄다. 실제 제공자 직전의 고정값 생략·스키마 변환 뒤에도 제약이 유지되는지 확인했다. 스키마를 무시하는 모델 응답은 기존 방식대로 거절한다.',
'보존한 판단과 보안: 모델이 정한 상태·이유·주장·원문·미확인 gap을 임의 채택하거나 삭제하지 않았다. 같은 원문을 인용했다는 이유로 잠정 판단을 최종 답에 채택하지 않는다. 서로 다른 연결은 합치지 않으며 배열 순서까지 정확히 같은 관계만 저장용으로 재사용한다. 실제 claim 존재·자기 원문·범위별 누락/중복·원문/권한/해시·상태 revision·예산 검사는 계속 적용한다. v1/v2 저장 기록도 읽을 수 있다.',
'검증: 신규58개 모두 통과. 확대 검사까지 고유172개 통과, 기존 fixture2개 실패. 실패2개는 SimpleNamespace 저장소 대역에 check_unchanged 메서드가 없는 것으로, 수정 전 동일525파일 기준에서도 같은2개가 실패했다. 후보의 실제 로컬 API 경로를 모의 모델로6조건 실행했다: 정상, 범위 오류 보완, 반복 범위 오류 종료, need 오류 보완, 반복 need 오류 종료, OPEN 유지. 성공 결과 저장·재검증·동일 요청 재조회 추가 모델호출0을 확인했다. 작업 통합 뒤 실제 API2개를 다시 확인했으며172개에 중복 합산하지 않는다.',
'반영: 제품3파일(assessment_links/completion_execution/need_continuity)+Oracle 준비계획1+pin31=35파일 변경. 기존1322의 멀티턴 명령/후속 지침/검토 보완 수정과1323 기동 순서를 보존했다. 동결 후보와 작업525파일 SHA 동일, native639개 실행SQL/list/AST 동일, engine30/497파일 및 작업 prepare_oracle_queries --check 통과. 원복은 이 ADR artifacts/working-before에 이번35파일의 이전 바이트를 보존했다.',
'남은 부분: 새 실모델 호출0회이므로 실제 답변 품질·지연 개선, 전체60문항 통과, 멀티턴 완전 해결을 주장하지 않는다. 법률 의미 판단이나 서로 다른 검토 행 사이의 의미 충돌은 모델 재판단이 필요하다. 제공자429·공백 스트림·UNKNOWN의 외부 원인도 이번 수정으로 해결되지 않는다. 기존 중단·중복 전송 방지 정책을 유지했다. MAIN140에는 앞선1322 및 이번1324 수정이 아직 반영되지 않았다.',
'기록·호환: 새 저장 연결 영수증은 assessment-review-links-v3-direct다. 새 코드가 과거v1/v2를 읽는 것은 확인했으나, 옛 코드가 새v3 기록을 읽는다는 뜻은 아니다. 롤백 시 새 판본의 기록을 옛 reader에 강제로 전달하지 않는다. 실험 기록은 격리되어 있으며 현재 제품 기록 DB를 변경하지 않았다. 두 시험 runtime은 모든 파일SHA를 확인한 무손실 압축본과 복원 안내로 보존했다.',
'준비 실패 보존: 첫 검사는 과거/현재 test_scope_review 파일명의 import 충돌로 수집 단계에서 중단했다. 의도한 fixture의 절대 경로 및 importlib 수집으로 정정했고 후보 제품 코드는 바꾸지 않았다. 통합 전 검사도 pytest node ID에 파일명이 없어서 신규검사 집계 조건에서 한 번 중단했다. 실제 함수 이름으로 확인하도록 검사만 정정한 뒤 적용했다. 두 준비 실패 및 기존 fixture 실패 결과를 성공 결과로 덮어쓰지 않았다.'
]
(OUT/'근본원인_수정과_검증결과.txt').write_text('\n\n'.join(texts)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'new_models':0,'control_fixture_failures':2,'same_as_candidate':True},'integrated':summary},comparisons=[{'metric':'Preexisting fixture failure control','baseline_failed':2,'candidate_same_failed':2,'new_failures':0,'new_tests_passed':58}],judge_disagreements=0,usage={'physical_calls':0},latency={'candidate_contract_seconds':a['seconds'],'provider_wire_seconds':p['seconds'],'working_api_seconds':w['seconds'],'real_service_latency':'not_measured'},error_taxonomy=['Existing test double missing check_unchanged; not introduced'])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[texts[0],texts[1]+'\n\n'+texts[2],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),
 '완료1322/integrated 및1323/integrated를 합친 정확525파일에서 후보를 격리하고 rev001 동결. 신규 구조/저장/API 검사와 기존 관련 검사를 실행. 후보 제품수정 후속0. 수집 fixture 수정은 원 결과를 보존한 실행기 정정이다.',
 '합성 원문·주장·미확인 및 기존 검사 fixture. 실제 법률 정답지/외부모델0. candidate-integrated.json과 runner SHA로 실행을 고정했다.',
 json.dumps(summary,ensure_ascii=False),texts[8]+'\n\n'+texts[4],
 f'새 모델/비용0. 후보계약 {a["seconds"]:.3f}초, 제공자 스키마계약 {p["seconds"]:.3f}초, 작업 API 재검사 {w["seconds"]:.3f}초. 실제 서비스 속도 비교 아님. 실제 corpus 회수 없음.',
 texts[3],texts[6],texts[5]+'\n\n'+texts[7],
 '06_TOOLS/EXPERIMENTS/adr_1324/setup.py → 후보 3파일 수정 → freeze.py → check.py contracts-recheck/provider-wire/baseline-fixture-check → integrate.py → working-api → prepare_oracle_queries.py --check → archive_contracts.py → finish.py → adr_structure hash/status/validate --final/graph. PYTEST_ADDOPTS=--import-mode=importlib. 실행 시 보관 runtime은 receipt에 따라 별도 복원한다.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 최종 답변 검토 연결의 구조 수정\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(heads,values),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
    item=next(x for x in read(DES/'cases.json') if x['id']==q['case_id'])
    qv=['run-001 / integrated / isolated rev001. 합성 계약, 실제모델0.',json.dumps(item,ensure_ascii=False),
        '법률 정답 평가 아님. 정상/거절 상태, 명시된 claim/evidence/gap과 원래 판단 보존이 기준이다.',
        '### 회수·탈락 단계 원장 — run·arm별\n\n합성 fixture만 사용. 실제 corpus 회수 없음. stage_ledger not_applicable. 정확한 테스트 코드: 06_TOOLS/EXPERIMENTS/adr_1324/test_direct_links.py 및 contracts-recheck/result.json 각 test ID.',
        '새 제품 모델0. 모의 API 원장은 runtime-archives의 두 압축본과 전파일 해시 inventory로 복원 가능하다.',
        '새 중간 LLM0. 명시한 mock 응답을 현재 API 경로에 주입했다.',
        '채점 LLM0. 자동 검사 원본 contracts-recheck/result.json, provider-wire/result.json, baseline-fixture-check/result.json, working-api/result.json. 기존 실패는 보존.',json.dumps(summary,ensure_ascii=False)]
    (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(qh,qv),1))+'\n')
(ADR/'실험/README.md').write_text('# 구조 검사 범위\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts and 'runtime' not in p.parts]
paths += [p for p in Path(__file__).parent.glob('*.py')]+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1324','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code, full contract results, working integration, previous bytes and lossless runtime evidence','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print('172 unique passed;2 unchanged baseline fixture failures;58 new passed;working35 files;MAIN140 unchanged')

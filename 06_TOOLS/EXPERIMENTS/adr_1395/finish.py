from common import *
import shutil
tests=read(ART/'final-contracts/result.json')
post=read(ART/'checkout-native/result.json');integration=read(ART/'working-integration.json')
p=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
assert read(p)==integration['selected_main']
f=read(DES/'candidate-working.json');assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert tests['passed']==106 and tests['failed']==1
assert post['passed']==1 and post['exit_code']==0 and post['code_unchanged']
log=Path('/tmp/adr1395-selected-settings.log');assert '1 passed' in log.read_text() and 'FAILED' not in log.read_text()
shutil.copyfile(log,ART/'selected-settings.log')
measure=read(ART/'review-size.json')
summary={'status':'IMPLEMENTED_AND_CONTRACT_VERIFIED','product_changes':len(integration['products']),'total_working_changes':integration['changed_count'],
 'candidate_passed':tests['passed'],'candidate_snapshot_environment_failed':tests['failed'],'parent_same_failure':read(ART/'parent-settings-control/result.json')['failed'],
 'checkout_native_passed':post['passed'],'selected_root_settings_passed':1,
 'native_review_scenarios':read(ART/'native-r4/result.json')['passed'],'all528_working_matches_tested_integration':True,
 'preserved_concurrent':integration['preserved_concurrent'],'selected_main':integration['selected_main'],
 'native_execution_plans':integration['native_executable_count'],'engine':integration['engine'],
 'physical_model_calls':0,'semantic_quality_certified':False,'latency_measured':False,'review_size':measure['rows'],
 'limits':'One review per distinct valid ASSESS proposal, at most two proposals in the existing correction owner. Off/no catalog/no claims adds0. Identical review reuses its durable decision. Unknown cannot replay.'}
put(RUN/'result.json',summary)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'source':'1393/reviewed','same_environment_failure':1},'repaired':summary},
 judge_disagreements=0,usage={'physical_model_calls':0,'synthetic_only':True},latency={'real_latency_measured':False},
 error_taxonomy=['stale_development_engine_pin','synthetic_test_module_name_collision','finalize_stage_repository_whitelist','concurrent_1396_pin_detected','snapshot_missing_selected_data_path'])
put(ADR/'실험/manifest.json',m)
head='감시자 교통정리를 거쳐 온톨로지 조사 입력과 답변 직전 단축 검토를 작업 코드에 연결했다.'
bodies=[head,
'1393에서 검증한 조사 감시자는 주 모델의 행동과 실제 대상 결속을 담당했다. ASSESS는 답변·근거·사용 목록을 구조 검사했으며, 판단 사유와 빈 사용 목록의 의미 대조가 빠져 있었다.',
read(DES/'criteria.json')['hypothesis']+' '+str(read(DES/'criteria.json')['success']),
'완료1393 working528을 부모로 격리 후보에 구현했다. 초기 후보·실패 기록을 보존하고 1396 공용 핀 변경을 감지한 뒤 별도 후보로 검증했다. 최종 결합에서는 1396의 case_repository와 shortcut_cases를 실제 바이트 그대로 보존했다.',
'공개 상법의 기보관1383 응답과 합성 실제 FastAPI 요청을 사용했다. 외부 모델 호출0. 기존528파일 목록·640개 SQL 실행 표현과 엔진30/500 검사를 확인했다.',
'최종 통합 후보106통과, 환경 fixture1실패는 부모에도 동일. 실제 저장소의 선택 MAIN 설정 fixture1통과. 작업 체크아웃 API1통과(후보 검사와 중복). 묶음 전달·철회·중복·보완 성공·반복 거절과 조사 감시 입력 검사6통과는106에 포함된다.',
'첫 API 시도는 개발 후보 핀 미갱신으로 실패했다. 첫 동결 API에는 검사 파일명 test_native 충돌이 있었다. 이어 새 검토 단계의 종료 예산 분류를 저장소에도 명시해야 하는 계약 누락을 API에서 발견해 수정했다. 같은 제안의 반복 검토는 캐시를 재사용하므로 보완 성공 검사는 사유가 실제로 바뀐 제안으로 구성했다. 원본 기록을 보존했다.',
'새 Qwen 송신0. 보관 입력을 새 검토 입력으로 조립하면5903~10560자, 출력 스키마641~646자·PASS 응답19자다. 이는 공통 gateway/domain 부가 입력 전 조립본 문자 수이며 실제 토큰이나 지연 감소율이 아니다.',
'온톨로지 제공과 실제 채택을 구분하고, 경로 사용 요청·판단 사유·주장·사용 목록의 의미 차이는 감시자가 지적하게 했다. 감시자는 답변을 대신 쓰지 않고 문제만 돌려준다. 구조 오류는 기존 검증기에서 먼저 거절한다. 보완 담당은 기존 ASSESS 한 곳이다.',
'현재 검증은 합성 모델과 보관 자료다. 새 Qwen의 의미 판정 정확도·시간은 미측정이다. 온톨로지가 제시되고 주장이 있는 유효 제안에는 검토 호출이 추가되며 서로 다른 보완 제안까지 최대2회다. 일반 질문에는 경로 채택을 강제하지 않는다.',
'작업 제품6+파생32=38파일 반영, 동결 통합본과528파일 일치. 선택 MAIN146은 bound-chat-review-20261105-r1이다. 이번 온톨로지 검토 연결의 현장 배포·운영 지식 게시0. 원복 바이트는 artifacts/working-before이며 병행2파일과 공용 핀을 다시 확인해야 한다.',
'체크 경로는 setup → edit_candidate → freeze → 최초 실패 보존 → rebase_candidate → freeze → native-r4 → stage_working → final-contracts → 부모 환경 대조 → integrate → checkout-native·선택 ROOT 설정 → measure → finish → archive/seal/hash/status/validate.']
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 감시자 온톨로지 검토\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(zip(heads,bodies),1))+'\n')
q=m['questions'][0]
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
qn=['run-001/repaired, 기보관·합성 모의 API',
'지금 감시자 코드에 온톨로지도 돌아가게 만들어봐 감시자 코드 여러곳에서 작업이나 계획중에 있으니까 일단 교통정리 먼저해봐',
'원기록의 경로·근거·주장 ID 대조 및 합성 PASS/REPAIR별 상태를 검사한다. 법률 정답을 제품에 추가하지 않았다.',
'### 회수·탈락 단계 원장 — run·arm별\n\n추가 회수 벤치마크0. 합성 API의 원문/승인 묶음 및 기보관1383 canonical 입력을 사용했다.',
'실제 외부 모델 호출0. runtime 아카이브와 test_ontology_native.py의 합성 입출력 규칙 보존.',
'실제 요청 gateway를 지나는 memory-ontology-supervisor 호출, FINALIZE 예산·단일 보완 담당, 원문·패키지·현재 요청 결속 검사.',
'독립 채점 모델0. 구조·원문·인용 ID 및 최종 채택 상태를 검사했다. 실패 fixture와 재시험을 개별 보존.',bodies[5]+' '+bodies[9]]
(ADR/'실험'/q['file']).write_text('# 감시자 온톨로지 연결\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(zip(qh,qn),1))+'\n')
(ADR/'실험/README.md').write_text(f"# 검증 기록\n\n[연결 검증]({q['file']})\n")
report=ROOT/'09_ARTIFACTS/AUDITS/20261105-ontology-supervisor';report.mkdir(exist_ok=True)
(report/'교통정리와_연결결과.txt').write_text('\n\n'.join(bodies)+'\n')
put(report/'result.json',summary)
print(head)

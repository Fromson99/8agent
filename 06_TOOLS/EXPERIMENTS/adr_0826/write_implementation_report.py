from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance'
Q=R/'04_EXPERIMENTS/ADR/ADR-0826-comparison-resume-qualification';L=R/'04_EXPERIMENTS/ADR/ADR-0827-comparison-resume-live-check'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(Q/'artifacts/design/freeze.json');v=read(Q/'artifacts/run-001/result.json');live=read(L/'artifacts/run-001/result.json');case=live['cases'][0]
assert v['strict_success']
assert '47 passed' in (Q/'artifacts/working-api.log').read_text()
consumer=read(Q/'artifacts/working-consumer-v2.json');assert consumer['status']=='PASS' and consumer['qualified_component_hashes_match']
prior=read(R/'04_EXPERIMENTS/ADR/ADR-0823-comparison-partial-qualification/artifacts/working-integration.json');current=read(Q/'artifacts/working-integration.json')
paths=sorted({r['path'] for d in (prior,current) for r in d['changes']})
implementation=[n for n in paths if not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json']
assert all(sha(R/n)==f['serving_files'][n] for n in implementation)
base=read(Q/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
binding={'workflow_version':'1.4.1','qualified_code_root':f['code_root'],'implementation_files':{n:sha(R/n) for n in implementation},'integrated_file_count':len(paths),'implementation_file_count':len(implementation),'active_pointer':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'active_pointer_unchanged':True,'working_service':consumer['entry'],'qualified_api_batches':[31,16],'working_api_passed':47,'working_service_checks':len(consumer['checks']),'actual_model_result':str((L/'artifacts/run-001/result.json').relative_to(R)),'genos_accessed':False}
(A/'IMPLEMENTATION_BINDING.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n')
text=f'''대사 조사 과제 설계 구현·검증 결과
2026-10-16 / 작업 코드 workflow 1.4.1

결과

설계 A–F를 기존 RAG와 대사 실행 경로에 구현하고 작업 코드에 통합했다.
관련 구현·설정 {len(implementation)}개 파일은 최종 검증 후보와 SHA-256이 같다.
엔진·워크플로우 연결 지문까지 포함한 변경 파일은 {len(paths)}개다.
동시에 진행되던 다른 작업의 코드와 지문 변경은 보존했다.
활성 로컬 MAIN76과 GENOS는 변경하지 않았다.

구현한 흐름

1. 상태 보존: 마지막 유효 RAG 결과, 최근 시도, 누적 원문과 확인 항목을 분리했다.
   후속 조사 실패가 기존 성공을 덮어쓰지 않으며, 서로 다른 주장은 원문과 함께 남는다.
2. 비교 항목표: 일반·절차·전결·비율 유형을 comparison_fields.json으로 관리한다.
   여러 쟁점을 별도로 추적한다. 질문 ID별 정답 조문이나 수치를 제품 설정에 넣지 않았다.
3. 양방향 조사: 반대쪽의 검증된 원문 위치·정의·의무를 검색 단서로 전달한다.
   반대쪽 원문은 SEARCH_HINT_ONLY이며 자기 쪽 규정의 증거로 사용할 수 없다.
4. 부족한 항목 조사: 기존 Pipeline.run 안에서 정확 위치, 정의, 명시 참조와 범위 검색을
   먼저 실행한다. 같은 과제·자료·예산을 유지하고, 동일 실패를 새 질문으로 반복하지 않는다.
5. 항목별 결과: 필요한 본문과 조건·예외 의존성을 연결한다. 같은 source_id의 원문 전체를
   자동 확장하지 않는다. 문구 차이, 근거 관계, 현재 적용성과 법적 부합은 별도 결과다.
   한쪽 제안이 검증에 실패해도 다른 쪽의 검증된 인용은 남긴다. 실패한 원제안도 보존한다.
6. 조사 경로 재사용: 기존 경로 저장 기능에 과제 맥락을 결속했다. 과거 답변이나 실패를
   정답으로 승격하지 않으며 판본·권한·원문 해시가 달라지면 재사용을 차단한다.

추가로 발견해 고친 재개 결함

실제 모델 실행이 중단된 뒤, 부모 워크플로우가 복원돼도 자식 RAG의 RUNNING 요청이
충돌로 거절되는 문제가 있었다. 부모와 사건 잠금을 소유한 같은 요청만 복구하도록 연결했다.
요청 ID·입력·문서 범위·진행 중인 부모 호출을 검증하고 기존 단계 상태와 누적 예산을 유지한다.
판단이 이미 커밋된 경우에는 기존 원문을 재검증해 저장된 결과를 반환한다.
접수 직후, 조사 체크포인트, 판단 커밋 직후의 실제 프로세스 종료를 내규·외규 양쪽에서 검사했다.

실행·설정 연결

service.py → workflow.api/runtime → risk_team_compare_workflow.flow/task_board
→ RagAdapter.ask_rag → workflow_rag → 기존 Pipeline.run과 원문 조사 도구.
비교 설정: 02_BACKEND/workflow/risk_team_compare_workflow/comparison_fields.json
과제 계약: comparison-research-v1. 응답 소비자는 workflow-result-v1의 추가 필드를 처리한다.
진행 중인 구버전 실행에 새 계약을 암묵적으로 적용하지 않는다. 코드·원문 binding이 달라지면 차단한다.
기존 원문·정의·참조 색인을 사용하며 원문 재색인이나 새 내규 반입은 수행하지 않았다.

기술 검증

- 유한 상태 조합 258/258 통과: 항목96, 원문 묶음16, 조사 과제42, 부분 제안40, 재개 권한64.
- 최종 후보 API·복구 검사 47/47 통과. 동결 실행기의 파일 복사 누락으로 최초31개와
  사전 선언한 나머지16개를 나눠 실행했다. 원래 테스트·제품 코드·통과 기준은 변경하지 않았다.
- 공통 회귀 214개: 기준과 후보 모두208개 통과, 동일6개 실패. 신규 실패0.
  잔여 실패는 test_source_span_norm.py의 direct_note=True 조합이며 정확한 ID와 로그를 남겼다.
- 작업 코드 통합 후 API47개와 실제 service.py/HTTP 소비자13개 재검사 통과.
- 새 프로세스 재개, 중복 요청, 예산·전송 실패, 권한·원문·상태 변조, 저장·표시 연결을 포함한다.

실제 모델 확인

등록된 risk-104 질문 원문 1건을 Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음으로 실행했다.
외규 원문 체크포인트에서 사전 지정한 프로세스 종료를 주입하고 같은 요청·마감·총예산으로 재개했다.
실제 호출 {live['product_model_calls']}회, HTTP {case['http_status']}, 최종 상태 {case['status']}.
항목 결과 {case['field_rows']}개, 법적 비교 행 {case['comparison_rows']}개, 최종 인용 근거 {case['reported_evidence']}개.
원문 span 대조 불일치 {live['original_span_mismatches']}건.
상세 적용 범위와 남은 부족은 ADR-0827의 manual-review.json 및 answer.txt를 따른다.
알려진 질문 1건과 합성 계약 검사는 일반 법률 정확도·검색 적합성 개선률이나 GENOS 성능을 인증하지 않는다.
프로세스 종료·재시작과 병행 테스트가 포함돼 지연 절감률도 산정하지 않았다.
필요한 내부 규정 자체가 없는 문제는 데이터 보강 과제로 남는다.

적용 상태와 복원

작업 코드와 검증 후보는1.4.1이다. 선택 포인터는 계속 MAIN76,
evidence-complete-comparison-20261016-r1 / workflow1.2.0을 가리킨다.
실제 서비스 연결 검사는 해당 코드의 앱을 service.py에 명시적으로 주입해 실행했다.
활성 포인터를 통한1.4.1 부팅·MAIN 승격·GENOS 반입 및 현장 검증은 수행하지 않았다.
복원은 ADR-0826 → ADR-0823의 working-integration.json을 역순으로 확인한다.
현재 파일이 receipt의 after 해시와 같을 때만 working-before 백업을 복원하고,
처음부터 없었던 파일만 해당 receipt에 따라 제거한다. 다른 변경이 있으면 먼저 병합해야 한다.

검증 기록

04_EXPERIMENTS/ADR/ADR-0826-comparison-resume-qualification/artifacts/run-001/result.json
04_EXPERIMENTS/ADR/ADR-0826-comparison-resume-qualification/artifacts/working-integration.json
04_EXPERIMENTS/ADR/ADR-0827-comparison-resume-live-check/artifacts/run-001/result.json
IMPLEMENTATION_BINDING.json: 검증 후보·작업 코드·선택 포인터의 정확한 지문.
DESIGN.txt는 작성 당시의 미구현 설계 기록으로 보존했다.
앞선 ADR-0819의 결과 경로 누락과 ADR-0820의 가설 메타데이터 미완성은 완료 기록을 덮어쓰지 않고
정정 사항으로 남겼다. 최종826/827의 개별 검증과 전체 ADR 그래프의 잔여 오류를 구분한다.
전체 그래프 검사 출력은 GRAPH.txt에 보존한다.
'''
(A/'IMPLEMENTATION.txt').write_text(text)
print('Implementation report written')

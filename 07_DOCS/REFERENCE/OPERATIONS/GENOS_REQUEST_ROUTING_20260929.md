# 인사·안내와 문서 탐색 요청 분기 — 2026-09-29

사용자 지시로 v5 MAIN 작업 코드의 첫 검색 계획에 검색 필요 여부를 연결했다.
일반 요청은 `service.py` → `/v1/rag/ask` → `Pipeline` → `ServingLegalAgent` →
`BoundedSourceSession` → 기존 Coordinator/StageRunner/출처 묶음/outbox를 따른다.
GENOS 기본 파일 프로필은 `bounded_source_selection_enabled=true`다. 이 값을 false로
명시한 이전 자유 도구 탐색 경로에는 이번 안내 분기를 적용하지 않는다.

## 동작과 입력·출력

- 인사·감사·가벼운 대화·에이전트 소개/사용법: 첫 `source-query-plan`이
  `agent_required=false`와 직접 답변을 반환한다. 검색 대상과 검색어는 빈 배열이다.
  원문 검색·읽기·선별·질문 요구 정리·법률 답변 작성·검토는 실행하지 않는다.
  같은 Result의 `answer.text`에 안내를 넣고 claims와 출처 묶음은 빈 채로 정상 발행한다.
- 문서 내용·법령 해석·규정 적용·계산: `agent_required=true`, 직접 답변은 빈 문자열,
  검색어는 1~4개다. 기존 원문 회수·모델 선별·답변 경로를 유지한다.
  인사와 법률 질문이 함께 있으면 검색해야 한다. 분류는 모델의 판단으로 현장 정확도는 별도다.
- "현재 볼 수 있는 문서가 뭐야?", "현재 문서 목록 보여줘": 기존 메타데이터 목록 경로로
  모델 호출 없이 요청에 허용된 문서 제목을 반환한다. "현재"·"볼수있는"을 제목 필터로
  오인하지 않는다. 명시 문서 제목 필터와 요청별 문서/팀 범위는 유지한다.

`source_query_planning.routing_schema/validate_routing`이 신규 서빙 계약을 소유한다.
검색과 직접 답변을 함께 내거나 직접 답변이 공백인 제안은 거부한다. 기존 검색 전용
`SYSTEM/schema/validate` 호출 계약은 보존한다. 외부 Request/Result 스키마는 유지한다.

검색 유무와 이유·첫 모델 view는 `REQUEST_ROUTED` 이벤트와 `request_routing` 메타데이터에
저장한다. 직접 답변은 `bounded_source_workflow.status=DIRECT_RESPONSE`와 provider receipt의
`response_mode=DIRECT_RESPONSE`로 구분한다. 원문이 없다는 오류·법률 검토 경고를 붙이지 않는다.
모델/형식/검색 실패를 인사로 바꾸지 않는다. 안내 모델에 실제 기능과 대화 이력 미보존 한계를
전달하고 자료의 존재·내용·법률 결론을 안내 답변에서 추측하지 않도록 지시한다.

기존 GENOS 워크플로우의 `render`는 같은 `answer.text`를 표시하므로 편집기 Python 교체는
필요하지 않다. 초기 데이터 세대·요청 범위·모델 결속 준비는 첫 판단 전에 그대로 수행한다.

## 변경과 배포 상태

실행 파일은 `folder_navigation.py`, `legal_agent/source_query_planning.py`,
`legal_agent/bounded_source_session.py`, `legal_agent/readable_log.py`다.
이 파일을 참조하는 engine manifest와 `00_SYSTEM/PIPELINE.json`의 코드 pin을 함께 갱신한다.
완료된 frozen 릴리스·데이터·CURRENT·로컬 ACTIVE_RELEASE는 변경하지 않는다.
GENOS에는 검증된 작업 코드를 기존 checkout에 적용하고 별도 코드서빙 리비전을 배포해야 한다.
현재 세션에서 현장 적용·내부 모델 응답·질문 성공은 확인하지 않았다.

## 검증·복구

모의 원문과 모의 모델로 인사/사용법의 정상 응답·검색 도구 0회·빈 출처 정상 발행·journal/outbox·
GENOS 채팅 렌더링, 문서 목록의 모델 0회, 법률 질문의 기존 회수/선별·답변 연결을 검사한다.
모의 분류는 실제 내부 모델의 판단 품질이나 GENOS 속도를 측정한 결과가 아니다.
명령과 실제 결과는 `09_ARTIFACTS/AUDITS/20260929-request-routing/`에 남긴다.

현장 확인은 워크플로우 테스트에서 "안녕", "어떤 질문이 가능해?", "현재 볼 수 있는 문서가 뭐야?",
"안녕, [실제 문서명]의 [내용 질문]"을 각각 입력한다. 안내는 빈 출처와 안내 문장을,
목록은 해당 팀 범위의 등록 문서를, 내용 질문은 원문 검색·답변을 보여야 한다.
모델 결속·데이터 준비 실패는 그대로 오류로 처리하며 안내 성공으로 간주하지 않는다.

복구는 audit의 `before/`에 보존한 실행 파일·engine manifest·PIPELINE을 해당 변경 부분만
되돌린 뒤 새 리비전을 배포한다. 후속 작업이 있으면 파일 전체를 덮어쓰지 않는다.

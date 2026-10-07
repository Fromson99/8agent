# GENOS 법률 에이전트 진행 과정 표시 구현 설계

상태: **설계 + 로컬 작업 코드 구현** · 2026-09-23 · 대상: `LEGAL_AGENT` 채팅, 현장 GENOS V1.8.6

후속 구현: `semantic_runtime/progress.py`, `08_DEPLOYMENT/GENOS/stream_app.py`,
`08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`에 진행 경로를 연결했다. 현재
사용자별 열람 권한 계약이 없어 작업 코드는 내부 문서명·좌표를 표시하지 않고
단계·건수만 보낸다. GENOS 코드서빙 시작 명령, 게이트웨이 SSE, 채팅의 조기 렌더와
중복 여부는 현장에서 확인해야 한다. 이 문서의 아래 일부 문장은 구현 전 설계 시점의
판단이며, 실제 배포 절차는 [채팅 연결](../OPERATIONS/GENOS_CHAT_WORKFLOW.md)을 따른다.

## 1. 결정 요약

사용자가 채팅에서 기다리는 동안 우리 법률 에이전트의 **실제 실행 상태**를 보여준다. 모델의 `reasoning_content`, 프롬프트, 원문 전문, 검증 전 초안은 화면으로 보내지 않는다. 표시 대상은 요청별로 확정된 단계, 도구 관찰, 원문 열람, 근거 선택, 검토 결과와 경과 시간이다. 최종 답변은 기존 검증·발행 경로가 완성한 `text`를 한 번만 사용한다.

**제안 경로:** 코드서빙의 요청별 관측 이벤트와 *커밋된* legal-agent journal → 허용 필드만 추리는 진행 투영기 → 코드서빙 `POST /stream`의 SSE → GENOS 워크플로우의 소켓 중계 → 채팅의 진행/`Visible Reasoner` 패널. 기존 `POST /json`과 `run(data) → {"text": ...}` 계약은 유지한다. `/stream`이나 소켓을 사용할 수 없는 배포는 `/json`으로 완료된 답을 받는다.

최초 설계는 코드와 현장 기록을 조사한 결과다. 후속 작업 코드에서 `service.py`의 실행 경로를 재사용하는 별도 `/stream` 어댑터와 워크플로우 수신기를 구현했다. GENOS 현장 배포·게이트웨이의 `/stream` 전달·채팅 패널의 실시간 표시 여부는 이 세션에서 확인할 수 없다. 다른 과제의 `/stream` 구현과 V1.8.6 표시 실측은 연결 가능성의 근거이지 우리 법률 RAG의 현장 성공 증거가 아니다.

이 기능은 응답 대기 중 **무엇을 하는지 알게 하는 기능**이다. 현재 약 270~300초라는 지연의 원인을 고치거나 모델 실행을 단축한다는 근거는 없다. 진행 이벤트에서 실제 지연 지점을 식별한 뒤 성능 수정은 별도로 결정한다.

## 2. 현재 경로와 변경 지도

| 위치 | 현재 실행 계약 | 제안 변경과 소비자 |
|---|---|---|
| `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`의 `_extract_question`, `run`, `call_code_serving` | 질문을 `LEGAL_AGENT`로 `/json`에 보내고 전체 JSON을 읽은 뒤 `{"text": ...}` 반환. `request_id`, `tm_code_serving`을 기록 | 질문 추출/팀 선택 계약은 유지. 선택된 `/stream`의 이벤트를 읽는 별도 함수와 V1.8.6 소켓 어댑터 추가. 종료 시 기존 `render()` 결과를 최종 `text`로 반환. 워크플로우 환경에 제안 설정 `GENOS_RAG_PROGRESS_UI=off|socketio` 추가 |
| `service.py`의 `service()`, `_normalize()`, `_call()` | `/json`을 통해 `LEGAL_AGENT → /v1/rag/ask`; 응답은 `{status, body}`. `request_id` 관측과 선택적 `GENOS_SHARED_LOG_DIR` 기록 | 현재 `service()`를 작업 실행의 단일 진입으로 재사용. 제안 ASGI 어댑터의 `/json`은 같은 `service()`를, `/stream`은 같은 요청을 한 번 실행하며 진행과 최종 결과를 SSE로 전달. 별도 에이전트 실행기 금지 |
| `02_BACKEND/semantic_runtime/app.py` → `pipeline.py` → `legal_agent/coordinator.py` | `/v1/rag/ask`에서 기본 `use_llm=true`; retrieve/select/assemble/answer 및 재탐색 수행 | 단계와 재진입은 그대로 둔다. 화면 전송은 이 함수의 판단을 바꾸지 않으며 실행 상태를 읽기만 한다 |
| `legal_agent` journal: `event`, `observation`, `entity_version`, `model_attempt` | 요청별 SQLite에 도구 관찰·판단·근거·모델 시도를 순서대로 보존 | 커밋된 행만 읽어 화면 상태로 투영. `WORKFLOW_TURN`, `QUESTION_PLAN`, `SOURCE_SELECTION`, `WORKFLOW_DRAFT`, `REVIEW_V2`/v5 검토 항목, `OBSERVATION`을 매핑. 모델 요청 시작/종료는 내용 없이 상태와 소요 시간만 사용 |
| `semantic_runtime/request_report.py`의 `_LiveLog.poll_journal()` | 선택적 내부 공유 `.log`에 요청 로그와 journal을 실시간 복제하며 프롬프트·원문·모델 응답도 다룬다 | 기존 원장/내부 로그는 유지. 화면 스트림에 이 파일의 문자열이나 `_model_reply()` 결과를 **그대로 사용하지 않는다**. 요청 ID 연결·커밋 순서 판독 패턴만 재사용하는 별도 allowlist 투영기를 둔다 |
| GENOS 코드서빙 HTTP 시작 방식 | 현행 배포가 플랫폼의 `service(config,data)`를 사용하는지 커스텀 ASGI를 사용하는지 미확인 | `/stream`을 쓰려면 동일 코드 리비전에서 HTTP 진입점과 시작 명령을 추가해야 한다. 과제7의 `front/app.py`는 `uvicorn` 커스텀 시작 방식 예시다. 현재 GENOS 리비전이 이를 허용하는지 선행 확인 |

`/stream`은 **제안 API**다. `POST /json`, `service(config,data)`, `/v1/rag/ask`, 외부 term-runtime-v1 Request/Result, journal 스키마, 선택된 데이터 세대는 변경하지 않는다. 따라서 이 표시 기능 자체는 원문·용어집·색인의 재구축을 요구하지 않는다. 코드서빙 리비전과 워크플로우 리비전은 각각 교체해야 한다. `GENOS_GENERATION`, 모델 ID, 해시 고정 프로필은 배포 시 실제 값을 대조하고 기존 값을 임의 변경하지 않는다.

## 3. 진행 이벤트 계약

### 3.1 서버 내부 계약과 화면 계약

제안 `rag-progress-v1` 이벤트는 한 요청에서 순서가 증가한다. 요청마다 `request_id`를 워크플로우가 생성해 코드서빙으로 보내고, 코드서빙의 `run_id`는 생성된 뒤에만 싣는다. `seq`는 **화면 스트림 전용 번호**이며 journal의 `event.seq`와 같은 값일 필요가 없다. 감사 연결은 `basis.kind`와 내부의 `journal_seq`/관측 이벤트 ID로 보존하되 화면 문자열에는 opaque ID를 반복하지 않는다.

```json
{
  "schema_version": "rag-progress-v1",
  "request_id": "요청 식별자",
  "run_id": "생성 후에만 존재",
  "seq": 7,
  "kind": "source_state",
  "phase": "investigate",
  "state": "READ_COMPLETE",
  "display": {"document_name": "표시 권한이 확인된 문서명", "coordinate": "확인된 조문 좌표"},
  "basis": {"kind": "OBSERVATION", "journal_seq": 23},
  "elapsed_ms": 18400
}
```

`kind`는 `phase`, `model_wait`, `source_state`, `decision`, `review`, `heartbeat`, `terminal`로 제한한다. `state`는 코드가 정한 enum만 허용한다. `display`는 **코드서빙에서** 검증된 원장·현재 세대 메타데이터로 구성한다. 워크플로우는 법령명이나 판단을 새로 만들지 않고 허용 이벤트를 짧은 한국어 문장으로만 렌더한다. SSE 프레임은 `data: {"event":"progress","data":{...}}\n\n`, 마지막은 `result` 또는 `error`; 스트림의 `Content-Type`은 `text/event-stream`이다. 초기 버전은 끊긴 SSE의 자동 재접속·중간 재생을 지원하지 않는다.

### 3.2 ‘어떤 법률을 보는가’의 상태 정의

| 화면 상태 | 허용 근거 | 표시 의미 |
|---|---|---|
| `CANDIDATE` | 범위 내 검색/목록 도구의 커밋된 `OBSERVATION` | “검색 후보에 나타남”. 아직 원문을 읽거나 적용 판단을 하지 않음 |
| `READING` | 유효한 범위 내 `read` 실행 시작. 대상 문서 ID가 서버에서 해소된 때 | “원문을 여는 중”. 완료·정확 span 검증은 아직 아님 |
| `READ_COMPLETE` | `OBSERVATION` 성공과 `evidence_unit` 저장·검증 | “원문을 읽음”. 관련성·법적 적용 확정 아님 |
| `SELECTED` | 현재 유효한 `source_selection` 또는 v5 bounded selection 커밋 | “답변 검토용 근거로 선택”. 선택 이유는 모델 제안 중 서버 검사를 통과한 짧은 구절로 표시 가능하나 법적 결론이라고 쓰지 않음 |
| `REVIEWED` | 현재 버전의 독립 검토/최종 발행 검사가 완료된 때 | “해당 주장을 검토함”. 판정은 `SUPPORTED`, `UNCERTAIN`, `NEEDS_RESEARCH` 등 실제 저장값으로만 표시 |
| `REVISED` | 이전 선택/초안이 무효화되거나 현재 head에서 빠진 때 | “앞선 선택을 재검토함”. append-only 채팅 패널에서는 정정 블록을 추가하고 최종 결과에는 현재 유효한 선택만 싣는다 |

`team_id`와 선택 세대는 **검색 범위**를 정할 뿐 사용자 접근 권한을 증명하지 않는다(`team_scope.py`의 계약). 문서명·좌표를 표시하려면 서버가 해소한 문서 ID가 검색 범위에 속하는지 확인하고, 별도로 채팅 사용자의 열람 권한까지 검증해야 한다. 현재 사용자별 권한 정보가 코드서빙으로 전달되는지는 미확인이다. 이 계약이 확인되기 전에는 내부 문서명·좌표를 보내지 않고 “범위 내 원문 1건 열람 중”처럼 단계·건수만 보낸다. 공개 법령명도 출처 공개 등급과 노출 정책을 검증한 경우에만 표시한다. 모호한 참조 관계, 부분 회수, 미확정 시행일은 그대로 “미확인”으로 표시한다. 검색 결과 제목·용어 연결만 보고 “적용 법률”이나 “위반”이라고 쓰지 않는다. 원문 발췌, 사용자의 질문 전문, 내부 파일 경로, 프롬프트, 인증키, 모델 응답 JSON, `reasoning_content`는 화면 진행 이벤트의 금지 필드다.

### 3.3 단계 투영

| 기존 출처 | 화면 문구 예시 | 발행 시점 |
|---|---|---|
| `request.started`, `binding.resolved`, `session.open.ready` | “요청과 자료 범위를 확인 중” | 시작/완료. 세대 불일치면 진행 실패 |
| `bounded_source.started`, `bounded_source.query_plan.finished` | “질문의 확인 대상을 정리 중” | 관측 이벤트. 모델 호출 중에는 `model_wait`와 경과 시간 표시 |
| `source_recall.*`, 도구 `OBSERVATION` | “관련 자료 검색 중”, “○○ 규정 원문 열람 중/완료” | 도구 시작 및 결과 커밋 이후. 후보·읽음 분리 |
| `SOURCE_SELECTION`, `BOUNDED_SOURCE_SELECTION`, 유효한 `entity_head` | “○○ 규정을 답변 검토용 근거로 선택” | 커밋·현재 유효성 확인 뒤 |
| `WORKFLOW_TURN`, `QUESTION_PLAN` | “추가 원문 확인 필요”, “초안 작성 단계로 이동” | 서버가 검증해 커밋한 `intent`/행동에 한함. 자유형 사고 문장 전송 금지 |
| `WORKFLOW_DRAFT`, 검토/반론 원장, `answer.control` | “답변 초안 검토 중”, “예외 조항 재확인 중” | 초안 내용 대신 단계·결과만 전송 |
| `request.finished`, 최종 outbox/답변 | “검토 완료” 또는 실패 분류 | 최종 검증 뒤 `result` 전송 |

소켓 패널의 표시는 서버 이벤트가 도착한 순서대로 하되, 화면 중복은 `(request_id, seq)`로 제거한다. 동일 상태의 반복 heartbeat는 갱신으로 처리한다. 단계가 변하지 않으면 “모델 응답 대기 · 경과 40초”처럼 **시간만** 갱신하며 가짜 퍼센트나 완료 예정 시간을 만들지 않는다.

## 4. 전송·워크플로우 구현 절차

1. **요청별 투영기(제안):** `02_BACKEND/semantic_runtime/` 아래에 화면용 모듈을 둔다. `obs`의 `request_id`가 일치하는 단계/모델 상태를 받고, journal은 기존 `request_report._LiveLog`처럼 커밋된 `event.seq` 이후만 읽는다. `OBSERVATION`/`source_selection`의 범위·현재 head를 확인하고 정해진 필드만 `rag-progress-v1`로 변환한다. 전역 로거를 사용하더라도 요청 ID로 격리하고 종료 시 handler와 reader를 반드시 해제한다. NFS의 원문 포함 `.log`를 파싱해 UI에 보내지 않는다.
2. **코드서빙 HTTP 어댑터(제안):** 기존 `service.service()`를 **한 번만** 호출하는 커스텀 ASGI 진입점을 둔다. `/json`은 기존 본문·응답과 동등하게 유지하고 `/stream`은 같은 요청을 작업 스레드에서 실행하며, 별도의 asyncio 큐에서 진행 이벤트와 heartbeat를 SSE로 보낸다. 모델 호출과 SQLite 접근이 이벤트 루프를 막지 않도록 한다. 완료 시 `service()`가 돌려준 `{status, body}`를 `result` 이벤트로 보낸다. 과제7의 `front/app.py`·`front/stream.py`는 전송 방식의 참고 구현이며 법률 판단 로직은 복사하지 않는다.
3. **GENOS 워크플로우(제안):** 현재 `call_code_serving()`의 `/json` 경로를 보존하고 `/stream` reader를 추가한다. 표준 라이브러리 `urllib` 읽기는 스레드에서 수행하고, 큐를 통해 워크플로우 이벤트 루프로 넘겨 `sio_server.emit`한다. 사용자 질문·팀 범위·요청 ID를 동일하게 전달한다. 사용자별 문서 열람 권한을 전달할 수 있다면 GENOS가 검증한 신원/권한 정보만 사용하며, 질문 본문이나 사용자가 보내는 `team_id`를 권한 증명으로 받지 않는다. `404/405`가 요청 실행 전에 온 때만 `/json` 한 번으로 대체한다. 연결 끊김·`500`·중간 타임아웃은 **재실행하지 않는다**. 동일한 법률 요청의 중복 실행과 원장 이중 생성을 막기 위해서다.
4. **V1.8.6 화면 어댑터(제안):** `run()`은 끝까지 dict 반환으로 유지한다. 현장 기록의 `nodeId`, `status:"FINISHED"`, `nodeLabel:"Visible Reasoner"`, `content:{"visible_rationale":...}`, 최종 `agentFlowExecutedData`, `token` 및 `end` 조건을 별도 함수에서 구성한다. 기록상 `token`이 없으면 패널이 렌더 모드에 들어가지 않는다. 답변은 최종 검증 전 확정되지 않으므로, 초기 `token`에 허용되는 진행 문구/빈 청크와 최종 답 토큰의 중복 여부는 **현장 최소 프로브의 필수 확인 사항**이다. `token`이 최종 답 텍스트로만 작동한다면 추론 패널의 사전 실시간 표시는 달성되지 않은 것으로 판정한다. 이 경우 진행 문구를 채팅 본문 토큰으로 보여줄 수 있는지 별도로 검증하거나 현재 `/json` 화면으로 되돌린다.
5. **최종 답:** 검증된 `render(body)`만 답변 텍스트로 사용한다. 현장 렌더 계약이 확인되면 반환 dict에는 동일한 `text`와 `agentFlowExecutedData`를 넣고, 소켓의 답 토큰·`end`와 중복되지 않게 한다. `result` SSE가 없거나 코드서빙 결과의 상태가 실패면 기존 추적 번호를 포함한 실패 문구를 한 번 반환한다. 진행 이벤트가 먼저 성공처럼 보였어도 최종 검증 실패를 숨기지 않는다. 소켓 오류는 답변을 실패시키지 않고 `/json`과 동일한 최종 반환을 유지한다.

기존 `GENOS_SHARED_LOG_DIR`은 내부 진단용으로 선택 사용한다. 제안 `/stream`은 같은 컨테이너 안의 요청별 이벤트를 소비하므로 워크플로우가 NFS에 접근할 필요가 없다. 현장 게이트웨이가 커스텀 `/stream`을 전달하지 못하면 NFS를 임의의 공개 진행 API로 대체하지 않는다. 이 경우 진행 UI는 미활성이고 기존 `/json`이 계속 작동해야 한다.

## 5. 정상·실패 시나리오

| 시나리오 | 기대 동작 | 확인할 경계 |
|---|---|---|
| 정상 법령 질문 | 요청 시작 → 범위 확인 → 후보·열람·선택·검토 이벤트 → 최종 `result` → 한 번의 답변 | 제목·좌표가 표시된다면 권한 확인 및 실제 원장/최종 source bundle과 일치. `tm_total`과 SSE 최종 시간 비교 |
| 모델이 270초 가까이 응답하지 않음 | 현재 `model_wait` 단계와 경과 시간 heartbeat. 300초 예산 만료 시 실패 상태/추적 번호 | heartbeat가 모델 응답 성공으로 보이지 않음. 프록시가 SSE를 버퍼링하거나 전체 요청을 300초에 끊는지 현장 검증 |
| 검색 후보가 있었으나 원문 회수 실패 | 후보 → 읽기 실패/미확인. 선택·법률 적용으로 승격하지 않음 | `READ_COMPLETE`를 성공 observation 전에 내지 않음 |
| 선택한 조항을 뒤에서 철회 | `REVISED` 정정 이벤트를 추가. 최종 패널/답변에는 현재 유효한 선택만 남김 | append-only UI의 과거 블록을 최종 사실처럼 방치하지 않음 |
| 검색 범위 거절·세대 불일치·열람 권한 미확인 | 제목 없이 범위 확인 실패 또는 제목을 생략한 단계 표시. 최종 실패/답변은 기존 경로의 판정에 따름 | 범위 바깥 또는 열람 권한 미확인 제목·원문·파일 경로가 SSE에 나타나지 않음 |
| `/stream` 404/405 | 같은 입력을 `/json`으로 단 한 번 전송, 최종 답만 반환 | 404/405가 실행 전 반환인지 확인; 그 외 오류에는 재실행 금지 |
| 소켓 실패·브라우저 종료 | 코드서빙의 요청 처리/원장은 독립적으로 종료. 채팅 UI는 최종 응답 또는 연결 실패를 표시 | 연결 취소가 작업 스레드를 자동 중단한다고 가정하지 않음. 누수·중복 호출 검사 |
| 동시 질문 | `(request_id, run_id)`별 별도 큐·seq·소켓 room | 다른 팀/대화의 제목·단계가 섞이지 않음 |

## 6. 비용·품질 기대치와 위험

| ID | 구분 | 값/산식과 근거 | 검증 |
|---|---|---|---|
| P-01 | 관측된 설정값 | 현재 v5 프로필 `wall_seconds=300`, 모델 시도 상한 14회. 이는 실제 지연이나 실제 호출 수가 아니다 | 배포 리비전의 해시 고정 프로필과 모델 로그 대조 |
| P-02 | 제안값 | 상태가 바뀔 때 이벤트 발행, 조용할 때 10초 간격 heartbeat. 300초 요청이면 단순 계산상 heartbeat **최대 약 30회**이며 재시도/다른 이벤트는 별도 | 현장 프록시 idle 제한·소켓 렌더 결과로 간격 조정 |
| P-03 | 기대 효과 미산정 | 최초 진행 표시 시간 = 코드서빙 접수/초기화 + 최초 관측 이벤트 생성 + SSE/소켓 전달. 현장 분포가 없어 초·p95 예측 불가 | 요청별 최초 이벤트 시각과 브라우저 표시 시각 측정 |
| P-04 | 지연 비용 미산정 | 추가 모델 호출은 **설계상 0회**. 총 추가 시간은 관측 투영·JSON 직렬화·전송/대기 부하이며 부하 측정 전 수치화 불가 | 동일 코드/세대에서 `/json` 대비 총시간·CPU·메모리·동시성 비교 |
| P-05 | 작업량 미산정 | 투영기, ASGI 어댑터, 워크플로우, 현장 렌더 검증, 장애·롤백 문서가 각각 필요. GENOS 시작 방식·게이트웨이 허용 여부가 일정의 선행 조건 | 기술 확인 후 패키지별 산정. 코딩 시간과 현장 리비전/승인 대기 분리 |

화면 이벤트는 읽기 전용이어야 한다. 단계 표시를 위해 검색/모델 호출을 추가하면 현재 답변의 성능·품질·감사 범위가 달라진다. 내부 원장의 풍부한 원문·프롬프트·모델 응답을 그대로 중계하면 정보 노출 위험이 있다. 반대로 이벤트를 과도하게 줄이면 “어떤 법률을 보는가”가 빈말이 된다. 해법은 **서버에서 검증한 상태를 우선 전송하고, 문서명·좌표는 검색 범위와 사용자 열람 권한을 모두 확인한 경우에만 전송**하는 것이다. 최종 근거 판정은 기존 출처 묶음/검토 결과를 따른다.

현재 `request_report._LiveLog`는 원장을 주기적으로 읽어 실시간 내부 `.log`를 만든다. 이 코드를 화면 포맷으로 직접 쓰면 내용·민감도·출력 크기 계약이 섞인다. 투영기는 커밋 순서와 요청 ID 연결만 재사용하고, UI용 필드와 최대 길이·이벤트 수 제한을 독립 계약으로 둔다. 반복 heartbeat는 합치거나 낮은 우선순위로 버릴 수 있으나 실제 선택/철회/실패 이벤트는 조용히 버리지 않는다. 큐가 포화되면 채팅 스트림은 명시 실패로 종료하고 요청 본체의 원장과 최종 답변은 보존한다.

## 7. 검증·도입·롤백

1. **계약 확인:** 실제 GENOS V1.8.6의 동일 채팅 앱에서 `return {"text":"..."}` 최소 프로브를 확인한 다음, `token`·`Visible Reasoner` 블록·`end`의 화면 표시 시점과 중복을 확인한다. 특히 `return` 전에 진행 블록이 보이는지, 초기 진행용 토큰이 답변 본문에 남는지 확인한다. 테스트 문구만 사용하며 실제 법률 질문/원문은 싣지 않는다. `/stream`의 `text/event-stream`이 게이트웨이에서 **조각별** 도착하는지, 커스텀 ASGI 시작 명령이 선택한 코드서빙 리비전에서 허용되는지 확인한다. 과제7 코드의 존재만으로 이 단계 통과 처리하지 않는다.
2. **로컬 계약 검사:** 모의 범위/원장으로 후보 → 열람 → 선택 → 철회 → 검토 → 결과 순서를 재현한다. `result` 전에 진행 이벤트가 도착하는지, 최종 `text`가 기존 `/json`과 같은지, 비밀·원문 전문·범위 밖 문서명·모델 응답이 전송되지 않는지 검사한다. `team_id`만 제공하거나 열람 권한을 확인할 수 없을 때 내부 문서명이 생략되는지도 검사한다. 실제 모델 성능 실험은 이 설계 검사의 대상이 아니다.
3. **현장 코드 확인:** 선택 코드·세대의 해시를 [GENOS 릴리스 게이트](../OPERATIONS/GENOS_RAG_GENERATION_HANDOFF.md)로 대조한 뒤 코드서빙 새 리비전과 워크플로우 새 리비전을 각각 배포한다. 채팅 앱 바인딩까지 확인한다. 먼저 `/json` 질의의 기존 성공을 보존하고, `/stream`으로 자료 목록/실제 근거 질문을 각각 확인한다. 모델/검색의 정확도와 진행 표시 성공을 따로 판정한다.
4. **합격 기준:** 첫 진행 이벤트가 최종 결과보다 먼저 **채팅 화면에** 나타남; `request_id`·문서 상태·최종 출처가 일치함; 답변 중복/범위 누출 없음; `/stream` 불가 시 `/json` 성공 유지; 동시 요청과 중간 연결 해제에서 원장·세대 변경 없음. 서버가 SSE를 보냈어도 채팅이 최종 반환 뒤에야 그리면 실시간 UI는 불합격이다. 성능은 기존 배포의 같은 질문/세대와 요청별 지연·모델 호출 수를 비교해 회귀 여부를 판정한다. 수치 허용 범위는 현장 기준선 측정 전에 임의로 확정하지 않는다.
5. **롤백:** 워크플로우의 제안 `GENOS_RAG_PROGRESS_UI=off`로 먼저 UI 전송을 끄고 기존 `/json` 브릿지 리비전으로 복귀한다. 코드서빙은 기존 시작 명령/리비전으로 되돌린다. 데이터 `CURRENT`, 원문, journal, 활성 세대는 건드리지 않는다. 이미 기록된 요청별 감사 산출물은 보존한다.

후속 작업 코드 구현과 로컬 계약 검사를 수행했다. 진행 채널·기존 채팅·서비스 진입·요청 보고 관련
테스트 37개가 통과했다. GENOS 현장 실험·배포와 독립 감독 검토는 수행하지 않았다.

## 확인한 근거

- `GENOS.md`; `07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md` — 현장 V1.8.6의 `dict return`과 소켓/`Visible Reasoner` 실측. 원본 진행 브릿지는 현재 받아 둔 브랜치에서 확인되지 않음.
- `07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/codeserving-vs-workflow-design.md` — 코드서빙이 주력 로직, 워크플로우가 채팅/스트리밍 중계 역할이라는 현장 회신.
- `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`; `service.py`; `02_BACKEND/semantic_runtime/app.py`; `02_BACKEND/semantic_runtime/pipeline.py`; `02_BACKEND/semantic_runtime/legal_agent/coordinator.py` — 현재 요청·반환 경로.
- `02_BACKEND/semantic_runtime/legal_agent/{repository.py,journal-v5.sql,bounded_source_session.py,workflow_tiers_session.py,tools_session.py,source_bundle.py}`; `02_BACKEND/semantic_runtime/request_report.py` — 상태/원장/검증과 내부 실시간 기록.
- `/home/jin/8-AGENT-fde-seungho-integration/07-issuance-note/front/{app.py,stream.py}`, `deploy/workflow/report_chat.py` @ `486f295c` — SSE와 워크플로우 소켓 중계의 **다른 과제 구현 예시**. 해당 코드의 현장 `/stream` 성공은 이 문서에서 확인되지 않음.
- `07_DOCS/REFERENCE/OPERATIONS/GENOS_RAG_GENERATION_HANDOFF.md` — 코드·세대 결속, 요청별 공유 로그, 배포 후 확인과 복구.

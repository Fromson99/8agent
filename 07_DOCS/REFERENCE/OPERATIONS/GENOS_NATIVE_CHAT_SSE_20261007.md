# 워크플로우 없는 직접 채팅과 SSE — 2026-10-07

사용자가 말한 통합 버전은 별도 GENOS Python 워크플로우를 실행하지 않고
코드서빙의 `/chat`에서 입력 처리·RAG 호출·답변 표시를 끝내는 방식이다.
2026-10-07 작업 코드는 기존 직접 호출을 유지하며 답변 수집기와 HTTP 스트림을 연결했다.
현장 리비전·채팅앱 바인딩은 외부 Codex에서 변경하거나 검증하지 않았다.

## 승호 cicd를 다시 확인한 결과

`git fetch infocz fde/seungho/cicd`로 확인한 커밋은
`388cd39208dd189b902799002884ef8c4d9025b0`(2026-10-06 21:13:45 +09:00)이다.
`02-els-qa/main.py`와 `workflow/chat.py`는 직접 호출 후 완성 JSON을 반환한다.
`07-issuance-note/front/app.py`와 `workflow/chat.py`는 직접 `/chat` SSE도 구현한다.

단, `36b9cc381bf576b663956b5df19a2c7d61eb6132`의 커밋 기록과
`07-issuance-note/deploy/prod.env`에는 현장 `/chat` SSE가
`'function' object has no attribute 'get'` 오류를 내서 `REPORT_PROGRESS=off`로
되돌렸다고 기록되어 있다. 같은 payload의 로컬 SSE는 완료됐다는 작성자 기록이다.
이는 승호님 과제의 현장 관찰이며, 우리 리비전에서 재현한 결과가 아니다.
플랫폼 수신/검증 경로의 문제를 의심할 근거지만 정확한 발생 함수와 수정 방법은
해당 플랫폼 traceback이 없어 미확인이다. SSE 서버 구현만으로 현장 문제 해결을 인증하지 않는다.

## 우리 실행과 수정

`main.py POST /chat → semantic_runtime.chat_adapter.chat → service.service`
`→ /v1/rag/ask → 기존 Pipeline/Coordinator/legal_agent v6`로 같은 프로세스에서 돈다.
코드서빙 URL·토큰을 읽어 자기 자신에게 HTTP를 보내지 않는다.
`main_socketio`나 `socketIOClientId`는 HTTP 스트리밍에 필요하지 않다.
기존 워크플로우 소스는 이 릴리스의 질문 추출·출처·표시 함수만 재사용한다.
플랫폼에 별도 Python 워크플로우를 배포·실행하는 의존성은 없다.

기존 `/chat`은 완료까지 기다린 JSON 반환이며 progress를 최종 배열로만 보존했다.
이번 수정은 요청 단위 `answer_stream.capture`와 progress sink를 직접 어댑터에 연결한다.
기존 `/stream`과 같은 bounded queue·작업 스레드·10초 heartbeat 수명주기를 사용한다.
답변 조각은 순서·요청 ID를 검사하고 기존 숫자 각주/Markdown 표시 함수를 적용한다.
느린 수신자에게는 답변 producer가 대기하며 progress만 생략될 수 있다.
연결 중단 후 기존 법률 요청은 원장을 닫고 끝내며 자동 재질의하지 않는다.

입력·출력:

| 응답 방식 | 출력 계약 |
|---|---|
| JSON | `{"code":0,"data":{채팅 필드,"text":최종 답변,...}}` |
| SSE | `data: {"event":"token","data":"표시할 문장"}` → `: keep-alive` → 마지막 `data: {"event":"result","data":{채팅 필드,"text":최종 답변,...}}` |

SSE 마지막 `result.data`는 JSON의 바깥 `code/data` 봉투로 다시 감싸지 않는다.
`result`가 마지막 이벤트이며 별도 `end` 이벤트는 보내지 않는다. 이는 cicd 직접 `/chat`과 같다.
Reasoner 최종 배열·출처·판단 토글·기억/AD 인증과 현재 원문 generation은 보존한다.
스트림 실패는 최종 상태를 실패로 표시하며 일부 본문을 완료 답변으로 승격하지 않는다.
모델의 기존 stream 지원/내부 trust zone/최종 검토 정책은 변경하지 않는다.
모델이 답변 조각을 보내지 않으면 진행/heartbeat를 보내고 완성 답변을 마지막에 전달한다.

## 실행 선택과 확인

Run은 `python3 main.py`로 지정한다. PORT가 제공되지 않으면 기존 리비전의 실제
수신 포트를 `--port`로 명시한다. Build는 기존 SSE 의존성
`python3 -m pip install -r 08_DEPLOYMENT/GENOS/requirements-sse.txt`다.
`service/service.py` 기본 JSON 로더만 실행하면 이 `/chat` 앱은 선택되지 않는다.

`GENOS_CHAT_TRANSPORT=json`이 기본이다. 직접 통합 실행은 이 설정에서도 사용한다.
`/chat?stream=1` 또는 본문 `stream:true`로 한 요청의 SSE를 명시한다.
`GENOS_CHAT_TRANSPORT=sse`는 기본 SSE를 선택한다.
`auto`는 `Accept:text/event-stream`을 따르는 선택형 모드다.
`?stream=0` 또는 본문 `stream:false`는 완성 JSON으로 복귀하며 query 설정이 우선한다.
플랫폼 등록 확인 `question=__verify__`는 모든 모드에서 모델 없는 JSON이다.

현장 확인은 기존 워크플로우 테스트 화면에서 코드서빙 `/chat`을 선택해 수행한다.
이 화면을 쓰는 것과 Python 워크플로우로 RAG를 실행하는 것은 다르다.
일반 직접 질문은 `execution_transport=in-process`,
`chat_adapter_revision=main-chat-sse-20261007-r1`를 확인한다.
SSE 수신만 확인할 때는 `{"API_TYPE":"SSE_CHECK","stream":true}`로 모델 없이
최종 `result.text`, `sse_check.sse_ready`, `chat_stream_transport.route=/chat`을 확인한다.
같은 플랫폼 검증 오류가 나면 일반 질의는 직접 JSON으로 유지하고 해당 요청의
플랫폼 traceback·배포 리비전·채팅앱 연결 정보를 결속해서 원인을 확인한다.
실제 모델 질의 성공·조기 화면 표시·긴 요청 수신은 각각 별도 현장 확인이다.

작업 코드/반입본만 갱신한다. 로컬 활성 릴리스 generation43의 동결 코드와
활성 포인터는 바꾸지 않는다. 과거 인계·롤백 기록과 원문/DB/CURRENT는 보존한다.
코드 적용·같은 checkout의 generation gate·Git push·리비전 배포·채팅 연결을 별도 상태로 남긴다.

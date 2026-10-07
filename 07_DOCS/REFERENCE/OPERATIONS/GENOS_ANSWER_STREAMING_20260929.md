# GENOS 최종 답변 생성 스트리밍 — 2026-09-29

사용자 지시로 MAIN 작업 코드의 v5 최종 작성 본문을 생성 중 전달한다.
리비전 표식은 `answer-stream-20260929-r1`이다. GENOS 현장 적용·내부 모델의 SSE 지원·
게이트웨이 버퍼링 여부·실제 화면 표시 속도는 이 세션에서 확인하지 않았다.

## 호출과 계약

`workflow/genos_rag_chat.py → /stream → 기존 service → Pipeline → v5 session →
ModelGateway.generate(compose, Draft) → GenosTransport.send_stream_once`를 사용한다.
별도 답변 모델이나 파이프라인을 만들지 않는다. 내부 GENOS transport, 요청의 SSE 수신기,
`final_review_enabled=false`가 연결된 작성 단계에서만 `stream=true`와 usage 수신을 요청한다.
계획·탐색·선별·검토와 기존 JSON 호출은 이전 전송 경로를 유지한다. 명시적으로 검토를 켠
프로필은 최종 확정 후 기존 경로로 전달한다. 인사·문서 목록의 직접 응답은 기존 경로다.

`legal_agent/answer_stream.py`의 요청별 ContextVar가 답변 수신기를 연결한다.
증분 JSON 파서는 `paragraphs[*].text`만 해제해 `answer_delta` SSE 이벤트로 보낸다.
이벤트 계약은 `schema_version=rag-answer-delta-v1`, `request_id`, 1부터 증가하는 `seq`,
`text`다. 원문·ID·근거 선택 이유·숨은 추론은 이 채널에서 전달하지 않는다.
JSON 키 순서와 fragment 경계, 따옴표·백슬래시·줄바꿈·한글·유니코드 surrogate pair를 처리한다.

모델 응답은 한 HTTP 호출에서 수신한다. SSE 전체 이벤트, 복원한 structured response,
실제 model·usage와 응답 해시는 기존 physical attempt 원장에 저장한다. 모델 ID 불일치,
전송 deadline, 단일 choice·structured channel, 입력·출력 계약 검사와 원문·세대·접근 범위
검사는 유지한다. 답변 표시 후 전송 오류에는 같은 모델 요청을 재시도하지 않는다.
형식·의미 보정이 필요하면 기존 예산·원장 경로로 처리하되 두 번째 작성 본문은 실시간으로
덧붙이지 않는다. 최종 결과가 이미 표시한 본문과 다르면 `답변 작성 결과` 아래에 확정 결과를
표시한다. 작성 중 텍스트를 승인된 claim이나 완료 응답으로 자동 저장하지 않는다.

GENOS HTTP 큐는 크기를 제한하고 답변 producer에 backpressure를 건다. 진행 이벤트를
생략하더라도 본문 fragment는 버리지 않는다. 채팅 접속이 끊겨도 underlying 요청 원장은
마무리하고 답변 수신기만 분리한다. 워크플로우는 request ID·연속 seq를 검사하고 같은
채팅 소켓으로 본문을 전달한다. 본문이 시작되면 진행·heartbeat 문단을 본문 중간에 붙이지 않는다.
최종 dict의 `text`는 기존 렌더러의 확정 답변·출처이며, 이미 전달한 본문 prefix를 다시 보내지 않고
남은 본문·출처와 `end`만 전송한다. soft break·`~`의 Markdown 처리도 최종 렌더링과 맞춘다.

서버가 `stream=true` 요청에 JSON을 한꺼번에 반환하면 같은 응답을 처리하며 모델을 다시
호출하지 않는다. 이 경우 본문은 완료 후 표시된다. 실제 점진 수신은 내부 모델과 GENOS
게이트웨이의 streaming 전달에 달려 있으므로 현장 질문으로 확인해야 한다.

## 현장 반영

- [적용 TXT](../../../08_DEPLOYMENT/GENOS/patches/GENOS_ANSWER_STREAM_20260929_R1_APPLY.txt)는 ZIP을
  내장한다. 기존 `~/DEV` Git checkout에서 실행하며 symlink 입구도 실제 Git root로 해석한다.
  첫 단계부터 로그·실패 상태를 남기고, 기존/신규 바이트 해시를 확인한 뒤 백업·적용한다.
  재실행은 `ALREADY_APPLIED`로 확인하며 관련 engine manifest와 PIPELINE pin도 함께 갱신한다.
  알 수 없는 기존 코드나 무관한 pin 오류는 쓰기 전에 중단한다. 데이터·CURRENT를 바꾸지 않는다.
- 적용 영수증의 `gate_zip`은 실제 적용 checkout의 코드·manifest를 담는다. 변경을 검토하고
  commit한 뒤 그 checkout의 Python으로 아래 gate를 실행한다. `SELECTED_GENERATION`에는
  현재 코드서빙 설정/검증 영수증으로 확인한 실제 세대 절대경로를 넣는다.

```bash
cd ~/DEV
.venv/bin/python 06_TOOLS/COMMANDS/genos_release_gate.py \
  --code-zip /적용영수증의/gate_zip \
  --deploy-root "$PWD" --generation "$SELECTED_GENERATION"
```

- gate를 통과한 commit을 push하고 같은 generation을 선택하는 새 코드서빙 리비전을 배포한다.
  기존 `stream_app:app` Run 설정은 사용한다. 데이터 재구축은 필요하지 않다.
- [워크플로우 전체 Python](../../../08_DEPLOYMENT/GENOS/patches/GENOS_ANSWER_STREAM_20260929_R1_WORKFLOW.py)을
  편집기 Python 단계에 별도로 교체·저장·배포한다. 진행 상태도 표시하려면 기존
  `GENOS_RAG_PROGRESS_UI=socketio`를 유지한다. `socketio-final`도 본문 스트리밍을 전달한다.
  `off` 또는 채팅 socket ID가 없는 테스트에서는 최종 dict만 표시된다.
- **워크플로우 테스트 화면에서만** `{"question":"SSE_CHECK"}`를 확인한다.
  `sse_ready=true`, `stream_answer_revision=answer-stream-20260929-r1`,
  `workflow_revision=answer-stream-20260929-r1`을 확인한 뒤 실제 법률 질문을 실행한다.
  작성 완료 전에 첫 본문이 올라오고, 완료 시 본문 중복 없이 출처가 붙어야 한다.
  SSE_CHECK는 전송 앱 표식만 검사하며 내부 모델 SSE 지원을 증명하지 않는다.

## 검증과 복구

모의 모델·자료로 본문 조기 표시, JSON/유니코드 경계, reasoning 비노출, model 결속,
미완료 stream 실패, buffered JSON의 호출 1회, v5 numbered references 검증·commit·
physical attempt 원장, 표시 후 전송 재시도 금지, 세 가지 표시 모드, 큐 260 fragment 무손실,
동시 요청 분리, 실제 TXT의 적용·재적용·원복·데이터 보존·기존 코드 거부를 검사했다.
관련 회귀를 포함해 136개 테스트가 통과했다. 기록은
`09_ARTIFACTS/AUDITS/20260929-answer-streaming/`에 있다.

스트리밍 변경 파일과 이를 참조하는 manifest 26개의 pin은 확인했다. 전체 작업 트리 검사에서는
이 변경과 무관한 `legal_agent/structure_query.py`의 기존 pin 불일치를 별도로 발견했다.
해당 코드·pin은 이 작업에서 승인하거나 갱신하지 않았다. 이를 전체 checkout의 배포 gate
통과로 보고하지 않으며, 현장 적용기도 실제 checkout의 무관한 drift를 별도로 검사한다.

원복은 적용 TXT의 `MODE=rollback ROLLBACK_FROM=백업경로`로 수행한다. 새 module은 삭제하고
기존 코드·pin을 백업 바이트로 복구한다. 이후 변경이 있으면 원복을 거부한다. 이전 코드서빙
리비전과 워크플로우 Python을 함께 복원한다. 코드 적용·Git push·데이터 선택·리비전 배포·
워크플로우 교체·현장 질문 성공은 각각 별도 상태다.

# 통합 `/chat` SSE 현장 확인

현재 통합 코드서빙의 일반 `/chat` 요청은 `GENOS_CHAT_TRANSPORT=json`이면 완성 JSON을
반환한다. JSON의 `agentFlowExecutedData`에 진행 카드가 들어 있거나 채팅창에 진행
문구가 보이는 것만으로 실시간 SSE 수신이 입증되지는 않는다. 이 점검은 기존 정상
JSON 경로를 유지하면서 요청 본문의 `stream: true`로 같은 통합 코드서빙의
`/chat` SSE 경로만 명시적으로 호출한다. 분리 워크플로우의 `/stream`은 점검하지 않는다.

1. GENOS 워크플로우 **테스트 화면**에 진단용 Python 단계를 별도로 만든다. 기존
   채팅 워크플로우의 Python 코드는 교체하지 않는다.
2. `WORKFLOW_PASTE_ALL.txt` 전체를 그 단계에 붙인다. 단계 환경변수에
   `GENOS_BASE_URL`, `GENOS_INTEGRATED_CODESERVING_ID`,
   `GENOS_CODESERVING_TOKEN`(또는 `GENOS_CODE_KEY`)을 넣는다.
   `GENOS_INTEGRATED_CODESERVING_ID`는 `/chat`이 배포된 **새 통합 코드서빙 ID**로
   지정한다. 분리 `/stream` 코드서빙 ID를 넣으면 비교가 무효다.
3. 입력 `{"probe_mode":"contract"}`를 한 번 실행한다. 이는 같은 `/chat`에
   `SSE_CHECK, stream:false`와 `SSE_CHECK, stream:true`를 각각 보낸다.
   둘 다 내부 모델을 호출하지 않는다. 출력의 `json_control`, `integrated_sse`,
   `json_ok`, `sse_ok`를 저장한다.
4. `json_ok=true`, `sse_ok=true`일 때만 입력
   `{"probe_mode":"live","question":"짧은 공개 테스트 질문"}`을 실행한다.
   실제 RAG를 한 번 호출하므로 선택한 데이터 세대와 내부 모델이 준비된 상태에서
   실행한다. `first_progress_token_ms`, `result_ms`, `progress_events`,
   `progress_before_result`를 저장한다. 진단 단계는 질문과 답변을 출력하지 않는다.

판정:

| 결과 | 확인된 범위 | 다음 확인 |
|---|---|---|
| `json_ok=true`, `sse_ok=false` | 같은 코드서빙의 JSON은 통과하지만 `/chat` SSE 계약은 실패 | `integrated_sse`의 HTTP 상태·Content-Type·오류 유형과 코드서빙 로그 확인 |
| 둘 다 `true`, `progress_before_result=false` | SSE 연결은 열리지만 실시간 진행 도착은 입증되지 않음 | `progress_events`, `first_progress_token_ms`, `result_ms`, 코드서빙 설정·프록시 버퍼링 확인 |
| 둘 다 `true`, `progress_before_result=true` | 워크플로우 테스트 단계에서 통합 `/chat`의 진행 토큰이 최종 결과보다 먼저 도착 | 채팅앱의 파싱·표시는 이 점검만으로 판정하지 않음 |

`first_progress_token_ms < result_ms`는 수신 순서의 증거다. 화면에 즉시
렌더링되었다는 증거는 아니다. `result_ms`와의 시간 차도 함께 보고
프록시가 이벤트를 모았다가 한 번에 넘기는지 판단한다. 현장 로그 없이
"통합 SSE가 안 된다"고 확정하지 않는다.

통합 SSE 계약과 소비 경로를 별도로 확인한 뒤 새 코드서빙 리비전의 기본값을
`GENOS_CHAT_TRANSPORT=sse`, `GENOS_RAG_PROGRESS_UI=sse-inline`로 지정하면 일반
`/chat` 질문도 진행 토큰을 받는다. 문제가 있으면 `GENOS_CHAT_TRANSPORT=json`으로
복귀한다. 이 설정은 코드 적용과 별개로 새 리비전 배포·채팅앱 바인딩 확인이
필요하다. Socket.IO 옵션은 계속 끈다. 진단 워크플로우 단계는 운영 채팅 흐름에
연결하지 않는다.

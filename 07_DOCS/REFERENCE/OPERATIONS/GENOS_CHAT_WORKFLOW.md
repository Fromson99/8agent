# GENOS 채팅 화면 연결

2026-10-29 출처 원문 펼치기를 **MAIN118 / source-accordion-20261029-r1**에 반영했다. 출처 버튼 → 개별 상자 → 확보 원문 펼침/접힘으로 동작한다. [GENOS 반입 안내](../../../../08_DEPLOYMENT/GENOS/handoffs/source_accordion_main118_20261029_r1/GUIDE.txt)에 코드서빙·워크플로우 편집기 적용을 구분했다. 로컬 선택서비스 검증을 마쳤으며 현장 배포/화면은 미확인이다.

2026-10-06 후속 로깅은 최신 RAG의 `progressive-cursor-v2` 조사·재개 계약에 맞춘다.
표시 revision은 `agent-input-action-output-20261006-r1`이다. 실제 모델 전송의 질문·작업·
자료 수와 일부 위치를 짧게 표시하고, 출력의 다음 행동·읽기 제안·새 검색어·충분성 판단을
요약한다. 모델 출력 수신은 제안이며 실제 READ 완료와 근거 채택을 구분한다.
전체 입력·출력·원문과 재개 checkpoint는 기존 journal/요청 보고서에 보존한다.

Fulltext 결과는 현재 문서 범위를 검증한 뒤 조·항·호·목을 순서대로 표시한다.
긴 목록은 여러 이벤트로 이어서 출력한다. `UNIT_READ_CHOICE`는 입력 위치·선택 범위·
이유를 표시하고 실제 READ는 묶음 안의 각 위치·확보 상태·기존 원문 재사용·새 구간 수를
구분한다. 최종 채택은 해시로 검증한 native SELECT의 `selected_originals.evidence_ids`만
사용한다. 같은 조에서 읽었지만 선택하지 않은 항·호를 채택 목록에 포함하지 않는다.
저장 `.log`도 같은 native 판단 projection을 사용한다. 표시용 LLM 호출은 추가하지 않는다.

조사 상태는 근거 충분, 연결 조사 미완료, 새 검색 요청, 후보 묶음 한도, 후보 소진을
구분한다. 미완료를 근거 채택·조사 완료로 표시하지 않는다. 최초 원문으로 충분성이 확인된
경로도 추가 연결 읽기를 생략한 이유를 표시한다. 검색·읽기·선별·재개 계약은 유지한다.

위치별 활동 이벤트는 문서별 요약으로 접히지 않는다. 진행을 본문에도 순서대로 보려면
워크플로우 환경의 `GENOS_RAG_PROGRESS_UI=socketio-inline`을 사용한다. `socketio`는
Reasoner에 표시하며 기존 `socketio-final`/`off` 설정은 유지한다. Reasoner 배열의 기존
최대 80개 노드와 느린 연결에서 진행 이벤트를 생략할 수 있는 SSE 큐 제한은 남아 있다.
전체 검색·읽기 기록은 journal/저장 로그에서 확인한다.

작업 코드의 source recall·unit READ/SELECT·진행 projection·요청 로그와
`08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`에 연결하고 엔진 코드 hash를 갱신했다.
관련 모의 계약·회귀 107개와 Python3.11 구문 검사를 통과했다. 기존 통합 테스트의 16개
실패는 로깅 수정 전후 같은 실패 목록으로 확인했으며 통합 전체 PASS로 처리하지 않는다.
[검증·수정 전후 대조](../../../09_ARTIFACTS/AUDITS/20261006-rag-activity-log/after-other-rag/verification.json).
활성 frozen 로컬 MAIN·NFS generation/CURRENT는 전환하지 않았다. GENOS 적용에는 새
코드서빙 리비전과 워크플로우 Python 편집기 전체 코드 반영을 각각 확인해야 한다.
현장 배포·내부 모델 판단·실제 화면 렌더링은 미확인이다. 아래 기록은 당시 표시 이력이다.

2026-10-06 사용자 요청으로 원문 열람 화면 로그를 문서별 요약으로 바꿨다.
`_ChatProgress`는 허용된 `reading`/`read_complete` 이벤트의 문서·위치 표기를 모아
같은 종류의 Reasoner 노드를 갱신한다. 두 열람 요약 외의 단계·선택 이유·대기·답변은 유지한다.
서로 다른 원문 위치는 내부 집계에 남기지만 화면에는 첫4개 문서의 건수와 나머지 문서 수를
표시한다. 일부→완료 상태 변경은 같은 위치의 갱신이며 건수를 중복 가산하지 않는다.
표시 건수는 문서명/위치 표기로 합친 값이지 정확한 canonical source 개수나 독립 법률 근거
개수로 인증하지 않는다. 숫자 마디 ID를 사용자 화면에 길게 나열하지 않는다.
`socketio-inline`은 각 열람 요약을 본문에 한 번만 추가하며 최신 누적 건수는 Reasoner와
최종 반환 배열에 갱신한다. 임의 단계·최종 답변을 삭제하거나 숨기지 않는다.

표시 revision은 `reasoner-display-read-summary-20261006-r1`이다.
기존 `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py` 전체를 워크플로우 Python 편집기에
반영·저장·배포하고 `WORKFLOW_SETTINGS`에서 revision을 확인한다. 코드서빙의 원문 검색·READ·
상세 원장과 세대/CURRENT는 이 표시 변경으로 바뀌지 않는다. `/chat`은 같은 파일의 표시 함수를
읽으므로 `/chat` 실행 환경은 해당 파일을 포함한 코드 배포가 별도로 필요하다. 이전 파일로
원복할 수 있으며 데이터 재구축·로그 원장 삭제는 필요 없다. 현장 반영/표시 검증은 미실행이다.

검증: 표시/채팅 진행 관련29개 검사와128마디 반복·두 모드·부분→완료·중복·옛 전송 배열 보존·
선택 이유·최종 답변 보존·Python3.11 문법 통과. 확대 답변/SSE 검사에는 AD_PROBE 호출 이전을
가정하는 기존 fixture 실패18개가 있으며, 변경 전 sql-ad-mode-v6 frozen workflow에도 동일한
18개 실패를 확인했다. 기존 fixture와 신규 AD 전송 계약의 차이를 표시 성공으로 처리하지 않는다.

2026-10-02 현행 작업 코드의 진행 표시는 `legal-agent-unified-v6`의 실제 native journal을
읽는다. INTENT·PLAN·RECALL·READ·SELECT·ASSESS·COMPOSE의 해시가 일치하는 수락 기록만
단계 완료로 표시한다. 정정은 실제 재실행한 단계만, 확정 경험 재사용은 `재결속`으로
구분한다. 추가 원문 재검색·판단/표현 수정·최종 경험 저장 상태도 실제 기록에 연결한다.
원문 제목은 검증된 run binding과 현재 사건의 문서 범위에 한정하며 답변 본문·전체 모델
출력·개인 조건을 진행 이벤트로 내보내지 않는다.

기존 사진의 `agentFlowExecutedData` **누적 배열** 및 각 노드의
`data.output.content` **JSON 문자열**(`visible_rationale`)을 유지한다. 각 알림 노드의
`status=FINISHED`는 알림 전달 형식이며, 전체 RAG/법률 검증 완료를 의미하지 않는다.
진행 표시와 답변 token/end 전달은 기존 경로를 사용한다. `socketio`는 Reasoner 패널,
`socketio-inline`은 기존 본문 진행 표시, `socketio-final`·`off`는 기존 표시 선택을 유지한다.

코드서빙은 수정된 `progress.py`·`stream_app.py`와 해당 코드의 엔진/PIPELINE 해시를 함께
배포한다. 별도로 `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py` 전체를 편집기에 반영한다.
워크플로우 테스트 화면의 `WORKFLOW_SETTINGS`에서 `progress_display_revision`은
`reasoner-display-v6-20261002-r1`, `SSE_CHECK`에서 `stream_progress_revision`은
`chat-flow-v6-20261002-r1`이어야 한다. 동일한 코드가 CI/CD의 `/chat` 함수 배선으로
이관된 뒤에는 그 배포 커밋과 워크플로우 바인딩을 확인한다. 이번 수정으로 해당 이관이나
현장 배포가 완료되지는 않는다. 모의 v6 실행·정정·재사용·실패·기존 화면/스트리밍 회귀
130개, v6 plan과 Python 3.11 구문을 확인했다. GENOS 현장 화면 표시는 미확인이다.

아래 2026-10-01 기록은 누적 배열/JSON 문자열 형식의 최초 적용 이력이다.
2026-10-01 현행 워크플로우 진행 표시 `reasoner-display-20261001-r1`은 사용자 사진처럼
누적 `agentFlowExecutedData` 배열과 각 노드의 `data.output.content` JSON 문자열을
전송한다. `socketio` 모드에서는 진행 문구를 Visible Reasoner에 표시하고 답변 본문은
기존 답변 SSE/최종 text 경로를 사용한다. 기존 본문 진행 표시는 `socketio-inline`로
선택한다. 기본 `socketio-final`·`off` 설정은 유지한다. 단계·원문 열람·판단 요약의
소비자는 기존 GENOS 채팅이며 검색/모델/서버 이벤트 계약은 변경하지 않는다.
워크플로우 Python 전체 교체·저장·배포와 채팅 앱 연결이 필요하다. 코드서빙 재배포나
데이터 재구축은 필요 없다. 로컬 관련 검사 118개 통과이며 현장 화면 표시는 미확인이다.
[전체 교체 Python](../../../08_DEPLOYMENT/GENOS/patches/GENOS_REASONER_DISPLAY_20261001_R1_WORKFLOW.py),
[설정·테스트·복구](../../../08_DEPLOYMENT/GENOS/patches/GENOS_REASONER_DISPLAY_20261001_R1_GUIDE.txt).
아래 R2 본문 표시 설명은 이전 형식의 기록이다.

2026-09-28 현행 작업 코드 `chat-flow-20260928-r2`는 R1의 진행 토큰에 Markdown
문단 간격을 넣고 단계를 번호로 구분한다. 실제 원문 reader가 여는 문서·조문,
원문 확보의 완료/일부 상태, 커밋된 근거의 채택·제외·보류와 이유, 질문의 확인
사항, 수행한 도구의 결과, 저장된 검토 결과를 별도 줄에 표시한다. 문서명은
해당 run의 해시 검증된 서버 binding에 포함된 document scope에 한정한다.
원문 본문·모델의 숨은 추론·전체 응답 JSON은 진행 이벤트에 넣지 않는다.
같은 문서의 페이지 알림은 합치고 모델 응답 수신/형식 검증 반복은 표시하지 않는다.
30초 heartbeat와 최종 반환 답변은 유지하며, 스트리밍 본문에는 최종 답변 구분선을 둔다.

`GENOS_CHAT_FLOW_20260928_R2_APPLY.txt`를 기존 `~/DEV`에 적용하면 네 소스 파일과
그 파일을 참조하는 엔진/PIPELINE 코드 해시만 함께 갱신한다. 데이터 generation과
CURRENT는 유지한다. commit/push와 코드서빙 리비전 배포 후, 별도로
`GENOS_CHAT_FLOW_20260928_R2_WORKFLOW_PASTE_ALL.txt` 전체를 워크플로우 Python 편집기에
반영한다. `GENOS_RAG_PROGRESS_UI=socketio`를 사용하며 명시적 final/off 설정은 보존한다.
워크플로우 테스트의 SSE_CHECK에서 두 진행 revision이 `chat-flow-20260928-r2`인지
확인한다. 다음은 이전 R1의 변경 이력이며 R2의 실제 현장 반영은 아직 미확인이다.

2026-09-28 `chat-status-20260928-r1`은 사용자에게 보이는 채팅 본문에도 실제 진행
단계와 대기 경과 시간을 보낸다. 이전 코드는 고정 안내 토큰만 보내고 단계는
Visible Reasoner 패널에만 전달했다. `socketio` 모드에서 실제 단계가 달라지면
`진행 · 관련 자료를 검색 중`, `진행 · 후보 원문을 열람 중`,
`진행 · 답변 초안을 작성 중 · 내부 모델 대기` 등 기존 이벤트의 문구를 토큰으로
추가한다. heartbeat는 마지막 확인 단계와 요청 경과 시간을 30초 간격으로 표시한다.
동일 단계 반복은 생략하고 같은 단계의 건수 변경은 최대 5초 간격으로 표시한다.
Reasoner 블록이 80개여도 본문 상태는 계속 전달한다. 반환 답변·원장·근거는 보존한다.

지난 SSE 시작 수정의 지연 service import가 첫 요청에서 로깅을 초기화하면서
ProgressCapture를 제거하던 문제도 재현했다. `stream_app`의 요청 worker가 로깅을
먼저 구성한 뒤 수집기를 붙이도록 순서를 수정한다. HTTP 시작은 여전히 자료를
적재하지 않는다. 서버와 워크플로우의 진행 리비전은 `chat-status-20260928-r1`이며
기존 서버 시작 리비전은 `sse-startup-20260928-r1`로 유지한다.

기존 시작 수정 R1 위에 `GENOS_CHAT_STATUS_20260928_R1_APPLY.txt`를 적용하고 두 파일을
검증 commit/push하여 새 코드서빙 리비전을 배포한다. 별도로
`GENOS_CHAT_STATUS_20260928_R1_WORKFLOW_PASTE_ALL.txt` 전체를 워크플로우 Python 편집기에
교체하고 저장·배포한다. 워크플로우 환경의 `GENOS_RAG_PROGRESS_UI=socketio`가 필요하다.
`socketio-final`·`off`는 기존 표시 선택을 유지한다. Run·Build·데이터·CURRENT·엔진
pin은 변경하지 않는다. SSE_CHECK에서 `workflow_revision`과 `stream_progress_revision`을
확인하고 실제 채팅에서 최종 답변 전 상태 문구가 보이는지 확인한다. 워크플로우 테스트에는
채팅 socket ID가 없을 수 있다. 로컬 61개 검사는 통과했으며 현장 표시 성공은 미확인이다.

**현장 검증은 워크플로우 테스트 화면만 사용한다.** 코드서빙 직접 테스트를 요구하지 않는다.
2026-09-25 r2부터 이 파일의 연결 코드(`08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`)
전체를 워크플로우 Python 단계에 교체하면 `{"API_TYPE":"WARMUP"}`와
`{"API_TYPE":"WARMUP_STATUS"}`도 같은 테스트 화면에서 실행된다.
질문 없는 입력의 ID/UUID는 질문으로 사용하지 않는다. 일반 질문은 `{"question":"실제 질문"}`다.
DEV 파일 적용·코드서빙 재배포만으로 이미 저장된 워크플로우 Python 코드가 바뀌지는 않는다.

2026-09-28 `timeout-sync-20260928-r1`은 `/json`과 `/stream` 모두
`GENOS_CODESERVING_TIMEOUT_SECONDS`(기본 2100초)를 읽는다. 이전 `/stream`의
35초 고정 소켓 대기는 제거했다. 같은 이름의 환경변수는 한 항목만 남긴다.
워크플로우 테스트 입력 `{"API_TYPE":"WORKFLOW_SETTINGS"}`는 모델/HTTP 호출 없이
실제 저장 리비전과 두 경로의 적용 대기값을 반환한다. `WORKFLOW_SETTINGS`를 질문으로
입력해도 같다. 주소·인증키·질문·원문은 설정 결과에 포함하지 않는다.
HTTP 500은 `failure_kind=http_error`, `http_status=500`, `tm_total`을 반환하며,
클라이언트 예외는 `failure_kind=client_exception`과 실제 `error_type`을 반환한다.
플랫폼 바깥의 success는 이 실패 안내 dict의 반환 성공일 수 있다.
`code_serving.stream.request.started/response.opened/request.failed/result.received`와
기존 `/json` 이벤트에는 `workflow_revision`이 포함된다.
[전수 확인·전체 ZIP 적용·현장 검증](GENOS_TIMEOUT_SYNC_20260928.md).

2026-09-28 후속 `sse-transport-20260928-r1`에서는 법률 질문을 소켓 ID와
진행 표시 설정과 관계없이 `/stream`으로 보낸다. `off`여도 전송은 SSE다.
진행 표시를 원하면 **워크플로우 환경 설정**을 `GENOS_RAG_PROGRESS_UI=socketio`로
저장·배포한다. 소켓 ID는 GENOS 채팅이 자동 전달하는 값을 사용한다.
시작 앱/새 리비전 연결은 워크플로우 테스트의 `{"question":"SSE_CHECK"}`로 확인한다.
이하 과거 `/json` 선택 설명은 변경 전 기록이며
[최신 SSE 인계](GENOS_SSE_TRANSPORT_20260928.md)를 따른다.


## 2026-10-29 출처 원문 펼치기 — 작업 코드

사용자 요청으로 기존 경로/문서명 목록을 `출처 · N건` 버튼과 문서별 접이식
박스로 바꿨다. 출처를 누르면 목록이 열리고 각 박스를 누르면 응답에 연결된
원문이 아래로 펼쳐진다. 다시 누르면 접힌다. 문서명·조항·있을 경우 판본을
표시하며 원문의 빈 줄·문자·긴 본문을 보존한다.

공통 표시 함수는 `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`의
`_source_cards`다. 일반 RAG는 채택된 `assembly.context[].text`, v4/v5와
이전 대사 응답은 검증된 source bundle의 `spans[].text`를 쓴다. 과거 응답에
spans 필드가 없으면 저장된 text/excerpt를 사용한다. 새 원문을 조회하거나
요약을 생성하지 않는다. 원문 없는 과거 답변은 미저장 안내, 미확보 후보는
표시 제외, 부분 확보는 확보한 범위만 보여 준다. 다른 판본·원문 범위는
제목이 같아도 합치지 않는다. 이미 원문을 접어서 표시하는 대사표는 유지한다.

native `/chat` JSON/SSE와 workflow 표시가 같은 렌더러를 사용한다.
`ANSWER_DISPLAY_REVISION=workflow-source-accordion-20261029-r1`로 이전
표시 결과의 재사용을 막는다. HTML/Markdown 문자는 실행하지 않고 원문으로
표시하며 새 브라우저 API 경로나 모델 호출은 필요 없다.

이번 완료 범위는 작업 코드·로컬 검사·모의 브라우저 확인이다. 선택 MAIN117과
GENOS 현장은 변경하지 않았다. GENOS 적용 시 코드서빙에 이 파일을 포함하고,
별도 workflow Python 단계를 사용하는 환경은 편집기 코드도 함께 반영해야 한다.
현장 HTML 허용/스타일과 실제 클릭은 워크플로우 테스트 화면에서 확인한다.
[검사 결과·미리보기](../../../../09_ARTIFACTS/AUDITS/20261029-genos-source-accordion/결과.txt).

## 2026-09-24 채팅 답변 형식 (이전 기록)

워크플로우는 법률 답변 뒤에 실제 채택된 문서명·조문 위치를 핵심/보완으로
구분해 `출처` 목록으로 붙인다. GENOS 채팅에서는 원문 API 경로를 링크로
넣지 않는다. 채팅의 링크 렌더링과 브라우저 열람 경로가 확인되지 않은 상태에서
상대 URL이 출처명 대신 노출된 현장 사진을 반영했다. 원문 열람 경로는 API의
`source_bundle.sources[].open_url`에 남는다.
v3의 `claim.source_ids`와 v4/v5의 검증된 source bundle을 각각 사용한다.
`확인 한계`, 실행 원장, 모델·검토 상세는 사용자 채팅 본문에 붙이지 않고
API 결과와 요청 원장에 남긴다. 열람 경로가 없어도 확인된 문서명·좌표는
표시한다. 원문 본문과 미채택 탐색 후보는 채팅의 출처 목록에 넣지 않는다.

2026-09-29 작업 코드는 v5 최종 작성의 본문을 `answer_delta` SSE로 받아 생성 중 표시한다.
완료 시 이미 보낸 본문을 반복하지 않고 남은 문장·출처를 붙인다. 내부 모델·게이트웨이의
점진 전달은 현장 확인 대상이며 코드서빙과 편집기 Python을 각각 적용해야 한다.
[현재 본문 스트리밍 계약](GENOS_ANSWER_STREAMING_20260929.md)을 따른다.

아래는 2026-09-25 당시 동작이다. 채팅 소켓 ID가 있으면 `socketio-final`을 기본으로 시도한다.
검증된 최종 답변은 생성이 끝난 뒤 조각으로 전달한다. `socketio`를 명시한 경우에만
답변 생성 중 진행 상태도 전달한다. 모델의 문장 생성 자체를 토큰별로 전달하는 방식은 아니다.
`GENOS_RAG_PROGRESS_UI=off`로 소켓 출력을 끌 수 있다. 기본 코드서빙에서
`/stream`을 제공하지 않으면 `/json`으로 복귀한 뒤 최종 답변만 조각으로 보낸다.
GENOS 현장 동작은 미확인이다.

2026-09-23 마지막 발송 ZIP `8agent-genos-readable-stage-log-20260923.zip`에는
아래 `/stream`과 Visible Reasoner 구현이 없다. 후속 패치노트 메일도
설명 TXT만 포함했으므로, 진행 표시에는 최신 전체 코드와 워크플로우
리비전 적용 및 채팅 앱 재연결이 필요하다.

## 2026-09-23 법률 에이전트 진행 표시 작업 코드

기존 GENOS **채팅 앱**을 그대로 쓴다. 워크플로우 Python 단계는
`08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`의 `run(data)`를 사용하고,
최종 답은 계속 `{"text": ...}` dict로 반환한다. 별도 프론트엔드가 필요하다는
설계가 아니다. 원장의 원문·모델 응답·숨은 thinking은 채팅에 보내지 않는다.

진행 표시를 켜려면 같은 코드서빙 리비전에서 커스텀 HTTP 시작 명령을 사용할 수 있어야 한다.
저장소 루트 기준 시작 명령의 예시는 다음과 같다. 포트는 해당 GENOS 리비전이 지정한
실제 수신 포트로 바꾼다. 이 명령은 **현장 미검증**이며, 플랫폼의 기본 `service(config,data)`
적재 방식은 `/stream`을 만들지 않는다.

```bash
uvicorn stream_app:app --app-dir 08_DEPLOYMENT/GENOS --host 0.0.0.0 --port <리비전 수신 포트>
```

이 앱은 `POST /json`에서 기존 `service()` 결과를 유지하고, `POST /stream`에서
동일한 `LEGAL_AGENT` 요청을 **한 번** 실행한다. SSE에는 검증된 단계·건수·경과 시간만
내보낸다. `OBSERVATION`의 열람 완료, 현재 근거 선택, 근거 철회, 검토 커밋을 구분한다.
현재 워크플로우에서 사용자별 내부 문서 열람 권한이 코드서빙으로 전달되는 계약은
확인되지 않아 진행 이벤트에 내부 문서명·원문·조문 좌표를 싣지 않는다.

워크플로우 리비전의 환경 설정에서 `GENOS_RAG_PROGRESS_UI=socketio`로 켜면
`/stream`을 읽고 `socketIOClientId`의 GENOS 채팅 소켓으로 `token`과
`Visible Reasoner` 블록을 보낸다. 마지막에 답 텍스트 토큰과 `end`를 보낸 뒤
`{"text": ..., "agentFlowExecutedData": [...]}`를 반환한다. 현재 `off`는
소켓 표시만 끄고 SSE 전송을 유지한다. `/stream`이 실행 **전** 404/405를 반환한 경우에만
`/json`으로 한 번 대체한다. 중간 연결 오류에서는 중복 법률 요청을 막기 위해
재실행하지 않는다. 2026-09-27부터 GENOS v5 기본 요청 예산은 1800초이며
워크플로우 호출 대기는 `GENOS_CODESERVING_TIMEOUT_SECONDS=2100`을 사용한다.
이미 저장된 360초 설정은 직접 변경해야 한다. 플랫폼 자체의 절대 제한은
이 설정으로 늘어나지 않는다. [전체 시간 설정](GENOS_FULLTEXT_WAIT_20260927.md).

현장에서는 짧은 모의 이벤트로 **최종 답변 전 진행 블록 표시**와 토큰/최종 dict의
답변 중복을 먼저 확인한다. 상위 V1.8.6 기록은 `token`, `nodeId`, `FINISHED`,
`Visible Reasoner`/`visible_rationale`, 최종 반환 블록, `end`를 모두 요구한다.
모의 확인용 Python 단계는 아래처럼 실제 질문·원문 없이 시험할 수 있다.

```python
import asyncio

async def run(data):
    from main_socketio import sio_server
    sid = data["socketIOClientId"]
    block = {"nodeId": "progress-probe-1", "nodeLabel": "Visible Reasoner",
             "status": "FINISHED", "content": {"visible_rationale": "자료 확인 중"}}
    await sio_server.emit("token", "확인 중입니다.\n\n", room=sid)
    await sio_server.emit("agentFlowExecutedData", block, room=sid)
    await asyncio.sleep(2)
    await sio_server.emit("token", "표시 확인", room=sid)
    await sio_server.emit("end", "end", room=sid)
    return {"text": "표시 확인", "agentFlowExecutedData": [block]}
```

코드서빙 게이트웨이에서 SSE가 조각별로 도착하는지도 확인한다. 서버 로그에 이벤트가
있어도 채팅이 마지막에 한꺼번에 그리면 실시간 표시 성공으로 보지 않는다.
채팅 앱이 기존 워크플로우 리비전에 고정되어 있으면 새 리비전 배포 후 앱 버전도
새 워크플로우에 재바인딩해야 한다. 코드서빙·워크플로우·채팅 바인딩의 실제 배포와
내부 모델 질문 E2E는 이 작업에서 수행하지 않았다.

진행 표시를 끈 기본 설정에서 GENOS 채팅 화면은 다음 경로로 답을 받는다.

`화면 질문 → 워크플로우 run(data) → 코드서빙 LEGAL_AGENT → /v1/rag/ask → {"text": ...} 반환`

2026-09-22 팀 선택은 입력의 `team_id`로 전달한다. [호출·팀 선택 계약](GENOS_LEGAL_AGENT_TEAMS.md)을 따른다.

먼저 [GENOS.md](../../../GENOS.md)의 환경·버전 기준을 확인한다. 2026-09-11 현재
[브릿지 코드](../../../08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py)의 `run(data)`는
완성된 답변을 `text`가 있는 dict로 반환하며 `yield`하지 않는다. 코드서빙이 만든 답변을
별도 LLM으로 재생성하지 않고, 실제 claim이 사용한 문서만 출처로 붙인다.

상위 main의 현장 V1.8.6 기록도 dict 반환이며, 데모 v1.9.1의 JSON token/end yield 규약과
다르다. 예전 “dict return이면 채팅 실패” 설명은 데모 기준으로만 읽는다.
다른 버전에 배포할 때는 그 환경의 반환 계약을 확인한다. 현재 코드 확인은 현장 배포 성공의 증거가 아니다.
근거: [버전별 현장 기록](../GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md).

## 1. 코드 저장소 적용

아래 `genos_apply_chat.sh` 절차는 해당 설치기가 포함된 인계본용이다. 설치 파일이 없거나 버전이 다르면 현재 커밋의 배포 절차를 사용한다.

전달 ZIP을 `/home/genos/DEV/TRANSFER`에 놓은 뒤 다음을 실행한다.

```bash
cd /home/genos/DEV/TRANSFER
bash genos_apply_chat.sh
```

스크립트는 기존 `/home/genos/DEV/service.py`를 전달본의 완성된 `service.py`로 교체하고
워크플로우 파일을 `/home/genos/DEV/08_DEPLOYMENT/GENOS/workflow/` 아래에 설치한다.
기존 service 파일은 `/home/genos/DEV/.genos-chat-backup-*`에 먼저 백업된다. 이후 변경을
Git에 커밋·push하고 그 커밋으로 코드서빙을 다시 배포한다.

## 2. GENOS 워크플로우 생성

GENOS 워크플로우 편집기의 Python 단계에 아래 파일 전체를 붙여 넣는다.

`08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`

진입 함수는 `run`이다. 채팅 앱 입력 전체를 `data`로 연결한다. `run`은 완성된 답변을
`text`가 있는 dict로 한 번 반환한다.

워크플로우 리비전 환경변수에는 주소, 코드서빙 ID, 토큰을 각각 넣는다. 워크플로우
코드가 이 값으로 최종 호출 URL을 조합한다.

```text
GENOS_BASE_URL=http://<GENOS주소>
GENOS_CODESERVING_ID=<코드서빙ID>
GENOS_CODESERVING_TOKEN=<코드서빙 API 인증키>
GENOS_CODESERVING_TIMEOUT_SECONDS=2100
GENOS_RAG_PROGRESS_UI=socketio-final
TEAM_ID=risk_team
```

기본 URL은 코드에서
`{GENOS_BASE_URL}/api/gateway/code_serving/{GENOS_CODESERVING_ID}/json`으로 만든다.
진행 표시를 켜면 같은 코드서빙 ID의 `/stream`을 사용한다.
`GENOS_CODESERVING_URL`은 사용하지 않는다.

LLM 서빙 ID와 코드서빙 ID는 서로 다르다. 여기에는 코드서빙 ID를 넣는다. 키는 저장소나
워크플로우 코드에 쓰지 않는다.

## 3. 코드서빙 직접 확인

워크플로우 연결 전 코드서빙이 답을 내는지 먼저 확인한다. 아래 명령은 토큰을 명령행 인자나
히스토리에 직접 남기지 않는다.

```bash
python - <<'PY'
import json, os, urllib.request

base = os.environ["GENOS_BASE_URL"].rstrip("/")
serving_id = os.environ["GENOS_CODESERVING_ID"]
url = f"{base}/api/gateway/code_serving/{serving_id}/json"
token = os.environ["GENOS_CODESERVING_TOKEN"]
body = json.dumps({
    "API_TYPE": "LEGAL_AGENT",
    "team_id": "risk_team",
    "question": "내규상 승인 절차를 알려줘",
    "channel": "genos-chat-test",
    "session_id": "manual-test-1",
    "user_id": "manual-test",
}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(url, data=body, method="POST")
req.add_header("Authorization", "Bearer " + token)
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req, timeout=120) as res:
    print(json.dumps(json.loads(res.read()), ensure_ascii=False, indent=2))
PY
```

정상 응답은 바깥에 `status: 200`, 안쪽 `body.answer.text`에 답변이 있다.

## 4. 화면 연결 확인

워크플로우를 저장·배포한 뒤 채팅 앱이 새 워크플로우 리비전을 선택했는지 확인한다. 화면에서
질문을 보내면 응답 객체의 `text`가 답변으로 표시된다. 진단용으로 `run_id`, `session_id`,
`tm_code_serving`, `tm_total`도 반환한다.

현재 `session_id`는 요청 추적용으로 전달되지만 대화 이력은 저장하지 않는다. 후속 질문이 앞선
대화를 자동으로 기억해야 한다면 별도의 승인된 세션 저장소와 이력 계약이 추가로 필요하다.

## 장애 구분

- `코드서빙 응답 401/403`: 코드서빙 인증키 또는 워크플로우 권한 문제
- `코드서빙 응답 404`: 코드서빙 ID나 URL 경로 문제
- `코드서빙 응답 422`: 질문/활성 데이터/LLM 구성 계약 문제. 코드서빙 로그의 상세 오류 확인
- `지금 답변을 가져오지 못했습니다`: 워크플로우에서 코드서빙까지의 네트워크 또는 설정 문제
- `관련 근거를 찾지 못해`: 호출은 성공했지만 활성 데이터에서 답변 근거를 만들지 못한 상태

## 2026-10-06 묶음 열람·충분 시 중단 R1

사진의 수백 개 Reasoner 카드에서는 같은 ID 갱신도 별도 카드로 쌓였다.
`reasoner-display-read-batches-20261006-r2`는 열람 중/확보 확인 채널을 각 한 번 전달하고
최종 누적 현황을 전달한다. 내부 현황·최종 판단 원문 목록과 상세 감사 원장은 유지한다.
위치 표시는 구조 surface의 상위 조·항·호·목을 연결하며 숫자 unit ID만 표시하지 않는다.
열람 위치 수는 전체 법령 통독/최종 채택 수가 아니다.

backend READ는 같은 조의 검색 단위와 상위 직접 본문을 묶어 먼저 12묶음 확보한다.
SELECT가 채택 원문과 필수 연결을 검토하고 충분 판정하면 미열람 후보를 보존한 채 중단한다.
부족하면 다음 묶음, 최대 8차수다. 필수 연결 미확인/빈 채택은 충분함으로 처리하지 않는다.
모든 최초 후보를 먼저 읽던 방식과 다른 계약이며 새 데이터 세대는 필요하지 않다.
[정확한 누적 ZIP/실행/편집/검증/원복](../../../08_DEPLOYMENT/GENOS/handoffs/progressive_reading_20261006_r1/GUIDE_UTF8.txt).
실제 GENOS 내부 모델 품질·렌더링·응답 시간은 현장 확인 전까지 미확인이다.

# 분리 워크플로우의 실시간 행위 카드 복구

현재 적용본은 `workflow_live_progress_20261008_r4`다. 사용자는 R3에서 답변 본문에
나온 “준비 중 · 자료와 요청 설정을 확인하고 있습니다”를 제거하되 GENOS의 접이식
추론·행위 로그를 유지하라고 정정했다. R4는 첫 카드 직전의 준비 token 송신을 제거했다.
준비·실제 행위·현재 판단 카드는 동일한 `agentFlowExecutedData` 경로로 보내고,
답변 token에는 검증한 최종 답변만 보낸다. `end`와 실제 송신한 카드의 최종 배열도 유지한다.
기존 `socketio-inline` 설정은 R4에서 `socketio`로 연결해 본문 진행 문구가 다시 붙지 않게 했다.
준비 상태는 패널 안에만 남으며 최종 답변 전 본문 token은 없다.

R3의 첫 준비 token은 수집 문서의 “답변 token 송신이 필요”를 “카드보다 먼저 필요”로
확대한 구현 선택이었다. 앞서 보존한 `df411b96`의 GENOS 514 브릿지는 누적 카드 후
실제 답변 token, 마지막 end 순서다. 카드 전 준비 문구를 필수로 볼 근거는 없다.
R2의 검사 실패는 당시 추가한 token 선행 가정에 따른 것이며 현장 패널 실패 실측이 아니다.
아래 R2/R3 설명과 원본 로그·봉인 발송 파일은 당시 이력으로 보존한다.

R4의 적용 위치는 기존 분리 워크플로우 Python 편집기다. R3 전체 TXT를 R4 전체 TXT로
교체해 저장하며 backend R5 ZIP·별도 SSE 서버·endpoint/ID/token/port·데이터 세대·DB·CM·
조사 예산·오류 로그·로컬 MAIN45를 유지한다. 현장 질문은 워크플로우 테스트 화면에서 확인한다.
로컬 관련 계약102개와 실제 전체 편집기 TXT12개가 통과했다. 지연된 AD_PROBE와 최종
SSE 결과 전 카드 송신, 그동안 본문 token 없음, 최종 답변만 본문 송신, 최종 카드 일치,
기존 본문 모드 별칭, SVG/현재 판단/전체 오류 보존을 확인했다. 신규 모델 호출은 없다.
검증은 `09_ARTIFACTS/AUDITS/20261008-workflow-panel-only-r4/`에 보존하며 실제 GENOS
브라우저 렌더링과 편집기 저장은 미확인이다.
최종 ZIP/PREPARE의 준비·재실행·기존 backend/데이터 보존·변경 파일/링크 보존
계약4개도 통과했다. ZIP 전체 member hash와 독립 TXT 해시를 확인했다.

사용자 현장 보고: 오늘 SVG 인계 이전에는 채팅 화면에서 최종 답변 전에 접을 수 있는 에이전트 행위 로그가 나왔다. R5 반영 이후 보이지 않으며 준비 중 표시도 필요하다. 실제 현장 코드·편집기 hash는 제공되지 않았다.

이전 구현은 `08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261007_r1/WORKFLOW_PASTE_ALL.txt`에 있다. 그 `_ChatProgress`는 입력 `socketIOClientId`를 받아 워크플로우 런타임의 `main_socketio.sio_server.emit`으로 `agentFlowExecutedData` 누적 카드를 보낸다. 별도 코드서빙의 `/stream` HTTP SSE 수신과 화면 카드 송신은 이 경로에서 이어진다. 이 구 인계의 실시간 계약 4개를 다시 확인했다.

반면 실제 발송 R5의 전체 workflow TXT는 `sid=''`, `enabled=False`, `show_inline_progress=False`이며 `_send`는 `emit=None`이면 반환한다. 별도 Python 단계의 `run`에는 송신기를 연결하는 코드가 없다. `WORKFLOW_SETTINGS`도 모드를 항상 off로 보고한다. 따라서 SSE를 읽고 최종 카드 JSON을 반환해도 처리 도중 채팅에는 송신하지 않는다. 서버 SSE_CHECK/최종 응답 통과만으로 이 화면 경로를 검증하지 못했다. 준비 전에 수행되는 AD_PROBE도 표시 생성보다 앞에 있어 첫 요청 준비 지연 중 화면이 비어 있었다.

작업 코드 `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py:run`에 구 카드 송신을 필요한 부분만 통합했다. SVG R10·판단 상세 R2·근거/권한/hash 계약은 유지한다. 기본 `GENOS_RAG_PROGRESS_UI=socketio`는 접이식 카드와 최종 답변을 보내고 `on`도 이 모드로 연결한다. `socketio-inline`은 기존 본문 진행 표시, `final-cards`는 완료 후 카드, `socketio-final`은 최종 본문, `off`는 진행 표시 끄기다. 카드가 없는 런타임이나 송신 실패에서도 backend를 재실행하지 않고 기존 최종 dict를 반환한다. 별도 SSE backend를 자체 Socket.IO 서버로 바꾸지 않는다.

첫 준비 카드는 AD_PROBE 전에 `준비 중 · 자료와 요청 설정을 확인하고 있습니다`를 송신한다. 이후 실제 SSE의 원문 확인·선택·판단 이벤트를 기존 Visible Reasoner 형식으로 즉시 전달한다. 모델의 숨은 추론을 노출하지 않는다. 외부 Python 소비자의 큐에서도 judgment/full_error는 일반 진행과 함께 버리지 않는다. `WORKFLOW_SETTINGS`는 실제 모드·socket client ID 존재·표시 revision을 보고하고 최종 `workflow_progress_delivery`는 실제 카드 emit 횟수/송신 오류 종류를 보고한다. emit 성공은 브라우저 렌더링 성공을 뜻하지 않는다.

사용자 추가 정정의 SSE는 승호님 코드에서 사용한 GENOS 기본 채팅 표시 기능이다. 로컬에 보존된 `fde/seungho/integration` commit `3809dfa0512cc4a2c9057bc3083f1944dd05f777`의 `07-issuance-note/deploy/workflow/report_chat.py:Progress.say`는 `main_socketio.sio_server.emit('token', ..., room=socketIOClientId)`을 사용한다. `fde/dongkuk/nltosql` commit `df411b96328b424fe57e9033b580d2d36854cf63`의 `08-offering/genos/workflow_progress_bridge.py`는 GENOS 514 참조의 `Visible Reasoner`/`visible_rationale`/`nodeId`/`FINISHED` 모양과 누적 카드·답변 token·end·최종 카드 dict를 따른다. GENOS 수집 문서 `07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md`의 V1.8.6 화면 렌더 조건도 대조했다. 승호 최신 cicd의 직접 `/chat` SSE와 이 분리 워크플로우 화면 채널은 코드에서 구분한다.

미발송 R2 후보는 카드 송신만 검사하고 첫 token이 처리 중 패널 렌더를 시작하는 조건을 반영하지 못했다. 해당 실패 검사와 봉인 R2 후보를 보존하고 R3로 이어 수정했다. R3는 첫 준비 token을 즉시 보낸 뒤 동일 Visible Reasoner 카드를 누적 송신한다. 준비 상태는 실제 AD_PROBE 전 실행 준비를 표시하며 데이터 준비 완료나 모델 판단으로 간주하지 않는다. `end`와 최종 dict의 카드 배열을 유지한다. 별도 backend가 최종 표시를 재사용해도 이미 실제 송신한 카드 배열을 다른 배열로 바꾸지 않는다. 기본 socketio 모드는 첫 준비 문구와 접이식 상세 카드를 보내며 나머지 상세 행위를 본문에 반복하지 않는다. socketio-inline은 기존 본문 진행 표시를 유지한다.

인계는 `08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r3/`의 ZIP과 `GENOS_WORKFLOW_LIVE_CARDS_20261008_R3_PASTE_ALL.txt`다. 이번 적용 위치는 기존 워크플로우 Python 편집기이며 전체 TXT를 교체해 저장한다. 이전 편집기 내용을 원복용으로 보존한다. 별도 SSE 서버·R5 코드 ZIP·NFS generation·DB·CM·조사 예산·오류 로그·로컬 MAIN45는 이번 복구에서 변경하지 않는다. 기존 endpoint/ID/token/port를 유지한다. 편집기 코드 변경은 Git push로 자동 반영되지 않는다. 현장 질문/warmup 확인은 워크플로우 테스트 화면에서 한다.

로컬 검증과 실패 전 기록은 `09_ARTIFACTS/AUDITS/20261008-workflow-live-cards-restore-r2/`에 있다. 초기 회귀 10개 중 R5 원본에서 8개 실패/2개 통과를 기록했다. 수정 후 준비 카드가 지연된 AD_PROBE보다 먼저 보이고, 실제 SSE 소비 경로의 원문·전체 판단 카드가 최종 result보다 먼저 emit되는 것을 검사했다. 구 정상 카드 인계·SSE/JSON fallback·직접 채팅·SVG·판단 상세·서버 표시 재사용 계약도 함께 확인했다. 신규 모델 호출과 GENOS 접근은 없다. 현장 편집기 저장·카드 렌더링 성공은 사용자 출력으로 별도 확인한다.

최종 R3의 관련 계약106개·정확한 편집기 TXT12개·첨부 PREPARE/ZIP 준비4개가 통과했다. 패널 수신 계약 검사는 첫 token→카드 모양→누적 배열→최종 token/end→같은 최종 카드 배열을 확인한다. 이는 기존 수집 계약을 모의 소비자로 검사한 결과이며 실제 GENOS 브라우저 렌더링 검사는 아니다. `native-feature-reference.json`은 조회한 원본 commit/path/hash를, R3 `HANDOFF.json`은 인계 ZIP/source/paste/hash와 현장 미확인 상태를 보존한다.

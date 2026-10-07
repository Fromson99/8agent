# GENOS 판단 과정 표시 — 작업 코드·반입 R2

2026-10-06 사용자 요청. 답변 아래 판단 전체를 접고, 일곱 단계와 사용 데이터/행위를 다시 접는다.
마지막은 코드가 작성한 Mermaid다. 별도 LLM 호출·판단 프롬프트 변경은 없다.
로컬 frozen MAIN·원문 generation·CURRENT·실제 GENOS 리비전은 전환하지 않았다.

## 생산·소비 연결

`/v1/rag/ask → legal_agent.unified_runtime.result_port`가 현재 사건 route의
INTENT/PLAN/RECALL/READ/SELECT/ASSESS/COMPOSE heads와 native judgment refs를 읽는다.
`judgment_view.build`는 각 payload hash를 확인하고 현재 문서 범위에 있는 원문만 투영한다.
`assembly.term_agent.judgment_view`에 `judgment-view-v1`을 추가한다. 현행 term-runtime-v1의
가변 term_agent 확장 안에 넣으며 answer.text/claims는 바꾸지 않는다. retrieval/selection에는
투영을 중복 저장하지 않는다. 최종 publication guard는 현재 route에서 투영을 재구성해 대조한다.
기존 완료 응답 파일에는 소급해서 투영을 넣지 않는다. 새 요청부터 생성한다.

워크플로우 `genos_rag_chat.py`의 render와 `/chat`의 chat_adapter가 같은 표시 함수를 사용한다.
워크플로우는 view hash, question/revision/route, 단계별 judgment refs를 확인한 뒤 HTML
details/summary와 Mermaid fenced block을 만든다. 기본은 전부 닫힌 상태다.
모델 텍스트·문서명·원문은 HTML escape하고 Mermaid는 고정된 단계명과 정수 건수만 사용한다.
스트리밍 최종 finish가 답변 이후 토글을 한 번만 전송한다. 기존 Reasoner 누적 배열은 유지한다.
Markdown 문단 변환은 토글 HTML과 code fence를 변경하지 않는다.

원문 확인에는 저장된 READ 범위의 label/조·항·호·목과 실제 원문을 표시한다.
SELECT에서 범위를 넓힌 경우 원래 READ 표시를 최종 범위로 덮어쓰지 않는다.
SELECT/ASSESS는 현재 선택 근거와 원문 인용, 판단, 미확인 사항을 표시한다.
최종 근거에 미포함된 원문은 미포함으로 표시하며 무관하다는 판단을 만들어 붙이지 않는다.
정정 시 현재 heads를 보여주며 이번 수행/현재 판단 유지/실제 확정 경험 연결을 구분한다.
숏컷 정책이 새 조사를 요구하면 그 실제 수행을 표시한다.

## 로그와 이유

`readable_log.py`와 `progress.py`는 비어 있거나 ‘이유 없음’인 reason을 사용자 표시에서 생략한다.
이유가 없는 것이 아니라 현재 출력에 기록되지 않았을 수 있으므로 다른 이유를 생성하지 않는다.
고정된 PLAN 구성은 ‘고정 처리’로 표시한다. source 원장·전체 모델 입출력은 감사 정본으로 보존한다.
개인 조건은 기존 인증된 사건 조회 범위 안에서 표시하며 진행 이벤트에 새로 노출하지 않는다.

## 반입과 검증

[R2 실행 안내](../../../08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r2/GUIDE_UTF8.txt),
[전체 워크플로우 교체 TXT](../../../08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r2/GENOS_JUDGMENT_VIEW_20261006_R2_WORKFLOW_PASTE_ALL.txt),
[모의 표시 미리보기](../../../08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r2/PREVIEW.html).

R2는 용어집 binding 복구 R1의 compact reader와 AD R2/연결 읽기 R2를 유지하는 누적 반입본이다.
새 데이터 구축은 필요 없다. 기존 ~/DEV에 검증·백업 후 적용하고 commit/gate/push/새 코드서빙
리비전과 워크플로우 편집기 전체 교체를 별도로 수행한다. 현장 질문·warmup은 워크플로우 테스트만 사용한다.

로컬 검사와 현장 상태의 정본은 R2 `VALIDATION.json`, `HANDOFF.json`이다.
Linux Chromium의 HTML/Markdown 중첩 토글·초기 닫힘·펼친 원문과 Mermaid 파싱/SVG를 검사했다.
PREVIEW.html은 모의 데이터와 미리 렌더한 SVG를 담은 로컬 예시이며 현장 화면 증거가 아니다.
실제 GENOS의 HTML 허용 태그와 Mermaid renderer, 워크플로우 편집기 반영·내부 모델 질의는 미확인이다.
현장에서는 details/summary와 Mermaid fenced block을 지원하는 기존 채팅 renderer가 필요하다.
외부 JS/CDN을 제품 코드나 반입 ZIP에 추가하지 않았다.

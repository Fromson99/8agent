# 답변 본문의 숫자 참조 표기 제거 — 2026-09-29

사용자 지시로 GENOS 채팅 답변의 문장 뒤에 붙는 `[4]`, `[3]`, `[1]`을 표시 단계에서
제거한다. `수집해야 합니다 [4].`는 `수집해야 합니다.`로 표시한다. 모델을 추가로 호출하거나
저장된 답변·claim·evidence·번호 매핑을 바꾸지 않는다. 출처 목록의 문서명·조문은 유지한다.

## 연결과 범위

`workflow/genos_rag_chat.py → _public_answer_text → render → _for_markdown → run(data).text`
및 `_ChatProgress.answer_delta → _without_inline_reference_numbers → socket token`에 연결한다.
숫자 하나, 쉼표로 연결한 번호 및 범위를 가진 문장 뒤 대괄호를 제거한다. 법령명·별표·시행일처럼
문자를 포함한 괄호, 따옴표로 표시한 인용문, 코드, 줄 첫머리의 목록 번호,
`[1](주소)` 링크와 문자가 있는 참조 링크 라벨을 보존한다. 생성된 참조와 원문의 숫자 표기를
모두 의미적으로 판별하는 기능은 아니며, 문장 뒤 숫자 각주 형태를 대상으로 한다.

증분 표시에서는 미완성 숫자 괄호와 닫힌 괄호 뒤의 링크 여부를 확인할 때까지 해당 부분을
보류한다. 숫자 참조가 fragment 경계에서 나뉘어도 화면에 잠깐 나타나지 않는다.
완료 시 이미 표시한 답변 prefix를 유지해 본문 중복과 `답변 작성 결과` 재출력을 방지한다.
`socketio`·`socketio-final`·`off`와 socket ID 없는 최종 dict 표시를 같은 규칙으로 처리한다.

기존 스트리밍 `WORKFLOW_REVISION=answer-stream-20260929-r1`은 유지한다.
새 표시 식별자 `answer_display_revision=answer-reference-display-20260929-r1`은
정상 응답과 SSE_CHECK의 `sse_check`에 추가한다. 서버 SSE 리비전과 워크플로우 표시 리비전은 별개다.

## 현장 반영과 복구

인계 폴더는 `08_DEPLOYMENT/GENOS/handoffs/answer_reference_display_20260929_r1/`이다.
`GENOS_ANSWER_REFERENCE_DISPLAY_20260929_R1_WORKFLOW_PASTE_ALL.txt` 전체를 기존 워크플로우의
Python 편집기에 교체하고 저장·배포한다. `run` 진입점과 기존 환경 설정을 사용한다.
백엔드 파일·엔진 manifest·PIPELINE·데이터 generation·CURRENT·로컬 frozen MAIN 변경은 없으며,
이 표시 수정에 코드서빙 리비전 교체나 데이터 재구축은 필요하지 않다.
저장소에서 코드를 다시 가져오는 환경에서는 기존 checkout의 워크플로우 파일을 반영한다.

**현장 확인은 워크플로우 테스트 화면에서만 수행한다.** `{"question":"SSE_CHECK"}`의
`sse_check.answer_display_revision`이 위 표시 식별자인지 확인한다. 이후 원래 질문에서 숫자
참조가 본문에 없고 출처의 문서명·조문은 보존되는지 확인한다. 이 세션은 GENOS에 접근할 수
없으므로 현장 편집기 반영·배포·실제 내부 모델 질문 성공은 미확인이다.

복구는 현장에서 교체 직전 백업한 Python으로 되돌리고 저장·배포한다. 인계 폴더의
`GENOS_ANSWER_REFERENCE_DISPLAY_20260929_R1_ROLLBACK.py`는 이번 로컬 수정 직전 코드이며,
현장의 이전 편집기 코드와 다르면 현장 백업본을 사용한다. 인계 manifest에 전후 파일 해시,
검증 환경, 로컬 선택 릴리스, 현장 generation·커밋·리비전의 미확인 상태를 남긴다.

## 검증

모의 입력으로 사진의 `[4]`·`[3]`·`[1]`, 연속·복수·범위 참조, 괄호·인용·코드·목록·링크 보존,
원래 API body 불변, 한 글자 단위 스트리밍 prefix와 완료 본문 일치, 세 표시 모드를 검사한다.
기존 답변 스트리밍·채팅·진행 표시 회귀를 포함해 115개 검사가 통과했다.
외부 모델이나 실제 내부 데이터는 사용하지 않았다. 전달 Python/TXT의 바이트 일치·문법·표시 예도 확인했다.
실행 결과와 파일 해시는 `09_ARTIFACTS/AUDITS/20260929-answer-reference-display/`에 보존한다.

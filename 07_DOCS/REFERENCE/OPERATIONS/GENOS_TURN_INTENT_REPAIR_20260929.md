# GENOS의 행동·종료 판단 충돌 수정

현장 사진의 실제 오류는 `MODEL_PROPOSAL_INVALID`와
`observe action results before DRAFT/CLARIFY; use CONTINUE for actions`다.
이는 `intent=DRAFT/CLARIFY`와 비어 있지 않은 `actions`가 함께 반환된 경우다.
`request finalized; remaining source judgments not fabricated`는 FINAL 시 남기는
공통 종료 기록이며 이 오류의 원인이나 GENOS 가드레일 탐지 결과가 아니다.

## 이전 R2와 변경 지점

R2는 bounded 판단·원문 선별·질문 참조와 JSON 형식 수정 경로를 연결했다.
사진의 충돌은 gateway에서 형식 검증을 통과한 뒤 `ObligationSession.validate_intent`에서
거절되었다. 기존 `ToolsSession.investigate`는 같은 오류 재수정 한도와 전체 호출·시간
예산에 따라 재요청하거나 종료한다. `SEMANTIC_REPAIR`는 재수정을 예약한 경우뿐 아니라
반복 한도 때문에 종료하는 경우에도 기록되므로 그 표식만으로 재호출을 증명하지 않는다.
사진만으로 반복 횟수·선택 프로필·호출 잔여량이나 플랫폼 가드레일 개입을 확정하지 않는다.

작업 코드의 `obligation_protocol.validate_wire`에서 같은 충돌을 먼저 검증한다.
`service.py` → Pipeline → ServingLegalAgent → ObligationSession → ModelGateway의
기존 같은 view 수정 경로가 실제 오류와 이전 출력 일부를 모델에 돌려준다.
수정된 전체 객체가 통과한 후에만 question plan·원문 선택·도구 실행을 반영한다.
`PROMPTS.investigate`에도 행동이 있으면 CONTINUE, DRAFT/CLARIFY이면 actions=[]를
명시한다. 판단을 서버가 임의로 바꾸거나 도구 행동을 성공으로 간주하지 않는다.
원래 `max_schema_repairs`·물리 호출 예산·deadline과 후속 검증을 유지한다.

## GENOS 출력 가드레일과 구분

LLM 서빙의 출력 필터가 거절 문구 또는 부적합한 구조를 반환하면 같은 모델 응답 검증
경로에서 실패할 수 있다. 거절 문구만 반환된 경우는 보통 JSON/스키마 오류이며,
사진의 정확한 오류는 구조 안의 intent/actions 충돌이 있어야 발생한다.
모델 자체의 잘못된 행동 지시와 출력 필터가 영향을 준 응답을 이 오류 한 줄로 구분할 수 없다.

현재 provider가 보내는 `finish_reason=content_filter`는 수신 계측과 원본 응답 journal에
보존된다. 값이 없거나 `stop`이라고 필터 미개입을 확정하지 않는다.
현장에서는 해당 호출 시각의 GENOS 가드레일 탐지 로그·대상 LLM 서빙과 모델 원본 응답을
대조한다. 출력 필터가 정정 응답까지 계속 차단하면 정정이 실패할 수 있으며 필터를 우회하지 않는다.
현재 최종 검토 비활성 경로의 형식·참조 검증은 잘못된 법률 결론 전체를 판정하는 기능이 아니다.

## R3 인계·검증·원복

[R3 인계 디렉터리](../../../../09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-compatible-r3/)의
ZIP/TXT를 같은 폴더에 저장하고 실행한다. 사진 기준 코드, R2 적용 코드, 통합판을
승인한 함수 서명으로 확인한다. 기존 R2 기능을 포함하며 다른 현장 함수·추가 바이트를
보존한다. 승인되지 않은 함수 변경은 쓰기 전에 거절한다. 발송된 R1/R2를 덮어쓰지 않는다.

```bash
bash GENOS_MODEL_DECISION_REPAIR_20260929_R3_APPLY.txt
```

기존 `~/DEV` Git checkout에 백업 후 적용한다. 처음부터 `/tmp/genos-selective-*/run.log`에
로그·종료 상태를 남긴다. `MODE=check`는 변경 없이 확인하고 재실행은 ALREADY_APPLIED다.
`BACKUP_READY` 경로를 사용한 `MODE=rollback ROLLBACK_FROM=...`으로 R3 이전 바이트와
엔진 pin을 복구하며 이후 현장 수정은 덮어쓰지 않는다.

runtime 두 파일을 변경하고 작업 코드의 엔진 manifest 20개와 PIPELINE 해시를 함께 갱신했다.
현장 R3는 기존 R2 파일까지 함께 확인·적용해 파일 5개와 해당 checkout의 pin을 결속한다.
데이터 generation·CURRENT·모델·워크플로우 Python 교체는 이 변경에 필요하지 않다.

변경 코드를 검토·commit한 뒤 같은 checkout과 실제 선택 generation으로 확인한다.

```bash
GENOS_GENERATION=/실제/선택/generation MODE=verify bash GENOS_MODEL_DECISION_REPAIR_20260929_R3_APPLY.txt
```

같은 commit을 push하고 새 코드서빙 리비전을 배포한다. 질문 확인은 워크플로우 테스트
화면에서 한다. 최종 답변, 정정 물리 호출, 출처, 실제 선택 리비전을 함께 확인한다.
작업 코드·로컬 frozen MAIN·GENOS 배포는 별도 상태이며 이번에는 frozen MAIN을 변경하지 않았다.
GENOS 배포·가드레일 실제 차단·현장 내부 모델의 정정 성공은 미확인이다.

모의 입력·응답에서 사진의 두 intent, 같은 view와 호출 계보, 실행 전 상태 불변,
반복·0회 한도, 읽기→선별→HTTP 답변, 필터 거절 응답의 신호 보존을 확인한다.
최종 ZIP/TXT를 기존 R2 이후 checkout에 실제 적용하고 그 runtime으로 계약 검사를 수행한다.
Python 3.11.15·현재 Python의 설치·재설치, 원복, 현장 추가 함수 보존과 배포 gate의
코드 ZIP 대조도 확인한다. 결과는 [감사 디렉터리](../../../../09_ARTIFACTS/AUDITS/20260929-turn-intent-repair/)에 보존한다.

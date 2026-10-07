# 사진 기준 판단 오류 수정과 메일 선택 적용

사용자가 제공한 현장 사진의 세 파일 SHA-256을 보관된 코드 바이트와 대조했다.

| 파일 | 확인한 SHA-256 | 대응 코드 |
|---|---|---|
| `legal_agent/bounded_source_session.py` | `55049c242db6bf28f8ee6a23b2dc813cb55ac302706b22e6adc9425ac21b37fb` | 프롬프트 정리 R1의 payload |
| `legal_agent/gateway.py` | `ffd8aca708a7a5b53c02e9f3a58787e416e44c0ccd5c62834b315cc327717982` | 답변 스트리밍 R1의 payload |
| `progress.py` | `1d5d5efec4a790d2f65cfb1df511d8c10046bb5e20a5503a5aaa54b49b3ffb23` | 진행 흐름 R2의 payload |

사진에서 앞서 실행한 MODEL_DECISION_REPAIR R1은 `prepare`의 첫 파일 검사에서
중단했다. 백업·소스 쓰기 전에 실패했으므로 그 실행으로 소스가 변경되지는 않았다.
R1이 요구한 통합판의 bounded 파일과 현장 파일은 다르다.

## 먼저 전달한 R2

[판단 오류 수정 R2 인계](../../../../09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-compatible-r2/)의
ZIP과 TXT를 같은 폴더에 저장한 뒤 실행한다.

```bash
bash GENOS_MODEL_DECISION_REPAIR_20260929_R2_APPLY.txt
```

기존 `~/DEV` 입구를 실제 Git root로 해석한다. 승인된 `_Protocol`과 bounded 판단 함수,
gateway 오류 재요청 함수, 진행 표시 함수·이벤트 사전만 변경한다. 옛 다중 case 검색 계획도
같은 검증·수정 루프에 연결한다. 없는 요청 분류·문서 현황 함수를 새로 추가하지 않는다.
통합판과 기존 오류 수정 R1의 함수 판도 지원하며 다른 함수·현장 추가 바이트를 보존한다.

코드·스키마·엔진 manifest의 기존 해시를 검증하고 사용하는 manifest와 PIPELINE 해시를
함께 갱신한다. 데이터 세대·CURRENT·모델 설정·워크플로우는 변경하지 않는다.
첫 단계부터 `/tmp/genos-selective-.../run.log`에 로그를 남긴다.
`BACKUP_READY`의 백업과 `TRANSFER/genos-selective-20260929-r1/`의 영수증을 보존한다.
재실행은 `ALREADY_APPLIED`, 사전 확인은 `MODE=check`, 원복은 `MODE=rollback`이다.
후속 변경이 생긴 파일은 원복으로 덮어쓰지 않는다.

R2 메일은 `hyungjininfocz.son@partner.samsung.com`으로 발송했다.
제목은 `[GENOS] 사진 기준 단독 적용 R2 — 판단 오류 수정 (R1 교체 ZIP/TXT)`이고,
발송 ID와 실제 첨부 해시는 해당 인계의 `EMAIL_SENT.json`·`DELIVERY.json`에 남긴다.
발송된 R1·R2 자료를 다시 생성하거나 덮어쓰지 않는다.

## 다른 코드 메일의 선택 적용

[공통 선택 적용 인계](../../../../09_ARTIFACTS/HANDOFFS/20260929-selective-compatible-r1/)는
9월 28~29일 코드 패치 16개를 기능별로 선택하도록 준비한 대체 적용기다.
기존 메일의 ZIP/TXT를 현장에 원격으로 바꾼 것은 아니다. 추가 기능은 이 공통 ZIP/TXT로
선택한다. 기본 선택은 판단 오류 수정 하나이며 나머지를 자동으로 적용하지 않는다.

```bash
SELECT=request-prepare MODE=check bash GENOS_SELECTIVE_20260929_R1_APPLY.txt
SELECT=request-prepare bash GENOS_SELECTIVE_20260929_R1_APPLY.txt
```

| SELECT | 기능 | 원래 코드 인계 |
|---|---|---|
| `decision-repair` | 판단 오류 수정 | MODEL_DECISION_REPAIR R2 |
| `answer-stream` | 답변 생성 SSE | ANSWER_STREAM R1 |
| `prompt-compaction` | 모델 입력 정리 | PROMPT_COMPACTION R1 |
| `chat-flow` | 진행 문단·문서·조문 표시 | CHAT_FLOW R2 |
| `request-unlimited` | 요청 수 제한 해제 | REQUEST_UNLIMITED R1 |
| `latency` | 요청 준비·캐시·warmup·계측 | LATENCY R2 |
| `relation-wait` | 관계 탐색 별도 제한 제거 | RELATION_WAIT R1 |
| `final-review-off` | 최종 답변 검토 생략 | FINAL_REVIEW_OFF R1 |
| `proposal-retry` | 모델 제안 수정 재요청 | PROPOSAL_RETRY R1 |
| `sse-startup` | SSE 기동 시 지연 적재 | SSE_STARTUP R1 |
| `response-overhead` | 정상 로그·반복 준비 비용 수정 | RESPONSE_OVERHEAD R3 |
| `team-logs` | 날짜·팀별 질문답변 요약 | TEAM_REQUEST_LOGS R3 |
| `thinking-log` | 모델 요청·응답 로그 표시 | THINKING_LOG R3 |
| `fulltext-diagnostics` | fulltext 구간별 계측 | FULLTEXT_DIAGNOSTICS R1 |
| `fulltext-location` | 위치 구성의 본문 전체 조회 제거 | FULLTEXT_LOCATION R2 |
| `request-prepare` | 원장 초기화·projection 준비 비용 수정 | REQUEST_PREPARE R1 |

전체 파일을 옛 payload로 교체하는 대신 기록된 before→after 변경분을 적용한다.
두 immutable 통합 릴리스와 답변 SSE 후속본에서 이미 포함된 기능은 정확한 SHA-256과
manifest에 근거해 보존한다. 보존 출처는 `SELECTIVE_MANIFEST.json`의
`preserve_sources`·`preserve_sha256`에 명시한다. 날짜만으로 현장 파일을 선택하지 않는다.
함수 기반 기존 적용기의 승인 함수·선행 캐시 검사는 유지한다.
변경 충돌·선행 함수 누락·기존 pin 불일치는 소스 쓰기 전에 중단하며 강제 덮어쓰지 않는다.

SSE 시작 파일은 별도 코드 메일로 전달되어 통합 전체 ZIP에 없는 경우가 있다.
선택 기능의 검증된 SSE 시작 파일이 없을 때는 그 파일만 생성한다.
ANSWER_STREAM·CHAT_FLOW를 새로 적용한 경우 워크플로우 편집기 반영은 별도다.
공통 적용기는 워크플로우 편집기·Run·Build 설정·Git push·코드서빙 리비전을 조작하지 않는다.

전체 코드 교체, PeCab 구축/재구축, 명시 참조 MAIN 데이터 생성, 로그 분석·상태 조회 TXT는
이 코드 선택기의 대상에 포함하지 않는다. 별도 데이터·운영 계약을 그대로 따른다.

## 검증과 상태

[계약 검사](../../../../05_TESTS/CONTRACTS/test_genos_selective_handoff.py)는
사진과 동일한 세 파일과 보관된 통합 코드를 넣은 모의 Git checkout에서 수행한다.
R2의 최종 ZIP/TXT, Python 3.11·현재 Python, 적용·재적용·원복·코드 gate 비교,
모의 JSON·판단 오류 수정, 오래된 case 계획의 중복 번호 오류 수정을 확인한다.
다른 15개 선택 기능의 재실행, 오늘 메일의 앞/뒤 적용, generic delta 9개의 정확한
보관 기준에서 첫 설치와 원복, 데이터·명시 프로필 pin 보존을 검증한다.
16개 기능을 임의의 모든 조합으로 현장에서 실행했다는 의미는 아니다.
사용자가 제공하지 않은 현장 파일 바이트와 실제 GENOS 내부 모델·속도·리비전은 미확인이다.

코드 적용 후 실제 변경을 검토·commit하고 실제 선택 generation으로 배포 게이트를 실행한다.

```bash
GENOS_GENERATION=/실제/선택/generation MODE=verify bash GENOS_SELECTIVE_20260929_R1_APPLY.txt
```

게이트를 통과한 commit을 push하고 같은 generation으로 새 코드서빙 리비전을 배포한다.
최종 질의와 SSE 확인은 워크플로우 테스트 화면에서만 한다.
`APPLIED`, 코드 gate 통과, 메일 발송을 실제 GENOS 배포 성공으로 기록하지 않는다.

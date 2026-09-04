# ADR-0166 실험 질문 인덱스

> 이 폴더는 질문별 실제 LLM 입력·출력·채점 기록을 보존한다. 집계만 보고 개별 원문을 삭제하지 않는다.

## 작업 선점

- owner: `Codex`
- scope: Complete permanent v2 regression, tooling, path, provenance, resolver, packaging, and CAS hardening
- scope key: `permanent-v2-completion`
- created at: `2026-09-04T00:23:39.298640Z`
- status: `completed`

## 계보

- experiment ID: `ADR-0166-experiment-v1`
- branch: `A`
- parent arm: `ROOT`
- 이 분기의 변경 가설: 영수증 기반 경로 해석과 canonical 패키징으로 과거 기록 hash를 보존한다.

## 병합

- merge: 해당 없음

## 다른 ADR과의 관계

- 관련 ADR: 없음

## Arm

| arm ID | 역할 | 직접 부모 | 바뀐 것 | 고정한 것 |
|---|---|---|---|---|
| `baseline` | baseline | ROOT | base commit 작업판 | 동일 WSL/Python 환경 |
| `hardened-v2` | candidate | baseline | 경로·영수증·패키징 hardening | 배포·LLM·검색/답변 미변경 |

## 질문 인덱스

| 번호 | case ID | run | arm별 판정 | paired 분류 | 실패 유형 | 파일 |
|---:|---|---|---|---|---|---|
| - | - | - | - | - | - | 질문 단위 평가 없음 |

## 집계

- phase: `audit`
- in-sample: `false`
- run 상태: `run-001 / complete`
- arm별 정답: 질문 평가 해당 없음; 기본 회귀 1960/1960 통과
- 사전 지정 비교쌍별 신규 정답 / 회귀: 해당 없음 / 회귀 실패 0
- judge 불일치: judge 호출 없음

## 단계별 회수·탈락 집계

| run | arm | stage | kind | 후보 before→after | gold before→after | gold gain/loss | micro recall | 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---|
| `run-001` | hardened-v2 | repository-audit | not_applicable | - | - | - | - | retrieval 미변경 |

질문별 exact 원장은 각 질문 파일에, hash 고정 기계 판독본은 run의
`retrieval-stage-ledger-v1` artifact에 둔다. inherited retrieval은 원본 path와 SHA-256을,
retrieval이 없으면 구체적인 not-applicable 사유를 남긴다.

설계, 계보, 실행과 집계의 기계 판독본은 [manifest.json](manifest.json)에 있다.

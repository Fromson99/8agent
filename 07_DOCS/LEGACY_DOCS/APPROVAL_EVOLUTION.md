# 승인 receipt → 아키텍처 진화 후보

사람이 승인한 정본 업데이트를 규칙 귀납과 RAG 탐색 개선이 함께 읽기 위한 공통
계보다. 기존 `edge_rules.json`·`candidates.json`·`glossary.json`은 계속 각 기능의
정본이고, `$RAG_LOG_DIR/approval_receipts.jsonl`(미지정 시 구조 스토어 옆
`rag/approval_receipts.jsonl`)은 그것들을 대체하지 않는 append-only 관측 원장이다.

```text
사람 판정
  ├─ 기존 정본 projector ─▶ 다음 질의에 즉시 반영
  └─ approval receipt ─────▶ 실패×효과 집계 ─▶ 닫힌 mutation target 후보
                                                    │
                          기존 승인 문 ◀─ shadow·사람 검수 ◀─ replay/holdout
```

## 현재 연결된 판정

| 판정 | 즉시 반영 | receipt effect | 실패 유형 |
|---|---|---|---|
| 오참조 승인 | 간선 억제 | `suppress` | `잘못된_참조` |
| 착지 교정 승인 | 도착 재지정 | `redirect` | `얕은_착지` |
| 참조무관 후순위 | 확장 후순위 | `demote` | `과도한_참조확장` |
| 검색무관 진입제외 | 진입 차단 | `entry_block` | `검색_진입오염` |
| 구조 고침 | 검수 처리 | `structure_fixed` | `구조화_오류` |
| 질문 기억 활성/기각 | 직행 좌표 활성/비활성 | `memory_activate/reject` | 기억 누락/오염 |
| 답변 오답 | 기대 좌표 기록 | `answer_overturn` | `답변_오류` |
| 용어 승인/기각 | 검색 정본 발행/차단 | `term_activate/reject` | 용어 누락/오염 |
| 규칙 적중 뒤집힘 | 반례·자동 강등 검사 | `rule_overturn` | `규칙_반례` |

## 원장 계약

- receipt 실패가 이미 성립한 정본 승인을 되돌리지 않는다.
- 판정 번복은 옛 행을 수정하지 않고 새 행을 append한다.
- 집계는 `subject_key`별 최신 행만 세므로 반복 클릭은 증거를 늘리지 않는다.
- 일반 규칙 산출을 다시 교정한 사건은 규칙 반례로만 쓰고 양성 귀납·탐색 표본에서
  제외한다.
- `탐색후보`는 자동 변경 명령이 아니다. control 후보는 별도 replay·holdout·shadow와
  사람 승인을 통과해야 한다.

## API

```text
GET /v1/rag/approvals?current_only=true
GET /v1/rag/approvals/evolution?min_evidence=2
```

첫 API는 receipt와 저장 위치를, 둘째는 실패 유형·효과·독립 증거 수·문서 범위·
추천 mutation target을 반환한다. `control:`은 `controls.py`에 실제 등록된 수치
손잡이이고, `operator:`는 규칙·라우터·파서처럼 별도 bounded DSL이 필요한 단계다.
구현은 `lawrag/core/rag/approvals.py`다.

현재 단계는 **승인 신호 정규화와 결정적 후보 집계**까지다. 다음 단계의 실행기는
`control:` 후보는 `controls.py` 손잡이만 변이하고, `operator:` 후보는 해당 단계의
닫힌 변이 DSL이 생기기 전까지 자동 실행하지 않는다. 실행 receipt에는
code/corpus/control fingerprint와 골든·홀드아웃 성적을 고정해야 한다.

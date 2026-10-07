# RAG 멀티턴 체인 프로토타입 결과

ADR-0593 · WSL 로컬 · 합성 원문 6단위 · 연속 대화 5개 · Qwen3.8 · MAIN 미변경

**실행 결과를 구현 범위 안에서 판정한다. 실제 RAG API/Coordinator·GENOS 연결 검증은 포함하지 않는다.**

| 흐름 | CURRENT_ONLY | CHAIN |
|---|---|---|
| SEQ01 | 13/20 | 20/20 |
| SEQ02 | 15/15 | 15/15 |
| SEQ03 | 16/17 | 16/17 |
| SEQ04 | 10/10 | 10/10 |
| SEQ05 | 14/15 | 15/15 |

## 핵심 기능 판정과 채점 범위

사전 동결 검사는 CHAIN **76/77**, CURRENT_ONLY **68/77**이다. 순차 사례 전체의 해당 검사 통과는 각각 **4/5**, **2/5**다.
이 점수는 정해진 필드·영수증 검사이며 전체 기능 정상률이 아니다. 별도 trace 검토에서 검사 밖의 실행 오류도 확인했다.

| 기능 | 실제 관찰 | 판정 |
|---|---|---|
| 긴 대화에서 최초 조건으로 복원 | SEQ01 15턴: 최초 발언 1번과 26개 관련 node 조회, INTENT부터 재실행, B로 복원 | 모의 경로 정상 |
| 다음 턴·새 요청의 최종 경로 소비 | SEQ01 16·17턴: B 유지, 17턴 현재 route를 가져와 새 LLM 작성 | 고정 조건·연결의 모의 소비 정상 |
| 두 질문 중 하나만 정정 | SEQ02 G2 수정 동안 G1의 단계 ID 유지 | 모의 경로 정상 |
| 새 긴급 조건·재정정 | 긴급 true/false가 SELECT·ASSESS와 새 답변에 반영 | 상태·판단 반영 정상 |
| 검색 계획·읽기 수정 | SEQ03 2턴: PLAN→RECALL→READ→SELECT→ASSESS→COMPOSE | 모의 경로 정상 |
| 선별 단계만 재검토 | SEQ03 CHAIN 3턴: model.stage=SELECT, action=FOLLOW지만 실행은 COMPOSE만 | 실행기 오류 |
| 표·문장 재작성 | SEQ03 5·6턴: 기존 LLM compose만 실행, 앞선 단계 ID 그대로 | 모의 경로 정상 |
| 잘못 가져온 경험 연결 정정 | SEQ04: G1 연결 복원, G2 경험의 단계 보존 | 모의 ID 연결 정상; 실제 wiki 서비스·의미 매칭 미연결 |
| 중단된 정정 복구 | SEQ05 5턴의 계획된 실패 중 ACTIVE route 없음; 6턴 ASSESS→COMPOSE로 재개, C 사용 | 모의 경로 정상 |
| 옛 실행 재수집·늦은 게시 | 현재 route만 사용하고 과거 revision 게시 거부 | 기계적 guard 정상; 실제 worker·경합·캐시 미검증 |
| 현재 조건 조회 | 답변에 긴급 확인 필요가 있지만 INSPECT 응답에 assessment 필드 없음 | 관측/응답 계약 누락; frozen 검사 실패 1개 |
| 최종 원문 회수 집계 | 마지막 READY가 다른 goal이면 final INSPECT/REUSE의 실제 경로와 ledger가 어긋남 | 집계 오류; 보고된 recall로 회수 품질 판단 금지 |

선별 오류 원인은 FOLLOW의 값이 바뀌지 않으면 지정한 stage와 무관하게 COMPOSE로 보내는 분기다.
사용자가 SELECT를 지정한 경우 해당 단계와 의존 결과를 재실행하도록 고쳐야 한다.
현재 기록이 없어 최초 조건을 복원할 수 없을 때, 모델이 현재 값을 그대로 적용하는 것을 막는 guard도 보강 대상이다.

INSPECT 필드 누락 때문에 needs_check를 null로 채점한 원래 결과는 그대로 보존했다.
답변 문장에는 긴급 예외 확인 필요가 남아 있어, 이를 실제 판단 오류라고 단정하지 않는다.
회수 ledger는 집합 산식 검사를 통과할 수 있어도 최종 질문과의 소속 오류가 있으므로 성능 근거로 쓰지 않는다.
점수·제품 출력·gold를 바꾼 재채점은 하지 않았다.

이번 새 요청 소비는 새로운 turn/journal과 LLM 작성에서 현재 bundle을 사용하는 방식이다.
별도의 생산 session binding이나 자연어 유사 의도 검색이 새 사례에서 그 bundle을 찾는 것까지 검증하지 않았다.

## 기능별 실제 관찰

### SEQ01

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규에서 국내 법인의 긴급 예외 적용 조건을 확인해줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 아니 외규에서 해외 법인의 필요 서류를 확인하는 것으로 바꿔줘. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 4 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 5 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 6 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 7 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 8 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 9 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 10 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 11 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 12 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 13 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 14 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 15 | 앞의 전환은 잘못됐어. 첫 질문의 목적과 규정 범위와 당사자 조건 전부 원래대로 다시 봐줘. 그 최초 질문까지 거슬러 확인해. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 16 | 그러면 지금 조건에서 결론과 근거를 다시 알려줘. | READY / B | COMPOSE |
| 17 | 같은 조건으로 새 대화에서 물으면 이 최종 경로를 써줘. | REUSED / B | COMPOSE |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```

### SEQ02

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규의 국내 법인 절차를 확인해줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 두 번째 질문은 내규의 해외 법인 절차야. | READY / A | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 두 번째 질문만 외규로 고쳐줘. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 4 | 두 번째 질문은 긴급 사건이라는 조건도 고려해줘. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 5 | 방금 긴급이라고 고친 건 잘못이야. 두 번째 질문은 긴급하지 않아. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 6 | 첫 번째 질문의 현재 결론은 뭐야? | INSPECTED / B |  |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```

### SEQ03

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규의 본문만 검색해서 국내 법인 절차를 확인해줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 본문만 읽은 게 문제야. 단서와 서류도 포함하도록 검색 계획과 원문 읽기부터 고쳐줘. | READY / B | PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 이제 근거 선별 단계부터 다시 검토해서 단서도 근거로 유지해줘. | READY / B | COMPOSE |
| 4 | 판단에서 긴급 여부가 빠졌어. 이 사건은 긴급이야. 다시 판단해줘. | READY / B | SELECT,ASSESS,COMPOSE |
| 5 | 지금 최종 답변만 표로 보여줘. | READY / B | COMPOSE |
| 6 | 같은 내용으로 표 대신 문장으로 자세하게 써줘. | READY / B | COMPOSE |
| 7 | 그럼 현재 적용 절차와 긴급 조건은 어떻게 돼? | INSPECTED / B |  |

미충족 항목:
```json
[
  {
    "turn": 7,
    "field": "needs_check",
    "expected": true,
    "observed": null,
    "pass": false
  }
]
```

실제 오류:
```json
[]
```

### SEQ04

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 첫 번째 경험은 내규 국내 법인의 절차 확인이야. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 두 번째 경험은 외규 해외 법인의 절차 확인이야. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 첫 번째 질문에 두 번째 경험을 잘못 연결했다고 가정하자. | FIXTURE /  |  |
| 4 | 가져온 경험이 잘못됐어. 첫 번째 질문은 첫 번째 경험으로 연결해. 두 번째 경험 자체는 유지해줘. | REUSED / B | COMPOSE |
| 5 | 첫 번째 질문에 해당하는 현재 경로로 다시 알려줘. | REUSED / B | COMPOSE |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```

### SEQ05

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규에서 국내 법인 절차를 알려줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 외규로 고쳐줘. | READY / D | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 그 정정은 잘못됐어. 다시 내규로 봐줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 4 | 국내가 아니라 해외 법인이야. | READY / A | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 5 | 두 번째 정정에서 내규로 돌린 게 잘못됐어. 외규 기준을 유지해줘. | ERROR /  | INTENT,PLAN,RECALL,READ,SELECT |
| 6 | 중단된 정정을 이어서 처리해줘. | READY / C | ASSESS,COMPOSE |
| 7 | 지금 최종 경로로 다시 답해줘. | READY / C | COMPOSE |
| 8 | 옛 실행을 다시 수집해도 최종 경로를 사용해줘. | REUSED / C | COMPOSE |

미충족 항목:
```json
[]
```

실제 오류:
```json
[
  {
    "turn": 5,
    "error": "predeclared injected stage failure"
  }
]
```


## 비용·지연·회수


```json
{
  "by_arm": {
    "CURRENT_ONLY": {
      "checks_passed": 68,
      "checks_total": 77,
      "sequences_passed": 2,
      "sequences_total": 5,
      "runtime_errors": 1
    },
    "CHAIN": {
      "checks_passed": 76,
      "checks_total": 77,
      "sequences_passed": 4,
      "sequences_total": 5,
      "runtime_errors": 1
    }
  },
  "paired": {
    "candidate_only": 2,
    "baseline_only": 0,
    "both_correct": 2,
    "both_incorrect": 1
  },
  "usage": {
    "calls": 230,
    "input_tokens": 174848,
    "output_tokens": 25227,
    "reported_cost_usd": 0.09582436,
    "reasoning_tokens": 0
  },
  "turn_latency_seconds": {
    "CURRENT_ONLY": {
      "p50": 4.164125462062657,
      "p95": 7.489335741964169
    },
    "CHAIN": {
      "p50": 4.529990877024829,
      "p95": 8.224430812057108
    }
  },
  "retrieval": {
    "CURRENT_ONLY": {
      "before_filter": 30,
      "after_filter": 15,
      "presented_total": 13,
      "presented_mean": 2.6,
      "presented_p50": 3,
      "presented_p95": 3,
      "golden_recall": 0.42857142857142855,
      "selectivity": 0.43333333333333335
    },
    "CHAIN": {
      "before_filter": 30,
      "after_filter": 15,
      "presented_total": 12,
      "presented_mean": 2.4,
      "presented_p50": 2,
      "presented_p95": 3,
      "golden_recall": 0.7142857142857143,
      "selectivity": 0.39999999999999997
    }
  }
}
```

## 범위와 한계

- Synthetic stage executor, not production API/Coordinator integration
- Gold loaded only after all product calls
- Baseline is current-only ablation, not old MAIN
- No real law, PDF ingestion, DB admin or approval implementation
- One sequential family per case; exploratory in-sample
- 세션/경로용 SQLite와 Native WorkRepository 기록은 실제 실행했다. 원문 읽기·선별·판단·작성은 합성 stage executor다.
- 기본 네 port의 생산 Coordinator, 인증 adapter, 실제 READ/presentation ledger, two-DB worker·lease·SSE·캐시 서버는 붙이지 않았다.
- 현재 경로의 오래된 revision 거부를 검사했으며, 실제 동시 서버 경합·캐시 장애 시험은 아니다.
- 법률 승인·DB 관리 기능은 이번 실험 대상에서 제외했다.
- 정식 ADR graph 검사 결과는 별도 validation receipt에서 확인한다.

[ADR 기록](../../../04_EXPERIMENTS/ADR/ADR-0593-rag-chain-native-kind-repair/README.md) · [원시 결과](../../../04_EXPERIMENTS/ADR/ADR-0593-rag-chain-native-kind-repair/artifacts/run-001/result.json)

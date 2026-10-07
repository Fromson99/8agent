# RAG 멀티턴 체인 프로토타입 결과

ADR-0592 · WSL 로컬 · 합성 원문 6단위 · 연속 대화 5개 · Qwen3.8 · MAIN 미변경

**실행 결과를 구현 범위 안에서 판정한다. 실제 RAG API/Coordinator·GENOS 연결 검증은 포함하지 않는다.**

| 흐름 | CURRENT_ONLY | CHAIN |
|---|---|---|
| SEQ01 | 0/1 | 0/1 |
| SEQ02 | 0/1 | 0/1 |
| SEQ03 | 0/1 | 0/1 |
| SEQ04 | 0/1 | 0/1 |
| SEQ05 | 0/1 | 0/1 |

## 기능별 실제 관찰

### SEQ01

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규에서 국내 법인의 긴급 예외 적용 조건을 확인해줘. | ERROR /  |  |
| 2 | 아니 외규에서 해외 법인의 필요 서류를 확인하는 것으로 바꿔줘. | ERROR /  |  |
| 3 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 4 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 5 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 6 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 7 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 8 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 9 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 10 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 11 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 12 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 13 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 14 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | ERROR /  |  |
| 15 | 앞의 전환은 잘못됐어. 첫 질문의 목적과 규정 범위와 당사자 조건 전부 원래대로 다시 봐줘. 그 최초 질문까지 거슬러 확인해. | ERROR /  |  |
| 16 | 그러면 지금 조건에서 결론과 근거를 다시 알려줘. | ERROR /  |  |
| 17 | 같은 조건으로 새 대화에서 물으면 이 최종 경로를 써줘. | ERROR /  |  |

미충족 항목:
```json
[
  {
    "field": "sequential_case_completed",
    "expected": true,
    "observed": false,
    "pass": false
  }
]
```

실제 오류:
```json
[
  {
    "turn": 1,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 2,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 3,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 4,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 5,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 6,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 7,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 8,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 9,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 10,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 11,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 12,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 13,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 14,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 15,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 16,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 17,
    "error": "experience link conditions differ or route pending"
  }
]
```

### SEQ02

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규의 국내 법인 절차를 확인해줘. | ERROR /  |  |
| 2 | 두 번째 질문은 내규의 해외 법인 절차야. | ERROR /  |  |
| 3 | 두 번째 질문만 외규로 고쳐줘. | ERROR /  |  |
| 4 | 두 번째 질문은 긴급 사건이라는 조건도 고려해줘. | ERROR /  |  |
| 5 | 방금 긴급이라고 고친 건 잘못이야. 두 번째 질문은 긴급하지 않아. | ERROR /  |  |
| 6 | 첫 번째 질문의 현재 결론은 뭐야? | INSPECTED /  |  |

미충족 항목:
```json
[
  {
    "field": "sequential_case_completed",
    "expected": true,
    "observed": false,
    "pass": false
  }
]
```

실제 오류:
```json
[
  {
    "turn": 1,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 2,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 3,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 4,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  },
  {
    "turn": 5,
    "error": "CHECK constraint failed: kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review')"
  }
]
```

### SEQ03

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규의 본문만 검색해서 국내 법인 절차를 확인해줘. | NOT_RUN /  |  |
| 2 | 본문만 읽은 게 문제야. 단서와 서류도 포함하도록 검색 계획과 원문 읽기부터 고쳐줘. | NOT_RUN /  |  |
| 3 | 이제 근거 선별 단계부터 다시 검토해서 단서도 근거로 유지해줘. | NOT_RUN /  |  |
| 4 | 판단에서 긴급 여부가 빠졌어. 이 사건은 긴급이야. 다시 판단해줘. | NOT_RUN /  |  |
| 5 | 지금 최종 답변만 표로 보여줘. | NOT_RUN /  |  |
| 6 | 같은 내용으로 표 대신 문장으로 자세하게 써줘. | NOT_RUN /  |  |
| 7 | 그럼 현재 적용 절차와 긴급 조건은 어떻게 돼? | NOT_RUN /  |  |

미충족 항목:
```json
[
  {
    "field": "sequential_case_completed",
    "expected": true,
    "observed": false,
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
| 1 | 첫 번째 경험은 내규 국내 법인의 절차 확인이야. | NOT_RUN /  |  |
| 2 | 두 번째 경험은 외규 해외 법인의 절차 확인이야. | NOT_RUN /  |  |
| 3 | 첫 번째 질문에 두 번째 경험을 잘못 연결했다고 가정하자. | NOT_RUN /  |  |
| 4 | 가져온 경험이 잘못됐어. 첫 번째 질문은 첫 번째 경험으로 연결해. 두 번째 경험 자체는 유지해줘. | NOT_RUN /  |  |
| 5 | 첫 번째 질문에 해당하는 현재 경로로 다시 알려줘. | NOT_RUN /  |  |

미충족 항목:
```json
[
  {
    "field": "sequential_case_completed",
    "expected": true,
    "observed": false,
    "pass": false
  }
]
```

실제 오류:
```json
[]
```

### SEQ05

| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규에서 국내 법인 절차를 알려줘. | NOT_RUN /  |  |
| 2 | 외규로 고쳐줘. | NOT_RUN /  |  |
| 3 | 그 정정은 잘못됐어. 다시 내규로 봐줘. | NOT_RUN /  |  |
| 4 | 국내가 아니라 해외 법인이야. | NOT_RUN /  |  |
| 5 | 두 번째 정정에서 내규로 돌린 게 잘못됐어. 외규 기준을 유지해줘. | NOT_RUN /  |  |
| 6 | 중단된 정정을 이어서 처리해줘. | NOT_RUN /  |  |
| 7 | 지금 최종 경로로 다시 답해줘. | NOT_RUN /  |  |
| 8 | 옛 실행을 다시 수집해도 최종 경로를 사용해줘. | NOT_RUN /  |  |

미충족 항목:
```json
[
  {
    "field": "sequential_case_completed",
    "expected": true,
    "observed": false,
    "pass": false
  }
]
```

실제 오류:
```json
[]
```


## 비용·지연·회수


```json
{
  "by_arm": {
    "CURRENT_ONLY": {
      "checks_passed": 0,
      "checks_total": 5,
      "sequences_passed": 0,
      "sequences_total": 5,
      "observed_turns": 22,
      "runtime_errors": 22
    },
    "CHAIN": {
      "checks_passed": 0,
      "checks_total": 5,
      "sequences_passed": 0,
      "sequences_total": 5,
      "observed_turns": 23,
      "runtime_errors": 22
    }
  },
  "paired": {
    "candidate_only": 0,
    "baseline_only": 0,
    "both_correct": 0,
    "both_incorrect": 5
  },
  "usage": {
    "calls": 43,
    "input_tokens": 39444,
    "output_tokens": 5859,
    "reported_cost_usd": 0.02235636
  },
  "retrieval": {
    "CURRENT_ONLY": {
      "before_filter": 0,
      "after_filter": 0,
      "presented_total": 0,
      "presented_mean": 0,
      "presented_p50": 0,
      "presented_p95": 0,
      "golden_recall": 0.0,
      "selectivity": 0.0
    },
    "CHAIN": {
      "before_filter": 0,
      "after_filter": 0,
      "presented_total": 0,
      "presented_mean": 0,
      "presented_p50": 0,
      "presented_p95": 0,
      "golden_recall": 0.0,
      "selectivity": 0.0
    }
  },
  "turn_latency_seconds": {}
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

[ADR 기록](../../../04_EXPERIMENTS/ADR/ADR-0592-rag-chain-sequential-prototype/README.md) · [원시 결과](../../../04_EXPERIMENTS/ADR/ADR-0592-rag-chain-sequential-prototype/artifacts/run-001/result.json)

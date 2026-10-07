# 멀티턴 체인 엄격 수정 결과

ADR-0596 · WSL 로컬 · 합성 원문 6단위 · 6개 연속 대화·49턴 · Qwen3.8 · MAIN 미변경

이번 구현은 research 프로토다. 실제 RAG API/Coordinator, GENOS, 의미 기반 wiki 검색, DB 관리·법률 승인 연결은 포함하지 않는다.

순차 기능 검사 **219/258**, 전체 사례 **0/6**. 모델 0회 adversarial 계약 **24/24**, 실제 모델 text 검증기 calibration **13/15**(false pass 0, false fail 2).

## 원인별 수정

| 원인 | 수정 |
|---|---|
| FOLLOW가 명시 단계를 덮어씀 | 지정한 단계와 변경 조건·pending 중 가장 앞단부터 재실행 |
| 원본 없는 복원 명령 수용 | 동일 질문의 회수 원발언 확인; 원본이 없으면 상태를 바꾸지 않고 적용 보류 |
| 직접 변경/과거 복원 표현 차이로 정상 요청 거부 | 실제 적용 값의 의미 동등성 확인, 불필요한 복원 메타데이터 정리, 명령 수리 최대 1회 |
| 기존 근거 설명에 재판단 실행 | 설명은 COMPOSE, 선별·검토·판단 요청은 해당 단계로 구분 |
| 조회/재사용 응답에 판단 누락 | 소비 경로의 immutable 노드에서 assessment·retrieval·goal·revision 함께 반환 |
| 다른 질문의 마지막 검색을 집계 | 최종 응답의 실제 route_id와 goal에 집계 결속 |
| LLM 답변 문장이 현재 판단과 모순 | facts·절차·출처의 기계 검사와 text 검증; 작성 수리 1회 실패하면 게시 차단 |
| 긴급 미확인과 비긴급을 혼동 | null/false/true를 상태·판단·답변에서 유지 |
| native 기록 실패 뒤 head 변경 | node/head 트랜잭션 롤백 |

## 관측 누락을 포함한 별도 확인


```json
{
  "unexpected_status": 15,
  "unnecessary_reassessment": 0,
  "final_text_mismatch": 0,
  "response_binding_errors": 0,
  "rejected_drafts": 27,
  "command_repairs": 1
}
```

재시도는 제품 command 1회·compose 1회로 제한하며 원 요청·거절 이유·수리 결과를 기록한다. 실험 전체를 몰래 재실행하지 않는다.

## 기능별 확인

| 사례 | 통과 검사 | 핵심 확인 |
|---|---|---|
| SEQ01 | 85/94 | 긴 대화의 최초 조건 역추적, 설명 12턴의 upstream 유지, 최종 경로 재사용 |
| SEQ02 | 13/25 | 다른 질문 보존, 정정·재정정·조회 |
| SEQ03 | 42/45 | PLAN·SELECT 재진입, 표/문장 작성만 실행, 긴급 판단 조회 |
| SEQ04 | 23/25 | 잘못 연결한 경험만 수정, 다른 묶음 보존 |
| SEQ05 | 25/33 | 반복 정정·오차단 회귀·ASSESS 실패 후 재개·퇴역 경로 재수집 차단 |
| GUARD | 31/36 | 미확인→비긴급→긴급→미확인, 조회·재사용 |

## 미충족 항목


```json
[
  {
    "case": "SEQ01",
    "checks": [
      {
        "turn": 2,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 15,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "CLARIFY",
        "pass": false
      },
      {
        "turn": 2,
        "field": "procedure",
        "expected": "C",
        "observed": null,
        "pass": false
      },
      {
        "turn": 15,
        "field": "scope",
        "expected": "INTERNAL",
        "observed": "EXTERNAL",
        "pass": false
      },
      {
        "turn": 15,
        "field": "party",
        "expected": "DOMESTIC",
        "observed": "FOREIGN",
        "pass": false
      },
      {
        "turn": 15,
        "field": "task",
        "expected": "EXCEPTION",
        "observed": "DOCUMENTS",
        "pass": false
      },
      {
        "turn": 15,
        "field": "procedure",
        "expected": "B",
        "observed": null,
        "pass": false
      },
      {
        "turn": 16,
        "field": "procedure",
        "expected": "B",
        "observed": "C",
        "pass": false
      },
      {
        "turn": 17,
        "field": "procedure",
        "expected": "B",
        "observed": "C",
        "pass": false
      }
    ]
  },
  {
    "case": "SEQ02",
    "checks": [
      {
        "turn": 1,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 2,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 3,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 5,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 6,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "\u0050ENDING",
        "pass": false
      },
      {
        "turn": 1,
        "field": "procedure",
        "expected": "B",
        "observed": null,
        "pass": false
      },
      {
        "turn": 2,
        "field": "procedure",
        "expected": "A",
        "observed": null,
        "pass": false
      },
      {
        "turn": 3,
        "field": "procedure",
        "expected": "C",
        "observed": null,
        "pass": false
      },
      {
        "turn": 5,
        "field": "needs_check",
        "expected": false,
        "observed": null,
        "pass": false
      },
      {
        "turn": 6,
        "field": "procedure",
        "expected": "B",
        "observed": null,
        "pass": false
      },
      {
        "field": "closed_routes",
        "expected": true,
        "observed": false,
        "pass": false
      },
      {
        "field": "stale_publication_blocked",
        "expected": true,
        "observed": false,
        "pass": false
      }
    ]
  },
  {
    "case": "SEQ03",
    "checks": [
      {
        "turn": 2,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 2,
        "field": "procedure",
        "expected": "B",
        "observed": null,
        "pass": false
      },
      {
        "turn": 2,
        "field": "required_stage_descendants",
        "expected": [
          "PLAN",
          "RECALL",
          "READ",
          "SELECT",
          "ASSESS",
          "COMPOSE"
        ],
        "observed": [
          "PLAN",
          "RECALL",
          "READ",
          "SELECT",
          "ASSESS"
        ],
        "pass": false
      }
    ]
  },
  {
    "case": "SEQ04",
    "checks": [
      {
        "turn": 2,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 2,
        "field": "procedure",
        "expected": "C",
        "observed": null,
        "pass": false
      }
    ]
  },
  {
    "case": "SEQ05",
    "checks": [
      {
        "turn": 1,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 2,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 3,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 4,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 1,
        "field": "procedure",
        "expected": "B",
        "observed": null,
        "pass": false
      },
      {
        "turn": 2,
        "field": "procedure",
        "expected": "D",
        "observed": null,
        "pass": false
      },
      {
        "turn": 3,
        "field": "procedure",
        "expected": "B",
        "observed": null,
        "pass": false
      },
      {
        "turn": 4,
        "field": "procedure",
        "expected": "A",
        "observed": null,
        "pass": false
      }
    ]
  },
  {
    "case": "GUARD",
    "checks": [
      {
        "turn": 1,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 3,
        "field": "request_completed_or_predeclared_fault",
        "expected": [
          "INSPECTED",
          "READY",
          "REUSED"
        ],
        "observed": "ERROR",
        "pass": false
      },
      {
        "turn": 1,
        "field": "procedure",
        "expected": "B",
        "observed": null,
        "pass": false
      },
      {
        "turn": 3,
        "field": "urgent",
        "expected": true,
        "observed": false,
        "pass": false
      },
      {
        "turn": 3,
        "field": "needs_check",
        "expected": true,
        "observed": null,
        "pass": false
      }
    ]
  }
]
```

## 비용·지연·범위


```json
{
  "by_arm": {
    "BLIND": {
      "checks_passed": 219,
      "checks_total": 258,
      "sequences_passed": 0,
      "sequences_total": 6,
      "runtime_errors": 14
    }
  },
  "paired": {},
  "retrieval": {
    "BLIND": {
      "before_filter": 30,
      "after_filter": 15,
      "presented_total": 13,
      "presented_mean": 2.1666666666666665,
      "presented_p50": 2.5,
      "presented_p95": 3,
      "golden_recall": 0.6666666666666666,
      "selectivity": 0.3611111111111111
    }
  },
  "judge_disagreements": 0,
  "guard_checks": {
    "passed": 24,
    "total": 24
  },
  "calibration": {
    "passed": 13,
    "total": 15,
    "false_pass": 0,
    "false_fail": 2
  },
  "turn_latency_seconds": {
    "BLIND": {
      "p50": 12.706670265994035,
      "p95": 19.106990901986137
    }
  },
  "usage": {
    "calls": 322,
    "input_tokens": 253195,
    "output_tokens": 39222,
    "reported_cost_usd": 0.14586352,
    "reasoning_tokens": 0
  }
}
```

코드·schema·prompt를 바꾼 인샘플 실험이므로 일반 법률 정확도나 GENOS 성능으로 일반화하지 않는다. 검증기 calibration 15개는 작은 합성 표본이며 완전한 의미 검증을 인증하지 않는다.

[전체 턴·모델 원문](../../../04_EXPERIMENTS/ADR/ADR-0596-rag-chain-blind-text-facts/실험/README.md) · [코드·계보](../../../04_EXPERIMENTS/ADR/ADR-0596-rag-chain-blind-text-facts/README.md)

# 멀티턴 체인 엄격 수정 결과

ADR-0598 · WSL 로컬 · 합성 원문 6단위 · 6개 연속 대화·49턴 · Qwen3.8 · MAIN 미변경

이번 구현은 research 프로토다. 원문 검색은 합성 stage executor이고 상태·경로는 실제 SQLite/NativeRepository에 저장한다. 실제 RAG API/Coordinator·GENOS·의미 기반 wiki 검색·공통 온톨로지 DB 적재기는 아직 연결하지 않았다. 질문 대상 goal_anchor는 테스트 입력에서 제공한다.

순차 기능 검사 **297/300**, 전체 사례 **5/6**. 모델 0회 adversarial 계약 **30/30**, 실제 모델 text 검증기 calibration **17/17**(false pass 0, false fail 0).

## 원인별 수정

| 원인 | 수정 |
|---|---|
| FOLLOW가 명시 단계를 덮어씀 | 지정한 단계와 변경 조건·pending 중 가장 앞단부터 재실행 |
| 원본 없는 복원 명령 수용 | 동일 질문의 회수 원발언 확인; 원본이 없으면 상태를 바꾸지 않고 적용 보류 |
| 정정 순번을 발언 순번으로 오독 | 같은 goal의 정정별 ordinal·turn_id·변경 전후 조건·변경 필드를 실제 immutable node에서 구성 |
| 답변 수리가 실패 초안/과거 답변을 그대로 반복 | 충돌 과거 답변 제외, 수리에는 실패 초안 대신 정확한 사실 문구·필수 출처를 전달 |
| 직접 변경/과거 복원 표현 차이로 정상 요청 거부 | 실제 적용 값의 의미 동등성 확인, 불필요한 복원 메타데이터 정리, 명령 수리 최대 1회 |
| 기존 근거 설명에 재판단 실행 | 설명은 COMPOSE, 선별·검토·판단 요청은 해당 단계로 구분 |
| 조회/재사용 응답에 판단 누락 | 소비 경로의 immutable 노드에서 assessment·retrieval·goal·revision 함께 반환 |
| 다른 질문의 마지막 검색을 집계 | 최종 응답의 실제 route_id와 goal에 집계 결속 |
| LLM 답변 문장이 현재 판단과 모순 | facts·절차·출처의 기계 검사와 text 검증; 작성 수리 1회 실패하면 게시 차단 |
| 검증 LLM이 기대값에 맞춰 틀린 문장도 통과시킴 | 기대값 없이 text만 추출한 후 실제 용어·원문 span을 현재 사실과 대조 |
| 추출기가 표현을 바꿔 인용하거나 사실 확인과 예외 판단을 혼동 | 의미값은 유지한 채 실제 text의 인용구만 회복; true/false/null 별칭과 사실/예외 구분 |
| 긴급 미확인과 비긴급을 혼동 | null/false/true를 상태·판단·답변에서 유지 |
| native 기록 실패 뒤 head 변경 | node/head 트랜잭션 롤백 |

## 관측 누락을 포함한 별도 확인


```json
{
  "unexpected_status": 1,
  "unnecessary_reassessment": 0,
  "final_text_mismatch": 0,
  "response_binding_errors": 0,
  "rejected_drafts": 1,
  "command_repairs": 0
}
```

재시도는 제품 command 1회·compose 1회로 제한하며 원 요청·거절 이유·수리 결과를 기록한다. 실험 전체를 몰래 재실행하지 않는다.

## 기능별 확인

| 사례 | 통과 검사 | 핵심 확인 |
|---|---|---|
| SEQ01 | 100/100 | 긴 대화의 최초 조건 역추적, 설명 12턴의 upstream 유지, 최종 경로 재사용 |
| SEQ02 | 40/40 | 다른 질문 보존, 정정·재정정·조회 |
| SEQ03 | 48/48 | PLAN·SELECT 재진입, 표/문장 작성만 실행, 긴급 판단 조회 |
| SEQ04 | 28/28 | 잘못 연결한 경험만 수정, 다른 묶음 보존 |
| SEQ05 | 45/45 | 반복 정정·오차단 회귀·ASSESS 실패 후 재개·퇴역 경로 재수집 차단 |
| GUARD | 36/39 | 미확인→비긴급→긴급→미확인, 조회·재사용 |

## 미충족 항목


```json
[
  {
    "case": "GUARD",
    "checks": [
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

## 실제 연결 범위
실행한 경로: 합성 사용자 요청 → LLM 명령 해석·검증/수리 → 동일 goal 이력 역추적 → 지정 stage와 영향을 받는 하위 stage → 실제 SQLite 노드/의존 관계 저장 → 유효 route 선택 → 새 요청의 consume → 답변 text 검사 → 게시.
reingest는 퇴역 route 제외 계약을 검사한다. 실제 온톨로지 레코드 생성·공통 DB 저장·의미 검색은 이 프로토에서 실행하지 않았다.
상태/원기록/퇴역 경로는 감사용으로 보존하지만 지식 재사용은 현재 유효 route만 소비한다.
목표 선택을 LLM이 자연어로 찾아내는 품질, 임의 법률 문장 검사, 여러 세션의 동시 변경·분산 트랜잭션은 미검증이다.
## 비용·지연·범위


```json
{
  "by_arm": {
    "GROUNDED": {
      "checks_passed": 297,
      "checks_total": 300,
      "sequences_passed": 5,
      "sequences_total": 6,
      "runtime_errors": 2
    }
  },
  "paired": {},
  "retrieval": {
    "GROUNDED": {
      "before_filter": 36,
      "after_filter": 18,
      "presented_total": 12,
      "presented_mean": 2,
      "presented_p50": 2.0,
      "presented_p95": 2,
      "golden_recall": 1.0,
      "selectivity": 0.3333333333333333
    }
  },
  "judge_disagreements": 0,
  "guard_checks": {
    "passed": 30,
    "total": 30
  },
  "calibration": {
    "passed": 17,
    "total": 17,
    "false_pass": 0,
    "false_fail": 0
  },
  "turn_latency_seconds": {
    "GROUNDED": {
      "p50": 12.561921510030515,
      "p95": 16.846585009945557
    }
  },
  "usage": {
    "calls": 328,
    "input_tokens": 273691,
    "output_tokens": 38751,
    "reported_cost_usd": 0.14423484,
    "reasoning_tokens": 0
  }
}
```

코드·schema·prompt를 바꾼 인샘플 실험이므로 일반 법률 정확도나 GENOS 성능으로 일반화하지 않는다. 검증기 calibration 17개는 작은 합성 표본이며 완전한 의미 검증을 인증하지 않는다.

[전체 턴·모델 원문](../../../04_EXPERIMENTS/ADR/ADR-0598-rag-chain-ordinal-grounded-repair/실험/README.md) · [코드·계보](../../../04_EXPERIMENTS/ADR/ADR-0598-rag-chain-ordinal-grounded-repair/README.md)

# 멀티턴 체인 엄격 수정 결과

ADR-0605 · WSL 로컬 · 합성 원문 6단위 · 6개 연속 대화·49턴 · Qwen3.8 · MAIN 미변경

이번 구현은 research 프로토다. 원문 검색은 합성 stage executor이고 상태·경로는 실제 SQLite/NativeRepository에 저장한다. 실제 RAG API/Coordinator·GENOS·의미 기반 wiki 검색·공통 온톨로지 DB 적재기는 아직 연결하지 않았다. 질문 대상 goal_anchor는 테스트 입력에서 제공한다.

순차 기능 검사 **303/303**, 전체 사례 **6/6**. 모델 0회 adversarial 계약 **35/35**, 실제 모델 text 검증기 calibration **17/17**(false pass 0, false fail 0).

## 원인별 수정

| 원인 | 수정 |
|---|---|
| FOLLOW가 명시 단계를 덮어씀 | 지정한 단계와 변경 조건·pending 중 가장 앞단부터 재실행 |
| 현재 발언을 과거 출처로 오독하면 수리 전에 중단 | 현재 turn_id와 회수된 과거 ID 목록을 명시; 입구 오류도 상태 변경 전 한 번만 재해석, 재실패하면 차단 |
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
  "unexpected_status": 0,
  "unnecessary_reassessment": 0,
  "final_text_mismatch": 0,
  "response_binding_errors": 0,
  "rejected_drafts": 3,
  "command_repairs": 1
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
| GUARD | 42/42 | 미확인→비긴급→긴급→미확인, 조회·재사용 |

## 기능 단위의 직접 검사
| 기능 | 통과 / 검사 |
|---|---|
| 요청 완료 / 사전 선언한 장애 감지 | 49/49 |
| 최초 원발언을 실제 회수·참조 | 1/1 |
| 표현 변경 시 앞단 유지 | 2/2 |
| 지정 단계와 후속 단계 실행 | 14/14 |
| 응답의 목표·경로·리비전 결속 | 47/47 |
| 조회/응답에 실제 판단·근거 반환 | 47/47 |
| 게시 문장의 현재 판단 일치 | 47/47 |
| 무관한 질문 유지 | 1/1 |
| 무관한 해결 묶음 유지 | 1/1 |
| 잘못 연결한 경험 링크 수정 | 1/1 |
| 후속 요청이 유효 경로 소비 | 3/3 |
| 재판단 실패 때 과거 경로 차단 | 1/1 |
| 퇴역 경로 제외 계약 | 1/1 |
| 현재 경로의 의존 관계 완결 | 6/6 |
| 낡은 리비전 게시 거부 | 6/6 |
| NativeRepository에 의존 관계 기록 | 6/6 |
| 목표마다 유효 경로 하나 유지 | 6/6 |
47개 일반 완료 응답, 사전 선언 ASSESS 장애 1턴, 잘못된 wiki 연결을 심는 fixture 1턴으로 구성한다. 상태가 다르면 실제 결과의 판정을 따른다.
퇴역 경로 제외는 reingest 계약 검사이며 공통 온톨로지 DB 적재기 검증이 아니다.

## 미충족 항목


```json
[]
```

## 실제 연결 범위
실행한 경로: 합성 사용자 요청 → LLM 명령 해석·검증/수리 → 동일 goal 이력 역추적 → 지정 stage와 영향을 받는 하위 stage → 실제 SQLite 노드/의존 관계 저장 → 유효 route 선택 → 새 요청의 consume → 답변 text 검사 → 게시.
reingest는 퇴역 route 제외 계약을 검사한다. 실제 온톨로지 레코드 생성·공통 DB 저장·의미 검색은 이 프로토에서 실행하지 않았다.
상태/원기록/퇴역 경로는 감사용으로 보존하지만 지식 재사용은 현재 유효 route만 소비한다.
목표 선택을 LLM이 자연어로 찾아내는 품질, 임의 법률 문장의 모든 세부 주장·수치·인용에 대한 원문 함의 검사, 변경된 원문 세대와 재사용 경로의 결속, 여러 세션의 동시 변경·분산 트랜잭션은 미검증이다. 본 text 검사는 합성 절차·범위·법인·긴급 상태·예외 확인 및 제공 출처 집합으로 한정된다.
## 제공자 오류를 포함한 실행 기록
제품 구현은 완료된 부모 ADR0601 SAFE_STATE와 byte-exact하게 같다. 달라진 것은 실험 호출의 동시 요청 1개, 요청 간격 1초, retryable HTTP 오류 대기 5초 후 최대 1회 재시도다. command/compose 수리는 각각 최대 1회를 유지한다. 모델·Parasail FP8·reasoning none·fallback 없음도 유지한다.
Transport 재시도는 원 실패 response와 별도 receipt로 기록한다. 실패 호출의 사용량이 제공되지 않으면 0으로 추정하지 않고 미확인으로 남긴다.
이전 실험은 595의 문장 검사 false pass, 596의 정상 문장 false rejection, 597의 의미 수리 실패, 598의 출처 입구 수리 누락, 599의 공급자 429 실패를 그대로 보존했다. 성공 실행만 남긴 결과로 해석하지 않는다.
## 비용·지연·범위


```json
{
  "by_arm": {
    "RETEST": {
      "checks_passed": 303,
      "checks_total": 303,
      "sequences_passed": 6,
      "sequences_total": 6,
      "runtime_errors": 1
    }
  },
  "paired": {},
  "retrieval": {
    "RETEST": {
      "before_filter": 36,
      "after_filter": 18,
      "presented_total": 13,
      "presented_mean": 2.1666666666666665,
      "presented_p50": 2.0,
      "presented_p95": 3,
      "golden_recall": 1.0,
      "selectivity": 0.3611111111111111
    }
  },
  "judge_disagreements": 0,
  "guard_checks": {
    "passed": 35,
    "total": 35
  },
  "calibration": {
    "passed": 17,
    "total": 17,
    "false_pass": 0,
    "false_fail": 0
  },
  "turn_latency_seconds": {
    "RETEST": {
      "p50": 15.987164413090795,
      "p95": 24.927967014955357
    }
  },
  "usage": {
    "calls": 341,
    "input_tokens": 292356,
    "output_tokens": 39317,
    "reported_cost_usd": 0.15189612,
    "reasoning_tokens": 0
  },
  "transport": {
    "request_attempts": 341,
    "provider_error_attempts": 0,
    "retry_scheduled": 0,
    "failed_request_usage": "unavailable unless returned by provider; not imputed as zero",
    "budget": {
      "concurrent_requests": 1,
      "max_retryable_http_retries": 1,
      "backoff_seconds": 5,
      "gap_seconds": 1
    }
  }
}
```

코드·schema·prompt를 바꾼 인샘플 실험이므로 일반 법률 정확도나 GENOS 성능으로 일반화하지 않는다. 검증기 calibration 17개는 작은 합성 표본이며 완전한 의미 검증을 인증하지 않는다.

[전체 턴·모델 원문](../../../04_EXPERIMENTS/ADR/ADR-0605-corrected-chain-full-model-regression/실험/README.md) · [코드·계보](../../../04_EXPERIMENTS/ADR/ADR-0605-corrected-chain-full-model-regression/README.md)

# 엄격 수정 프로토와 제공자 중단 기록

**코드·32개 계약 검사·3개 HTTP 재시도 단위 검사는 완료했다. 전체 실제 모델 검증은 HTTP429로 미완료다.**

ADR0599와 제품 코드는 byte-exact하다. 모델·Parasail FP8·reasoning none·fallback 없음도 유지했다. 대기 5초 후 최대 1회 재시도했지만 공유 풀 제한이 계속되어 추가 호출을 중단했다.


```json
{
  "execution_aborted": true,
  "cause": "Parasail shared upstream pool HTTP429 persisted through one bounded retry; offline audit aborted",
  "turns_attempted": 49,
  "turn_status": {
    "READY": 19,
    "ERROR": 29,
    "INSPECTED": 1
  },
  "error_type_counts": {
    "ExperimentProviderError": 24,
    "GuardError": 4,
    "TypeError": 1
  },
  "completed_text_audits": 4,
  "functional_score": null,
  "calibration_this_run": "not_executed",
  "guard_checks": {
    "passed": 32,
    "total": 32
  },
  "transport_unit": {
    "kind": "ordinary runner transport unit check; no real model calls",
    "checks": [
      {
        "name": "one retryable HTTP failure recovers once",
        "passed": true
      },
      {
        "name": "second provider failure stops",
        "passed": true
      },
      {
        "name": "nonretryable provider failure not retried",
        "passed": true
      }
    ],
    "passed": 3,
    "total": 3
  },
  "transport": {
    "request_attempts": 188,
    "http429_error_attempts": 59,
    "retry_scheduled": 33,
    "failed_request_usage": "unavailable, not imputed as zero"
  },
  "usage": {
    "successful_calls_with_usage": 129,
    "input_tokens": 123998,
    "output_tokens": 15325,
    "reported_successful_cost_usd": 0.0594526
  }
}
```

동일 제품의 실제 모델 문장 검사 17/17은 [ADR0599](ADR-0599_RAG_CHAIN_STRICT_REPAIR_20261001.md)에서 확인했다. 이번 run의 calibration 통과로 바꾸어 말하지 않는다.

원인별 구현 변경·함수 위치는 ADR0599 보고서를 따른다. 공통 온톨로지 DB 적재·의미 기반 wiki 검색·실제 RAG/GENOS는 미연결이다. 이번 SQLite 기록은 작업 상태/감사이며 지식 재사용은 현재 유효 route만 소비한다.

[실제 턴·전체 모델 원문](../../../04_EXPERIMENTS/ADR/ADR-0600-rag-chain-bounded-provider-retest/실험/README.md)

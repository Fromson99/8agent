# 정정 체인 프로토 엄격 수정 검토

**코드 수정 후보와 일반 계약 검사 35/35를 완료했다. 실제 모델의 전체 49턴 재검증은 제공자 HTTP429로 미완료다. MAIN/GENOS에는 적용하지 않았다.**

같은 답변 검사 함수·prompt의 실제 Qwen3.8 문장 calibration은 ADR0599에서 17/17(잘못된 문장 통과 0, 정상 문장 오차단 0)이었다. 새 49턴 실행의 통과 점수로 대신하지 않는다.

## 원인과 수정 위치

| 직접 원인 | 수정 | 함수/계약 |
|---|---|---|
| FOLLOW 처리에서 명시 재검토 단계를 COMPOSE로 덮어씀 | 명시 stage, 조건 변경 영향, pending 중 가장 이른 단계부터 실행 | process / STAGES |
| 과거 조건 복원에 실제 원발언 검사가 없음 | 같은 goal의 회수 원발언·immutable input에서 조건 확인, 원기록이 없으면 적용 보류 | context / origin_config |
| 두 번째 정정을 두 번째 발언으로 읽음 | 정정 ordinal과 turn_id, 변경 전후 조건, 변경 필드를 분리해 제공 | context.correction_chain |
| 현재 발언 번호를 과거 출처로 넣으면 수리 전에 예외 종료 | current_turn_id·allowed_original_refs 명시, 입구 오류도 한 번 재해석, 재실패하면 변경 전 거부 | process / COMMAND_ADMISSION |
| 조회·재사용에 판단과 실제 소비 경로가 빠짐 | 소비 route의 실제 노드에서 assessment·retrieval·goal·revision 반환 | envelope / route_parts |
| 집계기가 다른 질문의 마지막 검색을 사용 | 응답 route_id와 goal의 실제 소비 경로에서 계측 | frozen experiment measured_route / ledger |
| 작성 LLM이 판단을 바꾸거나 검사 LLM이 기대값에 맞춰 잘못 읽음 | 사실·출처 기계 검사, 기대값 없는 text 추출, 실제 span/용어 대조, 별도 전체 문장 검사 | compose_checked / text_fact_errors |
| 정상 표현의 인용구를 바꾸고 사실 확인과 예외 판단을 혼동 | 추출 의미값 유지, 실제 text 인용구만 회복; false/null/true와 사실/예외 구분 | normalize_text_evidence |
| 수리 LLM이 실패 초안·과거 답변을 반복 | 충돌 과거 답변 제외, 실패 초안 대신 정확한 사실 문구·필수 출처를 전달하여 새로 작성 | compose_checked repair_targets |
| 긴급 미확인과 비긴급을 합침 | None/False/True를 상태·판단·작성에 유지 | urgent / needs_check |
| native 기록 실패 뒤 head가 바뀔 수 있음 | node/head 트랜잭션 롤백, pending 재개, 낡은 경로 게시 거부 | put / publish_guard |
| 제공자 장애로 초기 goal이 없으면 조회·시험 연결에서 NoneType 오류 | 없음 상태는 구조화 PENDING, 재사용·연결은 초기 상태 확인 후 수행 | envelope / consume / process |

## 실제 연결과 소비

합성 요청 → 명령 해석/검사/최대 1회 수리 → 동일 goal의 정정 체인 역추적 → 필요한 논리 stage 및 후속 실행 → 실제 SQLite node/edge/head/route 저장과 NativeRepository 의존 관계 → 현재 유효 경로 소비 → 답변 검사 → 게시를 프로토로 구성했다.

작업 상태/발언/퇴역 경로는 감사용으로 보존한다. 지식 재사용은 최종 ACTIVE route만 소비한다. 수정 시 영향받는 옛 route를 RETIRED로 바꾸고, 실패 상태를 READY로 게시하지 않는다.

**공통 온톨로지 DB 적재기는 미연결이다.** reingest는 퇴역 route 제외 계약을 검사할 뿐 실제 온톨로지 레코드를 적재하는 코드가 아니다. 실제 서비스/API/Coordinator·legal_wiki/user_wiki 의미 검색·GENOS·인증/공유 세션 처리도 이번 프로토에 연결하지 않았다.

## 확인 결과

| 확인 | 결과 | 해석 |
|---|---|---|
| 기존 정정·단계·출처·게시 계약 + 초기 상태 없음 3개 | 35/35 | Scripted 모델 출력을 쓰는 일반 상태/트랜잭션 검사, 외부 모델 0회 |
| 같은 text 검사 함수·prompt, 실제 Qwen 문장 17개 | 17/17 | ADR0599의 완료 기록, 새 전체 실행 점수는 아님 |
| 제한 HTTP 재시도 단위 검사 | 3/3 | 1회 복구, 재실패 중단, 비재시도 오류 즉시 중단 |
| 최신 49턴 실제 모델 재검증 | 미완료 | ADR0600에서 59개 HTTP429 응답, audit 중단; 전체 점수 생성하지 않음 |

35개 상세 판정:
```json
[
  {
    "name": "explicit FOLLOW re-entry INTENT",
    "pass": true,
    "detail": {
      "executed": [
        "INTENT",
        "PLAN",
        "RECALL",
        "READ",
        "SELECT",
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "explicit FOLLOW re-entry PLAN",
    "pass": true,
    "detail": {
      "executed": [
        "PLAN",
        "RECALL",
        "READ",
        "SELECT",
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "explicit FOLLOW re-entry RECALL",
    "pass": true,
    "detail": {
      "executed": [
        "RECALL",
        "READ",
        "SELECT",
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "explicit FOLLOW re-entry READ",
    "pass": true,
    "detail": {
      "executed": [
        "READ",
        "SELECT",
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "explicit FOLLOW re-entry SELECT",
    "pass": true,
    "detail": {
      "executed": [
        "SELECT",
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "explicit FOLLOW re-entry ASSESS",
    "pass": true,
    "detail": {
      "executed": [
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "explicit FOLLOW re-entry COMPOSE",
    "pass": true,
    "detail": {
      "executed": [
        "COMPOSE"
      ]
    }
  },
  {
    "name": "missing original cannot mutate or answer",
    "pass": true,
    "detail": {
      "status": "CLARIFY",
      "unchanged_revision": 1
    }
  },
  {
    "name": "restore ignores invented command value and uses immutable origin",
    "pass": true,
    "detail": {
      "scope": "INTERNAL",
      "original_refs": [
        1
      ]
    }
  },
  {
    "name": "pending earlier re-entry is not replaced by resume stage",
    "pass": true,
    "detail": {
      "executed": [
        "PLAN",
        "RECALL",
        "READ",
        "SELECT",
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "foreign goal provenance rejected",
    "pass": true,
    "detail": "foreign refs rejected before mutation"
  },
  {
    "name": "PRESENT cannot bypass upstream edits",
    "pass": true,
    "detail": {
      "executed": [
        "PLAN",
        "RECALL",
        "READ",
        "SELECT",
        "ASSESS",
        "COMPOSE"
      ]
    }
  },
  {
    "name": "INSPECT REUSE complete route envelopes",
    "pass": true,
    "detail": [
      "INSPECTED",
      "REUSED"
    ]
  },
  {
    "name": "unknown false true remain distinct",
    "pass": true,
    "detail": [
      false,
      true,
      null
    ]
  },
  {
    "name": "invalid answer blocks publication and bounded resume: bad_facts",
    "pass": true,
    "detail": {
      "rejected_attempts": 2,
      "resumed": [
        "COMPOSE"
      ]
    }
  },
  {
    "name": "invalid answer blocks publication and bounded resume: bad_sources",
    "pass": true,
    "detail": {
      "rejected_attempts": 2,
      "resumed": [
        "COMPOSE"
      ]
    }
  },
  {
    "name": "invalid answer blocks publication and bounded resume: bad_procedure",
    "pass": true,
    "detail": {
      "rejected_attempts": 2,
      "resumed": [
        "COMPOSE"
      ]
    }
  },
  {
    "name": "invalid answer blocks publication and bounded resume: reject_text",
    "pass": true,
    "detail": {
      "rejected_attempts": 2,
      "resumed": [
        "COMPOSE"
      ]
    }
  },
  {
    "name": "final inspect retrieval is actual G1 route despite later G2 execution",
    "pass": true,
    "detail": {
      "consumed_goal": "G1",
      "last_other_goal": "G2"
    }
  },
  {
    "name": "stale revision and manifest corruption rejected",
    "pass": true,
    "detail": "stale and corrupt manifest blocked"
  },
  {
    "name": "native write failure rolls back chain node/head",
    "pass": true,
    "detail": "chain node/head rollback confirmed"
  },
  {
    "name": "invalid command repaired once without upstream mutation",
    "pass": true,
    "detail": {
      "executed": [
        "COMPOSE"
      ],
      "command_repairs": 1
    }
  },
  {
    "name": "explicit values normalize irrelevant restore metadata",
    "pass": true,
    "detail": "explicit value, rather than irrelevant original metadata, is authoritative"
  },
  {
    "name": "scope verifier anchoring cannot bypass literal text proof",
    "pass": true,
    "detail": "wrong term mapping and invented quote both rejected mechanically"
  },
  {
    "name": "actual-text quote recovery and typed emergency aliases",
    "pass": true,
    "detail": "exact existing substring recovered; typed null/false/true retained"
  },
  {
    "name": "fact confirmation and exception confirmation are separate",
    "pass": true,
    "detail": "fact confirmation did not become an exception judgment"
  },
  {
    "name": "normalization cannot hide scope or exception contradictions",
    "pass": true,
    "detail": "quote normalization cannot repair a wrong scope value or hide explicit exception contradiction"
  },
  {
    "name": "correction ordinal is separate from utterance turn",
    "pass": true,
    "detail": "second correction is turn 3, with its exact before/after conditions"
  },
  {
    "name": "fresh repair is unanchored and fact/source grounded",
    "pass": true,
    "detail": "one fresh rewrite received exact mandatory source and fact constraints"
  },
  {
    "name": "unknown exception need remains unknown",
    "pass": true,
    "detail": "an unknown need is not automatically a positive need"
  },
  {
    "name": "current-turn provenance error receives bounded repair",
    "pass": true,
    "detail": "unavailable current-turn reference repaired once before state admission"
  },
  {
    "name": "provenance repair budget cannot bypass admission",
    "pass": true,
    "detail": "two invalid proposals do not mutate state or consume a fake origin"
  },
  {
    "name": "uninitialized inspection and mapping are null safe",
    "pass": true,
    "detail": "no-goal inspection/mapping returns explicit pending, without state/link writes"
  },
  {
    "name": "uninitialized reuse does not consume a route",
    "pass": true,
    "detail": "missing goal cannot consume an invented route"
  },
  {
    "name": "wrong-link fixture requires initialized goal",
    "pass": true,
    "detail": "test fixture prerequisite fails explicitly before writes, not TypeError"
  }
]
```

실제 이전 문장 calibration의 원문 hash 확인:
```json
{
  "path": "04_EXPERIMENTS/ADR/ADR-0599-rag-chain-provenance-repair-admission/artifacts/run-001/calibration-result.json",
  "sha256": "a230df4d1b0387239e7082141aa0a08bb2540dc72d96d273f4a41bd17fbafbbb",
  "passed": 17,
  "total": 17,
  "false_pass": 0,
  "false_fail": 0,
  "text_functions_unchanged": true,
  "semantic_prompts_unchanged": true,
  "fresh_run": false
}
```


## 아직 확인하지 못한 범위

자연어로 어느 질문/묶음인지 찾는 정확도(goal_anchor는 시험 입력에서 지정), 변경된 원문 세대와 과거 경로의 결속, 임의 법률 세부 주장·수치·인용의 근거 검증, 17턴보다 더 긴 모델 대화, 여러 세션의 동시 변경/분산 트랜잭션, 온톨로지 적재와 위키 의미 검색, GENOS 현장 품질은 미확인이다.

전체 기능이 해결됐다고 판단할 근거가 부족하다. 확인된 코드 결함은 수정했으며, 별도 실제 모델 통합 검증과 생산 연결이 남았다. 제공자는 같은 Qwen3.8/Parasail FP8/reasoning none을 유지했고 fallback을 사용하지 않았다.

## 검토 파일

[수정 코드](../../../02_BACKEND/lawrag/research/candidates/adr_0601/safe-state-chain/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/chain_prototype.py) · [상태 계약 원문](../../../04_EXPERIMENTS/ADR/ADR-0601-rag-chain-empty-state-guards/artifacts/run-001/result.json) · [문장 검사 원문](../../../04_EXPERIMENTS/ADR/ADR-0599-rag-chain-provenance-repair-admission/artifacts/run-001/calibration-result.json) · [실제 모델 중단 기록](ADR-0600_RAG_CHAIN_STRICT_REPAIR_20261001.md)

MAIN 포인터·원문·두 SQL draft·완료 부모의 코드/실험/원 결과는 보존했다. SQL draft가 이 프로토의 production DB 구현으로 바뀌었다는 뜻이 아니다. 최신 standalone ADR final validation과 전체 graph 상태는 각 artifacts receipt로 별도 기록한다.

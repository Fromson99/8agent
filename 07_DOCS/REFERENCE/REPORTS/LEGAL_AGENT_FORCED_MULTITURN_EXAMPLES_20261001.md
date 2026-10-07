# 실제 모델 강제 멀티턴 예시 — ADR-0610

22턴 입력을 사전에 고정하고 실제 Qwen3.8(27B), Parasail FP8, reasoning none, fallback 없음으로 실행했다. 원문은 **모의승인규정**이다. 실제 법률 해석 결과가 아니다.
현재 실행 대상은 완료된 ADR-0609 프로토의 동일한 코드다. 새로 설계한 domain-control-v1의 등록된 개념·방법·경로와 사전/사후 검증은 구현하지 않았다. 이 문서의 모델 답변은 실제 응답이며, 설계 예시로 만든 답변이 아니다.
사전 체크포인트 **94/113**, 해당 턴의 모든 체크를 통과한 턴 **13/22**. 이는 상태·목표·복원·실행 범위·표·설명 여부를 함께 보는 기능 판정이며 법률 정확도 비율이 아니다. 실제 모델 성공 호출 125회, 성공 호출 보고 비용 $0.078589.
모의 원문: 제1조 “국내 대상의 승인 절차는 A이다. 해외 대상의 승인 절차는 B이다.” / 제2조 “긴급 사건은 별도 예외를 확인해야 한다.” 제2조에는 구체적 예외 절차가 없다.
## 관찰된 실패의 원인

이 절은 원점수를 바꾸지 않는 사후 진단이다. 기능 체크 통과와 설명 내용의 정확성을 구분한다.

| 원인 | 실제로 드러난 동작 | 필요한 통제 |

|---|---|---|
| 명령 종류와 변경 내용의 일관성을 코드로 검사하지 않는다. LLM의 `reason`은 표현 요청이라고 설명하면서 `action=CORRECT`를 출력할 수 있다. 검사 LLM도 이를 승인했다. | mixed-corrections 7의 표 요청과 9의 이력 설명 요청이 모두 `CORRECT/COMPOSE`가 됐다. | 상태 차이·요청 종류·허용 방법을 함께 검증하고, 표현·이력 조회 방법에는 지식 무효화 권한을 주지 않아야 한다. |
| 지식 폐기를 실제 사실·판단의 변경이 아니라 `action!='PRESENT'`라는 명령 이름에 연결했다. | 8턴에서 저장한 국내 경험이 9턴의 설명 요청 직후 `ACTIVE→RETIRED`가 됐다. 10~13턴에서 재사용·정정·저장이 연쇄적으로 막혔다. | 사실·근거·적용 판단이 달라졌는지로 무효화 범위를 계산하고, 표현 변경에는 확인된 판단 묶음을 유지해야 한다. |
| 설명을 생성하는 COMPOSE와 그 검사기에 정정 이벤트가 전달되지 않는다. | 9턴 실제 답변은 “별도의 정정 과정 없이 원문 근거를 직접 인용하여 판단을 내렸습니다.”였다. 앞서 3~6턴에는 실제 정정 이벤트가 네 개 있다. | 이력 설명은 실제 사건/정정 ID를 조회하는 별도 방법으로 실행하고, 설명 문장이 그 ID·원문에 연결되는지 검증해야 한다. |
| 재실행 범위를 LLM이 고른 `stage`와 필드별 최소 단계의 최솟값으로 정한다. 불필요하게 앞단으로 돌아가는 선택은 막지 않는다. | 3~6턴은 대상 조건의 수정·복원인데 네 번 모두 INTENT부터 일곱 단계를 재실행했다. 명령 검사도 통과했다. | 변경 필드와 적용 관계 의존성으로 필요한 단계를 계산하고, 추가 탐색을 택할 때는 등록된 도메인 사유와 근거가 필요하다. |
| 개념과 선택 이유는 자유 문자열이며 등록된 도메인 경로에 묶여 있지 않다. | 실제 명령에는 `reason`이 있지만 `purpose_id/method_id/path_template_id`가 없다. 저장되는 CONCEPT는 모델이 만든 label, JUDGMENT는 일곱 단계 payload다. | 승인된 개념·관계·방법·경로 중에서 선택하고, 탐색 목적과 원문 확인 후의 적용 판단을 별도로 검증해야 한다. |

특히 두 번째 원인은 DB의 체인 연결 자체가 끊어진 문제가 아니다. **설명 요청을 정정으로 오분류한 결과가 ‘지식 폐기’ 권한까지 행사한 문제**다. 최초 이벤트와 정정 이력은 DB에 남아 있지만 재사용 목록에서 최종 경험이 빠진다.

또한 9턴의 자동 체크는 `answer.text`가 비어 있지 않으면 설명 기능을 통과시킨다. 이 검사만으로는 “정정 과정이 없었다”는 잘못된 설명을 잡지 못한다. 원점수는 그대로 보존하며, 설명의 내용 오류는 이 진단에 별도로 적었다.

이 실행은 domain-control-v1 설계의 효과를 비교한 실험이 아니다. 현재 프로토의 상태 복원은 실제로 동작했지만, **각 판단이 온톨로지에서 허용한 도메인 경로를 따르는 상태는 아직 아니다.** 이 차이를 새 구현에서 검증해야 한다.

판정 기준에도 한 가지 문제가 있었다. stage-reentry 2턴은 새로 긴급 조건을 추가하며 예외까지 검토하도록 요청했다. 모델은 긴급 예외 검색어를 추가했고 시스템은 PLAN부터 다시 실행했다. 새 조건에 맞는 근거를 확보하는 동작이므로 **ASSESS부터만 실행해야 한다는 사전 기대가 지나치게 좁았다.** 이 체크 실패는 `judge_or_gold_error`로 진단한다. 원점수는 고치지 않는다. 특히 이를 “모든 조건 수정은 검색을 다시 하면 안 된다”는 구현 규칙으로 만들면 안 된다.

미충족 체크 19개는 독립적인 원인 19개를 뜻하지 않는다. 네 번의 불필요한 전체 재실행에서 4개, 9턴의 경험 폐기 후 10~13턴이 막히면서 14개, 긴급 조건에 대한 과도한 사전 기준에서 1개가 발생했다. 잘못된 설명 내용은 자동 점수에 잡히지 않은 추가 진단이다. 수정 대상 체크의 4개 미충족도 다른 질문을 수정한 결과가 아니라, 후속 요청이 막혀 목표 자체가 생성되지 않은 결과다.

구현 근거: [명령 검사와 복원](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0610/forced-turn-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py:156), [재실행 시작점](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0610/forced-turn-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py:241), [경험 폐기 분기](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0610/forced-turn-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py:271), [설명 단계의 실제 입력](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0610/forced-turn-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/memory_rag.py:121).

## 기능별 사전 판정

| 검사 | 통과/전체 |
|---|---:|
| 응답 상태 | 18/22 |
| 절차 A/B 문구 | 10/13 |
| 수정 대상 질문 | 18/22 |
| 미확인 답변의 지식 발행 차단 | 7/7 |
| 현재 상태와 활성 루트 일치 | 22/22 |
| 지정 재실행 범위 | 6/14 |
| 다른 질문 보존 | 5/5 |
| 과거 조건의 정확한 복원 | 4/4 |
| 표 형식 | 2/2 |
| 설명 응답 존재 여부(내용 정확성 제외) | 2/2 |

## 전체 대화 한눈에 보기

조건부 READY 상태만으로 정답을 판정하지 않았다. 실제 답변·실행 단계·상태 체크를 아래에 함께 남긴다.
| 사례·턴 | 사용자 입력 원문 | 실제 상태 | 다시 실행한 단계 |
|---|---|---|---|
| mixed-corrections/1 (M1) | 모의승인규정 제1조의 승인 절차를 알려줘. 대상은 국내야. | READY | INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| mixed-corrections/2 (M1) | 별도의 두 번째 질문이야. 모의승인규정 제1조에서 해외 대상의 승인 절차를 알려줘. | READY | INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| mixed-corrections/3 (M1) | 첫 번째 질문만 정정할게. 대상은 국내가 아니라 해외야. 두 번째 질문은 유지해. | READY | INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| mixed-corrections/4 (M1) | 첫 번째 질문의 첫 정정이 잘못됐어. 그 질문을 최초에 말했던 대상 조건으로 되돌려 판단해줘. | READY | INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| mixed-corrections/5 (M1) | 방금 한 두 번째 정정도 잘못됐어. 첫 번째 질문에서 첫 정정 직후의 대상 조건으로 다시 돌아가줘. | READY | INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| mixed-corrections/6 (M1) | 최종적으로 첫 번째 질문의 대상은 최초 질문 때 조건이 맞아. 정정들을 거슬러 최초 대상 조건으로 복원해줘. 두 번째 질문은 그대로야. | READY | INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| mixed-corrections/7 (M1) | 두 번째 질문의 조건과 결론은 그대로 두고 최종 답변만 표로 써줘. | READY | COMPOSE |
| mixed-corrections/8 (M1) | 첫 번째 질문은 지금 최종 답이 맞아. 이 질문의 최종 정답 루트를 저장해줘. | STORED | 실행 목록 없음 |
| mixed-corrections/9 (M1) | 첫 번째 질문에서 왜 그 결론이 됐는지, 어떤 정정을 거쳐 어떤 근거를 채택했는지 설명해줘. | READY | COMPOSE |
| mixed-corrections/10 (M2) | 모의승인규정 제1조 승인 절차를 알려줘. 대상은 국내야. 이전 대화에서 내가 최종 확인한 경험을 활용해줘. | CLARIFY | 실행 목록 없음 |
| mixed-corrections/11 (M2) | 방금 질문의 대상은 해외가 맞아. 국내로 들고 온 것은 잘못됐으니 해외로 다시 판단해줘. | CLARIFY | 실행 목록 없음 |
| mixed-corrections/12 (M2) | 지금 해외 대상의 최종 답이 맞아. 이 질문의 정답 루트를 저장해줘. | CLARIFY | 실행 목록 없음 |
| mixed-corrections/13 (M3) | 새 대화야. 모의승인규정 제1조 국내 대상의 승인 절차를 이전에 최종 확인한 경험으로 알려줘. | CLARIFY | 실행 목록 없음 |
| stage-reentry/1 (S1) | 모의승인규정 제1조의 국내 대상 승인 절차를 알려줘. | READY | INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| stage-reentry/2 (S1) | 그 질문에 조건을 추가해줘. 대상은 국내이고 긴급 사건이야. 긴급 사건의 예외까지 고려해 다시 판단해줘. | READY | PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| stage-reentry/3 (S1) | 현재 국내·긴급 사건 조건은 유지해. 검색계획을 고쳐서 검색어를 "승인 절차"와 "긴급 사건 별도 예외" 두 개로 바꾸고 원문을 찾아 다시 판단해줘. | READY | PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| stage-reentry/4 (S1) | 현재 검색 결과의 원문을 다시 읽는 단계부터 재검토해줘. 목적과 국내·긴급 조건, 검색계획은 유지해. | READY | READ → SELECT → ASSESS → COMPOSE |
| stage-reentry/5 (S1) | 현재 읽은 원문 중 근거를 선정하는 단계부터 다시 해줘. 목적과 국내·긴급 조건, 검색계획은 유지해. | READY | SELECT → ASSESS → COMPOSE |
| stage-reentry/6 (S1) | 긴급 조건을 추가한 정정이 잘못됐어. 첫 질문 최초의 대상 조건으로 돌아가고 긴급 조건은 제거해줘. 지금 검색계획은 유지해. | READY | ASSESS → COMPOSE |
| stage-reentry/7 (S1) | 이 질문을 최초부터 어떻게 고쳤고 현재 왜 이 결론인지 근거와 함께 설명해줘. | READY | COMPOSE |
| stage-reentry/8 (S1) | 현재 조건과 결론을 그대로 두고 최종 답변만 표로 써줘. | READY | COMPOSE |
| stage-reentry/9 (S1) | 이 질문은 지금 최종 답이 맞아. 최종 정답 루트를 저장해줘. | STORED | 실행 목록 없음 |

## 실패한 사전 체크 원문

```json
[
  {
    "case": "mixed-corrections",
    "turn": 3,
    "kind": "executed_stages",
    "expected": [
      "ASSESS",
      "COMPOSE"
    ],
    "observed": [
      "INTENT",
      "PLAN",
      "RECALL",
      "READ",
      "SELECT",
      "ASSESS",
      "COMPOSE"
    ],
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 4,
    "kind": "executed_stages",
    "expected": [
      "ASSESS",
      "COMPOSE"
    ],
    "observed": [
      "INTENT",
      "PLAN",
      "RECALL",
      "READ",
      "SELECT",
      "ASSESS",
      "COMPOSE"
    ],
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 5,
    "kind": "executed_stages",
    "expected": [
      "ASSESS",
      "COMPOSE"
    ],
    "observed": [
      "INTENT",
      "PLAN",
      "RECALL",
      "READ",
      "SELECT",
      "ASSESS",
      "COMPOSE"
    ],
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 6,
    "kind": "executed_stages",
    "expected": [
      "ASSESS",
      "COMPOSE"
    ],
    "observed": [
      "INTENT",
      "PLAN",
      "RECALL",
      "READ",
      "SELECT",
      "ASSESS",
      "COMPOSE"
    ],
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 10,
    "kind": "status",
    "expected": [
      "REUSED"
    ],
    "observed": "CLARIFY",
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 10,
    "kind": "procedure_token",
    "expected": "A",
    "observed": "",
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 10,
    "kind": "executed_stages",
    "expected": [
      "COMPOSE"
    ],
    "observed": null,
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 10,
    "kind": "target",
    "expected": [
      "M2",
      1
    ],
    "observed": null,
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 11,
    "kind": "status",
    "expected": [
      "READY"
    ],
    "observed": "CLARIFY",
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 11,
    "kind": "procedure_token",
    "expected": "B",
    "observed": "",
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 11,
    "kind": "executed_stages",
    "expected": [
      "ASSESS",
      "COMPOSE"
    ],
    "observed": null,
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 11,
    "kind": "target",
    "expected": [
      "M2",
      1
    ],
    "observed": null,
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 12,
    "kind": "status",
    "expected": [
      "STORED"
    ],
    "observed": "CLARIFY",
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 12,
    "kind": "target",
    "expected": [
      "M2",
      1
    ],
    "observed": null,
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 13,
    "kind": "status",
    "expected": [
      "REUSED"
    ],
    "observed": "CLARIFY",
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 13,
    "kind": "procedure_token",
    "expected": "A",
    "observed": "",
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 13,
    "kind": "executed_stages",
    "expected": [
      "COMPOSE"
    ],
    "observed": null,
    "pass": false
  },
  {
    "case": "mixed-corrections",
    "turn": 13,
    "kind": "target",
    "expected": [
      "M3",
      1
    ],
    "observed": null,
    "pass": false
  },
  {
    "case": "stage-reentry",
    "turn": 2,
    "kind": "executed_stages",
    "expected": [
      "ASSESS",
      "COMPOSE"
    ],
    "observed": [
      "PLAN",
      "RECALL",
      "READ",
      "SELECT",
      "ASSESS",
      "COMPOSE"
    ],
    "pass": false
  }
]
```

## 턴별 실제 답변과 수정 근거

### mixed-corrections / 1 — M1

사용자: 모의승인규정 제1조의 승인 절차를 알려줘. 대상은 국내야.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G5c76c94cd37d452293166c908341cdf6",
  "revision": 1,
  "executed": [
    "INTENT",
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "START",
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "국내"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 국내"
    ],
    "reason": "사용자가 모의승인규정 제1조의 승인 절차에 대해 국내를 대상으로 질문했습니다. 제공된 문서 목록에서 '모의승인규정'을 검색 대상으로 설정하고, 지역 조건을 facts에 기록하여 초기 검색을 시작합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": null,
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "state": {
    "task": "모의승인규정 제1조의 승인 절차 확인",
    "source_category": "ALL",
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "국내"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 국내"
    ]
  },
  "events_for_this_request": [
    1
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-01.json)

### mixed-corrections / 2 — M1

사용자: 별도의 두 번째 질문이야. 모의승인규정 제1조에서 해외 대상의 승인 절차를 알려줘.

실제 답변:

모의승인규정 제1조에 따르면, 해외 대상의 승인 절차는 B입니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G59182461b6e540df9cb0e9c943c45645",
  "revision": 1,
  "executed": [
    "INTENT",
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "START",
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "해외"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 해외"
    ],
    "reason": "사용자가 '별도의 두 번째 질문'이라고 명시하여 기존 질문과 무관한 새로운 질문으로 판단했습니다. 대상 지역이 '해외'로 변경되었으므로, 기존 질문의 '국내' 조건을 복사하지 않고 현재 발언에서 추출한 '해외' 조건을 facts에 기록하여 초기 검색을 시작합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": null,
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "state": {
    "task": "모의승인규정 제1조의 승인 절차 확인",
    "source_category": "ALL",
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "해외"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 해외"
    ]
  },
  "events_for_this_request": [
    2
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-02.json)

### mixed-corrections / 3 — M1

사용자: 첫 번째 질문만 정정할게. 대상은 국내가 아니라 해외야. 두 번째 질문은 유지해.

실제 답변:

해외 대상의 승인 절차는 B입니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G5c76c94cd37d452293166c908341cdf6",
  "revision": 2,
  "executed": [
    "INTENT",
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "지역",
        "value": "해외"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 해외"
    ],
    "reason": "사용자가 첫 번째 질문의 대상 지역을 '국내'에서 '해외'로 정정하고, 두 번째 질문은 유지하라고 지시했습니다. 따라서 첫 번째 질문(G5c76c94cd37d452293166c908341cdf6)을 대상으로 지역 조건을 '해외'로 변경하고, 검색 쿼리도 이에 맞게 '해외'로 갱신합니다. 두 번째 질문(G59182461b6e540df9cb0e9c943c45645)은 변경 사항이 없으므로 무시합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": "G5c76c94cd37d452293166c908341cdf6",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "해외"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 해외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "events_for_this_request": [
    3
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-03.json)

### mixed-corrections / 4 — M1

사용자: 첫 번째 질문의 첫 정정이 잘못됐어. 그 질문을 최초에 말했던 대상 조건으로 되돌려 판단해줘.

실제 답변:

국내 대상의 승인 절차는 A이다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G5c76c94cd37d452293166c908341cdf6",
  "revision": 3,
  "executed": [
    "INTENT",
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "지역",
        "value": "국내"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 국내"
    ],
    "reason": "사용자가 첫 번째 질문의 첫 번째 정정(지역을 '해외'로 변경한 것)이 잘못되었다고 지적하고, 최초에 말했던 대상 조건으로 되돌려 판단해달라고 요청했습니다. 기록을 확인하면 첫 번째 질문(G5c76c94cd37d452293166c908341cdf6)의 최초 상태(event id 1)에서 지역 조건은 '국내'였습니다. 따라서 현재 '해외'로 변경된 조건을 최초 상태의 '국내'로 복원해야 합니다. 이는 기록에서 원래 값을 복원하는 상황이므로 restore_event와 restore_fields를 지정합니다. 복원 대상은 facts와 queries입니다. task, document_ids, source_category는 변경 사항이 없으므로 null 또는 KEEP으로 처리합니다.",
    "restore_event": 1,
    "restore_fields": [
      "facts",
      "queries"
    ],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": "G5c76c94cd37d452293166c908341cdf6",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "국내"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 국내"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "events_for_this_request": [
    4
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-04.json)

### mixed-corrections / 5 — M1

사용자: 방금 한 두 번째 정정도 잘못됐어. 첫 번째 질문에서 첫 정정 직후의 대상 조건으로 다시 돌아가줘.

실제 답변:

해외 대상의 승인 절차는 B입니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G5c76c94cd37d452293166c908341cdf6",
  "revision": 4,
  "executed": [
    "INTENT",
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "지역",
        "value": "해외"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 해외"
    ],
    "reason": "사용자가 '방금 한 두 번째 정정도 잘못됐어'라고 하여, 직전 정정(두 번째 정정, event id 4)을 취소하고 그 이전 상태인 '첫 번째 질문에서 첫 정정 직후'의 조건으로 복원하라고 요청했습니다. 기록을 확인하면 첫 번째 질문(G5c76c94cd37d452293166c908341cdf6)의 첫 번째 정정(event id 3) 직후 상태는 지역이 '해외'였습니다. 따라서 현재 '국내'로 복원된 조건을 다시 '해외'로 복원해야 합니다. 이는 기록에서 원래 값을 복원하는 상황이므로 restore_event(3)와 restore_fields(facts, queries)를 지정합니다.",
    "restore_event": 3,
    "restore_fields": [
      "facts",
      "queries"
    ],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": "G5c76c94cd37d452293166c908341cdf6",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "해외"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 해외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "events_for_this_request": [
    5
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-05.json)

### mixed-corrections / 6 — M1

사용자: 최종적으로 첫 번째 질문의 대상은 최초 질문 때 조건이 맞아. 정정들을 거슬러 최초 대상 조건으로 복원해줘. 두 번째 질문은 그대로야.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G5c76c94cd37d452293166c908341cdf6",
  "revision": 5,
  "executed": [
    "INTENT",
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "지역",
        "value": "국내"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 국내"
    ],
    "reason": "사용자가 첫 번째 질문의 대상 조건을 '최초 질문 때 조건'으로 복원해달라고 요청했습니다. 기록을 확인하면 첫 번째 질문(G5c76c94cd37d452293166c908341cdf6)의 최초 상태(event id 1)에서 지역 조건은 '국내'였습니다. 현재 상태는 '해외'이므로, 기록에서 원래 값을 복원하는 상황이므로 restore_event(1)와 restore_fields(facts, queries)를 지정하여 최초 조건으로 되돌립니다. 두 번째 질문(G59182461b6e540df9cb0e9c943c45645)은 '그대로'라고 명시되어 있으므로 변경 사항이 없습니다.",
    "restore_event": 1,
    "restore_fields": [
      "facts",
      "queries"
    ],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": "G5c76c94cd37d452293166c908341cdf6",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "국내"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 국내"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "events_for_this_request": [
    6
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-06.json)

### mixed-corrections / 7 — M1

사용자: 두 번째 질문의 조건과 결론은 그대로 두고 최종 답변만 표로 써줘.

실제 답변:

| 항목 | 내용 |
| :--- | :--- |
| 지역 | 해외 |
| 승인 절차 | B |

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G59182461b6e540df9cb0e9c943c45645",
  "revision": 2,
  "executed": [
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": null,
    "format": "table",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 두 번째 질문(G59182461b6e540df9cb0e9c943c45645)의 조건과 결론은 유지하되, 최종 답변 형식만 표로 변경해달라고 요청했습니다. 이는 내용 변경이 아닌 표현 방식(PRESENT/COMPOSE)의 수정이므로, 해당 goal을 대상으로 format을 'table'로 변경하고 나머지 필드는 유지(null)합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "COMPOSE",
    "target": "G59182461b6e540df9cb0e9c943c45645",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "해외"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 해외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "events_for_this_request": [
    7
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-07.json)

### mixed-corrections / 8 — M1

사용자: 첫 번째 질문은 지금 최종 답이 맞아. 이 질문의 최종 정답 루트를 저장해줘.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "STORED",
  "goal_id": "G5c76c94cd37d452293166c908341cdf6",
  "revision": 5,
  "executed": null,
  "command": {
    "action": "FINALIZE",
    "document_ids": null,
    "facts": null,
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 첫 번째 질문(G5c76c94cd37d452293166c908341cdf6)의 현재 최종 답이 맞다고 확인하고, 해당 질문의 최종 정답 루트를 저장해달라고 명시적으로 지시했습니다. 이는 단순한 답변 생성이 아닌 저장 승인에 해당하므로 FINALIZE 명령을 발동합니다. 대상은 첫 번째 질문의 goal ID이며, 다른 필드는 변경 사항이 없으므로 null로 처리합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "COMPOSE",
    "target": "G5c76c94cd37d452293166c908341cdf6",
    "task": null
  },
  "state": null,
  "events_for_this_request": [],
  "active_knowledge_count": 1
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-08.json)

### mixed-corrections / 9 — M1

사용자: 첫 번째 질문에서 왜 그 결론이 됐는지, 어떤 정정을 거쳐 어떤 근거를 채택했는지 설명해줘.

실제 답변:

제시된 근거에 따르면, 국내 대상의 승인 절차는 A입니다. 이 결론은 '모의승인규정' 제1조 정의 조항에서 명시된 내용을 그대로 채택하여 도출되었습니다. 해당 조항은 국내와 해외 대상의 승인 절차를 구분하여 규정하고 있으며, 현재 사실에서 지역이 '국내'로 확인되었으므로 해당 조항의 국내 대상에 해당하는 부분인 'A'를 적용한 것입니다. 별도의 정정 과정 없이 원문 근거를 직접 인용하여 판단을 내렸습니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "G5c76c94cd37d452293166c908341cdf6",
  "revision": 6,
  "executed": [
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": null,
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 첫 번째 질문(G5c76c94cd37d452293166c908341cdf6)의 결론 도출 과정, 정정 이력, 채택된 근거를 설명해달라고 요청했습니다. 이는 기존 질문의 내용 변경이 아니라, 해당 질문의 처리 이력과 근거를 바탕으로 설명을 생성하는 표현 단계(COMPOSE)의 요청으로 판단됩니다. 따라서 해당 goal을 대상으로 format을 'prose'로 유지(또는 명시)하고, 나머지 조건 필드는 변경하지 않습니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "COMPOSE",
    "target": "G5c76c94cd37d452293166c908341cdf6",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "지역",
        "value": "국내"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "모의승인규정 제1조 승인 절차",
      "모의승인규정 제1조 국내"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조의 승인 절차 확인"
  },
  "events_for_this_request": [
    8
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-09.json)

### mixed-corrections / 10 — M2

사용자: 모의승인규정 제1조 승인 절차를 알려줘. 대상은 국내야. 이전 대화에서 내가 최종 확인한 경험을 활용해줘.

실제 답변:

**자연어 답변 없음.** 사용자가 이전 대화에서 최종 확인한 경험을 활용하라고 지시했으나, 제공된 knowledge 목록이 비어 있어 재사용할 수 있는 저장된 경험 ID가 없습니다. 따라서 경험을 선택할 수 없으므로 CLARIFY가 필요합니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "CLARIFY",
  "goal_id": null,
  "revision": null,
  "executed": null,
  "command": {
    "action": "CLARIFY",
    "document_ids": null,
    "facts": null,
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 이전 대화에서 최종 확인한 경험을 활용하라고 지시했으나, 제공된 knowledge 목록이 비어 있어 재사용할 수 있는 저장된 경험 ID가 없습니다. 따라서 경험을 선택할 수 없으므로 CLARIFY가 필요합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": null,
    "task": "모의승인규정 제1조 승인 절차 확인"
  },
  "state": null,
  "events_for_this_request": [],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-10.json)

### mixed-corrections / 11 — M2

사용자: 방금 질문의 대상은 해외가 맞아. 국내로 들고 온 것은 잘못됐으니 해외로 다시 판단해줘.

실제 답변:

**자연어 답변 없음.** knowledge required

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "CLARIFY",
  "goal_id": null,
  "revision": null,
  "executed": null,
  "command": {
    "action": "REUSE",
    "document_ids": null,
    "facts": null,
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 '방금 질문'의 대상이 해외임을 확인하고, 국내로 잘못 판단된 부분을 해외 기준으로 다시 판단해달라고 명확히 지시했습니다. 이는 기존 진행 중이던 질문(목표)에 대한 조건 정정 및 재판단 요청입니다. 제공된 goals 목록이 비어 있어 ID를 직접 참조할 수는 없으나, 대화 맥상에서 '방금 질문'이 유일한 수정 대상이므로 해당 목표를 재사용(REUSE)하여 ASSESS 단계에서 해외 기준으로 재분석하도록 처리합니다. repair_feedback에서 지적한 CLARIFY 오류를 피하기 위해, 명확한 재판단 지시에 따라 실행 단계를 설정합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "ASSESS",
    "target": null,
    "task": null
  },
  "state": null,
  "events_for_this_request": [],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-11.json)

### mixed-corrections / 12 — M2

사용자: 지금 해외 대상의 최종 답이 맞아. 이 질문의 정답 루트를 저장해줘.

실제 답변:

**자연어 답변 없음.** 사용자가 '정답 루트를 저장해줘'라고 명시적으로 최종 확인 및 저장 요청을 했음에도, 제안된 명령의 action이 'CLARIFY'로 지정되어 있어 저장(FINALIZE) 의도와 일치하지 않습니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "CLARIFY",
  "goal_id": null,
  "revision": null,
  "executed": null,
  "command": {
    "action": "CLARIFY",
    "document_ids": null,
    "facts": null,
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 '이 질문의 정답 루트를 저장해줘'라고 지시했으나, 제공된 goals 목록이 비어 있어 저장 대상이 되는 특정 질문(목표)을 식별할 수 있는 ID가 없습니다. repair_feedback에서도 'target not offered'라고 명시되어 있으므로, 저장할 대상 질문을 명확히 지정할 수 없어 확인이 필요합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "COMPOSE",
    "target": null,
    "task": null
  },
  "state": null,
  "events_for_this_request": [],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-12.json)

### mixed-corrections / 13 — M3

사용자: 새 대화야. 모의승인규정 제1조 국내 대상의 승인 절차를 이전에 최종 확인한 경험으로 알려줘.

실제 답변:

**자연어 답변 없음.** 사용자가 이전에 최종 확인한 경험을 재사용(REUSE)하도록 요청했으나, 현재 제공된 knowledge 목록이 비어 있어 참조할 수 있는 저장된 경험(knowledge_id)이 없습니다. 새 세션에서 경험을 가져오려면 해당 경험이 시스템에 존재해야 하므로, 현재 상태에서는 대상 경험을 결정할 수 없습니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "CLARIFY",
  "goal_id": null,
  "revision": null,
  "executed": null,
  "command": {
    "action": "CLARIFY",
    "document_ids": null,
    "facts": null,
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 이전에 최종 확인한 경험을 재사용(REUSE)하도록 요청했으나, 현재 제공된 knowledge 목록이 비어 있어 참조할 수 있는 저장된 경험(knowledge_id)이 없습니다. 새 세션에서 경험을 가져오려면 해당 경험이 시스템에 존재해야 하므로, 현재 상태에서는 대상 경험을 결정할 수 없습니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": null,
    "task": null
  },
  "state": null,
  "events_for_this_request": [],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/mixed-corrections/turn-13.json)

### stage-reentry / 1 — S1

사용자: 모의승인규정 제1조의 국내 대상 승인 절차를 알려줘.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다. 다만, 제2조에서 언급된 '긴급 사건'에 대한 별도 예외 조항의 구체적인 내용이나 적용 범원은 제공된 원문에 포함되어 있지 않아 확인이 불가합니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 1,
  "executed": [
    "INTENT",
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "START",
    "document_ids": [
      "d"
    ],
    "facts": [],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "국내 대상 승인 절차"
    ],
    "reason": "사용자가 모의승인규정 제1조의 국내 대상 승인 절차에 대해 새로운 질문을 하였습니다. 기존 목표가 없으므로 새 질문으로 시작하며, 제공된 문서 '모의승인규정'을 검색 범위로 설정하고 해당 조항과 절차에 대한 정보를 찾기 위해 INTENT 단계로 진입합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "INTENT",
    "target": null,
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "state": {
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인",
    "source_category": "ALL",
    "document_ids": [
      "d"
    ],
    "facts": [],
    "queries": [
      "모의승인규정 제1조",
      "국내 대상 승인 절차"
    ]
  },
  "events_for_this_request": [
    9
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-01.json)

### stage-reentry / 2 — S1

사용자: 그 질문에 조건을 추가해줘. 대상은 국내이고 긴급 사건이야. 긴급 사건의 예외까지 고려해 다시 판단해줘.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다. 다만, 긴급 사건에 대해서는 제2조에서 '별도 예외를 확인해야 한다'고 규정하고 있습니다. 제공된 원문에는 긴급 사건에 대한 구체적인 예외 절차나 적용 범위에 대한 명시적 조항이 포함되어 있지 않아, 긴급 사건에 대한 최종 승인 절차(A 유지 또는 변경 여부)를 확정할 수 없습니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 2,
  "executed": [
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "모의승인규정 제1조",
      "국내 대상 승인 절차",
      "긴급 사건 예외"
    ],
    "reason": "사용자가 기존 질문에 '국내'와 '긴급 사건'이라는 조건을 추가하고, 긴급 사건의 예외까지 고려하여 다시 판단해 달라고 요청했습니다. 이는 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)에 대한 정정(CORRECT)에 해당합니다. 새로운 조건들을 facts에 기록하고, 긴급 사건 예외에 대한 검색을 위해 queries를 확장하며, 기존 문서 범위와 소스 범주는 유지합니다. 조건이 추가되었으므로 판단(ASSESS) 단계를 다시 수행해야 합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "ASSESS",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "queries": [
      "모의승인규정 제1조",
      "국내 대상 승인 절차",
      "긴급 사건 예외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "events_for_this_request": [
    10
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-02.json)

### stage-reentry / 3 — S1

사용자: 현재 국내·긴급 사건 조건은 유지해. 검색계획을 고쳐서 검색어를 "승인 절차"와 "긴급 사건 별도 예외" 두 개로 바꾸고 원문을 찾아 다시 판단해줘.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다. 다만, 긴급 사건에 대해서는 제2조에서 '별도 예외를 확인해야 한다'고 규정하고 있어, 제1조의 일반적 절차(A)가 그대로 적용되는지 여부는 제공된 원문만으로는 확정할 수 없습니다. 따라서 긴급 사건에 대한 구체적인 예외 절차나 적용 범위에 대한 명시적 조항이 부재하여, 해당 사건의 최종 승인 절차는 추가 확인이 필요합니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 3,
  "executed": [
    "PLAN",
    "RECALL",
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": [
      "승인 절차",
      "긴급 사건 별도 예외"
    ],
    "reason": "사용자가 기존 질문의 조건(국내, 긴급 사건)은 유지하되, 검색 계획을 수정하여 검색어를 '승인 절차'와 '긴급 사건 별도 예외'로 변경하고 원문을 다시 찾아 판단해 달라고 요청했습니다. 이는 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)에 대한 정정(CORRECT)에 해당합니다. facts는 기존 조건을 유지하고, queries는 사용자가 지정한 두 개의 검색어로 교체합니다. 검색 계획 변경 및 재검색을 위해 PLAN 단계로 진입합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "PLAN",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "queries": [
      "승인 절차",
      "긴급 사건 별도 예외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "events_for_this_request": [
    11
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-03.json)

### stage-reentry / 4 — S1

사용자: 현재 검색 결과의 원문을 다시 읽는 단계부터 재검토해줘. 목적과 국내·긴급 조건, 검색계획은 유지해.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다. 다만, 긴급 사건에 대해서는 제2조에서 '별도 예외를 확인해야 한다'고 명시되어 있어, 제1조의 일반적 절차(A)가 그대로 적용되는지 여부는 제공된 원문만으로는 확정할 수 없습니다. 따라서 긴급 사건의 구체적인 예외 절차나 적용 범위에 대한 명시적 조항이 부재한 한계 내에서, 국내 대상의 기본 절차는 A이며 긴급 사건의 예외 여부는 추가 확인이 필요합니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 4,
  "executed": [
    "READ",
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 기존 질문의 목적과 조건(국내, 긴급 사건) 및 검색 계획은 유지하되, 현재 검색 결과의 원문을 다시 읽는 단계(READ)부터 재검토해 달라고 요청했습니다. 이는 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)에 대한 정정(CORRECT)에 해당하며, 변경 사항이 없으므로 관련 필드들은 null로 처리하고 READ 단계로 진입합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "READ",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "queries": [
      "승인 절차",
      "긴급 사건 별도 예외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "events_for_this_request": [
    12
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-04.json)

### stage-reentry / 5 — S1

사용자: 현재 읽은 원문 중 근거를 선정하는 단계부터 다시 해줘. 목적과 국내·긴급 조건, 검색계획은 유지해.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다. 다만, 긴급 사건에 대해서는 제2조에서 '별도 예외를 확인해야 한다'고 규정하고 있어, 제1조의 일반 절차(A)가 그대로 적용되는지 여부는 제공된 원문만으로는 확정할 수 없습니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 5,
  "executed": [
    "SELECT",
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 기존 질문의 목적과 조건(국내, 긴급 사건) 및 검색 계획은 유지하되, 현재 읽은 원문 중 근거를 선정하는 단계(SELECT)부터 다시 수행해 달라고 요청했습니다. 이는 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)에 대한 정정(CORRECT)에 해당하며, 변경 사항이 없으므로 관련 필드들은 null로 처리하고 SELECT 단계로 진입합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "SELECT",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      },
      {
        "name": "사건 유형",
        "value": "긴급 사건"
      },
      {
        "name": "고려 사항",
        "value": "긴급 사건의 예외"
      }
    ],
    "queries": [
      "승인 절차",
      "긴급 사건 별도 예외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "events_for_this_request": [
    13
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-05.json)

### stage-reentry / 6 — S1

사용자: 긴급 조건을 추가한 정정이 잘못됐어. 첫 질문 최초의 대상 조건으로 돌아가고 긴급 조건은 제거해줘. 지금 검색계획은 유지해.

실제 답변:

모의승인규정 제1조에 따르면, 국내 대상의 승인 절차는 A입니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 6,
  "executed": [
    "ASSESS",
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": [
      {
        "name": "대상",
        "value": "국내"
      }
    ],
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 긴급 조건을 추가한 정정이 잘못되었다며, 첫 질문의 최초 대상 조건(국내)으로 돌아가고 긴급 조건을 제거해 달라고 요청했습니다. 이는 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)에 대한 정정(CORRECT)에 해당합니다. 기록(event id 9)에서 최초 상태의 facts를 확인하여 '대상: 국내'만 유지하고, 이후 추가된 '사건 유형: 긴급 사건'과 '고려 사항: 긴급 사건의 예외'를 제거합니다. 검색 계획(queries)은 유지하라고 했으므로 null로 처리하며, 조건 변경에 따라 판단(ASSESS) 단계를 다시 수행해야 합니다.",
    "restore_event": 9,
    "restore_fields": [
      "facts"
    ],
    "source_category": "KEEP",
    "stage": "ASSESS",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [],
    "queries": [
      "승인 절차",
      "긴급 사건 별도 예외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "events_for_this_request": [
    14
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-06.json)

### stage-reentry / 7 — S1

사용자: 이 질문을 최초부터 어떻게 고쳤고 현재 왜 이 결론인지 근거와 함께 설명해줘.

실제 답변:

모의승인규정 제1조에 따른 국내 대상 승인 절차는 A입니다. 해당 조항은 국내 대상과 해외 대상의 승인 절차를 각각 A와 B로 명시하고 있으며, 이는 제공된 근거 문서의 제1조 정의 부분에서 확인됩니다. 따라서 질문에서 요구한 국내 대상 승인 절차는 A로 확정됩니다.

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 7,
  "executed": [
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": null,
    "format": "prose",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 질문의 수정 이력과 현재 결론의 근거를 설명해 달라고 요청했습니다. 이는 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)에 대한 새로운 표현/설명 요청으로, 기존 상태(조건, 검색 계획 등)는 유지하면서 COMPOSE 단계에서 답변을 생성해야 합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "COMPOSE",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [],
    "queries": [
      "승인 절차",
      "긴급 사건 별도 예외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "events_for_this_request": [
    15
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-07.json)

### stage-reentry / 8 — S1

사용자: 현재 조건과 결론을 그대로 두고 최종 답변만 표로 써줘.

실제 답변:

| 항목 | 내용 |
| :--- | :--- |
| **근거 조항** | 모의승인규정 제1조 |
| **국내 대상 승인 절차** | A |
| **해외 대상 승인 절차** | B |
| **원문 인용** | "국내 대상의 승인 절차는 A이다. 해외 대상의 승인 절차는 B이다." |

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "READY",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 8,
  "executed": [
    "COMPOSE"
  ],
  "command": {
    "action": "CORRECT",
    "document_ids": null,
    "facts": null,
    "format": "table",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 현재 조건과 결론을 유지한 채 최종 답변의 형식만 표로 변경해 달라고 요청했습니다. 이는 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)에 대한 표현 방식(PRESENT/COMPOSE)의 정정(CORRECT)에 해당합니다. 따라서 task, document_ids, facts, queries, source_category는 변경하지 않고(KEEP/null) format만 'table'로 설정하며 COMPOSE 단계로 진입합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "COMPOSE",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": {
    "document_ids": [
      "d"
    ],
    "facts": [],
    "queries": [
      "승인 절차",
      "긴급 사건 별도 예외"
    ],
    "source_category": "ALL",
    "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
  },
  "events_for_this_request": [
    16
  ],
  "active_knowledge_count": 0
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-08.json)

### stage-reentry / 9 — S1

사용자: 이 질문은 지금 최종 답이 맞아. 최종 정답 루트를 저장해줘.

실제 답변:

| 항목 | 내용 |
| :--- | :--- |
| **근거 조항** | 모의승인규정 제1조 |
| **국내 대상 승인 절차** | A |
| **해외 대상 승인 절차** | B |
| **원문 인용** | "국내 대상의 승인 절차는 A이다. 해외 대상의 승인 절차는 B이다." |

실제 명령·상태(명령이 거부된 경우 최종 제안도 함께 보존):
```json
{
  "status": "STORED",
  "goal_id": "Gcd68276e87ca4f56a3050d3728c7c8a2",
  "revision": 8,
  "executed": null,
  "command": {
    "action": "FINALIZE",
    "document_ids": null,
    "facts": null,
    "format": "table",
    "knowledge_id": null,
    "queries": null,
    "reason": "사용자가 현재 질문에 대한 최종 답이 맞다고 확인하고 최종 정답 루트를 저장해 달라고 명시적으로 요청했습니다. 이는 저장 승인(FINALIZE)에 해당하며, 기존 목표(Gcd68276e87ca4f56a3050d3728c7c8a2)의 상태와 조건은 유지합니다.",
    "restore_event": null,
    "restore_fields": [],
    "source_category": "KEEP",
    "stage": "COMPOSE",
    "target": "Gcd68276e87ca4f56a3050d3728c7c8a2",
    "task": null
  },
  "state": null,
  "events_for_this_request": [],
  "active_knowledge_count": 1
}
```
[실제 입력·응답·DB 상태 전체](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/stage-reentry/turn-09.json)

## 저장과 과거 기록의 처리

작업용 session/event/node와 재사용할 knowledge/ontology를 구분한다. 모든 발언은 작업 이력을 이어가기 위해 남을 수 있지만, 확인되지 않은 답변은 지식 묶음으로 발행하지 않는다. 틀린 루트는 ACTIVE에서 제외하고 감사 이력으로 보존한다.
```json
{
  "knowledge": [
    {
      "id": "Ke4a3f84d7c7c8a7ca0dc417c",
      "bundle": "G5c76c94cd37d452293166c908341cdf6",
      "revision": 5,
      "status": "RETIRED",
      "state": {
        "document_ids": [
          "d"
        ],
        "facts": [
          {
            "name": "지역",
            "value": "국내"
          }
        ],
        "queries": [
          "모의승인규정 제1조",
          "모의승인규정 제1조 승인 절차",
          "모의승인규정 제1조 국내"
        ],
        "source_category": "ALL",
        "task": "모의승인규정 제1조의 승인 절차 확인"
      }
    },
    {
      "id": "K839969934befe35f629bd78e",
      "bundle": "Gcd68276e87ca4f56a3050d3728c7c8a2",
      "revision": 8,
      "status": "ACTIVE",
      "state": {
        "document_ids": [
          "d"
        ],
        "facts": [],
        "queries": [
          "승인 절차",
          "긴급 사건 별도 예외"
        ],
        "source_category": "ALL",
        "task": "모의승인규정 제1조에 따른 국내 대상 승인 절차 확인"
      }
    }
  ],
  "routes": {
    "ACTIVE": 3,
    "RETIRED": 13
  },
  "ontology_node_count": 29,
  "ontology_edge_count": 41
}
```
## 재현·원시 근거

[실험 결정문](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/README.md) · [계보·모델·동결 계약](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/실험/manifest.json) · [원점수와 전체 결과](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/result.json) · [실제 실험 DB](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/run-001/memory.sqlite)
운영 MAIN·GENOS에 적용한 결과가 아니다. 단일 모의 원문, 사전에 강제로 정한 사용자 턴, 한 번 실행한 탐색 실험이다. 긴 실제 업무 대화의 일반 성능은 이 결과로 확정할 수 없다.

참고: 사전 명세의 temperature 설명은 provider default였으나, 동결된 공통 호출기와 실제 125개 요청은 모두 temperature=0을 사용했다. 모델·제공자 변경이나 fallback은 없었다.

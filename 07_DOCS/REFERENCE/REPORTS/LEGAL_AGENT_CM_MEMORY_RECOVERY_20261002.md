# 실제 CM 데이터 멀티턴 수정·재실험 — ADR-0612

실제 저장 CM 질문 **cm-038(대표자의 내부회계 보고 위임), cm-003(신규상장 의무보유)**에서 시작해 각각 12턴·7턴을 진행했다. 수정 전후 같은 19턴씩 총38턴이며, 정정용 후속 발언은 실험을 위해 작성했다. 모의 A/B 규정을 쓰지 않았다. 저장된 공개 원문145문서 범위를 허용하고 실제 검색·원문 읽기를 거쳤다. CM 전체61문항 전수평가는 아니다.

제품·중간 처리와 분리된 사후 평가는 qwen/qwen3.8-27b, Parasail FP8, reasoning none, temperature0, fallback 없음이다. 골든 답은 제품 입력에 제공하지 않았다. 법률 결과는 저장 CM 기준답과의 일치 평가이며 현행 법률 자문 인증은 아니다.

## 수정한 범위

수정 전은 ADR0611 GUARDED 동결본이다. 출력·범위·판단 복구가 이번 변경이고, 아래 방법 통제·이력·경험 보존은 그 부모에서 상속했다.

| 변경 | 동작 |
|---|---|
| 유한한 출력·복구 | 검색어 최대4개와 필드 길이 한도를 둔다. 잘린 응답·JSON 형식 오류는 같은 입력으로 한 번만 복구하고 재실패하면 중단한다. |
| 접근 범위와 검색 초점 | 질문에 법령명이 등장해도 허용 문서를 그 법령으로 축소하지 않는다. 명시적 문서 제한만 EXPLICIT로 처리하고, 기본 AUTHORIZED 범위에서 기존 참조 탐색을 사용한다. |
| 판단 복구 | 원문 인용·의미 검사에서 거부되면 실패한 판단과 이유를 전달해 ASSESS를 한 번 다시 수행한다. 재검사를 통과해야 답변 단계로 간다. |
| 상속한 허용 방법 선택 | 모델은 CASE_START, FACT_UPDATE, STATE_RESTORE, HISTORY_EXPLAIN, ANSWER_PRESENT 등 등록된 메모리 작업 방법을 선택한다. 서버가 해당 방법의 동작과 시작 단계를 정한다. |
| 설명·표의 권한 | 이력 조회와 표현 방법은 사실·목적·검색 계획을 몰래 바꾸지 못한다. 잘못된 필드를 제출하면 거부하고 제한된 재수정을 요청한다. |
| 경험 폐기 | 명령 이름만 보고 폐기하던 분기를 제거했다. 실제 상태가 바뀌거나 판단을 다시 검토하는 경우에 이전 경험을 무효화한다. 표현만 바꾸면 확인된 경험을 보존한다. |
| 이력 근거 | 이력 설명은 DB의 실제 이벤트·이전/이후 조건·복원 대상 ID로 출력한다. 모델이 과거 경위를 만들어 쓰는 경로를 없앴다. 일반 최종 답변·표는 계속 LLM이 작성한다. |
| 보조 검사 | 일반 답변 작성과 검사에도 실제 정정 이력을 전달해, 존재하는 정정을 부정하는 설명을 점검하도록 했다. |

**구현 범위는 메모리 작업의 방법·권한 통제다. 법률 개념·관계·적용 경로 전체를 승인된 온톨로지로 강제하는 기능은 아직 아니다.** 현재 원문 선택 이유와 법률 개념명에는 자유 문장이 남는다.

수정 구현의 모델 없는 상태·권한 계약 검사: **43/43**. 제품 MAIN·GENOS에 활성화하지 않은 격리 후보에서 검증했다.

## 실제 모델 결과

정상 응답은 내용의 정답 여부와 별개다. READY는 답변을 생성했다는 상태이며, 법률 기준답 일치는 아래 별도 행에서 본다.

| 항목 | 수정 전 BASELINE | 수정 후 RECOVERED |
|---|---:|---:|
| 정상 응답 턴 | 5/19 | 3/19 |
| 상태·권한 체크 | 12/33 | 5/33 |
| CM 기준답 일치 | 0/12 | 3/12 |
| 정정 이력 설명 정확성 | 1/2 | 0/2 |

이력 설명은 실제 이전 상태·정정·복원 과정을 모두 설명하는지 별도 사후 평가했다. 상태 점수와 법률 답변 점수는 합산하지 않는다. 한 가지 원인으로 여러 후속 턴이 막히면 체크 실패가 여러 번 집계된다.

```json
{
  "legal": {
    "guarded_only": 3,
    "baseline_only": 0,
    "both_correct": 0,
    "both_wrong": 9
  },
  "history": {
    "guarded_only": 0,
    "baseline_only": 1,
    "both_correct": 0,
    "both_wrong": 1
  }
}
```

## 턴별 비교

### cm-038-chain

| 턴 | 사용자 입력 원문 | 수정 전 | 수정 후 |
|---|---|---|---|
| 1 | 대표자의 보고의무는 위임할 수 있는가?<br>(업무 문맥: 내부회계관리제도) | ERROR / Incomplete or blocked OpenRouter response | ERROR / 별도 실행 없음 |
| 2 | 방금 질문은 주주총회에 대한 보고를 뜻했어. 보고받는 기관을 주주총회로 정정해서 다시 판단해줘. | CLARIFY / 사용자가 '방금 질문'의 보고 대상 기관을 '주주총회'로 정정하고 다시 판단해달라고 명확히 지시했습니다. 이는 현재 대화 컨텍스트의 마지막 질문을 대상으로 하는 사실 정정(CORRECT) 요청에 해당하며, 제공된 방법 중 FACT_UPDATE가 적절합니다. 그러나 제안된 명령은 goals가 비어 있다는 이유로 대상이 불분명하다고 판단하여 NEED_TARGET(CLARIFY)를 선택했습니다. '방금 질문'이라는 표현은 대화 흐름상 직전 질문을 가리키는 명확한 지시이므로, 추가 확인 없이 FACT_UPDATE를 통해 정정해야 합니다. 따라서 제안된 명령이 사용자의 의도와 일치하지 않습니다. | READY / READ → SELECT → ASSESS → COMPOSE |
| 3 | 첫 정정도 잘못됐어. 이사회 및 감사에 대한 보고로 정정해서 다시 판단해줘. | CLARIFY / 사용자의 발언 '첫 정정도 잘못됐어. 이사회 및 감사에 대한 보고로 정정해서 다시 판단해줘'는 기존 판단의 사실관계(보고 대상)를 수정하고 재판단을 요청하는 명확한 의도입니다. 이는 FACT_UPDATE(사실 수정 및 재평가)에 해당하며, 제공된 기록에서 대상을 특정할 수 없다는 이유로 NEED_TARGET(확인 요청)을 제안한 것은 사용자의 명시적 수정 지시를 무시하는 것입니다. | READY / ASSESS → COMPOSE |
| 4 | 두 번째 정정이 틀렸어. 첫 번째 정정 직후의 보고 대상 조건으로 돌아가줘. | CLARIFY / restore fields require STATE_RESTORE | ERROR / 별도 실행 없음 |
| 5 | 이제 최초 질문 때의 범위로 돌아가줘. 정정 때 추가한 보고 대상 조건을 없애고 최초 질문 전체에 답해줘. | CLARIFY / 사용자가 '최초 질문'으로 복원해 달라고 명확히 요청했으나, 제안된 명령은 복원 대상이 특정되지 않았다며 NEED_TARGET(CLARIFY)를 지정했습니다. 이는 명시된 복원 요청을 무시하고 불필요한 확인을 요구하는 것이므로 유효하지 않습니다. | ERROR / 별도 실행 없음 |
| 6 | 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘. | CLARIFY / 사용자가 '이 질문'이라고 지칭하여 현재 대화 맥락의 질문을 명확히 가리키고 있으므로, 대상이 불분명하여 확인(NEED_TARGET)이 필요한 상황이 아닙니다. 명시된 자연어 최종 확인·저장 요청에 따라 FINALIZE(EXPERIENCE_CONFIRM)를 제안하는 것이 적절하며, 불필요한 확인 요청으로 유효한 명령을 거절하고 있습니다. | ERROR / 별도 실행 없음 |
| 7 | 이 질문을 최초부터 어떤 정정을 거쳐 고쳤는지, 현재 왜 이 결론인지 실제 기록과 근거를 설명해줘. | CLARIFY / 사용자가 '이 질문'의 최초 내용, 정정 과정, 현재 결론에 대한 기록과 근거 설명을 요청했으나, 제공된 goals 목록이 비어 있어 설명 대상이 되는 특정 질문(목표)을 특정할 수 없습니다. 기록에서 요청 대상을 특정할 수 없으므로 확인이 필요합니다. | ERROR / 별도 실행 없음 |
| 8 | 현재 조건과 결론은 유지하고 최종 답변만 표로 써줘. | CLARIFY / target not offered | ERROR / 별도 실행 없음 |
| 9 | 대표자의 보고의무는 위임할 수 있는가?<br>(업무 문맥: 내부회계관리제도) 이전 대화에서 내가 최종 확인한 경험을 활용해줘. | CLARIFY / knowledge required | CLARIFY / knowledge required |
| 10 | 방금 질문에서 보고받는 기관을 이사회 및 감사로 정정해줘. | CLARIFY / 사용자가 '방금 질문'이라는 명확한 상대적 지시를 통해 정정 대상을 특정하고 있으므로, 대상 불명확으로 인한 확인 요청(CLARIFY)은 불필요합니다. 제공된 방법 중 '방금 질문'의 사실(보고받는 기관)을 수정하는 FACT_UPDATE를 선택해야 합니다. | CLARIFY / 사용자가 '방금 질문'의 조건을 정정했지만, 제공된 goals 목록이 비어 있어 정정 대상 질문을 특정할 수 없습니다. 따라서 대상 확인이 필요합니다. |
| 11 | 방금 정정이 잘못됐어. 이 대화의 최초 질문 때 범위로 복원해줘. | CLARIFY / restore fields require STATE_RESTORE | CLARIFY / 사용자가 '이 대화의 최초 질문'으로 복원을 요청했으나, 제공된 goals 목록이 비어 있어 복원할 대상 질문을 특정할 수 없습니다. 기록에서 요청 대상을 결정할 수 없으므로 확인이 필요합니다. |
| 12 | 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘. | CLARIFY / 사용자가 '이 질문의 최종 정답 루트를 저장해줘'라고 명시적으로 최종 확인 및 저장(FINALIZE)을 요청했으나, 제안된 명령은 NEED_TARGET(CLARIFY)로 설정되어 있습니다. 이는 저장 요청이 있는 상황에서 유효한 명령을 거절하는 것으로, 시스템 지침에 따라 유효하지 않습니다. | CLARIFY / 사용자가 현재 답변이 최종 맞다고 확인하고 정답 루트 저장을 지시했으나, 제공된 goals 목록이 비어 있어 저장 대상이 되는 질문(목표)을 특정할 수 없습니다. 저장할 대상 질문을 확인해야 합니다. |

### cm-038-chain / 1

사용자: 대표자의 보고의무는 위임할 수 있는가?
(업무 문맥: 내부회계관리제도)

**수정 전 실제 답변**

답변 없음: Incomplete or blocked OpenRouter response

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-01.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-01.json)

### cm-038-chain / 2

사용자: 방금 질문은 주주총회에 대한 보고를 뜻했어. 보고받는 기관을 주주총회로 정정해서 다시 판단해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '방금 질문'의 보고 대상 기관을 '주주총회'로 정정하고 다시 판단해달라고 명확히 지시했습니다. 이는 현재 대화 컨텍스트의 마지막 질문을 대상으로 하는 사실 정정(CORRECT) 요청에 해당하며, 제공된 방법 중 FACT_UPDATE가 적절합니다. 그러나 제안된 명령은 goals가 비어 있다는 이유로 대상이 불분명하다고 판단하여 NEED_TARGET(CLARIFY)를 선택했습니다. '방금 질문'이라는 표현은 대화 흐름상 직전 질문을 가리키는 명확한 지시이므로, 추가 확인 없이 FACT_UPDATE를 통해 정정해야 합니다. 따라서 제안된 명령이 사용자의 의도와 일치하지 않습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-02.json)

**수정 후 실제 답변**

내부회계관리제도에서 주주총회에 대한 대표자의 보고의무는 위임할 수 없습니다.

주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따르면, 회사의 대표자는 사업연도마다 주주총회, 이사회 및 감사에게 내부회계관리제도의 운영실태를 보고해야 합니다. 이 조항의 단서에서는 '회사의 대표자가 필요하다고 판단하는 경우 이사회 및 감사에 대한 보고는 내부회계관리자가 하도록 할 수 있다'고 명시하고 있습니다.

위 규정은 이사회 및 감사에 대한 보고만 위임이 가능하도록 예외를 인정하고 있으며, 주주총회에 대한 보고의무에 대해서는 위임 예외 규정이 존재하지 않습니다. 따라서 주주총회 대상 보고의무는 대표자가 직접 수행해야 하며, 내부회계관리자에게 위임할 수 없습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-02.json)

### cm-038-chain / 3

사용자: 첫 정정도 잘못됐어. 이사회 및 감사에 대한 보고로 정정해서 다시 판단해줘.

**수정 전 실제 답변**

답변 없음: 사용자의 발언 '첫 정정도 잘못됐어. 이사회 및 감사에 대한 보고로 정정해서 다시 판단해줘'는 기존 판단의 사실관계(보고 대상)를 수정하고 재판단을 요청하는 명확한 의도입니다. 이는 FACT_UPDATE(사실 수정 및 재평가)에 해당하며, 제공된 기록에서 대상을 특정할 수 없다는 이유로 NEED_TARGET(확인 요청)을 제안한 것은 사용자의 명시적 수정 지시를 무시하는 것입니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-03.json)

**수정 후 실제 답변**

내부회계관리제도에서 대표자의 보고의무는 주주총회, 이사회 및 감사(또는 감사위원회)에 대한 것으로 규정되어 있습니다. 이사회 및 감사에 대한 보고는 대표자가 필요하다고 판단하는 경우 내부회계관리자에게 위임할 수 있습니다. 다만, 주주총회에 대한 보고의 위임 여부는 제공된 원문에 명시되어 있지 않으며, 위임의 전제 조건은 '회사의 대표자가 필요하다고 판단하는 경우'이고 내부회계관리자가 상근이사(또는 해당 이사의 업무를 집행하는 자)로 지정되어 있어야 합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-03.json)

### cm-038-chain / 4

사용자: 두 번째 정정이 틀렸어. 첫 번째 정정 직후의 보고 대상 조건으로 돌아가줘.

**수정 전 실제 답변**

답변 없음: restore fields require STATE_RESTORE

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-04.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-04.json)

### cm-038-chain / 5

사용자: 이제 최초 질문 때의 범위로 돌아가줘. 정정 때 추가한 보고 대상 조건을 없애고 최초 질문 전체에 답해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '최초 질문'으로 복원해 달라고 명확히 요청했으나, 제안된 명령은 복원 대상이 특정되지 않았다며 NEED_TARGET(CLARIFY)를 지정했습니다. 이는 명시된 복원 요청을 무시하고 불필요한 확인을 요구하는 것이므로 유효하지 않습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-05.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-05.json)

### cm-038-chain / 6

사용자: 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '이 질문'이라고 지칭하여 현재 대화 맥락의 질문을 명확히 가리키고 있으므로, 대상이 불분명하여 확인(NEED_TARGET)이 필요한 상황이 아닙니다. 명시된 자연어 최종 확인·저장 요청에 따라 FINALIZE(EXPERIENCE_CONFIRM)를 제안하는 것이 적절하며, 불필요한 확인 요청으로 유효한 명령을 거절하고 있습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-06.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-06.json)

### cm-038-chain / 7

사용자: 이 질문을 최초부터 어떤 정정을 거쳐 고쳤는지, 현재 왜 이 결론인지 실제 기록과 근거를 설명해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '이 질문'의 최초 내용, 정정 과정, 현재 결론에 대한 기록과 근거 설명을 요청했으나, 제공된 goals 목록이 비어 있어 설명 대상이 되는 특정 질문(목표)을 특정할 수 없습니다. 기록에서 요청 대상을 특정할 수 없으므로 확인이 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-07.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-07.json)

### cm-038-chain / 8

사용자: 현재 조건과 결론은 유지하고 최종 답변만 표로 써줘.

**수정 전 실제 답변**

답변 없음: target not offered

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-08.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-08.json)

### cm-038-chain / 9

사용자: 대표자의 보고의무는 위임할 수 있는가?
(업무 문맥: 내부회계관리제도) 이전 대화에서 내가 최종 확인한 경험을 활용해줘.

**수정 전 실제 답변**

답변 없음: knowledge required

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-09.json)

**수정 후 실제 답변**

답변 없음: knowledge required

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-09.json)

### cm-038-chain / 10

사용자: 방금 질문에서 보고받는 기관을 이사회 및 감사로 정정해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '방금 질문'이라는 명확한 상대적 지시를 통해 정정 대상을 특정하고 있으므로, 대상 불명확으로 인한 확인 요청(CLARIFY)은 불필요합니다. 제공된 방법 중 '방금 질문'의 사실(보고받는 기관)을 수정하는 FACT_UPDATE를 선택해야 합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-10.json)

**수정 후 실제 답변**

답변 없음: 사용자가 '방금 질문'의 조건을 정정했지만, 제공된 goals 목록이 비어 있어 정정 대상 질문을 특정할 수 없습니다. 따라서 대상 확인이 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-10.json)

### cm-038-chain / 11

사용자: 방금 정정이 잘못됐어. 이 대화의 최초 질문 때 범위로 복원해줘.

**수정 전 실제 답변**

답변 없음: restore fields require STATE_RESTORE

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-11.json)

**수정 후 실제 답변**

답변 없음: 사용자가 '이 대화의 최초 질문'으로 복원을 요청했으나, 제공된 goals 목록이 비어 있어 복원할 대상 질문을 특정할 수 없습니다. 기록에서 요청 대상을 결정할 수 없으므로 확인이 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-11.json)

### cm-038-chain / 12

사용자: 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '이 질문의 최종 정답 루트를 저장해줘'라고 명시적으로 최종 확인 및 저장(FINALIZE)을 요청했으나, 제안된 명령은 NEED_TARGET(CLARIFY)로 설정되어 있습니다. 이는 저장 요청이 있는 상황에서 유효한 명령을 거절하는 것으로, 시스템 지침에 따라 유효하지 않습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-038-chain/turn-12.json)

**수정 후 실제 답변**

답변 없음: 사용자가 현재 답변이 최종 맞다고 확인하고 정답 루트 저장을 지시했으나, 제공된 goals 목록이 비어 있어 저장 대상이 되는 질문(목표)을 특정할 수 없습니다. 저장할 대상 질문을 확인해야 합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-038-chain/turn-12.json)

### cm-003-chain

| 턴 | 사용자 입력 원문 | 수정 전 | 수정 후 |
|---|---|---|---|
| 1 | 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?<br>(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조) | READY / INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE | READY / INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| 2 | 방금 질문의 재무적투자자는 벤처금융 또는 전문투자자에 해당하는 경우야. 그 자격 조건을 추가해서 다시 판단해줘. | ERROR / 별도 실행 없음 | CLARIFY / 사용자의 요청은 기존 판단에 '벤처금융 또는 전문투자자'라는 새로운 자격 조건을 추가하여 다시 판단하는 것입니다. 이는 단순한 사실 정정(FACT_UPDATE)이 아니라, 새로운 조건이 적용된 근거를 찾아 판단을 재수행해야 하므로 조사 계획(PLAN) 단계의 수정이 필요합니다. 제안된 명령은 method_id를 FACT_UPDATE로 지정하고 stage를 ASSESS로 설정했으나, reason에서는 RESEARCH_REPLAN을 선택한다고 설명하는 등 명령 필드와 실제 의도가 일치하지 않습니다. 새로운 조건이 추가되어 검색 및 판단 범위가 변경되므로 RESEARCH_REPLAN(action: CORRECT, stage: PLAN)이 적절하며, FACT_UPDATE(ASSESS)는 기존 사실만 바꾸고 판단을 재확인하는 용도로 부적합합니다. |
| 3 | 그 정정이 잘못됐어. 최초 질문에 없던 자격 조건을 추가하지 말고 최초 질문 때 조건으로 되돌려줘. | READY / ASSESS → COMPOSE | ERROR / 별도 실행 없음 |
| 4 | 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘. | STORED / 별도 실행 없음 | ERROR / 별도 실행 없음 |
| 5 | 이 질문의 최초 조건과 정정, 다시 최초로 복원한 과정을 실제 기록에 근거해 설명해줘. | READY / HISTORY_EXPLAIN | ERROR / 별도 실행 없음 |
| 6 | 지금 조건과 결론을 유지하고 최종 답변만 표로 써줘. | READY / COMPOSE | ERROR / 별도 실행 없음 |
| 7 | 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?<br>(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조) 이전 대화에서 내가 최종 확인한 경험을 활용해줘. | ERROR / 별도 실행 없음 | CLARIFY / knowledge required |

### cm-003-chain / 1

사용자: 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?
(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조)

**수정 전 실제 답변**

재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호에 해당합니다.

제26조 제1항 제3호는 "상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자"를 의무보유 대상으로 규정하고 있습니다. 질문의 사실관계인 '재무적투자자'와 '제3자배정'은 이 조항의 취득 방식 요건과 일치합니다. 반면, 제4호는 '벤처금융 또는 전문투자자'가 '모집이나 매출이 아닌 방법'으로 취득한 주식에 대해 규정하고 있어, 단순 제3자배정 취득과 직접적으로 일치하지 않습니다.

다만, 제3호 적용을 위해서는 '상장예비심사 신청일 전 1년 이내'에 취득했는지 여부가 확인되어야 하며, 제공된 사실에는 이 시점 정보가 명시되어 있지 않아 최종 적용 여부는 추가 확인이 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-003-chain/turn-01.json)

**수정 후 실제 답변**

재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호의 본문 요건에 해당합니다. 제3호는 '상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자'를 의무보유 대상으로 규정하고 있으며, 재무적투자자의 제3자배정 취득은 이 요건을 충족합니다.

다만, 코스닥시장 상장규정 시행세칙 제23조 제4항 제2호에 따라 '벤처금융 또는 전문투자자가 취득한 경우'는 제3호의 단서에서 정하는 예외에 해당하여 제3호의 의무보유 대상에서 제외됩니다. 재무적투자자가 벤처금융 또는 전문투자자에 해당한다고 가정할 경우, 제3호의 6개월 의무보유 적용은 배제됩니다.

이 경우 제4호의 적용 여부가 문제됩니다. 제4호는 '벤처금융 또는 전문투자자가 모집이나 매출이 아닌 방법으로 취득한 투자기간이 2년 미만인 주식등'을 대상으로 하며, 제3자배정 취득은 '모집이나 매출이 아닌 방법'에 해당합니다. 따라서 해당 재무적투자자가 전문투자자 또는 벤처금융에 해당하고, 투자기간이 2년 미만이며, 자본금의 10% 한도 내인 경우 제4호에 의해 상장일부터 1개월의 의무보유 대상이 됩니다.

결론적으로, 재무적투자자가 제3자배정으로 취득한 주식은 기본적으로 제3호의 요건에 해당하지만, 벤처금융 또는 전문투자자에 해당하면 제3호에서 제외되고, 추가 요건(투자기간 2년 미만, 자본금 10% 한도 등)을 충족할 경우 제4호에 해당하여 1개월의 의무보유 대상이 됩니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-003-chain/turn-01.json)

### cm-003-chain / 2

사용자: 방금 질문의 재무적투자자는 벤처금융 또는 전문투자자에 해당하는 경우야. 그 자격 조건을 추가해서 다시 판단해줘.

**수정 전 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-003-chain/turn-02.json)

**수정 후 실제 답변**

답변 없음: 사용자의 요청은 기존 판단에 '벤처금융 또는 전문투자자'라는 새로운 자격 조건을 추가하여 다시 판단하는 것입니다. 이는 단순한 사실 정정(FACT_UPDATE)이 아니라, 새로운 조건이 적용된 근거를 찾아 판단을 재수행해야 하므로 조사 계획(PLAN) 단계의 수정이 필요합니다. 제안된 명령은 method_id를 FACT_UPDATE로 지정하고 stage를 ASSESS로 설정했으나, reason에서는 RESEARCH_REPLAN을 선택한다고 설명하는 등 명령 필드와 실제 의도가 일치하지 않습니다. 새로운 조건이 추가되어 검색 및 판단 범위가 변경되므로 RESEARCH_REPLAN(action: CORRECT, stage: PLAN)이 적절하며, FACT_UPDATE(ASSESS)는 기존 사실만 바꾸고 판단을 재확인하는 용도로 부적합합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-003-chain/turn-02.json)

### cm-003-chain / 3

사용자: 그 정정이 잘못됐어. 최초 질문에 없던 자격 조건을 추가하지 말고 최초 질문 때 조건으로 되돌려줘.

**수정 전 실제 답변**

제시된 사실(재무적투자자, 제3자배정 취득)에 따르면, 해당 주식은 **코스닥시장 상장규정 제26조 제1항 제3호**에 해당합니다.

**판단 근거**
1. **제3호 적용**: 제26조 제1항 제3호는 '상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자'를 의무보유 대상으로 규정하고 있습니다. 질문의 핵심 조건인 '제3자배정'으로 취득한 주식은 이 조항의 취득 방식 요건과 일치합니다.
2. **제4호 비적용**: 제26조 제1항 제4호는 '벤처금융 또는 전문투자자'가 '모집이나 매출이 아닌 방법'으로 취득한 주식에 대해 규정하고 있습니다. '재무적투자자'라는 표현은 법률상 '벤처금융 또는 전문투자자'와 동일시할 수 없으며, 제3자배정 취득은 제4호에서 명시한 '모집이나 매출이 아닌 방법'의 일반적 정의와도 직접적으로 연결되지 않습니다. 따라서 단순 '재무적투자자'의 제3자배정 취득은 제4호의 적용 대상이 아닙니다.

**한계점**
* 제3호 적용을 위해서는 '상장예비심사 신청일 전 1년 이내'에 취득했어야 한다는 시간적 요건이 충족되어야 하나, 제공된 사실에는 취득 시점이 명시되어 있지 않아 이 요건 충족 여부는 확인이 필요합니다.
* 해당 재무적투자자가 법적으로 '벤처금융 또는 전문투자자'에 해당하는지 여부가 확인되지 않아, 제4호 적용 가능성의 완전한 배제를 위한 법적 정의 확인은 추가 조사가 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-003-chain/turn-03.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-003-chain/turn-03.json)

### cm-003-chain / 4

사용자: 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.

**수정 전 실제 답변**

제시된 사실(재무적투자자, 제3자배정 취득)에 따르면, 해당 주식은 **코스닥시장 상장규정 제26조 제1항 제3호**에 해당합니다.

**판단 근거**
1. **제3호 적용**: 제26조 제1항 제3호는 '상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자'를 의무보유 대상으로 규정하고 있습니다. 질문의 핵심 조건인 '제3자배정'으로 취득한 주식은 이 조항의 취득 방식 요건과 일치합니다.
2. **제4호 비적용**: 제26조 제1항 제4호는 '벤처금융 또는 전문투자자'가 '모집이나 매출이 아닌 방법'으로 취득한 주식에 대해 규정하고 있습니다. '재무적투자자'라는 표현은 법률상 '벤처금융 또는 전문투자자'와 동일시할 수 없으며, 제3자배정 취득은 제4호에서 명시한 '모집이나 매출이 아닌 방법'의 일반적 정의와도 직접적으로 연결되지 않습니다. 따라서 단순 '재무적투자자'의 제3자배정 취득은 제4호의 적용 대상이 아닙니다.

**한계점**
* 제3호 적용을 위해서는 '상장예비심사 신청일 전 1년 이내'에 취득했어야 한다는 시간적 요건이 충족되어야 하나, 제공된 사실에는 취득 시점이 명시되어 있지 않아 이 요건 충족 여부는 확인이 필요합니다.
* 해당 재무적투자자가 법적으로 '벤처금융 또는 전문투자자'에 해당하는지 여부가 확인되지 않아, 제4호 적용 가능성의 완전한 배제를 위한 법적 정의 확인은 추가 조사가 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-003-chain/turn-04.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-003-chain/turn-04.json)

### cm-003-chain / 5

사용자: 이 질문의 최초 조건과 정정, 다시 최초로 복원한 과정을 실제 기록에 근거해 설명해줘.

**수정 전 실제 답변**

현재 판단과 실제 수정 이력입니다.

제시된 사실(재무적투자자, 제3자배정 취득)에 따르면, 해당 주식은 **코스닥시장 상장규정 제26조 제1항 제3호**에 해당합니다.

**판단 근거**
1. **제3호 적용**: 제26조 제1항 제3호는 '상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자'를 의무보유 대상으로 규정하고 있습니다. 질문의 핵심 조건인 '제3자배정'으로 취득한 주식은 이 조항의 취득 방식 요건과 일치합니다.
2. **제4호 비적용**: 제26조 제1항 제4호는 '벤처금융 또는 전문투자자'가 '모집이나 매출이 아닌 방법'으로 취득한 주식에 대해 규정하고 있습니다. '재무적투자자'라는 표현은 법률상 '벤처금융 또는 전문투자자'와 동일시할 수 없으며, 제3자배정 취득은 제4호에서 명시한 '모집이나 매출이 아닌 방법'의 일반적 정의와도 직접적으로 연결되지 않습니다. 따라서 단순 '재무적투자자'의 제3자배정 취득은 제4호의 적용 대상이 아닙니다.

**한계점**
* 제3호 적용을 위해서는 '상장예비심사 신청일 전 1년 이내'에 취득했어야 한다는 시간적 요건이 충족되어야 하나, 제공된 사실에는 취득 시점이 명시되어 있지 않아 이 요건 충족 여부는 확인이 필요합니다.
* 해당 재무적투자자가 법적으로 '벤처금융 또는 전문투자자'에 해당하는지 여부가 확인되지 않아, 제4호 적용 가능성의 완전한 배제를 위한 법적 정의 확인은 추가 조사가 필요합니다.

수정 이력:
- [1] 최초 질문: 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?
(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조)
  질문 목적: null → "재무적투자자가 제3자배정으로 취득한 주식이 코스닥시장 상장규정 제26조 제3호와 제4호 중 어디에 해당하는지 판단한다"
  문서 구분: null → "ALL"
  문서 범위: null → ["3521c3aaa5a735fd"]
  사건 조건: null → [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}]
  검색 계획: null → ["코스닥시장 상장규정 제26조 제3호", "코스닥시장 상장규정 제26조 제4호", "재무적투자자 제3자배정 취득 주식 의무보유"]
  적용 방법: CASE_START — 새 질문의 목적과 조건을 분리한다
- [2] 1차 정정: 방금 질문의 재무적투자자는 벤처금융 또는 전문투자자에 해당하는 경우야. 그 자격 조건을 추가해서 다시 판단해줘.
  사건 조건: [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}] → [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}, {"name": "투자자 자격", "value": "벤처금융 또는 전문투자자"}]
  적용 방법: FACT_UPDATE — 현재 사건 사실만 바꾸고 적용 판단을 다시 확인한다
- [3] 2차 정정: 그 정정이 잘못됐어. 최초 질문에 없던 자격 조건을 추가하지 말고 최초 질문 때 조건으로 되돌려줘.
  사건 조건: [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}, {"name": "투자자 자격", "value": "벤처금융 또는 전문투자자"}] → [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}]
  기록 [1]의 지정 조건을 복원했습니다.
  적용 방법: STATE_RESTORE — 기록된 특정 이벤트의 조건을 정확히 복원한다

현재 판단의 원문 근거:
- 재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호에 해당한다. / article:3e4ab92e38b531a09f6419a9 / 원문: 3. 상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자: 상장일부터 6개월(기술성장기업 또는 제31조제1항에 따른 신속이전기업은 1년으로 한다). 다만, 세칙으로 정하는 경우는 제외한다.
- 제26조 제1항 제4호는 '벤처금융 또는 전문투자자'가 모집이나 매출이 아닌 방법으로 취득한 주식에 대해 규정하고 있어, 단순 '재무적투자자'가 제3자배정으로 취득한 경우와 직접적으로 일치하지 않는다. / article:3e4ab92e38b531a09f6419a9 / 원문: 4. 벤처금융 또는 전문투자자가 모집이나 매출이 아닌 방법으로 취득한 투자기간(상장예비심사 신청일을 기준으로 한다)이 2년 미만인 주식등(벤처금융 또는 전문투자자가 취득한 주식등 중에서 상장신청일 현재 상장신청인의 자본금을 기준으로 각각 100분의 10에 상당하는 한도까지의 주식등으로 한정한다): 상장일부터 1개월. 다만, 세칙으로 정하는 경우는 제외한다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-003-chain/turn-05.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-003-chain/turn-05.json)

### cm-003-chain / 6

사용자: 지금 조건과 결론을 유지하고 최종 답변만 표로 써줘.

**수정 전 실제 답변**

| 구분 | 내용 |
| :--- | :--- |
| **판단 대상** | 재무적투자자가 제3자배정으로 취득한 주식의 코스닥시장 상장규정 제26조 제1항 해당 조항 |
| **적용 조항** | **제26조 제1항 제3호** |
| **근거** | 제3호는 "상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자"를 대상으로 하며, 취득 방식이 제3자배정인 경우 투자자 유형(재무적투자자)과 무관하게 해당 조항에 우선 적용됩니다. |
| **제4호 배제 이유** | 제4호는 "벤처금융 또는 전문투자자"가 모집이나 매출이 아닌 방법으로 취득한 주식에 대해 규정하고 있습니다. 현재 사실에서 투자자가 벤처금융 또는 전문투자자에 해당하는지 여부가 확인되지 않았으므로, 단순 '재무적투자자'로서 제3자배정 취득 시 제3호에 해당한다고 판단합니다. |
| **의무보유 기간** | 상장일부터 6개월 (기술성장기업 또는 신속이전기업은 1년) |
| **한계점** | 1. 제3자배정 취득 시점이 '상장예비심사 신청일 전 1년 이내'인지 여부가 제공된 사실에 명시되어 있지 않아 제3호 적용 요건 충족 여부를 최종 확정할 수 없습니다.<br>2. 해당 재무적투자자가 '벤처금융 또는 전문투자자'에 해당하는지 여부가 제공된 사실에 명시되어 있지 않아 제4호 적용 가능성 배제를 위한 법적 정의 확인이 필요합니다. |

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-003-chain/turn-06.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-003-chain/turn-06.json)

### cm-003-chain / 7

사용자: 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?
(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조) 이전 대화에서 내가 최종 확인한 경험을 활용해줘.

**수정 전 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/BASELINE/cm-003-chain/turn-07.json)

**수정 후 실제 답변**

답변 없음: knowledge required

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/RECOVERED/cm-003-chain/turn-07.json)

## 실패와 미확인 범위

확인된 구조적 원인: 첫 CM038 근거 보완 호출에서 C001·C002를 각각 두 번 선택했다. 모든 ID가 허용 목록 안이었지만 중복 ID 검사에서 전체 선별이 실패했다. 또한 복원 후 검사 모델이 이전 이벤트를 최신 상태로 잘못 읽거나, 원문에 있는 기관별 일반 규칙 설명을 사건 사실 추가로 오해했다. 현재 상태 복원과 최종 답변 검증은 서로 다른 성공 조건이다.

아래 원점수는 실행 전 동결한 채점 기준을 그대로 사용한다. 초기 답변이 실패하면 출력 state가 없어 복원 비교도 실패할 수 있으므로, 상태 체인의 실제 복원 여부는 별도 진단 자료에서 구분한다.

```json
[
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 1,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 2,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 3,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 6,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "exact_history_event_references",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "presentation_only_compose",
    "pass": false,
    "expected": [
      "COMPOSE"
    ],
    "actual": null
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 9,
    "kind": "completion",
    "pass": false,
    "expected": "REUSED",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 10,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 12,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 2,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 7,
    "kind": "completion",
    "pass": false,
    "expected": "REUSED",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 1,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": [
      {
        "name": "업무 문맥",
        "value": "내부회계관리제도"
      },
      {
        "name": "보고 대상 기관",
        "value": "주주총회"
      }
    ],
    "actual": null
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 6,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "exact_history_event_references",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "presentation_only_compose",
    "pass": false,
    "expected": [
      "COMPOSE"
    ],
    "actual": null
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 9,
    "kind": "completion",
    "pass": false,
    "expected": "REUSED",
    "actual": "CLARIFY"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 10,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 12,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "CLARIFY"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 2,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 3,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 3,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": [
      {
        "name": "업무 문맥",
        "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"
      }
    ],
    "actual": null
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 4,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "exact_history_event_references",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 6,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 6,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 6,
    "kind": "presentation_only_compose",
    "pass": false,
    "expected": [
      "COMPOSE"
    ],
    "actual": null
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 7,
    "kind": "completion",
    "pass": false,
    "expected": "REUSED",
    "actual": "CLARIFY"
  }
]
```

```json
[
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 1,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 2,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 3,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "history",
    "verdict": {
      "correct": false,
      "reason": "입력된 events와 answer가 모두 비어 있어, 정정 이력을 대조할 수 있는 정보가 없습니다. 요청된 정정 과정을 설명하지 않았으므로 false입니다."
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 9,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 10,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 1,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "기준답은 '시행세칙 제23조 제4항 제2호'를 근거로 제시하여, 재무적투자자(벤처금융 또는 전문투자자)가 제3자배정으로 취득한 주식은 제3호의 단서(세칙으로 정하는 경우)에 해당하여 제3호에서 제외되고 제4호가 적용된다고 결론짓고 있습니다. 반면, 평가 대상 답변은 제3호에 해당한다고 결론짓고 있으며, 기준답의 핵심 근거인 '시행세칙'의 적용을 누락하고 있습니다. 따라서 결론과 핵심 단서가 일치하지 않아 false입니다."
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 2,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 3,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "참고답(reference_answer)은 '시행세칙 제23조 제4항 제2호'를 근거로 제시된 재무적투자자가 벤처금융 또는 전문투자자에 해당하여 제3호 단서에 의해 제외되고, 결국 '제4호'가 적용된다고 결론짓고 있습니다. 반면, 평가 대상 답변은 '제3호'에 해당한다고 결론짓고 있으며, 참고답의 핵심 근거인 시행세칙의 예외 규정을 무시하고 있습니다. 따라서 결론과 핵심 단서가 일치하지 않아 false입니다."
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 7,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 1,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "history",
    "verdict": {
      "correct": false,
      "reason": "입력된 events와 answer가 모두 비어 있어, 정정 이력을 대조할 수 있는 정보가 없습니다. 따라서 원래 상태, 조건 변경, 복원 대상에 대한 설명을 검증할 수 없으므로 false로 판단합니다."
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 9,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 10,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 2,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 3,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "history",
    "verdict": {
      "correct": false,
      "reason": "입력된 events와 answer가 모두 비어 있어, 정정 이력을 대조할 수 있는 정보가 없습니다. 요청된 정정 과정을 설명하지 않았으므로 false입니다."
    }
  },
  {
    "arm": "RECOVERED",
    "case_id": "cm-003-chain",
    "turn": 7,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  }
]
```

이번 실험은 처음부터 arm당 재사용 2회·복원 4회를 동결했다. 이력·표 이후 경험 보존은 해당 질문의 묶음으로 확인했다. ADR0611의 단순 통과 개수와 직접 합산하지 않는다.

조건 복원·이력 설명·경험 보존이 성공해도 법률 판단의 정확성을 보장하지 않는다. 원문 누락, 적용 대상 해석, 예외·참조 연결, 온톨로지의 도메인 적합성은 각각 검증해야 한다.

## 비용·지연과 출처

```json
{
  "usage": {
    "calls": 160,
    "cost_usd": 0.39525388,
    "input_tokens": 1302754,
    "output_tokens": 46209,
    "judge_calls": 9
  },
  "arms": {
    "BASELINE": {
      "functional_passed": 12,
      "functional_total": 33,
      "legal_correct": 0,
      "legal_total": 12,
      "history_correct": 1,
      "history_total": 2,
      "completed_turns": 5,
      "turns": 19,
      "calls": 59,
      "cost_usd": 0.11917216,
      "input_tokens": 361596,
      "output_tokens": 18988,
      "latency": {
        "p50": 11.419294449035078,
        "p95": 80.01348948897794
      }
    },
    "RECOVERED": {
      "functional_passed": 5,
      "functional_total": 33,
      "legal_correct": 3,
      "legal_total": 12,
      "history_correct": 0,
      "history_total": 2,
      "completed_turns": 3,
      "turns": 19,
      "calls": 92,
      "cost_usd": 0.27022492,
      "input_tokens": 925078,
      "output_tokens": 26313,
      "latency": {
        "p50": 18.958570052986033,
        "p95": 54.730239622993395
      }
    }
  },
  "generation": "01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation",
  "generation_id": "term-source-1acfbe06921527e74a0b",
  "store_sha256": "422cfa15b9dba609f3c6105e3d5d3c7dbdb27e90a09469d57ca6bc602b4d9c72",
  "scope_documents": 145,
  "source_manifest_export_allowed_unchanged": false
}
```

[실험 결정문](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/README.md) · [동결 설계·계보](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/실험/manifest.json) · [원점수](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/run-001/result.json) · [공개 원문 출처 결속](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery/artifacts/design/source-binding.json)

[수정된 메모리 실행](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0612/bounded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py) · [등록된 메모리 방법과 이력 출력](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0612/bounded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/memory_methods.py) · [답변 작성·검사 입력](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0612/bounded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/memory_rag.py)

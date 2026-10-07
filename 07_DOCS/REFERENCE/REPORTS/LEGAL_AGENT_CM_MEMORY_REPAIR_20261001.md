# 실제 CM 데이터 멀티턴 수정·재실험 — ADR-0611

실제 저장 CM 질문 **cm-038(대표자의 내부회계 보고 위임), cm-003(신규상장 의무보유)**에서 시작해 각각 12턴·7턴을 진행했다. 수정 전후 같은 19턴씩 총38턴이며, 정정용 후속 발언은 실험을 위해 작성했다. 모의 A/B 규정을 쓰지 않았다. 저장된 공개 원문145문서 범위를 허용하고 실제 검색·원문 읽기를 거쳤다. CM 전체61문항 전수평가는 아니다.

제품·중간 처리와 분리된 사후 평가는 qwen/qwen3.8-27b, Parasail FP8, reasoning none, temperature0, fallback 없음이다. 골든 답은 제품 입력에 제공하지 않았다. 법률 결과는 저장 CM 기준답과의 일치 평가이며 현행 법률 자문 인증은 아니다.

## 수정한 범위

| 변경 | 동작 |
|---|---|
| 허용 방법 선택 | 모델은 CASE_START, FACT_UPDATE, STATE_RESTORE, HISTORY_EXPLAIN, ANSWER_PRESENT 등 등록된 메모리 작업 방법을 선택한다. 서버가 해당 방법의 동작과 시작 단계를 정한다. |
| 설명·표의 권한 | 이력 조회와 표현 방법은 사실·목적·검색 계획을 몰래 바꾸지 못한다. 잘못된 필드를 제출하면 거부하고 제한된 재수정을 요청한다. |
| 경험 폐기 | 명령 이름만 보고 폐기하던 분기를 제거했다. 실제 상태가 바뀌거나 판단을 다시 검토하는 경우에 이전 경험을 무효화한다. 표현만 바꾸면 확인된 경험을 보존한다. |
| 이력 근거 | 이력 설명은 DB의 실제 이벤트·이전/이후 조건·복원 대상 ID로 출력한다. 모델이 과거 경위를 만들어 쓰는 경로를 없앴다. 일반 최종 답변·표는 계속 LLM이 작성한다. |
| 보조 검사 | 일반 답변 작성과 검사에도 실제 정정 이력을 전달해, 존재하는 정정을 부정하는 설명을 점검하도록 했다. |

**구현 범위는 메모리 작업의 방법·권한 통제다. 법률 개념·관계·적용 경로 전체를 승인된 온톨로지로 강제하는 기능은 아직 아니다.** 현재 원문 선택 이유와 법률 개념명에는 자유 문장이 남는다.

수정 구현의 모델 없는 상태·권한 계약 검사: **34/34**. 제품 MAIN·GENOS에 활성화하지 않은 격리 후보에서 검증했다.

## 실제 모델 결과

| 항목 | 수정 전 BASELINE | 수정 후 GUARDED |
|---|---:|---:|
| 정상 응답 턴 | 8/19 | 5/19 |
| 상태·권한 체크 | 12/33 | 12/33 |
| CM 기준답 일치 | 5/12 | 0/12 |
| 정정 이력 설명 정확성 | 1/2 | 1/2 |

이력 설명은 실제 이전 상태·정정·복원 과정을 모두 설명하는지 별도 사후 평가했다. 상태 점수와 법률 답변 점수는 합산하지 않는다. 한 가지 원인으로 여러 후속 턴이 막히면 체크 실패가 여러 번 집계된다.

```json
{
  "legal": {
    "guarded_only": 0,
    "baseline_only": 5,
    "both_correct": 0,
    "both_wrong": 7
  },
  "history": {
    "guarded_only": 1,
    "baseline_only": 1,
    "both_correct": 0,
    "both_wrong": 0
  }
}
```

## 턴별 비교

### cm-038-chain

| 턴 | 사용자 입력 원문 | 수정 전 | 수정 후 |
|---|---|---|---|
| 1 | 대표자의 보고의무는 위임할 수 있는가?<br>(업무 문맥: 내부회계관리제도) | READY / INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE | ERROR / Incomplete or blocked OpenRouter response |
| 2 | 방금 질문은 주주총회에 대한 보고를 뜻했어. 보고받는 기관을 주주총회로 정정해서 다시 판단해줘. | READY / ASSESS → COMPOSE | CLARIFY / target not offered |
| 3 | 첫 정정도 잘못됐어. 이사회 및 감사에 대한 보고로 정정해서 다시 판단해줘. | READY / ASSESS → COMPOSE | CLARIFY / target not offered |
| 4 | 두 번째 정정이 틀렸어. 첫 번째 정정 직후의 보고 대상 조건으로 돌아가줘. | READY / ASSESS → COMPOSE | CLARIFY / restore fields require STATE_RESTORE |
| 5 | 이제 최초 질문 때의 범위로 돌아가줘. 정정 때 추가한 보고 대상 조건을 없애고 최초 질문 전체에 답해줘. | READY / ASSESS → COMPOSE | CLARIFY / 사용자의 요청은 '최초 질문'이라는 명확한 시간적 기준과 '정정 때 추가한 조건'이라는 구체적인 변경 사항(보고 대상 조건)을 명시하고 있어 복원 대상이 충분히 특정됩니다. 제공된 goals 목록이 비어 있다는 기술적 상태만으로 대상을 특정할 수 없다고 판단하여 NEED_TARGET을 선택한 것은 적절하지 않으며, 이는 유효한 복원 요청을 부당하게 거부하는 것입니다. 따라서 valid=false입니다. |
| 6 | 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘. | STORED / 별도 실행 없음 | CLARIFY / 사용자가 '지금 답변'과 '이 질문'을 지칭하여 저장 대상을 명확히 특정했으며, 이는 현재 대화 컨텍스트의 마지막 질문을 의미합니다. 제공된 goals 목록이 비어 있다는 기술적 상태만으로 대상을 특정할 수 없다고 판단하여 CLARIFY를 제안한 것은 유효한 명령을 부당하게 거절한 것입니다. 현재 발언의 마지막 조건에 맞는 명시적 저장 요청이므로 FINALIZE(EXPERIENCE_CONFIRM)가 적절합니다. |
| 7 | 이 질문을 최초부터 어떤 정정을 거쳐 고쳤는지, 현재 왜 이 결론인지 실제 기록과 근거를 설명해줘. | READY / COMPOSE | CLARIFY / 사용자가 특정 질문의 최초 내용, 정정 과정, 현재 결론에 이르기까지의 실제 기록과 근거를 설명해 달라고 요청했습니다. 그러나 제공된 goals 목록이 비어 있어 설명 대상이 되는 질문(목표)을 특정할 수 없습니다. 기록에서 요청 대상을 특정할 수 없으므로 확인이 필요합니다. |
| 8 | 현재 조건과 결론은 유지하고 최종 답변만 표로 써줘. | READY / COMPOSE | CLARIFY / target not offered |
| 9 | 대표자의 보고의무는 위임할 수 있는가?<br>(업무 문맥: 내부회계관리제도) 이전 대화에서 내가 최종 확인한 경험을 활용해줘. | CLARIFY / knowledge required | CLARIFY / 사용자가 이전 대화에서 최종 확인한 경험을 활용하도록 요청했으나, 제공된 knowledge 목록이 비어 있어 재사용할 대상 경험을 특정할 수 없습니다. 따라서 대상 확인이 필요합니다. |
| 10 | 방금 질문에서 보고받는 기관을 이사회 및 감사로 정정해줘. | CLARIFY / 사용자가 '방금 질문'을 언급했으나 제공된 goals 목록이 비어 있어 정정 대상이 되는 기존 질문을 특정할 수 없습니다. 정정할 대상이 없으므로 확인이 필요합니다. | CLARIFY / 사용자가 '방금 질문'이라는 명확한 상대적 지시를 통해 정정 대상을 특정하고 있으므로, 대상 불명확으로 인한 확인 요청(CLARIFY)은 불필요합니다. 제공된 방법 중 현재 사실만 변경하는 FACT_UPDATE가 적절하며, 이를 무시하고 확인을 요구한 것은 유효한 명령을 거절한 것입니다. |
| 11 | 방금 정정이 잘못됐어. 이 대화의 최초 질문 때 범위로 복원해줘. | CLARIFY / original event not retrieved | CLARIFY / restore fields require STATE_RESTORE |
| 12 | 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘. | CLARIFY / 사용자가 '지금 답변이 최종 맞아'라고 명시적으로 최종 확인을 요청하고 '저장해줘'라고 지시했으므로 FINALIZE 명령이 유효합니다. 제안된 CLARIFY 명령은 goals 목록이 비어 있다는 이유로 확인을 요청하고 있으나, 이는 현재 대화 맥락에서 이미 확정된 답변을 저장하는 요청을 잘못 해석한 것입니다. 명시된 자연어 최종 확인·저장 요청이 있으므로 FINALIZE가 적절하며, CLARIFY는 유효하지 않습니다. | CLARIFY / 사용자가 '이 질문의 최종 정답 루트를 저장해줘'라고 명시적으로 저장(FINALIZE)을 요청했으나, 제안된 명령은 NEED_TARGET(CLARIFY)로 저장 없이 확인만 하도록 되어 있어 요청과 일치하지 않습니다. |

### cm-038-chain / 1

사용자: 대표자의 보고의무는 위임할 수 있는가?
(업무 문맥: 내부회계관리제도)

**수정 전 실제 답변**

내부회계관리제도에서 대표자의 보고의무는 주주총회와 이사회 및 감사에 대한 보고로 구분되며, 이사회 및 감사에 대한 보고는 대표자가 필요하다고 판단하는 경우 내부회계관리자에게 위임할 수 있습니다. 주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따르면, 회사의 대표자는 사업연도마다 주주총회, 이사회 및 감사에게 내부회계관리제도의 운영실태를 보고하여야 합니다. 다만, 대표자가 필요하다고 판단하는 경우 이사회 및 감사에 대한 보고는 내부회계관리자가 하도록 할 수 있습니다. 따라서 주주총회에 대한 보고의무는 위임이 불가능하며, 이사회 및 감사에 대한 보고의무만 위임이 가능합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-01.json)

**수정 후 실제 답변**

답변 없음: Incomplete or blocked OpenRouter response

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-01.json)

### cm-038-chain / 2

사용자: 방금 질문은 주주총회에 대한 보고를 뜻했어. 보고받는 기관을 주주총회로 정정해서 다시 판단해줘.

**수정 전 실제 답변**

주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따르면, 회사의 대표자는 사업연도마다 주주총회, 이사회 및 감사에게 내부회계관리제도의 운영실태를 보고하여야 합니다. 다만, 이사회 및 감사에 대한 보고는 대표자가 필요하다고 판단하는 경우 내부회계관리자가 하도록 위임할 수 있으나, 주주총회에 대한 보고는 위임 대상에서 제외되어 있습니다. 따라서 내부회계관리제도에서 대표자의 주주총회 보고의무를 위임할 수 없습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-02.json)

**수정 후 실제 답변**

답변 없음: target not offered

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-02.json)

### cm-038-chain / 3

사용자: 첫 정정도 잘못됐어. 이사회 및 감사에 대한 보고로 정정해서 다시 판단해줘.

**수정 전 실제 답변**

내부회계관리제도에서 대표자의 보고의무는 이사회 및 감사에 대한 보고에 한하여 내부회계관리자에게 위임할 수 있습니다. 주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따르면, 회사의 대표자는 사업연도마다 주주총회, 이사회 및 감사에게 내부회계관리제도의 운영실태를 보고해야 합니다. 다만, 대표자가 필요하다고 판단하는 경우 이사회 및 감사에 대한 보고는 내부회계관리자가 하도록 할 수 있습니다. 따라서 주주총회에 대한 보고의무는 위임이 불가능하며, 이사회 및 감사에 대한 보고만 위임이 가능합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-03.json)

**수정 후 실제 답변**

답변 없음: target not offered

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-03.json)

### cm-038-chain / 4

사용자: 두 번째 정정이 틀렸어. 첫 번째 정정 직후의 보고 대상 조건으로 돌아가줘.

**수정 전 실제 답변**

주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따르면, 회사의 대표자는 사업연도마다 주주총회, 이사회 및 감사에게 내부회계관리제도의 운영실태를 보고해야 합니다. 다만, 이사회 및 감사에 대한 보고는 대표자가 필요하다고 판단하는 경우 내부회계관리자가 하도록 위임할 수 있습니다. 그러나 주주총회에 대한 보고의무는 위임 대상에서 제외되어 있으므로, 내부회계관리제도에서 대표자의 주주총회 보고의무를 위임할 수 없습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-04.json)

**수정 후 실제 답변**

답변 없음: restore fields require STATE_RESTORE

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-04.json)

### cm-038-chain / 5

사용자: 이제 최초 질문 때의 범위로 돌아가줘. 정정 때 추가한 보고 대상 조건을 없애고 최초 질문 전체에 답해줘.

**수정 전 실제 답변**

내부회계관리제도에서 대표자의 보고의무 위임 여부는 보고 대상에 따라 다릅니다. 주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따라 대표자는 사업연도마다 주주총회, 이사회 및 감사에게 내부회계관리제도의 운영실태를 보고해야 합니다. 이 중 이사회 및 감사에 대한 보고는 대표자가 필요하다고 판단하는 경우 내부회계관리자가 하도록 위임할 수 있습니다. 그러나 주주총회에 대한 보고의무는 위임할 수 없으며, 반드시 대표자가 직접 수행해야 합니다. 또한, 내부회계관리제도의 관리·운영에 대한 대표자의 책임 자체는 위임할 수 없습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-05.json)

**수정 후 실제 답변**

답변 없음: 사용자의 요청은 '최초 질문'이라는 명확한 시간적 기준과 '정정 때 추가한 조건'이라는 구체적인 변경 사항(보고 대상 조건)을 명시하고 있어 복원 대상이 충분히 특정됩니다. 제공된 goals 목록이 비어 있다는 기술적 상태만으로 대상을 특정할 수 없다고 판단하여 NEED_TARGET을 선택한 것은 적절하지 않으며, 이는 유효한 복원 요청을 부당하게 거부하는 것입니다. 따라서 valid=false입니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-05.json)

### cm-038-chain / 6

사용자: 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.

**수정 전 실제 답변**

내부회계관리제도에서 대표자의 보고의무 위임 여부는 보고 대상에 따라 다릅니다. 주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따라 대표자는 사업연도마다 주주총회, 이사회 및 감사에게 내부회계관리제도의 운영실태를 보고해야 합니다. 이 중 이사회 및 감사에 대한 보고는 대표자가 필요하다고 판단하는 경우 내부회계관리자가 하도록 위임할 수 있습니다. 그러나 주주총회에 대한 보고의무는 위임할 수 없으며, 반드시 대표자가 직접 수행해야 합니다. 또한, 내부회계관리제도의 관리·운영에 대한 대표자의 책임 자체는 위임할 수 없습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-06.json)

**수정 후 실제 답변**

답변 없음: 사용자가 '지금 답변'과 '이 질문'을 지칭하여 저장 대상을 명확히 특정했으며, 이는 현재 대화 컨텍스트의 마지막 질문을 의미합니다. 제공된 goals 목록이 비어 있다는 기술적 상태만으로 대상을 특정할 수 없다고 판단하여 CLARIFY를 제안한 것은 유효한 명령을 부당하게 거절한 것입니다. 현재 발언의 마지막 조건에 맞는 명시적 저장 요청이므로 FINALIZE(EXPERIENCE_CONFIRM)가 적절합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-06.json)

### cm-038-chain / 7

사용자: 이 질문을 최초부터 어떤 정정을 거쳐 고쳤는지, 현재 왜 이 결론인지 실제 기록과 근거를 설명해줘.

**수정 전 실제 답변**

내부회계관리제도에서 대표자의 보고의무 위임 여부는 보고 대상에 따라 달라집니다. 주식회사 등의 외부감사에 관한 법률 제8조 제4항에 따르면, 대표자는 사업연도마다 주주총회, 이사회, 감사에게 내부회계관리제도 운영실태를 보고해야 합니다. 이 중 주주총회에 대한 보고의무는 위임할 수 없으며, 반드시 대표자가 직접 수행해야 합니다. 반면, 이사회 및 감사에 대한 보고는 대표자가 필요하다고 판단하는 경우 내부회계관리자에게 위임할 수 있습니다. 따라서 대표자의 보고의무는 주주총회 대상은 비위임, 이사회 및 감사 대상은 조건부 위임이 가능합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-07.json)

**수정 후 실제 답변**

답변 없음: 사용자가 특정 질문의 최초 내용, 정정 과정, 현재 결론에 이르기까지의 실제 기록과 근거를 설명해 달라고 요청했습니다. 그러나 제공된 goals 목록이 비어 있어 설명 대상이 되는 질문(목표)을 특정할 수 없습니다. 기록에서 요청 대상을 특정할 수 없으므로 확인이 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-07.json)

### cm-038-chain / 8

사용자: 현재 조건과 결론은 유지하고 최종 답변만 표로 써줘.

**수정 전 실제 답변**

| 구분 | 판단 | 근거 |
| :--- | :--- | :--- |
| 주주총회 보고 | 위임 불가 | "④ 회사의 대표자는 사업연도마다 주주총회, 이사회 및 감사(감사위원회가 설치된 경우에는 감사위원회를 말한다. 이하 이 조에서 같다)에게 해당 회사의 내부회계관리제도의 운영실태를 보고하여야 한다. 다만, 회사의 대표자가 필요하다고 판단하는 경우 이사회 및 감사에 대한 보고는 내부회계관리자가 하도록 할 수 있다." |
| 이사회 및 감사 보고 | 위임 가능 | "다만, 회사의 대표자가 필요하다고 판단하는 경우 이사회 및 감사에 대한 보고는 내부회계관리자가 하도록 할 수 있다." |

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-08.json)

**수정 후 실제 답변**

답변 없음: target not offered

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-08.json)

### cm-038-chain / 9

사용자: 대표자의 보고의무는 위임할 수 있는가?
(업무 문맥: 내부회계관리제도) 이전 대화에서 내가 최종 확인한 경험을 활용해줘.

**수정 전 실제 답변**

답변 없음: knowledge required

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-09.json)

**수정 후 실제 답변**

답변 없음: 사용자가 이전 대화에서 최종 확인한 경험을 활용하도록 요청했으나, 제공된 knowledge 목록이 비어 있어 재사용할 대상 경험을 특정할 수 없습니다. 따라서 대상 확인이 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-09.json)

### cm-038-chain / 10

사용자: 방금 질문에서 보고받는 기관을 이사회 및 감사로 정정해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '방금 질문'을 언급했으나 제공된 goals 목록이 비어 있어 정정 대상이 되는 기존 질문을 특정할 수 없습니다. 정정할 대상이 없으므로 확인이 필요합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-10.json)

**수정 후 실제 답변**

답변 없음: 사용자가 '방금 질문'이라는 명확한 상대적 지시를 통해 정정 대상을 특정하고 있으므로, 대상 불명확으로 인한 확인 요청(CLARIFY)은 불필요합니다. 제공된 방법 중 현재 사실만 변경하는 FACT_UPDATE가 적절하며, 이를 무시하고 확인을 요구한 것은 유효한 명령을 거절한 것입니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-10.json)

### cm-038-chain / 11

사용자: 방금 정정이 잘못됐어. 이 대화의 최초 질문 때 범위로 복원해줘.

**수정 전 실제 답변**

답변 없음: original event not retrieved

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-11.json)

**수정 후 실제 답변**

답변 없음: restore fields require STATE_RESTORE

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-11.json)

### cm-038-chain / 12

사용자: 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '지금 답변이 최종 맞아'라고 명시적으로 최종 확인을 요청하고 '저장해줘'라고 지시했으므로 FINALIZE 명령이 유효합니다. 제안된 CLARIFY 명령은 goals 목록이 비어 있다는 이유로 확인을 요청하고 있으나, 이는 현재 대화 맥락에서 이미 확정된 답변을 저장하는 요청을 잘못 해석한 것입니다. 명시된 자연어 최종 확인·저장 요청이 있으므로 FINALIZE가 적절하며, CLARIFY는 유효하지 않습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-038-chain/turn-12.json)

**수정 후 실제 답변**

답변 없음: 사용자가 '이 질문의 최종 정답 루트를 저장해줘'라고 명시적으로 저장(FINALIZE)을 요청했으나, 제안된 명령은 NEED_TARGET(CLARIFY)로 저장 없이 확인만 하도록 되어 있어 요청과 일치하지 않습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-038-chain/turn-12.json)

### cm-003-chain

| 턴 | 사용자 입력 원문 | 수정 전 | 수정 후 |
|---|---|---|---|
| 1 | 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?<br>(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조) | ERROR / 별도 실행 없음 | READY / INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE |
| 2 | 방금 질문의 재무적투자자는 벤처금융 또는 전문투자자에 해당하는 경우야. 그 자격 조건을 추가해서 다시 판단해줘. | ERROR / 별도 실행 없음 | ERROR / 별도 실행 없음 |
| 3 | 그 정정이 잘못됐어. 최초 질문에 없던 자격 조건을 추가하지 말고 최초 질문 때 조건으로 되돌려줘. | ERROR / 별도 실행 없음 | READY / ASSESS → COMPOSE |
| 4 | 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘. | ERROR / 별도 실행 없음 | STORED / 별도 실행 없음 |
| 5 | 이 질문의 최초 조건과 정정, 다시 최초로 복원한 과정을 실제 기록에 근거해 설명해줘. | CLARIFY / knowledge required | READY / HISTORY_EXPLAIN |
| 6 | 지금 조건과 결론을 유지하고 최종 답변만 표로 써줘. | ERROR / 별도 실행 없음 | READY / COMPOSE |
| 7 | 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?<br>(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조) 이전 대화에서 내가 최종 확인한 경험을 활용해줘. | CLARIFY / 사용자가 '이전 대화에서 내가 최종 확인한 경험'을 활용하라고 명시했으나, 제공된 knowledge 목록이 비어 있어 재사용할 수 있는 저장된 경험 ID가 존재하지 않습니다. 또한 repair_feedback에서 'knowledge required'라고 지적되었으므로, 구체적인 경험 ID를 확인하거나 제공해 줄 것을 요청해야 합니다. | ERROR / 별도 실행 없음 |

### cm-003-chain / 1

사용자: 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?
(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조)

**수정 전 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-003-chain/turn-01.json)

**수정 후 실제 답변**

재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호에 해당합니다. 해당 조항은 '상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자'를 의무보유 대상으로 규정하고 있으며, 의무보유 기간은 상장일부터 6개월(기술성장기업 또는 신속이전기업은 1년)입니다.

반면, 제4호는 '벤처금융 또는 전문투자자'가 모집이나 매출이 아닌 방법으로 취득한 주식에 대해 규정하고 있어, 단순히 '재무적투자자'라는 표현만으로 제4호에 직접 해당한다고 보기 어렵습니다. 따라서 제공된 사실(제3자배정 취득)에 기반할 때 제3호가 적용되는 것이 타당합니다.

다만, 제3호 적용을 위해선 '상장예비심사 신청일 전 1년 이내'에 취득했는지 여부가 충족되어야 하며, 이 사실은 현재 제공된 정보에 명시되어 있지 않아 확인이 불가합니다. 또한 재무적투자자가 '벤처금융 또는 전문투자자'에 해당하는지 여부는 원문에서 정의되지 않아 제4호와의 관계 판단에 한계가 있습니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-003-chain/turn-01.json)

### cm-003-chain / 2

사용자: 방금 질문의 재무적투자자는 벤처금융 또는 전문투자자에 해당하는 경우야. 그 자격 조건을 추가해서 다시 판단해줘.

**수정 전 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-003-chain/turn-02.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-003-chain/turn-02.json)

### cm-003-chain / 3

사용자: 그 정정이 잘못됐어. 최초 질문에 없던 자격 조건을 추가하지 말고 최초 질문 때 조건으로 되돌려줘.

**수정 전 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-003-chain/turn-03.json)

**수정 후 실제 답변**

재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호에 해당하며, 의무보유 기간은 상장일부터 6개월(기술성장기업 또는 신속이전기업은 1년)입니다. 제4호는 '벤처금융 또는 전문투자자'가 모집이나 매출이 아닌 방법으로 취득한 주식에 적용되며, '재무적투자자'라는 용어는 해당 조항에 명시되어 있지 않습니다. 다만, 제3호 적용을 위해선 '상장예비심사 신청일 전 1년 이내'에 취득했는지 여부가 확인되어야 하나, 현재 사실에 취득 시점이 포함되어 있지 않아 기간 요건 충족 여부는 확인 불가합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-003-chain/turn-03.json)

### cm-003-chain / 4

사용자: 지금 답변이 최종 맞아. 이 질문의 최종 정답 루트를 저장해줘.

**수정 전 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-003-chain/turn-04.json)

**수정 후 실제 답변**

재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호에 해당하며, 의무보유 기간은 상장일부터 6개월(기술성장기업 또는 신속이전기업은 1년)입니다. 제4호는 '벤처금융 또는 전문투자자'가 모집이나 매출이 아닌 방법으로 취득한 주식에 적용되며, '재무적투자자'라는 용어는 해당 조항에 명시되어 있지 않습니다. 다만, 제3호 적용을 위해선 '상장예비심사 신청일 전 1년 이내'에 취득했는지 여부가 확인되어야 하나, 현재 사실에 취득 시점이 포함되어 있지 않아 기간 요건 충족 여부는 확인 불가합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-003-chain/turn-04.json)

### cm-003-chain / 5

사용자: 이 질문의 최초 조건과 정정, 다시 최초로 복원한 과정을 실제 기록에 근거해 설명해줘.

**수정 전 실제 답변**

답변 없음: knowledge required

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-003-chain/turn-05.json)

**수정 후 실제 답변**

현재 판단과 실제 수정 이력입니다.

재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호에 해당하며, 의무보유 기간은 상장일부터 6개월(기술성장기업 또는 신속이전기업은 1년)입니다. 제4호는 '벤처금융 또는 전문투자자'가 모집이나 매출이 아닌 방법으로 취득한 주식에 적용되며, '재무적투자자'라는 용어는 해당 조항에 명시되어 있지 않습니다. 다만, 제3호 적용을 위해선 '상장예비심사 신청일 전 1년 이내'에 취득했는지 여부가 확인되어야 하나, 현재 사실에 취득 시점이 포함되어 있지 않아 기간 요건 충족 여부는 확인 불가합니다.

수정 이력:
- [1] 최초 질문: 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?
(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조)
  질문 목적: null → "재무적투자자가 제3자배정으로 취득한 주식의 코스닥시장 상장규정 제26조상 의무보유 대상 구분(제3호 또는 제4호)을 확인한다"
  문서 구분: null → "ALL"
  문서 범위: null → ["3521c3aaa5a735fd"]
  사건 조건: null → [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}]
  검색 계획: null → ["코스닥시장 상장규정 제26조 제3호", "코스닥시장 상장규정 제26조 제4호", "재무적투자자 제3자배정 의무보유"]
  적용 방법: CASE_START — 새 질문의 목적과 조건을 분리한다
- [2] 1차 정정: 방금 질문의 재무적투자자는 벤처금융 또는 전문투자자에 해당하는 경우야. 그 자격 조건을 추가해서 다시 판단해줘.
  사건 조건: [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}] → [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}, {"name": "투자자 자격", "value": "벤처금융 또는 전문투자자"}]
  적용 방법: FACT_UPDATE — 현재 사건 사실만 바꾸고 적용 판단을 다시 확인한다
- [3] 2차 정정: 그 정정이 잘못됐어. 최초 질문에 없던 자격 조건을 추가하지 말고 최초 질문 때 조건으로 되돌려줘.
  사건 조건: [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}, {"name": "투자자 자격", "value": "벤처금융 또는 전문투자자"}] → [{"name": "취득 방식", "value": "제3자배정"}, {"name": "투자자 유형", "value": "재무적투자자"}, {"name": "업무 문맥", "value": "신규상장 의무보유 - 코스닥시장 상장규정 제26조"}]
  기록 [1]의 지정 조건을 복원했습니다.
  적용 방법: STATE_RESTORE — 기록된 특정 이벤트의 조건을 정확히 복원한다

현재 판단의 원문 근거:
- 재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호에 해당하며, 의무보유 기간은 상장일부터 6개월(기술성장기업 또는 신속이전기업은 1년)이다. / article:3e4ab92e38b531a09f6419a9 / 원문: 3. 상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자: 상장일부터 6개월(기술성장기업 또는 제31조제1항에 따른 신속이전기업은 1년으로 한다). 다만, 세칙으로 정하는 경우는 제외한다.
- 제26조 제1항 제4호는 '벤처금융 또는 전문투자자'가 모집이나 매출이 아닌 방법으로 취득한 주식에 대해 적용되며, '재무적투자자'라는 용어는 해당 조항에 명시되어 있지 않다. / article:3e4ab92e38b531a09f6419a9 / 원문: 4. 벤처금융 또는 전문투자자가 모집이나 매출이 아닌 방법으로 취득한 투자기간(상장예비심사 신청일을 기준으로 한다)이 2년 미만인 주식등(벤처금융 또는 전문투자자가 취득한 주식등 중에서 상장신청일 현재 상장신청인의 자본금을 기준으로 각각 100분의 10에 상당하는 한도까지의 주식등으로 한정한다): 상장일부터 1개월. 다만, 세칙으로 정하는 경우는 제외한다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-003-chain/turn-05.json)

### cm-003-chain / 6

사용자: 지금 조건과 결론을 유지하고 최종 답변만 표로 써줘.

**수정 전 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-003-chain/turn-06.json)

**수정 후 실제 답변**

### 판단

1. **제3호 해당 여부**: 재무적투자자가 제3자배정으로 취득한 주식은 코스닥시장 상장규정 제26조 제1항 제3호의 적용 대상에 해당합니다. 다만, 제3호 적용을 위해서는 '상장예비심사 신청일 전 1년 이내'에 취득했어야 한다는 시간 요건이 충족되어야 하며, 현재 확인된 사실에는 취득 시점이 포함되어 있지 않아 해당 요건 충족 여부는 확인이 불가합니다.
2. **제4호 해당 여부**: 제26조 제1항 제4호는 '벤처금융 또는 전문투자자'가 모집이나 매출이 아닌 방법으로 취득한 주식에 대해 적용됩니다. 현재 유효한 사실에는 '재무적투자자'가 '벤처금융 또는 전문투자자'에 해당한다는 자격 조건이 포함되어 있지 않으므로, 원문상 '재무적투자자'라는 용어가 제4호에 명시되어 있지 않다는 점을 고려할 때 제4호 적용을 단정할 수 없습니다.

### 근거

| 구분 | 조항 | 적용 대상 | 의무보유 기간 | 비고 |
| :--- | :--- | :--- | :--- | :--- |
| 제3호 | 제26조 제1항 제3호 | 상장예비심사 신청일 전 1년 이내에 상장신청인이 제3자 배정 방식으로 발행한 주식등을 취득한 자 | 상장일부터 6개월 (기술성장기업 또는 신속이전기업은 1년) | 세칙으로 정하는 경우 제외 |
| 제4호 | 제26조 제1항 제4호 | 벤처금융 또는 전문투자자가 모집이나 매출이 아닌 방법으로 취득한 투자기간이 2년 미만인 주식등 (자본금의 10% 한도) | 상장일부터 1개월 | 세칙으로 정하는 경우 제외 |

### 한계

- 제공된 원문에는 '재무적투자자'라는 용어가 명시적으로 정의되지 않았으며, 제3호와 제4호의 적용 대상 구분 시 '재무적투자자'가 '벤처금융 또는 전문투자자'에 포함되는지 여부는 원문만으로 판단할 수 없다.
- 제3호 적용을 위해선 '상장예비심사 신청일 전 1년 이내'에 취득했는지 여부가 확인되어야 하나, 현재 사실에 취득 시점이 포함되어 있지 않아 기간 요건 충족 여부는 확인 불가하다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-003-chain/turn-06.json)

### cm-003-chain / 7

사용자: 재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?
(업무 문맥: 신규상장 의무보유 - 코스닥시장 상장규정 제26조) 이전 대화에서 내가 최종 확인한 경험을 활용해줘.

**수정 전 실제 답변**

답변 없음: 사용자가 '이전 대화에서 내가 최종 확인한 경험'을 활용하라고 명시했으나, 제공된 knowledge 목록이 비어 있어 재사용할 수 있는 저장된 경험 ID가 존재하지 않습니다. 또한 repair_feedback에서 'knowledge required'라고 지적되었으므로, 구체적인 경험 ID를 확인하거나 제공해 줄 것을 요청해야 합니다.

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/BASELINE/cm-003-chain/turn-07.json)

**수정 후 실제 답변**

답변 없음: ERROR

[입력·응답·그 시점의 DB 상태](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/GUARDED/cm-003-chain/turn-07.json)

## 실패와 미확인 범위

```json
[
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [
      "Kc9d46033ec74923fbafdb387"
    ],
    "actual": []
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "history_does_not_mutate_goal",
    "pass": false,
    "expected": "same goal/route/events",
    "actual": [
      "COMPOSE"
    ]
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "exact_history_event_references",
    "pass": false,
    "expected": [
      1,
      2,
      3,
      4,
      5
    ],
    "actual": []
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
    "turn": 1,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
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
    "turn": 3,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 3,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 4,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "ERROR"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "exact_history_event_references",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 6,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 6,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "BASELINE",
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
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 7,
    "kind": "completion",
    "pass": false,
    "expected": "REUSED",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 1,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 2,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 3,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 4,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 5,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 6,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "exact_history_event_references",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 8,
    "kind": "confirmed_experience_preserved",
    "pass": false,
    "expected": [],
    "actual": []
  },
  {
    "arm": "GUARDED",
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
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 9,
    "kind": "completion",
    "pass": false,
    "expected": "REUSED",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 10,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 11,
    "kind": "restore_exact_facts",
    "pass": false,
    "expected": null,
    "actual": null
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 12,
    "kind": "completion",
    "pass": false,
    "expected": "STORED",
    "actual": "CLARIFY"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-003-chain",
    "turn": 2,
    "kind": "completion",
    "pass": false,
    "expected": "READY",
    "actual": "ERROR"
  },
  {
    "arm": "GUARDED",
    "case_id": "cm-003-chain",
    "turn": 7,
    "kind": "completion",
    "pass": false,
    "expected": "REUSED",
    "actual": "ERROR"
  }
]
```

```json
[
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
      "reason": "제품 답변 없음",
      "judge_called": false
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
      "reason": "제품 답변 없음",
      "judge_called": false
    }
  },
  {
    "arm": "BASELINE",
    "case_id": "cm-003-chain",
    "turn": 5,
    "kind": "history",
    "verdict": {
      "correct": false,
      "reason": "입력된 events와 answer가 모두 비어 있어, 정정 이력을 대조할 수 있는 정보가 없습니다. 요청된 정정 과정을 설명하지 않았으므로 false입니다."
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
    "arm": "GUARDED",
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
    "arm": "GUARDED",
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
    "arm": "GUARDED",
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
    "arm": "GUARDED",
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
    "arm": "GUARDED",
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
    "arm": "GUARDED",
    "case_id": "cm-038-chain",
    "turn": 7,
    "kind": "history",
    "verdict": {
      "correct": false,
      "reason": "입력된 events와 answer가 모두 비어 있어, 정정 이력을 대조할 수 있는 정보가 없습니다. 요청된 정정 과정을 설명하지 않았으므로 false입니다."
    }
  },
  {
    "arm": "GUARDED",
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
    "arm": "GUARDED",
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
    "arm": "GUARDED",
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
    "arm": "GUARDED",
    "case_id": "cm-003-chain",
    "turn": 1,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "기준답은 '시행세칙 제23조 제4항 제2호'를 근거로 제시하여, 재무적투자자(벤처금융 또는 전문투자자)가 제3자배정으로 취득한 주식은 제3호의 단서(세칙으로 정하는 경우)에 해당하여 제3호에서 제외되고 제4호가 적용된다고 결론짓고 있습니다. 그러나 대상 답변은 제3호가 적용된다고 결론짓고 있으며, 기준답의 핵심 근거인 '시행세칙'에 대한 언급이 전혀 없고 결론이 정반대입니다."
    }
  },
  {
    "arm": "GUARDED",
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
    "arm": "GUARDED",
    "case_id": "cm-003-chain",
    "turn": 3,
    "kind": "legal",
    "verdict": {
      "correct": false,
      "reason": "저장 기준답(reference_answer)의 핵심 결론은 '시행세칙 제23조 제4항 제2호에 따라 벤처금융 또는 전문투자자가 취득한 경우 제3호 단서에 해당하여 제3호에서 제외되고 제4호가 적용된다'는 것입니다. 그러나 제공된 답변은 '제3호에 해당하며... 제4호는... 적용되지 않는다(재무적투자자 용어 미명시)'라고 결론짓고 있어, 기준답의 핵심 결론(제4호 적용)과 정면으로 모순됩니다. 또한 기준답에 포함된 필수 단서인 '시행세칙 제23조 제4항 제2호'를 언급하지 않아 필수 단서가 누락되었습니다."
    }
  },
  {
    "arm": "GUARDED",
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

사전 성공 기준의 서술에 재사용 요청을 세 개라고 적었지만, 실제 동결 입력·gold·실행은 arm당 두 개였다. 설명의 숫자 오류를 보존하며 결과를 본 뒤 턴을 추가하거나 점수를 바꾸지 않았다.

조건 복원·이력 설명·경험 보존이 성공해도 법률 판단의 정확성을 보장하지 않는다. 원문 누락, 적용 대상 해석, 예외·참조 연결, 온톨로지의 도메인 적합성은 각각 검증해야 한다.

## 비용·지연과 출처

```json
{
  "usage": {
    "calls": 156,
    "cost_usd": 0.25945028,
    "input_tokens": 766913,
    "output_tokens": 41649,
    "judge_calls": 11
  },
  "arms": {
    "BASELINE": {
      "functional_passed": 12,
      "functional_total": 33,
      "legal_correct": 5,
      "legal_total": 12,
      "history_correct": 1,
      "history_total": 2,
      "completed_turns": 8,
      "turns": 19,
      "calls": 83,
      "cost_usd": 0.13348216,
      "input_tokens": 418388,
      "output_tokens": 18146,
      "latency": {
        "p50": 19.070346087915823,
        "p95": 39.78515829297248
      }
    },
    "GUARDED": {
      "functional_passed": 12,
      "functional_total": 33,
      "legal_correct": 0,
      "legal_total": 12,
      "history_correct": 1,
      "history_total": 2,
      "completed_turns": 5,
      "turns": 19,
      "calls": 62,
      "cost_usd": 0.11983464,
      "input_tokens": 334803,
      "output_tokens": 22212,
      "latency": {
        "p50": 9.88836335297674,
        "p95": 63.124828577041626
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

[실험 결정문](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/README.md) · [동결 설계·계보](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/실험/manifest.json) · [원점수](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/run-001/result.json) · [공개 원문 출처 결속](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0611-cm-memory-method-guards/artifacts/design/source-binding.json)

[수정된 메모리 실행](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0611/method-guarded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py) · [등록된 메모리 방법과 이력 출력](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0611/method-guarded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/memory_methods.py) · [답변 작성·검사 입력](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0611/method-guarded-memory/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/memory_rag.py)

## 실제 실패 원인과 후속 수정 범위

- GUARDED CM038 첫 resolver가 검색어를 무제한 생성해 6,400 출력 토큰 한도에서 잘렸다. 최초 goal이 만들어지지 않아 이후 정정 11턴이 연쇄적으로 막혔다. COMMAND에 배열 길이 제한이 없고 불완전 JSON에 대한 복구가 없었다.
- CM003은 양 arm 모두 상장규정 한 문서만 검색 범위로 선택했다. 시행세칙 제23조를 읽지 못했다. 기준답은 제3호 단서와 시행세칙에 따른 제4호 적용이지만, 수정본은 제3호라는 오답을 반환했다. 원문 인용 검사는 통과해도 누락된 근거까지 검증하지 못한다.
- CM003 조건 정정에서 원문에 없는 인용을 생성했고, ASSESS 단계에는 실패 피드백을 반영하는 복구가 없었다.
- CM003 다른 대화 재사용에서는 모델이 고른 문서 범위가 달라 동일 경험 재사용이 차단됐다. 질문에 언급한 문서와 접근 가능한 검색 범위를 같은 필드로 취급한 것이 원인이다.
- CM003 이력 설명·표 작성은 확인한 경험을 보존하고 실제 이벤트를 사용했다. 하지만 첫 질문과 정정의 법률 판단 실패까지 해결됐다는 의미는 아니다.

이 결과를 본 뒤의 수정·재실험은 ADR0612에서 별도로 예약·동결한다. ADR0611 결과는 변경하지 않는다.

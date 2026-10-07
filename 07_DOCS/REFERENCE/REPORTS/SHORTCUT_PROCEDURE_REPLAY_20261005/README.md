# 조사 절차 직접 실행·예외 판단 실험

**정상적인 조사 절차 재사용에서는 조사용 LLM 호출을 0회로 줄였다. 최종 판단·답변 작성 2회는 유지한다. 공개 법률 질문 3개에서 확인했으며 MAIN은 변경하지 않았다.**

## 무엇을 구현했는가

1. 고정된 7개 단계의 방법은 코드가 선택하고 감사 기록을 남긴다. 방법을 고르기 위한 모델 호출은 없다.
2. 성공한 조사의 명령, 검색 계획, 원문 선택, 참조 선택과 당시의 전체 입력·선택지를 기존 DB에 저장한다.
3. 다음 요청에서는 현재 검색과 원문 읽기를 실제 실행한다. 저장된 선택은 같은 질문·권한·문서 범위·원문/코드/설정 버전·전체 선택지가 맞을 때만 다시 적용한다.
4. 예상과 다르면 해당 단계에서 모델이 판단한다. 예상/실제 입력, 바뀐 지점, 모델의 선택과 이유를 별도 이력으로 남긴다.
5. 원문과 답변 검증 및 게시가 끝난 조사만 재사용 가능해진다. 중단된 조사와 미완성 기록도 보존하지만 재사용 활성화는 하지 않는다.
6. 최종 법률 판단과 답변은 현재 원문으로 새로 생성한다. 과거 답변을 복사하거나 법률적 정답으로 자동 승인하지 않는다.

정본은 기존 사건 DB의 `sw_procedure_step`, `sw_procedure_activation`, `sw_procedure_event`다. 실행 순서는 기존 v6가 소유하고, 저장된 단계 선택을 원래 검증기·도구 실행 경로에 돌려준다. 별도 운영 실행기나 새 필수 위키는 만들지 않았다.

## 실제 재사용 결과

| 사례 | 기록 | 모델 호출 | 요청 시간 | 원문 기준 답변 평가 |
|---|---|---:|---:|---|
| 개인정보 정의 | ADR-0646 | 2회 | 17.8초 | 두 평가 모두 통과 |
| 정보공개 원칙 | ADR-0646 | 2회 | 7.4초 | 두 평가 모두 통과 |
| 상법 적용 순서 | ADR-0648 | 2회 | 42.6초 | 두 평가 모두 통과 |

세 사례의 **조사 과정 모델 호출은 0회**, 남은 2회는 `memory-assess`, `memory-compose`다. 평가에는 실제 모델을 사용했고, 각 답변은 고정 원문/루브릭에 따른 두 차례 판정을 모두 통과했다. 전문가의 법률 검증이나 현행 법령 전체의 정확도 인증은 아니다.

개인정보·정보공개는 같은 프로세스의 새 세션, 상법은 일관된 DB 백업을 읽은 **새 프로세스와 새 세션**이다. 상법42.6초에는 검색 자원 초기화가 포함된다. 이 시간들을 하나의 동등 조건 지연 비교로 합산하지 않는다. 속도 차이에는 초기화·캐시 효과도 포함되며, 모델 호출 감소는 실제 호출 기록으로 확인했다.

## 예상 이탈 검증

공개 합성 준용관계의 현재 선택지를 실제 모델에 제공한 별도 실험이다. 실제 법률의 복잡한 준용 사슬 전체를 검증한 것으로 확대하지 않는다.

| 상황 | 절차 판단 모델 호출 | 실제 처리 |
|---|---:|---|
| 최초 조사 | 1회 | 선택과 이유 저장 |
| 같은 원문·같은 준용 대상 | 0회 | 저장 선택 적용 |
| 준용 대상 변경 | 1회 | 새 대상을 선택하고 이력 보존 |
| 데이터 세대 변경 | 1회 | 현재 입력으로 재판단 |
| 질문 변경 | 1회 | 새 질문에 맞게 판단 |

권한·문서 범위·메뉴 변경, 손상된 기록, 실패 기록 비활성화, 정정, 프로세스 장애·복구 등을 포함한 계약 검사 **80개 통과**. 동일 제품 코드로 재시작 실험까지 확인했다.

## 남은 문제와 MAIN을 유지한 이유

상법의 **최초 조사**에서 기존 v6와 후보 모두 원문 선별 모델이 빈 선택을 반환해 중단된 사례가 있다. 후속 성공 조사 이후에는 절차를 재사용해2회만 호출했지만, 이것으로 최초 실패가 해결됐다고 보지 않는다. 실패한5회와 이후 성공한6회의 학습 비용도 보존했다.

현재 재사용은 **동일 입력 계약**에 대한 보수적인 구현이다. 다른 표현을 같은 법률 쟁점으로 일반화하거나, 새로운 매개변수에 자동 적용하는 기능까지 완성한 것은 아니다. 예상이 달라지거나 저장된 절차가 없으면 기존 모델 조사로 돌아간다.

알려진3사례의 probe이고 독립 holdout이 아니므로 운영 품질·일반화·GENOS 성능은 미확인이다. 활성 MAIN은 `legal-agent-source-prefix-20260930-r3` 그대로이며, 운영 DB·Git main·GENOS 배포도 바꾸지 않았다.

## 실패를 포함한 실험 계보

- [ADR-0645](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0645-shortcut-deterministic-procedure/README.md): 첫 후보. fulltext 강제로 탐색 범위가 넓어졌고 최초 조사 실패. 정상 재사용2회는 확인.
- [ADR-0646](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0646-shortcut-preserve-discovery-route/README.md): 기존 탐색 경로를 보존한 제품 후보. 최초 선별 실패가 기존 v6에서도 재현. 두 사례의 정상 재사용 확인.
- [ADR-0647](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0647-shortcut-confirmed-procedure-replay/README.md): 실험용 DB 사본에서 완료 기록이 빠져 재사용 전제 불충족. 새 조사6회를 재사용 성공으로 세지 않았다.
- [ADR-0648](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0648-shortcut-consistent-seed-replay/README.md): SQLite backup으로 완료 기록까지 포함하고 활성 절차 존재를 사전 확인. 같은 제품 코드로 상법 재사용2회·답변 평가 통과.

ADR-0645·0646·0648의 개별 최종 검사 통과. ADR-0647에는 완료 후 확인된 메타데이터 오류(unchanged retrieval reason 누락)가 남아 있으며, 완료 기록을 덮어쓰지 않았다. [전체 계보 검사](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0648-shortcut-consistent-seed-replay/artifacts/graph-validation.txt)에는 별도의 기존 오류가 남아 있어 전체 기록 검사 통과로 보고하지 않는다.

## 코드와 실제 저장 예

- [저장·대조·이탈 기록 구현](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0648/procedure/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/procedure_memory.py)
- [기존 실행 경로에 재사용 연결](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0648/procedure/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/wiki_execution.py)
- [실제로 저장된 개인정보 조사 절차](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0646-shortcut-preserve-discovery-route/artifacts/procedure-example.json)
- [상법 재시작 후 실제 호출·평가 결과](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0648-shortcut-consistent-seed-replay/artifacts/run-001/result.json)
- [보고서 수치·한계 정본](RESULTS.json)

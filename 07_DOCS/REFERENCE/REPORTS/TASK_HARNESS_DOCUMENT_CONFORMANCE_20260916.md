# 작업 하네스 — 설계·구현 정합성 검토

검토일: 2026-09-16. **판정: 수정 필요. 연결 구조는 상당 부분 구현했지만, 문서의 핵심 처리 흐름을 충족했다고 판단할 수 없다.** 특히 의미 단위의 후보 검토, 실패 후 수정 재시도, 실제 진척 판단에 확인된 결함이 있다. 임의의 구현률·정합성 점수는 산정하지 않았다.

이 검토는 구현 작성자의 **자체 검토**다. 독립 에이전트·외부 전문가 검증이 아니다. 원본 설계·제품 코드·활성 릴리스를 수정하지 않았으며, 새 모델 실험이나 배포도 하지 않았다. 기존 모의 계약 테스트와 추가 결정적 반례 검사만 실행했다.

## 대상과 버전

- 상위 요구: 사용자 설명의 6개 항목. 온톨로지는 공통 의미·제약, 하네스는 상태·허용 행동·예산·완료를 소유하고, 같은 작업 유형의 확인 의무를 재사용하며, 기존 RAG 도구를 연결하고, 의미 단위 수집·후보 검토·탐색 진척을 보완한다. 첫 범위는 개념 정의와 적용 범위 설명이다.
- [구현 전 연결 설계](/home/jin/8-AGENT/07_DOCS/REFERENCE/REPORTS/RAG_TASK_HARNESS_FIT_20260916.md), [후속 운영 문서](/home/jin/8-AGENT/07_DOCS/REFERENCE/OPERATIONS/TASK_HARNESS.md), [전체 아키텍처](/home/jin/8-AGENT/00_SYSTEM/ARCHITECTURE.md)를 대조했다. 구현 전 설계의 “미구현·미실험”은 작성 당시 상태이며, 후속 실패 기록을 무시한 현재 상태 주장으로 해석하지 않았다.
- 검토한 현재 task_harness/task_policy/adapter/navigation_match 및 관련 실행·스키마 11개 파일은 ADR0438 frozen rev-001의 바이트와 일치한다. 따라서 ADR0438·ADR0440의 실행 실패를 현재 같은 코드의 증거로 사용할 수 있다.
- 선택된 로컬 활성 포인터는 `navigation-rag-20260916-v1`, generation 14이며 릴리스 manifest 해시도 일치한다. 작업 코드의 후보와 실제 선택된 릴리스를 구분했다. GENOS 접근·현장 실행은 하지 않았다.
- 파일별 SHA-256, 검토 시각, 관련 실험 ID와 관측 재계산은 [근거 명세](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/20260916-task-harness-document-conformance/evidence-manifest.json)에 고정했다. 이후 수정본은 해당 해시와 구분해서 재검토해야 한다.

## 요구사항별 정합성

| 요구사항 | 직접 확인한 구현 | 판정 |
|---|---|---|
| 원문·좌표·버전·해시 재사용 | 기존 Store, TermIndex, glossary_assets, ReverseMatcher 및 navigation 도구 호출. query/generation/source hash와 정책 binding을 provenance에 기록 | 정합 |
| 온톨로지의 공통 의미·범위·미확인 구분 | 원천별 정의·관계와 미승인 표시, 범위 필터·원문 검토는 재사용. 새 공통 의미·관계 제약 엔진은 없고 모델 판단에 의존. 문서명/목표 개념 구분도 없음 | 부분 정합. 현행 용어집을 완성된 의미 제약 엔진이라고 부르면 과장 |
| 하네스가 상태·허용 행동·예산·완료 소유 | TaskSession이 의무 ID/문장을 고정하고 모델 actions를 검증. 해석·탐색·근거검토 호출 예산을 합산 | 정합. 실제 완료정책 적합성과 진척 계산은 별도 문제 |
| 같은 작업 유형에 같은 확인 의무 적용 | definition_scope의 definition/requirements/exceptions 고정 3개 | 첫 단일 유형 범위에서는 정합. 일반 작업 유형 생성기는 아님 |
| 작업 정의·도구 계약·전이를 DB로 관리 | SQLite 정의·검토 영수증·버전·해시 고정, 제안/검토/게시 CLI 연결. 예산·의무 문장·EXPLORING 허용 도구 부분집합은 DB 설정 | 부분 정합. 도구 계약은 코드와 동일한 설명 문자열만 허용, args 검사는 코드에 분산. 완료 연산·전체 상태 전이·오류 정책은 고정 코드 |
| 의미 단위를 보존하고 후보를 실질 검토 | 질문 원문 span 보존, OPEN_TERM/READ 후 CONCEPT 결정 장치 존재 | 불충족 사례 확인. 문서명 부분 매칭 후보가 상한에 걸려 목표 개념 검토 전에 종료: DR-H01 |
| 오류를 알려 수정하고 탐색 진척 관리 | 오류 trace·상한·재시도·NO_PROGRESS 존재 | 불충족 사례 확인. 해석 오류는 다음 입력에 없고, 진척은 실제 상태 변화가 아닌 행동 인자 지문 위주: DR-H02/03 |
| 근거의 의미 적합성과 미확인 표시 | 인용 검증 뒤 별도 모델 review, UNKNOWN/CONFLICT 기록, 일부 검토 완료 의무의 근거는 부분 답변에 남길 수 있음 | 부분 정합. 범위 밖 한계까지 무조건 차단하는 정책은 상위의 한정 답변 요구와 조정 필요: DR-H04 |
| 내부 TaskSpec/TaskState/ConstraintResult 계약 | spec/state dict, 모델 출력용 3종 JSON Schema와 정책 수동 검증 존재 | 부분 정합. 제안된 내부 상태 독립 스키마·구조화된 제약 판정 계약은 미구현: DR-H05 |
| 기존 retrieve/select/assemble/answer·피드백 연결 | 명시 implementation 선택 → adapter → selected_ids/findings → 기존 출력. 피드백이 run 파일 해시와 query/source 세대를 참조 | 정합. 사용자 피드백과 의무별 검토의 연결은 run 파일을 통한 간접 연결 |
| 실패·미정의 사항을 검토 후보로 저장 | checkpoint와 TASK_IMPROVEMENT proposal을 함께 저장. PROPOSED, canonical_approval=false | 정합. 운영 검토·반영 자동화까지 구현한 것은 아님 |
| 복구·재개·권한·외부 작업 확장 | 요청 안의 제한 재시도와 checkpoint만 있음. resume API, 권한 변경 재검사, 외부 실행·중복 방지는 없음 | 문서가 이미 미구현/후속 범위로 명시. 새 문서 오류로 집계하지 않음 |

실제 후보 경로는 `Pipeline.__init__`의 명시 선택 → `ServingTaskHarnessAgent.retrieve` → `TaskSession.run` → 기존 select/assemble/answer다. 앱은 실행 journal을 주입하고 하네스에서는 기존 잔여 문자열 학습 수집을 제외한다. 정상 모의 HTTP 경로에서 답변·피드백·journal 연결까지 확인했다. 실제 선택된 로컬 릴리스는 `service.application`이 별도 코드 패키지로 로드하므로 작업 파일 수정만으로 활성화되지 않는다.

## 발견사항

| ID | 심각도 | 주장/위치 | 직접 근거 | 영향·필요한 보완 | 문서 반영 상태 | 구현·검증 해결 상태 |
|---|---|---|---|---|---|---|
| DR-H01 | 높음 | 의미 단위 보존과 실질 후보 검토 | [interpret](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:123)에서 모든 label을 부분문자열 matcher로 보내고 후보24개 즉시 ASK_USER. ADR0440 설명6개 모두 이 경로 | 문서 범위와 설명 대상 개념을 구분하고, 후보 과다를 곧 사용자 정보 부족으로 보지 말 것. 목표 후보의 관련성 검토·추가 탐색을 먼저 수행 | 운영 문서와 ADR0440에 실패가 이미 기재됨 | 미해결. 원문 읽기0/6 |
| DR-H02 | 높음 | 구조화 오류에 근거한 제한 재시도 | [interpret 입력](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:110)은 question/initial뿐. 오류는 [last에 저장](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:328)하지만 INTERPRETING 재호출에서는 사용하지 않음. 잘못된 span 3회 재시도 입력 해시 동일 | 실제 수정 근거가 없는 반복. 이전 잘못된 해석과 오류를 해석기 입력에 전달하고, 문자열 위치 확정 책임을 모델에 과도하게 맡기지 않을 것 | 운영 문서에 동일 요청 반복 실패는 기재. 요청 내 복구 설명은 단계별 제한 필요 | 미해결. 이번 계약 반례로 재확인 |
| DR-H03a | 높음 | 실제 후보 검토를 진척으로 인정 | [진척 계산](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:304)은 CONCEPT를 전부 제외. 이미 읽은 서로 다른 후보4개를 각1회 선택/제외하면 기본 상한4에서 NO_PROGRESS | 정상 검토를 완료 직전에 끊음. uncertain→selected/rejected 같은 유효 상태 전이를 진척으로 계산하고 동일 상태 반복만 제외 | 새 발견. 기존 문서의 진척 설명으로는 드러나지 않음 | 미해결. 4개 유효 결정 후 중단 재현 |
| DR-H03b | 중간 | 결과 지문과 의무 상태로 중복 탐색 판별 | 같은 줄의 지문은 result가 아닌 tool/args. LIST의 생략 가능한 기본 옵션만 다른6호출은 결과가 완전히 동일해도 모두 새 진척 | 같은 정보 반복을 숨김. 기본 인자 정규화, 결과/확보 근거/의무 상태 변화 기반으로 판별 | 새 발견. 설계의 “결과 지문과 의무 상태”와 다름 | 미해결. 결과 지문1개, no_progress=0, 총 예산까지 소모 재현 |
| DR-H04 | 중간 | 확인한 범위를 설명하고 범위 밖 사항은 미확인으로 남김 | [review 채택](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:180)은 SUPPORTED·scope_checked=true여도 limitations가 하나라도 있으면 deferred. [완료](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:206)는 모든 의무 REVIEWED·미해결0 요구 | “범위 밖 세부 요건 미확인”과 “결론을 지지하지 못하는 미확인”을 구분할 수 없음. 필수 미충족과 허용된 범위 한계를 별도 계약으로 정할 필요 | 운영 문서는 현 코드의 엄격 조건을 정확히 명시. 상위 요구·실험의 한정 답변 허용과 정책 정합성 조정 필요 | 차단 동작 재현. 임의 한계가 붙으면 항상 통과시켜야 한다는 뜻은 아님. 설계 정책 보완 필요 |
| DR-H05 | 중간 | 내부 상태 독립 스키마·제약 결과 계약 | [TaskSpec 생성](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:69), [TaskState 출력](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/task_harness.py:239)은 dict. 외부 [term_agent](/home/jin/8-AGENT/00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json:184)는 object만 검사. ConstraintResult에 해당하는 ID/버전/PASS·FAIL·UNKNOWN/허용 후속 행동 통합 계약 없음 | 상태 소비자·향후 재개/DB 정의 확대 때 구조적 오류를 검출할 계약 부족. 기존 출력 외형을 유지하면서 내부 버전 스키마와 제약 판정 기록을 추가할 필요 | 연결 설계가 권고한 부분이 구현 문서에 충분히 구분되지 않음 | 미구현. 이것만으로 실제 잘못된 답변이 발생했다고 단정하지 않음 |

DR-H04는 “미확인이 있으면 답변을 전혀 못 한다”는 주장이 아니다. 다른 의무에 이미 채택된 근거는 부분 답변으로 출력할 수 있다. 문제는 범위 밖 한계가 기록된 해당 근거까지 일괄 보류하고, 한계를 명시한 유효 답변을 정상 완료로 구분할 계약이 없다는 점이다.

DB 설정의 제한도 첫 구현의 단일 작업 범위를 고려해야 한다. 새 도구 연산에 코드가 필요한 것은 상위 문서와 일치한다. 다만 지금 구현을 범용 DB 기반 작업 엔진·전체 상태 전이 정의기로 설명해서는 안 된다.

## 검증과 수치의 의미

| 항목 | 분류·분모 | 확인 결과 | 해석 한계 |
|---|---|---|---|
| 기존 하네스 계약·HTTP 연결 테스트 | 이번 로컬 검사22개 | 22 passed, 기존 Starlette/httpx deprecation warning1개 | 모의 모델의 정해진 행동에 대한 검사. 실제 질문 품질 통과가 아님 |
| 추가 반례 검사 | 네트워크 없는 결정적 검사4개 | DR-H02, DR-H03a, DR-H03b, DR-H04 동작 재현 | 결함/정책 제한을 확인하는 검사이며 “기능4개 성공”으로 세지 않음 |
| ADR0438 하네스 | 과거 관측, 설명6개 + 보호2개 | 설명 FINISH0/6, 원문 읽기0/6, 제품22호출 | 현재 코드와 동결 코드 해시 일치 확인. 과거 단회 자동 채점의 보호 질문 오판은 재사용하지 않음 |
| ADR0440 상향 모델 | 과거 관측, 동일 설명6개 + 보호2개 | 설명 FINISH0/6, 원문 읽기0/6, 제품8호출. 설명6개 span 일치 후 후보24개로 중단 | 동일6질문이므로 ADR0438과 합쳐 독립 표본12개로 보지 않음 |
| 정확도·비용 개선 및 운영 품질 | 미확인 | 성공 요청이 없어 정상 완료 기준 개선을 입증하지 못함 | 조기 종료로 호출이 줄어든 것을 효율 개선으로 해석하지 않음 |

[테스트 로그](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/20260916-task-harness-document-conformance/pytest.log), [반례 기록](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/20260916-task-harness-document-conformance/contract-observations.json), [재현 코드](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/20260916-task-harness-document-conformance/check_contracts.py)를 보존했다. 추가 반례의 후보 검토 검사는 “이미 원문/정의를 전달받은 후보4개” 상태를 모의로 구성해 이후 진척 판정만 확인했다.

이번 검토는 실험·배포가 아니므로 새 ADR이나 MAIN 승격을 수행하지 않았다. 원본 설계의 외부 사례·정량 예상치를 원용하지 않았고, 새로운 웹 자료나 법률 해석을 검증한 것도 아니다. 권한 변경·다중 프로세스 동시 checkpoint·프로세스 재시작 복구는 새로 실행하지 않았다. 문서에 이미 미구현이라고 적힌 항목은 해결된 것으로도, 새 문서 결함으로도 세지 않았다.

## 수정 우선순위와 해결 확인

1. DR-H01/02: 문서 범위와 목표 개념을 분리하고, 실제 해석 오류를 다음 시도에 전달. 같은 공개 사례에서 관련 후보 검토와 원문 읽기까지 도달하는지 확인.
2. DR-H03: 유효 후보 결정·새 근거·의무 변화는 진척, 기본 옵션 표기만 다른 동일 결과는 무진척으로 판별. 위 반례가 더 이상 발생하지 않는지 계약 검사.
3. DR-H04: 허용된 범위 밖 미확인과 필수 근거 부족을 명세에서 구분. 제한된 범위의 답변 완료와 잘못된 단정 차단을 함께 검증.
4. DR-H05: 내부 상태·제약 판정 스키마를 추가하고 기존 adapter·journal·feedback 소비자를 함께 확인.
5. 수정본은 새 해시·새 ADR로 검증하고, 기존 질문뿐 아니라 분리된 질문으로도 확인. 문서에 문제를 적었다는 이유로 이 발견사항을 해결 처리하지 말 것.

현재 구현을 정확히 부르면 **기존 RAG에 연결된 단일 작업 하네스 초안**이다. 상태·검토·예산의 기반은 있으나, 사용자가 의도한 요청 해석 → 실질 후보 검토 → 원문 확인 → 적절한 완료 흐름은 아직 충족하지 못했다.

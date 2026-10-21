# CM 법률 지식 데이터와 실행 계약

이 문서는 온톨로지·Legal Wiki·숏컷을 기존 조사 실행기에 연결하기 위한 구현 계약 제안이다. 모든 새 타입·버전·연산·테이블 이름은 제안이며 현행 API나 DB에 이미 존재하는 것으로 해석하지 않는다. 설명에 사용하는 `demo:` ID는 실제 법률 지식이나 배포 식별자가 아니다.

JSON은 핵심 필드만 보인 축약 예시다. 완전한 실행 페이로드나 JSON Schema 인증 사례가 아니며, 실제 구현에서는 공통 참조·권한·버전 필드를 조립한 뒤 별도 버전 스키마로 검사한다.

[전체 설계](README.md) · [질문 대응표](QUESTION_REQUIREMENTS.tsv)

## 공통 식별자와 범위

공통 참조는 `kind, id, revision, content_hash`다. 객체 ID는 표시 이름·질문 문장·특정 도구명과 분리한다. 동일 여부가 검토되지 않은 기존 객체를 이름만으로 병합하지 않는다.

| 공통 항목 | 계약 |
|---|---|
| schema_version | 소비 가능한 버전 명시. 신규 필드를 기존 승인 계약에 몰래 추가하지 않음 |
| id / revision | 서버가 발급·증가. revision 내용은 불변 |
| content_hash | canonical serialization의 hash. 서버가 계산 |
| source_refs | 문서 계열·판본·좌표·본문 hash 또는 기존 근거 식별자 |
| origin_refs | 원 사건·발언·후보·검토 기록. 원문 근거와 구분 |
| scope | 업무·상품·주체 역할·행위·단계·관할·기준시점·문서 범위 |
| review | 검토 상태·책임자·근거·결정 revision. 사용자가 화면에서 매번 입력하는 메타데이터는 아님 |
| lifecycle | 초안·게시·사용 중지 등 사용 상태 |
| dependencies | 의존 객체의 ID·revision·hash와 의존 역할 |
| visibility | 서버가 계산하는 접근 범위. 클라이언트가 권한을 넓힐 수 없음 |

`scope`의 각 차원은 `UNSPECIFIED`, `ANY_REVIEWED`, `VALUES`를 구분한다. 빈 배열을 모든 업무에 적용된다는 뜻으로 사용하지 않는다. 범용 방법에 허용된 ANY와 범위가 아직 모르는 지식의 UNSPECIFIED는 다르다.

법률상 적용 시점과 시스템에 기록한 시점은 별도다. `effective_from/effective_to`는 근거로 확인한 효력 기간이고 `recorded_at`은 시스템 기록 시각이다. 특정 과거 시점 질의는 해당 판본을 선택한다. 시점 미확인은 현재판의 효력을 과거로 확장하는 근거가 아니다.

객체 lifecycle, 근거 현재성, 의미 검토, 이번 요청에서의 적용 가능성을 하나의 `APPROVED` 값으로 합치지 않는다.

여러 근거를 묶은 주장·방법 적용은 필요한 모든 근거에 대한 접근권한을 충족해야 한다. 화면의 연결 개수·제목·영향 목록에서도 권한 밖의 자료를 노출하지 않는다. 공유 가능한 일반 방법과 제한된 사건 사실은 분리하고, 사용 사례가 공통 방법에 연결됐다고 사례 본문까지 공개하지 않는다.

## 입력 항목

제안 타입은 `review-field-v1`이다. 입력 항목은 값의 의미와 표현 계약이며 사건의 실제 값을 담지 않는다.

| 필드 | 필요 | 의미 |
|---|---|---|
| concept_ref / definition_refs | 예 | 기존 개념과 범위 있는 정의 연결 |
| label / description | 예 | 현업 표시와 의미 |
| value_type | 예 | boolean, enum, decimal, money, ratio, date, duration, entity_ref, text |
| dimension | 수치형 | 통화·시간·비율 등의 차원과 허용 단위 |
| legal_purpose | 예 | 값을 사용하는 검토 목적. 예: 신용위험 측정과 전결 판단 구분 |
| scope | 예 | 그 정의가 적용되는 업무·문서·판본 범위 |
| allowed_origins | 예 | 사용자 진술, 원문 명시, 코드 계산, 모델 제안 등 허용 출처 |
| normalization | 선택 | 의미를 바꾸지 않는 허용 표기 정규화 |
| equivalence_refs | 선택 | 다른 입력과의 동일성·변환을 뒷받침하는 검토된 관계 |

동일한 “금액”이라는 이름만으로 필드를 합치지 않는다. `신규 거래금액`, `기존 명목 익스포져`, `위험조정 익스포져`, `전결 판단금액`은 서로 다른 역할일 수 있다. 공통 상위 개념을 연결할 수 있지만 값 대체에는 구체 관계가 필요하다.

금액은 십진 문자열과 통화로 전달한다. 이진 부동소수점 반올림을 기본값으로 쓰지 않는다. ‘억’ 표기는 정규화 계약에 따라 바꾸되 원래 표현을 남긴다. 다른 통화 환산에는 출처·시점이 있는 환율이 필요하다. 기간을 날짜로 바꾸는 휴일·말일·기산일·초일 산입 정책은 별도 근거가 없으면 추측하지 않는다.

현재 사건의 값은 다음처럼 기존 fact에 연결한다. 아래는 형식 예시다.

```json
{
  "schema_version": "review-fact-binding-v1",
  "field_ref": {"id": "demo:new_amount", "revision": 1},
  "value": {"type": "money", "decimal": "30000000000", "currency": "KRW"},
  "status": "ASSERTED",
  "origin": {"kind": "USER", "event_ref": "demo:event", "quote_ref": "demo:quote"},
  "fact_ref": {"id": "demo:fact", "revision": 1}
}
```

`ASSERTED`는 사용자 진술로 주어진 값이라는 뜻이다. 사실·법률 검증을 통과했다는 뜻이 아니다. 조건부 답변에서 사용자 가정으로 사용할 수 있으나 이를 원문 근거로 바꾸지 않는다. 모델이 추정한 값은 제안 상태로 유지하고 자동 생략·수치 계산의 확정 입력에 넣지 않는다.

## 검토 방법

제안 타입은 `review-method-v1`이다. 일반적인 조사 방법과 업무별 적용을 분리한다.

| 필드 | 계약 |
|---|---|
| purpose | LOOKUP 등 방법 코드와 현업 설명 |
| requested_outputs | 이 방법이 제공할 수 있는 결과의 타입·의미 |
| inputs | 입력 ID, 용도, 필요한 시점, 미확인 시 행동 |
| evidence_needs | 필요한 근거의 역할. 정의·본문·예외·별첨·과거판 등을 구분 |
| steps | 목적·입출력·선행 항목·발동 조건·필요 능력·결과 계약 |
| policies | 우선순위 감소, 조건부 생략, 근거 사용 제한, 다시 조사할 조건 |
| completion | 수행한 작업·확보 범위·의미 판단의 별도 상태 계약 |
| supported_contexts | 검토 가능한 업무 범위 또는 범용 방법이라는 검토된 표시 |
| example_case_refs | 설계·미리보기용 질문 ID. 런타임 정답·프롬프트 입력이 아님 |

입력의 필요 시점은 `BEFORE_CALCULATION`, `BEFORE_REUSE`, `FOR_FINAL_APPLICATION`, `OPTIONAL_HINT`처럼 용도로 표현한다. 필수 입력이 없다는 이유로 모든 원문 읽기를 막지 않는다.

step은 특정 tool 함수명을 담지 않는다. `LOCATE_SOURCE`, `READ_SOURCE`, `FOLLOW_EXPLICIT_REFERENCE`, `ENUMERATE_SCOPE`, `READ_VERSION_CHAIN`, `EVALUATE_TYPED_EXPRESSION` 같은 필요한 능력을 요청한다. 실제 함수·인자·schema hash는 에이전트 어댑터가 책임진다.

원문을 읽어야 다음 분기가 결정되는 방법은 허용한다. 모든 분기를 질문 해석 단계에서 확정하도록 요구하지 않는다. 이미 결정된 도구 인자와 행위만 코드가 수행하며, 의미 선택이 필요한 부분은 기존 판단 지점으로 전달한다.

## 업무별 적용

제안 타입은 `review-application-v1`이다. “어떤 업무의 어떤 질문에 어느 방법을 어떤 지식으로 연결할지”를 표현한다.

| 필드 | 계약 |
|---|---|
| context_scope | 업무·상품·주체·행위·단계·판본 범위 |
| purpose_refs | 적용되는 검토 목적 |
| method_refs | 사용할 방법의 고정 revision |
| input_bindings | 업무상 값과 방법의 입력 연결 |
| evidence_bindings | 근거 요구를 채우는 Wiki·원문 경로 |
| output_bindings | 방법 결과를 다음 검토 항목과 연결 |
| applicability | 적용 조건과 그 근거. 미확인 처리 명시 |
| variants | 공통 적용의 명시적 변형·예외. 부모의 법적 효력을 자동 상속하지 않음 |
| restrictions | 적용·생략·전환의 제한 및 근거 |

내용이 겹친 적용 항목은 게시 시 충돌 대상으로 보여준다. 법률상 우선순위를 생성 시각·조회 순위·작성자 직급으로 결정하지 않는다. 기계적으로 함께 적용할 수 없는 두 게시 항목은 자동 적용을 보류하고 해당 지식을 탐색 단서로만 제공한다. 이 제한은 충돌한 항목에만 적용한다.

공통 방법과 업무 적용을 잇는 예시는 다음과 같다. 실제 준칙이나 계산식을 확정한 데이터는 아니다.

```json
{
  "schema_version": "review-application-v1",
  "id": "demo:amount_review",
  "revision": 1,
  "context_scope": {"business": {"mode": "VALUES", "values": ["demo:business"]}},
  "method_refs": [{"id": "demo:quantity_review", "revision": 1}],
  "input_bindings": [
    {"target": "demo:quantity_input", "source_field": "demo:new_amount", "relation": "EXPLICIT_BINDING"}
  ],
  "evidence_bindings": [
    {"need": "demo:calculation_basis", "wiki_ref": {"id": "demo:wiki", "revision": 1}}
  ],
  "unknown_policy": "CONTINUE_SOURCE_RESEARCH",
  "lifecycle": "DRAFT"
}
```

## 조건과 계산

제안 조건 계약은 `review-expression-v1`이다. 기존 `reuse_policy.condition()`의 연산을 제자리에서 다른 의미로 바꾸지 않고 버전을 추가한다.

| 연산군 | 허용 내용 | 제약 |
|---|---|---|
| 논리 | all, any, not | 길이·깊이 한도는 선택 profile에 결속 |
| 동등·집합 | eq, in | 의미가 같은 타입·범위만 비교 |
| 수치 비교 | lt, lte, gt, gte | 차원·단위 일치, 근거 있는 기준값 |
| 산술 | add, subtract, multiply, divide | 입력·출력 차원 검사, 0 나눗셈은 계산 미완 |
| 날짜·기간 | before, after, duration_compare | 달력 연산 정책이 없는 상태에서 일수 추측 금지 |
| 표 참조 | lookup_row | 특정 판본의 완전한 키·조건을 가진 표에 한정 |

초기 역산은 검토된 식의 변수 대입과 명시적 단순 역산식에 한정한다. 일반 수식 해석기나 법률 규칙 전체의 자동 정리 증명을 전제로 두지 않는다. 지원하지 않는 식은 설명과 원문으로 넘기며 수치를 만들지 않는다.

연산 결과는 `TRUE`, `FALSE`, `UNKNOWN`과 입력·근거·버전·계산식을 담은 receipt다. `CONFLICT`는 상충하는 값/근거의 별도 상태로 유지하며 비교값을 임의 선택하지 않는다. 조건 실행은 conflict를 자동 적용 불가로 취급하고 양측을 기존 판단에 전달한다.

`not UNKNOWN`은 UNKNOWN이다. `all`은 확정 FALSE가 있으면 FALSE, 모두 TRUE면 TRUE, 나머지는 UNKNOWN이다. `any`는 확정 TRUE가 있으면 TRUE, 모두 FALSE면 FALSE, 나머지는 UNKNOWN이다. 이 계산과 별개로 원래 입력의 충돌 표시는 보존한다. 결과 FALSE를 “자료가 존재하지 않음” 또는 “법률상 금지”로 재해석하지 않는다.

AST에는 필드 참조·검토된 상수·연산만 허용한다. 임의 Python/SQL/JavaScript·네트워크 호출·파일 접근을 넣지 않는다. 원문이나 모델 출력이 실행 가능한 코드가 되지 않는다.

동일 값이 들어와도 적용 목적·범위가 다르면 그 receipt를 재사용하지 않는다. 정확 일치 여부는 현재 사실 revision, 식 revision, 근거 revision, 의미 범위와 단위로 계산한다.

## 제외와 재조사

| 정책 | 실행 효과 | 미확인 시 |
|---|---|---|
| DEPRIORITIZE | 후보 순위 낮춤 | 조사 가능성은 유지 |
| SKIP_CHECK | 특정 검토 항목만 생략 | 해당 항목 생략하지 않음 |
| RESTRICT_SUPPORT | 특정 주장에 단독/최종 근거로 쓰는 범위 제한 | 원문·참고 정보는 별도 역할로 유지 |
| REOPEN_CHECK | 생략했던 항목 또는 종료된 탐색 재개 | 실제 새로운 근거·조건 변화가 있는지 기존 상태로 확인 |

접근 차단은 지식의 임의 정책이 아니라 기존 권한 계층의 책임이다. 현업이 작성한 업무 규칙으로 접근권한을 넓히지 못한다.

SKIP_CHECK에는 조건·대상 항목·적용 범위·근거·재조사 조건이 필요하다. “이번 질문에 안 썼다”는 관측만으로 생성하지 않는다. 누락된 Wiki, 검색 0건, 도구 실패는 부정 사실이나 생략 조건을 충족하지 않는다.

REOPEN_CHECK는 기존 누적 deadline·예산·실패 이력을 이어받는다. 표시 이름·이유 문구가 달라졌다는 이유로 새로운 작업으로 계산하지 않는다.

## Legal Wiki 확장 계약

제안은 `legal-wiki-review-links-v1`이며 기존 Wiki의 내용을 새 테이블에 복제하지 않는다. 새 Wiki revision에 참조 필드를 추가하고 실행용 projection을 다시 만든다.

| 추가 항목 | 계약 |
|---|---|
| concept_refs | 개념·범위 있는 정의 연결 |
| purpose_refs / application_refs | 어떤 검토에 사용 가능한지 |
| input_refs / output_refs | 지식을 적용하기 위한 값과 제공할 결과 |
| assertion_scope | 주장마다 적용 범위·효력시점 |
| expression_ref | 계산 가능한 식이 있는 경우의 검토된 표현식 |
| evidence_role | 정의·한도·예외·산정식·절차·과거판 등 근거 역할 |
| reuse_capability | 위치 안내, 조사 절차, 조건부 지식, 승인된 계산. 자동 결론과 구별 |
| transfer_relations | 다른 업무·정의의 값을 가져다 쓸 수 있다는 근거 있는 연결 |

주장·근거·해석 설명은 기존 Claim/Member/Dependency가 정본이다. 구조화하지 못한 지식은 일반 설명으로 보존한다. 모든 Wiki가 조건식·산정식으로 바뀌어야 게시 가능한 것은 아니다.

후보 생성 시 기존 ID의 수정인지 새 지식인지 제안한다. 기존 compiler가 원 사건·주제·질문에 묶어 만든 ID를 일괄 바꾸지 않는다. 통합이 검토되면 정본으로 사용할 ID와 다른 단위의 alias/변형 연결을 명시하고 원 지식·사건 출처를 남긴다.

원문 판본이 바뀌었을 때 역할별로 다르게 처리한다. 내용과 정의 범위가 유지되는지 확인되지 않은 주장·산정식은 자동 적용에서 제외한다. 위치 안내로 계속 사용할 수 있는지의 판본 이행도 별도 확인한다. 이전 원문 hash를 새 판본에 재사용하지 않는다.

## 숏컷과 요청 상태 확장

사건·발언·사실·정정은 기존 `sw_*` 정본에 남긴다. 새로운 모델을 위한 대화 기록 저장소를 하나 더 만들지 않는다.

기존 trace와 need/task에 다음 참조를 추가한다.

| 항목 | 값 |
|---|---|
| knowledge_binding | 선택한 지식·원문 릴리스와 계약 버전 |
| method_instance | 방법·업무 적용 ID/revision와 이번 요청의 입력 연결 |
| applied_units | Wiki·정확 일치 절차·근거 경로 ID/revision |
| decision_receipts | 코드 조건·계산의 입력·결과·근거 |
| acquisition_refs | 기존 읽기·도구 결과·원문 구간 참조 |
| unresolved | 현재 미확인 항목과 원인. 기존 needs와 연결 |
| deviations | 어떤 적용이 왜 불가능했는지와 다시 조사한 경로 |
| coverage | 요청한 범위·조회한 범위·읽은 범위·비교한 범위 |

조건 계산 receipt는 내부 추론 전문을 저장하라는 뜻이 아니다. 입력·조건·결과·근거처럼 재현에 필요한 구조화된 실행 사실을 저장한다.

이력 전체와 빠른 조회용 색인은 구분한다. 실패한 실행도 원장에 보존하지만 재사용 가능한 성공 경로로 활성화하지 않는다. 부분 성공에서 실제 확보한 원문은 적법한 범위에서 다시 사용할 수 있으며, 전체 해결로 표시하지 않는다.

## 계획과 실행 상태

제안 계획은 `review-plan-v1`이다. 게시된 방법을 현재 요청에 연결한 결과이며 별도의 법률 정답이 아니다.

```json
{
  "schema_version": "review-plan-v1",
  "request_ref": "demo:request",
  "goal_revision": 1,
  "items": [
    {
      "id": "demo:need_1",
      "method_ref": {"id": "demo:quantity_review", "revision": 1},
      "requested_outputs": ["demo:calculation_basis"],
      "input_refs": ["demo:fact"],
      "wiki_refs": [{"id": "demo:wiki", "revision": 1}],
      "after": [],
      "application_status": "PARTIAL",
      "missing": ["demo:aggregation_scope"]
    }
  ],
  "fallback_owner": "EXISTING_RESEARCH_EXECUTOR"
}
```

단계별 상태는 다음 세 축을 분리한다.

| 축 | 예시 상태 | 의미 |
|---|---|---|
| 적용 | MATCHED, PARTIAL, NOT_APPLICABLE, UNRESOLVED | 이 방법·지식을 이번 요구에 얼마나 연결할 수 있는지 |
| 실행 | READY, RUNNING, COMPLETE, PARTIAL, FAILED, SKIPPED | 실제 작업 수행 상태 |
| 의미 | UNASSESSED, SUPPORTED, DISPUTED, UNRESOLVED | 원문·사실에 대한 현재 판단의 상태 |

이 명칭을 기존 wire enum에 그대로 추가하지 않는다. `ResearchLedger`·`NativeResearchTasks`·답변 계약의 현행 상태에 매핑하는 adapter를 만들고, 저장/화면 소비자와 함께 버전 전환한다. 조사 완료가 의미상 부족 해소를 자동으로 뜻하지 않는다.

요청 상태에 적용한 방법 목록과 실행 기록은 같은 journal의 트랜잭션으로 보존한다. 모델 입력용 요약은 그 정본에서 만든 읽기 뷰다.

### 계획 조립 절차

아래는 제안 알고리즘이며 실행 가능한 현행 함수가 아니다.

```text
1. 원문·지식 binding, principal, goal revision, 기존 예산을 고정한다.
2. 기존 질문 해석 또는 유효한 부모 입력에서 목적·사실·원하는 결과를 얻는다.
3. 후보 방법과 업무 적용의 참조를 고정한 binding으로 묶어 읽는다.
4. 요청한 결과에서 필요한 선행 항목만 역으로 연결한다.
5. 입력은 현재 사건 fact 또는 실제 원문 receipt에 결속한다.
   - 없는 입력은 미확인으로 남긴다.
   - 의미 범위가 다른 입력은 자동 대체하지 않는다.
6. 확인된 조건에 한해서 자동 조회·계산·생략 항목을 정한다.
   - 미확인 조건은 관련 자동 적용만 보류한다.
7. 정확 일치 숏컷·Wiki 경로·새 조사 항목의 읽기 대상을 합친다.
   - 같은 판본·좌표·권한·읽기 범위의 획득은 한 번 수행한다.
   - 같은 원문을 서로 다른 관점으로 판단할 필요까지 삭제하지 않는다.
8. 기존 ResearchLedger / NativeResearchTasks에 계획 참조를 기록한다.
9. 기존 실행기가 준비된 항목을 수행하고 남는 부분은 기존 탐색에 전달한다.
10. 원문·미확인·계산 receipt를 기존 판단과 답변 소비자에게 전달한다.
```

순환은 게시 시 참조 검사와 요청 조립 시 방문 집합으로 검출한다. 순환에 걸린 항목만 자동 계획에서 제외하고 조사 필요로 남긴다. 동적으로 발견한 새 근거는 기존 조사 상태에 추가하며 계획 조립 전체를 무조건 다시 시작하지 않는다.

계획은 모델에 전체를 다시 읽혀 승인받는 문서가 아니다. 코드가 실행 가능한 항목은 그대로 처리하고 모델에는 현재 판단에 필요한 원문·입력·남은 항목만 제공한다.

### 실제로 줄이는 판단과 남기는 판단

| 항목 | 준비된 지식이 있는 경우 | 계속 필요한 판단 |
|---|---|---|
| 어떤 자료부터 찾는가 | 현재 조건에 맞는 검토된 원문 경로로 이동 | 경로 불일치·새 쟁점의 탐색 |
| 어떤 사실을 확인하는가 | 요청 결과에 필요한 입력 항목 연결 | 사용자 표현과 법적 범주의 모호한 대응 |
| 같은 원문을 다시 읽는가 | 범위가 일치하는 기존 receipt 재사용 | 새 판본·읽지 않은 부분의 확보 |
| 숫자를 어떻게 계산하는가 | 확인된 식·단위·입력으로 코드 계산 | 해당 식의 적용 근거가 불명확한 경우 |
| 어떤 조사를 생략하는가 | 현재 사실과 검토된 생략 조건으로 제한 적용 | 미확인 조건·새 반례·상충 원문 |
| 법률상 어떻게 결론 내리는가 | 기존 승인 계약의 재사용 범위만 유지 | 새 질문의 원문 적용·충돌·충분성 판단 |

첫 소비 계약은 질문이 다른 경우의 조사 방법·원문 경로·검토된 계산 재사용을 지원한다. 기존 exact-question 판단 재사용 제한을 단순 삭제하지 않는다. 새로운 질문 간 최종 법률 결론 재사용은 별도의 근거·전제 계약과 검증 없이 켜지 않는다.

## 조사 범위 계약

`review-scope-v1`의 목적은 “모두”의 의미와 실제 조사 범위를 추적하는 것이다.

| 항목 | 계약 |
|---|---|
| requested_scope | 사용자 요청한 주제·문서·기간·대상 |
| scope_mode | pinpoint, enumerate, corpus, history |
| universe_binding | 조사 대상 목록의 문서/판본/색인 지문 |
| enumeration | 발견한 대상과 cursor, 종료 여부, 실패/미확보 |
| acquired | 실제 읽은 원문 구간과 기존 receipt |
| compared | 비교한 의미 축과 양측 원문 |
| limitations | 등록 자료 범위, 빠진 판본/별첨, 예산·도구 실패 |

목록이 완전히 열거되었다는 것은 그 목록의 종료를 뜻한다. 관련 법률 전부가 존재한다는 증명이나 의미 비교 완료를 뜻하지 않는다. 상충이 없다는 결론에는 실제 조사 범위와 해석의 한계를 함께 표시한다.

## 도구 교체와 다른 에이전트

공통 계약의 생산자는 현업 지식 게시이며 소비자는 각 에이전트의 adapter다.

| 공통 능력 | 기존 연결 후보 | 반환 요구 |
|---|---|---|
| LOCATE_SOURCE | `law_candidates`·현재 검색 도구 | 후보 문서/판본/좌표·검색 범위 |
| READ_SOURCE | `unit_reading`·현재 원문 읽기 | 원문·구간·판본·권한·더 읽을 범위 |
| FOLLOW_EXPLICIT_REFERENCE | 원문 참조·관계 조회 | 출발 span·명시 참조 대상·미해소 |
| ENUMERATE_SCOPE | 문서·구조 목록 조회 | 목록/cursor·완료 여부·제약 |
| READ_VERSION_CHAIN | 판본 계열 조회 포트 | 판본·기간·연결·빠진 부분. 현행 연결 여부 별도 확인 필요 |
| EVALUATE_TYPED_EXPRESSION | 새 조건/계산 함수 | 입력·연산·결과·미확인·출처 receipt |

에이전트 연결 시 지원 능력·입출력 버전을 등록한다. 요청마다 전체 도구 목록을 LLM으로 검사하지 않는다. 지원하지 않는 능력은 해당 방법 자동 실행을 하지 않고 원문 탐색 또는 제한 결과로 연결한다. 미지원 기능을 성공으로 표시하지 않는다.

도구의 이름 변경은 adapter에서 처리한다. 결과의 의미·원문 범위 계약이 바뀌면 호환성 버전을 올리고 영향받는 방법·projection을 재검사한다. 다른 에이전트도 동일 계약을 소비할 수 있지만 연결 어댑터 없이 동일하게 동작한다고 보장하지 않는다.

## API

독립된 관리 서버를 기본값으로 추가하지 않는다. 현재 `/v1/rag/memory/query`와 `/v1/rag/memory/command`에 명시적인 v2 계약 분기를 추가하거나 같은 handler를 호출하는 UI 경로를 연결한다. 기존 body allowlist와 AD 세션 조건을 함께 변경해야 하며 지금 호출할 수 있는 연산이 아니다.

| 분류 | 제안 연산 | 입력과 출력 |
|---|---|---|
| 조회 | topics, knowledge_detail | 검색·필터·cursor → 접근 가능한 목록/연결 |
| 조회 | impact | 초안 revision → 추가·삭제되는 연결, 영향 대상과 검사 범위 |
| 조회 | preview | 초안 revision·저장된 상황 ref → 조건/검토 항목의 전후 차이 |
| 조회 | runs_for_knowledge | 지식 ID/revision → 실제 적용 요청과 결과의 제한된 목록 |
| 명령 | save_draft | expected_revision·typed changes → 새 초안 revision |
| 명령 | prepare_publication | 초안 refs·예상 head → 검사·빌드 작업 ID |
| 명령 | publish | 준비된 build ID/hash·예상 channel revision → 게시 작업/완료 receipt |
| 명령 | retire / rollback | 대상 revision·사유·예상 head → 사용 중지/복원 receipt |
| 조회 | operation_status | 멱등성 키 또는 작업 ID → 진행·실패·결과 |

공통 명령 봉투의 형식 예시:

```json
{
  "contract_version": "knowledge-command-v2",
  "operation": "save_draft",
  "idempotency_key": "demo:command",
  "arguments": {
    "object_id": "demo:amount_review",
    "expected_revision": 1,
    "changes": [
      {"field": "description", "value": "현재 질문에 필요한 산정 기준을 확인한다"}
    ]
  }
}
```

principal·tenant·scope·허용 문서는 서버가 인증에서 가져온다. 클라이언트가 보낸 user_id·team_id·AD 활성 표시를 신뢰해 권한을 부여하지 않는다. UI 로그인으로 관리 세션을 발급하는 경로와 현재 채팅 AD 경로는 같은 권한 검사 함수를 사용해야 한다.

재전송은 같은 멱등성 키와 입력 hash를 사용한다. 입력이 달라지면 충돌이다. 게시 명령은 새 지식 내용이나 임의 코드를 받지 않고 검사를 통과한 정확한 build를 참조한다. 호출 성공과 실제 게시 완료를 구분해 반환한다.

preview는 기본적으로 코드 조건 적용을 수행한다. 현재 원문 조회나 모델이 필요한 미리보기는 별도 작업으로 명시하며, save/publish를 암묵적으로 수행하지 않는다.

HTTP/명령 결과는 다음 경계를 사용한다. 기존 오류 분류와 매핑하며 새 재시도 계층을 만들지 않는다.

| 결과 | 처리 |
|---|---|
| 200 | 조회 또는 동기 명령 완료. 실제 저장 revision/receipt 포함 |
| 202 | 작업 접수. 게시 완료와 구분하고 작업 ID 제공 |
| 400/422 | 형식·타입·지원하지 않는 계약. 필드별 문제를 묶어서 반환 |
| 401/403 | 인증·권한 문제. 다른 범위의 객체 존재 여부를 불필요하게 노출하지 않음 |
| 409 | revision·멱등성 입력·게시 대상 충돌. 최신 head 또는 확인 가능한 작업 상태 제공 |
| 503 또는 기존 저장 장애 계약 | 외부 저장소 장애. 쓰기 결과 미확정이면 상태 조회가 필요함을 표시 |

### 실제 편집 예

현업이 특정 업무에서 “기한 연장 검토 시 승인 주체도 확인”을 추가하면, 화면은 기존 PROCEDURE 방법의 업무 적용 항목을 수정한다. 공통 방법 전체를 자동 수정하지 않는다. 담당자는 변경된 확인 항목, 해당 업무에 연결된 Wiki, 영향을 받는 실행 사례를 같은 화면에서 본다.

같은 변경이 모든 업무에 필요한 공통 수정이라면 공통 방법의 새 revision을 제안한다. 이때 시스템은 기존 application의 참조를 즉시 일괄 변경하지 않고 영향 목록과 채택 대상을 보여준다. 게시한 릴리스에서 선택된 참조만 다음 요청에 적용한다.

### 편집 권한

| 권한 | 허용 범위 |
|---|---|
| 조회 | 현재 principal로 읽을 수 있는 지식·근거·사례 |
| 업무 편집 | 지정 업무 범위의 초안과 수정 후보 |
| 지식 게시 | 담당 범위의 검토·게시·사용 중지·복원 |
| 기능 관리 | 지원 연산·adapter·계약 버전·운영 설정 |

역할을 모두 다른 사람에게 맡기는 절차는 강제하지 않는다. 한 담당자가 업무 편집과 게시 권한을 함께 가질 수 있다. 기술 기능 관리 권한을 부여하지 않아도 일상적인 업무 지식 수정은 가능해야 한다.

## 저장 포트와 Oracle 논리 구조

정본과 projection을 분리하고 같은 payload를 두 편집 저장소에 복사하지 않는다. 아래는 논리 이름이며 현장 테이블명·DDL은 아니다.

| 논리 저장 단위 | 저장 내용 | 현재 정본/이행 |
|---|---|---|
| 기존 용어·정의 | Concept/Definition/원문 참조 | 현행 데이터 계약 유지, 범위 있는 ID 연결 |
| ReviewDefinition | FIELD/METHOD/APPLICATION의 id·revision·kind·scope·hash·payload | 신규 업무 계약, 타입별 검증. 모든 법률 데이터를 넣는 범용 표가 아님 |
| ReviewDependency | 위 객체의 의존 대상·revision·role | Wiki는 기존 dependency가 정본. 조회 시 합쳐 보는 뷰 |
| 기존 Wiki/Shortcut 원장 | sw_unit·knowledge·claim·procedure·fact·trace 등 | 기존 식별자·내용·이력 보존. Oracle 포트 이행은 별도 |
| KnowledgeRelease | 사용할 객체 revision 목록·검토/빌드 정보·원문 호환성 | 불변 manifest와 내용 hash |
| KnowledgeLookup | 후보·목적·업무·입력 ID·근거 경로 색인 | 재생성 가능한 조회용 projection |
| ServingBinding | source_query_release·knowledge_release·계약 버전·channel revision | 하나의 원자적 선택. 기존 원문 ACTIVE와 충돌하지 않게 reader 버전 분리 |
| 기존 작업·감사 큐 | 빌드·게시·피드백 작업과 상태 | ad_jobs/기존 큐 확장, 별도 스케줄러 기본 도입 없음 |

지식 릴리스에 원문 본문·기존 Wiki 본문을 모두 재복제하지 않는다. 불변 객체와 원문을 참조하고 변경된 projection만 구축한다. 게시 manifest에는 실제 포함된 revision과 호환 범위를 기록한다. 원문 릴리스가 변경되면 의존성을 기준으로 영향을 계산하며 기존 정확 일치 숏컷의 전체 binding 검사를 근거 없이 완화하지 않는다.

ServingBinding은 기존 source ACTIVE의 RELEASE_ID에 새 종류의 ID를 몰래 넣는 방식으로 구현하지 않는다. 현재 manifest schema와 FK 계약을 보존하는 별도 버전의 선택 포트가 필요하다. `off` 모드는 기존 선택을 사용하고, 새 소비 모드에서는 source와 knowledge를 한 번에 고정한다.

읽기 포트는 다음 책임을 갖는다.

```text
resolve_binding(channel, principal)
lookup_candidates(binding, query_features, purpose_hints, cursor, limit)
read_review_bundle(binding, object_refs, principal)
lookup_wiki_routes(binding, purposes, context, input_field_ids, principal)
read_execution_refs(request_ref, principal)
```

호출 형태는 제안이다. 필요한 조회를 묶고 기존 원문 조회 포트와 같은 request budget을 사용한다. 사용자·모델이 SQL을 생성하지 않는다. 게시 내용에 principal 범위가 포함되지 않은 경우에도 실행할 때 현재 권한으로 다시 제한한다.

현재 `State` 포트는 작은 요청 상태와 CAS를 지원하지만 sw_* 전체 SQL 의미를 대신하지 않는다. SQL 트랜잭션·불변 기록·동시 편집을 보존하는 repository 포트 또는 외부 상태 계층이 필요하다. 이 설계에서 `State`에 SQLite 파일 전체를 담거나 GENOS에 로컬 쓰기 fallback을 추가하지 않는다.

## 게시와 변경 전파

1. 현업이 초안을 저장한다. 기존 head를 바꾸지 않는다.
2. 기존 작업 큐가 변경한 객체와 직접/전이 의존 대상을 계산한다. 원문 본문은 복사하지 않는다.
3. 타입·참조·순환·미지원 능력·조건 충돌·권한 범위를 검사한다. 법률 의미 충돌은 검토 대상으로 표시한다.
4. 영향을 받는 조건 상황과 실제 소비 계약을 확인한다. 변경 없는 객체의 검사를 반복하지 않는다.
5. 불변 KnowledgeRelease와 필요한 조회 데이터가 준비되면 게시 가능한 build를 기록한다.
6. Dataiku/승인된 데이터 게시 경로가 ServingBinding을 expected_revision으로 교체한다.
7. 실패하면 기존 binding을 유지한다. 응답이 유실되면 operation_status로 실제 완료 여부를 확인한다.

객체 단위의 수정과 release 게시를 구분한다. 초안 작성 도중 현재 답변이 달라지지 않는다. 사용자에게 “저장됨”, “게시 준비 중”, “사용 중”, “게시 실패”를 구별해 보여준다.

원문 변경은 해당 source dependency에 연결된 정의·주장·식·방법 적용의 재검토 후보를 만든다. 영향받지 않은 지식은 유지한다. 배치가 승인 상태를 자동으로 덮어쓰거나, 오래된 의미를 새 판본으로 자동 승인하지 않는다.

## 지식 강화와 관리 부담

기존 사건 정정과 source 변경을 활용해 후보를 만든다. 기본 후보는 새 지식을 계속 추가하기보다 기존 항목 수정, 중복 통합, 범위 축소, 생략 규칙 철회, 오래된 경로 정리다.

후보에는 원 기록·수정 이유·영향·재현 가능한 상황을 연결한다. 사용 횟수와 사용자의 만족 반응만으로 법률적 정확성을 판정하지 않는다. 사람이 반려한 제안은 이유를 남겨 같은 근거의 반복 제안을 줄인다.

일반 현업 편집에서 운영 코드와 도구 adapter는 바꾸지 못한다. 새 연산과 능력은 개발자가 구현·계약 검사한 뒤 선택 가능한 옵션으로 제공한다.

## 이행과 롤백

| 이행 대상 | 방법 | 재구축 범위 |
|---|---|---|
| domain catalogue v1 | 기존 reader 유지, 새 조회 계약 병행 | 새 입력·방법·적용 객체와 색인 |
| 기존 Wiki | 새 revision에 선택적 참조 추가. 미매핑은 탐색 단서 유지 | 변경 Wiki의 projection만 |
| 기존 숏컷 | 과거 이벤트 보존, 새 요청부터 참조 기록 | 필요 범위의 연결 색인. 사건 사실 복제 없음 |
| 원문·용어 | 현행 ID·판본 유지 | 이 기능 때문에 전체 원문 재구축하지 않음 |
| 현재 관리 API | v1과 명시적인 v2 분기 | UI·AD 공통 권한/명령 소비자 |
| 저장 backend | 로컬·외부 상태·Oracle 포트를 구분 | 실제 스키마·트랜잭션 호환성 검사 뒤 이행 |

기능 모드 제안은 `off`, `observe`, `consume`이다. observe는 구조화된 계획과 실제 기존 동작을 기록하되 새 모델 호출로 병렬 평가하지 않는다. 관측 오버헤드는 별도 측정한다. consume 전환은 같은 코드 검증과 효과 비교 후 수행한다.

rollback은 기능 모드·지식 binding·필요한 코드 릴리스를 기존 호환 조합으로 되돌린다. 이미 수행한 외부 업무를 되돌리는 기능으로 설명하지 않는다. 원문 조회 중심의 이 설계에서도 게시·정정·실패 이력은 보존한다.

## 구현 검사의 범위

| 검사 | 기대 결과 |
|---|---|
| 서로 다른 금액 의미·같은 숫자 | 필드/범위가 달라 임의 합산·대체하지 않음 |
| 같은 필드·다른 단위 | 허용 정규화 또는 미확인. 무조건 수치 비교하지 않음 |
| 조건 TRUE/FALSE/UNKNOWN·충돌 | 생략·계산·근거 사용의 경계가 계약대로 다름 |
| 방법 일부 입력 누락 | 확보 가능한 원문은 읽고 관련 계산만 미완 |
| 정확 일치 경로와 방법이 같은 원문 요구 | 같은 요청의 원문 획득을 합치고 두 항목에 receipt 연결 |
| 전체 범위·소수 Wiki 적중 | 적중과 조사 완료를 구분 |
| 과거판 누락 | 현재판을 과거로 대체하거나 삭제일을 추측하지 않음 |
| Wiki 철회·권한 축소 | 현재 권한/철회 검사와 제한 답변에 반영 |
| 정정·재개·중복 요청 | 같은 상태 소유자, 누적 예산·최초 deadline 유지 |
| 게시 충돌·응답 유실 | 기존 활성 버전 유지 또는 실제 완료 조회, 중복 게시 없음 |
| 다른 에이전트의 미지원 능력 | 해당 자동 실행 생략, 성공 위장 없음 |
| 실제 서비스 소비 | 동일 pin으로 입력→조사→원문→답변→원장→관리 화면 연결 |

위 검사는 계획이며 이번 문서 작성에서 실행한 제품 검사 목록이 아니다. 모델·프롬프트·검색 효과 비교는 별도 ADR로 동결해 수행한다.

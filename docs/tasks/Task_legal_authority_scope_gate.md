# Task — 법적 권한·업무처리 가능 여부 질의의 범위 게이트

> 상태: Backlog  
> 등록일: 2026-08-28  
> 성격: 제품 답변 안전장치 + 법률관계 데이터 보강

## 문제

기업 사용자가 “이 업무를 위탁해도 되는가”, “대리시켜도 되는가”, “내부 전결로
처리해도 되는가”처럼 행위의 적법 여부를 물으면, 관계 이름이나 근거 조문 하나만
찾아서는 결론을 낼 수 없다. 허용 범위, 상대방 자격, 재위임 가능성, 필요한 절차와
잔존 책임까지 확인되지 않은 상태에서 가능하다고 답하면 안 된다.

현재 위탁 질의 라우팅과 일반 답변 체크리스트만으로는 이 범위 확인을 강제하지
못한다. 법률관계도 새 스키마에는 세분된 술어가 있으나 실제 데이터와 제품 런타임의
연결 상태가 균일하지 않다.

## 구현 범위

### 0. 법률관계의 세 축

문서의 5·6·7번을 다음의 서로 다른 판단축으로 고정한다. `수직/수평`은 설명용
표현으로만 쓰고, 실제 스키마에는 의미가 분명한 `relation_axis`를 저장한다.

| 문서 구분 | relation_axis | 현재 family | 판단 질문 |
|---|---|---|---|
| 5. 입법 위임·수임·재위임 | `NORM_COMPLETION` | `LEGISLATIVE_LINK` | 누가 세부 규범을 완성하는가 |
| 6. 권한 위임·업무 위탁·대리·전결·임용 | `COMPETENCE_ALLOCATION` | `COMPETENCE_TASK` | 누가 권한을 행사하고 업무를 수행하는가 |
| 7. 적용·준용·예에 따름 | `RULE_INCORPORATION` | `RULE_USE` | 다른 규범을 어떤 방식과 범위로 가져오는가 |

`수임`을 하나의 범용 `RECEIVES_FROM` 의미로 합치지 않는다. 입법수임은
`LEGISLATIVE_DELEGATION`, 권한수임은 `DELEGATES_ADMINISTRATIVE_AUTHORITY`, 수탁은
`ENTRUSTS_TASK`의 역방향 view로 각각 생성한다. 정본 간선과 사용자 표시 방향을
분리하여 5번과 6번의 의미가 섞이지 않게 한다.

### 1. 질의 분류와 결론 게이트

다음 유형을 별도 고위험 질의군으로 분류한다.

- 권한 위임·수임·재위임
- 사무·업무 위탁·재위탁
- 대리·복대리
- 내부 위임전결·단순 집행
- 임용·지정 등 사람 또는 기관에 대한 권한 부여

“가능/불가능” 결론 전 아래 항목을 근거와 함께 채운다.

1. 원 권한자 또는 의무자
2. 상대방과 그 법적 자격
3. 관계 유형(위임·위탁·대리·전결·집행 등)
4. 의사결정권 이전인지 보조업무 처리인지
5. 허용·금지되는 업무와 권한의 범위
6. 재위임·재위탁·복대리 가능 여부
7. 승인·보고·고시·통지·계약 등 절차
8. 원 권한자의 지휘·감독과 잔존 책임
9. 다른 법률의 금지·자격·인가 요건
10. 사실관계에서 아직 확인되지 않은 조건

핵심 조건이나 근거가 비어 있으면 단정형 “가능”을 금지하고, `판단보류/추가 확인
필요`와 누락 사실을 반환한다.

### 2. 규칙 사용 동사의 데이터 선행과제

범위 판단에 필요한 다음 표현을 추출 단계부터 구분한다.

- `적용한다` → 수정 없이 적용 (`DIRECTLY_APPLIES`)
- `준용한다` → 성질에 맞게 바꾸어 적용 (`INCORPORATES_MUTATIS_MUTANDIS`)
- `예에 따른다` → 제도·절차의 예를 따름 (`FOLLOWS_EXAMPLE_OF`)

현재 레거시 참조 파서는 `준용`만 별도 라벨로 만들며, 긍정형 `적용한다`와
`예에 따른다`는 보통 일반 인용으로 남는다. canonical 데이터 생성과 제품 검색이
위 세 관계를 동일한 의미로 소비하도록 보강한다. `적용례(APPLIES_TO)`는 시행·경과
시점 관계이므로 `DIRECTLY_APPLIES`와 혼동하지 않는다.

### 3. 스키마별 실행 로직

관계 스키마를 단순 라벨이나 검색 필터로 끝내지 않고 다음 제품 로직까지 연결한다.

1. **추출**: 법문 표면형과 문맥을 typed predicate로 정규화한다.
2. **해소**: source·target 조문 및 기관·직위 endpoint를 정확한 좌표로 연결한다.
3. **범위화**: 적용되는 조·항·호, 대상 업무, 조건, 예외와 제외 범위를 구조화한다.
4. **관계 닫힘**: 질문에 활성화된 필수 companion 조문을 축별 방향과 상한에 따라 회수한다.
5. **판단**: 축별 체크포인트를 모두 충족한 경우에만 가능·불가능 결론을 만든다.
6. **설명**: 관계명뿐 아니라 근거, 범위, 치환, 절차, 잔존 책임과 미확인 조건을 제시한다.

축별 전용 로직은 다음과 같다.

- `NORM_COMPLETION`: 위임사항·위임범위·수임규정·재위임 근거·하위 규범의 완성 여부를 추적한다.
- `COMPETENCE_ALLOCATION`: 원 권한자·수행자·행위 명의·결정권 이전·상대방 자격·감독 및 책임을 추적한다.
- `RULE_INCORPORATION`: 직접 적용·준용·예에 따름을 구별하고 원용 범위·문구 치환·조건·부분 배제를 추적한다.

공통 edge에는 적어도 `relation_axis`, `predicate`, `source`, `target`,
`surface_expression`, `legal_basis`, `scope`, `conditions`, `exclusions`, `evidence`,
`confidence`를 보존한다. 축별 속성은 별도 props로 확장한다.

스키마에 간선이 존재해도 해당 추출·닫힘·판단·답변 로직이 제품 경로에 연결되지
않으면 기능 완료로 보지 않는다.

### 4. 중간 Decision Packet 컴파일과 표적 회수

넓은 최초 회수 결과를 곧바로 최종 LLM에 넘기지 않는다. 최초 회수와 법률 판단
사이에 핵심 쟁점 한 구간을 구조화하는 `Decision Packet Compiler`를 둔다.

1. `Query Sketch`: 질문을 하나로 확정하지 않고 family·관계·행위 후보를 복수로 만든다.
2. `Broad Retrieval`: 정확 일치, 용어 색인, 벡터, 법률관계 확장을 합집합으로 회수한다.
3. `Candidate Bundle`: 같은 판단에 필요한 근거들을 관계 단위 묶음으로 구성한다.
4. `Decision Packet Compile`: 쟁점, 후보 관계, 지배 규칙, 판단요소, 예외·수식자,
   금지 추론과 누락 근거를 명시한다.
5. `Coverage Gate`: 필수 근거가 비면 해당 누락만을 목표로 표적 재검색하고 결론을 막는다.
6. `Assessment`: 근거가 준비된 packet에 대해서만 실체 판단을 수행한다.
7. `Answer`: 판단 결과와 근거를 사용자 질문에 맞게 표현한다.

packet에는 적어도 `issue`, `proposed_relation`, `governing_rule`, `elements`,
`modifiers`, `prohibited_inferences`, `missing_evidence`, `assessment_readiness`를 둔다.
컴파일 결과와 별개로 원문 근거 lane을 유지하여 누락된 구조화나 잘못된 역할 배정을
후속 단계가 교정할 수 있게 한다.

필수 evidence coverage가 전부 채워졌다는 것은 법률 결론이 아니라 근거 준비 상태다.
따라서 coverage 런타임의 완료 상태는 개념상 `EVIDENCE_READY` 또는
`RETRIEVAL_COMPLETE`로 취급하고, `SUPPORTED` 같은 실체 판단 용어는 assessment 이후에만
사용한다.

### 5. 질의 grounding과 다중 채널 검색 도구

현재 분산된 다음 세 경로는 하나의 검색 계획 도구 아래에서 조정하되, 서로 다른
증거 채널로 유지한다.

- LLM의 typed slot 추출: actor·action·object·관계·조건 후보 생성
- 원문 문자열의 역색인·도메인 lexicon 매칭: DB 값과 canonical 후보 생성
- LLM의 법령식 full-text 질의 생성: 원문과 다른 법문 표현으로 recall 확장

family는 어떤 관계 규칙과 검색 경로를 열지 정하는 routing 정보다. 같은 family 안에도
행위, 대상 업무, 주체 자격과 조건이 다른 조문이 많으므로 family만으로 최종 후보를
선정하지 않는다. 최소한 명시적 법령 좌표, 핵심 `action`, `object`, `actor` 후보를 함께
사용한다. 다만 이 slot들을 완벽히 하나로 확정해야만 검색할 수 있는 hard gate로 만들지
않는다.

검색 계획 도구의 출력 계약은 다음을 포함한다.

- `original_query`
- `family_hypotheses[]`: family, confidence, 근거가 된 원문
- `mentions[]`: 원문 표면형, actor/action/object 역할, 정규화 후보 Top-N, confidence,
  exact·lexicon·vector·LLM 등 provenance
- `search_queries[]`: exact, fielded keyword, full-text, assertion, vector, relation expansion별 질의와 생성 이유
- `hard_constraints[]`: 사용자가 명시한 법령명·조문·수치 등 버리면 안 되는 조건
- `soft_signals[]`와 `unresolved_mentions[]`

이 계약은 canonical 법률지식 스키마와 분리된 runtime observation 스키마다. 질의 LLM이
canonical entity·predicate·조문 좌표를 자유 생성하게 하지 않는다. 다음 세 층을
구별한다.

1. `QueryMention`: 질문에 실제 존재하는 원문 span과 offsets. 원문에 없는 값은 mention으로 만들 수 없다.
2. `GroundingCandidate`: 기존 DB의 entity·concept·predicate·semantic card ID에 대한 Top-N 연결 후보.
3. `InterpretationHypothesis`: 원문에 직접 쓰이지 않은 법적 성격·수단목적·사실적용 후보.
   canonical 사실이 아니라 근거와 confidence가 붙은 runtime 가설로만 둔다.

LLM이 생성한 법률용어는 `expansion_terms`로만 사용할 수 있고, DB 조회로 존재가 확인되지
않은 값은 canonical ID나 확정 slot이 될 수 없다. 후보가 없거나 충돌하면
`UNRESOLVED`를 정상 상태로 반환한다.

`actor/action/object`는 모든 질문에 강제하는 단일 frame이 아니다. 공통 mention 위에
family 또는 predicate별 signature를 적용한다. 예를 들어 업무위탁 후보에는
`source_actor`, `target_actor`, `regulated_action`, `task_object`, `legal_effect`,
`conditions`가 필요하고, 준용 후보에는 `incorporating_rule`, `incorporated_rule`,
`scope`, `substitutions`, `exclusions`가 필요하다. 후보 endpoint의 semantic type과
predicate signature가 slot 역할과 호환되지 않으면 해당 landing을 감점하거나 거부한다.

질문 표현과 법문 표현 사이의 연결도 종류를 구분한다.

- 동의어·별칭: `ALIAS`
- 상하위 개념: `IS_A`
- 실무 수단과 법적 목적: `MEANS_TO_END`
- 사실관계의 법적 행위유형 후보: `FACT_CHARACTERIZATION`
- 질문 용어와 법정 용어의 대응: `QUERY_TO_LEGAL_CONCEPT`

이 bridge들은 source-backed 사전·정의·검증된 관찰이 있으면 재사용하고, 질문 시점에
새로 생성된 bridge는 canonical graph에 쓰지 않는다. 따라서 `사내규정 정비`를
`내부통제·경영투명성`에 연결하거나 `국채 선매도`를 특정 금융투자업 행위로 분류하는
것은 단순 entity 추출이 아니라 별도 interpretation hypothesis다.

예를 들어 `외부 기관`은 초기에 단일 DB 값으로 덮어쓰지 않고 원문을 보존한 채
`수탁기관`, `제3자`, 특정 자격기관 등의 후보를 연결한다. `업무 위탁`은 action 후보,
`심사업무`는 object 후보로 유지한다. exact match는 강한 신호로, field가 맞는 lexicon
후보는 그 다음 신호로, LLM 생성어와 vector 이웃은 recall용 약한 신호로 사용한다.

각 채널의 결과는 합집합으로 모은 뒤 후보 bundle과 coverage로 가지친다. 한 채널의
낮은 점수가 다른 채널의 정확한 후보를 조기에 제거하지 않게 한다. 비용은 다음처럼
단계화한다.

1. 매 질의에 exact·alias·역색인·명시 조문 해석을 먼저 실행한다.
2. 하나의 구조화 LLM 호출에서 typed mention 후보와 채널별 검색어를 함께 생성할 수 있다.
3. 낮은 confidence, 충돌 또는 coverage 누락이 있을 때만 vector 확장과 표적 LLM 재질의를 실행한다.

도구는 답변을 직접 만들지 않고 `Query Search Plan`과 채널별 실행 영수증을 반환한다.
따라서 구현 형태는 하나의 거대한 검색 알고리즘이 아니라 여러 검색 adapter를 조정하는
`Legal Search Planner`가 적합하다. 이후 Decision Packet의 `missing_evidence`가 같은
planner에 표적 recovery 요청을 되돌려 보낸다.

## 완료 기준

- 대표 질의 세트에서 관계 유형·범위·자격·절차·잔존 책임이 모두 근거 조문에 연결된다.
- 재위임·재위탁 근거가 없거나 금지된 사례는 가능 답변을 내지 않는다.
- `적용한다/준용한다/예에 따른다`가 서로 다른 canonical 술어로 적재되고 회수된다.
- 5·6·7번 관계가 `relation_axis`로 구별되고 범용 `RECEIVES_FROM`이 의미를 혼합하지 않는다.
- 각 축의 추출→해소→범위화→닫힘→판단→설명 경로가 end-to-end로 연결된다.
- 필수 관계 닫힘과 문맥 관계 닫힘 정책이 실제 제품 경로에서 검증된다.
- 정답 근거가 회수된 대표 사례에서 Decision Packet이 근거 역할과 누락 조건을 안정적으로 구분한다.
- 질의 grounding은 원문 mention과 Top-N DB 후보 및 provenance를 보존하며, family 하나로 조기 확정하지 않는다.
- 원문 span이 없는 LLM 생성값은 mention 또는 canonical entity로 저장되지 않으며, 미해소 상태를 허용한다.
- family·predicate별 signature 검증으로 source/target 역할이 뒤바뀌거나 인접 semantic card에 잘못 착지한 후보를 식별한다.
- 질문-법정용어 bridge와 사실관계의 법적 성격 부여는 canonical 지식과 분리된 runtime 가설로 추적된다.
- 다중 채널 검색 계획의 실행 영수증으로 각 후보가 exact·lexicon·LLM·vector 중 어디서 왔는지 추적할 수 있다.
- coverage 누락은 전체 재검색이 아니라 누락된 판단요소를 겨냥한 표적 recovery로 이어진다.
- 변경은 실험 ADR 및 승격 절차를 거쳐야 하며, 이 문서는 구현이나 MAIN 승격을 뜻하지 않는다.

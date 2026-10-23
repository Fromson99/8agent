# 데이터 객체와 함수 계약

[전체 목차](../../../ARCHITECTURE/ONTOLOGY_V3.md) · [구현 목차](../IMPLEMENTATION_NAMES.md)

원래 논의의 절 번호를 유지했습니다. 설계 제안과 구현·검증 상태는 각 절의 구분을 따릅니다.

<a id="impl-5"></a>

## 5. 새로 명시할 데이터 객체

아래 이름은 M04의 **제안 계약 이름**이다. 지금의 스키마에 같은 필드가 이미 있다는 의미가 아니다. 공통 참조는 ID·revision·content hash·권한 범위에 결속한다. 원문 전체를 복제하지 않고 현재 원문 계약의 span·판본을 참조한다.

| 객체 | 실제 관리하는 단위 | 소유·소비 구현 |
|---|---|---|
| `ExperienceRef` | 조사 경험과 그 버전의 참조 | M01 생성, M03·M05에서 출처로 사용 |
| `EvidenceRoute` | 어떤 근거 필요를 어떤 원문 위치로 해결했는지와 재사용 조건 | M02 관리, M07·기존 원문 탐색 소비 |
| `KnowledgeCandidate` | 아직 채택되지 않은 의미 주장·관계 후보와 원문·경험 출처 | M03 생성, M05 저장, M06 검토 |
| `KnowledgeAssertion` | 기업이 관리할 하나의 의미 주장. 조건·예외·적용 범위·원문 지지 포함 | M04 정의, M05 저장 |
| `KnowledgeRelation` | 어떤 객체의 어떤 의미가 다른 객체에 어떻게 의존하는지 | M04 정의, M05 저장, M07·M09 소비 |
| `EvidenceBinding` | 주장·관계와 원문을 연결하고 정의·계산·예외 등 근거 역할 표시 | M05 관리, M07·M08 소비 |
| `ReviewDecision` | 고정된 지식 버전에 대한 채택·반려·이견·사용 중단의 이유와 행위자 | M06 기록, M05 이력 조회 |
| `KnowledgeRelease` | 소비에 제공할 버전 묶음. 검토 상태와 별도로 게시 선택 관리 | M06 관리, M07·M08 재확인 |
| `KnowledgeOffer` | 특정 질의에 제시한 지식·검토 항목·근거 경로 | M07 생성, M08 전달 |
| `KnowledgeUse` | 제시·선택·적용·계산·사후 검토 중 실제 기록된 사용 사건 | M08 기록, M09·M10 소비 |
| `DecisionDependency` | 최종 주장 ID가 어떤 지식 버전·사실·계산·해석에 의존하는지 | M08 기록, M09 역조회 |
| `ImpactReport` | 영향 대상과 직접/간접 경로, 확인 범위·누락·미확인 | M09 생성, M10 표시 |

‘검토 상태’, ‘게시 상태’, ‘현재 원문과의 유효성’, ‘이번 사안에 대한 적용 판단’은 다른 축으로 유지한다. 하나의 APPROVED 값으로 네 가지를 모두 표현하지 않는다.

개념 자체의 ID와 정의는 기존 용어집·정의 계약을 우선 참조한다. 조직별 정의가 필요하면 적용 범위를 가진 명시적 정의 주장으로 추가하고 출처를 남긴다. 같은 문자열이라는 이유로 기존 개념을 자동 병합하지 않는다.

`KnowledgeRelation`의 후보 종류로는 정의 사용, 계산 입력, 합산 범위 결정, 예외, 근거 지지 등을 둘 수 있다. 종류별 허용 입력·출력·조건·합성 규칙을 정해야 하며, 이 표만으로 자동 전이 추론을 허용하지 않는다.

<a id="impl-6"></a>

## 6. 파일별 호출 계약

다음 시그니처는 **설계 목표**다. 실제 구현 시 기존 계약의 버전 변경·권한·예산 전달을 함께 검토한다. 별도의 모델 호출이나 새 실행기를 자동 추가하지 않는다.

### M03: 지식 후보 생성기

```python
build_candidates(input_refs, *, source_port, experience_port,
                 model, model_binding, principal, budget)
    -> CandidateBatch
```

- 기존 `compile_snapshots`의 출처·성공 기록·인용 검사를 재사용한다.
- 입력은 적격 조사 경험뿐 아니라 선정된 원문 범위도 지원하는 방향이다. 기업 지식의 생성이 과거 답변 발생 여부에만 종속되지 않게 한다.
- 후보와 출처·추출 이유를 반환하고 M05에 저장한다. 이 함수가 검토 결정·게시를 확정하지 않는다.
- 이행 초기에는 기존 경험 입력을 지원하고, 원문 직접 입력은 같은 계약을 검증한 뒤 추가한다.

### M05: 기업지식 원장

```python
KnowledgeRegistry.get(ref, principal) -> KnowledgeRecord
KnowledgeRegistry.append_revision(object_id, value, *,
                                  expected_revision, principal) -> KnowledgeRef
KnowledgeRegistry.dependencies(ref, principal) -> DependencyPage
```

- 기존 Oracle `Repository`의 불변 기록과 CAS를 재사용한다.
- 모델 텍스트의 해시나 질문 문구를 조직 지식의 영구 ID로 사용하지 않는다. 영구 ID와 내용 버전을 구분한다.
- 쓰기는 M06의 권한·명령 경계 안에서 수행한다. `append_revision` 자체를 무권한 외부 API로 노출하지 않는다.
- 원문·경험·basis 관계는 기존 정본을 참조한다.

### M06: 지식 검토·게시 서비스

```python
KnowledgeLifecycleService.command(principal, command) -> OperationReceipt
```

- 현행 command 엔드포인트와 operation ID를 유지한다.
- 현행 초안·게시 준비·게시·채널 중단·롤백에, 객체별 검토 결정·개별 사용 중단·명시적 대체를 버전 계약으로 추가한다.
- 개별 사용 중단과 채널 전체 중단의 명령을 구분한다. 옛 `retire` 요청을 조용히 개별 철회로 재해석하지 않는다.
- 관찰·단순 인용 검증·사용자 사실 확인은 법적 해석 승인으로 바꾸지 않는다.
- 같은 작업 ID의 결과 불명은 기존 operation 조회로 복구한다.

### M07: 지식 조회 서비스

```python
KnowledgeQueryService.find_entry_points(query_context, principal) -> KnowledgeOffer
KnowledgeQueryService.find_evidence(evidence_need, query_context,
                                   principal) -> KnowledgeOffer
```

- 최초 진입과 조사 중 새 근거 필요라는 두 호출 목적을 명시한다.
- `query_context`에는 현재 질문, source binding, 확인된 사실의 참조, 기준일과 업무 범위를 넣는다. 미제공은 미확인으로 보존한다.
- 근거 필요는 판단 대상·필요 역할·현재 확보 상태에 연결한다. 같은 필요·같은 상태를 다른 문구로 바꾸었다고 새로운 조회 예산을 만들지 않는다.
- M05의 유효 지식과 M02의 경로를 조회하고 기존 원문 탐색에 전달한다. 저장된 결론을 답변으로 반환하는 함수가 아니다.

### M08: 지식 적용 서비스

```python
KnowledgeApplicationService.prepare(query_context, principal) -> KnowledgeOffer
KnowledgeApplicationService.record_application(
    decision_ref, selected_refs, evidence_refs, fact_refs,
    interpretation, dependencies, *, execution_context) -> KnowledgeUseRef
KnowledgeApplicationService.revalidate(usage_refs, principal) -> ValidationReceipt
```

- 기존 `request_entry`, 조사·판단·발행 경로에서 호출한다.
- 제시된 후보와 선택된 후보를 구분하고, 새 해석을 기존 검토 관계의 속성으로 덮어쓰지 않는다.
- 기존 journal에 사용 사건을 기록한다. 명시적으로 선택한 관계, 검증된 원문, 수행한 계산을 각각 결속한다.
- 선택·인용·계산 결과의 스키마를 검증한 뒤 시스템이 참조 ID·버전·출처를 조립한다.
- 아직 의미 판단이 끝나지 않은 경우에는 미확인과 전달 사실을 남긴다. 이를 모든 원문 전달의 중단 조건으로 만들지 않는다.

### M09: 변경 영향 분석기

```python
KnowledgeImpactAnalyzer.analyze(changed_refs, principal, *,
                               scope, cursor=None) -> ImpactReport
```

- M05의 지식 의존관계와 M08 사용 기록의 조회용 색인을 함께 사용한다.
- 영향 후보와 재검토 완료를 구분한다. 과거 답변을 자동 수정하는 함수가 아니다.
- 원문 개정의 입력은 기존 basis migration·원문 세대 변경 기록에서 받는다.
- 권한으로 볼 수 없는 대상, 미색인 구간, 예산 때문에 확인하지 못한 범위가 있으면 완전한 영향 조회라고 표시하지 않는다.

### M10~M12: 표현·실행 정책·조건 평가

- `views.py::render_knowledge(record, reviews, usages)`: 같은 지식 ID의 화면·문서 표현. 렌더러는 승인 상태를 변경하지 않는다.
- `ResearchExecutionPolicy.select(stage, state, session)`: 단계 실행 정책을 선택·기록. 법률 개념을 검토 완료했다고 표시하지 않는다.
- `condition_evaluator.evaluate(expression, facts, binding=...)`: 제한된 형식 조건을 실행. 타입·단위·미확인·반올림 정책을 보존한다. 표현하지 못하는 법적 해석을 코드가 추정하지 않는다.

---

[이전: 구현 단위 이름과 파일 구조](MODULES.md) · [목차](../IMPLEMENTATION_NAMES.md) · [다음: 호출 연결과 저장 책임](INTEGRATION.md)

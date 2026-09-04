# 4축 기반 목표 아키텍처

## 1. 고정 평가축

| 축 | 시스템 질문 | 핵심 산출물 | 게이트 |
|---|---|---|---|
| 구축 가능성 | 원문에서 안정적으로 만들 수 있는가 | Structure, DetectionHint, SemanticObservation | exact source, schema, UNKNOWN 보존 |
| 유지보수 가능성 | 작은 단위로 고치고 돌릴 수 있는가 | immutable generation, overlay, receipt | hash, lineage, atomic activation |
| 검색·판단 효용성 | 정답 Rule과 필수 단서를 작게 묶는가 | Concept, Clause, Rule, Proviso, Relation, RuleBundle | recall, bundle completeness, provenance |
| 피드백 학습 | 동일 실패를 줄이고 검증된 질문을 빠르게 찾는가 | FeedbackEvent, ChangeCandidate, QueryShortcut | generation lock, replay, approval |

전 단계에 `원문 근거 + 버전 + 감사 + 롤백 + 접근권한`을 공통 불변조건으로 둔다.

## 2. 시스템 계층

```text
DatasetPackage / SourceSet
  └─ Source: DocumentVersion → StructuralUnit → TextBlock → ClauseSpan
       └─ Observation: DetectionHint(규칙) + SemanticObservation(LLM)
            └─ Canonical semantics: Concept + SemanticClause + Rule + Proviso
                 └─ LegalRelation + Evidence
                      └─ Projection: RetrievalCard + RuleBundle + Index
                           └─ Runtime: QueryFrame + CandidateSet + Trace
                                └─ Control: Feedback → Candidate → Experiment → Approval → Release
```

### 의미 경계

- 규칙은 단서 존재, exact span, 명시 참조 표면형만 `DetectionHint`로 만든다.
- 조건·결과·효과·완결 방식·연결 대상은 LLM `SemanticObservation`이 판단한다.
- observation은 exact source라는 이유만으로 canonical `ACCEPTED`로 승격하지 않는다.
- `SemanticClause`는 하나의 행위·상태 명제, `Rule`은 최소 IF→THEN 실행단위다.
- `Proviso`는 Rule을 조건부로 변경하는 노드다. 내부 완결 단서도 노드로 남기고, 외부 요건이 필요할 때만 관계를 따라간다.
- Actor/Predicate/Object/Condition/Outcome은 Concept의 고정 속성이 아니라 Clause·Rule 안의 `RoleBinding`이다.
- 기존 `Frame`은 observation, 규칙 `Requirement`는 hint, 모호한 public `Assertion`은 `SemanticClause`/`Rule`로 이행한다.

## 3. canonical 최상위 폴더

| 경로 | 단일 책임 | 현재 v1 호환 경로 |
|---|---|---|
| `00_SYSTEM` | 아키텍처·스키마·전역 정책·이행 계약 | 신규 |
| `01_DATA` | immutable dataset/build/source-set·카탈로그 | `data` |
| `02_BACKEND` | 설치 가능한 `lawrag` 패키지·API·파이프라인 | `lawrag` |
| `03_FRONTEND` | 운영·검수·실험 UI | `experiment-studio`, API static UI |
| `04_EXPERIMENTS` | ADR·dataset refs·candidate·run·decision | `docs/adr`, `benchmarks`, `lawrag/research` |
| `05_TESTS` | unit·contract·integration·E2E·fixture | `tests` |
| `06_TOOLS` | 얇은 CLI·migration·audit·reporting | `scripts` |
| `07_DOCS` | 현행 설계·도메인·운영 문서 | `docs` 중 ADR 외 |
| `08_DEPLOYMENT` | GENOS·onsite·local profile·package | `config`, GenOS scripts/docs |
| `09_ARTIFACTS` | 보고서·내보내기·release 산출물 | `artifacts` |
| `90_RUNTIME` | log·cache·out·tmp·private mount | `var`, `tmp` |
| `99_ARCHIVE` | 읽기 전용 구 세대 | root legacy ADR, `data/_archive`, `docs/archive` |

`service.py`는 GENOS code-serving 계약 때문에 루트에 남는다. Python 패키지는
최종적으로 `02_BACKEND/lawrag`에 있지만 import 이름은 계속 `lawrag.*`다.

## 4. 데이터 패키지와 조합

데이터의 내용 출처와 생성 장소를 혼합하지 않는다.

| 축 | 허용값 예 |
|---|---|
| `source_origin` | `public_external`, `restricted_internal`, `curated_shared`, `synthetic` |
| `security_class` | `public`, `internal`, `restricted` |
| `representation` | `real`, `mock` |
| `authority` | `authoritative`, `curated`, `observation`, `evaluation` |
| `build.execution_site` | `outside`, `genos` |
| artifact `role` | `raw`, `structure`, `observation`, `semantic`, `relation`, `lexical_index`, `vector_index`, `evaluation` |

모든 패키지는 `dataset-package-v2`를 사용하며 `SourceSet`이 여러 패키지를
선택한다. 시스템은 물리 파일을 합치지 않고 `UnifiedCorpusView`로 논리적으로
합성한다. 모든 hit·RuleBundle·답변 trace는 `dataset_id/version_id/build_id/package_id`를
보존한다.

서로 다른 hash의 동일 `logical_id+role`은 기본적으로 충돌이다. 여러 버전을 같이
검색하려면 `keep_namespaced`, 대체하려면 소스셋에 우선순위를 명시해야 한다.
제한 패키지가 하나라도 선택되면 조합물은 exportable이 아니다.

## 5. 실험과 승격

```text
04_EXPERIMENTS/EXPERIMENTS/<ADR-ID>/
  SPEC/          가설·기준·dataset/source-set hash
  ARMS/          baseline/candidate 차이
  RUNS/          exact input/output/usage/latency/stage ledger
  DECISION/      Accepted/Rejected/롤백
```

- 완료된 기존 ADR은 path/hash가 계보이므로 다시 쓰거나 일괄 이동하지 않는다.
- 새 실험 저장소는 ID resolver를 거치고, legacy `docs/adr` resolver를 병행한 뒤 이행한다.
- research candidate는 production runtime에서 import할 수 없다.
- OOS·회귀·비용 게이트와 명시 승인을 통과한 release만 GENOS 프로파일이 선택한다.

## 6. 피드백과 숏컷

```text
FeedbackEvent
  → Diagnosis
  → ChangeCandidate
  → ExperimentRun
  → Approval
  → Promotion
  → Release
```

숏컷은 예전 답변을 저장하지 않고 검증된 검색 경로를 저장한다.

```text
QuerySignature
  → source_set_hash + authority_generation + semantic_generation 일치
  → reviewed shortcut
  → pinned Rule/Proviso/Relation landing
  → 현행 RuleBundle 재조립
```

세대·법령버전·소스셋이 다르면 숏컷은 즉시 stale이다. 피드백은 canonical
데이터를 즉시 수정하지 않고 항상 candidate를 만든다.

## 7. GENOS release

```text
outside build
  → signed/hash-fixed package
  → GENOS QUARANTINE
  → schema/hash/ACL/code compatibility validation
  → immutable install generation
  → internal restricted package build
  → SourceSet compose
  → graph/index build keyed by source_set_hash
  → smoke + provenance/access audit
  → ACTIVE_RELEASE.json atomic pointer swap
```

불변 `release-manifest-v1`은 code package, MAIN generation, SourceSet,
semantic/authority generation, lexical/vector index fingerprint를 하나의 hash 단위로
묶는다. `release-activation-plan-v1`은 그 manifest hash와 schema/hash/ACL/smoke/
provenance receipt, 현재 active pointer generation/hash, 롤백 release ID를 묶는다.
SourceSet을 별도 active 포인터로 두지 않고 `ACTIVE_RELEASE`에 고정해
코드·데이터·그래프·인덱스 split-brain을 막는다.

롤백은 파일 복사가 아니라 이전 `ACTIVE_RELEASE` 포인터를 새 세대로 발행하는
방식으로 한다. vector index도 `source_set_hash + embedding_model_fingerprint`를 키로
삼아 다른 조합의 index를 재사용하지 않는다.

활성화된 release는 불변·조회 전용이다. 질문·비교·검색만 serving plane에서
허용하고, upload·피드백 적용·조회 외 API·인덱스 재생성은 authoring/control
plane이 새 DatasetPackage·SemanticGeneration·Release를 만드는 방식으로만
처리한다. runtime binding 문서의 자기 서명만 믿지 않고, release manifest가
예상한 code·MAIN·SourceSet·semantic·index live bytes와 대조한다.

## 8. 이행 단계

1. `bridge`: 중앙 경로 API·패키지·소스셋·숏컷 계약을 추가하고 v1 물리 경로를 보존한다.
2. `reference-cutover`: 모든 하드코딩 경로와 `scripts.*` import를 중앙 API로 교체한다.
3. `copy-verify-0`: 새 폴더로 복사하고 live hash·readiness를 검증하되 아직 읽기 전환은 하지 않는다.
4. `dual-read`: 검증된 양쪽을 읽어 구조·회수·ACL·provenance를 비교하고 SourceSet을 OOS 검증한다.
5. `activate-v2`: receipt를 남기고 `LAWRAG_LAYOUT_VERSION=v2`를 원자적으로 전환한다.
6. `retire-v1`: 일정 기간 롤백 가능 상태를 거친 뒤 lowercase root를 제거한다.

현재는 1단계다. 완료 ADR·대용량 데이터·더티 워크트리를 즉시 물리
이동하는 것은 계보·사용자 변경·GENOS 경로를 파괴하므로 금지한다.

# Legal Graph v1

`legal-graph-v1`은 기존 구조 트리와 검색 관계를 덮어쓰지 않는 immutable sidecar다.
한 세대 안에서 법령 버전, 하위 조문 좌표, 추출 관측, 승인된 assertion, 검색용 projection을
분리한다. ADR-0103의 compiler-v3는 typed semantic entity와 모든 현행 하위 단위의
source-only landing card까지 생성한다. 제품 검색 경로는 배선됐지만 검증 스위치는 기본 OFF다.

## 1. 계층과 정본 경계

| 계층 | 주요 record | 의미 |
|---|---|---|
| canonical | instrument/provision/structural unit, semantic concept, rule/relation assertion | 버전과 근거를 가진 정본 또는 명시적으로 표시된 legacy 이관값 |
| observation | definition/frame/requirement/relation observation, unresolved relation | 파서·모델·원천에서 관측했지만 법적 진실로 자동 승격하지 않는 값 |
| projection | ProvisionCard, ClosureProjection, legacy relation view | 정본과 관측으로부터 언제든 다시 만들 수 있는 검색 view |
| runtime | QueryFrame, activation, bundle, trace | 질문별 판단. immutable corpus 세대에는 쓰지 않음 |

Frame과 정규식 정의·Requirement는 정확한 원문 위치를 가질 수 있어도 observation이다.
정확한 위치는 의미 승인을 뜻하지 않는다. 기존 active Frame assertion은 원래 승인·출처를
보존하되 `imported_active_unverified`/`LEGACY_BACKED`로 구별한다.

## 2. 좌표와 ID

관계의 정본 endpoint는 가능한 가장 깊은 실제 구조 단위다. 조 단위 좌표는 별도
`article_root` projection으로 함께 저장한다.

```text
법 제2조 제6호 나목  ── exact endpoint
법 제2조              ── article compatibility endpoint
```

허용 precision은 다음과 같다.

- `EXACT_SPAN`: 실재 node와 block, block-local `start/end`, quote SHA-256이 모두 확인됨
- `EXACT_UNIT`: 항·호·목을 포함한 실재 구조 node까지 확인됨
- `ARTICLE_FALLBACK`: 원천 시스템이 조 단위까지만 확정함
- `DOCUMENT_ONLY`: 대상 문서만 공식적으로 확인됨
- `UNRESOLVED`: 실재 좌표를 확정하지 못함

하위 node에 기존 `coordinate_key`가 없으면 원본을 수정하지 않고 공통
`LegalCoordinate`와 부모-자식 하강 결과를 v2 overlay로 저장한다. 없는 항·호·목을
추정해 만들지 않으며, 부분 해소 시 마지막 실재 prefix와 미해소 suffix를 남긴다.

모든 persistent ID는 `legal-graph-id-v1` canonical JSON의 SHA-256으로 만든다. 입력 순번,
절대 경로, 생성 시각은 semantic ID에 포함하지 않는다. 세대 ID는 compiler contract와
입력 파일 hash, authority generation으로 결정된다.

## 3. 엔티티와 assertion

compiler-v3가 원문 관측에서 승격하는 의미 엔티티의 닫힌 타입은 다음 8개다.

```text
FormulaExpression       QuantityConstraint      TemporalConstraint
DocumentRequirement     AuthorityAllocation     ClassificationCriterion
ExceptionAssertion      DefinitionSense
```

각 엔티티는 exact lower-unit source, Evidence, observation ID, RuleAssertion과 검색용
SemanticCard를 가진다. 원문에 직접 쓰이지 않은 부정 결론은 RelationAssertion으로 만들지 않고
근거 묶음과 `requires_review=true`를 가진 runtime `LegalAssessment`로 분리한다.

기존 Concept 전체를 `LegalEntity`로 바꾸지 않는다. 조직·사람·문서처럼 지속적 대상을
확정할 수 있을 때 LegalEntity/Revision을 만들고, `domain_term`과 `action`은 우선
`SemanticConcept` 및 legacy binding으로 보존한다. scoped term은 별도의 TermSense다.

RuleAssertion은 역할(`ACTOR`, `PREDICATE`, `OBJECT`, `TARGET`, `MODALITY`, `CONDITION`,
`EXCEPTION`, `METHOD`, `EFFECT`, `FUNCTION`)과 source/evidence를 분리한다. RelationAssertion은
항상 직접 방향 하나만 canonical로 저장한다. inverse, `implemented_by`, `defined_by`,
`threshold_of` 같은 소비자 편의 방향은 projection이다.

관계 predicate는 다음 family로 제한한다.

- 규범: `REGULATES_ACTION`, `ALLOCATES_AUTHORITY`, `REQUIRES_SUBMISSION_OF`,
  `COMPUTES_VALUE`, `TRIGGERS_WHEN_THRESHOLD_MET`
- 정의·분류: `DEFINES`, `ALIASES_AS`, `SETS_CLASSIFICATION_CRITERIA_FOR`
- 입법 연결: `LEGISLATIVE_DELEGATION`, `LEGISLATIVE_REDELEGATION`,
  `SUPPLEMENTS_BY_ADMINISTRATIVE_RULE`
- 권한·업무: `DELEGATES_ADMINISTRATIVE_AUTHORITY`, `ENTRUSTS_TASK`,
  `APPOINTS_TO_POSITION`, `ALLOCATES_INTERNAL_APPROVAL`
- 규칙 사용: `DIRECTLY_APPLIES`, `INCORPORATES_MUTATIS_MUTANDIS`,
  `FOLLOWS_EXAMPLE_OF`, `DEPENDS_ON_REQUIREMENTS_OF`, `LEGAL_BASIS_IN`, `REFERENCES`
- 한정·우선: `QUALIFIES_RULE`, `EXCEPTION_TO`, `EXCLUDES_APPLICATION_OF`,
  `OVERRIDES_NOTWITHSTANDING`, `FALLBACK_TO`, `EXPLICIT_PRIORITY_OVER`
- 법적 효과·시점·제재·개정: `DEEMS_AS`, `PRESUMES_AS`, `SUBSTITUTES_FOR`,
  `EXEMPTS_FROM`, `ALLOWS_OMISSION_OF`, temporal predicates, sanction predicates,
  `AMENDS`, `SUPERSEDES`, `REPEALS`

입법 위임과 행정권한 위임, 업무 위탁은 서로 다른 predicate다. “위임”이라는 표면형만으로
셋을 합치지 않는다.

## 4. 원천 accounting과 관계 생성

생성기는 다음 순서를 따른다.

1. `law_index`와 154개 structure 문서의 authority generation을 고정한다.
2. 모든 문서·node를 versioned structural unit으로 만들고 현행 139문서의 모든 article에
   sparse ProvisionCard를 만든다.
3. canonical registry는 semantic concept, taxonomy, legacy-backed RuleAssertion으로 이관한다.
4. definition, frame, Requirement는 observation으로 저장한다.
5. source-backed definition/frame/requirement observation을 8개 typed LegalEntity,
   RuleAssertion, Requirement/TermSense, typed RelationAssertion으로 승격한다.
6. 관측이 없는 현행 조·항·호·목에도 `STRUCTURE_ONLY` SemanticCard를 만든다. 이 카드는
   원문 landing projection일 뿐 LegalEntity나 법적 assertion을 주장하지 않는다.
7. `refs.py`와 `delegation.json`의 모든 raw row를 RelationObservation으로 저장하고 exact
   endpoint를 재해소한다.
8. source-backed RelationAssertion을 만들고, 현재 RelationBundle key 중 덮이지 않은 항목만
   `ARTICLE_FALLBACK` compatibility assertion으로 보충한다.
9. assertion에서 ClosureProjection을 파생한 뒤 조 단위로 접어 현행 RelationBundle과 대조한다.
10. 독립 validator를 통과한 staging 세대만 원자적으로 게시하고 `CURRENT.json`을 교체한다.

모든 raw relation observation은 정확히 하나의 terminal disposition을 갖는다.

```text
mapped | support_only | unresolved | suppressed | out_of_contract | parse_error
```

한 observation이 여러 assertion을 지지하는 것은 별도 many-to-many link로 표현한다. 중복
assertion을 병합하더라도 raw observation을 삭제하지 않는다.

## 5. 검색에서의 사용 계약

ProvisionCard는 조문 자체의 두 번째 정본이 아니다. 구조 좌표, definition/requirement
관측, proposition 참조, incoming/outgoing projection ID, coverage만 담는 sparse view다.

```yaml
facets:
  definition_observation_ids: []
  frame_observation_ids: []
  requirement_observation_ids: []
  legacy_rule_assertion_ids: []
  relation_assertion_ids: []
  unresolved_relation_ids: []       # exact source를 가진 미해소 관계만
relation_ports:
  outgoing_projection_ids: []       # 이 조문 아래 exact endpoint에서 출발
  incoming_projection_ids: []       # 이 조문 아래 exact endpoint로 도착
coverage:
  semantic_status: ENRICHED | SPARSE
  frame_status: AVAILABLE | NOT_EXTRACTED
```

facet과 port는 ID만 저장하며 정본 payload를 복제하지 않는다. source와 target이 같은 조문인
self-edge는 양쪽 port에 나타나지만 `relation_assertion_ids`에서는 한 번만 나타난다. 하위
항·호·목의 방향성은 RelationAssertion에 그대로 남고 ProvisionCard에서만 article root로 fold한다.

`legal_semantic_entity_search` 스위치를 켠 검색기는 다음 절차로 sidecar를 사용한다.

```text
질문 → 다축 QueryFrame → SemanticCard의 항·호·목 landing
     → 기존 LegalClosure floor와 candidate union
     → source-backed typed closure(최대 2-hop)
     → protected DecisionBundle → bounded final rerank
     → 직접 규칙 또는 reviewable LegalAssessment
```

`LEGISLATIVE_DELEGATION`은 source endpoint가 질문의 판단 요소와 관련될 때 규칙 완성을 위해
따라간다. 전역 mandatory 확장은 금지한다. 최종 20개가 찬 경우 상위 12개 floor를 보호하고
최대 4개만 source-backed 후보로 교체한다. invalid/stale/missing generation이나 stage-ledger
병합 오류는 기존 floor로 fail-open한다. ADR-0103 인샘플 기준을 통과하지 못했으므로 스위치는
기본 OFF이며 MAIN 승격도 하지 않는다.

활성화 예시는 다음과 같다.

| 관계 | closure class | 활성화 조건 예 |
|---|---|---|
| 입법 위임 | rule completion | 질문이 위임 문구가 맡긴 기준·범위를 요구함 |
| 준용 | borrowed rule | 준용 span이 선택된 규칙의 판단에 필요함 |
| 배제·예외 | qualifier pair | host rule 또는 배제 span이 관련됨 |
| 정의 적용 | definition scope | term이 질문/선택 조문에 있고 scope가 유효함 |
| 제재 | sanction lookup | 위반 결과·제재 의도가 있음 |
| 부칙 | temporal lookup | 시행일·적용례·경과조치 의도가 있음 |
| 일반 인용 | navigational | target relevance가 확인됨 |

## 6. 검증과 운영

필수 gate는 다음과 같다.

- 모든 manifest artifact의 hash, bytes, row count 일치
- generation/authority generation 혼합 0
- 154문서·170,931 node accounting, 현행 article card 17,365개,
  `STRUCTURE_ONLY` 하위 단위 카드 82,108개
- source-backed semantic entity/card 94,247개와 8개 타입별 cardinality
- dangling entity/evidence/endpoint/projection 참조 0
- exact span의 block substring과 quote SHA-256 일치
- raw observation terminal partition 완전성 및 silent drop 0
- closure compatibility fold와 기존 89,474개 section relation key의 완전 일치
- candidate projection은 `NEVER_REQUIRED`, 모든 projection은 `runtime_wired=false`
- 동일 입력 두 빌드의 generation/content hash 동일

생성 실패 시 `CURRENT.json`을 바꾸지 않는다. 롤백은 이전 generation을 가리키도록 pointer만
되돌리는 방식이며, 기존 structure·canonical·delegation·검색 MAIN 파일은 수정하지 않는다.

## 7. 저장 위치와 재생성

```text
data/legal_graph/
├─ CURRENT.json
└─ generations/<generation_id>/
   ├─ manifest.json
   ├─ source_accounting.json
   ├─ canonical/*.jsonl.gz
   ├─ observations/*.jsonl.gz
   ├─ projections/*.jsonl.gz
   └─ validation/summary.json
```

실행 가능한 스키마 계약은 `lawrag/core/legal_graph/model.py`에 있고 각 row와 manifest는
`schema_version=legal-graph-v1` 및 compiler contract를 고정한다.

대용량 JSONL은 deterministic gzip(`mtime=0`)으로 저장한다. manifest의 physical path는
`.jsonl.gz`이고 `logical_path`, row count, bytes, SHA-256, compression을 함께 기록한다.
validator는 압축 여부와 무관하게 logical artifact 계약을 검사한다.

```bash
.venv/bin/python scripts/build_legal_graph_v1.py build \
  --structure-store data/structure

.venv/bin/python scripts/build_legal_graph_v1.py validate \
  --structure-store data/structure
```

동일 입력·compiler contract·projection policy이면 generation ID와 모든 artifact byte가 같아야
한다. 이미 존재하는 동일 세대는 검증 후 `reused=true`로 재사용하며, 같은 ID에 다른 manifest가
나오면 immutable generation conflict로 실패한다.

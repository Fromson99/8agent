# 데이터·처리 계약

[전체 설계](README.md) · 아래 schema·테이블·신규 메서드·설정 이름은 모두 제안이다. 현재 실행 가능한 계약과 혼동하지 않는다.

## 1. 논리 저장소와 정본

| 저장 영역 | 정본 책임 | 저장 내용 | 쓰기 주체 |
|---|---|---|---|
| shortcut DB | 수신 기록, 사건 현재 상태, 연결·정정, 지식 revision·게시 상태 | 아래 제안 테이블 | 인증된 repository 서비스 |
| native WorkRepository journal | 실제 실행 내역 | 모델 호출, 도구 입력·출력, 증거 span, 단계 판단 | 기존 legal_agent 실행기 |
| artifact 저장소 | 크기가 큰 불변 payload | 도구 원결과·첨부·export, 길이·해시·저장 위치 manifest | artifact writer |
| 기존 원문·용어 generation | 법령·내규·용어 원문 | 원문 및 구조·용어·색인 | 기존 MAIN 구축 파이프라인 |
| wiki projection·검색 색인 | 재생성 가능한 조회본 | Markdown, JSON, 용어·쟁점 검색 색인 | compiler/projector |

shortcut은 하나의 **논리 시스템**이다. 기존 native journal을 통째로 DB에 복사할 필요는 없다. 영속성·보존 정책이 보장된 참조로 소유 관계를 연결한다. journal 정리 전에 참조된 실행을 불변 artifact로 이전하고 참조 해소를 확인한다.

로컬 경로는 `load_layout(root).path('runtime') / 'semantic'`을 기준으로 해결한다. 제안 새 DB는 그 아래 `case-memory/cases-v4.sqlite`, artifact는 `case-memory/artifacts`, 위키는 `case-memory/wikis/<scope-id>/<build-id>`다. `v4`는 사건 DB 스키마 세대이며 agent v6 또는 릴리스 세대와 별개다. GENOS는 같은 논리 runtime을 배포 설정으로 해결한다.

첫 적용은 단일 writer와 로컬 내구 디스크를 전제로 한다. NFS는 검증된 snapshot·artifact 교환 용도로 제한한다. 이 조건이 현장에 없으면 writer 서비스 또는 트랜잭션 DB를 확보하기 전 저장 활성화를 보류한다. NFS의 DELETE journal 사용만으로 다중 호스트 안전성을 인증하지 않는다. DB가 달라져도 아래 repository 계약·이벤트 ID는 유지한다.

## 2. 식별자와 사건·개념의 관계

```text
tenant/principal
  ├─ session ─ turn ─ request ─ run
  └─ investigation(사건/업무) ─ branch(대화 갈래) ─ issue(쟁점)
       ↕ session_investigation / event_assignment
shortcut events·fact revisions·judgment refs·tool traces
       ↕ knowledge_member(정확한 기록 범위와 역할)
legal_wiki knowledge_unit ─ revision ─ claim / procedure / source dependencies
       ↕ concept_membership
검토된 용어·개념 또는 미승인 발견 후보
```

한 session은 여러 investigation을 다룰 수 있고, 한 investigation은 여러 session에 걸친다. 한 turn에도 여러 쟁점이 있을 수 있다. 사건 ID와 지식 단위 ID를 동일시하지 않는다. 같은 법률 개념을 사용하는 별개 사건은 끝까지 독립적인 사실 revision을 가진다.

분류 전 수신 이벤트는 session/intake aggregate에 기록한다. 이후 사건·갈래 배정은 별도 관계 이벤트로 추가하며 원이벤트를 다른 aggregate로 옮기지 않는다. 온라인 issue 배정은 대화를 이어가기 위한 임시 작업 구분이다. legal_wiki의 의미 단위 분절·결합은 그 배정을 참고하되 새 revision으로 조정할 수 있다. 저장 전에 개념 분절이 끝나야 하는 의존 관계를 만들지 않는다.

모든 ID는 scope가 있는 불투명 식별자다. 의미가 같은 질문이라는 이유로 내용 해시를 사건 ID로 쓰지 않는다. 클라이언트의 사건 ID는 힌트이며 서버가 권한·revision·소속을 검사한다. 이름·회사명만으로 사건을 자동 합치지 않는다.

## 3. 제안 테이블과 필수 계약

`tenant_id`, `visibility_policy_id`, `created_at`, schema version은 해당 행/상위 aggregate에서 명시적으로 상속한다. 관계와 해시만으로 접근권한을 추정하지 않는다.

| 테이블/aggregate | 핵심 필드·제약 | 사용처 |
|---|---|---|
| intake_request | scope, session_id, request_id, input_hash, status; 논리 요청 키 UNIQUE | 모델 호출 전 수신·재시도 |
| memory_event | event_id, aggregate_id, seq, type, actor, payload_ref/hash, request/run, recorded_at, occurred_at, causation_id; aggregate+seq UNIQUE, append-only | 원발언·정정·연결·게시 이력 |
| investigation | id, scope, current_revision, title, status | 세션을 넘는 같은 업무 |
| session_investigation | session_id, investigation_id, valid_from_event, detached_event | 세션의 사건 연결 이력 |
| branch / issue | id, investigation_id, parent_branch, question, scope_constraints, status | 갈래·쟁점 분리 |
| event_assignment | event_id, text_range, branch/issue_id, relation, revision, proposal/review state | 발언의 일부만 해당 쟁점에 배정 |
| fact_revision | fact_id, revision, subject_id, predicate, typed_value, unit, valid_time, asserted_event, scope, supersedes, status | 정정·조건 비교 |
| judgment_ref | ref_id, run/entity/version, payload_hash, issue_id, fact_revision_refs, rationale_ref, source_refs | 기존 native 판단 연결 |
| tool_trace_ref | action_id, journal_ref, tool_schema_hash, purpose_ref, request/result hashes, status, evidence_refs | 실제 실행 기록 |
| relation_revision | from/to ref, type, version, reason, supporting_events, status | continues, corrects, contradicts, same_topic 등 |
| knowledge_unit / revision | stable id, revision, topic, jurisdiction, applicable_time, scope, lifecycle, completeness, verification_refs, body_hash | legal_wiki 정본 |
| knowledge_member | unit_revision, event/judgment/fact/source ref, exact span/version, role | 원기록 추적 및 중복 없는 참조 |
| knowledge_claim | unit_revision, claim_id, statement, condition_expr, exception_checks, evidence_refs, rationale, unresolved | 주장 단위 조건·근거 |
| procedure_revision | id/revision, inputs, preconditions, typed steps, branches, stop/reentry rules, tool_contract_refs | 다음 실행의 조사 절차 |
| dependency | dependent_revision, dependency_ref/version/hash, effect, usage_role | 정정·원문 변경 영향 계산 |
| verification_receipt | 대상 revision/hash, 검사 종류·정책·검사자·근거·결과·시점, expiry/change triggers | 검증 범위 추적 |
| reuse_receipt | request, unit_revision, mode, current conditions/source/permission checks, adopted refs, rejected reasons | 실제 사용과 출처 설명 |
| outbox / consumer_cursor | event, consumer, dedup key, status, lease, retries, watermark | wiki 구성·색인·복구 |
| build_manifest / import_receipt | source watermark, input hashes, compiler/model/prompt/schema/policy, outputs, status | 재현·이행·롤백 |

DB 제약은 외래키, 복합 scope 검사, 불변 기록 갱신 금지, head 전환의 expected_revision 비교를 포함한다. FK만으로 다른 tenant 참조를 막을 수 없으므로 복합키 또는 repository의 동일 트랜잭션 검사로 강제한다. seq는 aggregate 내 순서이며 전역 동시 이벤트의 시간순을 의미하지 않는다.

우선 색인은 `(scope, session, request)`, `(scope, investigation, revision)`, `(aggregate, seq)`, `(issue, status)`, dependency의 양방향 ref, `(scope, concept, lifecycle)`, outbox `(consumer,status,next_attempt)`에 둔다. 제목·질문·용어 표면 검색은 파생 색인에서 처리하되 반환 후 정본 권한·현재성을 재확인한다.

## 4. 기록 예시와 판단 설명

다음은 합성 예시다. 실제 사용자 데이터나 실행 완료 증거가 아니다.

```json
{
  "schema_version": "shortcut-event-v1-proposed",
  "event_id": "ev-demo-004",
  "scope_id": "private-demo",
  "aggregate_id": "case-demo-a",
  "seq": 4,
  "type": "FACT_CORRECTED",
  "actor": {"kind": "user", "principal_id": "user-demo"},
  "session_id": "session-demo-2",
  "request_id": "request-demo-4",
  "expected_revision": 3,
  "payload": {
    "utterance": "아까 그 투자자의 취득 시점은 18개월 전이 아니라 8개월 전이야.",
    "target_fact": {"id": "fact-demo-holding", "revision": 1},
    "new_value": {"kind": "duration", "value": 8, "unit": "month"},
    "applicability": {"investigation_id": "case-demo-a", "subject_id": "investor-demo-b"},
    "reason_source": "explicit_user_correction"
  },
  "causation_id": "ev-demo-001"
}
```

원발언은 그대로 보존하고 실제 계산용으로는 취득일·판정 기준일·달력 규칙을 별도 정규화한다. “8개월”만으로 정확한 날짜를 만들어 내지 않는다. fact의 상태는 `USER_ASSERTED`, `DOCUMENT_SUPPORTED`, `DISPUTED`, `SUPERSEDED` 등을 구분하며 사용자 진술이 법적 자격 증명을 자동 대신하지 않는다.

사실이 원래 잘못됐다는 정정과 실제 세계에서 이후 바뀐 상태를 구별한다. 예를 들어 직장이 바뀌었다면 이전 재직 사실을 오답으로 지우지 않고 유효기간을 나눈다. 회고 시점의 질문은 그 시점에 맞는 사실·규정 버전으로 해석한다.

판단에는 `question`, `conditions_used`, `adopted_evidence`, `interpretation_point`, `reason_summary`, `rejected_alternatives`, `limitations`를 구조화한다. 해석 지점은 예를 들어 “제3호 단서로 빠지는 것과 제4호 요건에 해당하는 것은 별도 검사”다. 저장하는 것은 모델이 출력한 검토 가능한 설명·증거·선택 사유다. 출력되지 않은 내부 추론을 추정해 채우지 않는다. 과거 기록에 이유가 없으면 `NOT_RECORDED`로 보존하고 절차·판단 재사용 등급을 제한한다.

## 5. 상태는 여러 축으로 관리

| 축 | 상태 예시 | 변경 주체·효과 |
|---|---|---|
| 수신/실행 | RECEIVED, RUNNING, COMPLETED, FAILED, INTERRUPTED | 실행기; 실패도 기록 유지 |
| 사실·연결 | ASSERTED, SUPPORTED, DISPUTED, SUPERSEDED | 정정 처리기·검증기 |
| 서사 완결성 | OPEN, BOUNDED, CLOSED_CANDIDATE | compiler 제안 + 필수 항목 검사 |
| 사용자 확인 | NONE 또는 confirmation_event_ref + 확인 범위 | 사용자의 명시 발언 해석 |
| 검증 | STRUCTURE, SOURCE, INTERPRETATION 별 PASS/FAIL/UNKNOWN | 검사 영수증; 단일 confidence 점수로 합치지 않음 |
| 지식 수명 | DRAFT, PUBLISHED, STALE, DISPUTED, RETIRED | compiler/publisher 및 변경 감지 |
| 접근 범위 | PRIVATE, CASE_SHARED, TEAM_REVIEWED, PUBLIC_APPROVED | 인증·공유 정책; 모델이 확대 못 함 |
| 사용 모드 | NONE, HINT, PROCEDURE, JUDGMENT | 요청 시 정책 평가 결과 |

`PUBLISHED`는 지정 범위에 조회할 수 있다는 뜻이다. 모든 사용 모드가 열리거나 공통 법률 정답으로 승인됐다는 뜻이 아니다. 사용자 확인이 없어도 증거가 있는 절차 후보를 만들 수 있다. 사용자가 확인해도 법령명·예외 검증이 실패하면 판단 재사용은 허용하지 않는다.

## 6. 온라인 실행 순서와 커밋 경계

1. 기존 인증 adapter/HMAC으로 principal·팀·문서·반출 범위를 정한다. 인증 없는 세션은 임시 범위로 격리하고 개인 기록 조회·세션 간 연결을 허용하지 않는다.
2. `intake_request`와 `UTTERANCE_RECEIVED`를 같은 트랜잭션에 저장한다. 같은 키·같은 입력은 이어가기 또는 완료 응답 조회, 다른 입력은 충돌이다. 수신 저장 실패는 성공 접수로 응답하지 않는다.
3. 현재 사건 후보·명시 참조를 조회하고 사건/갈래 배정을 제안한다. 구조·권한을 코드로 검사한다. 모호한 정정은 `ASSIGNMENT_PENDING`으로 남기며 임의의 사실을 수정하지 않는다.
4. 필요한 사건 aggregate를 ID 순서로 잠그고 expected_revision으로 상태·정정·무효화·outbox를 원자 갱신한다. LLM·외부 도구 호출 동안 DB 잠금을 잡지 않는다.
5. legal_wiki 후보를 예산 내 탐색하고, 적용 검사 후 사용 계획과 `reuse_receipt`를 저장한다.
6. 기존 INTENT→PLAN→RECALL→READ→SELECT→ASSESS→COMPOSE의 필요한 지점에 진입한다. 각 도구를 호출하기 전에 action을 예약하고 이후 결과·실패를 기록한다.
7. native 판단·증거 artifact가 내구 저장된 뒤 shortcut에 참조를 수락한다. 당시 사건 revision과 사용한 지식·원문·권한을 게시 직전에 재확인한다. 중간 정정이 있었으면 늦은 결과를 이력으로 보존하고 현재 답변으로 게시하지 않는다.
8. 답변 참조와 outbox를 shortcut 트랜잭션에 커밋하고 기존 publication 경로로 내보낸다. 게시 실패는 동일 answer_id로 재시도한다. 미완료 스트림은 provisional로 취급하고 완료 receipt 전 확정 기억으로 만들지 않는다.

native journal·artifact·shortcut DB 사이의 분산 트랜잭션을 가정하지 않는다. 실행 ID와 hash 기반 reconciliation으로 미수락 결과를 찾는다. native 저장 후 shortcut 커밋 전 종료되면 해당 실행을 재검사해 수락하거나 orphan으로 남긴다. shortcut 커밋 후 응답 전 종료되면 모델을 재호출하지 않고 커밋된 답변을 회수한다. 참조 artifact가 없으면 게시와 재사용을 차단한다.

## 7. 중복·겹침·정정의 처리

“겹침 없이”는 의미가 비슷한 모든 기록을 하나로 합친다는 뜻으로 구현하지 않는다.

- 전송 중복: 요청 키·입력 hash로 한 번만 수신한다.
- artifact 중복: 허용 scope 안에서 같은 내용 hash의 바이트를 공유한다. 다른 권한 영역 간 존재 여부는 노출하지 않는다.
- 사실 정정: 동일 subject·predicate·유효시점·사건 범위인지 먼저 검사한다. 다른 사건의 같은 표현은 독립 사실이다.
- 같은 사건 연결: 명시 선택 또는 충분한 식별 근거가 있는 경우 연결 이벤트를 남긴다. 애매하면 후보만 유지한다.
- 같은 주제: `SAME_TOPIC` 연결로 표현한다. 사건 병합·사실 상속을 일으키지 않는다.
- 여러 지식의 공통 근거: 원본 한 개에 여러 membership을 둔다. 의도된 참조 중복이다.
- 잘못된 병합: 과거 연결을 삭제하지 않고 철회 revision과 분리 매핑을 만들며 파생 지식을 다시 구성한다.

정정 처리기는 `FACT_CORRECTED`, `EVIDENCE_REVOKED`, `SOURCE_CHANGED`, `LINK_RETRACTED`, `INTERPRETATION_DISPUTED`별 의존 그래프를 순회한다. 실제 판단에 사용한 연결은 해당 주장과 하위 답변을 STALE로 만든다. 탐색 힌트만 사용하고 원문에서 독립적으로 판단한 답변에는 잘못된 사실 상속을 적용하지 않는다. 정책 변경 등 판단에 영향을 주는 의존은 별도 등록한다. 알려진 미해결 의존이 있으면 안전한 사용 모드로 내리거나 재조사한다.

큰 의존 그래프 전체를 한 쓰기 트랜잭션에서 수정하지 않는다. 원본 revision 변경과 invalidation epoch·outbox를 먼저 커밋하고 후속 전파는 배치로 처리한다. 전파가 완료되지 않은 동안에도 조회·게시에서 의존 원본 revision과 검사 watermark를 대조하므로 오래된 파생 결과를 현재본으로 쓸 수 없다. 재사용 gate를 통과한 검사 결과는 요청 내에서도 해당 revision에만 유효하다.

## 8. legal_wiki compiler

compiler는 기존 야간 작업 진입점의 소비자 모듈로 구현한다. 작업자 이름은 새 논리 역할이며 별도 봇·독립 서버 증설을 요구하지 않는다.

모델 transport는 현재 선택 환경의 공통 adapter를 주입한다. 내부 대화의 분류·요약·지식 구성·검증은 GENOS 내부 모델로 처리하고, 과거 action-memory의 공개 외부 모델 생성기를 비공개 기록에 그대로 연결하지 않는다. 반출 가능성은 모든 입력 member의 정책 교집합으로 확인한다. 모델·정책·예산이 없거나 부적합하면 MODEL_UNAVAILABLE로 작업을 남기며 외부 provider로 자동 전환하지 않는다.

1. **변경 묶음 고정:** outbox watermark와 대상 사건 revision을 고정한다. 처음부터 모든 대화를 다시 읽지 않는다.
2. **기록 수집:** 원발언 span, 정정, 현재 사실, 도구 실행, 채택/제외 근거, 주장, 열린 질문을 수집한다. 제외된 예전 결론도 오류 학습용 역할을 붙여 보존한다.
3. **분절 제안:** 질문·조건·결론이 독립적으로 설명되는 최소 쟁점 단위를 제안한다. 문장 수·시간·세션 경계로 자르지 않는다. 필수 맥락의 dependency를 포함한다.
4. **기존 단위와 비교:** 같은 topic/조건/시점·규정 버전의 단위에 추가·수정할지, 조건 변형·새 쟁점·상충 단위로 남길지 제안한다. 병합 후보는 근거와 반례를 함께 출력한다.
5. **완결성 확인:** 필요한 사실, 참조 규정, 위임·예외, 열린 질문을 구조화한 checklist로 검사한다. 결론이 달라지는 미확인 조건은 조건부 분기를 만들거나 OPEN으로 남긴다.
6. **증거·해석 검사:** source adapter가 문서명·좌표·인용·버전을 검증한다. 적용 요건·예외 해석은 별도 verifier 또는 담당 검토자의 영수증을 요구한다. LLM 검토만 수행한 경우 그 한계를 그대로 표시한다.
7. **범위 검사:** 모든 member의 접근 정책을 만족하는 독자에게만 노출한다. 개인 사례에서 공통 규칙을 만들 때는 개인 사실 제거와 별도 공개/공유 검토를 거친다.
8. **새 revision 저장:** 입력 hash, compiler/model/prompt/policy hash, 변경 이유, lineage, 완결성·검증 상태를 저장한다. 입력 이후 정정이 있으면 현재본 게시를 거부하고 재큐잉한다.
9. **게시·색인:** 정본 head를 조건부 전환하고 projection outbox를 발행한다. Markdown·검색은 성공한 build manifest에 원자적으로 연결한다. 실패 시 기존 유효 projection을 유지한다.

재현은 같은 결과 텍스트의 재생성을 보장한다는 뜻이 아니다. 동일 입력·설정·실제 모델 출력과 소비 경로를 추적할 수 있게 한다. 모델 비결정성은 기록한다.

한 지식 단위는 `질문/개념 → 적용 범위 → 조건/예외 → 해석·주장 → 원문 → 절차 → 실제 사례 참조 → 정정 이력 → 미해결점`으로 표현한다. 조건이 다른 결론은 variants로 유지한다. 기존 검토된 용어 ID는 사용하되 새 개념은 DISCOVERY로 남긴다.

compiler의 구조화 출력은 `units`, `members`, `claims`, `procedures`, `relations`, `unassigned_spans`, `conflicts`, `completeness_checks`를 필수 top-level 항목으로 둔다. 모든 주장에 입력 범위 내 참조를 요구하고, 존재하지 않는 사건·source·tool ID, 순환하는 실행 절차, scope 확대를 거부한다. 같은 span의 다중 membership은 역할과 공유 이유가 있으면 허용한다. 분절되지 않은 부분을 버리지 않고 `unassigned_spans`로 남긴다. 의미상 분절·병합이 적절한지는 이 구조 검사와 별도의 검토·평가 대상이다.

## 9. 실제 도구 기록과 재사용 절차

| 실제 실행 기록 | 다음에 쓰는 절차 |
|---|---|
| 당시 tool name/schema, 실제 arguments, 실행 이유, 결과·오류·지연, 채택한 증거 | tool contract, parameter schema, 사전 조건, 입력 매핑, 분기 조건, 예상 결과 검증, 중단/재조사 지점 |
| 일시적인 native source handle도 원래 모습으로 보존 | durable document ID·generation·unit/block/span·hash에서 현재 handle을 다시 발급 |
| 잘못된 실행도 역사로 보존 | 검토를 통과한 단계만 실행 가능 |

예: `현재 문서 찾기 → 해당 조항 읽기 → 정의·위임 조항 읽기 → 단서 검사 → 별도 적용 조항 검사 → 누락 조건 질문 → 주장과 원문 대조`를 절차로 저장한다. 각 단계에 왜 필요한지와 무엇을 확인해야 다음 단계로 갈 수 있는지 붙인다.

compiler는 도구를 발명하지 않고 실행기의 등록된 read-only tool catalogue에서 선택한다. 기록의 문자열이나 Markdown을 실행 코드로 취급하지 않는다. 입력 schema·권한·세대·도구 버전이 맞지 않으면 단계 실행을 거부하고 PLAN/RECALL로 돌아간다. 쓰기·전송 등 외부 효과 도구가 향후 추가되면 현행 권한과 중복 방지 계약을 별도로 적용한다.

## 10. 조회·재사용 정책

조회 순서는 `권한과 문서 범위 → 사건/쟁점/용어 검색 → 조건 비교 → 정확한 revision 조회 → 원문·의존 상태 검사 → 사용 모드 결정`이다. 임베딩은 선택 후보 탐색 수단이며 첫 구현 필수 의존성으로 두지 않는다. 기존 용어 기반 RAG 계약을 유지한다.

condition은 문자열 facts의 완전 일치 대신 typed field와 연산(`eq`, `in`, `before`, `duration_lt`, `all`, `any`)으로 표현한다. UNKNOWN을 FALSE 또는 TRUE로 바꾸지 않는다. 복잡한 법률 자격은 근거 있는 predicate와 검토 영수증으로 표현하고 수치 비교만으로 추론하지 않는다.

| 사용 모드 | 최소 통과 조건 | 실패 경로 |
|---|---|---|
| HINT | 권한, 출처 추적, 사용 금지/철회 상태 아님; 미검증 표시 | 후보 제외 또는 원문부터 탐색 |
| PROCEDURE | HINT + 도구 계약 검증 + 입력 매핑 + 적용 전제·중단 지점 | PLAN/RECALL 재계획 |
| JUDGMENT | 정확한 claim revision, 필요한 사실·조건 충족, 예외 확인, 원문 현재성, 해석 검증 정책 충족, disputed/stale 의존 없음 | 필요한 단계 재판단, 근거 부족 시 조건부 답변 |

원문이 같아도 법률 적용 시점이 달라지면 다시 검사한다. 코드 hash 하나가 바뀌었다고 모든 지식을 폐기하는 대신 영향받는 계약·정책별 의존을 검사하는 방향으로 바꾼다. 단, 호환성 검증 영수증이 없는 변경은 안전하게 재검증한다. 사용자 권한 철회는 캐시 만료를 기다리지 않고 조회·게시 시 차단한다.

## 11. 기존 API·CLI와의 연결

| 인터페이스 | 현재 | 제안 확장 |
|---|---|---|
| `/v1/rag/ask` | v6 pipeline·세션·요청 처리 | optional investigation_id/branch_id/expected_revision, 수신 상태·사건 ref·reuse receipt 반환; 기존 입력 호환 |
| `/v1/rag/memory/query` | experience, user_wiki, legal_wiki, questions, history | 사건·쟁점·knowledge revision·trace·변경 이력 조회 kind 추가, 동일 인증/페이지 제한 유지 |
| 기존 대화 정정 | resolver가 현재 goal 변경 | 서버가 event append와 영향 계산 수행; 별도 사용자 저장 명령 강요 없음 |
| `pipeline.py unified-memory migrate/status/wiki-rebuild` | v2/action-memory 이관·현황·projection | v3/native/legacy shortcut 명시 import, schema v4 이행, rebuild 검증·상태 확장 |
| `pipeline.py action-memory build/status` | 완료 journal 기반 야간 build | 명시 `--store-version`/`--mode` 제안으로 shortcut outbox 소비·wiki compiler 실행; 초기 기본은 기존 동작 유지 |

위 CLI 옵션·조회 kind는 아직 존재하지 않는다. 운영 명령처럼 그대로 실행하지 않는다. 구현 시 PIPELINE의 단계·스키마·생산자·소비자 선언과 실제 dispatch를 함께 변경하고 `WORKING_CODE_ONLY`/비활성 상태로 시작한다.

새 설정은 capture, compile, hint, procedure, judgment reuse를 각각 끄고 켤 수 있어야 한다. 기본 후보는 capture 검증 후 활성, compiler는 DRAFT 생성, JUDGMENT 재사용은 비활성이다. 구체적인 batch 크기·token/시간·저장 예산은 운영량 계측 후 고정한다. 기존 설정 상한을 처리량으로 해석하지 않는다.

API 확장은 응답 schema version으로 구분하고 기존 필드를 유지한다. trace·knowledge 조회에는 cursor와 허용 scope를 결속한다. 목록 페이지 제한 때문에 정확한 ID 조회가 실패하지 않도록 후보 검색과 get을 분리한다. 사용자에게 저장·재사용 여부를 설명하는 필드는 선택 정보이며 내부 원장 전체를 응답에 넣지 않는다.

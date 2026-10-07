# 에이전트 반복 판단·내부 탐색 구현안

- 상태: 구현 제안. 기존 제품 코드·활성 릴리스·진행 ADR을 변경하지 않았다.
- 기준: 2026-09-19, Git a3ac254cc8fba708e39cf37482707a5570fd388d 및 작업 코드. 원자료 파일 해시는 agentic-sources.json에 기록한다.
- 작성·검토: implementation-design-report 스킬 적용, 자체 검토. 신규 모델 호출·품질 평가·현장 GENOS 실행 없음.
- 관련 설계: [기존 상세 설계](DESIGN.md). 기존 설계의 선형 단계 배선을 아래 §7에서 명시적으로 확장한다.
- 범위 해석: “내부 탐험”은 우선 등록된 법령·내규·문서 폴더·목차·정의·참조 및 해당 요청의 작업 상태 탐색이다. 코드·프롬프트 수정은 별도의 개선 후보 생성 경로로 다룬다.

## 1. 구현 결정

질문마다 유지되는 작업 상태를 중심으로 조사 → 잠정 결론 → 반례 확인 → 재탐색 → 수정이 반복되게 한다. 도메인 하네스는 필요한 확인 사항·근거 의미·완료 기준을 소유하고, 에이전트 프로파일은 모델 호출·도구 노출·문맥·예산을 조정한다. 서버 실행기는 상태 전이와 실제 자료 접근을 집행한다.

두 종류의 반복은 더블하네스의 두 축과 별개다.

- 요청 안의 반복: 같은 질문의 해석·근거 선택·잠정 주장·답변을 수정한다.
- 요청 사이의 개선: 실행 실패와 사람 판정에서 검색 경로·색인·프롬프트·코드 수정 후보를 만들고 별도 검증한다.

매번 이전 답을 다시 읽고 자신감을 높이는 방식에는 외부 교정 신호가 없다. 반복을 허용하는 이유는 새 원문, 기존 원문의 구체적인 재해석 근거, 잘못된 계산·인용의 검증 결과, 사실 정정, 또는 범위가 명확한 미확인 해소 시도여야 한다. 추론을 다시 했다는 이유만으로 진전이나 정답을 선언하지 않는다.

정확도는 매 턴 단조 증가한다고 보장할 수 없다. 새 반례를 발견해 결론을 철회하거나 범위를 줄이는 것도 필요한 개선이다.

## 2. 이번에 확인한 현재 코드의 제한

| 근거 | 현재 동작 | 반복 판단에 필요한 변경 |
|---|---|---|
| 완료 rev3 loop.py:184,197 | adopt 후 adopted=true이면 이후 drop이 반영되지 않음 | 근거 원문은 보존하고, 쟁점별 채택 관계는 사유와 함께 철회·수정 가능 |
| 완료 rev3 loop.py:230 | done 또는 새 카드·expand 없음으로 종료 | 새 근거 외에도 반례·기존 근거 재해석·쟁점 변화·미확인 탐색 소진을 구별 |
| 완료 rev3 Loop.run | 탐색과 최종 조립을 한 함수에서 처리 | investigate / pack / compose / review 역할 분리 |
| pipeline.py:64 | legal-rag의 nodes를 한 차례 순회 | 명시적인 재탐색·재조립 전이와 단계 산출물 무효화 |
| stages.py:4 | retrieve를 호출할 때 plan을 새로 생성 | 같은 요청의 재탐색에서는 동일 Query ID·판본·허용 범위를 재사용 |
| stages.py:14,20 | assemble/answer가 term_agent에 고정 | 선택된 adapter의 단계 구현으로 dispatch |
| FolderNavigator.catalogue/outline/read_unit | 폴더·문서·목차·원문 구간 탐색 도구가 이미 존재 | 기존 도구를 통합 ToolBroker에 연결; 법률 후보 루프에 자동 연결되어 있지는 않음 |
| FolderNavigator.read_unit | 한 source article로 정확히 해소되는 구조 구간만 읽음 | 장/전체 문서는 자식 노드로 분할해서 읽기. 실패를 임의의 단일 조문으로 변환하지 않음 |
| ServingDocumentAgent.resources | 요청별 DB 자원과 세대 결속 메타데이터 준비 | 재사용 가능한 자원 팩토리로 추출, 깊은 agent 상속은 추가하지 않음 |
| app.ask, feedback.record_feedback | 성공 run 저장·답변 단위 PROPOSED 피드백 | 요청별 중간 checkpoint와 수정 계보; 장기 개선은 검토된 후보만 사용 |

완료 ADR의 snapshot은 수정하지 않는다. 제품 구현은 완료 후보의 계보를 고정한 신규 후보에서 수행한다.

## 3. 요청별 작업 공간과 판단 수정

제안 WorkState는 전역 문서 의미 DB가 아니라 요청 하나의 구조화된 작업 기록이다. 원문을 Rule/SemanticClause로 재작성하는 폐기된 구축 방식은 재도입하지 않는다.

| 상태 | 주요 정보 | 변경 원칙 |
|---|---|---|
| binding | query_id, generation/store/index hashes, domain/profile/code hashes, trusted scope | 요청 중 고정. 데이터 교체는 새 binding의 재실행 |
| intent | 원질문 구간, 해석 후보, 선택 이유, revision | 질문 범위를 바꾸는 해석이면 의존 쟁점과 주장을 재검토 |
| facts | 사용자 진술·확인 여부·출처·revision | 모델 추측으로 unknown을 사실로 바꾸지 않음 |
| issues | 필수 확인 사항, evidence_state, fact_state, required, origin | 근거 연결과 의미 확정을 구별; 비적용도 이유 기록 |
| frontier | 다음 읽기·검색 후보, 대상 쟁점, 얻으려는 정보, 시도 이력 | 재탐색 가능한 작업 목록. 중요도는 추정이며 진실 점수가 아님 |
| evidence | 정확한 원문 span, immutable handle, 판본·해시, 실제 전달 영수증 | 원문·핸들 불변. 새 구간은 새 handle |
| assessments | issue↔evidence별 supports/qualifies/contradicts/irrelevant/uncertain | 모델의 의미 판단 제안임을 표시. 동일 원문도 쟁점별 역할이 다름 |
| claims | 잠정 주장, 의존 facts/issues/evidence, revision, review_status | 수정을 덮어쓰지 않고 새 revision 생성 |
| challenges | 대상 주장·버전, 결함 종류, 원문 근거 또는 미확인 질문, 상태 | 비판이 곧 사실은 아님. 근거 없이 기존 주장을 자동 기각하지 않음 |
| budgets | 실제 모델 시도·토큰·도구·deadline·출력 예약 | 역할별 호출과 수리·전송 재시도까지 집계 |
| journal | 행동, 관찰, 승인된 전이, 변경 전후 hash, 간단한 수정 이유 | 장황한 내부 사고 대신 근거·행동·판단 변경의 감사 기록 |

예를 들어 E7 원문은 보존하면서 “E7이 I2를 뒷받침한다”는 평가를 철회할 수 있다. E7이 다른 쟁점 I3에는 여전히 필요하면 해당 관계는 유지한다. 전역 dropped 비트 하나로 모든 용도를 지우지 않는다.

철회 제안에는 대상 관계 revision, 원문 span 또는 구체적인 재해석 이유가 필요하다. 서버는 참조·권한·현재 revision을 검증하고 의미 상태를 NEEDS_REVIEW/CONTESTED로 전환한다. 의미적으로 올바른 철회인지 코드 검증만으로 확정하지 않는다.

의존 상태 변경 시:
1. 영향을 받은 claim을 stale로 표시한다.
2. 해당 claim을 대상으로 한 과거 리뷰를 stale로 표시한다.
3. 선택·조립·답변 파생 산출물을 무효화한다.
4. 원문·과거 관찰은 보존하고 필요한 frontier만 다시 연다.
5. 새 평가·답변은 새 revision으로 생성한다.

새 반례 때문에 무효화된 과거 답변은 “예전 점수가 더 높았다”는 이유로 최종 선택하지 않는다. 보관된 답변 중 현재 사실·근거·미해결 상태와 양립하는 것만 복구 후보가 된다.

## 4. 내부를 탐색하는 도구 표면

에이전트에게 실제 폴더 구조, 문서 목록, 목차와 본문 탐색을 모두 제공한다. 특정 도구 순서를 모든 질문에 강제하지 않는다. 명시 조문 질문은 직독하고, 문서명·업무명만 있는 질문은 문서 목록과 목차로 들어갈 수 있다.

아래 이름은 제안 ToolBroker API이며 현행 함수명과 구분한다.

| 제안 도구 | 현재 연결 대상 | 반환·주의 사항 |
|---|---|---|
| list_documents(scope, filter, cursor) | FolderNavigator.catalogue | 문서·폴더 분류, 판본 결속, 페이지 정보. 목록은 읽은 근거가 아님 |
| list_structure(document, parent, cursor) | FolderNavigator.outline | 실제 source_unit 계층. 인쇄 목차와 동일하다고 보장하지 않음 |
| read_node(document, node, page) | FolderNavigator.read_unit, Store.section/source | 정확한 원문 blocks와 immutable spans. 범위가 여러 조면 분할·페이지 |
| search_text(scope, query, cursor) | 기존 FTS / Search.articles / IndexTools | 검색어·필터·세대·rank/cursor. 낮은 순위 재진입과 직접 조문 지목 |
| search_subtree(document, root, query, field) | folder_navigation.search_structure | 실제 하위 범위의 제목/본문 검색. 후보 ID만 있으면 추가 read 필요 |
| lookup_definition(term, scope) | TermIndex / TermTools의 정의 navigation | 정의 원문과 적용 문맥. 용어 연관성은 결론 아님 |
| follow_reference(source_span, direction) | 명시 참조 + ReferenceResolver / 기존 역참조 도구 | 원문 mention·해소 상태·대상 판본·target. 역참조를 위임으로 자동 확정하지 않음 |
| inspect_work(issue/claim) | 신규 WorkState view | 현재 근거, 반대 근거, 미확인, 시도한 경로, 무효화된 주장 |
| propose_update(typed operations) | 신규 reducer | 모델의 상태 변경 제안. 모델에 직접 DB 쓰기를 허용하지 않음 |

공통 반환에는 observation_id, binding, scoped handle, cursor, complete/truncated, exact_read_extent를 둔다. pagination을 끝까지 읽었는지와 검색어로 모든 의미상 관련 규정을 찾았는지는 별개다.

기존 탐색 context는 좁혀진 문서 범위를 보존한다. 다른 폴더의 참조를 따라갈 때는 narrowed context와 요청의 원래 허용 범위를 구별한다. 근거 있는 새 탐색 분기는 원래 허용 범위 안에서 만들되, 사용자가 특정 문서만 보라고 제한한 경계나 trusted ACL을 넘지 않는다.

문서 연결이 누락되었거나 별표·첨부가 구조화되지 않았다면 DATA_GAP을 남긴다. 모델이 새 조문이나 누락된 표 셀을 지어내 채우지 않는다. 구조화 수정은 별도 데이터 후보→재구축 경로다.

실제 내부 데이터와 비공개 질문은 GENOS 내부 모델에서 처리한다. 현재 Request에는 trusted principal이 없으므로 user_id 문자열을 ACL로 간주하지 않는다. 초기 공유 코퍼스 범위와 추후 사용자별 권한 도입을 구별한다. 모든 읽기·검색·참조·결과 전달에 같은 유효 범위를 적용한다.

## 5. 모델 역할과 피드백

첫 후보는 하나의 모델/provider adapter로 다음 역할을 조건부 실행한다. 역할마다 상주 모델이나 병렬 agent를 반드시 만들 필요는 없다.

- Investigator: 질문 해석, 다음 탐색 제안, 원문 평가, 잠정 주장 수정.
- Challenger: 특정 결론을 뒤집을 근거·누락 조건·사실 혼동을 확인. 추상적인 “더 검토하라” 대신 해결 가능한 쟁점과 읽기 요청 반환.
- Composer: 현재 유효한 주장·근거·한계를 사용자 답변으로 서술.
- 서버 검증: ID·span·판본·예산·revision·인용 관계·형식·일부 결정론 계산을 검사.

Challenger는 초기 질문, 대상 claim, 관련 원문과 주변 문맥, 사용자 사실, 미해결 사항을 받는다. Investigator의 장황한 판단 서술을 복제하지 않고 다른 탐색 경로를 제안할 수 있게 한다. 같은 모델의 다른 호출도 독립된 정답 판정자가 아니다.

결함 반환 예:
- UNSUPPORTED_CLAIM: 유효한 인용이 해당 결론을 지지하는지 의문.
- MISSED_QUALIFIER: 예외·적용 대상·조건 누락.
- CONFLICTING_SOURCE: 상충 가능 원문 발견.
- MISSING_FACT: 결론에 필요한 사용자 사실 부족.
- WRONG_SCOPE_OR_VERSION: 문서·판본·적용 범위 불일치.
- CITATION_FORMAT_ERROR: 단순 형식·핸들 오류.
- DATA_GAP: 탐색에 필요한 원문/참조 대상 미제공.

각 challenge는 targeted claim revision, anchors, reason_summary, proposed_next_action을 가진다. 이미 있는 원문의 재해석으로 제기하는 반례도 허용한다. “새 원문이 없으면 수정 불가”라는 경직된 규칙은 두지 않는다.

반영 방법:
- 추가 근거가 필요하면 RESEARCH로 되돌린다.
- 기존 근거로 서술만 수정 가능하면 RECOMPOSE한다.
- 사실 부족이면 조건부 답변 또는 CLARIFY한다.
- 반례가 해결되지 않으면 주장을 제한하고 unresolved를 남긴다.
- 근거 없는 비판은 pending challenge로 관리하고 예산 안에서 조사한다. 반복되는 추상 비판은 무한 재시작을 유발하지 않는다.

모든 턴에 조사관→비판관→작성자를 고정 호출하지 않는다. 다중 출처의 결론·예외/위임 의존·충돌·확정적 부재 주장 등 도메인 trigger에서 targeted review를 수행한다. 단순 원문 조회는 별도 모델 비판 없이 코드 검증으로 종료할 수 있다.

## 6. 핵심 루프와 종료

다음은 제어 흐름 의사코드다. 현재 제공되는 실행 함수가 아니다.

~~~python
request_context = bind_once(request, source_generation, allowed_scope)
work = work_repository.create(request_context)

while budget.can_investigate(reserving="finalize"):
    view = work.compact_view_with_original_evidence()
    proposal = investigator.propose(view, tool_menu)
    checked = validate_proposal(proposal, work.revision, request_context)

    # 탐색 도구와 상태 변경은 순차 반영; read-only batch는 ID별 observation을 보존한다.
    observations = broker.execute_reads(checked.read_actions, budget)
    work.record_observations(observations)
    work.apply_review_proposals(checked.updates)  # 아직 받지 않은 새 원문 채택은 금지
    work.update_frontier_and_invalidate_dependents()
    work.checkpoint()

    # 신규 원문은 다음 모델 입력에 실제 전달돼야 평가할 수 있다.
    if work.has_unreviewed_decision_relevant_evidence():
        continue

    gate = assess_gate(work)
    if gate.requires_targeted_review:
        review = challenger.inspect(work.targeted_review_view(), budget)
        work.apply_challenge_proposal(review)
        if work.needs_more_evidence():
            continue
    if gate.may_finalize or work.no_progress_limit_reached():
        break

# 최종 조립 이후 재탐색은 아래 §7의 같은 요청 coordinator가 처리한다.
return work.snapshot_with_gate()
~~~

판단 진전은 하나의 점수로 압축하지 않는다. 원문 전달, 필수 쟁점의 근거 연결, 유효한 반례, 사실 정정, 범위를 갖춘 미확인 탐색 결과를 별도 계수로 둔다. 새 카드 수가 늘어도 질문과 무관하면 유효 진전이 아니다. 관계를 단순 연결하는 것은 “평가 제안 변화”이며 정답 향상으로 집계하지 않는다.

반복 탐색 키는 tool + 정규화 arguments + scope/binding + cursor로 만든다. 같은 빈 검색을 바꾼 표현만으로 무한 시도하지 않게 시도 이력과 결과 중복을 본다. 반면 새 cursor·새 사실·새 반례에 따른 같은 문서 재독은 허용한다.

같은 의존 상태에서 claim을 뒤집었다가 되돌리는 진동도 기록한다. 구체적인 새 근거·재해석 근거 없이 반복되면 CONFLICTED/BOUNDED로 끝낸다.

종료는 “모델 자신감 95%” 같은 자가 점수로 정하지 않는다.
- READY: 필요한 확인 사항과 중요한 challenge가 처리됨. 법률 정답 인증 의미 아님.
- BOUNDED: 확인된 부분과 남은 공백을 분리한 답변.
- CLARIFY: 답을 바꾸는 사용자 사실·의도 필요.
- FAILED: 유효한 binding/권한/실행 자체가 성립하지 않음.

프로파일별 실제 시도 수·시간 상한·무진전 상한·targeted review 예산은 후보 설정으로 동결하고 측정한다. 특정 횟수를 검증된 최적으로 제시하지 않는다. 마감 때 모든 claim이 무효면 예전 잘못된 초안을 내보내지 않고 유효한 근거 설명과 미해결만 반환한다.

## 7. 기존 파이프라인에서 재탐색을 구현하는 방법

기존 DESIGN.md §10은 investigate→pack→compose를 한 차례 실행하는 최초 통합이었다. 사용자가 요청한 “최종 답을 판단하고 다시 탐색”까지 하려면 그 설계를 확장해야 한다.

권장안: 새 standalone 서비스/중복 파이프라인을 만들지 않고 기존 Pipeline.run에 요청별 coordinator를 추가한다. 다른 implementation의 기존 선형 실행은 유지하며 선택된 legal-agent-v1 후보에만 허용 전이를 사용한다.

~~~text
retrieve → select → assemble → answer+targeted review
    ↑                              │
    └──────── RESEARCH ────────────┤
                      answer ← RECOMPOSE
                                   │
                                FINAL
~~~

RESEARCH는 retrieve부터 재실행하고 select/assemble/answer의 과거 산출물을 무효화한다. 저장된 원문·관찰·탐색 이력은 같은 WorkState에 남긴다. 새 선택과 조립은 현재 revision으로 다시 만든다.

RECOMPOSE는 기존 assembly와 일치하는 근거만 사용하는 수정이다. 근거 추가/삭제나 선택 변경이 생기면 RECOMPOSE로 처리할 수 없으며 RESEARCH 또는 명시적인 select/assemble 재실행이 필요하다. 첫 구현에서는 단순하게 RESEARCH 경로로 통일할 수 있다.

내부 제안 StageControl:
~~~json
{
  "kind": "RESEARCH",
  "run_id": "run-demo",
  "query_id": "query-demo",
  "expected_state_revision": 7,
  "answer_revision": 2,
  "evidence_revision": 5,
  "issue_ids": ["I2"],
  "challenge_ids": ["K1"],
  "reason_code": "MISSED_QUALIFIER"
}
~~~

이 값은 모델의 자연어 답변에서 정규식으로 추출하지 않는다. 별도의 모델 review 계약을 검증한 뒤 서버가 생성하는 제어 포트다. 예제 ID는 모의 데이터이며 실제 코드 API가 아니다.

배선 변경:
1. 초기 Query를 request context에 한 번 저장한다. 재탐색에서 stages.retrieve가 새 query ID를 만들지 않는다.
2. engine manifest의 answer 출력에 기존 result와 별도의 내부 control 포트를 선언한다.
3. PIPELINE의 contract resolver가 내부 control 스키마 URI/definition도 명시 처리하도록 확장한다. 현재 term-runtime-v1 고정 검증에 임의 필드를 끼워 넣지 않는다.
4. 허용 전이·반복 상한·무효화 대상을 후보 실행 명세에 고정한다. trace에 실제 방문 순서를 저장한다.
5. pending result는 기존 result 계약으로 검증해도 control이 FINAL이기 전에는 API에 공개하지 않는다.
6. 최종 result의 retrieval/selection/assembly/answer는 동일한 query/binding과 현재 evidence revision에 결속되어야 한다.
7. 모든 중간 answer는 journal의 draft이며 app.ask는 FINAL/BOUNDED/CLARIFY의 최종 일관된 결과만 저장·반환한다. 실패 checkpoint는 별도 보존한다.
8. FINAL은 READY/BOUNDED/CLARIFY 등 의미상 관문 결과를 함께 가진다. 모델의 done=true는 직접 FINAL 권한이 없다.

새 control 포트·coordinator에는 후보 엔진 manifest, code hashes, contract registry, 연결 테스트가 모두 필요하다. 설정 이름 추가만으로 동작하지 않는다.

외부 Request/Result 필드는 첫 통합에서 유지한다. 사용자 다중 턴 재개·취소·비동기 상태 조회는 현 API에 없으므로 v2 요청/운송 계약으로 도입해야 한다. “이어서 더 조사해”를 지원하려면 run_id, facts patch, trusted identity, idempotency와 재개 semantics를 app·workflow·테스트까지 같이 설계한다.

## 8. 제안 파일 변경 지도

모든 신규 이름은 제안이며 아직 생성된 제품 모듈이 아니다.

| 파일/모듈 | 책임 | 소비자·설정 |
|---|---|---|
| legal_agent/state.py | WorkState, revision, 의존 관계, frontier | investigator/challenger/coordinator |
| legal_agent/reducer.py | 제안 검증, 채택 관계 철회, stale 전파 | 서버 전용 |
| legal_agent/tools.py | 탐색 도구의 scope/binding/observation 계약 | 기존 FolderNavigator/Store/FTS/TermIndex adapters |
| legal_agent/investigator.py | 다음 읽기와 평가 제안 | model adapter + profile |
| legal_agent/challenger.py | 특정 claim의 반례·누락 확인 | 선택적 review phase |
| legal_agent/loop.py | 조사 안의 행동/관찰 반복 | 기존 Loop.run 분리 |
| legal_agent/composer.py | 유효 주장·원문 묶음으로 답변 | 기존 plain 방식 유지 |
| legal_agent/coordinator.py | 요청별 전이, 단계 무효화, 예산, 결과 commit | Pipeline.run이 호출; 별도 서비스 엔드포인트 아님 |
| legal_agent/journal.py | 이벤트·checkpoint·revision CAS | workspace runtime logical root |
| semantic_runtime/legal_agent_adapter.py | 기존 retrieve/select/assemble/answer 계약 매핑 | 선택된 implementation만 적재 |
| semantic_runtime/pipeline.py, stages.py | 재진입·내부 control 포트·명시 adapter dispatch | 엔진 manifest/PIPELINE 후보 |
| semantic_runtime/app.py | 요청 context, 실패 checkpoint, 최종 일관성 | 현재 API 및 추후 재개 API |
| feedback / learning 연결 | 근거·세대 결속 개선 제안 | 검토·검증 뒤 적용 |

문서 원문 구조와 source ID는 재사용한다. 원문/관계 색인 계약에 필요한 지문·참조 출처가 빠져 있으면 파생 색인만 신규 세대로 재구축한다. 코퍼스 전체 의미 스키마 재생성은 이 구현의 전제조건이 아니다.

## 9. 실행 시나리오와 실패 경계

모의 질문: “우리 규정에서 X 업무는 누가 승인하며 기한은 언제인가?” 아래 내용은 실제 법률이 아니다.

1. 문서명 불명 → 문서 목록에서 관련 폴더·문서를 확인한다.
2. 목차에서 승인 절차를 찾고 정확한 항을 읽는다.
3. E1을 바탕으로 C1: “원칙상 위원회 승인” 잠정 주장 생성.
4. 원문에 별표의 세부 기한 참조 → I2와 frontier를 만든다.
5. 별표가 등록되어 있으면 읽고, 없으면 DATA_GAP. 다른 서식의 숫자로 대체하지 않는다.
6. Challenger가 형제 항의 특례를 발견해 C1에 K1 challenge 생성.
7. 기존 C1과 이에 의존한 초안은 stale. 관련 형제 항을 읽어 E3 추가.
8. 사실 F1이 특례 적용 여부를 결정하는데 사용자 미제공 → 조건부 결론으로 C2 작성.
9. 답변에는 원칙·특례·확인된 기한·필요한 사실을 구분한다.
10. 사용자가 나중에 F1을 주면 재개 계약이 있는 버전에서만 해당 쟁점을 다시 연다.

| 경우 | 검출·처리 | 사용자 결과 / 잔여 한계 |
|---|---|---|
| 채택 원문 재평가 | 관계 revision을 철회하고 영향 claim을 stale | 수정 이유와 현재 결론 |
| 반례가 다른 주체 규정 | 적용 주체 비교, challenge 검토 후 기각 가능 | 불필요한 답변 회귀 억제, 의미 판단은 미검증 |
| 같은 자료 재독으로 오류 발견 | source span을 근거로 평가 변경 허용 | 새 문서 없이도 정정 가능 |
| 여러 조가 있는 장을 read_node | 자식/leaf 분할과 정확한 구간 페이지 | 전체 장이 읽혔다고 잘못 기록하지 않음 |
| 참조 순환·반복 빈 검색 | 방문 키·cursor·쟁점 이력으로 중복 제어 | 미해결과 시도 범위를 명시 |
| 재탐색 중 모델 timeout | 실제 시도 원장·남은 예산·valid claims 확인 | 일관된 부분 답변 또는 실패 |
| timeout 뒤 늦은 응답 | call ID·state revision·deadline 검증, 전이 거부 | 완료 상태가 뒤늦게 바뀌지 않음 |
| 서버 재시작 | event/checkpoint로 interrupted 기록 | 최초판은 자동 의미 재개 보장 안 함 |
| 같은 control 중복 전달 | event ID dedupe + revision CAS | 중복 재탐색/상태 쓰기 방지; 과금 exactly-once는 보장 안 함 |
| 데이터 세대 변경 | 실행 binding 유지 또는 새 요청으로 restart | 새·구 판본 혼합 인용 방지 |
| 접근 권한 변경 | 매 도구/결과 전달 시 검증 | 취소된 자료·그 파생 주장을 제거하고 재검토 |
| 조립에서 새 공백 발견 | control RESEARCH, 단계 산출물 무효화 | 최종 결과의 출처·선택 기록 일관성 |
| 조립만으로 수정 가능 | 같은 evidence revision에서 RECOMPOSE | 불필요한 검색 비용 제한 |
| 수정 반복이 무진전 | 반복 사유와 상한 검증 | BOUNDED/CLARIFY; 자가 점수로 완료 안 함 |
| 외부 문서에 도구 지시문 포함 | 원문은 자료로만 전달, ToolBroker 권한은 서버 소유 | 자료가 scope/profile을 바꾸지 못함 |

## 10. 요청 사이의 지속적 개선

현재 feedback은 PROPOSED 기록을 만들며 자동 검색 반영은 없다. 다음 루프는 별도 개선 작업으로 구현한다.

실행 기록/사람 판정 → 실패 위치 분류 → 수정 후보 → 계약 검증 → 동결된 품질 비교 → 채택/기각 → 다음 버전.

수정 후보의 종류:
- 질문 표현과 문서/용어를 잇는 탐색 힌트.
- 명시 참조 해소·문서 별칭의 오류 수정.
- 예외/별표를 읽는 도구 절차.
- 모델별 prompt/profile 조정.
- reducer/adapter/색인 연결 코드 수정.
- 원문 구조화 오류의 데이터 재구축 제안.

개선 agent는 해당 오류의 로그·코드·계약을 읽고 격리된 후보를 수정할 수 있다. 실행 중인 요청의 원문·도메인 기준·운영 코드를 직접 고쳐 자기 검사를 통과시키는 경로는 두지 않는다. 사용자 답변 서비스와 개발 도구는 별도 권한/실행 환경이다.

검증된 검색 경로는 “그때의 답” 대신 “어떤 조건에서 어떤 정의/원문을 확인했는지”를 기억한다. 새 요청에서는 현재 판본으로 다시 읽는다. 피드백은 원문 세대·출처·사람 검토 상태에 묶이고 오래된 판본에서는 stale 처리한다. 반례가 된 근거도 전역 삭제하지 않는다.

제품 입력에는 평가 기준답변을 넣지 않는다. 평가 agent의 점수는 정답 정본이 아니며, 평가기 설정 변경으로 점수만 높이는 후보를 별도로 식별한다. 동일 사례의 의역을 독립 holdout처럼 나누지 않는다.

장기 루프도 agent가 계속 호출되는 무제한 서비스라는 뜻은 아니다. 운영 결과가 쌓일 때 후보를 만들고, 명시적인 실험·승격 절차로 검증된 버전을 채택하는 기능이다.

## 11. 검증과 단계별 도입

| 작업 단위 | 산출물 | 완료 판단 |
|---|---|---|
| A. 상태 전이 | WorkState/reducer/journal | 채택 철회, stale 전파, 늦은 응답, 중복 이벤트의 모델 없는 계약 검사 |
| B. 내부 탐색 도구 | ToolBroker와 기존 도구 adapters | 폴더→목차→원문→참조의 출처·scope·pagination 보존 |
| C. 반복 조사 | investigator + 조건부 challenger | 모의 도구 관찰로 반례→재탐색→주장 수정 흐름 연결 확인 |
| D. 파이프라인 재진입 | control 포트/coordinator/adapter | 최종 모든 단계의 query/binding/revision 일치; FINAL 전 공개 없음 |
| E. 품질 비교 | 동결된 신규 ADR 후보 | 정답·회귀·미답변·근거 도달·비용을 같은 조건으로 비교 |
| F. 현장 및 개선 루프 | GENOS 계약 확인, 검토된 feedback 적용 | 실제 내부 모델·권한·저장·재개 기록 확인 |

첫 제품 후보에서 A~D의 작은 수직 경로를 먼저 완성한다. 큰 agent 집단·복잡한 장기 기억·전 코퍼스 의미 그래프를 선행조건으로 두지 않는다.

필수 계약 시나리오: 채택된 근거 철회, 다른 쟁점의 근거는 유지, 새 근거를 전달하기 전 채택 금지, challenge 대상 revision 불일치 거부, RESEARCH에서 옛 assembly 무효화, RECOMPOSE에서 새 출처 금지, 같은 query 유지, 동시/중복 control 거부, 표·장 구간 분할, 범위 밖 참조, 종료 직전 권한 변경, 최종 답변 계약과 브릿지 소비 일치.

품질 비교에서 분리할 효과:
- 기준 후보.
- 근거 보존/상태 수정만 추가.
- 내부 탐색 도구 추가.
- targeted challenge와 재탐색 추가.
- 피드백 기억 추가는 이후 별도 후보.

성공 기준은 결과를 보기 전에 신규 ADR에서 수치로 동결한다. 실제 모델의 기본 신규 실험 설정과 데이터 전송 범위는 현행 저장소 정책을 따른다. 이 문서 작성에서는 품질 실험을 실행하지 않았다.

핵심 관측:
- 최초 답이 틀렸으나 반복 후 맞은 경우.
- 최초 답이 맞았으나 반복 후 틀린 경우.
- 잘못된 반례가 유발한 회귀.
- 필수 미확인과 불필요한 유보.
- 결정 근거의 발견/전달/채택/조립/인용 단계별 도달.
- 모델 물리 호출, 입출력 토큰, 실제 종단 지연, 중단·재개율.

순 품질 이득 = 회복한 오답 수 - 새로 만든 오답 수. 단순 최종 총점만으로 수정 역할의 효과를 설명하지 않는다. 반복을 끄는 rollback은 검증된 기존 implementation 선택으로 수행하고, 실패 run과 후보 이력은 보존한다.

## 12. 비용·기대효과·일정 판단

관측은 기존 상세 설계 및 해당 ADR의 조건을 따른다. 아래 가정은 최적 설정이나 성능 예측이 아니다.

| ID | 종류 | 값/식·단위 | 근거·불확실성 |
|---|---|---|---|
| O1 | 관측 | 조립 확인표 호출 92→274~282, 해당 Gemini 정답 30/51 유지 | ADR-0466/LEGAL_AGENT_SYSTEM. 모든 답변의 고정 비판 루프는 비용 증가를 정당화하지 못했음 |
| O2 | 관측 | rev3 저장 모델 요청 Gemini 176/51, Qwen 180/51 | existing-run-diagnostics.json. 요청당 평균 호출이며 E2E 지연 아님 |
| C1 | 계산 | 추가 호출/질문 = p_review×calls_review + p_research×calls_research + p_recompose×calls_recompose - calls_saved | 각 확률은 전체 요청 중 비율. 중복 발생은 각 단계 실제 호출로 합산 |
| A1 | 가정 | p_review=0.3, calls_review=1, p_research=0.1, calls_research=2, 나머지 0 → +0.5회/질문 | 설명용 시나리오. 기존 176/51 대비 호출 수 약 14.5% 증가; 비용·지연 증가율 아님 |
| C2 | 계산 | 비용 = Σ(단계별 입력 토큰×입력 단가 + 출력 토큰×출력 단가) + 데이터/평가/운영 비용 | 실제 receipt와 승인된 환경의 가격 필요. 단가 미확인으로 금액 미산정 |
| T1 | 목표 | 기존에 맞은 답을 뒤집는 회귀를 제한하면서 미해결 근거를 회복 | 임계값은 실험 전에 선택; 현재 정확도 상승폭 미예측 |

추가 검토 비용의 손익분기는 품질 개선으로 줄어드는 사람 재검토/오류 처리 비용이 추가 모델·색인·평가·운영 비용을 넘을 때다. 사람 시간 단가와 오류 비용이 없어 금액 계산은 미산정이다.

개발 일정은 A~F 의존 작업 분해까지 제시한다. 현재 담당 인력·현장 검증 대기·계약 변경 범위가 확정되지 않아 인일/달력 일정은 미산정이다. 첫 후보의 연결 검사 뒤 각 작업 실제 시간을 측정해 보정한다.

## 13. 자체 검토에서 보완한 사항

- 초기 “답변에서 필요하면 다시 검색” 설명은 기존 선형 파이프라인의 기록 일관성을 깨뜨렸다. §7에 제어 포트·재진입·무효화와 동일 Query 결속을 추가했다.
- 새 증거만 진전으로 인정하면 기존 원문의 재해석과 오인용 수정이 막힌다. 구체적인 재해석 근거를 허용했다.
- 과거 초안을 무조건 보존·선택하면 이미 반박된 주장이 살아남는다. 복구도 현재 의존 상태에 대한 유효성 검사를 요구했다.
- 문서별 adopted/drop 상태는 쟁점마다 다른 근거 역할을 표현하지 못한다. 채택 관계를 쟁점별 revision으로 분리했다.
- 내부 구조 읽기는 여러 조를 한꺼번에 반환하지 못하는 현재 제한을 확인했다. leaf 분할과 정확한 읽기 범위 계약을 추가했다.
- 반복 판단·내부 탐색·장기 개선의 개념 설계와 실제 제품 구현/품질 검증을 구분했다.


## 14. 함께 제공하는 산출물과 확인 범위

- [제안 내부 제어 포트 스키마](AGENTIC_CONTROL.schema.json): RESEARCH/RECOMPOSE/FINAL과 대상 상태·답변·근거 revision.
- [모의 제어 메시지](agentic-control-examples.json): 유효 예제 3개, 무효 예제 6개. 실제 실행 원장이 아니다.
- [구조 검증 결과](agentic-validation.json): JSON Schema 자체 확인 및 9개 예제의 기대 수용/거부 확인. 상태 전이 실행·서빙 연결·법률 정확도 검사가 아니다.
- [원자료 지문](agentic-sources.json): 읽은 코드·계약·설계 23개 파일의 절대 경로와 SHA-256.
- [구조 검증 재실행](validate_agentic_protocol.py): 저장소 .venv Python과 기존 jsonschema를 사용한다. 외부 모델·네트워크 호출 없음.

# 도구·상태·하네스 구현 계약

상태: 제안. 이 문서와 [contracts.schema.json](contracts.schema.json)은 보고서 부속 명세이며 현재 제품이 읽지 않는다. schema의 구조 검증과 아래 의미 검증을 모두 구현해야 한다. 숫자 한도는 방어적 메시지 크기 경계이며 기대 사용량이 아니다. 실제 profile의 남은 예산이 더 작으면 그 값이 우선한다.

## C01. 식별자와 서버 결속

기본 R은 선택된 서빙 세대의 등록 자료 전체다. 이번 사용자는 자료 제한을 지정하지 않았다. 아래 scope 검사는 자료 세대·실제로 명시된 요청 범위를 구별하는 계약이며, 특정 문서에 들어갔다고 그 문서 밖의 탐색을 막는 규칙이 아니다. 임시 문서/폴더 검색 필터는 모델이 스스로 바꿀 수 있다.

| 모델용 별칭 | 의미 | canonical identity | 인용 가능 여부 |
|---|---|---|---|
| R | 이 요청의 허용 자료 집합 | generation + sorted authorized documents | 아니오 |
| F | 폴더/명시 필터 자료 집합 | R + 필터 + 세대 | 아니오 |
| D | 논리 문서의 특정 판본 | document_version_id | 아니오 |
| U | 저장된 구조 위치 | document_id + unit_id + branch | 아니오 |
| P | 검색/용어/참조로 발견한 읽기 후보 | source_id + target extent + generation | 아니오 |
| T | 등록된 용어 | glossary binding + canonical term id | 아니오 |
| L | 탐색 관계/유입 경로 | relation id + 양 끝 + 방향 + witness hash | 아니오 |
| E | 실제 READ로 고정한 원문 범위 | document/source + ordered spans + hashes | 현재 제시된 검증 원문만 |
| C | 초안의 주장 | request + server claim id + version | 답변 검토 대상 |
| Q | 원질문의 서버 발급 구간 | original question hash + span | 사용자 발화 출처 |

별칭 패턴만 맞으면 유효한 것이 아니다. 요청 소유, 세대, effective scope, 현재 offered/presented 여부를 검사한다. 서버가 view_id에 맞는 기대 revision을 내부에서 읽는다. 모델에게 revision 숫자 계산을 맡기지 않는다. 도구로 반환됐지만 아직 전송되지 않은 핸들은 다음 행동의 대상이 될 수 없다.

source_id가 같은 서로 다른 항/호를 읽는 P는 extent가 다르면 구별한다. 같은 source+extent의 후보는 재사용하고 routes만 추가한다. E identity는 정확 원문 범위이며 카드 수와 일대일이 아니다. 새 요청에서 별칭을 다시 생성한다.

## C02. 도구 호출과 결과 봉투

모델 행동: `{tool, args, reason}`. action_id는 서버가 view_id와 행동 순번에 결속해 발급한다. 같은 view의 동일 응답 재처리는 같은 action_id, 새로운 턴의 반복 읽기는 새 action_id다.

서버 결과 필수 필드:

```text
action_id, tool, args_hash, status,
target_binding, resolved_location,
items[], evidence_ids[], next_cursor,
coverage { requested_extent, returned_extent, complete, truncated, basis },
search_receipt|null, navigation_targets[],
error { code, field, explanation, retryable, suggested_actions[] }|null,
budget { action_reserved, io_executed, reused, duration_ms },
provenance { generation_id, source/index/glossary/policy hashes }
```

status는 OK/EMPTY/PARTIAL/UNRESOLVED/REUSED/DENIED/ERROR다. 각 status의 complete는 결과 범위에만 적용한다. EMPTY는 실행한 필터에서 못 찾았다는 뜻이다. NOT_APPLICABLE은 모델 평가로 남기며 도구 상태로 오용하지 않는다. coverage에 원문 없음/법률 부재의 추정은 쓰지 않는다.

cursor는 도구 이름·정규화 인자·target·세대·권한·정렬·위치에 결속한다. 필터나 검색어를 바꾸면서 기존 cursor를 붙이면 CURSOR_MISMATCH다. page 크기는 서버 profile이 정하고 응답에 실제 크기를 표시한다. caller가 한도보다 큰 결과를 요청할 수 없다.

suggested_actions는 현재 handler가 실행할 수 있는 인자만 만든다. 추천이 다음 행동의 enum 전체를 대체하지 않는다. 원문 속 문자열을 명령으로 복사하지 않는다. 권한 밖 대상의 존재·이름을 오류 메시지로 새로 노출하지 않는다.

## C03. 도구별 인자와 의미

모든 cursor는 첫 호출 null이다. 부속 schema는 각 도구의 required와 additionalProperties=false를 고정한다.

| 도구 | args | 추가 의미 검증 |
|---|---|---|
| browse | target, relation=self/parent/document/root, view=children/outline/tree/neighbors, depth, cursor | target은 R/F/D/U/P/E. relation 해소 후 지원 view 검사. depth는 tree에만 의미 있으며 다른 view는 1 |
| search | query, target, mode=fulltext/literal/title, cursor | target R/F/D/U. title은 문서·구조 제목만 검색. fulltext 실제 backend receipt 필수 |
| match_terms | text, target, strategy=auto/direct/bridge, cursor | target R/F/D/U. glossary의 전역 의미와 target 내 출현을 따로 표시 |
| term_occurrences | terms, target, match=any/all, cursor | terms는 현재 노출 T. all은 같은 source 단위 교집합, 의미적 동시충족으로 해석 금지 |
| locate | locator, target, branch=body/addendum/annex/any, cursor | 저장 좌표와 공식 명칭만 해소. 복수 판본·부칙 구분. UNKNOWN은 fallback 추정 금지 |
| lookup_definition | query, target, cursor | 문서 정의 우선 정렬과 외부 사전 정의를 역할별 구분. 반환 위치는 READ 전 인용 불가 |
| follow_reference | evidence, direction=outgoing/incoming/both, cursor | E의 정확 source와 읽은 witness 범위 구분. 미읽은 witness는 후보로만 반환 |
| read | target, extent=exact/subtree/article, cursor | target D/U/P/E. E는 기존 범위 재제시만, exact로 제한. D는 문서 페이지 읽기, article은 단일 조로 유일하게 해소될 때만 |
| inspect | section=history/evidence/candidates/questions/challenges/budget, cursor | 전체 journal 원문을 무제한 전송하지 않음. pending/parked/UNASSESSED와 현재 상태를 표시 |

browse(R,children)은 R 아래 폴더/직접 문서를, browse(R,outline)은 자료 집합의 문서 제목 목록을 준다. R의 outline을 문서 내부 조문 목록으로 해석하지 않는다. browse(D,outline)은 본문의 큰 헤딩과 조 단위를, browse(U,children)은 실제 직접 자식을 준다. 일반 문서에서 조가 없으면 저장 상위 section만 표시한다. 미분류 블록은 별도 ‘구조 미확인 원문’ 항목으로 접근 가능하게 하고 임의 법적 계층을 만들지 않는다.

tree의 depth 상한은 profile에 결속한다. 부속 schema의 방어적 최대 depth=4는 품질 목표가 아니라 입력 한도 제안이며 구현 전에 profile과 일치시킨다. 첫 제품 후보는 기본 depth=1이다. 전체 펼치기는 자동 동작이 아니며 paging과 도구 예산을 소비한다.

neighbors의 범위는 relation이 해소한 node의 형제다. ROOT의 neighbors나 복수 문서에 걸친 E의 단일 parent 요청은 INVALID_NAVIGATION으로 되돌리고 유효한 대상들을 제시한다. 정보가 없을 때 기본 문서를 임의 선택하지 않는다.

문서 READ는 여러 source에 걸칠 수 있다. 각 source의 정확 span으로 E를 나눠서 반환하며 하나의 가짜 source로 합치지 않는다. read(subtree)는 요청 마디의 저장 span을 사용한다. 표/별표 범위는 필요한 셀 헤더·단위가 잘렸다는 것을 표시하고 추가 읽기 대상으로 둔다. 숫자·문자 위치는 모델이 작성하지 않는다.

## C04. 검색 결과·용어 관계·참조 카드

P/U 항목은 문서명, 좌표, 헤딩, target, ancestor path, read_action, routes, preview 여부를 가진다. preview는 원문 발췌인지 헤딩인지 표시하고 citation_eligible=false다. 근거와 무관한 문서 ID를 모델이 P 문자열로 직접 생성하지 않는다.

match_terms의 항목은 matched_surface/question_span, T, label, source, definition_hint, strategy, ambiguity_group, in_scope_occurrence_count, L[]를 가진다. L은 everyday→legal의 방향을 명시하고 저장 관계의 실제 source/target도 보존한다. 용어 관계와 법령 참조 관계는 kind로 구분한다.

term_occurrences 결과 P에는 사용 T 및 L 경로가 붙는다. 출현 span이 없는 과거 색인은 source-level occurrence라고 표시한다. 새로운 span을 추정하지 않는다. 가용 색인의 계약이 source 수준이면 그대로 검색에 쓰되 pinpoint 인용은 READ가 책임진다.

fulltext 결과에는 query_terms, tokenizer, ranking_policy, searched_extent, excluded_filter, returned_count, total_status=exact/unknown/capped를 기록한다. 기존 limit=80을 전체 결과 존재 상한처럼 사용하지 않는다. 후속 페이지가 가능한 검색 세션/안정 정렬을 adapter에 구현하거나 SEARCH_CAPPED를 명시하고 재검색을 허용한다.

관계 거절은 L의 route-specific 상태다. 동일 canonical edge라도 질문 구간별 부적절함이 다를 수 있으므로 rejection_key=(question-span, edge, direction, target-scope)로 기록한다. 다른 의미 질문까지 전역 오염시키지 않는다.

## C05. 모델의 조사 결정

`TurnDecision`은 다음 배열을 모두 가지되 빈 배열을 허용한다.

```text
actions[]                    위 도구 행동
assessments[]                {evidence:E, summary, disposition, role, reason, question_refs:Q[]}
candidate_decisions[]        {candidate:P, decision:PARK|REOPEN, reason}
route_decisions[]            {route:L, decision:REJECT|RESTORE|DEFER, reason}
question_updates[]           {question_refs:Q[], interpretation, missing_fact|null, reason}
intent                       CONTINUE|DRAFT|CLARIFY|STOP_PARTIAL
reason                       다음 전환의 짧은 이유
```

assessments의 disposition은 ADOPT/REJECT/DEFER, role은 SUPPORT/CHALLENGE/CONTEXT다. ADOPT는 support 선택을 포함하되 role이 CHALLENGE이면 검토 묶음 보존을 뜻한다. 답변이 주장에 인용할 때 원문 의미를 별도로 검토한다. DEFER여도 중요한 challenge이면 검토 묶음에 들어갈 수 있다. REJECT는 인용 집합에서 제외하지만 검토 중 반론 원문으로 제시할 수 있다.

한 E에 동일 턴의 상충 disposition을 넣으면 거절한다. 이전 E 평가를 고치면 서버가 version을 올린다. 모델이 원문 요약을 수정해도 E 자체를 변경하지 않는다. UNASSESSED는 서버의 기본 상태이며 모델이 ‘읽음 완료’를 자체 선언하지 않는다.

질문 요약은 Q 원문을 덮어쓰지 않는다. 새로운 해석이 이전 해석을 바꿨음을 event로 기록하고 이전 의존 주장만 STALE로 만든다. 추정한 사실을 사용자 사실로 승격하지 않는다. 전체 필수 쟁점 목록이나 finding 생성은 도구 호출·초안의 선행 조건이 아니다.

CLARIFY 요청도 가능한 검토된 부분 설명을 보존한다. 사용자에게 묻는 질문은 결론을 바꾸는 누락 사실이어야 하며 서버가 title/질문 요약을 사용자 사실로 채우지 않는다.

## C06. 상태 전환과 재진입

```text
START → INVESTIGATE
INVESTIGATE --도구행동--> EXECUTE → PRESENT → INVESTIGATE
INVESTIGATE --정정필요--> REPAIR → INVESTIGATE
INVESTIGATE --DRAFT+유효 근거--> SELECT → ASSEMBLE → COMPOSE → REVIEW
REVIEW --원문 부족--> INVESTIGATE
REVIEW --해석/표현 오류--> COMPOSE
REVIEW --검토 이의--> REBUTTAL → REVIEW
REVIEW --준비/한계--> FINAL → COMMIT_READY → COMPLETED
모든 실행 단계 --무결성 실패--> FAILED
실행 예산 부족 --유효 결과 보존--> FINAL(BOUNDED 또는 CLARIFY)
프로세스 소유자 상실 → INTERRUPTED
```

위 내부 phase를 journal-v2에 추가한다. stage 포트는 기존 retrieve/select/assemble/answer를 유지한다. REVIEW와 REBUTTAL은 answer 단계 내부 역할이며 바깥 재진입 control에는 REVIEW를 추가한다. cycle은 answer 진입 시 증가하며 재검토도 모델 예산을 소비한다. SELECT나 ASSEMBLE을 생략하는 재진입은 artifact revision이 현재인지 확인한다.

중요 구별: 새 도구 결과 후에는 다음 모델 판단이 필요하지만, 매번 별도 도메인 검토 모델을 호출할 필요는 없다. 조사 판단 안의 짧은 assessment를 사용한다. 메타데이터 조회 요청은 법률 COMPOSE/REVIEW를 생략한 결정론 렌더링을 허용하며 claims=[]로 남긴다.

## C07. 도메인 검토와 반론

`ReviewDecision`:

```text
checks[] {claim:C, verdict:SUPPORTED|NEEDS_RESEARCH|NEEDS_REWRITE|UNCERTAIN,
          evidence:E[], issue, reason, actions:ToolAction[]}
question {status:RESOLVED|PARTIAL|MISSING_FACT|UNRESOLVED,
          question_refs:Q[], reason}
```

claim 버전·현재 원문 제시·scope는 서버가 검사한다. 검토에 없는 C는 미검토이지 자동 탈락 확정이 아니다. 누락을 피드백해 가능한 경우 보완하고 예산이 없으면 해당 C를 미확인으로 남긴다. SUPPORTED는 evidence가 비어 있을 수 없고 그 주장의 인용 E 전체를 대조했는지 확인한다. 이 구조 검사는 법률적 지지를 증명하지 않는다.

`Rebuttal`: `{claim:C, evidence:E[], reason, requested_resolution:REVIEW_AGAIN|WITHDRAW_CLAIM}`. 검토 objection ID/version은 호출 view에서 서버가 묶는다. 새 주장은 반론으로 위장해 게시하지 않고 COMPOSE로 보낸다. 원문 없이 검토에 동의/반대하는 투표를 하지 않는다.

검토자가 근거 없는 전면 거부를 했다면 형식적 무효 검토로 정정한다. 근거를 댔지만 해석이 다른 경우에는 구체적 원문과 반론을 보존하고 제한 재검토한다. 재검토가 불일치를 해결하지 못하면 affected claim과 그 종속 claim만 보류한다. 무관한 독립 claim은 유지한다.

## C08. 출력 소비자·사용자 설명

기존 answer.text에는 검토된 설명과 필요한 실제 한계를 둔다. 기술 예외 원문·내부 P/E 번호를 그대로 노출하지 않는다. answer.claims[].source_ids는 canonical source_ids다. 실행 종료가 실패한 경우에도 ‘관련 법령이 없다’로 바꾸지 않고 ‘후보는 찾았으나 원문 확인/적용 검토를 완료하지 못함’처럼 단계를 구분한다.

assembly.term_agent.exploration_v2는 schema_version, status, finish_reason, examined/selected/unresolved counts, phase receipts summary, evidence_decisions(짧은 요약·이유), trace_binding을 담는 제안이다. 내부 상세 원문/권한 정보는 필요 이상 공개하지 않는다. UI와 GENOS 브릿지가 이 확장을 무시해도 기존 answer/unresolved는 유효해야 한다. 사용자에게 왜 근거를 쓰지 않았는지 요청받으면 실제 assessment를 근거로 설명하고 없으면 ‘미평가’라고 표시한다.

피드백은 기존 /v1/rag/feedback의 실행/답변/세대 해시 결속 후보로 보낸다. 모델이 거절한 L·E를 용어집/원문에서 삭제하지 않는다. 제품 오류 분류와 도메인 판단 오류를 별도 종류로 남겨 이후 새 검토/실험에서 다룬다.

## C09. 초기 profile과 capability

초기 제안 한도는 [설계 N01/N02](DESIGN.md)의 관측/가정 구분을 따른다. 새 필드: browse_depth_limit, max_items_per_page, max_same_error_repairs, max_review_disputes, context_policy, bootstrap_mode, capabilities_required. 해당 필드는 v2에서만 읽는다.

capability는 BROWSE/FTS/LITERAL/TITLE/TERM_MATCH/TERM_OCCURRENCE/LOCATE/DEFINITION/REFERENCE/READ/INSPECT 각각 지원·바인딩 상태를 가진다. 필수 capability가 없으면 준비 실패, 선택 capability가 없으면 모델에게 unavailable 이유와 대체 도구를 명시한다. 이름만 제공하고 handler가 없는 상태는 금지한다. 특정 phase가 browse/search를 조용히 제거하지 않는다. 검토에서 직접 실행이 필요하면 action 제안→Coordinator 실행으로 동일 registry를 사용한다.

## C10. 구현 전에 고정할 선택

제안 결정을 이미 정한 항목: 선택적 트리, 명시 target, 단일 registry, 서버 소유 상태, typed 별칭, 복구 가능한 거절, 전체 자료 자동 채택 금지, 표적 검토와 반론, 기존 API와 stage 재사용, 새 v2 계약, 원문 불변.

측정 후 정할 항목: 모델별 prompt 강도/정확 context byte limit, 표적 원문 묶음 크기, source 선읽기의 품질·비용, 품질 승격 문턱. 현재 모델 특성이나 과거 단일 사례로 수치를 단정하지 않는다. 이 미확인 사항을 숨긴 채 실행 완료로 표시하지 않는다.

## C11. Journal v2의 저장 단위와 인덱스

기존 run/event/evidence_unit/evidence_span/observation/presentation/entity_version/dependency/publication 구조를 기반으로 새 DB를 만든다. 아래는 필요한 논리 테이블과 키다. 기존 테이블에 이미 같은 기능이 있으면 adapter로 매핑하고 중복 원장을 만들지 않는다. 기존 DDL의 entity kind/phase CHECK가 닫혀 있으므로 새 값은 v2에서만 선언한다.

| 논리 테이블 | 필수 필드·키 | 주요 소비/인덱스 |
|---|---|---|
| navigation_alias | alias PK, kind, canonical_json, binding_hash, first_offered_view | kind+canonical_hash UNIQUE, 별칭 해소 |
| navigation_cursor | cursor PK, operation_hash, binding_hash, position_json | 안정 paging·잘못된 커서 거부 |
| candidate_route | candidate_key, route_key, tool_action_id, question_refs, witness, status | candidate+route UNIQUE, 경로별 거절 |
| read_coverage | source/extent, ordered intervals, read_action_id, complete_basis | 원문 범위 합집합, source+binding index |
| evidence_assessment | E, version, view_id, summary, disposition, role, reason, Q refs | E+version PK, 최신 판단/철회 |
| action_receipt | action_id PK, canonical_args_hash, state, result_hash, result_json, budget, timestamps | 중복실행 방지·partial 복구 |
| presentation_item | view_id, physical_attempt, kind, canonical_id, exact_content_hash, delivered_status | view+item PK, 원문 제시 입증 |
| domain_challenge | challenge_id, version, claim_version, source/witness, reason, status | claim+version, 반론·미해결 추적 |
| review_resolution | challenge_version, rebuttal, evidence_set, outcome, attempt_id | 검토 이의 한도·해결 이력 |
| task_gap | server gap_id, Q refs, origin, description, status, related E/C | 질문 누락·사실 부족·기술적 실패 구분 |

모델이 이 테이블의 행/SQL을 작성하지 않는다. 서버 reducer가 TurnDecision을 검사한 뒤 기록한다. 영속 event는 원문·view·도구 결과 해시를 가리킨다. 데이터베이스 transaction 실패는 rollback하며 성공한 도구의 외부 원문 읽기 자체를 되돌렸다고 표시하지 않는다. observation의 durable 기록 실패 시 그 결과를 근거로 사용하지 않고 STORAGE_ERROR를 반환한다.

## C12. 최소 입력 화면과 우선순위

view에는 view_id, original_question, Q refs, binding_summary, tool_capabilities, authorized_root, locations, last_action_results, candidate_page, exact_evidence, assessments, gaps/challenges, budgets가 있다. 출력 schema도 같은 ToolRegistry에서 생성한다. question 구간은 서버가 경계로 분할하고 빠진 텍스트 없이 원질문 전체를 보존한다. 의미 쟁점 생성은 선택 사항이다.

고정 우선순위는 질문/안전한 실행 가능 도구 계약 → 현재 검토 대상 원문·그 반론 → 복구 오류와 직전 행동 결과 → 판단·미해결 요약 → 후보 헤딩이다. 우선순위가 낮아 빠진 항목은 omitted receipt로 알리고 inspect/read/browse로 다시 접근할 수 있다. 출력 입력 크기를 맞추려고 정답 조문 기준으로 자료를 선택하지 않는다.

검색 결과 순위는 relevance의 후보 힌트다. provenance 종류를 전역 우선순위로 고정해 참조 후보가 FTS/트리 위치를 영원히 가리지 않게 한다. view는 현재 실행한 도구의 결과 페이지를 먼저 보여주고 이전 후보는 inspect(candidates)에서 접근한다. 현재 질문과 관련된 미해결 challenge는 별도 영역에 남긴다.

검토 패킷은 같은 claim 버전의 support/challenge, 원질문과 사실 상태, 이전 objection/rebuttal을 모두 포함한다. 패킷이 잘리면 검토 범위 PARTIAL이다. 이전 ‘SUPPORTED’는 근거 집합·claim·사실·정책 버전이 바뀌면 재사용하지 않는다.

## C13. 종료 gate의 구체적 판단

1. 원문/인용/권한/버전 무결성 위반은 해당 결과의 게시를 막는다. 별도 오류/한계 응답과 검토 완료된 독립 결과의 보존 가능성을 검사한다.
2. claim별 PRESENTED E, 현재 claim/review version, 정확 인용, 필요한 사실 조건이 충족되는지 확인한다. 코드가 의미 정답을 판정했다고 표시하지 않는다.
3. 미해결 challenge가 현재 결론에 영향을 줄 수 있으면 해당 claim을 제한한다. 중요도는 근거와 이유를 가진 수정 가능한 판단이다. 읽지 않은 모든 참조를 필수 과제로 만들지 않는다.
4. 질문 전체 직접 대조에서 빠진 Q/사실은 설명·질문·한계 중 하나로 드러나야 한다. 정답을 모른다는 이유로 Q를 삭제하지 않는다.
5. 재탐색 필요와 실행 가능한 행동·남은 예산이 있으면 RESEARCH, 자료는 충분하고 초안 오류이면 RECOMPOSE, 검토 이의이면 REVIEW다. priority는 원문 부족→초안 수정→검토 이의로 고정하지 않고 해당 주장의 의존 관계를 따라 선행조건부터 처리한다.
6. 충분하면 FINAL READY, 미확인 부분이 남으면 FINAL BOUNDED, 결론을 바꾸는 사용자 사실이 필요하면 FINAL CLARIFY다. 모든 상태에서 의미적 정확도는 외부 평가 대상이다.
7. SUPPORT 없이 일반 결론을 만들거나 ‘0 selected → top FTS 자동 선택’을 실행하지 않는다. 메타데이터 질문은 별도 evidence_kind=metadata의 렌더링으로 정상 종료할 수 있다. 이 구분은 내부 및 term_agent.exploration_v2에만 두고 닫힌 Answer/Request의 최상위 필드로 추가하지 않는다.

## C14. 위키·사전 지식의 범위

위키를 활용할 때는 원문 코퍼스에 등록된 해석자료 또는 해시 고정 knowledge bundle 중 어떤 경로인지 capability에 명시한다. 현재 source-first에서 위키가 자동 동작한다고 가정하지 않는다. 등록 자료라면 search/read의 동일 경계와 role=interpretive/reference를 따르고, bundle이면 lookup_definition의 navigation_hint로만 제공한다. 후자의 문장은 E 법률 원문으로 자동 승격하지 않는다.

위키의 요약·용어 힌트로 검색어를 바꿀 수 있지만 최종 법률 적용은 대상 원문·판본을 확인한다. Outdated/Disputed 표지가 있으면 그대로 전달한다. 위키/사전이 없거나 검색이 실패해도 fulltext/literal/구조 탐색의 접근을 막지 않는다. 짧은 말 필터의 정책 근거는 해당 matcher/용어 정책이며 위키 존재로 대체하지 않는다.

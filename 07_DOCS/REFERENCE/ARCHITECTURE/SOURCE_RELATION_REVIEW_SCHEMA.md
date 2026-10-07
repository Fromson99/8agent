# 원문 관계 데이터와 검토 스키마 v1

상태: ADR-0480 격리 후보의 CM003 연결/READ 프로토타입 + 운영 확장 설계. 운영 배선 변경 없음.
범위: 원문을 빠짐없이 찾아오는 연결. 사건의 법적 결론을 DB 규칙으로 미리 넣지 않는다.

## 1. 설계 결정

관계를 `함께 읽기`로 저장하지 않는다. **어느 원문 구간이 어느 구간에 대해 무엇을 하는지** 저장한다.
“관련 원문을 읽는다”는 저장된 관계를 소비하는 탐색 정책이지 관계의 의미가 아니다.
조문 A가 B와 연결된다는 사실과, 그 관계가 현재 사건에 적용된다는 판단은 분리한다.

이번 CM003의 한 관계는 다음과 같다. 아래 내용은 해당 immutable 저장 원문에 관한 것이며 최신 법률 적용 인증이 아니다.

```
시행세칙 제23조 제4항 ── SPECIFIES_DELEGATED_CASES_OF ──▶ 상장규정 제26조 제1항 제3호 단서
                  위임된 ‘경우’를 구체적으로 정한다
```

규정 제26조를 읽은 후 incoming 조회하면 세칙 제23조 제4항을 얻는다. 역방향 탐색을 하더라도
관계의 저장 방향/의미는 바꾸지 않는다. “재무적투자자는 제4호에 해당한다”는 결론은 저장하지 않는다.

## 2. 현재 코드와 차이

| 지점 | 현재 상태 | 이번 후보/제안 |
|---|---|---|
| `term_index.py`의 `reference`, `reference_end` | 명시 참조와 양 끝 article 연결 | 유지. 검토된 관계 release를 별도 sidecar로 결속하는 확장 제안 |
| `term_references.py:compile_references` | 작업 코드에 target unit path/block 기능이 있음 | 관계 제안 생성기의 parser 입력으로 사용 가능. 현재 실험 세대 재구축과 별개 |
| 선택 세대 `navigation-source-20260918-body-v1` | 기존 색인에 세부 target block/unit 필드가 실질적으로 없음 | 해당 세대의 실제 source_unit/source_block을 직접 고정한 한 관계를 별도 DB에 작성 |
| `SourceSession.execute(read_node)` | 원문 READ, 범위·해시 검증, 서버 evidence 기록 | 변경 없이 재사용. 새로운 `read_target`이 정확한 unit을 선택하고 모든 cursor를 소비 |
| `relation_issues.py` | 오연결 거절 기록만 저장. 서빙으로 돌아오지 않는 정리 목록 | 새 proposal로 이행 가능한 입력. 기존 기록/승인 없는 상태 보존 |
| `source_relations.py` (격리 후보) | 신규 | typed 관계 조회, 실험 fixture 주입, 제안 저장, 정확한 subtree READ |
| 검토 UI·인증·release 발행·서빙 등록 | 이번 구현에 없음 | 아래 계약으로 후속 구현. SQL 표가 존재한다고 서비스 완성으로 보지 않음 |

부모 ADR-0479는 원문을 작성·검토에 줘도 CM003 판단을 틀렸다. 이번 작업은 이를 해결했다고
주장하지 않는다. 모델이 놓칠 수 있는 연결을 데이터화하여 **회수 책임**을 서버로 옮기는 최소 연결이다.
초기 더블하네스의 장부 작성 실패를 되풀이하지 않도록 모델은 ID·revision·해시·트랜잭션을 만들지 않는다.

## 3. 관계 유형 — 방향과 필수 부가정보

| type | from → to의 의미 | 필요한 정보/경계 |
|---|---|---|
| `REFERS_TO` | 원문이 다른 원문을 명시 참조 | 특정 효과 미확정인 참조를 위임/예외로 과장하지 않음 |
| `DELEGATES_TO` | 위임 문장이 구체화할 기관/하위 규정의 원문을 지목 | 위임한 사항의 원문 span. 구체 대상 미상은 proposal에 남기고 확정 edge 금지 |
| `SPECIFIES_DELEGATED_CASES_OF` | 구체적 경우의 목록 → 그 경우를 위임한 문장 | 위임 문구, 대상의 본문/단서 구분, 각 호를 포함한 읽기 범위 |
| `PROVISO_TO` | 단서 구간 → 그 단서가 붙는 본문 구간 | 동일 조문 내부도 가능. 단서라고 모두 적용 제외는 아님; 효과는 원문 보존 |
| `INCORPORATES` | 준용 문장 → 준용 대상 | 포함/제외 항·호, 문구 치환, 조건의 각각 정확한 근거 구간 |
| `VALUE_DEFINED_IN` | 비율·금액·기간·산식 참조 문장 → 값/산식이 있는 구간 | value_kind, 단위 원문, 표 행·열·각주. 값 복사/자동 계산과 구별 |
| `TERM_DEFINED_IN` | 정의를 참조한 용어 구간 → 정의 원문 | 정의의 적용 범위·동명이의어 구분. 용어가 같다고 전역 연결하지 않음 |
| `CASE_BRANCH_OF` | 구별되는 대상/조건의 가지 → 공통 분기 문장 | 분기 조건 span과 결과 span. X/B 가지를 보존하며 항상 상호배타적이라고 가정하지 않음 |

위 enum은 후보 DDL에 구현했다. 유형별 qualifier의 세부 검증·자동 추출은 **확장 설계**다.
불분명하면 `REFERS_TO`로 낮춰 기록하거나 검토 대기시킨다. 새 type은 스키마 버전과 소비자 호환성을 함께 올린다.

### 한정·제외·치환을 잃지 않는 확장 payload (제안)

```
qualifiers = {
  target_role: "proviso" | "main_text" | "definition" | "table_value",
  included_anchors: [anchor_id],
  excluded_anchors: [anchor_id],
  condition_anchors: [anchor_id],
  substitutions: [{from_span, to_span, witness_anchor}],
  value_kind: "ratio" | "amount" | "duration" | "formula" | null
}
```

예: “제4항(제2호는 제외한다)을 준용”은 제4항으로 가는 edge에 제2호 제외 구간을 붙인다.
“A를 B로 본다”는 준용 관계의 치환 정보로 보존한다. 이를 LLM의 자유문장 설명 하나에만 맡기지 않는다.
qualifier 누락/미상은 `unknown`으로 보존하고 “제외 없음”으로 해석하지 않는다.
표는 셀 좌표와 머리글/단위/각주 anchor를 결속해야 하며, 현재 prototype은 텍스트 subtree만 READ한다.

## 4. 테이블과 책임

후보의 실행 가능한 DDL: `source_relations.sql` (ADR0480 candidate). 정본 원문 저장소는 수정하지 않는다.

| 테이블 | 핵심 컬럼 | 책임 |
|---|---|---|
| `anchor` | id, generation_id, store_sha256, document_id, source_id, unit_id, coordinate, selector_json, payload_sha256 | 문서 버전+조/항/호/목+블록 내 Unicode 위치. 원문 SHA와 인용 문자열 검증 |
| `relation_revision` | id, relation_id, revision, relation_type, from_anchor, to_anchor, qualifiers_json, witness_json, origin, supersedes, payload_sha256 | 관계의 불변 버전. 출처가 LLM인지 공식 데이터인지와 검토 여부는 별개 |
| `proposal` | action, base_revision, generation_id, from_anchor, candidate_json, reason, evidence_json, producer_kind/id, run_id, idempotency_key, payload_sha256 | 미완성 연결·누락 의심·오류 신고. 미상 대상 허용, 적용 권한 없음 |
| `review_event` | proposal_id, decision, reviewed_payload_sha256, reviewer_principal, auth_receipt_sha256, reason, at | 검토한 정확한 payload와 인증된 사람의 결정. 현재는 저장 계약만 구현 |
| `relation_release` | id, generation_id, store_sha256, purpose, manifest_sha256 | 한 데이터 세대에서 쓰는 불변 관계 묶음. fixture와 published 구분 |
| `release_member` | release_id, revision_id, approval_event_id | 해당 release에서 활성인 exact revision 목록. published는 승인 증거 없는 삽입 거부 |

`anchor.selector`에는 `kind`, 원천 artifact hash, `spans[{block_id,start_cp,end_cp,text,block_hash,span_hash}]`가 들어간다.
범위는 Unicode code point 기준 `[start,end)`다. **관계 증명 span과 회수 extent는 다르다.**
CM003의 witness는 블록236 머리문장 한 개지만 회수 extent는 저장 unit218 전체 블록236~244다.
regulation 쪽 anchor는 블록301에서 “다만,”이 시작되는 위치 이후의 단서다.

`coordinate`는 읽기 쉬운 보조 라벨이다. 최종 인용용 법령명·조문명은 모델/제안자가 적은 라벨을 믿지 않고
immutable 문서/구조 ID를 조회하여 서버가 구성해야 한다. 현재 exact subtree 검증은 수행하지만 자유 라벨의 의미를 인증하지 않는다.

구체적인 두 endpoint가 확정되지 않은 proposal은 active relation이 될 수 없다. 여러 대상이 정확히 열거되면
각 대상별 edge와 공통 witness를 만든다. 모호한 후보 여러 개를 모두 확정 관계로 만들지 않는다.

### 상태는 세 축으로 분리한다

- 증거/해결: `unresolved / ambiguous / exact` (확장 검증 receipt에 기록).
- 검토: `pending / needs_info / approved / rejected` (proposal + review_event로 도출).
- 활성화: 특정 release에 포함됐는가. 승인됐다고 현재 요청의 release를 즉시 바꾸지 않는다.

원문과 정확히 맞는 span이라는 것만으로 의미상 관계가 옳다고 보장하지 않는다.
LLM confidence가 높아도 human-approved로 자동 승격하지 않는다.

## 5. LLM 자동 작성과 사람 검토 흐름

```
parser/LLM → 제안 또는 누락·오연결 신고 → 기계적 원문 검증
          → 사람 검토(수정 가능) → exact payload 승인
          → 새 관계 revision + 새 release → 다음 요청에 명시 적용
```

1. 배치 추출 LLM은 원문·문서 구조를 보고 관계 유형, 출발 구간, 목표 locator, 증거 구간, qualifier를 제안한다.
   목표를 못 찾으면 `MISSING`과 원문 근거·찾는 대상의 설명을 남긴다. 임의 source ID를 만들지 않는다.
2. 질의 중 모델도 `ADD/MISSING/CORRECT/REMOVE`를 제출할 수 있다. CORRECT/REMOVE는 기존 exact revision을 지목한다.
   모델에는 도구의 짧은 별칭을 제공하고 서버가 binding된 ID로 해석하는 API를 후속 연결한다.
3. proposal writer는 append-only 권한만 받는다. 모델이 `approved=true`를 넘겨도 거부한다.
   제안은 해당 질문의 증거가 아니고, 제안 실패 때문에 최종 답변 작성을 막지 않는다.
4. 기계 검사는 원문 일치, 범위, 실제 항·호 존재, 세대, 중복, 타입별 필수 항목을 검사한다.
   연결의 법적 타당성은 사람 검토 대상으로 남긴다. 연도/개정 시점이 다른 원문을 자동 결합하지 않는다.
5. 사람 화면은 양쪽 원문·각 호·witness·한정/제외·변경 전후 diff를 나란히 보여야 한다.
   reviewer identity는 로그인 세션에서 가져오며 모델 출력의 `actor=human`을 절대 사용하지 않는다.
6. 수정 승인 시 수정한 payload를 새 버전으로 만들고 그 hash를 승인한다. 이후 수정하면 승인은 무효다.
   실행 중인 요청은 기존 release 고정; publish는 승인된 snapshot에만 원자적으로 포인터 교체한다.
7. 오연결 신고만으로 기존 relation을 삭제하지 않는다. 사람이 REMOVE를 승인하면 새 release에서 제외하고
   과거 release·revision·신고·검토 이력은 남긴다. 긴급 격리는 별도의 관리자 권한/감사 이벤트다.

현재 prototype은 제안 저장·중복 키 재사용 검사·역참조·읽기만 실행한다. 자동 LLM 추출기, 로그인,
검토 화면, 서비스 권한 분리, 원자적 게시 및 세대 재구축은 구현하지 않았다. SQL의 approval hash 제약은
인증을 대신하지 않는다. published 조회는 후보에서 아예 비활성이고 실제 사람 승인 건수는 0이다.
앱 API는 append-only지만 DB 소유자에게 직접 SQL 변경을 금지하는 ACL/운영 trigger는 후속 작업이다.

## 6. 회수와 최종 출처 표

질문 → 기존 탐색/READ → 읽은 source에 맞는 relation release 조회 → 해당 target의 정해진 extent READ
→ 서버 evidence 기록 → 모델에 실제 제시 → 모델이 인용한 evidence 검증 → 서버 최종 출처 표.

관계 metadata/preview 조회만으로 evidence나 인용 자격을 생성하지 않는다. `read_target`은 실제
`SourceSession.execute`를 호출하며 page cursor를 끝까지 처리하고 원문 전체 extent와 재대조한다.
제시/인용은 기존 하네스의 별도 계약이다. 이번 probe는 READ까지만 검증했으므로 모델 제시/최종 인용은 0이다.

최종 표의 확장 제안:

`claim_id → citation/evidence_id → document version + article/subunit + actual cited spans + source hash`

관계 경로는 별도 설명 컬럼으로 둘 수 있지만, 조회한 relation 전체를 최종답변의 근거로 출력하지 않는다.
읽기 이력·제시 이력·최종 인용을 분리한다. 이번 실험 결과의 evidence 목록은 최종답변 출처 표가 아니다.

## 7. 실패·운영 경계

| 조건 | 동작/복구 |
|---|---|
| 원문 hash/세대 바뀜 | 자동 재결속 금지. 새 anchor 후보 + 재검토/재발행. 과거 release 재현 가능 |
| 대상 원문 없음/모호함 | proposal의 target 미상 유지. 필요 자료 수집 후보, 임의 첫 번째 target 선택 금지 |
| 요청 권한 밖 대상 | 원문/문서명 노출 없이 TARGET_OUTSIDE_SCOPE. scope 자동 확대 금지 |
| 그래프 순환·중복 | 운영 확장 시 `(generation,anchor,revision,direction)` visited 집합, hop/페이지 상한, 미완료 목록 기록 |
| 페이지 중단/예산 소진 | partial evidence는 기록해도 complete=false. 완전 회수/법령 부재로 오인 금지 |
| exact span만 있는 대상 | 현재 adapter는 fail-closed. 전문으로 몰래 넓히지 않음. 세부 span READ adapter 후속 구현 |
| 중복/재시도 | idempotency key 동일 payload는 기존 proposal 반환, 다른 payload면 충돌. 동시 submit 충돌 재조회 API 후속 구현 |
| 두 검토자의 동시 수정 | base revision CAS 확인 후 한 건만 발행. 오래된 검토는 재검토; publisher 후속 구현 |
| DB/추출기 장애 | 정상 원문 탐색 유지, 연결 미확인 한계 표시. 관계 장부 완성을 답변 전제조건으로 만들지 않음 |
| 악성/틀린 LLM 제안 | untrusted observation으로 저장. 모델에는 승인·게시 권한 없음; 사람 검토/타입별 검증 후에만 활성화 |

토큰 7만은 허용 가능한 사용자 예산이지 현재 구현이 지원한다는 뜻이 아니다. 기존 60,000자 설정은
이번에 바꾸지 않았다. 필요한 항·호와 예외를 유지하되 무관한 법령 전문을 일괄 투입하지 않는다.

## 8. 검증·도입·예상치

실측 결과는 ADR-0480/result.json이 정본이다. 성공 기준은 한 explicit relation의 올바른 원문 READ이며
정답률·LLM 자동 작성률·누락률·사람 검토 처리량은 미측정이다. CM003 수동 링크는 인샘플이므로 독립 성능 근거가 아니다.
부모의 전체 탐색 기준군을 다시 돌린 것이 아니다. “empty relation release”와 “one relation release”의 연결 차이만 비교한다.

- M1: 신규 relation contract 18개 + 기존 source-first 47개. 합성 계약 단위이며 실제 법률 정확도와 구별.
- M2: CM003 기대 target은 unit218의 9개 source block. 3블록/page로 3페이지를 모두 READ해야 통과.
- M3: 이번 모델·judge 호출 목표 0회. LLM 자동 추출의 비용 절감은 아직 미산정.
- 비용 계산식: 구축/검토/재개정 비용 + 질의당 관계 조회/추가 READ 비용 − 반복 관계 탐색 비용.
  재사용이 적거나 잘못된 링크가 많으면 비용이 증가한다. 재사용 횟수·검토 시간 실측 전 손익분기 단정 금지.

도입 순서: (1) 단일 link 검증 (2) 타입별 qualifier schema와 실패 사례 (3) 인증된 proposal/review/publisher
(4) 해시 고정된 새 relation release를 기존 navigation에 주입 (5) 별도 어려운 사례/전체 51문항에서 회수·인용·정답 검증.
기존 어려운 문제는 `fsc_hard_retrieval_v3.json`에 있으나 이 실험에서는 실행/변경하지 않았다.
롤백은 기존 release 포인터로 복귀하고 새 proposal/review 이력은 보존한다. 운영 활성화는 별도 승인이다.

자체 검토이며 독립 감독 검토/배포 승인이 아니다. 구현 설계 보고서 스킬에 따라 구현·설계·미확인을 분리했다.

## 근거

- `04_EXPERIMENTS/ADR/ADR-0480-cm003-reviewed-source-relations/PLAN.md`, `실험/manifest.json`, `artifacts/run-001/`
- `02_BACKEND/lawrag/research/candidates/adr_0480/explicit-link/revisions/rev-002/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_relations.py`
- 같은 경로의 `source_relations.sql`
- `02_BACKEND/semantic_runtime/legal_agent/source_tools.py`, `term_index.py`, `term_references.py`, `relation_issues.py`
- `07_DOCS/REFERENCE/ARCHITECTURE/DATA_LINKAGE_AND_HARD_CASES.md`, `SOURCE_RETRIEVAL_AND_PROVENANCE.md`

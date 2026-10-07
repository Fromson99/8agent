# 탐색 사유·선택형 원문 읽기·준용 관계 안내 추가 구현 설계

작성일: 2026-09-21. 상태: **구현 제안 / 코드 연결 자체 검토 / 미구현·미실험·미배포**.

기준은 현재 작업 코드의 `legal-agent-tools-v2`다. 이전 [도구 탐색 설계](../TOOL_EXPLORATION_DOUBLE_HARNESS_20260921/DESIGN.md)를 덮어쓰지 않는 후속 설계다. 사용자 요구는 도구 실행 이유, 원문 채택·기각 이유, 후보 정보를 보고 읽기 선택, 준용 연결의 자동 안내다. 이번 산출물은 설계이며 코드 변경이나 MAIN 활성화가 아니다.

## 1. 결정 요약

다음 기능을 기존 요청 세션에 추가한다. 새 독립 실행기나 별도 RAG 파이프라인은 만들지 않는다.

- **행동·판단 기록:** 실행 전 목적 → 실제 결과 → 원문 평가 → 판단 수정 → 최종 주장 연결을 저장한다. 다음 모델 입력, 검토자, 사용자용 요약이 같은 기록을 소비한다.
- **후보 발췌:** 제목·좌표만이 아니라 일치 위치의 실제 원문 발췌와 표시 범위를 제공한다. 후보 발췌는 읽기 선택용이며 답변의 인용 근거가 아니다.
- **자동 관계 안내:** READ 뒤 직접 명시 참조를 조회하여 출발 문구·방향·관계 유형·대상·미해결 상태를 함께 보여 준다. 관계 없음과 조회 미완료를 구별한다.
- **제한된 준용 선읽기:** 유일하게 해소되고 허용 범위에 있는 outgoing 준용 대상은 정책에 따라 자동 READ한다. 일반 인용·역참조·모호한 대상은 자동 전문 읽기 대상이 아니다. 자동 읽기는 모델의 자발적 발견으로 집계하지 않는다.
- **관계 확인 조건:** 준용에 의존하는 주장은 출발 원문과 대상 원문, 적용 범위·치환·예외의 검토가 없으면 확정하지 않는다. 관련 없다는 판단도 이유와 검토를 남긴다.

원칙: **자동 발견 ≠ 원문 제시 ≠ 이해 ≠ 채택 ≠ 사례 적용 확정.** 시스템은 기록·권한·제시·완료 조건을 검사하고, 법적 관련성과 문언 해석은 모델 판단 및 후속 사람 검증 대상으로 남긴다. 내부 사고과정 전체가 아니라 검증 가능한 짧은 행동 목적·근거 설명을 기록한다.

### 범위 및 배포 상태

전체 MAIN 중 RAG 서빙과 실행에 연결된 피드백이 변경 대상이다. 원문 구조화·용어집 정본·의미 추출 체계의 재설계는 제외한다. 폐기한 Rule/조건/효과 의미 스키마를 복원하지 않는다.

작업 `PIPELINE.json`의 기본은 v2지만 로컬 활성 포인터는 `document-navigation-rag-20260921-v1`, 포인터 generation 17이다. v2 기본 프로필 모델은 미결속이다. GENOS는 이 세션에서 접근 불가이며 내부 모델·현장 화면·성능은 미확인이다. 기준 파일 지문은 별도 [BASELINE.json](BASELINE.json)에 남긴다.

## 2. 확인한 현재 연결과 빈 부분

| 영역 | 현재 코드에서 확인한 사실 | 추가 구현 필요 |
|---|---|---|
| 요청 | service → app.ask → Pipeline → ServingLegalAgent.open_session → Coordinator/StageRunner → outbox | 이 경로를 유지하고 버전 선택만 확장 |
| 도구 이유 | `protocol.action`의 reason 필수, `record_observation`의 request_json에 저장 | 질문 연결·실행 주체·원인 행동·기대 확인 사항, 원본 이유와 재시도 구분 |
| 원문 평가 | v2 assessment에 summary/disposition/role/reason/question_refs. 현재 평가를 다음 view와 metadata에 제공 | 평가 없는 READ를 기각으로 오인하지 않는 전수 상태, 과거 수정 이력, 질문별 상반된 평가 |
| 후보 | `ExplorationTools.node_card`에 제목·좌표·위치·route·read_action | 발췌·발췌 좌표/해시·실제 표시 영수증. 고정 사유 ‘원문 확인’의 무비판적 복사 방지 |
| 과거 발췌 | `MultiSession.term_hits`가 용어 출현 주변 원문을 preview_only로 제공 | 아이디어만 재사용. 후보 등록 부작용이 있는 source_card를 새 경로에서 직접 호출하지 않음 |
| 참조 색인 | reference JSON에 reference_role/basis, source_text/hash, mention 좌표, source/target unit 및 block 범위 | 자료별 필드·해소 상태 확인. 누락 필드를 준용으로 추정하지 않음 |
| v2 참조 조회 | 모델이 follow_reference를 골라야 실행. 대상 카드·witness·direction·resolution 제공 | 역할·역할 근거 누락 복원, 자동 동봉, 정확 witness/target 범위 보존 |
| 원문 읽기 | READ와 coverage, 실제 성공 view의 정확 E 검사 존재 | 관계 발견/선읽기 작업의 영속 큐·공통 예산·부분 성공 연결 |
| 최종 판정 | 주장 검토와 전체 질문 상태로 READY/BOUNDED/CLARIFY 결정 | 준용 의존 상태를 주장별 완료 판정과 무효화 의존성에 연결 |
| 출력 소비자 | metadata에 현재 evidence_decisions. 로컬 app.home은 답변·한계, GENOS render는 답변·출처 위주 | 실행·기각·관계 요약의 실제 화면 소비 경로 필요. JSON 저장만으로 화면 완료 처리 금지 |

참조 유형은 현재 색인에서 문언의 `준용` 등으로 분류하는 **탐색 단서**다. 한 문장에 여러 대상·인용·준용이 섞이면 역할이 대상별로 정확하지 않을 수 있다. 유형 표시를 확정 법률관계로 승격하지 않는다.

## 3. 목표 실행 흐름

```text
기존 요청/권한/세대 결속
  → 도구 선택 + 목적 기록
  → 검색·지목·구조 탐색 → 후보 카드 + 실제 발췌
  → READ 선택 또는 후보 보류/재탐색 + 이유
  → 원문 READ 영속 저장
  → 직접 참조 조회 작업 등록·실행
      ├─ 관계 안내 + 대상 카드 + 미해결/미제시 상태
      └─ 유일·허용 outgoing 준용 → 제한된 자동 READ → 하위 관계는 안내만
  → 모델 입력 조립: 출발 원문 / 대상 원문 / 관계 안내 / 목적·결과·이전 판단
  → 성공 전송 영수증 → 원문·관계별 평가
  → 미확인 관계 처리: 추가 읽기 / 사유 있는 제외 / 한계 유지
  → 초안 → 출발·대상·관계 공동 검토 → 재탐색/반론 또는 게시
  → 답변 + 한계 + 판단 요약 + 실행 기록 식별자 → 기존 피드백
```

특정 문서·조항이 명확하면 locate → READ로 바로 간다. 모든 요청에 목록·트리·후보 평가를 강요하지 않는다. 일반 탐색에서는 발췌를 보고 선택한다. 같은 턴에 새 도구 결과를 받기도 전에 기각·채택·DRAFT할 수 없는 현재 제시 검사는 유지한다.

## 4. 추가 계약 — 제안 이름이며 현재 API가 아님

### 4.1 ActionPurpose / ActionReceipt

모델 ToolAction에는 기존 tool/args/reason에 `question_refs`, `expected_information`을 추가한다. 사유는 ‘찾아보기’가 아니라 무엇을 확인할지 설명한다. 질문 없는 내부 점검은 question_refs를 비우되 도구 상태 확인 목적을 명시한다. 문자열 공백만인 이유와 미제시 대상을 거부한다. 이유의 의미적 충실성은 형식 검사만으로 보장하지 않는다.

서버가 채우는 영수증:

| 필드 | 의미·검사 |
|---|---|
| action_id, actor | MODEL / SYSTEM_POLICY / REVIEWER. 서버가 실제 호출 경로로 결정, 모델 임의 지정 불가 |
| parent_action_id, trigger_reference_id | 자동 참조 조회·선읽기를 원인 READ에 연결 |
| policy_id/hash | 자동 행동 목적을 결정한 고정 정책. 모델 reason으로 위장하지 않음 |
| input_view_id, proposed_action | 실제 모델이 본 입력과 제안 원본. 시스템 행동은 model view가 없음을 명시 |
| effective_args, status, observation_id | 실제 실행 범위·오류·결과. 서버가 범위를 조용히 넓히지 않음 |
| evidence_ids, relation_ids, next_cursor | 읽은 원문·발견 관계·부분 완료 |
| consumed_budget, reused_from | 실제 예약·시간·캐시 재사용. 새 발견/새 I/O와 구별 |

같은 action_id의 재전송은 목적을 포함한 canonical proposal hash가 같아야 한다. I/O 캐시는 tool/args/세대 기준으로 공유할 수 있으나, 서로 다른 이유로 다시 수행한 행동 기록을 합치지 않는다. 실행되지 않은 제안·예산 전 중단도 `NOT_EXECUTED`와 서버 사유로 남긴다. 모델의 사후 이유로 실행 전 목적을 덮어쓰지 않는다.

### 4.2 CandidatePreview

`node_card`는 부작용 없는 카드 생성과 route 등록을 분리한다. 카드 생성 자체를 신규 발견으로 세지 않는다.

- 위치: candidate_id, source_id, document/version, unit_path, target extent, 권한 범위, 세대 hash.
- 발견 단서: query/term/reference 및 parent action. ranking은 검색 우선순위이지 적용 가능성 점수가 아니다.
- 발췌: `preview_spans[{block_id,start_cp,end_cp,text,block_hash,span_hash}]`, `preview_basis`, `source_chars`, `preview_chars`, `preview_complete`, `truncated`, `suppressed_reason`.
- 상태: `citation_eligible=false`, 현재 요청의 READ/제시/평가 상태는 별도 계산한다. 이미 읽은 후보를 항상 content_read=false로 표시하지 않는다.

발췌 우선순위는 저장된 일치 span → 검증된 참조 witness 주변 → 제목/선두 원문 순이다. FTS가 hit offset을 제공하지 않으면 없다고 표시하고 선두 발췌를 사용한다. 형태소 순위로부터 정확 일치 좌표를 발명하지 않는다. 표/항목을 잘라 붙여 새 문장을 만들지 않고 생략과 개별 span을 표시한다.

발췌 정책은 기본 READ 범위와 분리한다. 실제 전송 view에서 살아남은 preview hash/범위만 presented로 기록한다. 제목만 보여줬거나 context limit로 빠졌으면 발췌 제시로 세지 않는다. 발췌 전체가 짧은 원문과 같아도 READ·정확 E 제시 계약 없이 인용하지 않는다.

### 4.3 EvidenceDisposition / CoverageLedger

기존 ADOPT/REJECT/DEFER와 SUPPORT/CHALLENGE/CONTEXT를 유지하되 평가 단위는 `(E, question_ref)`로 한다. 같은 원문이 질문 일부를 지지하고 다른 부분에는 적용되지 않을 수 있다. 서버가 평가 ID·version·supersedes를 관리하고 기존 판단 이력을 보존한다.

모델 평가: summary, disposition, role, reason, question_ref, `basis_spans`(현재 제시 E 내부의 정확 인용 범위), 필요 시 `related_relation_ids`. 원문 관련성 기각은 검증 가능한 짧은 이유를 요구한다. REJECT는 ‘해당 질문/주장의 근거로 제외’이지 문서가 무효라는 뜻이 아니다.

다음 상태를 혼합하지 않는다.

| 상태 | 책임·의미 |
|---|---|
| PREVIEW_ONLY / PARKED | 아직 원문 평가가 아님. 후보를 보류한 사유 기록, 재열기 가능 |
| READ_STORED_NOT_PRESENTED | 원문은 저장했지만 모델에게 전달하지 못함 |
| PRESENTED_UNASSESSED | 제시됐으나 판단 응답이 없음 |
| ADOPT / REJECT / DEFER | 모델이 실제 제시된 원문을 평가함 |
| STALE | 후속 원문·질문·관계 변경으로 재평가 필요 |
| UNASSESSED_AT_STOP | 종료 시 남은 미평가. 예산/전송/중단 사유를 서버가 기록 |

모든 READ에 상태는 남기되 모든 READ에 억지 기각을 요구하지 않는다. 종료 직전 모델의 형식적 사유를 받으려 무한 재호출하지 않는다. 판단하지 않은 관련 원문·자동 준용 대상은 최종 확인 한계에 반영한다. 단순히 발견한 모든 후보를 읽거나 평가해야만 답변할 수 있는 전역 장부는 만들지 않는다.

### 4.4 RelationNotice

공용 순수 어댑터 `reference_cards`(제안)를 자동 동봉과 수동 follow_reference가 같이 사용한다. v2에서 빠진 역할과 세부 범위를 복원한다.

필드: `relation_id`, `reference_id`, `from_source/unit`, `direction`, `reference_role`, `reference_role_basis`, `role_status`, `witness_spans/hash`, `mention_span`, `target_candidates`, `target_unit_path/block_ids`, `resolution`, `witness_presented`, `target_read_coverage`, `target_presented`, `scan_status`, `next_cursor`, `guidance_code`.

- 자동 조회는 이번 READ 범위와 실제 겹치는 witness/mention을 기준으로 한다. 같은 조의 다른 항에 있다는 이유만으로 현재 읽은 항의 준용이라고 설명하지 않는다.
- 블록 ID와 부분 문자열만으로 관계 위치를 확정하지 않는다. 색인의 mention 좌표·source_text/hash와 원문 블록을 검증한다. 준용 문언 전체를 아직 읽지 않았으면 문맥 추가 읽기를 안내하고 `witness_presented=false`를 유지한다.
- target_block_ids가 있으면 우선 보존한다. unit 정보가 없다는 이유로 자동으로 조 전체로 확장하지 않는다. 판본·범위·대상이 유일하지 않으면 미해결로 남긴다.
- `reference_role=APPLIES_MUTATIS_MUTANDIS`는 ‘문언상 준용 단서’다. `role_status=HINT`에서 시작하며, 출발 문언의 현재 view 확인 및 모델 검토와 분리한다. 혼합 문장으로 유형이 불명확하면 `AMBIGUOUS` 안내만 하고 자동 적용하지 않는다.
- incoming은 ‘B가 A를 참조함’으로 표시한다. A가 B를 준용하는 것으로 방향을 뒤집지 않는다. 용어 bridge·유사 검색은 명시 준용과 다른 경로다.
- 누락·오류·페이지 남음은 `scan_status=PARTIAL/FAILED`다. 빈 배열을 ‘관계 없음’으로 해석하지 않는다. 스캔 완료도 선택 색인 범위에서 완료한 것이며 실제 법률관계 전체의 완전성을 뜻하지 않는다.

고정 안내 문구는 신뢰된 정책 템플릿에서 생성하고 원문은 별도 data 영역에 둔다. 원문의 명령형 문장을 에이전트 지시로 실행하지 않는다.

> 준용 확인 필요: A의 표시된 문구가 B를 준용한다고 밝힙니다. B의 읽기·제시 상태는 아래와 같습니다. 이 관계에 의존하는 결론을 내리려면 A의 준용 범위·치환·예외와 B의 대상 범위를 함께 확인하십시오. 이 안내는 사례 적용 확정이 아닙니다.

미제시 witness에는 ‘준용 단서가 색인에 있으나 해당 문언은 아직 제시되지 않음’이라는 다른 문구를 쓴다.

## 5. 자동 동봉·선읽기 정책

### 동작 결정표

| 발견 관계 | 자동 안내 | 자동 대상 READ | 답변 확정 조건 |
|---|---|---|---|
| outgoing 준용 단서, witness 검증, 유일·허용·범위 확정 | 수행 | 공유 예산 안에서 제한된 직접 대상 선읽기 | 출발·대상 정확 E 제시 및 관계 공동 검토 |
| 준용 단서는 있으나 witness 문맥 미확인 | 미확인 안내 | 우선 출발 문맥 확인, 대상 읽기는 대기 | 준용 여부·범위부터 확인 |
| 준용 대상 복수·미해소·버전 충돌 | 수행 | 임의 선택 금지 | 지목/검색으로 해소 또는 의존 주장 보류 |
| 일반 인용·위임 범위 단서 | 수행 | 기본은 모델 선택 | 해당 관계를 근거로 사용할 때 추가 검토 |
| incoming / 용어 연관 | 방향·경로를 구별해 수행 | 기본은 모델 선택 | 참조 존재만으로 적용 주장 금지 |
| 권한/요청 scope 밖 | 제한 사실만 제공 | 금지 | 요청 범위 내에서는 확인 불가로 기록 |

기본 자동 READ 깊이는 직접 대상까지만이다(N01). A→B를 자동 읽었을 때 B→C는 안내·대기 상태로 남고 자동 재귀 READ하지 않는다. 모델이 C 확인을 선택하면 일반 READ가 가능하나, 단순 E 재제시/캐시 재사용으로 자동 깊이를 초기화하지 않는다. `(generation, canonical target extent)` 방문 기록과 edge 기록은 분리해 순환 A→B→A도 보존하되 중복 자동 읽기는 막는다.

초기 자동 선읽기 적격성은 기계적으로 확인 가능한 조건으로 제한한다: 검증된 원문 frame에 단일 참조 mention, 저장된 준용 단서, 유일 대상, 정확한 대상 범위, 허용 scope, 원문 hash 일치. 복수 mention·혼합 유형·좌표 결손은 안내만 한다. 여기서 witness 검증은 서버가 저장 원문과 위치를 확인했다는 뜻이며 모델이 읽고 의미를 확인했다는 뜻이 아니다. 자동 선읽기는 그 전에도 수행될 수 있고, 이후 성공 view에서 출발·대상·안내가 실제 제시되어야 평가할 수 있다. 잘못 붙은 준용 단서 때문에 불필요한 선읽기가 생길 가능성은 남기되 적용 확정으로 전파하지 않는다.

자동 선읽기는 중요 관계를 놓치지 않도록 노출하는 정책이지, 먼저 읽었다는 이유로 채택하는 정책이 아니다. 사용자가 지정한 scope는 넓히지 않는다. 임시 탐색 필터는 원 요청의 허용 corpus 안에서만 돌아갈 수 있다.

제안 프로필 항목: preview span/총 글자 한도, relation notice 페이지/총 글자 한도, `auto_reference_read_depth`, `max_auto_reference_reads_per_request`, `max_auto_reference_chars_per_request`, 참조 스캔 시간 한도, 최종 평가·검토용 예산 reserve. 깊이 외 구체 수치는 자료 길이·모델 wire 한도 확인 후 프로필에 명시하며 ‘무제한’을 기본으로 두지 않는다.

자동 참조 조회·READ도 공통 도구 횟수·시간·원문/입력 예산을 예약한다. 추가 LLM 호출 없이 서버가 실행할 수 있어도 I/O·토큰·검토 비용은 사라지지 않는다. 슬롯이 부족하면 `AUTO_READ_SKIPPED_BUDGET`로 남기고 다음 view 및 최종 한계에 전달한다. 앞선 성공 READ를 취소하거나 자동 채택하지 않는다.

## 6. 판단·검토·완료 조건

관계 상태는 하나의 ‘완료’ 플래그 대신 축을 분리한다: 발견/제시, 대상 해소, READ coverage, 질문별 관련성, 검토 결과. 제안 `RelationAssessment`에는 relation_id, question_ref, decision(RELEVANT/NOT_RELEVANT/DEFER), reason, 출발·대상 evidence_refs, 확인한 범위·치환·예외 메모를 둔다. 자동으로 Rule 정본을 생성하지 않는다.

1. 채택한 E에 표시된 준용 관계는 관련성 판단을 해야 한다. 미판단을 NOT_RELEVANT로 간주하지 않는다. 미완료 스캔·미제시 관계도 한계로 드러낸다.
2. NOT_RELEVANT는 현재 질문/주장에 한정된 제외다. 출발 E의 근거와 이유를 검토자에게 제시한다. 출발 문언만으로 제외 가능한 경우 불필요한 대상 전체 READ를 강제하지 않는다. 대상 내용에 관한 이유라면 그 대상 E를 실제로 읽어야 한다.
3. RELEVANT이고 주장이 준용에 의존하면 출발 witness와 대상 범위의 실제 제시 및 coverage가 필요하다. 대상 일부만 읽었다면 확인한 범위로 주장을 제한하거나 필요한 항·단서까지 이어 읽는다.
4. Draft에 `relation_dependencies`를 추가한다. 모델의 빈 dependencies만 믿지 않고 채택 E에 연결된 준용 notice를 서버가 재대조한다. 관련성 미판단·미해소·미제시 관계를 숨긴 주장은 완료 검사에서 거부한다.
5. reviewer는 관계가 있는 각 주장에 출발/대상 E, 적용 범위·치환·예외, 관계 제외 사유를 함께 확인한다. 반대 근거와 기각 이력을 숨기지 않는다. 출발 E와 대상 E가 컨텍스트에 함께 못 들어가면 의미 검토 완료로 세지 않는다.
6. 판단 수정·대상 재해소·새 관계 발견 시 그 상태에 의존한 claim/review만 STALE로 만든다. 관계集合 변경 버전도 의존성에 넣어 나중에 발견한 관계가 이전 검토를 우회하지 못하게 한다.
7. 막힌 주장은 보류하고 독립적으로 확인한 주장은 반환할 수 있다. 영향을 받는 질문이 남으면 BOUNDED, 사용자 사실이 필요하면 CLARIFY다. 모델 없이 목록을 조회하는 요청에는 의미 관계 검토를 강요하지 않는다.

코드는 좌표/제시/누락/의존성 검사를 할 수 있지만, ‘실제로 준용과 무관한 결론인가’, ‘치환을 올바르게 읽었는가’를 완전히 판정하지 못한다. 모델의 근거 없는 제외·잘못된 reviewer 동의는 잔여 위험이며 품질 평가 항목이다.

## 7. 저장·재시도·복구·표시

### 저장과 원자성

기존 event/entity_version/observation/evidence/model_view/presentation/publication을 재사용한다. 추가 제안 테이블은 action_context, preview_presentation, relation_notice, relation_assessment 및 dependency head, system_task다. 실제 DDL은 다음 내부 journal 버전으로 고정한다.

READ의 E·observation·action receipt와 참조 조회 작업 등록을 같은 트랜잭션으로 확정한다. 대형 원문 조회는 트랜잭션 밖에서 수행하되 검증된 결과와 작업 intent를 함께 commit한다. 현재 execute의 observation 저장과 action_receipt 저장 사이 경계를 그대로 두고 새 자동 처리를 덧붙이지 않는다.

자동 작업은 `run + parent_action + policy_hash + reference_id + target_extent`로 중복 방지한다. 관계 조회와 각 선읽기의 성공/실패는 독립 영수증으로 남긴다. 대상 읽기 하나의 실패로 A의 성공 원문을 지우지 않는다. context budget 전에 제시하지 못한 자동 결과는 저장 성공/미제시 상태를 유지한다.

소유자를 잃은 RUNNING은 기존처럼 INTERRUPTED로 종료하고 미완료 작업도 기록한다. 이번 설계에 자동 세션 재개·중단 후 모델 재호출은 포함하지 않는다. 같은 살아 있는 요청 안의 재시도만 idempotent하게 처리한다. COMMIT_READY의 게시 재시도는 고정 응답을 재사용하며 관계를 재조회하지 않는다.

### 다음 모델 입력

`ToolsSession.view`를 확장하여 현재 질문 관련 미완료 관계·실행 목적/결과·평가 변경 요약을 넣는다. 최근 행동만 잘라서 필수 준용 notice가 사라지지 않게 한다. 장문의 전체 history를 매번 주입하지 않는다. inspect에서 이전 행동·판단 버전·관계 상태를 페이지로 조회할 수 있게 한다.

필수 출발/대상 E와 관계 안내를 우선 패킹하고 발췌·선택 후보는 남는 공간을 사용한다. 필수 자료가 안 들어가면 부분 검토 또는 재탐색으로 반환하며, 누락 자료를 검토했다고 표시하지 않는다. 정확 E와 preview를 다른 필드로 두고 현재 strip_text가 preview를 무심코 제거하지 않는지 wire 수준에서 검사한다.

### 사용자·운영자 소비자

외부 term-runtime-v1의 닫힌 최상위 Result는 유지한다. 새 내부 계약으로 검증한 `assembly.term_agent.exploration_v3`에 action_summary, evidence_decisions, relation_checks, outstanding_checks, audit(run_id/revision/hash/complete)를 둔다. 전체 원문·provider 원시 응답·인증 정보·로컬 경로를 사용자 trace에 복사하지 않는다.

- 로컬 `app.home`: 답변 아래 ‘탐색·근거 판단’ 펼침 UI에서 실행 이유, 채택/기각/보류, 준용 대상 읽기 여부, 판단 변경을 표시한다. 텍스트 이스케이프를 적용한다.
- GENOS `genos_rag_chat.render`: 기존 답변·출처에 짧은 ‘확인 과정/미확인 관계’를 덧붙인다. 모델로 답변을 다시 생성하지 않는다. 플랫폼이 접기 UI를 지원한다고 가정하지 않고 텍스트 표시로 설계한다.
- 서버 journal: 전체 이력의 정본. 화면 요약이 잘리면 truncated/총수/미확인 수를 명시한다. ‘전체 기록 제공’은 저장 정본 보존을 뜻하며 모든 원문을 채팅에 노출한다는 뜻이 아니다.
- 운영자 전체 조회: 기존 run_tool 진입점에 읽기 전용 `legal_agent_trace.py` 명령을 추가하는 방안(제안). 명시 run_id와 runtime root로 지문·권한을 검증하고 순서화된 JSON을 출력한다. 기존 공개 HTTP에 run_id만으로 journal을 읽는 endpoint를 추가하지 않는다. 사용자별 전체 조회 API는 소유권 인증 계약이 마련된 뒤 별도 구현한다.
- 피드백: 기존 run/answer/generation 결속을 유지한다. 새 내부 relation/assessment ID를 피드백 대상으로 받을 경우 피드백 schema와 소비자도 함께 버전 확장한다. 최초 구현은 기존 피드백으로 실행을 가리키고 해당 이력에서 원인을 조사한다.

표시된 reason은 ‘모델이 제출한 판단 설명’, 자동 reason은 ‘시스템 정책’으로 구별한다. 저장이 됐다는 이유로 설명의 진실성까지 인증하지 않는다.

## 8. 변경 지도·호환성·재구축

이 설계의 모델 메시지와 저장 필수 항목은 기존 v2와 호환되지 않는다. **내부 제품 계약 v3를 새로 만들고 v1/v2 재현 경로는 보존**한다. 이름은 제안이다: legal-agent-tools-v3 / legal-agent-rag-v3, tool-exploration-v3.schema.json, journal-v3.sql, domain-v3/profile-tools-v3, ENGINES/legal_agent/3.0.0. 공통 코드를 분리해 재사용하되 서로 다른 정책을 v2 파일의 기본값에 몰래 덧씌우지 않는다.

| 변경 지점 | 책임·변경 | 소비자/설정/검증 |
|---|---|---|
| tools_protocol.py 및 v3 계약 모듈 | action 목적, 질문별 평가, relation assessment, draft/review 관계 의존성 | registry→모델 schema→validate→session까지 일치 |
| exploration_tools.py 및 공용 reference_cards(제안) | 순수 후보 발췌, 역할/정확 범위 보존, 수동·자동 참조 공용 조회 | node_card/search/locate/term_occurrences/lookup_definition/follow_reference; 같은 범위 같은 카드 |
| source_tools.py::_read | 검증된 target block 범위로 기존 READ 사용 | 새 별도 원문 리더 금지. exact/subtree/article 및 cursor 회귀 |
| tools_session.py 및 v3 세션 | 자동 작업 drain, evidence/relation 평가, view 패킹, claim별 gate | investigate/apply_turn/commit_draft/commit_review/answer_and_review |
| repository.py + v3 repository/DDL | READ와 자동 task 원자 commit, 버전 평가/의존성, 표시 영수증 | 과거 DB in-place migration 금지, 중복/동시성/중단 검사 |
| tools_policy.py 및 v3 정책 | 안내 템플릿·발췌/자동 읽기/예산 한도, 명시 모델 binding | 모든 설정 hash 고정, 모델 없이 숨은 생성 호출 없음 |
| legal_agent_adapter.py / pipeline.py / app.py / service.py | v3 선택·동일 session 진입점·검증 allowlist | 명시 후보 profile로 먼저 연결, 기본/활성 전환은 별도 |
| publication.py / coordinator.py | 버전별 opener, 관계 gate와 outbox, 단계 artifact 무효화 | COMMIT_READY 재게시/INTERRUPTED, 기존 Result 검증 |
| legal_agent_contracts.py / control.py / PIPELINE.json | v3 schema/엔진/정책/DDL 패키징·hash 고정 | 미등록 파일 누락, frozen release 덮어쓰기 검사 |
| app.py::home / genos_rag_chat.py::render | 기록 요약 실제 표시 | HTML escaping, 구 Result fallback, 미확인 관계 표시 |
| 새 trace command(제안) | 로컬 운영자 읽기 전용 이력 조회 | run 소유/경로/DB 버전/지문 검증, raw secrets 미노출 |
| CONTRACTS 테스트와 운영 문서 | 아래 시나리오/회귀/설정·복구 문서 | 모델 합성 응답을 실제 품질 실험과 구분 |

초기 단계에서는 원문 재수집·구조화·용어집 재검토 없이 현재 reference/occurrence/source 필드를 재사용한다. 선택 세대의 필드가 누락되면 capability/미해결 상태를 노출한다. 다중 대상 문장에서 역할을 정밀 분리하거나 reference 생성 정책을 바꾸면 **새 파생 색인 세대**가 필요하며 reference·lookup·RAG 소비자까지 재검증한다. 원문은 바뀌지 않는 한 재구축하지 않는다. journal v3는 새 요청에만 만들고 과거 릴리스·v2 journal은 그대로 보존한다.

## 9. 정상·실패 시나리오와 수용 검사

아래는 구현 후 수행할 합성 계약 검사 목록이며 이번 설계 작업에서 실행한 결과가 아니다.

| ID | 입력·분기 | 기대 저장·모델 입력·사용자 결과 |
|---|---|---|
| T-A | 검색 후보가 많고 실제 일치 span이 있음 | 후보 발췌/좌표/해시 표시 → 선택 이유 → READ → 기각 구절/이유 → 다음 view·화면까지 유지 |
| T-B | 명시 조항 질문 | 불필요한 목록 강제 없이 지목→READ. 잘못된 판본/동명 대상은 보류 |
| T-C | A가 B 특정 항을 준용, B 유일·허용 | A receipt→자동 notice→정확 B 선읽기→같은 성공 view에 원문/안내→관계 검토→A/B canonical 인용 |
| T-D | A에 ‘이 경우 …로 본다’가 뒤쪽 페이지에 있음 | 앞부분만 보고 준용 검토 완료 금지, 이어읽기 또는 bounded. 치환 문구와 B 비교 |
| T-E | A 한 문장에 B 인용·C 준용이 혼재 | frame 수준 역할은 HINT/AMBIGUOUS. 관계 타입을 대상별 확정하지 않음, 증거 있는 정정 기록 |
| T-F | A→B→A 또는 A→B→C | edge는 보존, 자동 중복·무한 재귀 없음. C 의존 결론이면 모델 추가 읽기 또는 보류 |
| T-G | target 복수/미해소/구판/권한 밖 | 임의 최신 파일 선택·scope 확장 금지, 제한된 notice와 미확인 사유. 제한 대상 원문/민감 메타데이터 미노출 |
| T-H | source의 다른 항만 READ / incoming 참조 | 현재 읽은 범위 밖 witness를 제시됐다고 세지 않음. incoming 방향 반전 금지 |
| T-I | 자동 선읽기 성공, 모델 입력에서 제외 | READ_STORED_NOT_PRESENTED, 채택·검토·citation 금지. 현재 wire 제시 후에만 변경 |
| T-J | 모델이 이유 없이 준용 무관 처리 / dependencies 누락 | schema/관련성 상태 검사와 reviewer 재검토. semantic 오판 가능성 별도 표시 |
| T-K | 단순 질문에 무관한 준용이 존재 | 출발 E 근거로 이유 있는 제외 가능. 불필요한 전 문서 읽기를 완료 조건으로 삼지 않음 |
| T-L | E가 Q 일부만 지지 / REJECT였다가 ADOPT로 수정 | 질문별 평가 공존, 과거 사유 보존, 영향 claim/review만 무효화 |
| T-M | 자동 작업 도중 오류·예산 소진·취소 | 앞선 READ 보존, 작업별 receipt 및 UNASSESSED_AT_STOP, 필요한 관계는 bounded |
| T-N | 동일 action 재전송 / 같은 args 다른 reason | 같은 id 동일 제안은 중복 소비 없음, 같은 id 다른 이유는 충돌, 새 id는 새 행동·I/O 재사용 구분 |
| T-O | READ commit 전후 crash / outbox 재게시 | E+자동 task 원자성, RUNNING interrupted, COMMIT_READY 고정 결과 재게시. 중단 후 모델 재호출 없음 |
| T-P | 관계 notice가 context/paging으로 밀림 | 생략·미완료를 명시, 독립 claim만 게시. 숨긴 relation을 근거로 READY 불가 |
| T-Q | 원문 발췌/사유에 HTML 또는 ‘지시 무시’ 문구 | 데이터 취급·화면 escaping, 원문을 정책 안내로 실행하지 않음 |
| T-R | 신/구 profile·journal·Result 혼합 | 버전별 엄격 선택, 구 화면 fallback, 현재 v2 계약 회귀·패키지/서비스 배선 검사 |
| T-S | INDEX에 relation 필드/좌표가 없거나 손상 | hash 오류는 차단, 단순 누락은 명시 capability/UNKNOWN. 참조 없음으로 단정 금지 |
| T-T | 참조 없는 문서 / use_llm=false 목록 | 근거 없는 관계 생성 없음, 목록은 모델·자동 전문 읽기 없이 기존 경로 유지 |
| T-U | 답변의 준용 설명과 시스템 관계 태그가 충돌 | 원문 기반 정정/반론, 관계 태그를 정답으로 강제하지 않음 |

각 검사는 반환 JSON뿐 아니라 실제 모델 wire, journal의 버전/영수증, 최종 Result, 로컬 화면과 GENOS render 텍스트까지 확인한다. mock/합성 응답 통과는 실제 모델이 준용을 정확히 해석한다는 증명이 아니다.

## 10. 기대치·비용·수치 원장

기대하는 변화는 이유 누락의 가시화, 읽기 전 판단 재료 회복, 준용 대상 확인 누락 감소다. 정확도 향상률·지연·가격 절감·구현 인일은 현재 실측이 없어 산정하지 않는다. 코드에 설정 가능한 상한을 처리량 예측으로 쓰지 않는다.

| ID | 지표·종류 | 단위/분모·근거·산식 | 결론/검증 |
|---|---|---|---|
| N01 | 자동 READ 깊이, 정책 목표 | 부모 모델 READ에서 시작하는 자동 edge 거리. 기본 1단계 | 비용·순환 제어용 선택, 최적값 주장 아님. T-F로 확인 |
| N02 | 상태 추적 누락, 계약 목표 | 저장된 READ마다 coverage/disposition/미평가 상태 존재. 누락 건수 목표 0 | 정답률 아님. T-I/L/M/O로 저장·표시 대조 |
| N03 | 권한 밖 READ·미제시 E 인용, 계약 목표 | 합성 경계 사례의 위반 건수 목표 0 | 운영 오류 확률 0을 의미하지 않음. T-G/I/Q 검사 |
| N04 | 순 증분 비용, 계산식 | ΔC=(Δ입력토큰×입력단가 + Δ출력토큰×출력단가)/단가의 토큰 기준량 + Δ도구/I/O비용 + Δ검토운영비용. 전 항목 요청당 같은 화폐 단위 | 단가·토큰·운영 측정 전 금액 미산정. Δ는 추가 발췌/선읽기/사유/재검토에서 줄어든 중복 탐색을 뺀 값 |
| N05 | 순 증분 지연, 미확인 | 동일 요청군의 수신→최종 게시 E2E 분포 차이. 평균에서 tail 지연 추정 금지 | 자동 I/O 증가와 모델 왕복 감소를 함께 측정 |
| N06 | 관계 처리 품질, 미확인 | 정답 근거가 독립 검토된 문항/문서군별 준용 누락·오적용·잘못된 제외·정답→오답 | 관계 태그와 모델 사유만으로 정답 라벨 생성 금지 |
| N07 | 구현 공수, 미산정 | 계약/adapter/상태·gate/화면/통합·문서/재작업의 작업별 실측 합 | 겹치는 테스트를 중복 합산하지 않음. 인일과 현장 배포 대기 별도 |

손익분기는 줄어든 탐색·반복 읽기·오류 복구 비용이 새 발췌·선읽기·판단/검토·저장 비용과 같을 때다. 준용 후보가 대부분 무관하거나 발췌로 잘못 보류하는 경우 비용과 품질 모두 악화할 수 있다. 자동 대상 한도를 높이면 최악 입력/I/O는 늘지만 필요한 대상의 실제 발견이 늘지는 미확인이다. 모호한 대상 비율·평균 원문 길이·반복 view 수·재검토율을 민감 변수로 측정한다.

실제 비교 실험이 승인되면 현재 v2를 기준으로 정확한 코드/자료/모델/예산을 고정하고, 발췌·관계 안내·자동 READ의 기여를 분리한다. 문항 의역을 독립 표본으로 부풀리지 않는다. 일반 탐색·준용·중첩/순환·무관 참조·치환·권한/판본·예외 사례를 포함하고 개발 사례와 새로운 holdout을 분리한다. 성능·회귀 허용치는 결과를 보기 전에 동결한다. 실험을 시작할 때 저장소 두 실험 표준을 끝까지 읽고 새 ADR을 선점한다. 이번에는 평가·모델 호출을 시작하지 않는다.

## 11. 구현 순서·도입·롤백

| 단계 | 산출물·종료 조건 | 선행·담당 책임 |
|---|---|---|
| A 계약 고정 | v3 action/preview/relation/assessment/journal/profile 및 오류 계약, 현재 v2 회귀 기준 | 런타임/계약 담당. 배포/모델 값은 확인된 설정만 사용 |
| B 후보·관계 어댑터 | 순수 발췌, v2 누락 역할/정확 범위 복원, 수동 follow_reference 동등성 | 색인/탐색 담당. 기존 필드 재사용 우선, 새 세대가 필요하면 명시 |
| C 기록과 자동 작업 | 원자 READ+task, 공유 예산·중복/순환·부분 성공·중단 기록 | 세션/저장 담당. 합성 경계 검사 후 다음 단계 |
| D 판단·검토 | 질문별 이유/수정 이력, 관계 dependency, 공동 원문 view, claim별 gate | 세션/품질 담당. 허위 READY 및 과잉 차단 반례 검사 |
| E 소비자·포장 | HTTP/ELS_QUERY/로컬 UI/GENOS render/trace/feedback 연결, v3 package 재현 | 서비스/화면 담당. ‘기록만 있고 표시 안 됨’ 방지 |
| F 도입 판단 | 별도 승인된 품질 실험과 현장 검증, 명시 모델 프로필/반입/실행·검증·복구 절차 | 운영/사용자. 코드 완료·MAIN 승격·GENOS 배포를 별도 보고 |

단계의 담당은 책임 구분이지 인력이 배정됐다는 뜻이 아니다. 이번 설계로 활성 포인터나 PIPELINE 기본값은 바꾸지 않는다. 향후 구현은 같은 Pipeline의 명시 v3 profile로 검증하고 기본 선택 변경은 검증·승격 상태와 구별한다. 패키징에는 코드 리비전·의존성·설정 이름·schema/profile hash·선택 세대·실행/검증/복구 안내를 포함한다.

롤백은 요청 drain 후 검증된 이전 릴리스/프로필을 명시 선택한다. 진행 중 v3 요청에 v2 코드를 주입하거나 v3 DB를 v2로 변환하지 않는다. 원문/색인을 새로 만들었다면 해당 이전 code+data 조합으로 함께 되돌리고 receipt를 남긴다. 이미 게시한 응답·평가·기각 이유·피드백은 삭제하지 않는다.

## 12. 자체 검토·미해결 사항·출처

검토 방식: 동일 작성자의 코드·계약 대조 및 문서 자체 검토. 독립 감독 검토·실제 성능 인증·배포 승인이 아니다.

| 발견 사항 | 설계 대응 | 남는 한계 |
|---|---|---|
| v2 참조 출력에 역할과 상세 block 범위가 빠짐 | 공용 어댑터로 복원, 수동·자동 경로 동등성 검사 | 원 색인의 역할 오분류·누락은 여전히 가능 |
| source_id 단위 참조 조회가 READ 범위 밖 문언도 포함 | span 검증과 witness 제시 상태 분리 | 불완전 색인은 재구축 또는 미확인 유지 |
| 현재 화면은 새 판단 metadata를 소비하지 않음 | 로컬 home·GENOS render 변경 포함 | GENOS 현장 표시·권한 검증 미실행 |
| 모든 READ 판단 강제 시 예산 소진·허위 기각 유도 | 미평가 종료 상태 보존, 관련 claim만 완료 차단 | 모델의 관련성 오판은 품질 검증 필요 |
| action receipt와 observation의 저장 경계 | 새 journal에서 원자 READ+task commit | 구현 후 crash injection 확인 필요 |
| 자동 선읽기가 무제한 참조 확장으로 바뀔 위험 | 깊이/공통 예산/방문 기록/미완료 표시 | 최적 페이지·원문량 설정은 측정 필요 |

이번 설계의 근거는 아래 로컬 원자료다. 외부 사례 수치나 법률 해석 결론은 사용하지 않았다. 링크는 이 저장소 접근 권한이 있어야 읽을 수 있다.

- [MAIN 책임·현재 연결](../../../../00_SYSTEM/ARCHITECTURE.md), [PIPELINE](../../../../00_SYSTEM/PIPELINE.json), [데이터 계약](../../../../00_SYSTEM/DATA_MODEL.md), [GENOS 제약](../../../../GENOS.md).
- [v2 프로토콜](../../../../02_BACKEND/semantic_runtime/legal_agent/tools_protocol.py), [도구 이유 공통 계약](../../../../02_BACKEND/semantic_runtime/legal_agent/protocol.py), [v2 정책](../../../../02_BACKEND/semantic_runtime/legal_agent/tools_policy.py).
- [도구·카드·READ·참조](../../../../02_BACKEND/semantic_runtime/legal_agent/exploration_tools.py), [기존 원문 리더·참조 출력](../../../../02_BACKEND/semantic_runtime/legal_agent/source_tools.py), [참조 생성·역할 판정](../../../../02_BACKEND/semantic_runtime/term_references.py).
- [현재 view·평가·검토·gate](../../../../02_BACKEND/semantic_runtime/legal_agent/tools_session.py), [공통 저장](../../../../02_BACKEND/semantic_runtime/legal_agent/repository.py), [제시 검증](../../../../02_BACKEND/semantic_runtime/legal_agent/tools_repository.py), [journal v2](../../../../02_BACKEND/semantic_runtime/legal_agent/journal-v2.sql), [게시·복구](../../../../02_BACKEND/semantic_runtime/legal_agent/publication.py).
- [과거 용어 주변 발췌](../../../../02_BACKEND/semantic_runtime/multi_entry_navigation.py), [과거 source-first 설계](../LEGAL_AGENT_SOURCE_FIRST_DOUBLE_HARNESS_20260920/DESIGN.md). 과거의 설계 목표·실험 관찰을 이번 기능의 운영 성능으로 인용하지 않는다.
- [서비스 진입](../../../../service.py), [세션 선택](../../../../02_BACKEND/semantic_runtime/legal_agent_adapter.py), [API·로컬 화면](../../../../02_BACKEND/semantic_runtime/app.py), [GENOS 채팅 소비자](../../../../08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py), [외부 Result 스키마](../../../../00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json).
- [계약 생성기](../../../../06_TOOLS/COMMANDS/legal_agent_contracts.py), [v2 계약 테스트](../../../../05_TESTS/CONTRACTS/test_tool_exploration_v2.py), [v2 운영 안내](../../OPERATIONS/TOOL_EXPLORATION_V2.md), [이전 구현 검증 기록](../../../../09_ARTIFACTS/AUDITS/20260921-tool-exploration-v2-wiring/README.md).

최종 확인: 추가 설계만 작성했다. 모델 호출·새 실험·자료 재구축·런타임 코드 수정·기본 선택 변경·활성 릴리스 전환·GENOS 배포는 수행하지 않았다.

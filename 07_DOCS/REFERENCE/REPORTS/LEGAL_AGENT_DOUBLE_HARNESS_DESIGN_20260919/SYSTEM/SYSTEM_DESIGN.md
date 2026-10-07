# Legal Agent 더블하네스 시스템 상세 설계

작성 기준: 2026-09-19. 상태: **구현 명세와 검증 가능한 설계 부속물**. 제품 실행기·MAIN·GENOS를 변경하지 않았다. SQL은 임시 SQLite에서, 메시지 예시는 JSON Schema로 검사한다. 이는 제품 연결·모델 품질 검증과 구분한다.

이 문서는 [최종 설계](../FINAL/FINAL_DESIGN.md)의 실행 명세다. 핵심 선택은 **기존 Pipeline 안에 요청별 LegalSession을 만들고, 모델은 변경안을 제출하며, WorkRepository가 검증·저장·무효화를 수행하는 방식**이다. 모델이 원문, 권한, 실행 상태를 직접 수정하지 않는다. 법적 조건을 정하는 DomainSpec과 실행 예산·모델을 정하는 AgentProfile을 각각 해시로 고정한다.

## 1. 구현 범위와 현행 연결부

아래 `제안` 이름은 아직 제품에 존재하지 않는다. 작업 코드의 선택 분기와 활성 릴리스는 별개이며, 새 profile은 후보 snapshot에서만 선택한다. 기존 증거와 실패 이력은 [설계 근거표](../FINAL/DESIGN_RATIONALE.md)에 보존했다.

| 현행 파일·진입점 | 확인한 제약 | 구현할 변경 | 소비자·호환성 |
|---|---|---|---|
| `semantic_runtime/app.py:create_app, ask` | 공유 Pipeline, 실행 뒤 `runs/<id>.json` 저장. run_id는 Pipeline 밖에서 생성 | run_id·release·runtime 위치를 실행 context로 전달. 후보 경로는 publication 완료 뒤 반환 | 기존 `/v1/rag/ask` 요청·응답 유지 |
| `semantic_runtime/pipeline.py:Pipeline.__init__, run` | `legal-rag` 고정, 단계당 한 번 실행, 출력 schema URI 고정 | 후보 `legal-agent-rag-v1` 선택, 기존 단계 실행 부분을 StageRunner로 추출, LegalCoordinator가 재진입 제어 | 기존 profile 경로 회귀 검사 |
| `semantic_runtime/stages.py:retrieve` | 호출할 때마다 `plan()`으로 query_id 생성 | 후보 stages는 session.context.query 재사용 | 같은 요청의 모든 회차가 같은 query_id |
| `semantic_runtime/contracts.py:Contracts` | hash 검증·`$id` registry는 존재, port별 검증 API 없음 | `schema_id_by_path` 캐시와 `validate_port(contract_id, value)` 추가 | 새로운 control 계약과 기존 runtime 계약을 함께 검증 |
| `00_SYSTEM/SCHEMAS/pipeline-v1.schema.json` | contract 속성은 schema_path/sha256/definition만 허용 | `schema_id` 속성을 추가하지 않고 schema 파일의 `$id`를 읽음 | 현행 pipeline-v1 유지. 이전 개요의 schema_id 추가안을 수정 |
| `semantic_runtime/provider.py:Haiku.call` | 출력 상한 고정, 전송·해석·검증 결합 | 신규 ModelGateway + 단일 전송 adapter. 기존 decoder와 receipt 형식 일부 재사용 | 기존 provider.call 소비자 유지, 후보만 새 경로 |
| `semantic_runtime/genos.py:request_json` | 내부 재시도, read timeout이 총 요청 시간과 다름 | gateway가 전송 횟수를 소유하고 transport는 재시도하지 않음 | 실제 모델·endpoint는 배포 binding에서만 선택 |
| `semantic_runtime/document_agent.py:resources` | 요청별 tools/glossary/fulltext 연결을 열고 닫음 | 같은 lifecycle을 SourceResources로 감싸서 이용 | 전역 mutable agent나 DB connection을 새로 공유하지 않음 |
| `semantic_runtime/folder_navigation.py` | catalogue/outline/read_unit/search_structure 존재. read_unit은 단일 조문 단위 제약 | 허용 scope 내 핸들 변환·하위 노드 페이지 읽기·정확 span 어댑터 추가 | 기존 탐색·색인을 활용 |
| `semantic_runtime/app.py:search, links, health` | `retrieve`, `get_index`, `config`에 직접 의존 | ServingLegalAgent가 이 인터페이스를 제공 | `/search`는 모델 없이 시작점 반환, links/status 유지 |
| `service.py` | 구현 선택 allowlist가 존재 | 후보 서버에 `legal-agent-v1` 분기 추가 | 명시적 세대·후보 계약 root 없으면 시작 거부 |
| `semantic_runtime/feedback.py` | 저장된 run을 읽어 proposal 작성 | 기존 피드백은 유지. 쟁점/span 단위 피드백은 별도 내부 확장 | 과거 답변 자동 정답 승격 금지 |

파일 기준 root는 `/home/jin/8-AGENT/02_BACKEND`다. 각 원본의 실제 경로·SHA-256은 [sources.json](sources.json)에 있다. 과거 완료 ADR snapshot은 수정 대상이 아니다.

## 2. 배치 구조와 요청 수명

새 서비스·외부 작업 큐를 먼저 만들지 않는다. 기존 FastAPI의 동기 `ask` worker에서 요청 하나를 수행한다. app 수준에서 공유하는 것은 검증된 manifest, 설정, 읽기 전용 catalogue와 admission semaphore다. 각 요청은 다음을 소유한다.

```text
POST /v1/rag/ask
  RequestContext: run_id, query_id, release, binding, allowed_document_ids, deadline
  LegalSession
    WorkRepository  -> 요청별 journal.sqlite
    SourceSession   -> 요청별 원문/색인/glossary 읽기 연결
    ModelGateway    -> view 작성, 예산 예약, 전송, schema 검사
    LegalCoordinator -> 기존 StageRunner 호출 및 재진입
  RunPublisher     -> 기존 runs/<run_id>.json
```

runtime은 문자열로 하드코딩하지 않고 `load_layout(repository_root).path("runtime")`에서 해결한다. `contracts_root`는 후보 코드·스키마 root이며, 실행 산출물 root와 분리한다.

```text
<runtime>/semantic/
  legal-agent/runs/<YYYYMMDD>/<run_id>/journal.sqlite
  legal-agent/runs/<YYYYMMDD>/<run_id>/owner.lock
  runs/<run_id>.json                 # 기존 UI·feedback 소비 파일
  feedback/                         # 기존 proposal 위치
```

run_id는 app이 만드는 기존 hex UUID다. source generation, source store hash, index/glossary hash, DomainSpec hash, AgentProfile hash, code/manifest hash, 실제 model ID와 adapter version을 `binding_json`에 기록하고 canonical JSON hash를 `binding_hash`로 둔다. 인증키는 binding·모델 요청 기록에 포함하지 않는다.

요청 시작 때 `Pipeline.plan()`을 한 번만 호출한다. 원문 범위는 여기서 고정한다. 문서 내부 탐색은 허용된 document IDs를 좁힐 수 있으나 넓힐 수 없다. 현재 API에는 사용자 인증 identity가 없으므로 이 scope를 사용자별 ACL이라고 부르지 않는다. 다중 사용자 권한을 도입할 경우 인증 principal의 권한과 요청 scope의 교집합을 별도 입력으로 결속해야 한다.

예시 admission 한도는 프로세스당 동시 요청 4개다. 초과하면 큐에 쌓지 않고 503을 반환한다. 이 값은 검증 전 가정이며 전체 서버 동시성은 worker 수와 곱해진다. 요청 안의 tool read는 초기 구현에서 순차 수행한다. 서로 다른 요청의 session·SQLite handle을 공유하지 않는다.

`with open_session(...):`가 종료되면 source 연결, gateway HTTP client/async runner, journal 연결을 닫고 semaphore를 반환한다. 불변 catalogue cache는 generation+hash 키로만 재사용한다. 예외 경로에도 동일하게 적용한다.

## 3. 파일과 책임

아래는 **후보 코드에 만들 예정인** 파일 배치다. 선언형 Python 인터페이스 원본은 [interfaces.py](interfaces.py)에 제공한다.

```text
02_BACKEND/semantic_runtime/
  legal_agent_adapter.py       ServingLegalAgent, 기존 API 호환
  legal_agent/
    context.py                 RequestContext, binding, 핸들 해소
    repository.py              WorkRepository, transaction, revision
    source_tools.py            SourceResources/SourceSession, scope/span
    domain.py                  DomainSpec loader, check dispatch
    views.py                   모델에 실제 제시할 view와 presentation
    gateway.py                 예산·재시도·출력 검증
    transport.py               GENOS 단일 전송 adapter
    investigator.py            explore/update 요청 루프
    packer.py                  finding 의존 근거로 context 조립
    composer.py                문장별 structured 초안
    reviewer.py                최신 claim 검토
    gate.py                    READY/BOUNDED/CLARIFY, control 계산
    coordinator.py             단계 재진입, 종료 조건
    stages.py                  기존 포트와 LegalSession 연결
    publication.py             최종 결과 outbox/export/복구
    errors.py                  typed errors
00_SYSTEM/SCHEMAS/legal-agent-v1.schema.json
00_SYSTEM/LEGAL_AGENT/domain-v1.json
00_SYSTEM/LEGAL_AGENT/profile-<binding>.json
```

역할을 파일로 분리하는 것이 항상 모델을 세 번 호출한다는 의미는 아니다. Investigator가 여러 번 움직여도 select/assemble은 코드로 처리한다. Composer와 Reviewer는 답변 초안을 확정할 때 호출한다. source-only 경로에는 모델 호출이 없다.

핵심 메서드 계약:

| 메서드 | 입력 | 반환·부작용 |
|---|---|---|
| `ServingLegalAgent.open_session(request, context)` | 검증된 요청과 고정 binding | 요청별 context manager |
| `WorkRepository.snapshot()` | 없음 | revision, 최신 entity heads, frontier |
| `WorkRepository.apply_proposal(view, proposal, event_id=...)` | 모델이 읽은 view와 변경안 | 원자적 변경, tmp→영구 ID, stale 목록 |
| `SourceSession.execute(action, context)` | 허용된 ToolAction | 구조화 observation. 임의 경로·SQL 금지 |
| `ModelGateway.generate(phase, view, schema_name)` | bounded view와 출력 계약 | 검증된 변경안. 자동 상태 반영 없음 |
| `ModelTransport.send_once(body=..., ticket=...)` | 한 번의 전송 티켓 | raw response/receipt/error. 재시도 없음 |
| `StageRunner.execute(node_id, values, legal_session=...)` | 현재 포트 값과 session | manifest의 출력 포트별 검증된 값 |
| `LegalSession.answer_and_review(assembled)` | 현재 assembly | 내부 candidate result와 control |
| `WorkRepository.prepare_publication(result, destination_key)` | 검증된 Result+기존 envelope | publication PENDING hash |

`interfaces.py`는 타입·책임 선언이며 이 메서드들의 구현 파일은 아니다. 복구 스캐너·RunPublisher 등 세부 helper도 아래 절의 계약에 따라 구현한다.

## 4. 저장 구조: 원문과 판단을 분리한다

[journal.sql](journal.sql)은 요청별 SQLite DDL이다. append-only 영역과 현재 상태 projection을 같은 DB transaction으로 갱신한다. 초기 schema version은 `PRAGMA user_version=1`이다. 구 journal을 새로운 DomainSpec으로 자동 변환하거나 과거 완료 run을 수정하지 않는다.

| 테이블 | 키·주요 데이터 | 변경 방식 |
|---|---|---|
| run | singleton, run_id, binding, phase, status, revisions | 요청 하나의 현재 상태 |
| event | seq, unique event_id, before/after revision, payload/hash | append-only |
| entity_version | kind/id/version, payload/hash, created_seq | 판단·쟁점·사실·claim의 불변 버전 |
| entity_head | kind/id → 최신 version, validity | CURRENT/STALE/CONTESTED/RETRACTED |
| dependency | dependent version → prerequisite version | 버전 의존 관계, append-only |
| evidence_unit | E ID, source/document/unit/generation/hash, role | 불변 원문 근거 단위 |
| evidence_span | E ID/ordinal → block/start/end/text/hash | 원문 정확 구간, append-only |
| evidence_dependency | entity version → E ID | 판단이 이용한 원문 |
| observation | tool/action/result/status/hash | 성공·실패·빈 결과 모두 기록 |
| observation_evidence | observation → E IDs | 발견/읽기 계보 |
| frontier | item/issue/action/dedupe/priority/status | 남은 탐색 경로 |
| model_view | view/base revision/evidence revision/body/hash | 전송 문맥 snapshot |
| presentation | view/E ID/delivered text hash | 해당 view에 들어간 원문 |
| model_attempt | logical call/attempt/view/request/response/usage/status | 실제 전송 시도별 기록 |
| budget | limit/reserved/tool_used/finalization reserve | SQL 상한 검사 |
| stage_artifact | stage/revision/dependency hash/payload/valid | 현재 단계 결과와 과거 결과 |
| publication | 최종 result/hash/destination/PENDING 또는 PUBLISHED | 결과 저장 outbox |

모든 JSON hash는 기존 `contracts.digest()`와 같은 canonical JSON 규칙을 사용한다. UTF-8, 키 정렬, 공백 없는 separator, NaN 금지다. SQL의 hash 길이 검사는 실제 hash 일치를 증명하지 않으며 repository가 재계산한다.

SQLite는 journal_mode DELETE, synchronous FULL, foreign_keys ON을 사용한다. DB마다 writer는 한 요청 owner다. immutable table의 update/delete는 trigger로 거부한다. 이 보호는 애플리케이션의 우발적 변경 방지이며 파일 시스템 관리자에 대한 변조 방지는 아니다. event payload와 entity hash를 같이 기록해 재현과 사후 확인에 이용한다.

배치 선행 조건은 lock·fsync·원자적 파일 생성이 검증된 durable POSIX 파일 시스템이다. GENOS 공유 마운트가 이를 지원한다고 가정하지 않는다. 현장 저장소가 조건을 충족하지 않으면 DB 저장소 선택을 다시 검토해야 하며, 이 설계만으로 장애 내구성을 인증하지 않는다.

### 4.1 서로 다른 세 가지 번호

- `event.seq`: 전송 예약·응답·도구·상태 이벤트마다 증가한다.
- `state_revision`: 쟁점·판단·관찰 결과·frontier 등 다음 모델 판단에 영향을 주는 상태를 바꿀 때 증가한다.
- `evidence_revision`: 채택 관계, finding 또는 정확 근거가 바뀌어 assembly를 다시 만들어야 할 때 증가한다.

모델 호출을 예약하거나 receipt를 저장했다고 state_revision을 올리지 않는다. 그렇지 않으면 revision 10을 읽은 모델의 응답이 호출 기록 때문에 revision 11에 도착한 것으로 처리되어 정상 변경안까지 stale로 거절된다. claim 자체는 별도의 entity version으로 식별한다. 리뷰는 `C1`이 아니라 `C1/version=2`에 결속한다.

## 5. 상태 변경 트랜잭션

모델 출력은 DB 명령이 아니다. repository는 다음 순서로 **변경안 전체를 원자적으로** 적용한다.

1. 출력 JSON Schema와 phase별 허용 op를 검사한다.
2. 요청 밖에서 source evidence·presentation·scope·expected version을 읽어 사전 검증한다. transaction 안에서도 revision을 다시 확인한다.
3. `BEGIN IMMEDIATE`; event_id 중복이면 이미 반영한 동일 hash 결과를 반환한다. 같은 ID의 다른 내용이면 충돌로 거부한다.
4. run이 RUNNING이고 binding과 `view.base_state_revision`이 현재 값인지 검사한다.
5. `tmp:i1`, `tmp:a1`, `tmp:f1` 등을 배치 안에서 먼저 영구 ID로 배정한다. 중복 tmp, 존재하지 않는 참조, 의존 순환을 거절한다.
6. 모든 op를 새 버전으로 변환한다. 영향을 받는 기존 dependency의 역방향 closure를 계산한다.
7. event, entity_version, dependency, evidence_dependency를 insert한다. entity_head와 frontier를 갱신하고 하위 artifact를 invalid 처리한다.
8. compare-and-swap으로 run revisions를 갱신한 뒤 COMMIT한다. 실패 시 전체 ROLLBACK이다.

```sql
UPDATE run
SET state_revision = :next_state,
    evidence_revision = :next_evidence,
    next_event_seq = :next_seq
WHERE singleton = 1 AND status = 'RUNNING'
  AND state_revision = :expected_state
  AND binding_hash = :expected_binding;
-- rowcount != 1이면 모든 변경을 rollback한다.
```

영향받는 entity version을 찾는 실제 SQLite 문장:

```sql
WITH RECURSIVE affected(kind, entity_id, version) AS (
  SELECT :kind, :entity_id, :version
  UNION
  SELECT d.dependent_kind, d.dependent_id, d.dependent_version
  FROM dependency d JOIN affected a
    ON d.prerequisite_kind = a.kind
   AND d.prerequisite_id = a.entity_id
   AND d.prerequisite_version = a.version
)
SELECT kind, entity_id, version FROM affected;
```

`UNION`으로 중복 방문을 제거한다. 신규 dependency는 애플리케이션에서 DAG 검사를 수행한다. SQL 자체가 다단계 순환을 거절해 주는 것은 아니다. closure 중 현재 head가 정확히 해당 version인 항목만 STALE로 바꾼다. 이미 새 버전으로 교체된 head를 과거 의존 경로로 다시 무효화하지 않는다.

예: A1(쟁점 I1에서 E1 채택) → F1 → C1 → R1. A1을 철회하면 F1/C1/R1은 STALE이다. 다른 쟁점 I2의 A2가 E1을 사용하면 A2와 그 하위 판단은 유지한다. 원문 E1도 유지한다. `adopted=true` 같은 전역 영구 상태를 두지 않는다.

`updates`와 `reads`가 같은 응답에 있으면 updates를 먼저 commit한다. reads는 그 뒤에 실행한다. 아직 실행하지 않은 read의 예상 결과를 같은 배치에서 채택하는 행위는 거부한다. 새 observation은 다음 view에서 판단한다. 이 구분이 탐색과 판단의 실제 경계를 만든다.

## 6. 더블하네스의 파일 계약

[domain.example.json](domain.example.json)은 DomainSpec 초안이다. 원문 정확 구간, 제시 후 채택, 범위 확대 금지, 시점 미확인 시 적용 단정 제한, 질문 coverage, claim별 검토 요구를 담는다. 법률 자체를 사전 ontology로 전부 모델링하는 파일이 아니다.

[profile.example.json](profile.example.json)은 AgentProfile 배선 예시다. 모델 binding, 호출/도구/시간 상한, schema repair, context 상한, 병렬성과 admission 한도를 담는다. `REQUIRED_FROM_DEPLOYMENT`는 명시적 placeholder이며 운영 profile loader는 이를 거절해야 한다. 배포 시 실제 provider/model ID를 고정한다.

둘의 실행 우선순위는 다음과 같다.

```text
source scope·generation 불변 조건
  -> DomainSpec의 증거·종료 조건
  -> AgentProfile의 실행 한도
  -> 모델이 제안한 다음 행동
```

예산이 끝나도 DomainSpec 검사를 생략하지 않는다. 근거를 확보하지 못했다면 BOUNDED/CLARIFY로 끝내거나 기술 실패를 반환한다. `READY`는 법적 정답 인증이 아니라 **현재 근거와 명시한 검사 조건을 통과한 상태**다.

Domain check dispatch는 고정된 `check_id → evaluator` 테이블이다. JSON 설정에 Python import 경로나 임의 실행식을 허용하지 않는다. citation membership·hash·revision·scope는 deterministic check, 조건 보존·법적 적용은 model_review다. 원문에 특정 단어가 없다는 이유만으로 예외가 없다고 증명하지 않는다.

## 7. 모델 입력·출력과 질문/사실 처리

프로토콜은 [protocol.schema.json](protocol.schema.json), 모의 메시지는 [protocol-examples.json](protocol-examples.json)에 있다. 구현 때 candidate schema URI를 정해 pipeline registry에 hash 고정한다. 현재 파일 URI는 설계용이며 배포 manifest가 아니다.

모델 view의 논리 형식:

```json
{
  "view_id": "V12",
  "phase": "investigate",
  "base_state_revision": 8,
  "evidence_revision": 3,
  "question_pieces": [{"id":"Q1","text":"모의 질문 원문"}],
  "issues": [{"id":"I1","version":2,"state":"OPEN"}],
  "current_findings": [],
  "frontier": [{"id":"T4","reason":"인용된 특례 조항 미열람"}],
  "evidence": [{"id":"E1","text":"모의 원문 정확 구간","text_hash":"..."}],
  "handles": {"S1":"허용 scope","D1":"허용 문서","U3":"저장된 조문"},
  "budget_remaining": {"model_attempts":6,"tool_actions":20},
  "output_schema_name": "InvestigateDecision"
}
```

위 JSON은 설명 예시라 hash를 생략했으며 production fixture로 사용하지 않는다. 실제 view는 canonical JSON으로 저장한다. 시스템 지시는 DomainSpec과 phase 지시문, 데이터 메시지는 질문·원문·관찰 결과로 분리한다. 원문 속 “지시를 무시하라” 같은 내용은 문서 데이터다.

질문은 원문을 보존한 Q 조각으로 나눈다. 초기 단순 구현은 전체 질문 Q1을 유지해도 된다. 쟁점은 모델이 생성하되 최소 하나의 Q ID에 결속한다. 새로운 source-triggered 쟁점도 관련 Q와 원문 E를 함께 가리킨다. 최초 version에는 사실을 추정해 채우지 않는다.

`attach_fact`는 stated/unknown을 구분한다. stated는 질문의 정확 `[start_cp,end_cp)`와 텍스트 일치를 서버가 확인한다. 이는 **사용자가 그렇게 진술했다**는 뜻이며 사실의 진실성 검증이 아니다. unknown은 누락된 사실의 이름을 보존하고 `question_span=null`이어야 한다. 연동된 issue의 fact_state는 이 관계들로 계산한다. 후속 사용자 답은 현재 v1에서 자동 resume하지 않고 새 요청으로 처리한다.

InvestigateDecision의 허용 변경은 create_issue, assess, retract_assessment, propose_finding, attach_fact, mark_unresolved, mark_not_applicable다. 스키마 외 의미 검증은 다음과 같다.

| 변경 | 추가 검사 |
|---|---|
| create_issue | question origin이면 Q 참조 필수. source_trigger이면 제시된 E 필수. required 쟁점을 모델이 몰래 삭제 불가 |
| assess | 현재 view 또는 같은 요청의 성공 응답 view에 실제 제시된 정확 E. 해당 issue와 연결 |
| retract_assessment | expected_version 일치. 근거와 이유 기록. 기존 채택도 철회 가능 |
| propose_finding | CURRENT assessment/fact만 참조. supports/qualifies 등이 하나도 없으면 근거 있는 finding으로 확정하지 않음 |
| attach_fact | stated 원문 span 검증, unknown은 추정값 금지 |
| mark_unresolved | 실제 observation 존재. ERROR와 NOT_FOUND 구분. 검색 실패를 규정 부재로 변환 금지 |
| mark_not_applicable | 근거 기반 제안으로 저장. required coverage에서 제외하려면 검토 대상이 되어야 함 |

NOT_APPLICABLE의 검토 누락 방지를 위해 repository는 해당 제안에 대한 검토용 claim을 만든다. 이 claim은 내부 coverage 검토 대상이며 검토 전 issue를 완료로 세지 않는다. 사용자 문장에 반영하면 일반 최종 claim과 동일하게 인용한다. 내부 검토 claim과 출력 claim은 claim payload의 purpose=coverage/answer로 용도를 관리하고, 둘 다 같은 claim version 검사 절차를 따른다.

핸들 S/D/U/E는 run/view에 결속한 매핑이다. 모델이 임의 document_id, 파일 경로, SQL, URL을 직접 실행시키지 않는다. tmp ID는 한 응답 배치 안에서만 유효하다. 영구 handle의 형식만 맞추는 것으로 존재·권한 검사를 통과할 수 없다.

## 8. 내부 탐색 도구의 구현

| ToolAction | 재사용 지점·새 adapter | 결과와 제약 |
|---|---|---|
| list_documents | `FolderNavigator.catalogue` | metadata D handles, scope 내부, content_read=false |
| list_structure | `FolderNavigator.outline` | U handles, parent/child, 페이지 cursor |
| read_node | `read_unit` + source_block 조회 adapter | leaf는 정확 원문. chapter는 leaf/page로 나눔. chunk마다 불변 E 생성 |
| search_text | 현행 fulltext/matcher | hit는 발견 observation. 읽지 않은 문장은 evidence 채택 금지 |
| search_subtree | `search_structure` | 명시된 저장 subtree 안에서만 검색. 전역 fallback 금지 |
| locate_provision | 명시 참조·좌표 resolver | resolved/multiple/unresolved 구분. 동명·모호한 조문 임의 결정 금지 |
| lookup_definition | glossary/matcher | 정의 후보와 정본 source 위치. 정의 원문은 별도 읽기 |
| follow_reference | navigation.sqlite 명시 reference/end | outgoing/incoming, 출처 연결. 누락 target은 unresolved |
| inspect_work | journal projection | 현재 쟁점·철회·누락·frontier 확인, 파일 시스템 탐색 아님 |

`cursor`는 서버 발급 불투명 토큰이다. 안에는 run/binding hash, operation hash, 범위, offset, page size를 결속한다. DB model_view 또는 observation에 cursor 매핑을 저장하여 프로세스 내부 사전만으로 계보를 잃지 않게 한다. 다른 질문·문서·scope에 cursor를 재사용하면 거부한다.

read budget은 모델이 요청한 ToolAction마다 차감한다. 내부 DB 쿼리 수와 혼동하지 않는다. wrapper는 `limit+1` 읽기로 has_more를 구하고 페이지 크기를 서버 상한으로 고정한다. 거대한 단일 block은 codepoint 구간으로 나누며 TRUNCATED와 next cursor를 반환한다. 본문을 조용히 잘라 완전한 조항처럼 제공하지 않는다.

명시적 read 응답 형식은 status, observation_id, request_key, items, evidence_ids, next_cursor, coverage, error_code를 포함한다. `coverage`는 읽은 문서·unit/span 범위다. 검색 0건은 그 요청과 범위에서 못 찾았다는 뜻이다. 문서 전체에 규정이 없다는 결론으로 승격하지 않는다.

정확 span 검증은 서버가 원본 `source_block.text[start_cp:end_cp] == span.text`를 확인한다. 좌표는 Python Unicode codepoint이며 byte offset이나 UTF-16 index와 섞지 않는다. 정규화 검색 결과의 offset을 원문 offset으로 그대로 쓰지 않는다. 정규화는 탐색용이고 읽기는 원문 위치를 재해소한다.

한 E에 복수 span을 넣을 수 있다. text hash는 ordinal 순서의 span.text를 `\n`으로 연결한 값이다. source artifact hash·block hash·span hash·generation을 같이 고정한다. 의미가 비슷하다는 이유로 합치지 않고 동일 좌표·hash의 정확 중복만 제거한다. source role은 저장 metadata에서 가져오며 모르는 경우 reference/temporal unknown으로 보수적으로 처리한다.

새 근거를 저장하는 것(materialized), 모델 view에 넣는 것(presented), 쟁점에 채택하는 것(adopted), 답변 context에 넣는 것(packed), 문장이 참조하는 것(cited)은 각기 다른 기록이다. presentation만 존재한다고 모델이 읽고 이해했다고 단정하지 않는다. 응답을 실제 받은 attempt의 view인지까지 검사해야 해당 모델 판단의 가시 근거로 인정한다.

## 9. 전송·예산·시간 제한

현재 `Haiku.call`을 그대로 반복 호출하면 전체 예산을 정확히 통제할 수 없다. 신규 gateway는 다음 순서를 소유한다.

```text
build view -> save view/presentation
  -> reserve_attempt transaction
  -> mark SENT
  -> transport.send_once(total deadline)
  -> persist raw response/receipt
  -> decode -> schema validate -> semantic proposal validate
  -> repository.apply_proposal
```

예약 transaction은 `model_reserved < model_limit`을 검사하고 +1한다. investigate는 `model_limit-finalization_reserve` 경계도 지킨다. PREPARED 뒤 프로세스가 죽으면 실제 전송 여부가 불명확하므로 예약을 임의 환불하지 않는다. model_reserved는 청구된 호출 수가 아닌 보수적 실행 상한 계수다. 실제 전송·usage는 attempt별로 별도 집계한다.

현행 `genos.request_json`은 `range(1, max_retries + 1)`로 실행하므로 **한 번만 보내려면 max_retries=1**이다. 0은 한 번도 시도하지 않는다. 최종 신규 adapter는 자체 재시도 없는 send_once를 제공한다. profile의 max_transport_retries=1은 최초 전송 외 한 번 더 허용한다는 뜻이며, 둘은 이름이 비슷해도 의미가 다르다.

재시도 가능한 오류는 응답을 얻지 못한 전송 실패·429·일시적 5xx다. 상태 반영 전이며 남은 시간·시도 상한이 있어야 한다. 4xx 설정/인증 오류는 같은 입력으로 재시도하지 않는다. unknown timeout 뒤 재전송하면 원격 모델은 중복 생성할 수 있으므로 attempt를 따로 기록하고 원격 청구가 한 번뿐이라고 보장하지 않는다.

HTTP body 자체가 JSON이 아니면 status·headers의 비밀 제외 subset·body_text·원시 bytes hash를 JSON envelope로 저장한 뒤 decode 오류를 낸다. body가 JSON인 경우에도 모델 content 해석 전에 raw response를 보존한다.

JSON 오류는 transport retry가 아니다. 원시 응답을 저장한 뒤 오류 경로와 요구 schema를 전달하는 제한된 repair 호출을 한다. repair도 물리 호출 예산에 포함한다. ID·권한·근거 오류는 임의로 올바른 ID를 추측하여 대체하지 않는다. stale response는 현재 상태에 적용하지 않고 IGNORED_LATE 또는 stale proposal 이벤트로 남긴다.

총 시간 상한은 monotonic deadline으로 계산한다. socket read timeout은 byte 수신 사이의 timeout이라 총 응답 시간 보장이 아니다. 동기 worker 안의 요청별 `asyncio.Runner`가 새 httpx AsyncClient 단일 전송을 구동하고 `asyncio.timeout(remaining_seconds)`로 전체 HTTP 작업을 제한하는 방식으로 구현한다. request 종료 뒤 남겨진 네트워크 worker thread에 의존하지 않는다. 로컬 취소가 원격 모델 생성을 취소한다는 보장은 없다.

DB/tool 단계도 SQL progress handler와 페이지 상한을 적용하고 deadline을 전후로 검사한다. HTTP timeout만으로 모든 파일 I/O의 hard real-time 종료를 보장하지 않는다. shutdown grace와 upstream HTTP timeout은 최종 요청 시간·저장 여유를 수용하도록 배포 시 함께 설정해야 한다.

모델 발견(`/models`)과 endpoint/모델 binding 검증은 app 시작·배포 확인 단계에서 수행하고 시작 영수증을 남긴다. 질문 실행 도중 몰래 모델을 바꾸거나 기본 Anthropic 경로로 fallback하지 않는다. 신규 외부 품질 실험을 하게 되면 저장소 Gemini 정책·ADR 선점 절차를 별도로 따른다. 이번 문서 작업에서는 모델 호출을 하지 않았다.

## 10. Coordinator와 단계 재실행

후보 profile의 단계 순서는 기존과 같은 retrieve → select → assemble → answer다. answer만 result 외에 control 포트를 추가한다. 제어 포트는 Coordinator가 소비하고 외부 Result에는 넣지 않는다.

```python
# 제안 의사코드: product code가 아님
values = {"$input.request": session.request}
while True:
    if must_research:
        execute_and_merge("retrieve", values, session)   # 같은 query, 기존 Work 보존
        execute_and_merge("select", values, session)
        execute_and_merge("assemble", values, session)
    execute_and_merge("answer", values, session)
    control = values["answer.control"]
    if control["decision"] == "FINAL":
        return values["answer.result"]
    if control["decision"] == "RESEARCH":
        session.work.invalidate_from("retrieve", reason=...)
        must_research = True
    else:  # RECOMPOSE
        assert assembly_dependency_hash_is_current()
        session.work.invalidate_from("answer", reason=...)
        must_research = False
```

`LegalSession.investigate()` 내부는 view → 모델 변경안 → commit → tool observations를 반복한다. DRAFT 요청, budget 경계, no-progress 조건 중 하나가 오면 retrieve 결과를 낸다. 모델의 intent는 제안이다. Coordinator/Gate가 종료 규칙을 확인한다.

select는 CURRENT finding에 연결된 유효 assessment의 E만 선택한다. 기존 candidate 카드의 전역 adopted flag를 상태 정본으로 사용하지 않는다. assemble은 exact span을 pack한다. answer는 compose → deterministic 검사 → claim별 review → gate다.

review가 새 조사 행동을 제안하면 challenge와 frontier를 저장하고 RESEARCH를 반환한다. 이때 answer.result 포트에는 계약을 만족하는 내부 candidate 결과를 넣되 `term_agent.final=false` 등 기존 open object 내부에 상태를 표시하고 외부에 게시하지 않는다. 후보 출력도 Result schema를 통과해야 한다. final publication은 control FINAL 때만 가능하다.

RECOMPOSE는 이미 읽어 pack한 동일 근거에서 누락 조건·문장 형식을 고치는 경우다. 새로운 원문이나 채택 관계 변경이 필요하면 RESEARCH다. 조립 근거 hash가 달라졌는데 RECOMPOSE로 넘어가는 것은 내부 계약 오류다.

`max_cycles`는 최초 answer pass를 포함한 answer/review 회차 상한이다. `max_no_progress`는 새로운 원문·판단 수정·쟁점 해결 없이 동일 의미 탐색을 반복한 연속 횟수다. UUID 생성이나 로그 추가를 progress로 세지 않는다. canonical action+scope+generation+관련 issue 상태를 dedupe key로 삼고, 같은 빈 검색을 반복하면 frontier를 EXHAUSTED로 둔다. 새로운 단서·범위 축소 등 operation 의미가 바뀌면 새 항목이다.

## 11. 답변 조립·검토·종료 조건

Composer는 free-form 최종 text 대신 `paragraphs[{text,finding_ids,evidence_ids}]`만 반환한다. 각 문장은 최소 하나의 유효 finding과 정확 E에 연결한다. 문장 일부만 인용한 뒤 다른 법률 주장을 숨길 수 있는 별도 자유 서술 필드를 두지 않는다. 그렇더라도 한 문장 내부의 과도한 주장은 모델 검토와 평가로 탐지해야 하며 JSON 형식만으로 의미 일치를 보장할 수 없다.

서버는 paragraph별 C handle과 version을 만든다. E 집합은 해당 finding의 근거 집합 안에 있어야 한다. packed/presented 근거 밖의 인용, STALE finding, scope 밖 원문은 reject한다. 잘못된 인용만 지우고 법률 문장을 남기지 않는다.

Reviewer 입력은 최신 claim 문장, 연결 finding, 정확 원문, fact_state, 적용 시점, 열린 challenge다. 출력은 claim_id+claim_version+verdict+reason_code+anchor E+follow_up_reads다. 처리 규칙:

| 결과 | 서버 처리 |
|---|---|
| SUPPORTED | 정확 version에 review 저장. deterministic 조건도 통과해야 최종 후보 |
| NEEDS_RESEARCH | 근거 있는 challenge 생성, bounded tool action을 frontier로 추가 |
| NEEDS_REWRITE | 원문이 이미 있으면 RECOMPOSE, 없으면 RESEARCH |
| UNCERTAIN | 미확인 상태를 보존. budget이 있으면 목적이 분명한 조사만 허용 |

claim이 바뀌면 과거 SUPPORTED는 새 version을 승인하지 않는다. 리뷰어도 같은 모델의 오류를 반복할 수 있다. 모델을 하나 더 붙였다는 사실만으로 독립 검증이라고 부르지 않는다.

Gate는 아래 순서로 계산한다. 모델이 직접 READY를 선언할 수 없다.

1. binding·scope·hash·span·revision·contract가 깨지면 기술 실패.
2. 모든 최종 claim에 CURRENT dependencies, pack 포함 근거, 현재 version review가 있는지 검사.
3. required issue가 EVIDENCE_LINKED, 검토된 NOT_APPLICABLE, 명시적인 unresolved 중 하나로 coverage되는지 확인. 숨겨진 OPEN 쟁점이 있으면 계속 조사하거나 한계를 표시.
4. 충돌·사실 누락·시점 미확인이 결론에 미치는 영향을 반영해 READY/BOUNDED/CLARIFY 선택.

BOUNDED는 **통과한 문장만** 내보내고 무엇을 확인하지 못했는지 서버 템플릿으로 덧붙인다. 실패한 핵심 결론을 약한 면책문과 함께 유지하지 않는다. CLARIFY는 필요한 사용자 사실을 구체적으로 요청하고 해당 사실을 전제로 단정하지 않는다. 근거가 없으면 claims=[]를 허용하며 “확인 가능한 근거가 부족합니다” 같은 비법률 결론 템플릿만 출력한다.

context packing은 원칙/조건/예외/상충 근거와 open challenge의 anchor를 함께 고려한다. 같은 source의 선택 구간은 겹치는 구간만 합치고 사이에 있는 미선택 본문을 bounding range로 끼워 넣지 않는다. character 상한을 넘으면 명시적으로 incomplete 처리한다. 필요한 예외를 조용히 자르지 않는다. 최종 전송 전 배포 binding의 model context token 한도와 실제 token 계산 결과를 확인한다. 문자 수만으로 token 적합성을 판정하지 않는다. 토큰 계산기가 없으면 배포에서 검증한 한도로 명시적으로 보수 제한하고 미확인 상태를 남긴다.

## 12. 기존 응답 계약에 매핑

외부 `term-runtime-v1` Request·Result는 유지한다. 새로운 내부 Work를 Result 최상위에 추가하면 closed schema를 위반한다. 제어와 상세 journal은 내부에 두고 현재 열려 있는 term_agent 메타데이터에 run 상태·revision·trace ID만 넣는다.

| 현재 필드 | 새로운 내부 원천 |
|---|---|
| request | 검증한 기존 Request. resume_id 등 추가 금지 |
| query | 요청 시작 시 한 번 만든 Query |
| retrieval.candidates | materialized evidence의 canonical source 후보. original metadata 유지 |
| retrieval.routes/vector_status/generation_id | 실제 탐색 경로·vector 사용 여부·고정 세대 |
| selection.selected/discarded_ids | 최신 assessment/finding 기준 후보 subset. method는 기존 const `term-agent` |
| assembly.context | 선택한 정확 원문 fragments. canonical source ID는 유지 |
| assembly.unresolved/data_status | 미확인 사유와 generation의 실제 data_status |
| answer.claims | 검토 통과 paragraph를 id/text/source_ids로 변환 |
| answer.text | 통과 paragraph와 서버가 작성한 확인 한계 템플릿 |
| answer.unresolved | reason 객체 배열. 판단 한계를 일반 로그에 숨기지 않음 |
| answer.provider_receipt | receipt id/hash, model binding, usage summary. 내부 파일 경로를 공개할 필요 없음 |

E handle은 내부 정밀 인용 단위이며 외부 source_ids는 기존 canonical source ID를 가리킨다. 동일 source에 여러 E가 있으면 context에 ordered evidence_spans를 유지한다. 기존 consumer가 추가 메타데이터를 무시해도 source_id 연결은 유지한다. `answer.source_store_sha256`·generation_id는 요청 binding에서만 채운다.

app이 기존에 덧붙이는 run_id/release는 Result 검증 이후의 envelope다. 새 publication은 envelope까지 포함한 값을 저장한다. RunPublisher 이전에 내부 Result를 검사하고 envelope 필드만 별도로 붙인다. response 전체를 Result schema에 다시 넣고 closed schema 오류를 내지 않는다.

`use_llm=false`이면 source-only 경로로 metadata 시작점을 반환하고 claims=[]를 쓴다. 모델을 사용하지 않았는데 법적 판단을 완료한 것처럼 READY를 표시하지 않는다. `/v1/rag/search` 역시 현행 metadata 경로를 제공한다. get_index/config 호환을 빼먹으면 links·health가 깨지므로 ask 이외의 endpoint도 연결 검증 대상이다.

## 13. Pipeline registry·manifest 배선

후보 registry에 `legal-agent-rag-v1` profile을 만들고 implementation=legal-agent-v1에만 매핑한다. 새 네 단계 engine entrypoint는 위 legal_agent/stages.py의 retrieve/select/assemble/answer다. retrieve/select/assemble은 현행 runtime.retrieved/selected/assembled 계약을 사용한다. answer는 기존 result와 신규 legal.control을 출력한다.

새 answer slot을 선언해야 한다. 기존 term-answer slot에 control을 몰래 추가하면 output port 검사와 slot 일치 검사를 위반한다. 후보의 slot/engine IDs는 기존 엔진과 구분한다. 구체 배선 표는 [wiring-plan.json](wiring-plan.json)에 있다. hash placeholder가 있는 배포 가능한 manifest로 위장하지 않고 blueprint로 표시했다.

`Contracts.validate_port`의 제안 구현:

```python
def validate_port(self, contract_id, value):
    c = self.pipeline["contracts"][contract_id]
    schema_id = self.schema_id_by_path[c["schema_path"]]
    return self.validate(value, schema_id, c.get("schema_definition"))
```

schema_id_by_path는 __init__의 기존 파일 hash 검사에 성공한 뒤 채운다. 중복 `$id`에 서로 다른 schema가 들어오거나 같은 path에 conflicting hash가 선언되면 시작을 거부한다. schema definition이 실제 존재하는지도 사전 검사한다.

StageRunner는 기존 manifest hash, manifest.files의 코드 hash, 입출력 key set을 모두 유지한다. 입력 ports도 현재 contract에 맞게 검증한다. `context={"runtime":pipeline,"legal_session":session}`로 요청별 session을 전달한다. 공유 Pipeline 속성에 `current_session`을 저장하지 않는다.

기존 observability의 `next(iter(result.values()))`는 answer에 두 포트가 생기면 잘못된 값을 읽을 수 있다. retrieve.retrieved/select.selected/assemble.assembled/answer.result를 명시적으로 선택한다. model request/receipt·source observation·revisions는 journal, 운영 로그는 ID·건수·지연·오류 코드 중심으로 구분한다.

구현 순서는 코드 → schema → engine manifest의 실제 SHA → registry hash → candidate freeze다. 이 문서 작성으로 운영 PIPELINE.json이나 활성 포인터는 바꾸지 않았다. 초기 단계는 기존 generation을 사용하므로 원문/용어집 재구축은 필수가 아니다. 원문 block 좌표가 없는 자료는 정확 span이 확보되기 전 legal evidence로 승격할 수 없으며 해당 데이터 ingestion 보완이 별도 선행 작업이다.

## 14. 최종 저장과 장애 복구

모델이 최종 문장을 만들었다고 요청이 완료된 것이 아니다. 기존 feedback이 읽을 최종 run 파일까지 일관되게 저장해야 한다.

1. 최종 Result와 binding/hash를 검증한다.
2. journal transaction에서 publication=PENDING과 최종 envelope JSON/hash를 넣고 run=COMMIT_READY로 바꾼다.
3. RunPublisher가 동일 파일 시스템의 임시 파일에 canonical bytes를 쓰고 fsync한다.
4. destination이 없을 때만 원자적으로 설치한다. POSIX에서는 fsync된 임시 파일의 hard-link 생성 등 no-clobber primitive를 사용하고 디렉터리도 fsync한다. 단순 `os.replace`만으로 기존 다른 내용 덮어쓰기 방지를 주장하지 않는다.
5. destination이 이미 있으면 hash가 같은 경우만 idempotent 성공이다. 다르면 PUBLICATION_CONFLICT로 멈춘다.
6. journal transaction에서 publication=PUBLISHED/run=COMPLETED로 바꾼 뒤 HTTP 응답을 반환한다.

| 중단 시점 | 재시작 후 처리 |
|---|---|
| COMMIT_READY 전 | 같은 owner가 사라진 RUNNING을 INTERRUPTED로 표시. 모델 추론 자동 재개 없음 |
| COMMIT_READY 후, export 전 | journal의 확정 JSON만 export. 모델 재호출 없음 |
| export 후, PUBLISHED 기록 전 | destination hash 비교 후 PUBLISHED로 마무리 |
| PUBLISHED 후 응답 전달 실패 | 저장 완료 유지. 클라이언트의 새 요청은 별도 run |
| DB 무결성/출처 hash 오류 | FAILED. 검증된 다른 요청 결과로 자동 대체하지 않음 |

startup 복구는 살아 있는 다른 worker의 RUNNING을 중단 처리하면 안 된다. per-run owner lock 파일의 프로세스 lock을 session 전체 동안 유지하고, recovery scanner는 nonblocking exclusive lock을 얻은 run만 처리한다. OS가 process exit 때 lock을 해제하게 한다. owner_boot_id는 감사용 식별자이며 그 값이 다르다는 이유만으로 owner 사망을 판정하지 않는다. deployment filesystem의 lock 지원은 선행 검증 대상이다.

v1은 질문 재전송 중복 제거 API를 새로 약속하지 않는다. HTTP idempotency key 또는 resume API는 요청 schema·principal·generation·turn 계약을 확장한 후 도입한다. 내부 event_id 중복 제거와 클라이언트 요청 중복 제거는 다른 문제다.

## 15. 오류와 사용자에게 보이는 결과

| 코드 | HTTP/내부 상태 | 처리 |
|---|---|---|
| INVALID_REQUEST | 422 | 질문·scope·문서 ID 오류. InputContractError로 분리 |
| ADMISSION_FULL | 503 | 시작 전 거절, 모델 호출 없음 |
| SOURCE_NOT_FOUND | tool NOT_FOUND | 미확인 observation. 대안 경로 또는 bounded 종료 |
| SCOPE_DENIED / STALE_CURSOR | tool DENIED | 범위 확장 없이 모델에 구조화 오류 전달 |
| STALE_PROPOSAL | 내부 reject | 최신 view에서 재판단. 기존 state 변경 없음 |
| PROVIDER_AUTH_OR_CONFIG | 502 | 같은 인증 설정으로 재시도하지 않음 |
| PROVIDER_TRANSIENT | retry 또는 502 | 예산·deadline 안에서만 재전송 |
| MODEL_OUTPUT_INVALID | repair 후 502 | 사용자 요청 422로 오분류하지 않음 |
| NO_LEGAL_EVIDENCE | 200 BOUNDED/CLARIFY | claims 비우고 확인 불가 사유 반환 |
| BUDGET_EXHAUSTED | 200 bounded 가능 | 이미 검토 통과한 부분만 반환. 안전한 결과를 만들 수 없으면 기술 실패 |
| DEADLINE_EXCEEDED | 504 | publication 전 종료. 기존 미검토 초안 반환 금지 |
| SOURCE_CHANGED / INTERNAL_CONTRACT | 500 | binding/내부 코드 계약 위반, 조사 중단 |
| PUBLICATION_CONFLICT / STORAGE_FAILURE | 500 | journal 상태 보존, 외부 완료로 보고하지 않음 |

현행 app의 ValueError/ValidationError 전역 handler는 모델 출력까지 422로 보낼 수 있다. 후보 경로는 typed exception으로 변환하고 내부 검증 오류를 그대로 이 handler에 흘리지 않는다. 응답에는 run_id·오류 코드·사용자가 이해할 설명을 제공하고 내부 trace·경로·인증 정보를 포함하지 않는다.

## 16. 실제 수정 흐름의 모의 추적

아래는 **모의 업무규정** 사례이며 실제 법률 결론·모델 실행 기록이 아니다.

| 순서 | 입력·행동 | 저장 변화 | 다음 단계 |
|---|---|---|---|
| A | Q1: “승인을 받아야 하나?” | I1=승인 필요 여부, 사실 조건 unknown | 문서 목록→목차 |
| B | read_node(U2): 일반 승인 원칙 | O1/E1 저장, V2에 E1 제시 | Investigator 판단 |
| C | assess E1 supports I1, propose F1 | A1v1/F1v1, dependency F1→A1 | select/assemble |
| D | Composer: “원칙상 승인이 필요” | C1v1→F1v1 | Reviewer |
| E | Reviewer: 원문에 인용된 특례 미확인 | R1/CH1, U3 read frontier | RESEARCH |
| F | U3 특례 원문 E2 읽기·제시 | O2/E2/V4 | 조건 재판단 |
| G | A1 철회·조건부 A3/F2 생성 | A1v2, F1/C1/R1 STALE. E1은 보존 | select/assemble 재실행 |
| H | “일반적으로 필요하나 특례 해당 여부 확인 필요” | C2v1, E1/E2, 현재 version review | BOUNDED 또는 CLARIFY |
| I | gate FINAL | publication PENDING→PUBLISHED | 기존 run JSON과 응답 |

모델이 여러 번 같은 잘못된 판단을 할 수 있다는 한계는 남는다. 이 구조가 제공하는 것은 새 근거를 탐색하고 이전 판단을 실제로 철회하여 답변까지 변경할 수 있는 실행 경로, 그리고 왜 멈췄는지 재현할 기록이다. 정답에 가까워지는지 여부는 별도 평가로 확인해야 한다.

## 17. 검증 계획·작업 순서

| 작업 | 산출물 | 종료 조건·담당 책임 |
|---|---|---|
| W1 계약/저장 | schema, repository, migrations | backend: CAS/원자성/불변 원문/의존 무효화 검사 |
| W2 단일 전송 | gateway/transport/receipt | model adapter 담당: timeout·재시도·usage·실제 ID 검증 |
| W3 원문 탐색 | scoped tools/정확 span/cursors | retrieval 담당: subtree 범위·페이지·긴 원문 회귀 |
| W4 세션/단계 연결 | stages/StageRunner/coordinator | backend: 같은 query_id, 재진입, 병렬 요청 격리 |
| W5 조립/검토/gate | paragraph claims, review, closure | backend+도메인 검토자: 조건·부정·예외·충돌 시나리오 |
| W6 API/저장 복구 | publisher/admission/errors/search/links | runtime 담당: 강제 중단·중복 export·consumer 호환 |
| W7 후보 검증/현장 인계 | freeze된 후보와 근거/rollback | ADR 소유자·GENOS 운영자: 별도 품질/현장 기준 충족 |

W1/W2/W3 뒤 W4, 이어 W5/W6 통합 순서다. 모델 품질 실험에 들어가기 전 현재 저장소 실험 정책에 따라 ADR을 선점하고 기준/후보/성공 기준을 동결한다. 이번 작성 중 W1~W6 제품 구현이나 W7 품질 실험을 실행한 것으로 처리하지 않는다.

필수 제품 연결 시나리오:

- 채택했던 근거 철회와 관련 없는 쟁점 보존.
- 긴 조문 뒤쪽 예외 정확 전달, 두 불연속 span의 중간 본문 비혼입.
- 존재하지만 모델에 제시하지 않은 E 채택 거부.
- 유효한 출처 ID로 부정/조건을 뒤집은 문장의 검토 실패.
- source generation·scope 변경, 다른 요청 cursor 재사용 거부.
- 같은 revision의 동시 proposal, 지연 응답, rollback 중간 실패.
- retry/repair 포함 physical attempts 상한, no-progress 종료, 종료용 budget 보존.
- RESEARCH 때 query 유지·artifact 재생성, RECOMPOSE 때 stale assembly 거부.
- API search/links/health/source-only/feedback와 기존 Result 호환.
- commit 전/후/export 후 강제 종료, 살아 있는 다른 worker를 복구 대상으로 오인하지 않음.

품질 비교는 같은 부모 코드·세대·질문 집합·출력 평가 조건을 고정한다. 독립 단위는 원 사례이며 의역 질문들을 독립 표본으로 부풀리지 않는다. 자동 형식 검사와 법적 정답 판정은 분리하고, 범위별 정답·조건 누락·근거 없는 결론·확인 요청 적절성·회귀·호출/토큰/지연을 함께 평가한다. 구체 수치 통과 기준은 평가 결과를 보기 전에 도메인 검토자와 ADR에 확정한다.

활성화는 Accepted·out-of-sample·decision_eligible·complete와 기존 MAIN 승격 절차가 충족된 후보에 한한다. 초기 rollout 중 실패하면 이전 릴리스 포인터로 되돌리고 신규 요청을 기존 구현으로 시작한다. 이미 진행 중인 journal을 다른 구현으로 이어 실행하지 않는다. 새 journal은 runtime 산출물이므로 source generation을 롤백할 때 삭제하지 않는다.

## 18. 자원·기대효과와 미확인 값

설정 숫자는 처리량·정확도 예측이 아니다. 예시 profile은 현행 상한 일부를 이행하면서 추가 종료 규칙을 둔 배선안이다.

| ID | 값·분류 | 단위/분모·근거 | 해석·검증 |
|---|---|---|---|
| N01 | 14, 가정 | 물리 모델 시도/요청. 현행 max_calls=14를 새 의미로 대응 | 실제 사용량 아님. 재시도를 포함하므로 이전 호출 계수와 직접 동치 아님 |
| N02 | 3, 가정 | 종료용 예약 시도/요청 | compose/review/repair 여유. 정답 생성 보장 아님 |
| N03 | 56, 가정 | ToolAction/요청. 기존 max_actions 참고 | DB query 수/원문 수와 다름 |
| N04 | 300, 가정 | 초/요청. 기존 wall_seconds 참고 | 종료 상한 설계. GENOS latency로 검증 필요 |
| N05 | 60000, 가정 | context 문자/전송. 기존 context_chars 참고 | 모델 토큰 한도와 다름. 실제 tokenizer/serving 한도 추가 검사 |
| N06 | 2800, 관측→가정 | 출력 token 상한/시도. 현행 provider 값 | 실제 소비 token 아님. JSON 잘림률에 따라 후보 조정 |
| N07 | 3/2/1/1, 가정 | answer cycles/no-progress/schema repairs/transport retries | 종료 정책 초기값. 프로토콜 반복검사로 검증 |
| N08 | 1/4, 가정 | 요청 내 read 병렬도/프로세스 admission | 실제 처리 용량 미확인 |
| N09 | 미산정 | 정답률 변화, p95, 비용, 인일 | 제품 연결·측정·작업 분해 후 산정. 관측 없는 일정 약속 없음 |

모델 비용은 `Σ[(input_tokens×input_rate + output_tokens×output_rate)/1,000,000]`로 집계하되 모델별 단가가 확인될 때만 화폐 비용을 계산한다. 내부 serving에 해당 단가가 없으면 token·GPU/서빙 시간 등 실제 얻을 수 있는 단위로 남긴다. usage가 없는 timeout을 0 token이라고 기록하지 않는다.

호출 수의 손익분기는 `재사용으로 줄인 호출 수 > 추가 검토+수정+재탐색 호출 수`일 때다. 비용 손익분기는 각 호출의 token·단가를 가중해 다시 계산해야 한다. source 탐색·journal·검토 인력 비용도 별도다. 검토로 품질이 나아져도 지연·비용은 증가할 수 있다. no-progress와 쟁점에 한정한 review의 효과 크기는 미확인이다.

주요 잔여 위험은 모델의 같은 오판 반복, 정본 좌표·시점 누락, tool의 구조적인 미탐색, 모델 문맥 초과, 로컬 취소 뒤 원격 생성 지속, 현장 파일 시스템 차이다. 구조적으로 막을 수 있는 원문/범위/revision 오류는 코드 검사로, 의미 품질과 운영 지연은 평가·현장 시험으로 검증한다.

## 19. 부속물 확인 방법

```bash
.venv/bin/python -B 07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/SYSTEM/validate_system_design.py
```

실행 위치는 `/home/jin/8-AGENT`다. 검사기는 in-memory SQLite와 합성 메시지만 사용한다. 출력은 stdout이며 제품 파일·모델·MAIN을 변경하지 않는다. [validation.json](validation.json)에 이번 실행 결과, [SELF_REVIEW.md](SELF_REVIEW.md)에 자체 검토와 미완료 경계를 남긴다.

개발 착수 기준은 이 문서의 계약과 실패 동작이다. “에이전트가 잘 판단하게 프롬프트를 수정”하는 작업만으로 완료 처리하지 않는다. 요청 세션, 원자적 상태 변경, 정확 원문 도구, 단일 전송 계수, 단계 재진입, 최종 저장 복구가 함께 연결되어야 한다.

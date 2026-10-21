# 업무 검토 지식 구현 기록 — 2026-10-21

작업 코드에 `lawrag/legal_knowledge` 패키지, `/legal-knowledge/` 관리 화면, `/v1/legal-knowledge` 인증 API, 기존 RAG 연결을 구현했다. **관리와 질문 소비 기본값은 각각 `false`, `off`다. 선택된 MAIN96·Oracle 업무 데이터·GENOS 배포는 변경하지 않았다.** 이 문서는 10월 20일 전체 설계의 모든 기능을 완료했다는 기록이 아니다.

## 구현한 범위

| 기능 | 실제 생산자와 소비자 |
|---|---|
| 공통 계약 | `contracts.py`: 입력 항목, 검토 방법, 업무 적용, Wiki/사건 참조, 원문 판본·위치·본문 hash. JSON Schema 5종을 `00_SYSTEM/SCHEMAS/legal-knowledge`에 등록 |
| 편집 | `application.Service.command(save_draft)` → 불변 revision과 CAS head. 이미 게시한 revision을 초안 저장으로 바꾸지 않음 |
| 게시 | prepare → 고정 build ID/hash → publish. 기존 게시 항목을 보존하며 명시한 revision을 갱신. 의존 대상의 revision은 자동 교체하지 않아 충돌 시 수정 대상이 드러남 |
| 중지·복원 | 채널 전체 retire, 검증한 과거 build로 rollback. 원문·권한·참조를 재검사하고 이전 채널 revision과 감사 receipt 보존 |
| 의견 | 정확한 지식 revision에 PROPOSED 피드백. 입력한 실행 ID는 사용자 신고 참조이며 실제 실행 검증 상태로 승격하지 않음 |
| 저장 | `adapters/oracle.py`: 명시 주입한 DB-API 연결, 승인 테이블 매핑, SERIALIZABLE·CLOB·bind·CAS. 서버가 Oracle 테이블을 자동 생성하거나 로컬 DB로 대체하지 않음 |
| 위키·사건 | `adapters/existing.py`, `wiki/`, `shortcut/`: 기존 저장소의 `current`/`investigation`과 기존 compiler callable에 위임. 본문·사건 사실·컴파일러 복제 없음 |
| 질문 해석 | `request_entry.py` → `knowledge_bridge.prepare/augment`. `consume`에서 기존 모델 입력에 검토 안내를 추가. 부모 entry proposal 경로는 추가 해석 호출 없음 |
| 조사 | `UnifiedRag.open`과 기존 `UnifiedExecution.invoke`에 안내·원문 위치를 합침. 현재 검색·원문 읽기·법률 판단·정확 일치 숏컷 검증 유지 |
| 상태·응답 | `research_state.KnowledgeReferences`가 기존 저널에 `LEGAL_KNOWLEDGE_BOUND` 이벤트를 기록. 답변의 `assembly.term_agent.legal_knowledge`에 사용 버전·미확인 전달. 재전송과 발행에서 현재 권한·철회·원문 결속 재검사 |
| 기존 CLI | `06_TOOLS/pipeline.py legal-knowledge validate/oracle-ddl/command/operation-status`. UI와 같은 서비스의 명령 처리 사용 |

원문·Wiki를 법률 정답으로 자동 승인하지 않는다. 시간·사실·범위가 없으면 미확인을 보존하고 검토 안내로만 제공한다. 조회 실패의 안내는 실제 원문 부재를 뜻하지 않는다.

## 관리 화면과 인증

실행 중인 같은 FastAPI 앱의 `/legal-knowledge/`에서 사용한다. 새 서버·에이전트·스케줄러는 없다. 모든 정적 화면·목록·상세·명령에 인증을 적용한다. `create_app(..., knowledge_identity=..., knowledge_factory=...)`의 호스트 어댑터 또는 인증 미들웨어의 `request.state.knowledge_principal`이 필요하다.

호스트 principal 계약:

```python
{
    "authenticated": True,
    "tenant_id": "<host tenant>",
    "team_id": "<host team>",
    "user_id": "<authenticated login>",
    "document_ids": ["<currently authorized version IDs>"],
    "knowledge_roles": ["read", "edit", "publish"],
}
```

이 값은 클라이언트 JSON이나 임의 헤더에서 신뢰하지 않는다. 로그인·SSO 자체를 새로 만들지 않았다. 기존 RAG의 `session_identity.bind()`가 만드는 `user_id`는 팀·세션 저장 키이므로 관리 로그인과 동일시하지 않는다. 팀·선택 문서 범위는 교차 검사하고 지식 조회는 인증된 관리 주체로 수행한다. Wiki·사건 등 기존 외부 참조가 포함된 지식과 그 의존 항목은 보수적으로 작성자 개인 범위를 유지한다.

`read`는 조회, `edit`는 초안·의견, `publish`는 준비·게시·중지·복원 권한이다. 변경 요청에는 `X-Knowledge-Request: 1`과 같은 Origin 검사를 적용한다. 화면은 저장소와 브라우저에 로그인 토큰·업무 데이터의 영속 캐시를 추가하지 않는다. POST 결과가 불명확하면 마지막 작업 ID로 상태를 확인한다.

기본 검토 방법은 이름·업무·검색 표현·확인 항목을 폼으로 편집한다. 입력/업무 적용/Wiki·사건 연결과 복잡한 조건은 현재 고급 JSON 편집이 필요하다. **비개발자용 참조 선택기·조건 편집기의 전체 완성은 남은 범위다.** 시스템 원문 세대·색인 hash는 `/status`로 받아 읽기 전용 표시한다.

## Oracle 연결과 CLI

`factory(connection_factory, table_map, reference_factory)`는 같은 `Service`를 생성한다. `reference_factory`는 승인된 기존 위키/사건·용어·원문 조회 포트를 제공한다. 새 스키마는 `lk_record`(불변 정의·게시·채널 이력·명령 receipt), `lk_head`(CAS head), `lk_lookup`(게시 시 만든 소규모 조회 색인) 세 논리 테이블이다. 기존 sw_* 원장은 옮기지 않았다. 신규 업무 정의를 저장하는 테이블이 기존 원문·색인 파일을 담는 구조가 아니다.

```python
from lawrag.legal_knowledge.adapters.oracle import factory

knowledge_factory = factory(
    connection_factory=approved_oracle_connection,
    table_map=approved_table_mapping,
    reference_factory=existing_authority_context,
)
# 기존 create_app 호출에 knowledge_factory와 검증된 identity_resolver 주입.
# PIPELINE.legal_knowledge.management_enabled=True로 관리 기능 선택.
```

호스트의 실제 인증·DB 연결·테이블 매핑은 현장 설정이므로 이 작업에서 임의로 추정하지 않았다. `service.py`와 Oracle 요청 팩터리가 기본으로 만드는 앱에는 이 두 주입 값이 없다. **설정 파일만 true로 바꾸면 사용 가능하다는 뜻이 아니다.** 승인된 호스트 조립부가 두 값을 연결한 새 코드 릴리스에서 사용해야 한다. 실제 GENOS 인증·Oracle 트랜잭션 검사는 미수행이다.

WSL 로컬 명령:

```bash
.venv/bin/python 06_TOOLS/pipeline.py legal-knowledge --help
.venv/bin/python 06_TOOLS/pipeline.py legal-knowledge validate --file <draft.json>
.venv/bin/python 06_TOOLS/pipeline.py legal-knowledge oracle-ddl --table-map <approved-map.json>
.venv/bin/python 06_TOOLS/pipeline.py legal-knowledge command --host approved_site.knowledge:context --file <command.json>
.venv/bin/python 06_TOOLS/pipeline.py legal-knowledge operation-status --host approved_site.knowledge:context --operation-id <same-operation-id>
```

`--host`는 설치된 운영 조립 함수이며 `(service_factory, authenticated_principal)`을 반환한다. 임의 웹 요청에 모듈명을 받지 않는다. DDL은 출력만 한다. 현장에서는 `python3`를 사용하며 ZIP·실행 TXT 반입본은 이번 범위에 포함하지 않았다.

## 실패·복구 계약

| 종류 | 담당·한도·결과 |
|---|---|
| 형식·참조·순환 | contracts/Service가 의미 추정 없이 거부. 알려진 필드 경로와 오류 코드, 초안 불변 유지 |
| revision·동시 편집 | Repository/Oracle가 CAS/직렬화로 거부. 자동 재시도 0회, 현재 head와 같은 operation ID 상태 확인 |
| 응답 유실·commit 결과 불명 | 동일 명령·receipt를 재조회. 동일 ID의 다른 입력 거부. 쓰기 자동 재전송 없음 |
| 게시 중 실패 | transaction rollback으로 이전 binding 유지. 처리된 실패는 별도 receipt에 기록. 저장소 장애에서 실패 기록 저장 성공을 주장하지 않음 |
| 권한·해시·철회 | 영향 지식 사용 거부. 모델 보정 없음. 새 조회는 기존 원문 조사로 복귀; 이미 그 지식을 사용한 저장 답변 재발행은 거부 |
| 지식 조회 지연·실패 | Oracle 어댑터 단독 담당, 자동 재시도 0회. 관리 작업 15초, 물리 SQL call 최대 1.5초. RAG 조회는 기존 deadline과 1.5초 중 작은 값으로 제한. 실패 안내를 같은 저널에 기록 |
| 재개·중복 | 질문/원문/주체/범위/모드 지문별 기존 저널 참조 재사용. 원래 RAG deadline·모델/도구 예산 변경 없음 |
| 외부 모델 | `public_scope`가 있는 외부 transport에는 업무 지식 전달 차단. 외부 모델 반출 승인을 가정하지 않음 |

조건은 all/any/not, 동등·집합·비교, 제한 산술과 ISO 날짜 비교를 지원한다. 단위·타입 불일치, 나눗셈 0, 반올림 정책 없는 부정확 산술은 UNKNOWN이다. CONFLICT와 원래 부족을 유지한다. 달력 정책·복합 차원 산술·표 lookup·역산은 아직 지원하지 않는다.

## 현재 소비 한계

- RAG에는 현재 검토 안내와 원문 위치를 제공한다. 도구의 직접 실행·조사 자동 생략·코드 계산 결과를 법률 결론으로 연결하지 않았다. 실제 원문 획득은 기존 조사 실행기 책임이다.
- 질문의 의미를 별도 코드로 업무·필드에 확정하지 않는다. 정확한 업무/시점/typed fact 연결이 없는 항목은 UNRESOLVED다. 자동 계획이 전부 실행된 것으로 보고하지 않는다.
- 기존 원문 읽기 중복 방지·내규를 먼저 읽는 대사 흐름은 유지한다. 새 지식 경로와 모든 기존 숏컷 사이의 추가 획득 병합은 구현하지 않았다.
- 영향 조회는 현재 게시 묶음의 직접 의존 항목이다. 전역/전이 영향 탐색, 실제 실행 역색인, 자동 개선 후보 생성·검토 큐는 남았다.
- Wiki 본문 편집·새 모델 컴파일 작업을 이 API에서 실행하지 않는다. 기존 컴파일러를 호출하는 어댑터만 제공하며 기존 구축 명령이 소유한다. sw_* 전체 Oracle 이행은 미수행이다.
- `off`는 조회도 하지 않음, `observe`는 계획을 기록하되 모델 입력 불변, `consume`은 기존 해석·조사 호출에 안내를 추가한다. 속도·비용·품질 효과 비교는 아직 수행하지 않았다. 실모델 비교와 MAIN 승격은 새 ADR 동결 절차가 필요하다.

## 검사와 선택 상태

검사는 작은 합성 원문과 저장 fixture로 순차 실행했다. 테스트에서만 SQLite를 사용했다. 모의 Oracle DB-API 검사와 실제 Oracle 서버 검증은 구분한다. 실제 앱의 off/observe/consume → 조사 → 정확 원문 → 답변 메타데이터 → 저널 → 중복 응답 → 철회 후 재전송 거부를 검사했다. 로컬 Chromium에서 실제 관리 router를 호출해 편집·게시·의견·문자열 이스케이프·모바일 폭을 확인했다.

최종 검사 수·메모리·해시 목록은 [감사 결과](../../../../09_ARTIFACTS/AUDITS/20261021-legal-knowledge/RESULT.json), [검사 로그](../../../../09_ARTIFACTS/AUDITS/20261021-legal-knowledge/tests-final.txt), [브라우저 검사](../../../../09_ARTIFACTS/AUDITS/20261021-legal-knowledge/BROWSER_CHECK.json)를 따른다. 실제 모델 호출 0회, 선택 MAIN96 포인터 불변, Git commit/merge/push·GENOS 반입·배포 미수행이다.

관리/소비를 끄면 기존 RAG 경로로 돌아간다. 코드 복원은 이번 작업 직전 파일별 preimage와 신규 파일 목록을 사용하며, 이후 수정 유무를 해시로 확인해야 한다. 전체 후보·이전 Git 상태를 작업 트리에 덮어쓰지 않는다. Oracle 채널 복원은 `rollback`으로 새 revision을 기록하고 과거 실패·게시 이력을 보존한다.

## 후속 실제 E2E

사용자의 보유 데이터·질문 실행 요청으로 [E2E 실행기와 화면](E2E_20261021.md)을 추가했다. ADR0958의 첫 실패와 ADR0959 후속 실행을 구분하여 보존했다. 고정한 공개 질문3개와 실제 원문28문서에서 게시→기존 RAG 입력→답변→지식 버전→중복 요청을 실행하며, 정확한 결과·제한 답변·공급자 실패는 후속 기록을 따른다. 공개 지식 해시를 명시적으로 허용하는 외부 모델 연결은 동결한 연구 후보에만 있다. 위의 작업 코드 기본값 off, MAIN96 선택, 운영 Oracle·GENOS 상태는 유지된다.

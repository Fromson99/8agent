# legal_agent 통합 실행·경험·위키 — 작업 코드 v6

## 조사 한도 설정 (2026-10-07)

루트 `service.py`와 같은 모듈을 쓰는 `service.service`의 서비스 시작 설정이다.
v5/v6의 선택 프로필을 검증한 뒤 복사본에 적용하고, 같은 값을 실제 native journal과
요청 deadline에 전달한다. 로컬 frozen MAIN의 파일·해시와 활성 포인터는 유지한다.
GENOS 코드서빙에서는 이 서비스 변경이 반입·배포된 뒤 환경 설정에 등록해야 한다.

| 환경 설정 | 현재 로컬 v6 기본값 | 적용 범위 |
|---|---:|---|
| `GENOS_RAG_MAX_MODEL_ATTEMPTS` | 40 | 수정·재시도·최종 판단을 포함하는 물리 모델 시도 총량 |
| `GENOS_RAG_MAX_TOOL_ACTIONS` | 1024 | 공통 원장의 도구 시도 총량 |
| `GENOS_RAG_WALL_SECONDS` | 1800 | 요청 전체 시간, 초 |
| `GENOS_RAG_SEARCH_ROUNDS` | 8 | 법령 탐색의 추가 검색 질문 이력 한도 |
| `GENOS_RAG_ASSESSMENT_REENTRY_LIMIT` | 2 | 최종 판단에서 부족한 근거 때문에 SELECT로 재진입하는 횟수 |

모델 총량 40회 중 `finalization_reserve=3`을 남겨 조사 단계의 상한은 37회다.
INTENT·PLAN과 조사 중 수정·재시도도 이 조사 예산을 소비하며, 37회가 전부 검색 호출은 아니다.
모델 총량은 이 예약보다 커야 하고 도구 총량은 기존 `tool_finalization_reserve=4`보다 커야 한다.
재진입 횟수만 0을 허용한다. 다른 값은 양의 정수이며 빈 설정은 기존 프로필 값을 유지한다.
GENOS의 기존 기본 대기시간 1800초 보정도 유지한다. 진전 없는 반복 한도 2회는 기존 정책이다.

서비스 프로세스를 재시작하면 새 요청부터 적용한다. 같은 미완료 요청의 재개는 기존
예산·마감·실행 지문을 보존하므로 설정을 바꿔 이미 소비한 예산을 초기화할 수 없다.
요청 JSON에서는 이 환경 설정을 변경할 수 없다. 예시는 [.env.genos.example](../../../.env.genos.example)이다.
로컬 명령의 환경 변수로도 동일하게 적용하며, `.env.genos.example` 자체는 자동 로드하지 않는다.
직접 `create_app`을 쓰는 호스트는 기존 `legal_agent_profile` 인자로 설정한다.

`HEALTH` 응답과 `PING`의 로드된 `binding`에서 `investigation_budget`을 확인한다.
`effective_profile_sha256`은 적용 후 전체 프로필, `service_entry_sha256`은 실제 서비스 입구의
지문이다. 선택 릴리스의 `profile_sha256`과 구분하며 `runtime.investigation_budget`에도 기록한다.
GENOS 현장 적용값과 모델 답변 품질·성능은 별도 현장 확인이 필요하다.

아래는 2026-10-02 구현 시점의 기록이다.

2026-10-02. 구현 및 WSL 모의 계약 검증. 활성 MAIN·원문 generation·GENOS 리비전 전환 전.

**legal_agent는 유지한다.** `ServingLegalAgent`가 모델, admission lease, deadline,
WorkRepository, 원문 도구를 소유한다. 새 `legal-agent-unified-v6`를 명시적으로 선택하면
일반 법률 질문과 멀티턴 요청이 같은 Pipeline → Coordinator → legal_agent 실행을 사용한다.
`memory=true`는 호환 입력이며 v6에서 별도 실행기를 선택하지 않는다.

## 실행과 정본

```text
/v1/rag/ask → Pipeline.run → coordinator.run_case
  → CaseRepository: 현재 질문·정정·조건과 두 위키의 공통 경험 조회
  → 하나의 RuntimeModel / BoundedSourceSession / native journal-v6
  → INTENT → PLAN → RECALL → READ → SELECT → ASSESS → COMPOSE
  → 현재 revision 검사·경로 수락 → 기존 publication.prepare/export
  → 명시적 최종 확인 → 경험 확정 outbox → user_wiki / legal_wiki
  → 다음 대화: 같은 KnowledgeRepository에서 조건 비교·근거 재결속
```

- 기존 v5 원문 구조 탐색, SourceRecall, 정확 READ, 원문 선별, 모델 gateway를 사용한다.
  v6의 법률 질문은 Coordinator의 일곱 체크포인트로 진행한다. 선언된 네 엔진은 코드·포트
  검증과 기존 인사·목록·모델 미사용 경로를 유지한다. 법률 질문을 네 개의 선형 엔진으로
  실행했다고 보고하지 않는다.
- `session_id`를 case ID로, 기존 goal ID를 question ID로 사용한다. 정정은 같은 question의
  새 revision이다. 새 대화의 재사용은 새 question ID와 원래 experience ID를 연결한다.
- 각 판단은 `(run_id, kind, entity_id, version, payload_hash, choice_id)`로 참조한다.
  원문을 다시 검증·결속하고 과거 실행의 로컬 evidence 별칭을 현재 별칭으로 바꾼다.
- `runtime/case-memory/cases-v3.sqlite`가 사건·현재 경로·최종 경험·outbox의 정본이다.
  `runtime/legal-agent/runs/.../journal.sqlite` v6는 실제 모델 입출력·예산·원문·판단의 정본이다.
  두 DB의 갱신을 하나의 원자적 트랜잭션이라고 부르지 않는다.
- `runtime/case-memory/wikis/<주체 해시>/{user_wiki,legal_wiki}/index.json,index.md`는
  재생 가능한 파생본이다. 온라인 조회는 이 파일을 정답으로 읽지 않고 동일한 DB를 조회한다.
- 응답은 기존 `term-runtime-v1`의 query/answer/assembly를 보존하고 run ID, question ID,
  revision, experience ID, 실행 단계 정보를 envelope에 추가한다. 피드백은 같은 run/answer ID를 사용한다.
- 진행 표시는 같은 native journal의 수락 단계/해시·선택 원문과 실제 모델 대기를 읽는다.
  정정의 재실행과 확정 경험의 재결속을 구분하며 기존 GENOS 누적 Reasoner 노드/JSON 문자열
  형식을 유지한다. [진행 표시·편집기 반영·현장 확인](GENOS_CHAT_WORKFLOW.md).
- [공통 참조 계약](../../../00_SYSTEM/SCHEMAS/unified-case-memory-v1.schema.json),
  [native v6](../../../02_BACKEND/semantic_runtime/legal_agent/journal-v6.sql),
  [사건 정본](../../../02_BACKEND/semantic_runtime/legal_agent/case_repository.py).

## 일반 질문과 후속 요청

호스트에서 `create_app(..., implementation='legal-agent-unified-v6',
legal_agent_profile=<명시적 모델 프로필>, legal_agent_transport=<기존 transport>)`를 선택한다.
프로필은 bounded source selection을 사용해야 한다. 초기 v6의 요청당 모델 시도 상한은 40이다.
기존 v5의 14보다 커진 **정책 상한**이며 실제 호출 수·비용·지연을 측정한 값이 아니다.

일반 단일 질문은 `/v1/rag/ask`의 기존 question/document_ids/use_llm 입력으로 실행할 수 있다.
개인 이력과 후속 정정을 사용하려면 같은 API에 신뢰된 session_id/request_id와 사용자 신원을
전달한다. API body의 user_id와 team_id만으로 권한을 부여하지 않는다.

```json
{
  "question": "모의 질문",
  "session_id": "신뢰된 대화 ID",
  "request_id": "이번 논리 요청 ID",
  "user_id": "호스트가 확인한 사용자 ID",
  "team_id": "신뢰된 팀",
  "memory_authorization": {"issued_at": 0, "signature": "호스트 서명"}
}
```

위 서명은 예시이며 실제 유효 서명이 아니다. GENOS workflow의 기존 서명 어댑터 또는
호스트의 `memory_identity` 어댑터가 신원과 허용 문서를 확인한다. 팀별 문서 선택과 ACL은
별개다. 신원이 없는 일반 질문은 개인 기억을 조회하지 않는 임시 사건을 만든다.
HMAC/인증키는 원장·모델 입력·요청 fingerprint에서 제외한다. 외부 모델에는 현재 공개 동의와
허용 원문 범위만 적용하며, 비공개 이력이 있는 세션의 외부 전송을 거부한다.

정정·재정정·복원·표 변환·최종 확인은 question 자연어로 요청한다. 서버가 제공된 대상·방법
ID와 저장한 원이벤트를 검사한다. 원문 범위가 바뀌면 PLAN부터, 사실만 바뀌면 ASSESS부터,
표현만 바뀌면 COMPOSE부터 실행한다. 부족한 원문을 요구한 선별은 RECALL/READ로 돌아간다.
조건이 다른 경험의 재사용 요청은 새 조사를 실행한다. 잘못된 경험 연결의 수정도 현재 판단을
재검토하며, 원래 다른 질문의 경험을 수정하지 않는다.

## 기억과 두 위키 조회

`POST /v1/rag/memory/query`도 같은 신원 어댑터를 사용한다. 온라인 조회는 모델을 호출하지 않는다.

| query_kind | 추가 입력 | 결과 |
|---|---|---|
| `experience` | `experience_id` | 정확한 ID의 현재 확정 경험·조건·판단 refs·원문 refs |
| `user_wiki` | `question`(선택), `after`, `limit` | 사용자 관점의 확정 경험과 질문 이력 색인 |
| `legal_wiki` | `question`(선택), `after`, `limit` | 같은 경험을 개념 관찰·근거 관점으로 조회 |
| `questions` | `question`(선택), `after`, `limit` | 다른 대화의 미확정 질문도 포함하는 개인 질문 색인 |
| `history` | `question_id`, 정수 `after`, `limit` | 실제 원장 이벤트 페이지 |

두 위키의 experience ID/revision/hash/judgment refs는 같다. 검색 후보의 32개 한도는
정확한 ID의 존재·권한 판정에 사용하지 않는다. 질문·이벤트는 최대 100개씩 페이지 조회한다.
모델의 긴 이력 입력에는 최초 이벤트, 최근 이벤트, 명시한 정정 순번을 제공하고 부분 조회임을
표시한다. 임의의 장문 전체를 항상 모델에 넣거나 모든 과거 내용을 의미 검색한다고 주장하지 않는다.

## 온톨로지 통제의 실제 범위

[초기 catalogue](../../../00_SYSTEM/LEGAL_AGENT/domain-catalogue-v1.json)는 질문·원문·판단과
근거/적용 관계, 일곱 단계의 조사 방법을 닫힌 ID로 제공한다. 모델 선택을 실행 전에 검사·저장하며
판단 ref가 그 선택을 가리킨다. 미제공 ID, 관계의 잘못된 출발/도착 개념, 미제공 방법은 거절한다.
선택·인용·성공한 실제 모델 제시 영수증도 게시 전에 확인한다.

초기 catalogue의 법률 개념 커버리지는 `DISCOVERY_UNTIL_REVIEWED_IMPORT`다. 자동으로 추출한
개념명은 `CONCEPT_OBSERVATION / DISCOVERY`이며 공통 법률 온톨로지의 승인 개념이 아니다.
검토된 개념·관계를 입력하려면 ACCEPTED review receipt, 검토자, 원문 generation/hash,
근거 refs를 제공해야 한다. 다른 generation의 검토 항목은 이번 offer에서 제외한다.
컴파일은 이 입력의 구조·결속을 확인하며 법적 의미 정확도나 검토자의 권한을 인증하지 않는다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary domain-control verify --source <catalogue.json>
.venv/bin/python 06_TOOLS/pipeline.py glossary domain-control compile --source <reviewed.json> --output <새 catalogue.json>
```

컴파일만으로 선택된 catalogue를 변경하지 않는다. 새 파일의 해시를 통합 프로필에 명시하고
계약을 재패키징한다. catalogue/method/profile/code/source binding 변경은 기존 경험의 재사용을 막는다.

## 저장·중단·재시도·이관·복구

2026-10-02 사용자 사진의 공유 폴더에 맞춘 v6 반입 R1은
`GENOS_RUNTIME_DIR=/nfs-root/diamo/8-agent/runtime`을 코드서빙 환경에 설정한다.
`GENOS_MEMORY_JOURNAL_MODE=DELETE`와 `synchronous=FULL`을 사용하며
`/nfs-root`의 경험 DB에 WAL을 요청하면 시작 전에 거절한다. 로컬 기본은 WAL이다.
GENOS 내부 모델 환경 결속은 v6 프로필의 40회 시도 상한을 보존한다.
기존 runtime은 삭제하거나 자동 합치지 않으며 원문 세대 선택은 유지한다.
[반입·실행·잠금 점검·원복](../../../08_DEPLOYMENT/GENOS/handoffs/unified_v6_nfs_20261002_r1/GUIDE_UTF8.txt).
동일 호스트의 작은 DB/owner lock 검사는 여러 NFS 호스트의 잠금 인증이 아니다.
현장 확인 전 단일 서빙 인스턴스/worker를 사용하며 이전·새 리비전의 동시 쓰기를 피한다.
실제 현장 쓰기·답변·재사용 성공은 미확인이다.

- 정정 시작 시 기존 경로와 경험을 재사용에서 제외한다. 실패하면 PENDING을 유지한다.
  재사용 판단에 실제 의존한 후속 질문도 PENDING으로 전환한다. 독립 조사한 질문은 유지한다.
- 같은 주체·세션·request ID의 같은 입력은 완료 응답을 재검사해 반환한다. 다른 입력은 409다.
  실패한 같은 요청은 기록된 미완료 체크포인트부터 재시도하며 정정을 다시 적용하지 않는다.
  경험의 판단을 새 사건에 재결속하는 도중 실패한 경우도 마지막 저장 단계 뒤부터 재개한다.
  이 재결속의 모델 호출 동안 사건 DB 쓰기 트랜잭션을 유지하지 않는다.
- 세션 owner lock, 단계 저장 직전 revision 검사, 게시 직전 current route/원문/주체/ref 검사를 둔다.
  늦은 실행은 최신 상태를 덮어쓰지 못한다. 이전 revision의 요청 재전송도 최신 답으로 반환하지 않는다.
- native case_commit이 없는 v6 응답은 복구/게시할 수 없다. 준비된 응답은 기존 publication recovery로
  같은 결과를 발행한다. owner를 잃은 RUNNING 요청은 재시도 가능한 FAILED로 남긴다.
- 위키 생성이 실패해도 확정 경험·outbox는 보존된다. 온라인 두 위키는 정본으로 즉시 조회하고,
  같은 최종 확인 재전송 또는 명시적 재생성으로 파생 파일을 복구한다.
- 이는 WSL 단일 호스트/POSIX owner lock 검증이다. NFS·다중 서빙 인스턴스의 SQLite 쓰기·잠금
  신뢰성은 현장 검증 전이며 지원 완료로 간주하지 않는다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py unified-memory status
.venv/bin/python 06_TOOLS/pipeline.py unified-memory migrate --source <기존 memory-v2.sqlite> --runtime <선택 runtime>
.venv/bin/python 06_TOOLS/pipeline.py unified-memory migrate --legacy-kind action-memory --source <기존 action-memory.sqlite> --runtime <선택 runtime>
.venv/bin/python 06_TOOLS/pipeline.py unified-memory wiki-rebuild --runtime <선택 runtime> --generation <선택 generation> --principal <신뢰된 주체.json> --binding <정확한 현재 경험 binding.json>
```

이관은 원 DB의 일관된 snapshot과 모든 테이블의 원본 레코드·ID 매핑·receipt를 보존한다.
memory-v2의 질문/정정은 이름공간을 나눠 이관하고 경험은 `LEGACY_UNBOUND`, 질문은 재조사가
필요한 PENDING으로 둔다. action-memory의 개념/관계/중단 상태는 감사 원본으로 보존한다.
기존 로그·Markdown·action-memory가 사용자 확정 경험으로 자동 승인되지 않는다.
공통 법률 지식으로 활성화하는 자동 이관은 아직 구현 범위가 아니다.

## 검증·활성화 상태

[통합·복구 테스트](../../../05_TESTS/CONTRACTS/test_unified_legal_agent.py)와
[이관·복구 검사](../../../05_TESTS/CONTRACTS/test_unified_memory_recovery.py)는 모의 원문과 scripted
transport로 실제 FastAPI/Pipeline/native journal/DB/publication을 실행한다.
최초 질문→1차 정정→2차 정정→원이벤트 복원→확정→두 위키 조회→새 대화 재사용을 검사한다.
U01~U15의 구조 경계와 장애 변형을 확인했으며, [검증 기록](../../../09_ARTIFACTS/VERIFICATION/unified-legal-agent-20261002/VALIDATION.json)에 범위를 남긴다.

```bash
.venv/bin/python 06_TOOLS/run_tool.py legal_agent_contracts.py --version v6
.venv/bin/python 06_TOOLS/pipeline.py plan --profile legal-agent-rag-v6
.venv/bin/python -m pytest -q 05_TESTS/CONTRACTS/test_unified_legal_agent.py 05_TESTS/CONTRACTS/test_unified_memory_recovery.py
```

프로필 plan은 선언·코드 해시 검증이며 모델 질의 실행이 아니다. 실제 실행 진입점은 위의 API다.
전체 serving inventory의 활성 릴리스 비교는 작업 코드와 frozen MAIN의 차이로 거절될 수 있다.
이를 통과시키려고 활성 포인터를 바꾸지 않는다.

완료한 것은 공통 계약·첫 전체 흐름·현재성/복구/이관의 작업 구현이다. 전체 법률 도메인
카탈로그 채움, 세밀한 법률 관계별 영향 분석, 독립 법률 사례의 out-of-sample 품질·시간·비용
실험은 남아 있다. 알려진 공개 CM 2사례의 실제 Qwen3.8 실험은
[ADR-0619](../../../04_EXPERIMENTS/ADR/ADR-0619-unified-cm-guidance-interrupted-continuation/RESULT.md)에 기록했다.
최초0/2에서 가이드 후 핵심 판단 자동평가1/2로 바뀌었으나 일반 재검토도1/2였다.
CM-051은 근거를 확보한 뒤 해석 검증이 실패했다. CM-003은 분류를 교정한 뒤 새 법령명 오류가
발생했고, 두 위키에 같은 ID로 연결된 경험을 새 대화에 재사용할 때도 반복됐다. 전체 가이드 답변 성공은0/2이며
구체 가이드의 우월성·독립 사례 일반화·정답 기억의 안전성은 확인하지 못했다.
중단 원본은 ADR-0618에 보존하고 같은 코드·입력의 미완료 요청만 ADR-0619에서 재개했다.
MAIN 승격·GENOS 배포·workflow 편집기 반영은 수행하지 않았다.
GENOS에서 명시 선택하려면 `GENOS_RAG_IMPLEMENTATION=legal-agent-unified-v6`와
정확한 내부 모델 `LEGAL_AGENT_PROFILE/LEGAL_AGENT_PROFILE_SHA256`를 함께 사용한다.
현장 명령은 `python3`이며 실제 검증은 workflow 테스트 화면에서 한다.
롤백은 이전 frozen 릴리스·프로필·원문 generation을 다시 선택하고 v3 DB를 보존하는 방식이다.
구코드에 v3 DB를 쓰게 하지 않는다. 이전 v5 실행·기록은 삭제하지 않았다.

## 누적 반입 R4와 의미 검증기 제거 (2026-10-02)

사용자 요청으로 R2 발송본 이후의 ADR-0623 누적 구현을 작업 v6에 연결했다.
최소 단위 원문→닫힌 exact/subtree 선택→묶음 정·역참조→선택 원문→판단·작성·게시·경험 재사용이
같은 source/evidence 계약을 따른다. 현재 fulltext builder·manifest reader·NFS DELETE 저널과
이미 반영한 service/service.py 어댑터를 보존하며 frozen 후보를 통째로 덮어쓰지 않는다.
단위 경로는 선택 fulltext가 semantic-unit-fulltext-v1일 때만 v6에 자동 결속한다.
기존 조 단위 색인을 쓰면 기존 회수 경로다. 코드 설치만으로 색인·세대/CURRENT는 전환되지 않는다.

판단 후 memory-assess-check, 작성 후 memory-compose-check LLM 호출을 제거했다.
JSON 형식·제시한 ID/범위·정확한 인용·원문 해시·권한·현재 revision·게시 검사는 유지한다.
원장과 응답에 검토 SKIPPED, claim UNREVIEWED, quality_certified=false를 기록한다.
인용/형식 계약 위반의 제한된 수정 요청은 의미 검증기 호출이 아니다.

연결 수집은 아직 조 단위이며 현재 항·호·목의 관계만 우선 제시하는 요구는 미구현이다.
CM003의 예외 본문 미열람과 CM051의 id/scope 선택 실패는 기존 연구 결과로 보존하며
이번 모의 계약 통과를 두 사례의 법률 품질 개선으로 보고하지 않는다.
활성 MAIN 포인터·현장 GENOS 리비전은 변경하지 않았다.
인계 ZIP/TXT와 발송·검증 영수증은
08_DEPLOYMENT/GENOS/handoffs/unified_v6_cumulative_20261002_r4에 남긴다.

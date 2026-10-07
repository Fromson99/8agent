# 수정형 더블 하네스 — 구현·실행 안내

2026-09-19 작업 코드 기준. `legal-agent-v1`은 **명시적으로 선택하는 미승격 구현**이다.
계약·합성 통합 검사는 실제 모델의 쟁점 발견률·답변 정확도·GENOS 현장 검증을 대신하지 않는다.
`quality_certified=false`이며, 기존 MAIN 기본 프로필과 활성 릴리스는 변경하지 않았다.

설계 기준은 [시스템 상세 설계](../REPORTS/LEGAL_AGENT_DOUBLE_HARNESS_DESIGN_20260919/SYSTEM/SYSTEM_DESIGN.md)다.
그 문서의 작성 당시 상태와 부속 검증 기록은 보존했다. 이후 사용자 수정 요구인
**탐색 우선·잠정 쟁점 변경·질문 원문 직접 대조·서버 Q ID**를 현재 구현에 우선 반영했다.

## 1. 실제 연결 경로

`POST /v1/rag/ask → Pipeline.run → 요청별 LegalSession → Coordinator → StageRunner`

| 단계 | 실제 책임 | 다음 소비자 |
|---|---|---|
| retrieve | 빈 쟁점 상태로 문서 탐색 시작, 원문 읽기, 잠정 쟁점·판단 변경 | select |
| select | CURRENT finding과 같은 쟁점의 조건·상충 근거 선택 | assemble |
| assemble | 검증된 정확 구간 조립, 필요한 묶음이 상한을 넘으면 incomplete | answer |
| answer | 문단별 claim 작성 → 정확 버전 검토 → 질문 전체 직접 대조 → 서버 gate | Coordinator |
| RESEARCH | 같은 요청·질문·journal로 retrieve부터 재실행 | 네 단계 |
| RECOMPOSE | 현재 assemble인지 확인 후 answer만 재실행 | answer |
| FINAL | 외부 Result 계약 검사 → publication outbox → 내구성 있는 run JSON | API·피드백 |

선언 정본은 `00_SYSTEM/PIPELINE.json`의 `legal-agent-rag-v1`이다. 네 엔진의 실제
entrypoint는 `02_BACKEND/semantic_runtime/legal_agent/stages.py`이며 기존 Pipeline을 재사용한다.
`legal.control`만 내부 신규 계약이다. 외부 Request·Result는 `term-runtime-v1`을 유지하고,
제어 메타데이터는 기존 open object인 `term_agent`에 둔다.

`02_BACKEND/PIPELINE/engine_host.py`로 후보의 선언·해시·단계 연결을 검사할 수 있다.
실제 요청 수명·재진입 실행 진입점은 `Pipeline.run`/API다. 일반 artifact용
`engine_host.execute`에 이 후보를 주는 별도 CLI 실행은 제공하지 않는다.

## 2. 이번 수정 요구와 구현 위치

| 수정 요구 | 구현 |
|---|---|
| 쟁점 없이 탐색 | `legal_agent/session.py`: 최초 `list_documents`, 읽기 도구에 issue 선행조건 없음 |
| 질문·문서명·용어 보존 | `context.py`, `views.py`: 질문 원문 전체와 허용 문서 범위 매 호출 전달; 문서명을 법률 개념으로 강제 확정하지 않음 |
| 읽은 원문에서 잠정 쟁점 발견 | `updates.py`: `source_trigger` 생성 시 실제로 제시한 E 검사; 발견 자체의 의미 정확성은 모델 평가 대상 |
| 쟁점 수정·분할·병합·교체 | `revise_issue`, `split_issue`, `merge_issue`, `supersede_issue`; 이전 required/Q 범위를 조용히 삭제하지 못함 |
| 변경 후 판단 재검토 | `repository.py`: 버전 의존성을 따라 assessment/finding/claim/review 및 산출물 무효화; 원문은 보존 |
| 장부와 별도로 질문 전체 대조 | `reviewer.py`: 모든 Q ID와 전체 질문을 별도로 검사; 최종 남은 answer claim으로 답했는지 gate가 재확인 |
| 모델의 문자 위치 계산 제거 | `context.py`: 연속 원문 구간 Q1…Q64 생성, 이후 나머지 원문은 마지막 구간에 모두 보존; 모델은 ID만 선택 |

초기 쟁점은 탐색 권한을 좁히지 않는다. 단, 사용자가 정한 문서 scope 밖으로 넓히는 것도 허용하지 않는다.
`required`와 쟁점 내용은 여전히 모델 제안이므로, 장부 검사만으로 누락이 없다고 보증하지 않는다.

## 3. 저장·검토·출력 규칙

- 요청별 SQLite와 요청별 원문·색인 연결을 사용한다. 원문 E, 정확 구간, 모델 제시 이력은 불변이다.
- 모델 변경안은 예상 revision, 현재 entity version, 제시된 E, Q ID, 의존 관계를 검증한 뒤 한 transaction으로 적용한다. batch 실패는 전체 rollback한다.
- 한 번의 변경안 안에서 updates를 먼저 반영하고 reads를 실행한다. 아직 읽지 않은 결과를 같은 변경안에서 채택할 수 없다.
- 제시되지 않은 근거, 다른 요청 handle/cursor, 다른 세대·범위·해시·구간은 거부한다. 검색 결과 메타데이터는 읽은 원문이 아니다.
- 원문 조립은 선택 구간만 사용한다. 겹치는 구간은 합치되 원래 E anchor를 보존하고, 떨어진 구간 사이의 본문을 끼워 넣지 않는다.
- 모든 답변 문단은 finding/E를 가진 versioned claim이다. 현재 버전의 SUPPORTED review가 없는 문단은 최종 결론에 넣지 않는다.
- 같은 쟁점의 CURRENT `contradicts` 판단이 남으면, 검토 모델이 승인했더라도 해당 결론을 제외한다. 먼저 조사·판단 수정으로 상충 상태를 해소해야 한다.
- Composer의 자유형 limitations 메모는 journal과 Reviewer 입력에만 보존한다. 검토된 법률 문장처럼 그대로 출력하지 않는다.
- required 쟁점 누락, 직접 질문 검토 누락, 미완료 추가 읽기, 미확인 시점은 BOUNDED에 반영한다. 모르는 사용자 사실은 CLARIFY로 남긴다.
- READY도 정답 인증이 아니다. 실제 원문 adapter는 현재 효력 시점을 `unknown`으로 보존하므로 현재 적용을 단정하지 않는다.
- `use_llm=false`이면 법률 판단·claim을 만들지 않고 탐색 시작점과 한계만 반환한다. 기존 `GET /v1/rag/search`는 별도로 유지된다.

## 4. 설정과 명시적 선택

분리된 두 설정은 다음과 같다.

- DomainSpec: `00_SYSTEM/LEGAL_AGENT/domain-v1.json`. 검사·원문·범위 정책. v1은 감사된 정책만 받아들이며 검사를 끄는 변형은 거부한다.
- AgentProfile: `00_SYSTEM/LEGAL_AGENT/profile-source-only.json`. 호출·시간·문맥·도구 예산. 기본 model_binding은 null이다.

로컬 계약 검사에서는 `create_app(..., implementation='legal-agent-v1',
legal_agent_profile=..., legal_agent_transport=...)`로 합성 단일 전송 adapter를 주입한다.
실제 모델을 쓸 때는 배포 환경이 명시적으로 작성·해시 고정한 프로필이 필요하다.
source-only 템플릿을 실모델 설정 완료로 해석하지 않는다.

GENOS 연결 코드는 다음 설정을 요구하지만, 이번 구현 중 현장 호출·배포는 하지 않았다.

| 설정 | 의미 |
|---|---|
| `GENOS_RAG_IMPLEMENTATION=legal-agent-v1` | 후보 명시 선택; 로컬 frozen release override는 금지 |
| `GENOS_GENERATION` 또는 기존 GENOS generation pointer | 읽을 원문 세대; 기존 service 선택 규칙 유지 |
| `LEGAL_AGENT_PROFILE` | 코드 root 안의 배포 AgentProfile 경로 |
| `LEGAL_AGENT_PROFILE_SHA256` | 해당 파일의 실제 SHA-256 |
| 기존 `GENOS_LLM_*`/profile 환경 설정 | endpoint·model·인증; [GENOS 진입점](../../../GENOS.md) 참조 |

실모델 `model_binding`은 `provider=genos`, 정확한 `model`,
`adapter_version=genos-single-send-v1`, `trust_zone=internal`,
`endpoint_identity`(기존 `genos.from_env('llm')`이 정규화한 target.root의 SHA-256),
`max_input_bytes`를 모두 요구한다. 인증키는 프로필·journal에 넣지 않는다.
시작 시 `/models`의 설정 모델을 확인하며, 응답의 실제 model도 대조한다. 자동 fallback은 없다.

기본 한도는 물리 시도 14회, 최종 작성·검토 예약 3회, 도구 56회, 요청 300초,
answer/review 최대 3회, 연속 무진전 2회, JSON repair 1회, transport retry 1회다.
retry/repair도 같은 물리 시도 예산을 소비한다. timeout의 원격 실행·과금 여부는 unknown이며 0으로 기록하지 않는다.
실전송은 단일 HTTP 호출과 총 deadline을 사용한다. 내부 adapter에 숨은 retry를 두지 않는다.

문맥은 문자 한도에 더해 **배포에서 검증해 지정해야 하는 보수적 입력 byte 한도**를 검사한다.
현재 tokenizer 기반의 실제 token 적합성 측정은 없다. `max_input_bytes`의 배포 적합성은 미검증이다.
동시 수용 한도는 프로세스별 4개이며 초과 요청은 503이다. 프로세스 간 전역 수용 제어는 아니다.

## 5. 게시·중단 복구·롤백

경로는 `WORKSPACE.json`의 runtime root 아래다.

- journal: `90_RUNTIME/semantic/legal-agent/runs/YYYYMMDD/<run_id>/journal.sqlite`
- 최종 결과: `90_RUNTIME/semantic/runs/<run_id>.json`
- 피드백: 기존 `/v1/rag/feedback` 경로

`RUNNING → COMMIT_READY → COMPLETED` 순서다. FINAL만 outbox에 기록하고, fsync한 임시 파일을
no-clobber 방식으로 설치한다. 같은 hash 재게시는 허용하지만 다른 기존 결과를 덮어쓰지 않는다.
API뿐 아니라 직접 `Pipeline.run` 호출도 반환 전에 이 수명을 완료한다.

앱 시작 시 owner lock을 획득할 수 있는 journal만 복구한다. 살아 있는 요청은 건드리지 않는다.
COMMIT_READY는 저장된 outbox만 재게시한다. RUNNING에서 소유자가 사라졌으면 INTERRUPTED로 남긴다.
모델 자동 재호출·질의 자동 재개·알 수 없는 과금의 0 처리·과거 journal 자동 이행은 하지 않는다.
게시 대상 hash 충돌은 보존하고 실패하므로, 현장에서 양쪽 기록을 검토해야 한다.

기본 경로를 바꾸지 않았으므로 작업 코드 후보 사용 중단은 명시적 후보 선택을 제거하면 된다.
활성 릴리스 `document-navigation-rag-20260917-v2`(generation 16)와 frozen release는 그대로다.
후보 MAIN 승격·GENOS 배포·데이터 이행은 이 작업에 포함하지 않았다.

## 6. 재생성·검사 및 남은 검증

WSL `/home/jin/8-AGENT`와 저장소 `.venv/bin/python`을 사용한다.
후보 또는 공용 실행 코드를 수정하면 다음 명령으로 스키마·엔진 코드 해시를 다시 고정한다.
기존 working manifest의 의존 해시도 갱신하지만 frozen release·활성 포인터는 바꾸지 않는다.

```bash
.venv/bin/python -B 06_TOOLS/COMMANDS/legal_agent_contracts.py
.venv/bin/python -B -m pytest -q \
  05_TESTS/CONTRACTS/test_legal_agent_double_harness.py \
  05_TESTS/CONTRACTS/test_legal_agent_failures.py \
  05_TESTS/CONTRACTS/test_document_navigation_serving.py \
  05_TESTS/CONTRACTS/test_task_harness_wiring.py \
  05_TESTS/CONTRACTS/test_navigation_main_wiring.py \
  05_TESTS/CONTRACTS/test_term_agent_main_wiring.py \
  05_TESTS/CONTRACTS/test_rehash_engines.py \
  05_TESTS/CONTRACTS/test_genos_structured_server.py \
  05_TESTS/REGRESSION/core/test_genos_proxy_client.py
```

합성 사례는 승인 원칙 읽기 → 초기 판단 → Reviewer 추가 읽기 → 위임 예외 발견 →
기존 판단 철회·쟁점 교체 → 전체 단계 재실행 → 조건부 답변 게시까지 검사한다.
이외에 네 쟁점 변경 연산, 전이 무효화, 직접 질문 누락, 원문 scope/span,
호출 상한·repair·timeout, 동시 요청 격리, 게시 중단 복구, 기존 API 소비자 연결을 검사한다.

2026-09-19 최종 실행: **신규 44개 + 기존 회귀 43개 = 87개 통과**, 62.90초.
Starlette TestClient의 httpx 사용 중단 예정 경고 1건이 있었다.
후보 Python 21개 파일의 구문 검사와 `git diff --check`도 통과했다.
이 숫자는 계약·합성 통합·회귀 검사 수이며 실제 질문 정답 수가 아니다.

**아직 확인하지 않은 것:** 실제 모델의 처음 누락한 쟁점 발견률, 질문 전체 충족률,
실제 비용·지연·토큰 여유, 현장 GENOS 모델의 strict schema 지원, 운영 규모 성능,
원문 판본의 현재 법적 효력. 같은 모델의 Reviewer도 오류를 반복할 수 있다.
실제 품질 비교는 실험 표준에 따라 별도 ADR을 선점하고 사전 동결·평가해야 한다.

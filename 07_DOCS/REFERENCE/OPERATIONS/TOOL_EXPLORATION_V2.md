# MAIN 작업 코드의 도구 선택형 탐색 v2

2026-09-21 사용자 지시로 현재 작업 트리의 MAIN 기본 실행과 배선을 `legal-agent-tools-v2`로 연결했다. 제품 품질 실험과 활성 릴리스 전환은 수행하지 않았다. 활성 포인터·GENOS 배포와 작업 코드 선택은 구분한다.

## 실행과 계약

기존 `service.application → create_app → POST /v1/rag/ask → Pipeline.run → 요청 세션 → Coordinator/StageRunner → retrieve/select/assemble/answer → outbox` 경로를 사용한다. PIPELINE.json의 `legal-rag`와 `legal-agent-rag-v2`는 같은 v2 단계 선언을 사용한다. 명시 `document-navigation-v1`은 보존된 `document-navigation-rag-v1` 선언을, `legal-agent-v1`은 기존 v1 선언을 선택한다.

도구는 `tools_protocol.REGISTRY`의 browse/search/match_terms/term_occurrences/locate/lookup_definition/follow_reference/read/inspect다. 같은 정본에서 모델 출력 schema와 실제 dispatcher를 만든다. 형태소 fulltext가 없는 세대에서는 capability=false를 보여 주며 literal로 몰래 대체하지 않는다. ROOT는 기본적으로 등록 문서 전체이며, 사용자가 명시한 document_ids/scope가 있으면 그 범위에 결속한다. `/v1/rag/scopes`도 v2 기본값을 `전체`로 반환한다.

모델 탐색은 원질문·ROOT·도구로 시작한다. 트리·목록 선조회나 finding 장부 완성을 요구하지 않는다. 위치 후보와 READ 근거를 구별하고, 실제 전송된 view의 정확 원문에만 평가·인용을 연결한다. 도구 행동과 DRAFT를 함께 제안해도 새 결과를 다음 모델 입력에서 확인한다. 입력 한도로 생략된 새 결과가 있으면 즉시 DRAFT를 승인하지 않는다.

별칭·cursor는 요청과 자료 세대에 결속된다. READ는 exact/subtree/article, 부분 페이지, span 합집합 coverage와 재제시를 지원한다. 같은 완료 action_id는 이전 영수증을 반환하고 예산을 다시 소비하지 않는다. 새 턴에서 같은 READ를 요청하면 새 행동으로 계측하되 원문 I/O를 재사용한다. `REUSED`는 새 원문 발견을 뜻하지 않는다.

평가는 ADOPT/REJECT/DEFER 및 SUPPORT/CHALLENGE/CONTEXT다. 관련 반대 원문은 REJECT여도 검토 묶음에 보존한다. 초안·검토는 실제 E와 질문 구간에 연결한다. 검토 결과에 따라 RESEARCH/RECOMPOSE/REVIEW로 재진입한다. 오검토에는 원문 반론을 제시하고 제한 재검토한다. 독립적으로 검토된 주장은 보존하고 변경된 원문 평가·질문 해석에 의존한 주장은 무효화한다. 코드의 무결성 검사는 법률적 정답 판정이 아니다.

외부 Request/Result는 term-runtime-v1을 유지한다. canonical source_ids로 인용하고 추가 요약은 `assembly.term_agent.exploration_v2`에 둔다. 피드백은 기존 `/v1/rag/feedback`으로 실행·답변·세대에 결속된다. GENOS 서비스의 외부 mutation allowlist는 그대로이며 이 브릿지에서 피드백 POST를 새로 허용하지 않는다.

## 설정과 모델

제품 schema: `00_SYSTEM/SCHEMAS/tool-exploration-v2.schema.json`.
도메인: `00_SYSTEM/LEGAL_AGENT/domain-v2.json`.
기본 시스템 프로필: `00_SYSTEM/LEGAL_AGENT/profile-tools-v2.json`.

저장된 기본 프로필의 model_binding은 null이다. `use_llm=false`와 보수적으로 인식한 문서 목록 요청은 모델 없이 실행한다. 모델이 필요한 요청은 명시 모델 프로필이 없으면 설정 오류로 종료한다. 기존 Haiku/provider나 외부 대리 모델로 자동 전환하지 않는다.

GENOS 인계 시 설정:

```text
GENOS_GENERATION=<명시 서빙 세대 또는 기존 GENOS_DATA_ROOT/CURRENT 경로 사용>
GENOS_RAG_IMPLEMENTATION=legal-agent-tools-v2
LEGAL_AGENT_PROFILE=<코드 루트 아래의 현장용 v2 JSON 프로필 상대 경로>
LEGAL_AGENT_PROFILE_SHA256=<그 프로필의 SHA-256>
SEMANTIC_LLM_BACKEND=genos
```

현장 프로필의 model_binding에는 provider, model, adapter_version, endpoint_identity, trust_zone, max_input_bytes가 필요하다. 실제 내부 모델 ID와 내부 endpoint의 hash를 결속하고 `provider=genos`, `trust_zone=internal`, `adapter_version=genos-single-send-v1`을 사용한다. 기존 GENOS 전송 모듈의 인증·접속 환경변수는 [GENOS 진입점](../../../GENOS.md)을 따른다. 키를 JSON 프로필이나 보고서에 넣지 않는다. 실제 모델과 입력 한도는 현장에서 확인해야 하며 이 세션은 GENOS에 접근하지 않는다.

명시 구현 환경변수를 생략해 작업 MAIN의 기본 v2를 선택해도 LEGAL_AGENT_PROFILE/해시가 주어지면 읽는다. 로컬 frozen release는 자체 PIPELINE·프로필을 유지하며 환경변수로 덮어쓰지 않는다. `06_TOOLS/serve.sh`는 여전히 ACTIVE_RELEASE를 읽으므로 작업 코드 수정만으로 현재 로컬 릴리스를 교체하지 않는다.

## 저장·복구·이행

요청별 DB는 workspace의 runtime root 아래 `semantic/legal-agent/runs/<date>/<run_id>/journal.sqlite`다. v2의 SQLite user_version은 2이고 과거 v1 DB를 변경하지 않는다. 복구 시 버전을 판별해 해당 opener를 사용한다. COMMIT_READY만 outbox를 재게시하고 소유자를 잃은 RUNNING은 INTERRUPTED로 남긴다. 자동 모델 재호출이나 다음 사용자 발화의 세션 재개는 제공하지 않는다.

기존 문서·색인 세대는 재사용한다. 구조 부모/범위가 누락되거나 순환하면 임의 계층을 생성하지 않고 계약 오류로 처리한다. 원문·색인 정책을 바꿀 때는 별도 새 세대가 필요하다. 이번 작업은 원문·색인·용어집을 재구축하지 않았다.

## 패키징과 확인

기존 계약 생성기에 v2 옵션을 추가했다. 모델 호출이나 품질 실험을 하지 않는 코드·schema·manifest 패키징이다.

```bash
.venv/bin/python 06_TOOLS/COMMANDS/legal_agent_contracts.py --version v2 --default
.venv/bin/python -m pytest -q 05_TESTS/CONTRACTS/test_tool_exploration_v2.py
```

첫 명령은 작업 PIPELINE의 v2 기본 선택과 코드 hash를 갱신한다. 활성 포인터를 변경하지 않는다. 코드를 바꾼 뒤 hash 갱신 전에 실행하면 StageRunner가 실행을 거부한다. 검사 중인 코드와 manifest를 동시에 수정하지 않는다.

기존 release packager는 등록된 엔진 manifest와 관련 정책·workspace 파일도 복사하도록 보완했다. 패키지 생성이 모델 프로필 설정·품질 검증·승격을 대신하지 않는다. 실제 승격에는 저장소의 평가 및 promotion 절차가 적용된다. 이전 release로 롤백할 때 v2 journal을 보존한다.

검사는 합성 모델 응답을 사용한다. 도구 선택·원문 전달·부분읽기·범위·정정·검토 재진입·HTTP·피드백·동시 요청·저장·패키지 배선을 검증하며, 실제 모델의 법률 답변 품질과 GENOS 배포는 미검증이다. 최신 확인 결과와 기존 회귀 불일치는 [작업 기록](../../../09_ARTIFACTS/AUDITS/20260921-tool-exploration-v2-wiring/README.md)에 기록한다.

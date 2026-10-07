# GENOS LEGAL_AGENT 호출과 팀 선택

2026-09-22 작업 코드 계약. 워크플로우 → `service.service(config, data)` →
`/v1/rag/ask` → `Pipeline.run` → 선택된 RAG 요청 세션으로 연결한다.
GENOS 현장 적용과 내부 모델 성능은 미확인이다.

## 호출

워크플로우 Python 단계에 `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py` 전체를 넣고
`run(data)`에 질문과 팀을 같은 입력 객체의 최상위 필드로 전달한다.

워크플로우 리비전 환경변수 `TEAM_ID=risk_team`으로 팀을 고정할 수도 있다.
환경변수가 있으면 매 요청마다 읽어 앞뒤 공백을 제거한 뒤 입력 `team_id`보다 우선 적용한다.
환경변수가 없으면 아래 입력 파라미터를 사용한다. 둘 다 없으면 기존 전체 범위다.
명시적으로 설정한 `TEAM_ID`가 비어 있거나 형식이 잘못되면 호출 전에 오류로 중단한다.
전체 범위를 쓰려면 빈 값을 넣지 말고 환경변수를 제거한다.

```json
{"question": "내규상 승인 절차를 알려줘", "team_id": "risk_team"}
```

워크플로우는 다음 형태로 코드서빙에 전달한다. `financial_team`도 같은 방식이다.
팀명은 대소문자를 구분하며 실제 세대에 저장된 `<이름>_team`을 그대로 사용한다.

```json
{
  "API_TYPE": "LEGAL_AGENT",
  "question": "내규상 승인 절차를 알려줘",
  "team_id": "risk_team"
}
```

HTTP 직접 호출은 `POST /v1/rag/ask`에 `API_TYPE`을 제외한 객체를 보낸다.
`GET /v1/rag/teams`는 선택 세대의 팀명·문서 수·팀 미지정 문서 수를 반환한다.
코드서빙으로 조회할 때는 아래 기존 GET 중계 계약을 사용한다.

```json
{"op": "call", "method": "GET", "path": "/v1/rag/teams"}
```

정식 호출명은 `LEGAL_AGENT`이며 소문자 `legal_agent`도 정규화한다.
이전 워크플로우의 `ELS_QUERY`는 호환 별칭으로 유지한다. 두 호출 모두
`channel`, `session_id`, `request_id`, `user_id`를 RAG 입력에서 제거한다.
추적 메타데이터를 허용하지 않는 RAG 계약과 충돌하던 `user_id` 문제를 해결했다.
워크플로우 응답은 기존 `text` dict 반환이며 대화 이력을 저장하지 않는다.

## 선택 규칙

- `team_id` 지정: **해당 팀의 내규·외규만** 검색한다. 팀 미지정 문서는 제외한다.
- 공통 용어집은 탐색 단서로 유지한다. 문서 정의·출현·참조·원문 증거는 선택 문서 범위 안에서 탐색한다.
- `team_id` 생략: 기존 검색 범위를 유지한다. 명시적 `null`, 빈 문자열, 잘못된 형식,
  선택 세대에 없는 팀은 422이며 전체 검색으로 대체하지 않는다.
- `scope`는 기존 `기본`/`개정이력`/`전체` 구분이다. 팀 선택과 함께 쓰면 교집합을 사용한다.
- `document_ids`를 함께 쓰면 모두 그 팀 소속이어야 한다. 다른 팀 문서를 섞으면 422다.
  기존대로 `document_ids`와 `scope`를 동시에 지정할 수 없다.
- 팀 소속은 해시가 검증된 `document.document_metadata.team`과 수집 시 보존된
  `aliases[].team`을 사용한다. 동일 원문의 여러 팀 보관 기록은 각 팀에서 선택할 수 있다.
  현재 디스크 폴더명이나 질문 텍스트로 소속을 추정하지 않는다.
- 팀 선택은 검색 필터다. 접근권한·반출 승인·사용자 인증을 부여하지 않는다.

`GET /v1/rag/search`, `/documents`, `/scopes`, `/section`, `/nodes`,
`/document/outline`, `/document/read`, `/links`에도 `team_id`를 전달할 수 있다.
문서 목록은 팀 필터 후 페이지를 나눈다. 직접 원문 조회는 팀 밖 ID를 거부한다.
`/links`는 범위 밖 연결점이 있는 참조를 제외하며, 에이전트의 참조 탐색은
범위 밖 원문을 열지 않고 기존 미확인 상태를 보존한다.
팀 파라미터를 생략한 별도 API 호출에는 이전 요청의 팀을 자동 적용하지 않는다.

## 실행·데이터 계약과 배포

팀 선택은 `Pipeline.plan`에서 고정 문서 ID 목록으로 변환한다. `Pipeline.run`은
이를 기존 `term-runtime-v1` Request의 `document_ids`로 넘긴다. 검색·목록·원문 읽기·
관계 탐색·답변 게시 journal이 같은 문서 범위를 공유한다. 내부 스키마 버전은 그대로다.
새 DB 컬럼이나 의존 패키지는 없고, 새 `semantic_runtime/team_scope.py`가 필요하다.
`PIPELINE.json`과 그 엔진 manifest의 코드 해시를 함께 배포해야 한다.

이미 팀 메타데이터가 있는 선택 세대는 그대로 사용할 수 있다. 없는 과거 세대는
팀을 선택할 수 없다. [팀별 구축 계약](GENOS_TEAM_RAW.md)에 따라 새 구조화·통합 세대를
만들어 선택해야 하며, 완료된 원문/색인/manifest를 직접 수정하지 않는다.

이번 `8agent-genos-pipeline-workflow-team-env-20260922-r2.zip`은 ZIP 안의 경로가
`DEV` 루트와 일치한다. `~/DEV/TRANSFER`에 업로드한 뒤 `DEV`에 직접 풀면 포함된
작업 코드 파일을 곧바로 덮어쓴다.

```bash
cd -P ~/DEV
python3 -m zipfile -e TRANSFER/8agent-genos-pipeline-workflow-team-env-20260922-r2.zip .
```

기존 원문·색인·`.env`·가상환경·Git은 ZIP에 포함되지 않는다. ZIP에 없는 구 파일은
삭제되지 않으므로 현장 코드 백업과 차이를 확인한다. 압축 해제 뒤 코드서빙에 새 코드와
`GENOS_GENERATION` 또는 `GENOS_DATA_ROOT`로 선택한 현장 세대를 결속하고,
기존 내부 모델 프로필·설정으로 새 코드서빙 리비전을 배포한다. 워크플로우도 새 파일로
별도 배포해 채팅 앱이 선택하게 한다. 인증키 값은 코드에 넣지 않는다.
워크플로우 주소·서빙 ID·시간 제한은 [채팅 연결](GENOS_CHAT_WORKFLOW.md)의 설정을 따른다.

현장에서는 `/teams`와 팀별 `/documents`로 먼저 범위를 확인하고, 두 팀을 번갈아 질의해
선택 범위와 실제 답변을 확인한다. 복구 시 이전 코드서빙·워크플로우 리비전을 다시 선택한다.
데이터 선택까지 바꿨다면 그 변경 영수증의 롤백 절차를 별도로 사용한다.

이번 변경은 작업 코드만 수정한다. 로컬 활성 `legal-agent-v5-20260922-r3`의 frozen 코드,
ACTIVE_RELEASE, 완료 실험 후보와 GENOS 리비전은 변경하지 않는다. 로컬 frozen 릴리스를
그대로 선택하면 새 `team_id` 계약은 제공되지 않는다.

검증은 모의 원문·공통 용어집과 외부 호출 없는 v5 계약 검사다. 실제 GENOS 모델 응답 품질,
현장 데이터의 팀 누락·오분류, 현장 코드 반입·리비전 배포는 별도 확인이 필요하다.

2026-09-22 검증: 아래 6개 파일의 **114개 테스트 통과**. 팀 간 검색·목록·읽기·참조 범위,
중복 소속, 잘못된 팀 거부, 같은 프로세스에서 팀 전환, LEGAL_AGENT/기존 별칭,
실제 서비스 부팅과 v5 게시 journal까지 확인했다. 엔진 해시 불일치·미등록 모듈은 0개,
데이터 결속 검사도 통과했다. 기존 구 의미 세대의 정상 로드를 기대하던 테스트는 현행 계약의
이행 필요 오류를 확인하도록 갱신하고, 새 형식의 실제 부팅은 새 모의 세대로 검증했다.

```bash
.venv/bin/python -m pytest -q \
  05_TESTS/CONTRACTS/test_genos_team_selection.py \
  05_TESTS/CONTRACTS/test_legal_agent_v5.py \
  05_TESTS/CONTRACTS/test_legal_agent_failures.py \
  05_TESTS/CONTRACTS/test_document_navigation_serving.py \
  05_TESTS/REGRESSION/core/test_genos_rag_chat.py \
  05_TESTS/REGRESSION/core/test_service_entry.py
```

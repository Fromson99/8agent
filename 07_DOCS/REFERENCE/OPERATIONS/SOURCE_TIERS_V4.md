# 모델 선택 기반 출처 v4 — 실행·검증·복구

후속 기록: [ADR-0488 기반 엣지케이스 원장](../REPORTS/SOURCE_TIERS_EDGE_CASES_20260921/README.md). 외부 Qwen 실행에서 후보 발견 후 조기 종료, 원문 전달 실패, 선택 오류 복구 실패, 게시 설정 충돌을 확인했다. 아래의 모의 계약 검사·당시 구현 기록과 구분하며, 원장 정리만으로 제품이 수정된 것은 아니다.

2026-09-21 작업 코드. 수정 설계서 전체를 기준으로 기존 요청 세션과 StageRunner에 추가한 opt-in이다. 기본 v2, 기존 v3, 선택된 로컬 릴리스와 GENOS 배포 상태는 별도다.

## 계약과 실행

`service.py → create_app → Pipeline(legal-agent-rag-v4) → ServingLegalAgent → TiersSession → retrieve/select/assemble/answer → publication outbox`를 사용한다. 구현 ID는 `legal-agent-tools-v4`다. 별도 RAG 실행기·데이터 생성기는 없다.

- 도메인: `00_SYSTEM/LEGAL_AGENT/domain-v4.json`
- 시스템 프로필: `00_SYSTEM/LEGAL_AGENT/profile-tools-v4.json`
- 내부 schema: `00_SYSTEM/SCHEMAS/source-tiers-v4.schema.json`
- journal: `journal-v4.sql`, SQLite user_version 4. 이전 journal을 변환하지 않는다.
- 외부 결과: 기존 term-runtime-v1의 `assembly.term_agent.source_bundle`.

기본 모델 binding은 null이다. 프로그램으로는 기존 `create_app(..., implementation='legal-agent-tools-v4', legal_agent_profile=..., legal_agent_transport=...)`를 사용한다. GENOS에서는 명시적인 GENOS generation과 `GENOS_RAG_IMPLEMENTATION=legal-agent-tools-v4`, `LEGAL_AGENT_PROFILE`, `LEGAL_AGENT_PROFILE_SHA256`를 설정한다. 프로필의 내부 모델 ID·endpoint identity·신뢰 구역·검증된 최대 입력 bytes를 현장 설정에 결속해야 한다. 키를 프로필이나 journal에 넣지 않는다. 로컬 frozen release에 환경변수만 덮어쓰는 선택은 기존 서비스가 거부한다.

기본 한도는 CORE 5, SUPPLEMENTAL 5, 카드당 선택 원문 1,600자, 원문 페이지 4개, 관계 메뉴 12개다. 모델 물리 시도 14, 종료 예약 3, 짧은 선택 단계 최대 2회, 도구 56, 요청 세션 시간 300초다. 남은 세션 시간이 30초 미만이면 탐색을 중단하여 선택을 시도한다. 초기화 시간을 포함한 E2E 지연 보장은 아니며, 한도는 최적 품질의 실측값이 아니다. wire 전체는 모델 binding의 byte 한도를 별도로 확인한다.

모델은 실제 제시된 span ID와 CORE/SUPPLEMENTAL 역할·관련성 이유·해석 상태를 선택한다. pending/rejected는 현재 READ된 evidence ID와 사유를 사용한다. 원문을 읽지 않은 후보는 탐색 메뉴와 원장에 남는다. 묶음 채택은 같은 결정의 selections 배열에 원칙·예외를 각각 명시하는 방식이다. 그룹 ID를 서버가 자동 확장하지 않는다.

선택은 법적 ADOPT/SUPPORT와 별도다. 모델은 선택만 하고 해석·관계 평가 배열을 비워도 된다. 법적 주장을 작성하려면 기존 v3 평가·공동 검토가 추가로 필요하다. 기존 해석 평가에서만 채택한 원문을 tier 출처로 자동 옮기지 않는다. 선택이 없으면 NO_SELECTION이다.

## 최종 화면과 원문 열기

로컬 `/rag/`는 `/rag/source-tiers.js`로 핵심·보완 카드, 정확 발췌, 선택 이유, 해석 미확정 상태를 표시한다. 카드의 URL은 서버가 만드는 `/v1/rag/source?run_id=...&selection_id=...`다. 이 API는 발행된 선택과 현재 세대·문서·artifact·원문 hash를 대조한 뒤 선택 원문을 HTML로 제공한다. 선택 범위 밖 전체 문서는 기존 문서 탐색 API에서 확인한다.

`/v1/rag/source-candidates`는 해당 실행의 실제 검색·관계 카드와 READ 원장에서 미열람·미채택 후보를 페이지로 보여준다. DISCOVERED_NOT_READ, READ_UNSELECTED, PENDING을 구분하며 rejected와 이미 선택한 원문은 숨긴다. 모델이 보지 않은 후보를 채택 출처로 계산하지 않는다.

GENOS 워크플로 renderer도 bundle을 읽고 claims=[]·빈 answer에서도 문서명·조문 위치를 표시한다. 채팅 본문에는 원문 API 경로를 링크로 넣지 않는다. 현장 사진에서 상대 URL이 출처명 대신 노출되었다. 열람 경로는 API의 `source_bundle.sources[].open_url`에 보존되며, 브라우저 접근 가능한 인증 경로와 채팅 링크 렌더링은 현장 검증 전까지 미확인이다.

## 저장·복구·원복

선택은 versioned entity와 SOURCE_SELECTION 이벤트, 실제 model_view/attempt에 결속한다. bundle은 별도 versioned entity이며 선택 상태 hash와 자체 hash를 가진다. prepare/export는 journal과 결과의 동일성을 검증한다. 선택 변경 후 이전 bundle 발행은 거부하며 새 bundle이 필요하다.

COMMIT_READY는 기존 `publication.recover`가 현재 Store 검증 callback을 받은 경우만 복구한다. 앱 startup은 이 callback을 연결한다. callback 부재·세대/접근 범위 변경은 BLOCKED 이벤트를 남기고 발행하지 않는다. scope가 줄었을 때 모든 다른 결과 필드까지 포함한 누출을 막기 위해 전체 outbox 발행을 차단한다. 실행 중 source_selection은 보존되지만 소유자를 잃은 RUNNING은 기존 정책대로 INTERRUPTED이며 LLM을 자동 재호출하지 않는다.

현재 접근 검사는 선택된 Store와 요청/manifest scope 기준이다. 별도 사용자 ACL 제공자와의 연결, 변경된 권한에 따라 카드별로 정제하여 같은 실행을 재발행하는 경로는 구현 완료로 판정하지 않는다.

작업 원장은 기존 `06_TOOLS/run_tool.py legal_agent_trace.py --runtime-root <semantic-runtime> --run-id <id>`로 확인한다. v3/v4를 읽고 이벤트·선택·관계의 hash를 검사한다. 원복은 implementation/profile을 이전의 명시 설정으로 되돌리는 것이다. v4 journal·outbox·과거 릴리스는 삭제하지 않는다. MAIN 승격·GENOS 배포 명령은 실행하지 않았다.

## 검증과 품질 비교

```bash
PYTHONPATH=02_BACKEND .venv/bin/python -m pytest 05_TESTS/CONTRACTS/test_source_tiers_v4.py -q
```

24개 모의 계약 검사가 통과했다. [요구사항별 판정과 증거](../REPORTS/DOMAIN_SYSTEM_HARNESS_REDESIGN_20260921/IMPLEMENTATION_VERIFICATION_20260921.md)를 따른다. 실제 외부 Qwen·내부 GENOS 모델 호출은 하지 않았다.

수정 설계서 6절의 품질 비교는 후속 실험이다. v3 baseline과 v4를 같은 공개 승인 범위·질문·세대·K·총예산·Qwen FP8/thinking off로 사전 동결하고 하나의 ADR 배치에서 비교해야 한다. CM 및 이미 본 FSC는 회귀/in-sample로 표시한다. recall/precision·관련성·원문 무결성·선택→bundle→rendered 손실·비용과 법적 정답률을 분리하며, 이 계약 검사를 모델 품질 향상 근거로 쓰지 않는다.

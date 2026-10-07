# 에이전트 판단 하네스 v5 — MAIN 실행

2026-09-27 사용자 지시: 작업 코드의 최종 검토는 advisory로 전환했다. 선택된
근거로 최종 작성·저장된 모든 문장을 표시하고, 검토 실패·반론·누락은 문서·조문별
법률 검토 필요사항으로 전달한다. 아래 표의 거절은 strict 검토 기록의 미승인이지
답변 문장 삭제를 의미하지 않는다. 검토의 재작성/재탐색 요구는 최종 확인사항으로
전달하며 추가 검토 루프를 시작하지 않는다. [현재 계약](GENOS_FINAL_REVIEW_ADVISORY_20260927.md).

2026-09-23 로컬 활성 모델 분기: `legal-agent-local-gemma-20260923-r1`은 공개 질문 표시와
공개 문서 범위 검사를 통과한 요청에 Gemma를 호출한다. GENOS는 아래 내부 모델 파라미터
결속을 그대로 사용한다. [로컬 경로·실제 응답](LOCAL_GEMMA_SERVING.md).
아래의 “기본 모델 미결속”은 직전 로컬 릴리스의 설명이다.

2026-09-23: 현재 로컬 MAIN은 v5의 회수·선별 앞단에 ADR-0513/0517을 연결한 `BoundedSourceSession`이다. [선별·복구 MAIN의 실행 경로와 한계](BOUNDED_SOURCE_RECOVERY_MAIN.md)를 먼저 확인한다. 아래 일반 v5 조사 경로는 해당 옵션을 끈 경우와 기존 세대의 계약이다.

2026-09-22 사용자 지시: 성능 점수와 별개로 보강된 하네스를 MAIN에 연결한다. `quality_certified=false`이며 GENOS 배포·실제 Gemma 정답률 인증이 아니다.

## 실행 경로와 계약

HTTP `/v1/rag/ask` 및 `06_TOOLS/pipeline.py run --profile legal-rag` → `Pipeline` → `ServingLegalAgent` → `ObligationSession` → 기존 Coordinator/StageRunner → 결과 소비자다. CLI도 같은 요청 세션을 사용하며 재탐색·재작성·재검토를 수행한다. 구현은 `legal-agent-tools-v5`, 프로필은 `legal-agent-rag-v5`. v2~v4 명시 경로는 보존한다.

외부 Request/Result는 `term-runtime-v1`, 원문 카드 표시 계약은 `source-tiers-v4`를 유지한다. 새 요청 원장은 journal v5이며 번호→영구 ID 매핑을 요청마다 보존한다. 과거 원장은 덮어쓰지 않는다. 데이터·용어집·색인 세대는 바꾸지 않으며 하위 데이터 재구축도 없다. 새 영구 법률 규칙 DB는 만들지 않았다.

## 보강 내용

|영역|서버가 강제하는 계약|모델이 판단할 내용|
|---|---|---|
|번호 선택|현재 입력의 1, 2, 3 정수만 허용, 공간별 매핑·전달 영수증·오래된 응답 차단|어느 조문이 관련 있는가|
|질문 유지|질문 조각의 요구/배경 분리, 전부 포함, 중복 배경 금지, 요구→주장→검토 연결|실제 요구와 배경 구분|
|한 글자 출력|취약한 `pattern: \\S` 제거, 설명 문구 최소 길이·비공백 검사, 구체적 교정 오류|의미 있는 요구·근거 설명|
|판단→행동|빈 CONTINUE 거절, DRAFT/CLARIFY와 실행 행동 충돌 거절, 누락 사실 없는 CLARIFY 거절|적절한 검색·추가 사실·종료 선택|
|반복|질문 계획·이유 재작성은 진행으로 계산하지 않음, 기존 반복·호출·시간 상한 유지|새 정보가 필요한가|
|근거 읽기|조문 단위 읽기·페이지 커서 결속·양방향 직접 참조·비재귀 자동 읽기·미해결 참조 표시|일반 규칙·특례·유사 개념의 적용 여부|
|원문 대조|검토 출처별 원문 인용·초안 인용의 실제 포함 여부, 출처 전부 검토|개념/범위/조건/예외/확실성/질문 적합성의 의미 보존|
|자기모순|CHANGED/UNCERTAIN이 있는 SUPPORTED, 근거 없는 ANSWERED, 전체 질문 미해결과 요구 전부 해결의 충돌 거절|같은 모델이 모두 잘못 동의하는 의미 오류는 여전히 가능|
|부분 답변|지원된 주장 유지, 요구별 미확인·추가 사실·재탐색·재작성 상태 노출|정확한 유보 범위|

원문·도구 출력은 지시가 아니라 자료라는 기존 경계를 유지한다. 선택은 관련성 판단이며 법적 정답 승인이 아니다. 인용 일치도 의미적 함의를 증명하지 않는다.

## 모델 설정

모델 접속 설정은 `GENOS_BASE_URL`, `GENOS_LLM_SERVING_ID`, `GENOS_LLM_KEY`,
선택값 `GENOS_LLM_MODEL`로 통일한다. Qwen/Gemma 변수와 `GENOS_LLM_PROFILE`은
현행 코드에서 읽지 않는다. 직접 접속은 `GENOS_LLM_URL`을 사용한다.
코드서빙 환경의 선택값 `GENOS_RAG_MAX_OUTPUT_TOKENS`는 v5 모델 호출 1회당
`max_tokens`를 정하며 비우면 6400이다. 양의 정수만 허용하고 실제 모델의 수용 한도는
현장에서 확인한다. 워크플로우 환경의 토큰 설정으로 처리하지 않는다.
[데이터 세대 교체 시 유지할 전체 서빙 계약](GENOS_RAG_GENERATION_HANDOFF.md)을 따른다.

기본 배포 프로필 `00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json`은 **모델 미결속**이다. 현재 외부 세션에서 내부 GENOS 주소·모델을 추측해 호출하지 않는다. 출처 조회(`use_llm:false`)는 바로 실행되며, LLM 요청은 명시 모델 설정이 없으면 거절된다. 이전 실험용 Gemma/OpenRouter 반출 승인을 제품의 비공개 질문·문서로 확대하지 않았다.

GENOS 코드서빙에서 `GENOS_GENERATION` 또는 `GENOS_DATA_ROOT/generations/CURRENT.json`으로 v5를 실행하면 모델은 환경변수로만 결속할 수 있다. `GENOS_BASE_URL`, `GENOS_LLM_SERVING_ID`, `GENOS_LLM_KEY`, 선택값 `GENOS_LLM_MODEL`을 코드서빙 환경에 지정한다. 직접 서빙 URL이면 `GENOS_LLM_URL`을 사용한다. 입력 바이트 보호 상한은 프로필의 문맥 길이에서 코드가 계산하므로 별도 환경변수가 필요 없다. 이 상한은 실제 모델의 토큰 문맥 수용량을 보증하지 않는다. 모델 ID를 생략하면 시작 시 `/models`의 단일 ID를 조회하며, 여러 ID가 있으면 명시해야 한다. 시작 시 같은 endpoint의 모델 목록을 다시 확인한다. 이 결속은 메모리에서만 만들며 JSON 파일은 필요 없다. `GENOS_RAG_IMPLEMENTATION`은 MAIN의 v5 기본값을 쓰면 필요 없다. `LEGAL_AGENT_PROFILE`과 해시를 둘 다 명시했다면 기존 파일 결속이 우선한다. 모델 변수 없이 시작한 v5는 출처 조회만 가능하다. 로컬 활성 릴리스에는 이 환경 결속을 적용하지 않는다.

기존 해시 고정 프로필 파일을 사용하는 배포도 계속 지원한다. GENOS에서 기존 LLM 환경변수에 내부 endpoint·서빙 ID·키를 설정한 뒤 다음 명령으로 파일을 만들 수 있다. Qwen과 Gemma 모두 MODEL을 생략하면 공통 `/models` 조회로 단일 모델 ID를 선택해 새 프로필에 고정한다. 모델이 여러 개면 MODEL을 명시해야 한다. MODEL을 명시한 결속 명령은 네트워크에 접속하지 않는다. 서빙 환경에서도 MODEL은 생략할 수 있으며 프로필의 고정 ID를 시작 시 검증한다. 이전 `GENOS_LLM_MODEL` 값이 남아 있으면 명시 설정으로 취급되므로 전환 시 제거한다. 개발 PC의 데이터·엔진 결속을 재작성하지 않는다. 같은 파일의 설정이 달라지면 새 출력 이름을 사용한다. 입력 바이트 상한은 해당 배포에서 검증한 값을 사용한다.

```bash
.venv/bin/python 06_TOOLS/run_tool.py legal_agent_contracts.py --version v5 \
  --profile-output 00_SYSTEM/LEGAL_AGENT/profile-genos-v5.json \
  --bind-genos-from-env --max-input-bytes <검증된_입력_바이트_상한>
```

기존 `GENOS_GENERATION`, `GENOS_RAG_IMPLEMENTATION=legal-agent-tools-v5`, `LEGAL_AGENT_PROFILE=00_SYSTEM/LEGAL_AGENT/profile-genos-v5.json`, `LEGAL_AGENT_PROFILE_SHA256` 경로로 실행한다. 시작 시 선택 모델과 endpoint 결속을 확인하며 자동 모델 fallback은 없다. 로컬 고정 릴리스는 환경변수로 모델을 몰래 교체하지 않는다. 모델 결속 변경 시 새 릴리스를 준비·활성화해야 한다.

## 파이프라인 CLI

`request.json`은 `{"question":"자료 목록","document_ids":[],"use_llm":false}` 같은 기존 Request 계약이다. `inputs.json`에는 `{"request":{"path":"/절대경로/request.json","sha256":"파일 SHA-256"}}`을 기록한다. 실제 모델 설정 완료 후 `use_llm:true`를 사용한다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py plan --profile legal-rag
.venv/bin/python 06_TOOLS/pipeline.py run --profile legal-rag --inputs inputs.json --output /새로운/실행/경로
```

결과와 receipt는 지정된 실행 경로, 요청 원장은 논리 runtime의 `semantic/legal-agent/runs`에 남는다. 원장 확인은 기존 `legal_agent_trace.py --runtime-root <semantic-runtime> --run-id <id>`이며 v5도 지원한다. 중단 요청을 자동으로 이어서 모델 호출하지 않는다.

## 전환·원복

작업 프로필 선택과 로컬 ACTIVE_RELEASE 선택은 별도다. 사용자 지시의 품질 면제와 구조 검사 결과를 `semantic_runtime.control prepare/apply --confirm-main`에 결속한다. 전환 기록과 이전 포인터·설정은 새 릴리스의 `rollback`과 local receipts에 보존한다.

```bash
PYTHONPATH=02_BACKEND .venv/bin/python -m semantic_runtime.control rollback --confirm-main
```

원복은 선택된 로컬 릴리스/설정을 되돌리며 새 원장과 기존 결과는 삭제하지 않는다. 이미 실행 중인 프로세스는 앱을 다시 시작해야 새 선택을 읽는다. 이번 작업은 Git main 병합이나 GENOS 리비전 배포를 의미하지 않는다.

[구현 확인·자체 검토·검사 증거](../REPORTS/LEGAL_AGENT_V5_COMPLETION_20260922/README.md)

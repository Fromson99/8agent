# 로컬 MAIN 탐색 연결

2026-09-29 현행 로컬 선택은 `legal-agent-navigation-storage-20260929-r3`(포인터 generation 29)이다.
검색 navigation과 구축 감사 원장을 분리한 새 데이터 세대를 사용하며 답변 코드는 직전 r3와
동일한 frozen 파일이다. 아래 날짜별 절은 과거 상태다.
[선택·검증·복구](NAVIGATION_STORAGE.md), 정본 포인터 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`.

## 현재: 문서 탐색 모드 (2026-09-17)

사용자 지시 `main배선 진행해줘 끝까지`로 로컬 MAIN을 `document-navigation-rag-20260917-v1`(generation 15)로 전환했고, 같은 날 전수 조사·수정 뒤 `document-navigation-rag-20260917-v2`(generation 16)로 다시 전환했다.
품질 인증 false. [배선·검증·롤백 기록](../../../09_ARTIFACTS/AUDITS/20260917-document-navigation-main-wiring/README.md).

`PIPELINE.json`의 `term_agent.implementation=document-navigation-v1`이다. 첫 모델 호출이 질문을 해석한다.

| 질문 예 | 해석 | 응답 |
|---|---|---|
| `내규 폴더에 어떤 문서가 있어?` | catalogue | `문서명 검색 결과 10개: 상장주선인의 기업실사점검표(2024.12.31) …` |
| `외부 문서 kofia 폴더 트리 보여줘` | tree | `external/kofia/` 아래 `CMA 업무관련 모범규준/  - CMA 업무관련 모범규준 …` |
| 특정 문서 목차 요청 | outline | 저장된 조·항 구조 목차 |
| 조건·요건·예외 질문 | content | 질문 개념별 후보 → 3건씩 읽기 → 근거별 검토 → (모델 `SYNTHESIZE` 또는 예산 임계) 종합·검증 |
| 표현 연결 요청 | mapping | 이번 요청 안에서만 확인. 저장·재사용하지 않음 |

목록·트리·목차는 본문을 읽지 않으며 법률 주장을 만들지 않는다. `use_llm=false`면 해석 없이 문서·폴더·용어 시작점만 반환한다.
문서 목록 API(`/v1/rag/documents`, `/document/outline`, `/document/read`)도 같은 폴더 분류를 쓴다.

**내용 질문의 후보와 예산 (2026-09-17 v2).** 후보는 질문의 최대 표면형(포함되는 짧은 매칭 제거)마다 하나의 진입 항목으로 만들고, 그 등록 용어들의 출현 조문과 지정 문서의 명시 조문을 모은다. 1홉 관계 용어는 후보에 넣지 않고 카드에만 보인다.
순서는 미검토 → 참조 대상 → 모델이 검색으로 찾은 것 → 명시 조문 → 지정 문서 → 질문 개념 적중 수 내림차순이며 컷은 없다. 실측: `임원 겸직 제한 규정` 후보 27개, 1·2순위가 `지배구조법 제10조 겸직제한`, `부동산신탁사 모범규준 제14조 겸직 제한`.
요청당 호출 14회 중 해석 1~3회, 요구사항 1회, 읽기·검토 2회씩, 종합·검증 2회를 예약한다. 후보를 다 읽지 않아도 채택 근거가 있으면 종합한다. 예산이 종합 몫만 남으면 서버가 종합하고, 그마저 없으면 채택 인용을 검증 없이 제시하며 미확인에 적는다. 18,000자 초과 조문은 블록 단위로 이어 읽는다. 도구 오류는 거절 이벤트로 남고 세션은 계속된다.
미검토 후보 수는 `retrieval.term_agent.candidate_review`에 남는다. 참조 미확인은 종류별 한 줄로 요약한다. [2차 조사·수정 기록](../../../09_ARTIFACTS/AUDITS/20260917-document-navigation-main-wiring/README.md#2차-main-rag-전수-조사수정리팩터링--2026-09-17-v2).

**성능.** 용어집 파일 해시는 stat 서명이 같으면 재계산하지 않고, 역매칭 색인·구조 노드·좌표는 세대 해시별로 프로세스에 캐시한다. 첫 요청 약 35~47초(색인·용어집 최초 적재), 이후 요청 준비 약 2초.

**폴더 분류.** 로컬 159문서 세대에는 폴더 기록이 없다. 해시 사슬로 원본 RAW 파일을 찾아 출처 파일을 만들었다:
세대 원문 해시 → 패키지 구조 산출물 → 같은 폴더의 원본 → RAW의 동일 바이트 파일.
결과는 kofia 72 · law 62 · krx 11 · internal/risk_team 10이다.
`위험관리기준시행세칙_v1_2024` 등 4건은 동일 원본이 RAW에 없어 미확인으로 둔다. 제목으로 추정하지 않는다.
출처 파일은 세대 ID·store 해시에 묶여 있어 다른 세대에는 적용되지 않는다. GENOS 세대는 구축 시 기록된 `document_metadata`를 쓴다.

**제약.** HTTP에는 대화 ID가 없어 대화 간 폴더 선택 유지·매핑 승인은 없다. 다음 요청 범위는 `document_ids`로 넘긴다. 실제 모델 품질은 미측정이다.

아래는 직전 MAIN이던 탐색 루프(`navigation-loop-v1`)의 계약이다. 설정으로 계속 선택할 수 있다.

## 이전: ID 기반 탐색 루프 (2026-09-16)

2026-09-16 사용자 지시 `일단 이거 메인 배선해봐`로 ADR-0432 rev-001의 탐색 루프를 로컬 서빙 경로에 연결한다. 적용 여부와 최종 포인터는 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json` 및 [배선 기록](../../../09_ARTIFACTS/AUDITS/20260916-navigation-main-wiring/README.md)을 따른다. 품질 인증은 false이며 ADR의 판정을 변경하지 않는다.

## 입력 → 출력과 배선

`service.py`가 활성 릴리스의 코드·데이터 해시를 확인한다. `Pipeline`은 `PIPELINE.json`의 `term_agent.implementation=navigation-loop-v1`을 읽고 `ServingNavigationAgent`를 선택한다. 원문 전용 159문서 세대, 전체 용어집, 해당 용어의 출현·실제 관계·명시 참조 인덱스가 입력이다. 생산 경로는 실험 실행기나 정답 데이터를 읽지 않는다.

`질문 역매칭 → 등록 용어/구조 시작점 → 정의/최대 3홉 관계/구조 조회 → 조건별 원문 메타데이터 목록 → 원문 구간 읽기 → 채택·제외·보류 → 추가 탐색`으로 진행한다. 채택 결과만 기존 `select → assemble → answer → feedback`으로 전달한다. 원문 전체·해시는 기존 출력 계약으로 보존하며, 답변의 주장은 실제 읽고 채택한 구간에 연결한다.

모델에는 긴 등록 ID 대신 `T1/S1/A1/E1/D1` 짧은 ID를 보여준다. 응답은 ID 필드(`term_id`, `term_ids`, `structure_id`, `source_id`, `segment_id`, `document_id`)에서만 원래 ID로 되돌린다. 이슈 ID가 `A3`처럼 짧은 ID 형식이면 그 이슈만 거절한다. 2026-09-17 전에는 모든 문자열을 되돌려 이슈 `A3`가 원문 ID로 바뀌는 충돌이 있었다.

페이지당 8개는 표시량이다. 총 8개 확정 컷은 없다. 요청당 최대 14회 호출·56개 행동·300초, 검토 중 최대 6구간·18,000자, 모델 문맥 60,000자다. 종료 이유, 읽은 구간, 채택/제외 판단, 경로, ID 별칭은 응답의 `retrieval.term_agent`와 실행 기록에 남는다. 요청 간 판단은 공유하지 않는다.

`use_llm=false`는 시작점 메타데이터만 반환하고 본문 자동 조회·채택은 하지 않는다. 모델 연결이 실패하면 미완료로 반환하며 이전 에이전트로 자동 전환하지 않는다.

## 데이터와 모델 경계

운영 데이터는 `01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1`이다. 기존 원문·인덱스·용어집·캐시를 복사했으며 원래 manifest/해시/원문 generation ID와 `export_allowed=false`를 보존한다. `PIPELINE.json`의 glossary 경로는 선택 원문 세대에 상대적이며 경로 탈출을 거부한다. 준비 시 및 실제 조회 시 용어집·사전·캐시 해시를 확인한다. 조회 자원은 HTTP 요청별로 열고 닫으며 전체 용어집 검증·역매칭 색인 구성 비용이 요청마다 발생한다.

호스트가 주입하는 기존 provider 계약을 사용한다. Gemini는 ADR-0432의 실험 모델이었으며 이번 배선에서 로컬 MAIN의 모델을 Gemini로 바꾸지 않았다. 외부 반출 허용 범위를 확대하지 않았다. GENOS에서는 내부 모델과 동일 계약의 원문/색인/용어집 묶음을 별도로 준비해야 하며 현장 적용·호출은 미확인이다. glossary 묶음이 없는 이전 GENOS 데이터 세대에는 새 루프를 바로 적용할 수 없다.

## 검증과 재현

```bash
.venv/bin/python -m pytest -q \
  05_TESTS/CONTRACTS/test_navigation_loop.py \
  05_TESTS/CONTRACTS/test_navigation_main_wiring.py \
  05_TESTS/CONTRACTS/test_term_agent_main_wiring.py \
  05_TESTS/REGRESSION/core/test_semantic_provider_backend.py \
  05_TESTS/REGRESSION/core/test_semantic_observability.py
.venv/bin/python 06_TOOLS/semantic_runtime.py status
bash 06_TOOLS/serve.sh
```

테스트의 모델은 고정 응답을 반환한다. 다중 홉·누적 8개 초과 읽기·제외 후 재채택·ID/범위 검증·실제 데이터의 HTTP 답변/피드백 배선을 검사하며 답변 품질 평가가 아니다. ADR-0432 Gemini 결과는 필수 조문 3/4 읽기, 채택 3/3 정답 근거이며 실제 추가 탐색의 누락 복구는 미확인이다.

## 적용과 롤백

릴리스 준비는 `06_TOOLS/semantic_runtime.py prepare`로 새 불변 release를 만든다. 코드/스키마/설정·데이터 해시, 사용자 지시, 계약 검사 결과를 묶고 이전 포인터와 실행 진입점을 보존한다. `apply --manifest … --confirm-main`은 이전 포인터 해시가 일치할 때만 전환한다. `USER_DIRECTED_CUTOVER`는 품질 통과 승격과 구분한다.

명시적 롤백:

```bash
.venv/bin/python 06_TOOLS/semantic_runtime.py rollback --confirm-main
```

롤백은 직전 릴리스 포인터 및 PIPELINE/진입점을 복원하고 새 receipt를 남긴다. 서빙 프로세스는 선택 코드를 캐시하므로 적용·롤백 후 기존 로컬 프로세스가 있다면 재시작한다. 다른 프로젝트의 서버나 GENOS 서버를 조작하지 않는다. Git 병합·GENOS 배포는 별도 작업이다.

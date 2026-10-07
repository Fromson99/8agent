# 질문 시 구조·용어 탐색 맥락 — 로컬 MAIN 2026-09-30

사용자 지시로 로컬 활성 릴리스를 `legal-agent-question-navigation-qwen38-20260930-r2`
(포인터 generation 34)로 전환했다. 데이터 세대 `term-source-1acfbe06921527e74a0b`,
Qwen3.8 공개 질문 범위, 원문 인용 검증은 그대로다. 품질 인증은 `false`이며 GENOS
코드서빙·워크플로우 배포는 별도다. 이전 활성 릴리스는 rollback 대상으로 보존한다.

## 요청 경로

`service.py` → `Pipeline` → `ServingLegalAgent` → `BoundedSourceSession`에서 기존
문서·조문 좌표 구조 경로를 먼저 검사한다. 유일한 문서의 따옴표 안 단일 용어에 대한
정의 질문이면, 같은 문서의 저장된 정의 색인에서 정확한 표제어와 원문 source ID를 찾아
구조 경로에 포함한다. 이때도 원문 전체를 현재 요청에서 다시 READ하고, 선별 모델이
질문의 다른 요구·예외에 자료가 부족하다고 판단하면 기존 fulltext로 돌아간다.
여러 용어, 문서 모호성, 무인용 표현, 정의 색인 부재는 이 직접 경로로 좁히지 않는다.

구조 직접 경로가 없으면 한 번 계산한 `matcher.starts(question, scope)`에서 허용 문서,
조항 위치, 용어와 문서 내 정의 위치를 최대 3/8/6/8건으로 압축한다. 기존 첫 검색 계획
호출에 `navigation_context`로 제공한다. 이 값은 원문이나 법적 결론이 아닌 탐색 힌트이고
`citation_eligible=false`다. 같은 질문의 global/scoped 회수는 이 시작점 매칭 결과를
재사용한다. 계획 단계에 별도 모델 호출을 추가하지 않는다. 최종 답변은 현재 요청의
정확 원문 READ와 기존 인용 검증에만 의존한다.
문서가 특정되지 않았고 같은 정의 후보가 여러 문서에 넓게 퍼져 있으면 임의의 첫 목록을
제시하지 않고 `definition_candidates_ambiguous=true`로 표시한다.

기본 `SourceRecall`의 후보 읽기 범위는 여전히 조문 `article`이다. 이 변경만으로 모든
질문에서 항·호·목 단위 우선 읽기나 일반적인 정의 질의의 fulltext 생략이 이뤄지는 것은
아니다. 질문 맥락을 좁혀 찾는 첫 단계와 원문 읽기 크기 개선은 별개다.

## 검증·복구

구조 우선 계약 검사 29건 통과. 기존 전체 API 검사 1건은 작업 트리의 실험 모델 정책
파일과 엔진 pin 해시가 달라 엔진 실행 전 중단되어 이번 변경의 품질 판정에 포함하지
않았다. 새 frozen stage의 3,110개 엔진 파일 pin을 검증했다. 실제 공개 세대에서
`「증권의 발행 및 공시 등에 관한 규정」에서 '자기자본'은 어떻게 정의하나요?`가
정의 원문 source 1개로 해소되고, 탐색 맥락에는 같은 문서의 용어·정의 위치만 들어갔다.
`pipeline.py check --profile legal-rag`는 generation 34, Qwen3.8, HTTP health 200을
확인했다. 새 경로의 실제 Qwen 답변 품질·응답시간은 아직 측정하지 않았다.

고정 코드, 승인·검증 영수증은
`08_DEPLOYMENT/RELEASES/legal-agent-question-navigation-qwen38-20260930-r2/`에,
작업 stage는 `09_ARTIFACTS/AUDITS/20260930-question-navigation-main/stage-r2/`에 있다.
회귀 시 `semantic_runtime.control rollback --confirm-main`으로 이전 포인터를 새
generation으로 재선택한다. 실행 중인 기존 프로세스는 시작 때 선택한 코드를 쓰므로
새 릴리스를 쓰려면 해당 로컬 프로세스를 재시작해야 한다.

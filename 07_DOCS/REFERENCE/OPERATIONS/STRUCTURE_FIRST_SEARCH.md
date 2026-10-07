# 구조 원문 우선 검색 — 2026-09-29

사용자 요청으로 v5 MAIN 작업 코드의 검색 시작점을 저장 문서 구조에 연결했다.
명시 법령·내규명 또는 등록된 약칭과 조문 좌표가 유일하게 연결되면 해당 원문부터 읽는다.
법률/시행령의 같은 번호, 본문/부칙, 조·항·호와 가지조문을 구분한다.
원문 위치가 없거나 모호하면 기존 검색을 유지하며, 구조에서 읽은 원문이 질문에 부족해도
fulltext로 확장한다. 신규 모델·속도·검색 품질 비교 실험은 실행하지 않았다.

## 실행과 계약

`service.py` → `/v1/rag/ask` → `Pipeline` → `ServingLegalAgent` → v5 요청 세션이다.
`legal_agent/structure_query.resolve`가 요청에 허용된 문서명/약칭과
`source_unit.json`에 결속된 body 좌표를 대조한다. 제목·본문에서 조문을 만들어내지 않는다.
좌표 인덱스는 기존 immutable generation의 `stored_coordinates`를 기준으로 프로세스에서 재사용한다.
허용 source 집합은 같은 세대에서 검증된 matcher 위치 메타데이터로 구성한다.
범위 확인을 위해 `SourceMap.items()`로 전체 본문 JSON을 읽지 않는다.
명시 번호가 없는 경우에도 해당 문서의 실제 조문 표제가 질문에서 유일하게 일치하면 같은 경로를 쓴다.
공통 짧은 표제, 중복 표제, 부칙·별표·범위 질의나 해소되지 않은 문서명은 기존 탐색으로 남긴다.

### 원문 회수·선별 프로필

`bounded_source_selection_enabled=true`인 `BoundedSourceSession`:

1. 원질문의 문서·좌표/표제를 먼저 확인한다. 모든 명시 좌표가 확인되어야 좁은 회수를 시작한다.
2. 일치하면 검색어 계획 모델 호출과 global/scoped fulltext를 생략하고 `SourceRecall`이 해당
   source ID를 기존 READ로 확보한다. 원문 span·해시·세대·범위와 자동 참조 읽기 계약을 유지한다.
3. `source-triage`에 지정 조문의 실제 원문 전체를 전달한다. 기존 `issues/choices`에 이 경로만
   필수 `needs_fulltext:boolean`을 추가하며, 원질문의 모든 요구에 부족한 자료가 있는지 판단한다.
   선택은 법률 적용 승인이나 최종 답변 검토가 아니다.
4. 부족함·빈 선택·읽기 미완료·모델 문맥 한도 초과이면 기존 검색 계획 → global/scoped fulltext
   → 원문 선별·누락 복구로 한 번 확장한다. 처음 찾은 구조 source는 검색 후보에 보존한다.
5. 충분하면 기존 질문 요구 정리 → 작성 → 출처/outbox로 진행한다. 인사·안내·문서 목록 분기는 유지한다.

문맥 한도를 넘는 구조 원문을 임의 절단해 충분하다고 판단하지 않는다. 모델/형식 오류를 검색 부재나
안내 성공으로 바꾸지 않는다. 원문 회수 상한과 요청 전체 deadline·물리 호출 예산을 적용한다.

### 모델 도구 탐색 프로필

호환용 `bounded_source_selection_enabled=false` 경로도 `ObligationSession`의
첫 investigate 전에 같은 정확 원문을 읽는다. 첫 모델 입력에 원문과 `structure_first_search`를
전달하며 충분하면 선별·작성, 부족하면 참조/추가 검색하도록 안내한다. 이 경로에서 추가 도구
선택은 모델 판단이다. 후속 사용자 지시 통합에서는 GENOS 환경 기본을 true로 연결했다. 이전 false 설명은 변경 전 상태다.

## 기록과 배선

`STRUCTURE_QUERY_RESOLVED`는 MATCH/MISS, 문서·좌표, 원문 source ID, 해소 실패 이유를 보존한다.
bounded 재검색은 `STRUCTURE_QUERY_FULLTEXT_FALLBACK`에 최초 선별 판단과 이유를 남긴다.
Result의 `assembly.term_agent.structure_first_search`에서 해당 요청의 구조 일치와 재검색 여부를
확인한다. 모델 도구 탐색 경로의 첫 model view에도 실제 원문 준비 상태를 보존한다.
원질문은 변경하지 않으며 후보나 과거 답변을 정답으로 자동 승인하지 않는다.

신규 모듈과 호출 모듈은 소비 엔진 manifest 및 `PIPELINE.json` 코드 pin에 함께 결속한다.
데이터 스키마, 원문 세대, fulltext 색인, 외부 요청/결과 계약을 변경하지 않는다.
구조 우선 단독 구현에서는 활성 frozen 코드를 바꾸지 않았다. 후속 사용자 지시 통합으로 새 릴리스를 준비·선택한다.
현재 상태는 [통합 MAIN 기록](RAG_USER_DIRECTED_MAIN_20260929.md)을 따른다.
GENOS checkout 적용·Git push·코드서빙 새 리비전 배포·워크플로우 테스트는 별도 상태다.
이 변경만으로 워크플로우 Python 교체나 데이터 재구축은 필요하지 않다.

## 검증과 복구

`05_TESTS/CONTRACTS/test_structure_first_search.py`는 약칭/정식명·공백·가지조문·항,
복수 법령의 번호 결합, 요청 범위·모호한 약칭/표제·부분 일치·없는 조문·부칙·범위,
전체 원문 전달·문맥 한도·불충분 시 fulltext 확장·후보 보존·모의 답변 출처 발행과
모델 도구 탐색의 첫 원문 전달을 검사한다. 정확 구조 요청의 fulltext 0회는 합성 호출 계약이다.
실제 내부 모델의 충분성 판단·GENOS 속도·법률 답변 품질은 미확인이다.

검사 결과·변경 전 바이트·코드 pin 기록은
`09_ARTIFACTS/AUDITS/20260929-structure-first-rag/`에 보존한다.
복구는 신규 모듈의 호출을 제거하고 해당 변경 부분과 엔진 pin을 함께 되돌린다.
동시에 진행한 스트리밍·요청 분기 등의 후속 변경이 있으면 before 파일 전체를 덮어쓰지 않는다.

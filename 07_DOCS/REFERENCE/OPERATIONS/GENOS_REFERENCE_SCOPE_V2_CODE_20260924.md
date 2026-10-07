# 연결관계 로직 MAIN 작업 코드 반영 — 2026-09-24

## 상태

- `feature/legal_RAG` 작업 트리의 MAIN 실행 코드에 선택형 `reference-scope-v2` 빌드 경로를 추가했다. Git `main` 병합·commit·push는 이 작업에서 하지 않았다.
- 로컬 활성 릴리스 포인터와 기존 데이터 generation은 변경하지 않았다.
- **GENOS 코드스페이스 반입, NFS 새 세대 생성, 코드서빙 리비전 배포, 워크플로우 E2E는 아직 하지 않았다.** 이 저장소의 코드 변경을 GENOS 현장 적용으로 간주하지 않는다.
- 사용자가 확인한 현장 상태: 최신 MAIN 코드는 아직 GENOS에 배포되지 않았다. 따라서 현장 E2E는 먼저 기존 반입 코드·기존 구조화 세대의 결과로 기록한다.
- ADR-0530/0531의 공개 고정 사례는 연구 단계 `Proposed`, 인샘플이다. 전체 원문·모델 답변 품질과 GENOS 성능은 미확인이다.

## 실행 경로와 계약

`term_generation.build_generation`의 기본 `GENOS_REFERENCE_SCOPE_V2=0`은 기존 v4 탐색 색인을 만든다. 현재 GENOS의 기존 구조화/색인으로 질문부터 답변까지 E2E를 먼저 확인할 때 이 경로를 유지한다.

새 run ID로 `GENOS_REFERENCE_SCOPE_V2=1`을 명시하면 선택된 구조화 `source.sqlite`를 새 generation에 복사한 뒤 원문 블록과 기존 ID를 보존하면서 구조 앵커를 보강한다. `term_index.compile_index`가 `structure_anchor`와 `reference-scope-v2` 연결관계를 포함한 v5 탐색 색인을 만든다. 완성된 서빙 bundle은 `verify_assets`로 확인한다. `WorkSession`의 관계 탐색과 `READ`는 저장된 문자 범위와 원문 해시를 검증한 뒤 해당 범위만 전달한다. 알 수 없는 접미사나 구조에 없는 하위 마디는 정확한 연결로 승인하지 않는다.

빌드 환경값은 [설정 예시](../../../08_DEPLOYMENT/GENOS/pipeline.env.example)에 있다. 이 값은 **빌드 프로세스의 입력**이며 코드서빙 설정에 넣어 기존 DB를 바꾸는 스위치가 아니다. 기존 색인에 새 로직을 적용하려면 새로운 데이터 세대를 빌드하고 검증 후 선택해야 한다. 기존 구조화 세대·완료 색인은 보존한다.

## 로컬 확인

- WSL 개발 환경 검사 통과.
- 기존 참조 계약, 기존 관계의 범위 읽기, 새 v5 생성·`verify_assets`·문자 범위 읽기: 17개 테스트 통과.
- 더 넓은 문서 릴리스/탐색 검사 28개 중 25개 통과, 3개 실패. 실패는 용어 발견, RAW XML 통합의 용어 ID, 문서 순위 기대값이다. 이번 연결관계 변경과의 인과관계는 아직 분리 검증하지 않았다. 따라서 전체 회귀 통과로 보고하지 않는다.
- 실제 73,477개 source 전체 재구축과 GENOS 질문→답변 E2E는 아직 미실행이다. 기존 세대 E2E를 먼저 확인한 뒤 새 색인의 전체 실행·소비자 회귀를 확인한다.

## 수정 위치

- 원문 구조 마디·번호: `lawrag/core/structure/anchors.py`, `lawrag/core/reference_coordinate.py`, `lawrag/core/legal_coordinate.py`, `lawrag/core/structure/lawxml.py`, `lawrag/core/structure/proposers/hangul_jamo.py`, `lawrag/core/structure/lexicon/numerals.yaml`
- 빌드·색인·관계: `lawrag/pipeline/term_generation.py`, `semantic_runtime/term_index.py`, `semantic_runtime/term_references.py`, `semantic_runtime/term_references_legacy.py`
- 범위 소비: `semantic_runtime/reference_spans.py`, `semantic_runtime/multi_entry_navigation.py`, `semantic_runtime/work_navigation.py`, `semantic_runtime/structure_navigation.py`, `semantic_runtime/legal_navigation.py`

코드와 데이터 generation, Git push, GENOS 배포는 별도 상태로 기록한다.

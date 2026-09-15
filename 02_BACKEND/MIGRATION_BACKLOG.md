# 02_BACKEND 전환 상태

## CUTOVER 완료

- 편집 소스는 `02_BACKEND/lawrag`, 불변 배포 소스는 `GENERATIONS/20260904-code-v19`이다.
- MAIN promotion은 `lawrag.platform.main_promotion`, release activation은
  `lawrag.platform.release`, content snapshot은 `lawrag.runtime.content_snapshot`이 소유한다.
- 운영 retrieval-stage ledger를 `lawrag.runtime.retrieval_stage_ledger`로 이동했다.
- 실험 구현 19개를 `lawrag.research.experiments`, 레거시 연구 orchestration 14개를
  `lawrag.research.legacy_rag`로 격리했다.
- production의 `core.rag.experiments` import는 0건이고 code ship은 `lawrag.research`
  package를 포함하지 않는다.
- `core/rag` 최상위 호환 모듈은 106개에서 88개로 줄었고, 남은 모듈은
  `retrieval/evidence/reasoning/knowledge` 네 경계에 누락·중복 없이 귀속했다.
- 집중 회귀 210 passed, ontology CI 51 passed, GenOS 검색 smoke HTTP 200이다.

결정과 rollback 근거는 ADR-0185, 후속 저장소 정리는 ADR-0186이다. 활성 MAIN은
generation 5로 유지한다.

## ADR-0186 후속 정리 완료

- 신규 import를 위한 `core.rag.retrieval`, `core.rag.evidence`, `core.rag.reasoning`,
  `core.rag.knowledge` 경계를 추가했다.
- `_boundary.py`와 아키텍처 테스트가 모든 최상위 호환 모듈의 단일 소유권을 강제한다.
- 완료 ADR snapshot이 참조하는 기존 import 이름은 호환 표면으로 유지한다. 이 표면은 새
  연구 구현의 위치가 아니며 `lawrag.research` 재유입은 계속 금지한다.
- 연구 runner의 직접 `01_DATA/structure` 접근은 활성 release binding 접근으로 교체했다.
- 구형 dataset overlay sync와 임의 legacy tool 실행은 deny-by-default로 폐기했다.

불변 generation, 완료 ADR snapshot, promotion/apply/rollback receipt는 정리 대상으로
취급하지 않는다.

## ADR-0187 내부 구조 정규화 완료

- mutable 정리본은 `20260904-code-v19`로 발행하고 활성화했다. 운영 도구 target은
  `06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS`이며 MAIN은 generation 5를 유지한다.
- `LEGACY_SCRIPTS`, `LEGACY_TESTS`, `LEGACY_DOCS`, `LEGACY_ARTIFACTS` mutable 경로는
  제거했다. 이전 세대 안의 같은 이름은 rollback용 불변 증거라 보존한다.
- 내부 컨테이너 case와 예외는 `00_SYSTEM/INTERNAL_LAYOUT.json`이 강제한다.

## 비구조 후속 백로그

- Python 3.14.4 + Starlette 1.3.1 + httpx 0.28.1에서 동기 FastAPI `TestClient`가 최소
  앱에서도 deadlock된다. 의존성 조합을 고정하거나 async transport로 교체한 뒤
  `test_batch.py::test_API_가_라인업_실행_상태를_낸다`를 재실행한다.
- `test_legal_graph_v1.py`의 전체 120만 건 그래프 검증은 별도 장기 CI job으로 분리하고
  완료 receipt를 남긴다.
- ADR graph 재생성은 불변 legacy 계보의 `ADR-0158-experiment-v1/v2-candidate`를 현재
  ADR root에서 찾지 못한다. 완료 ADR을 고치지 말고 graph reader의 legacy-root 해석으로
  해결한다.
- `03_FRONTEND/APPS/experiment-studio`의 `npm audit` 결과 1 low·12 high advisory는
  의존성 호환성을 확인한 별도 보안 변경으로 처리한다.
- onsite/GenOS 호스트에 v19 코드를 실제 반입·재시작하는 작업은 로컬 폴더 정리와 분리해
  배포 승인 및 배포 receipt와 함께 수행한다.

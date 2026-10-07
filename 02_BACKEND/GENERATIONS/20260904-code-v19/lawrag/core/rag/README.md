# RAG package boundaries

`core.rag`의 기존 모듈 이름은 완료된 ADR snapshot과 외부 import를 깨뜨리지 않기 위한
호환 표면이다. 신규 코드는 다음 소유 경계를 통해 접근한다.

- `retrieval`: 색인, 검색, 확장, 회수 및 선택
- `evidence`: 좌표, 관계, 의미 저장소 및 관측
- `reasoning`: 법적 closure, 명제 판정 및 답변 조립
- `knowledge`: 승인된 규칙, 피드백 원장 및 lifecycle 제어

`_boundary.py`가 모든 최상위 Python 모듈의 단일 소유자를 선언한다. 아키텍처 검사는 누락,
중복 소유와 `experiments` 재유입을 거부한다. 물리 호환 모듈은 운영 동작이 아니라 import
안정성을 위한 것이며, 새 연구 구현은 `lawrag.research`에만 둔다.


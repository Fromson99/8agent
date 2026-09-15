# 02_BACKEND

`PIPELINE/`는 공통 엔진 실행기, `ENGINES/`는 명시적 버전 엔진이다. 선택 정본은 `00_SYSTEM/PIPELINE.json`이며 기존 receipt-bound GENERATIONS와의 이행 상태를 분리한다.

설치 가능한 mutable `lawrag` 소스를 둔다. import 이름은 항상 `lawrag.*`로 유지한다.
배포 시에는 이 소스를 직접 읽지 않고 `GENERATIONS/<generation>/lawrag`의 영수증 고정본을
사용한다.

Target modules: `contracts`, `ingestion`, `structure`, `observation`, `semantics`,
`graph`, `retrieval`, `feedback`, `runtime`, `api`, `deployment`.

현재 `core/rag` 호환 표면의 소유권과 완료된 전환 상태는
[`MIGRATION_BACKLOG.md`](MIGRATION_BACKLOG.md)에 기록한다. 완료 실험이 고정한 소스와
generation은 후속 정리에서도 제자리에서 보존한다.

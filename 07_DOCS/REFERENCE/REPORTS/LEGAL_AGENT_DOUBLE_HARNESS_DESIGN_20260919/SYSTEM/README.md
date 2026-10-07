# 더블하네스 시스템 구현 명세

개념·설계 이유를 정리한 기존 FINAL 다음 단계로, 실제 호출/상태 저장/배선/복구를 구체화한 부속 설계다.

| 파일 | 용도 |
|---|---|
| [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) | 파일·함수·SQL·모델/tool 계약·Pipeline 재실행·API 호환·장애 복구 |
| [journal.sql](journal.sql) | 요청별 SQLite 17개 테이블, 인덱스, 불변 영역 trigger |
| [interfaces.py](interfaces.py) | 신규 컴포넌트의 선언형 Python Protocol |
| [protocol.schema.json](protocol.schema.json) | 탐색 변경안·초안·검토·도구·설정의 JSON Schema |
| [protocol-examples.json](protocol-examples.json) | 합성 메시지 예시. 실제 모델 출력 아님 |
| [domain.example.json](domain.example.json) | DomainSpec의 검사·근거·종료 정책 |
| [profile.example.json](profile.example.json) | AgentProfile의 실행 예산 예시. 배포 모델 미지정 |
| [wiring-plan.json](wiring-plan.json) | 기존 Pipeline profile/slot/engine에 연결할 blueprint |
| [sources.json](sources.json) | 기존 코드·스키마·보고서의 읽기 시점 hash |
| [validate_system_design.py](validate_system_design.py) | SQL/schema/참조 검증. 제품·모델 호출 없음 |
| [validation.json](validation.json) | 이번 검증 출력 |
| [SELF_REVIEW.md](SELF_REVIEW.md) | 자체 검토, 보완 사항, 아직 검증하지 않은 경계 |

저장소 `.venv/bin/python -B`로 검사기를 실행한다. 결과는 stdout에 JSON으로 출력된다. 제품 구현, 모델 품질 실험, GENOS 실행, 활성 포인터 변경은 수행하지 않았다.

# 00_SYSTEM

저장소 전체의 아키텍처, 경로, 스키마, 보안, 이행 계약을 관리한다.
업무 코드나 실행 데이터를 두지 않는다.

- `ARCHITECTURE.md`: 4축 기반 목표 아키텍처
- `WORKSPACE.json`: canonical root와 v1 호환 경로
- `SCHEMAS/`: 데이터·소스셋·숏컷·레이아웃·릴리스 기계 계약
- `MIGRATION/`: 단계별 실행계획, 이행 차단 목록, root 파일 분류·hash 원장

현재는 `bridge` 단계다. 기존 lowercase 경로는 읽기 호환을 위해
남아 있지만, 새 최상위 영역은 반드시 번호+대문자 이름을 사용한다.

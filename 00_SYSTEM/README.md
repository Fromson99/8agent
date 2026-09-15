# 00_SYSTEM

- `PIPELINE.json`: 파이프라인 단계·엔진 선택·데이터 계약의 상위 SSOT
- `LEGAL_SCHEMA.json`: 법률 의미 스키마의 버전/hash와 구형 형식 이행 상태
- `DATA_MODEL.md`: 단일 의미 계약의 설명

저장소 전체의 아키텍처, 경로, 스키마, 보안, 이행 계약을 관리한다.
업무 코드나 실행 데이터를 두지 않는다.

- `ARCHITECTURE.md`: 4축 기반 목표 아키텍처
- `WORKSPACE.json`: canonical root와 활성 세대 결속
- `INTERNAL_LAYOUT.json`: 내부 컨테이너 이름·예외·퇴역 경로 기계 계약
- `SCHEMAS/`: 데이터·소스셋·숏컷·레이아웃·릴리스 기계 계약
- `MIGRATION/`: 단계별 실행계획, 이행 차단 목록, root 파일 분류·hash 원장

현재 작업 트리는 v2-only다. 사람이 탐색하는 컨테이너는 `UPPER_SNAKE_CASE`,
Python 패키지·npm 앱 ID는 언어 관례의 소문자, 세대·릴리스·ADR 식별자는 원형을 유지한다.

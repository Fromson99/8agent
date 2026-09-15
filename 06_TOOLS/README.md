# 06_TOOLS

얇은 CLI만 둔다. 재사용 로직은 `lawrag` 패키지로 옮기고 CLI는 인자 파싱과 출력만
담당한다.

`run_tool.py`는 `ACTIVE_TOOLS.json`에 등록된 운영 도구만 receipt-bound generation에서
실행한다. 단, `adr_structure.py`는 사용자 변경 실험 정책을 반영하기 위해
`COMMANDS/adr_structure.py` 작업 코드를 실행한다. 다른 도구의 불변 세대는 유지한다.

- `COMMANDS/`: 현재 운영 CLI 원본
- `EXPERIMENTS/ADR/`: ADR 번호에 결속된 재현 도구
- `EXPERIMENTS/RAG/`: `CLAIMS`, `DEFINITIONS`, `GRAPH`, `HAIKU`, `PROVISO`,
  `RETRIEVAL`, `GENERAL` 기능 축으로 나눈 RAG 분석·평가 도구
- `EXPERIMENTS/DATA/`: 데이터 구조 변환·검증 도구
- `EXPERIMENTS/DOCUMENTS/`: 보고서·도식 생성 도구
- `EXPERIMENTS/EVALUATION/`: 비-RAG 평가·골든셋 도구
- `EXPERIMENTS/OPERATIONS/`: 퇴역 운영 흐름의 재현 도구
- `MIGRATION/`: 구조 이행 전용 도구
- `AUDIT/`: 정적 감사 도구
- `GENERATIONS/`: 불변 배포 세대

운영 진입점은 항상 `06_TOOLS/run_tool.py`를 거친다.

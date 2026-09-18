# 07_DOCS

현행 아키텍처·도메인·운영·API 문서를 둔다. ADR은 `04_EXPERIMENTS`,
불변 세대와 폐기 원본은 `99_ARCHIVE`에 둔다.

`REFERENCE/` 아래 문서는 `ARCHITECTURE`, `OPERATIONS`, `RAG`, `EXPERIMENTS`,
`REPORTS`, `AUDITS`, `EXAMPLES`, `TASKS`, `ASSETS`, `ARCHIVE`로 분류한다.

- [과거 RAG 테스트: 모델·프롬프트별 실제 답변과 판정 기록](REFERENCE/REPORTS/RAG_TEST_REVIEW/README.md) — ADR-0056·0058·0188의 답변 1,128건과 당시 판정 근거.

- [백로그](BACKLOG.md) — 후속 작업·실험 아이디어와 구현 대기 설계.
- [개념 정의·적용 범위 작업 하네스](REFERENCE/OPERATIONS/TASK_HARNESS.md) — DB 정의·후보 검토·근거 검토·완료조건을 기존 RAG에 연결한 선택형 구현. 모의 계약 검사, 운영 반영·실제 모델 품질은 미검증.

- [여러 기관의 용어집 통합 설계](REFERENCE/ARCHITECTURE/MULTI_SOURCE_GLOSSARY.md) — 일상표현·기관별 정의·문서 연결; 의미 연결은 설계안. 공개 사전 수집은 별도 구현.
- [공개 용어집 수집 결과](REFERENCE/REPORTS/PUBLIC_GLOSSARY_COLLECTION_20260912.md) — 원천별 원문·항목 확보와 미완료 범위.
- [용어 지식그래프 확장·탐색 절차 재사용 검토 보고서](REFERENCE/REPORTS/GLOSSARY_LEARNING_AND_NAVIGATION_REUSE_20260916.md) — 사용 중 표현·용어 발견, 조건에 따른 탐색 절차 재사용, 구현안·위험·검증·단계별 도입. 설계 제안이며 구현·실험·MAIN 반영은 미실행.
- [구현 설계 보고서 DOCX](../09_ARTIFACTS/REPORTS/DOCUMENTS/금융법률_지식그래프_구현설계_보고서_20260916.docx) · [독립 감독 검토서 DOCX](../09_ARTIFACTS/REPORTS/DOCUMENTS/금융법률_구현설계_감독검토서_20260916.docx) · [검토 원본](REFERENCE/REPORTS/GLOSSARY_NAVIGATION_DESIGN_REVIEW_20260916.md) — 실제 연결 시나리오, 조건부 예상치·산식, 권한·버전·기록 계약의 선행 조건.

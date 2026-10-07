# 07_DOCS

- [2026년 10월 7일 누적 개발과 Git 푸시 상태](REFERENCE/OPERATIONS/GIT_WORK_STATUS_20261007.md) — 구현·선택된 로컬 MAIN·이후 작업본·실험 재현 소스·GENOS 현장 미확인 범위를 구분. 현재 작업본 계약 138개 통과/1개 실패와 채팅·NFS 관련 48개 통과를 기록.

- [법령별 후보 탐색과 부모 범위 읽기 구현](REFERENCE/REPORTS/LAW_GROUPED_NAVIGATION_DESIGN_20261006/IMPLEMENTATION.md) — 새 소유 본문 색인에 법령·조별 페이지, 모델의 법령 선택 이유, 부모·형제 READ, 다른 법령/재검색·SQL 재개를 연결. 사용자 후속 지시에 따라 미해결 필수 연결도 완료 허용하며 상태·경고를 보존. 작업 코드 구현이며 MAIN/GENOS 전환은 별도. [초기 설계](REFERENCE/REPORTS/LAW_GROUPED_NAVIGATION_DESIGN_20261006/DESIGN.md)는 이전 완료 정책의 역사 자료.

- [내부 법률 검색 스킬 v1](../00_SYSTEM/LEGAL_AGENT/skills/internal-legal-search/SKILL.md) · [유지·보강·제외 및 적용 설계](../00_SYSTEM/LEGAL_AGENT/skills/internal-legal-search/references/adoption.md) · [실패·공개 자료 추적표](../00_SYSTEM/LEGAL_AGENT/skills/internal-legal-search/references/failure-map.md) — 최신 ADR0508까지 반영한 제품용 지침. 정적 검증 완료. 격리 후보의 실제 연결·Gemma 비교는 [ADR0509](../04_EXPERIMENTS/ADR/ADR-0509-gemma-search-skill-harness-paired/README.md)에 기록. 최종 답변 완성 개선 없음, MAIN 미반영.

- [내부 법률 데이터 검색 전략 보강 설계](REFERENCE/REPORTS/LEGAL_SEARCH_SKILL_DESIGN_20260922/README.md) — 선택된 v5와 작업본을 구분해 유지·보강·축소 대상을 정리. 검색 결과 전달·질의 선택·중복 호출 개선의 코드 연결, 공개 skill 적용 범위, 검증·비용·롤백 계획. 설계안이며 구현·실험·MAIN 변경 없음.

- [Gemma 에이전트 판단 보강계획](REFERENCE/REPORTS/GEMMA_RAG_MODIFICATION_PLAN_20260921/README.md) — 질문 요구 유지, 다음 행동·적용 규칙 선택, 조건·예외 보존, 주장별 유보와 구체적 교정을 강화하는 수정 순서·코드 연결·검증 기준. 설계안이며 구현·실험·MAIN 전환 미실행.

- [LLM 능력 종합 리포트: 무엇을 잘하고 못했는가](REFERENCE/REPORTS/LLM_CAPABILITY_SYNTHESIS_20260921/README.md) — CM51·어려운 문제10의 기존 기록으로 명시 조건 추출, 적용 규칙 선택, 논리·예외 보존, 불확실성, 도구 상태, 자기검토를 정리. 모델 순위 대신 에이전트 판단의 강점·약점과 보강 대상을 구분한 문서 종합이며 추가 실험·제품 수정 없음.

- [원문 탐색·선택·답변 전체 흐름 재설계](REFERENCE/REPORTS/RAG_SOURCE_WORKFLOW_REDESIGN_20260921/DESIGN.md) — 모델/서버 책임, 조 선택과 강조 분리, 오류 복구·완료·게시 계약. 기존 엣지케이스40개와 전체 연결8개 수용 시나리오 및 자체 검토. 설계 제안이며 구현·실험·MAIN 변경 없음.

- [원문 탐색·선택·게시 엣지케이스 40개](REFERENCE/REPORTS/SOURCE_TIERS_EDGE_CASES_20260921/README.md) — ADR-0488 실행·코드 대조. 실제 관측과 추가 점검 조건, 오류 안내·재시도·부재 표시 기준을 구분한 원장. 제품 수정·재실행 없음.

- [원문 관계와 사람 검토 스키마](REFERENCE/ARCHITECTURE/SOURCE_RELATION_REVIEW_SCHEMA.md) — CM003 explicit link 최소 구현·READ 검증, 관계8유형·제안/검토/릴리스 분리. 자동 LLM 추출·사람 승인 서비스는 후속 설계.


- [원문 관계 추적과 결정론적 최종 출처표 설계](REFERENCE/ARCHITECTURE/SOURCE_RETRIEVAL_AND_PROVENANCE.md) — 위임·단서·준용·분기·비율 참조의 원문 확보 우선, 최종 사용 span에서 서버가 출처표 생성. 설계 제안이며 구현·실험·MAIN 변경 없음.

현행 아키텍처·도메인·운영·API 문서를 둔다. ADR은 `04_EXPERIMENTS`,
불변 세대와 폐기 원본은 `99_ARCHIVE`에 둔다.

`REFERENCE/` 아래 문서는 `ARCHITECTURE`, `OPERATIONS`, `RAG`, `EXPERIMENTS`,
`REPORTS`, `AUDITS`, `EXAMPLES`, `TASKS`, `ASSETS`, `ARCHIVE`로 분류한다.

- [과거 RAG 테스트: 모델·프롬프트별 실제 답변과 판정 기록](REFERENCE/REPORTS/RAG_TEST_REVIEW/README.md) — ADR-0056·0058·0188의 답변 1,128건과 당시 판정 근거.

- [새 법률 질의 시스템 legal_agent 구조](REFERENCE/ARCHITECTURE/LEGAL_AGENT_SYSTEM.md) — 새 패키지 모듈·부품 계약·GenOS 대리(Qwen3.5-122B FP8)·짓는 순서. 조립 단계가 ADR-0465 후보로 측정 중, MAIN 불변.
- [법률 질의 에이전트 하네스 설계 v2](REFERENCE/RAG/LEGAL_AGENT_HARNESS.md) — 앞단 분류·도메인 하네스/에이전트 프로파일 분리·서버 카드·답변 전 종합 관문·판례 다리/근거 분리·항 단위 읽기·피드백 루프. ADR-0462 실측(현재 26/51, 상한 44/51) 반영 설계안, 미구현.

- [백로그](BACKLOG.md) — 후속 작업·실험 아이디어와 구현 대기 설계.
- [개념 정의·적용 범위 작업 하네스](REFERENCE/OPERATIONS/TASK_HARNESS.md) — DB 정의·후보 검토·근거 검토·완료조건을 기존 RAG에 연결한 선택형 구현. 모의 계약 검사, 운영 반영·실제 모델 품질은 미검증.

- [여러 기관의 용어집 통합 설계](REFERENCE/ARCHITECTURE/MULTI_SOURCE_GLOSSARY.md) — 일상표현·기관별 정의·문서 연결; 의미 연결은 설계안. 공개 사전 수집은 별도 구현.
- [공개 용어집 수집 결과](REFERENCE/REPORTS/PUBLIC_GLOSSARY_COLLECTION_20260912.md) — 원천별 원문·항목 확보와 미완료 범위.
- [용어 지식그래프 확장·탐색 절차 재사용 검토 보고서](REFERENCE/REPORTS/GLOSSARY_LEARNING_AND_NAVIGATION_REUSE_20260916.md) — 사용 중 표현·용어 발견, 조건에 따른 탐색 절차 재사용, 구현안·위험·검증·단계별 도입. 설계 제안이며 구현·실험·MAIN 반영은 미실행.
- [구현 설계 보고서 DOCX](../09_ARTIFACTS/REPORTS/DOCUMENTS/금융법률_지식그래프_구현설계_보고서_20260916.docx) · [독립 감독 검토서 DOCX](../09_ARTIFACTS/REPORTS/DOCUMENTS/금융법률_구현설계_감독검토서_20260916.docx) · [검토 원본](REFERENCE/REPORTS/GLOSSARY_NAVIGATION_DESIGN_REVIEW_20260916.md) — 실제 연결 시나리오, 조건부 예상치·산식, 권한·버전·기록 계약의 선행 조건.

- [원문 선택 흐름 구현·Qwen 실험 결과](REFERENCE/REPORTS/RAG_SOURCE_WORKFLOW_IMPLEMENTATION_20260921/README.md) — 단계별 후보5개·최신 계약28개, CM018 검토/기준답1/1·필수출처1/2. 연구 후보이며 MAIN 미승격.

- [Gemma 판단 보강 전후 실제 실행 확인](REFERENCE/REPORTS/GEMMA_OBLIGATION_PROBE_20260922/README.md) — 공개 7문항 전후 실행, 요구문 한 글자·검토 ID 문제 및 실제 판단 관측. 자동 점수 신뢰 한계 포함.

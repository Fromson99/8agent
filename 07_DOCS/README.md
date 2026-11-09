# 07_DOCS

<!-- MAIN104_SQL_FOLLOWUP -->
**2026-10-27 — MAIN105 반영·실제 서비스 확인 완료:** [전체 반영·실제 실행·온톨로지 후속](REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MAIN_SQL_AND_ONTOLOGY_FOLLOWUP_20261027.md). 최초211초 원인의 MAIN104 SQL 수정에 반복 원문 확인 재사용과 네 연결 TEMP VIEW의 ID 점조회를 더했다. 보관응답1회 재생의 동일 계측35화면736.500→93.718초(87.275% 감소), 원문·행동·최종 답변 동일, 새 모델 호출0회다. 신규237조건·관측보조1,345조건을 구분한 ADR1081 검증 후 MAIN105 `navigation-validation-20261027-r1`을 선택했고 실제 서비스19확인(HEALTH·모의 HTTP1회·새 모델0회)이 통과했다. 작업 코드 통합에서 새4검사 통과, 기존7실패는 변경 전후 동일하다. 온톨로지는1074 부분실패→1077 상태 전환 수리→MAIN105 결합1079 실모델1셀/10호출을 완료했다. 두 원문의 판단 보존을 확인했지만 근거 연결 보완1회·제한 답변으로 품질 효과는 미인증이다. MAIN105 최종 누적본433파일·첨부4개를 삼성메일 SENT `1a17ae4c6976a0f7`로 발송·확인했다. 설치144명령·SQL18·상태13쌍을 통과했으며 MAIN104 첨부를 대체한다. P0~P4 전체 구현·전체 응답시간 개선·법률 품질·온톨로지 MAIN·GENOS 현장 배포 완료로 확대하지 않는다. 아래 이전 상태 기록과 구분한다.
<!-- /MAIN104_SQL_FOLLOWUP -->

**2026-10-27 — 211초 원인·최적화 확인:** [상세 측정과 결과](REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NAVIGATION_211S_ROOT_CAUSE_20261027.md). 정의 연결 조회의 전체 참조 VIEW 조립과 권한 ID 목록 반복이 원인이었다. 동일 계측의8개 대응 구간236.744→19.891초(91.598% 감소), 원래 화면·행동·전달 원문8/8 일치, 신규 모델 호출0회. 당시 SQL 두 수정은 작업 코드에 통합했고 선택 MAIN103·GENOS 배포는 유지했다. 이후 MAIN 반영 상태는 문서 상단 최신 기록을 따른다. 초기 준비·전체 응답시간·온톨로지 품질·GENOS 속도와 구분한다. 아래2026-10-26 상태는 선행 단계 기록이다.

**2026-10-26 성능 구현·실험 상태:** [상세 결과](REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NON_MODEL_LATENCY_IMPLEMENTATION_RESULT_20261026.md) · [전체 계획](REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NON_MODEL_LATENCY_OPTIMIZATION_PLAN_20261026.md). 격리 후보에 P0 계측·P1 일부와 온톨로지 재표시 오류 수정을 구현했다. 반복 스키마 검사96.17% 감소는 국소 비교이며 전체 서비스 개선율이 아니다. 초기 준비17.605초의98.266%를 이름 있는 구간에 귀속했고 연결 매칭·구조 결속10.676초가 가장 컸다. 실모델1회는 불완전 출력/연속 공백으로 중단, 온톨로지 효과와 전체 최적화는 미확인이다. P2/P3/P4·기본 작업 코드 통합·MAIN103·GENOS 반영은 미완료다. 과거 실험과 실패는 보존한다.

<!-- ADR1066_LIVE_STATUS -->
**2026-10-26 실제 모델 관찰: 부분 중단.** 사전 동결한 3문항×3조건 중 첫 문항 A0/A1은 제한 답변, A2는 원문 재표시의 상태 결속 오류로 중단했다. 나머지6셀은 미실행이다. 제품27호출·관찰 비용$0.17853620·제품 실행 합계762.10초, 채점 모델0회다. 관찰한 행동 응답19회에서 이전 필수 항목 누락과 입력 문자 차단은 재현되지 않았고, A1/A2 승인 묶음 실제 전달도 확인했다. 전체 성공·법률 정답·온톨로지 개선 인증은 아니다.

같은 원문 카드의 `presentation_id` 갱신이 전체 source hash를 바꿔 동일 온톨로지 페이지의 내용 변경으로 오인됐다. 별도로 조문 선택과 목적 불일치, 탐색 화면 구성 지연, 구형 gate의 evidence-ID 카드 감사 호환 문제가 남았다. 원문 검증을 끄지 않으며 결과 후 코드·점수를 수정하지 않았다. MAIN103·GENOS·운영 골드는 미변경이다. [결과·원인·원시 기록](../04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/POST_RUN_DIAGNOSIS.md). **아래 구현 당시의 “실모델0회·미실행” 표기는 과거 시점 기록이다. 현행 상태는 이 관찰을 따른다.**
<!-- /ADR1066_LIVE_STATUS -->


- [증분처리 — 법제처 규정 문서 증분 처리](REFERENCE/OPERATIONS/증분처리.md) — 바뀐 조문만 새 판본, 옛 판본은 시행 구간만 닫음. 흐름·상태, 계보 유지 판정 7종, 부칙 기반 조문별 시행일, 게이트·승인, 숨김 색인 후 한 트랜잭션 활성화, 새 표 10개(개발·운영 같은 이름)와 기존 Gold 연결 판단, 실문서 검증(공식 Y 68조문 누락0), 남은 일. 2026-11-06 로컬 작업 코드 구현·검증이며 개발·운영 DDL·Dataiku 현장·GENOS 반영은 미실시.

- [온톨로지 MVP 행동별 최소 응답 계약](REFERENCE/ARCHITECTURE/ONTOLOGY_V4/ACTION_CHOICE_CONTRACT_20261026.md) — 모델의 행동·대상·필요한 판단과 서버의 고정값 조립을 분리하고 정상·전체 보완을 같은 양식으로 연결. 입력 문자 차단 해제와 실제 구현·검사는 [최신 상태](REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MVP_EXECUTION_REPAIR_STATUS_20261026.md)에서 확인. 후보 구현과 MAIN103·GENOS 적용을 구분.

- [골드 레이어·메타마이너 규약과 원본 사진](REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/README.md) — 표준단어·논리명·물리명·유형별 용어, 도메인·코드값, 표준 신청·승인 절차와 골드 메타 작성 규약. [테이블 목록·Bizmeta·등록 대상·컬럼 정의 양식](REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/TABLE_SCHEMA_WORKBOOK.md)과 추가 사진7장 포함. 사용자 제공 사진 총27장 원본·내용 대응·SHA-256 보존.

- [온톨로지 v4: 조문 경로 조립·대화 축적·변경 영향](REFERENCE/ARCHITECTURE/ONTOLOGY_V4.md) — 2026-10-24 사용 중 필요·선택·정정 관찰과 [멀티턴 Legal agent](REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MULTITURN_LEGAL_AGENT.md) 설계 반영. 확인 답·미확인·경로 안내·행동 기록을 다음 턴에 연결하고 제어·저장·응답·화면·재개를 통합 교체. 기존 경로 컴파일·원문 확보·조건 변경 기능 유지. 설계 저장이며 제품 구현·MAIN·GENOS 반영은 별도.

- [온톨로지 v3 문서 안내](REFERENCE/ARCHITECTURE/ONTOLOGY_V3.md) — 방향·지식 모델·근거 기억·새 연결·설명/평가·구현 단위·DB 설계를 주제별 문서로 연결하는 목차. 기존 코드 검토와 DDL·조회 SQL·이행/검증 문서 포함.

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

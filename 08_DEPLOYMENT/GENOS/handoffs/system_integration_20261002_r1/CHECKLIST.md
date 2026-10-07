# 전체 시스템 통합·GENOS 이관 체크리스트

2026-10-02. **72개 항목. 최신 MAIN 작업 코드에 반영했다.** 현재 Git 브랜치는 feature/legal_RAG이며 Git main 병합과 활성 r3/generation37 전환은 하지 않았다. 원본 포함은 보존을 뜻하며 실제 모델/현장 전수 검증을 뜻하지 않는다.

## 기준·보존

| ID | 점검 항목 | 상태 | 근거(저장소 기준) |
|---|---|---|---|
| BASE-01 | 전체 MAIN의 RAW→구조화→용어·정의·참조→색인→RAG→피드백 책임 | 대조 완료 | `00_SYSTEM/ARCHITECTURE.md` |
| BASE-02 | 활성 r3 generation37와 작업 코드의 차이 | 대조 완료 | `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json` |
| BASE-03 | 기존 미커밋 변경과 최초 파일 해시 보존 | 완료 | `09_ARTIFACTS/MIGRATIONS/20261002-system-integration/before.json` |
| BASE-04 | 최신 MAIN 전체 코드1923개 보존·누적 구현 통합 | 통합 완료·전체 코드 1923개 대조 | `09_ARTIFACTS/MIGRATIONS/20261002-system-integration/full-code-inventory.json` |
| BASE-05 | 완료 ADR0590~0613의 계보·실패·원문 응답 보존 | 24개 ADR 보존·동결 검사180건 변경0 | `09_ARTIFACTS/MIGRATIONS/20261002-system-integration/history-inventory.json` |
| BASE-06 | 코드·데이터·설계·현장 상태를 별도 기록 | 별도 기록 완료 | `07_DOCS/REFERENCE/OPERATIONS/SYSTEM_MEMORY_INTEGRATION_20261002.md` |

## MAIN 구축·기존 기능

| ID | 점검 항목 | 상태 | 근거(저장소 기준) |
|---|---|---|---|
| MAIN-01 | RAW 반입·문서 ID·버전·원문 불변 계약 | 원본 포함 | `01_DATA/README.md` |
| MAIN-02 | PDF 전처리 청크·Docling·VLM 구조화 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/GENOS_PREPROCESSOR_PARSING.md` |
| MAIN-03 | DOCX와 형식별 구조화·실패 상태·재개 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md` |
| MAIN-04 | 선택 성공 문서 통합·중복 원문 충돌 검사 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/GENOS_RELEASE_STAGES.md` |
| MAIN-05 | 용어 corpus replace·기존/신규 후보 검토 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md` |
| MAIN-06 | 10월1일 의미 검토 OFF/ON·벌크 R2·중단/재개 | 현행 인계 자료 포함 | `GENOS.md` |
| MAIN-07 | 문서–용어 출현·정의·명시 참조 연결 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md` |
| MAIN-08 | 명시 참조 LLM 해소·범위/근거 검증 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/REFERENCE_RESOLUTION.md` |
| MAIN-09 | 구축 감사 원장과 서빙 navigation 분리 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/NAVIGATION_STORAGE.md` |
| MAIN-10 | PeCab fulltext 구축·검색 세대 결속 | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/GENOS_PECAB_REQUEST_ROUTING_20260929.md` |
| MAIN-11 | 내규/외규 접두어·팀/문서 범위 교집합 | 모의 계약 통과 | `05_TESTS/CONTRACTS/test_source_prefix_routing.py` |
| MAIN-12 | 인사·안내·목록·내용 요청 분기 | 모의 계약 통과 | `05_TESTS/CONTRACTS/test_request_routing.py` |
| MAIN-13 | 구조 원문 우선과 부족 근거 fulltext 확장 | 모의 계약 통과 | `05_TESTS/CONTRACTS/test_structure_first_search.py` |
| MAIN-14 | 원문 선별·누락 복구·완독 검증 | 모의 계약 통과 | `05_TESTS/CONTRACTS/test_bounded_source_selection.py` |
| MAIN-15 | 모델 형식·교차 필드 오류 수정·예산 유지 | 모의 계약 통과 | `05_TESTS/CONTRACTS/test_model_decision_repair.py` |
| MAIN-16 | 질문 의무 추적·최종 검토 설정·원문 인용 검증 | 원본 포함 | `02_BACKEND/semantic_runtime/legal_agent/question_obligations.py` |
| MAIN-17 | 모델 실제 수신 원문·thinking·공유 요청 로그 | 원본 포함 | `02_BACKEND/semantic_runtime/request_report.py` |
| MAIN-18 | 답변 SSE·숫자 참조 표시·진행 UI | 원본 포함 | `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py` |
| MAIN-19 | 데이터/모델 환경 분기·warmup·동시 요청 정책 | 원본 포함 | `service.py` |
| MAIN-20 | 피드백 후보·action-memory·legal_llm_wiki·retire overlay | 원본 포함 | `07_DOCS/REFERENCE/OPERATIONS/LEGAL_LLM_WIKI.md` |
| MAIN-21 | 선택형 glossary learning·task harness·golden 평가 | 원본 포함 | `00_SYSTEM/PIPELINE.json` |
| MAIN-22 | 단독 영업일 질문의 형태소 오분석과 용어 시작점 누락 | 기존 문제·미해결 | `09_ARTIFACTS/MIGRATIONS/20261002-system-integration/existing-build-check.log` |

## 멀티턴 통합

| ID | 점검 항목 | 상태 | 근거(저장소 기준) |
|---|---|---|---|
| MEM-01 | 질문 원장과 최종 경험 온톨로지 구분 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-02 | 한 질문 묶음 안의 반복 정정·최초 조건 복원 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-03 | 현재 사실과 과거 이력의 모델 입력 분리 | 기존 검증 계승 | `04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority` |
| MEM-04 | 12개 닫힌 작업 방법·서버 단계 결정 | 작업 코드 반영 | `02_BACKEND/semantic_runtime/legal_agent/memory_methods.py` |
| MEM-05 | RAG 7단계 부분 재실행과 현재 head 전환 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-06 | 추가 검색 신호→RECALL/READ/SELECT 재진입 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-07 | 재진입 이전 선택·사유 보존과 1회 한도 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-08 | 재실행 실패 시 이전 정답 재사용 차단·PENDING 복구 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-09 | 현재 답변의 표 변환만 COMPOSE 재실행 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-10 | 실제 정정 이벤트로 이유·이력 조회 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-11 | 사용자 최종 확인 때만 하나의 경험 묶음 게시 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-12 | 정정 전 경험 RETIRED·감사 이력 보존 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-13 | 새 대화 재사용 시 현재 사건으로 판단 노드 재결속 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-14 | 사용자·팀·문서·세대가 다르면 재사용 거부 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-15 | 잘못 찾은 경험의 wiki 연결만 수정 | 기존 구현 포함 | `02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py` |
| MEM-16 | 읽은 자료/채택 근거/인용·claim SUPPORTED_BY 구분 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-17 | 중복 request ID·CAS 충돌·늦은 결과 처리 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-18 | 기존 실험 SQLite 자동 적재 금지·새 v2 저장소 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| MEM-19 | 빈 근거·의미 판단 오류의 완전 해결 | 미완료 | `04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority/artifacts/final-findings.json` |
| MEM-20 | 무제한 긴 대화의 계층 조회·문단 anchor 정정 | 미구현 설계 보존 | `07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_MEMORY_MULTITURN_DESIGN_20261001.md` |
| MEM-21 | 한 턴 모델 호출·수정·시간 예산 공유와 종료 | 작업 코드 반영·모의 계약 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |

## 온톨로지 본 설계

| ID | 점검 항목 | 상태 | 근거(저장소 기준) |
|---|---|---|---|
| ONT-01 | 승인된 도메인 개념·관계·방법·경로 catalogue | 미구현 설계 보존 | `07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_ONTOLOGY_CONTROL_DESIGN_20261001.md` |
| ONT-02 | 각 판단에 원문·전제·도메인 proof 강제 | 미구현 설계 보존 | `00_SYSTEM/SCHEMAS/legal-agent-domain-journal-v1.draft.sql` |
| ONT-03 | native journal v6와 publication/recovery 연결 | 미구현 설계 보존 | `07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_ONTOLOGY_CONTROL_DESIGN_20261001.md` |
| ONT-04 | 용어집 compile·catalogue 버전 변경 시 경험 재검토 | 미구현 설계 보존 | `07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_ONTOLOGY_CONTROL_DESIGN_20261001.md` |
| ONT-05 | 일반 법률 지식 승인과 개인 경험 확인 구분 | 작업 코드 반영 | `02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py` |
| ONT-06 | DB 직접 수정·공통 지식 승인 UI | 사용자 별도 범위 | `07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_MEMORY_MULTITURN_DESIGN_20261001.md` |

## 입구·검증·이관

| ID | 점검 항목 | 상태 | 근거(저장소 기준) |
|---|---|---|---|
| SHIP-01 | service가 memory 요청의 세션/사용자 식별자 보존 | 작업 코드 반영 | `service.py` |
| SHIP-02 | 신뢰된 workflow 서명·서버 팀 문서 범위 검증 | 통합본 검사 통과 | `05_TESTS/CONTRACTS/test_memory_runtime_v2.py` |
| SHIP-03 | 식별자 정규화 충돌·익명 세션 공유 방지 | 작업 코드 반영 | `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py` |
| SHIP-04 | 서명·인증값을 모델/메모리 기록에서 제외 | 작업 코드 반영 | `02_BACKEND/semantic_runtime/app.py` |
| SHIP-05 | 실제 studio 사용자·세션 필드의 신뢰 경계 | GENOS 현장 확인 필요 | `GENOS.md` |
| SHIP-06 | 워크플로우 memory 비활성 시 기존 SSE 경로 유지 | 모의 계약 통과 | `05_TESTS/CONTRACTS/test_memory_adapters_v2.py` |
| SHIP-07 | 통합 코드·엔진·PIPELINE 해시 재결속 | 반영 | `00_SYSTEM/PIPELINE.json` |
| SHIP-08 | 일반 계약·회귀 검사 및 정확한 실행 결과 보존 | 292개 중290통과·기존 실패2 재현 | `09_ARTIFACTS/MIGRATIONS/20261002-system-integration/working-main-contracts.log` |
| SHIP-09 | 최종 ZIP/CODE_MANIFEST·데이터 제외·원본 동일성 검사 | 1929파일 ZIP·작업 코드 전체 해시 일치 | `08_DEPLOYMENT/GENOS/handoffs/system_integration_20261002_r1/CODE_MANIFEST.json` |
| SHIP-10 | ~/DEV 백업→적용→동일성 검증→재실행→롤백 | 로컬 적용·재실행·복구 검증 통과 | `09_ARTIFACTS/MIGRATIONS/20261002-system-integration/installer-validation.json` |
| SHIP-11 | python3 명령·지속 로그·실패 상태 기록 | 지속 로그·종료 상태 인계 | `08_DEPLOYMENT/GENOS/handoffs/system_integration_20261002_r1/RUN.sh` |
| SHIP-12 | 워크플로우 편집기 전체 코드·환경 설정 인계 | 전체 교체본·설정 안내 준비 | `08_DEPLOYMENT/GENOS/handoffs/system_integration_20261002_r1/README.md` |
| SHIP-13 | 현장 NFS generation·커밋·서빙 리비전 결속 | GENOS 현장 확인 필요 | `06_TOOLS/COMMANDS/genos_release_gate.py` |
| SHIP-14 | 활성 MAIN 전환: Accepted·분리평가 gate | 미충족·활성화 안 함 | `AGENTS.md` |
| SHIP-15 | 통합본 실제 모델·CM 법률 품질·지연 평가 | 미실행 | `통합 계약 테스트를 모델 품질로 보고하지 않음` |
| SHIP-16 | GENOS 내부 데이터·모델·워크플로우 현장 실행 | 현장 미확인 | `GENOS.md` |
| SHIP-17 | runtime 영속성·여러 현장 인스턴스의 SQLite 공유/쓰기 잠금 | GENOS 현장 확인 필요 | `08_DEPLOYMENT/GENOS/handoffs/system_integration_20261002_r1/README.md` |

검사 292개 중290개 통과, 기존 실패2개다. 법률 정답률로 환산하지 않는다. 과거 CM 실험의 실패·거절 판정은 그대로 보존한다. 활성화/현장 확인/설계 보존 항목은 완료로 표시하지 않았다.

# 온톨로지 v3 문서 안내

**온톨로지는 기업의 지식을 통제 가능하게 만들어준다.** 이 방향을 지식 모델, 근거 탐색, 검토·적용 기록, 구현 단위와 DB 설계로 구체화한 문서 모음입니다.

- 기준일: 2026-10-22. 논의·설계 제안이며 신규 기능 구현·DB 적용·MAIN 승격을 의미하지 않습니다.
- 초기 코드 검토 기준: MAIN99 / structured-selection-20261021-r1. 후속 문서 갱신 시 활성 포인터는 MAIN100 / unified-scope-semantics-20261022-r1, quality_certified=false로 확인했습니다. 초기 검토와 ADR0987 연구 후보를 MAIN100 기능으로 바꾸어 설명하지 않습니다.
- v3는 문서 이름이며 데이터 스키마·용어집 세대·MAIN 번호와 다릅니다.
- 저장 기준: Dataiku의 에이전트 레이어에 질의·판단·로그를, 골드 레이어에 구조화 데이터·온톨로지·LLM Wiki를 둡니다. [사용자 확인 기준](../../../00_SYSTEM/ARCHITECTURE.md#dataiku-data-layers).
- 재사용 지식의 일차 저장 단위는 원문입니다. 질문·답변·정정은 발견 이력이며, 개념·검토 사항·관계는 문서 판본·조항·span에 연결합니다.

## 이번 논의의 연결

**원문에 중요한 검토 사항을 붙이고 → 사용자가 보기 쉬운 클러스터로 정리하며 → 개념·관계·조건을 근거와 함께 구성·검토하고 → 질문 또는 확보한 원문에서 찾아 현재 사안에 적용합니다.** 클러스터는 지식 구성의 재료 정리와 조회를 돕습니다. 모든 질문에 같은 계산법·체크리스트를 적용하거나 온톨로지 생성에 반드시 선행해야 하는 단계로 두지는 않습니다.

검색 매칭은 관련 후보를 찾는 일이고 적용 판단은 현재 사실·범위·시점에 그 관계가 성립하는지 검토하는 일입니다. 기대 효과는 필요한 근거의 탐색과 누락을 줄이는 데 있습니다. 실제 CM 연구에서는 탐색량 감소를 관측했으나 정확도 개선을 확인하지 못했으며, 아래 설계와 실행 결과를 구분해 읽습니다.

## 필요한 주제로 이동

| 읽고 싶은 내용 | 문서 |
|---|---|
| 왜 필요한가, 기업 지식을 통제한다는 의미 | [방향과 기업 지식 통제](ONTOLOGY_V3/PURPOSE.md) |
| 현재 기반, 온톨로지와 행동 지침, 정의·공리의 실행 | [현재 기반과 지식 모델 공리](ONTOLOGY_V3/KNOWLEDGE_MODEL.md) |
| 공통 판단을 클러스터로 정리하는 이유, 온톨로지 생성 과정, 속도·정확도의 기대 효과 | [공통 클러스터에서 온톨로지 구성으로](ONTOLOGY_V3/CLUSTERING_AND_CONSTRUCTION.md) |
| 실제 질문의 목적·대상과 매칭, 원문에서 연결 지식 조회, 후보 검색과 적용 판단 | [질문·원문과 온톨로지 매칭](ONTOLOGY_V3/QUESTION_MATCHING.md) |
| 공통 검토 틀과 조문별 숏컷, 누락·루프, 최초 진입 | [근거 기억과 숏컷 최초 진입](ONTOLOGY_V3/EVIDENCE_MEMORY.md) |
| 원문을 일차 저장 단위로 삼는 기준, 질문의 역할 | [원문 중심 저장과 조회](ONTOLOGY_V3/SOURCE_ANCHORED_STORAGE.md) |
| CM 실제 로그의 가정 성공 보완 → 저장 → 같은/관련 질문 재사용 결과 | [CM 원문 중심 E2E 실행 결과](ONTOLOGY_V3/CM_E2E_RESULTS.md) |
| B→C→A 연결, 가상 사례, 관련 연구 | [새로운 관계 발견과 사례](ONTOLOGY_V3/RELATION_DISCOVERY.md) |
| 주장·근거 추적, 온톨로지 적중과 오류 평가 | [설명가능성과 근거 평가](ONTOLOGY_V3/EXPLAINABILITY_AND_EVALUATION.md) |
| 전체 흐름, 현재 구현과 제안의 경계, 검증 과제 | [전체 흐름과 구현 검증 과제](ONTOLOGY_V3/INTEGRATION_AND_VALIDATION.md) |
| 실제 모듈·파일·함수·입출력·소비자 | [구현 단위 문서 안내](../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/IMPLEMENTATION_NAMES.md) |
| Oracle 테이블·ERD·조회·철회·이행 | [DB 설계 문서 안내](../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/DATABASE_ARCHITECTURE.md) |
| 현행 코드를 읽고 확인한 사실과 개편 필요 범위 | [코드 검토](../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/REVIEW.md) |

## 읽는 순서

전체 맥락은 **방향 → 원문 중심 저장 → 공통 클러스터와 온톨로지 구성 → 질문·원문 매칭 → 실제 CM 결과 → 설명·평가** 순서로 읽습니다. 근거 기억과 새로운 관계 문서는 재사용·다단계 탐색을 상세히 설명합니다.

구현을 시작하려면 **질문 매칭의 현재 구현 경계 → 코드 검토 → 구현 단위 → DB 모델 → 조회 → 트랜잭션 → 이행** 순서로 읽습니다. 초기 코드 검토의 MAIN99 기준과 실제 선택 포인터를 대조해야 합니다.

대화의 특정 쟁점은 [쟁점별 찾아보기](ONTOLOGY_V3/DISCUSSION_MAP.md), 연구 원문은 [연구·표준 출처](ONTOLOGY_V3/SOURCES.md)에서 찾을 수 있습니다. 각 상세 문서 상단에 목차, 하단에 이전·다음 문서 링크가 있습니다.

## 문서 관리

상세 내용은 주제 문서에서 갱신하고 이 문서에는 안내와 링크를 유지합니다. 기존 구현·DB 문서 주소도 목차로 유지했습니다. 이전 통합 문서의 23절·24절 중복 요약은 각각 구현·DB 안내로 통합했습니다.

분리 전 원문과 후속 갱신 전 내용은 [보존 기록](../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/document_history/README.md)에 있습니다. 최초 분리의 [구성표](ONTOLOGY_V3/DOCUMENT_MAP.json)와 [검사 결과](ONTOLOGY_V3/REORGANIZATION_VALIDATION.json)는 당시 상태로 보존합니다. 이번 클러스터·생성·매칭 반영의 문서 목록·링크·보존 검사는 [별도 갱신 기록](../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/document_history/20261022_clustering_matching_validation.json)을 따릅니다.

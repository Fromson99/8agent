# 대화 쟁점별 찾아보기

[전체 목차](../ONTOLOGY_V3.md)

원래 논의의 절 번호를 유지했습니다. 설계 제안과 구현·검증 상태는 각 절의 구분을 따릅니다.

<a id="v3-a"></a>

## 부록 A. 논의 포함 여부

| 대화의 요청·쟁점 | 이 문서에서 정리한 위치 |
|---|---|
| 우리의 법률 온톨로지가 만들어지는 과정 | [3절](KNOWLEDGE_MODEL.md#v3-3) |
| 행동 지침 모음집처럼 보인다는 문제 | [4절](KNOWLEDGE_MODEL.md#v3-4) |
| 용어 관계와 정의·공리의 차이 | [4절](KNOWLEDGE_MODEL.md#v3-4)–[5절](KNOWLEDGE_MODEL.md#v3-5) |
| 공리를 컴퓨터에서 실행·컴파일할 수 있는가 | [5절](KNOWLEDGE_MODEL.md#v3-5) |
| 단순 연결과 상황에 따른 가지치기 | [4절](KNOWLEDGE_MODEL.md#v3-4)–[5절](KNOWLEDGE_MODEL.md#v3-5), [8절](EVIDENCE_MEMORY.md#v3-8) |
| 다른 사람들의 생각과 관련 연구 | [4절](KNOWLEDGE_MODEL.md#v3-4)–[5절](KNOWLEDGE_MODEL.md#v3-5), [12절](RELATION_DISCOVERY.md#v3-12), [연구·표준 출처](SOURCES.md#v3-b) |
| 금액 산정 부분이 부족할 때 기억을 떠올리는 기능 | [6절](EVIDENCE_MEMORY.md#v3-6) |
| 전체 탐색보다 빠른 정답 도달이라는 기준 | [1절](PURPOSE.md#v3-1), [6절](EVIDENCE_MEMORY.md#v3-6), [15절](INTEGRATION_AND_VALIDATION.md#v3-15) |
| 동일한 문제와 비슷한 문제의 재사용 차이 | [6절](EVIDENCE_MEMORY.md#v3-6), [9절](EVIDENCE_MEMORY.md#v3-9), [15절](INTEGRATION_AND_VALIDATION.md#v3-15) |
| 너무 추상적이면 LLM이 다시 이해해야 하는 문제 | [7.1절](EVIDENCE_MEMORY.md#v3-7-1) |
| 너무 구체적이면 데이터마다 기억해야 하는 문제 | [7.2절](EVIDENCE_MEMORY.md#v3-7-2), [13.3절](INTEGRATION_AND_VALIDATION.md#v3-13-3) |
| 공통 판단 묶음과 조문별 숏패스의 결합 | [7.3절](EVIDENCE_MEMORY.md#v3-7-3) |
| 법 질문마다 계산이 다른데 공통 판단은 왜 필요한가 | [공통 클러스터의 역할](CLUSTERING_AND_CONSTRUCTION.md#cluster-role) |
| 사용자가 보기 쉬운 클러스터와 온톨로지 구성 재료 | [역할 구분](CLUSTERING_AND_CONSTRUCTION.md#roles), [공통 묶음에서 의미 관계로](KNOWLEDGE_MODEL.md#v3-5-5) |
| 질문·답변·정정에서 발견한 지식을 원문에 저장 | [원문 중심 저장](SOURCE_ANCHORED_STORAGE.md), [생성 과정](CLUSTERING_AND_CONSTRUCTION.md#construction) |
| 원문 마킹에서 개념·관계·조건·검토·게시로 만드는 과정 | [온톨로지 구성](CLUSTERING_AND_CONSTRUCTION.md#construction), [가상 규정 예](CLUSTERING_AND_CONSTRUCTION.md#example) |
| 관계를 만들고 적용하면 속도·정확도가 좋아질 수 있는 이유 | [기대 효과와 역효과](CLUSTERING_AND_CONSTRUCTION.md#value), [실제 CM 결과](CM_E2E_RESULTS.md) |
| 질문과 온톨로지는 실제로 어떻게 매칭하는가 | [질문 기반 후보 회수](QUESTION_MATCHING.md#question-entry), [원문 기반 조회](QUESTION_MATCHING.md#source-entry) |
| 검색 매칭과 현재 사안의 적용 판단의 차이 | [매칭 대상과 두 판단](QUESTION_MATCHING.md#matching-target), [단계별 실행 예](QUESTION_MATCHING.md#worked-example) |
| 질문 표현이 달라지거나 지식이 없을 때의 처리 | [미적중·오적중·미확인](QUESTION_MATCHING.md#fallback), [현재 구현과 목표](QUESTION_MATCHING.md#implementation) |
| 같은 조문에서도 딕셔너리로 중요 부분 명시 | [7.4절](EVIDENCE_MEMORY.md#v3-7-4)–[7.5절](EVIDENCE_MEMORY.md#v3-7-5) |
| 중요한 근거의 누락과 추가 조사 루프 방지 | [8절](EVIDENCE_MEMORY.md#v3-8) |
| 최초 조문 진입점을 빠르게 찾는 과제 | [9절](EVIDENCE_MEMORY.md#v3-9) |
| B-C-A를 통한 새로운 연결의 가능성과 의미 | [10절](RELATION_DISCOVERY.md#v3-10)–[11절](RELATION_DISCOVERY.md#v3-11) |
| 계약 합산과 승인, 등급 하락과 보고의 예시 | [10.2절](RELATION_DISCOVERY.md#v3-10-2)–[10.3절](RELATION_DISCOVERY.md#v3-10-3) |
| 현재 구현과 설계·미검증 범위 구분 | [3절](KNOWLEDGE_MODEL.md#v3-3), [14절](INTEGRATION_AND_VALIDATION.md#v3-14)–[16절](INTEGRATION_AND_VALIDATION.md#v3-16) |
| 모델이 좋아진 이후의 지속 가치와 조직의 검토 이력 | [18절](PURPOSE.md#v3-18) |
| 일반 조사 지침과 실행 상태 관리의 구분 | [8절](EVIDENCE_MEMORY.md#v3-8), [18.1절](PURPOSE.md#v3-18-1) |
| 설명가능성의 범위와 실행 기록·사후 설명의 차이 | [19.1절](EXPLAINABILITY_AND_EVALUATION.md#v3-19-1) |
| 거래 사례에서 해석 의존 지점과 수정 영향 표시 | [19.2절](EXPLAINABILITY_AND_EVALUATION.md#v3-19-2)–[19.3절](EXPLAINABILITY_AND_EVALUATION.md#v3-19-3) |
| 온톨로지 hit과 근거 지지·새로운 적용 해석의 구분 | [20절](EXPLAINABILITY_AND_EVALUATION.md#v3-20) |
| 창의적인 연결을 미적중으로 불리하게 평가하지 않기 | [20.3절](EXPLAINABILITY_AND_EVALUATION.md#v3-20-3) |
| 주장 단위의 지표·평가 범위·핵심 오류와 해석 이견 | [21절](EXPLAINABILITY_AND_EVALUATION.md#v3-21) |
| 할루시네이션 확률의 보정과 자기평가의 한계 | [21.4절](EXPLAINABILITY_AND_EVALUATION.md#v3-21-4) |
| 모델 변화와 인간 검토 시간까지 포함한 후속 검증 | [18.3절](PURPOSE.md#v3-18-3), [22절](EXPLAINABILITY_AND_EVALUATION.md#v3-22) |
| 기업의 지식을 통제 가능하게 만드는 제품 방향 | [1절](PURPOSE.md#v3-1), [23절](../../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/IMPLEMENTATION_NAMES.md#v3-23) 및 연결된 코드 검토 |
| 기존 코드에 대응하는 구현 단위·파일·함수 이름 | [23절](../../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/IMPLEMENTATION_NAMES.md#v3-23) 및 연결된 구현 명명 상세 |
| DB 테이블·키·관계·조회·검토/철회·이행 설계 | [24절](../../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/DATABASE_ARCHITECTURE.md#v3-24) 및 연결된 DB 설계·DDL·SQL |

---

[이전: 설명가능성과 근거 평가](EXPLAINABILITY_AND_EVALUATION.md) · [목차](../ONTOLOGY_V3.md) · [다음: 연구와 표준 출처](SOURCES.md)

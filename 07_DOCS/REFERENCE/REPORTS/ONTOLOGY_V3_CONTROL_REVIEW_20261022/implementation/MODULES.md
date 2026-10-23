# 구현 단위 이름과 파일 구조

[전체 목차](../../../ARCHITECTURE/ONTOLOGY_V3.md) · [구현 목차](../IMPLEMENTATION_NAMES.md)

원래 논의의 절 번호를 유지했습니다. 설계 제안과 구현·검증 상태는 각 절의 구분을 따릅니다.

<a id="impl-1"></a>

## 1. 전체 이름과 구현 경계

전체 기능 이름은 **기업지식 통제 시스템 — Legal Knowledge Control**로 둔다. 기존 Python 패키지 `lawrag.legal_knowledge`, CLI `pipeline.py legal-knowledge`, API `/v1/legal-knowledge`를 확장한다. 새 최상위 패키지나 독립 서버를 추가하지 않는다.

‘온톨로지’는 이 시스템에서 **지식의 의미·관계·조건·제약을 정의하는 모델**을 가리킨다. 원장 저장, 검토 결정, 질의 적용, 영향 분석은 각각 아래의 명시적인 구현 책임으로 나눈다.

‘서비스’는 Python 애플리케이션 서비스 클래스라는 뜻이다. 각 행을 마이크로서비스·프로세스·별도 DB로 배포한다는 뜻이 아니다.

<a id="impl-2"></a>

## 2. 구현 단위 이름표

경로의 `backend/`는 workspace의 backend root인 `02_BACKEND/`를 줄여 쓴 것이다. **목표 경로**는 구현 시 생성·분리할 위치이며 지금 존재한다는 표시가 아니다.

| ID | 표시 이름 / 구현 이름 | 현재 코드와 처리 | 목표 코드 단위 | 주요 입력 → 출력 | 상태 |
|---|---|---|---|---|---|
| M01 | 조사경험 원장 / Investigation Ledger | `ShortcutCases`, `ShortcutRepository`의 질문·사실·trace·원문 기록 | 기존 `semantic_runtime/legal_agent/shortcut_cases.py`, `shortcut_repository.py`의 기록 경로 유지 | 요청·사실 수정·단계 receipt → 경험 ID·revision·근거 참조 | 기존 기반 유지, 책임 명확화 |
| M02 | 근거경로 인덱스 / Evidence Route Index | `core_evidence_route.finalize/lookup`, `wiki_recall.lookup` | 기존 `core_evidence_route.py`, `wiki_recall.py` 확장 | 현재 질문 또는 근거 필요·판본·권한 → 원문 위치 경로 | 기존 기반 확장 |
| M03 | 지식 후보 생성기 / Knowledge Candidate Builder | `legal_wiki_compiler.compile_snapshots`와 `wiki_proposal` | `lawrag/pipeline/knowledge_candidates.py::build_candidates` | 원문 또는 적격 조사 경험 → 근거 있는 지식 후보·미확인 | 추출 책임 분리·확장 |
| M04 | 지식 모델 / Knowledge Model | 관리 `contracts.py`, 위키 claim, 도메인 catalogue의 의미 계약이 분산 | `lawrag/legal_knowledge/model.py` | 개념 참조·주장·관계·조건·근거 → 검증 가능한 객체 계약 | 신규 통합 계약 |
| M05 | 기업지식 원장 / Knowledge Registry | `application.Service`의 definition 처리와 `adapters.Repository` | `lawrag/legal_knowledge/registry.py::KnowledgeRegistry` | 지식 객체·기대 revision → 고정 ID·불변 revision·계보 | 기존 저장 기반 확장 |
| M06 | 지식 검토·게시 서비스 / Knowledge Lifecycle Service | `Service.command/_prepare_publication/_publish/_retire` | `lawrag/legal_knowledge/lifecycle.py::KnowledgeLifecycleService` | 권한 있는 검토 결정·대상 버전 → 검토 이력·게시·개별 사용 중단 | 기존 명령 책임 분리·확장 |
| M07 | 지식 조회 서비스 / Knowledge Query Service | `Service.plan`, `planning.assemble`, `Repository.candidates` | `lawrag/legal_knowledge/query.py::KnowledgeQueryService` | 질문 또는 근거 필요·사실·기준일·권한 → 진입 후보·검토 항목·근거 경로 | 기존 조회 책임 분리·확장 |
| M08 | 지식 적용 서비스 / Knowledge Application Service | `knowledge_bridge`, `KnowledgeReferences`, 판단·발행 기록 | `semantic_runtime/legal_agent/knowledge_application.py::KnowledgeApplicationService` | 제시 지식·명시적 선택·원문·사실·판단 결과 → 주장별 적용 기록 | 기존 연결 확장·새 기록 계약 |
| M09 | 변경 영향 분석기 / Knowledge Impact Analyzer | `Service.impact`, `sw_dependency`, basis migration | `lawrag/legal_knowledge/impact.py::KnowledgeImpactAnalyzer` | 바뀐 지식·원문·사실 참조 → 영향받는 지식·경로·판단과 조회 범위 | 직접 의존 조회 확장 |
| M10 | 기업지식 콘솔 / Knowledge Console | `/legal-knowledge/` 관리 화면과 위키 projection | 기존 `lawrag/api/viewer/legal_knowledge/` 확장 + `lawrag/legal_knowledge/views.py` | 같은 지식·검토·적용 참조 → 화면·위키 문서 | 표현 책임 분리·확장 |
| M11 | 조사 실행 정책 / Research Execution Policy | `domain_control.METHODS`, 단계별 고정 `select` | `semantic_runtime/legal_agent/research_policy.py::ResearchExecutionPolicy` | 실행 단계·현재 상태 → 단계 정책 receipt | 현재 실행 책임에 맞춘 분리·명칭 변경 |
| M12 | 조건 평가기 / Condition Evaluator | `legal_knowledge/ontology/__init__.py`의 expression·scope 함수 | `lawrag/legal_knowledge/condition_evaluator.py` | 형식 조건·출처 있는 입력·scope → TRUE/FALSE/UNKNOWN/CONFLICT·계산 receipt | 현재 평가 책임에 맞춘 이동 |

M01·M02의 공개 이름은 명확히 하지만 파일·SQL 테이블의 일괄 rename은 하지 않는다. 기존 `sw_*` 원장에는 위키 데이터도 함께 있으므로 책임 분리와 데이터 이행을 마치기 전 저장소 전체를 새 ‘조사경험 원장’ 구현이라고 선언하지 않는다.

2026-10-22 원문 중심 저장 정정에 따라 M03의 출력은 **원문·개념에 붙이는 검토 지식 후보**다. M05는 원문 anchor와 개념별 지식을 관리하고, M07은 `question → concept`뿐 아니라 `source_anchor → checks/evidence_routes` 조회를 담당한다. M08은 현재 읽은 원문에 맞는 검토 사항을 판단 입력에 연결한다. 질문·답변별 묶음은 M01의 발견 이력이며 M05의 일차 저장 단위가 아니다. [실제 저장 예와 미구현 범위](../../../ARCHITECTURE/ONTOLOGY_V3/SOURCE_ANCHORED_STORAGE.md).

같은 날 후속 논의에서 공통 판단 묶음은 **사용자용 클러스터와 온톨로지 구성 재료를 정리하는 층**으로 구체화했다. M10은 같은 원문 지식 참조를 여러 묶음에서 보여주고, M03·M04는 원문별 개념·관계·조건 후보를 구성하는 방향이다. 클러스터 소속으로 의미 동치나 법적 적용을 확정하지 않는다. M07의 관련 후보 회수와 M08의 현재 사안 적용 판단을 분리하며, M11이 모든 공통 항목을 강제 조사하는 구조로 만들지 않는다. 이는 목표 책임이며 신규 런타임 구현을 뜻하지 않는다. [구성 과정](../../../ARCHITECTURE/ONTOLOGY_V3/CLUSTERING_AND_CONSTRUCTION.md) · [두 진입 경로와 코드 상태](../../../ARCHITECTURE/ONTOLOGY_V3/QUESTION_MATCHING.md#implementation).

M11의 의미는 단계 실행 정책이다. 현재 `DomainCatalogue`에 있는 REVIEWED 개념 입력 계약까지 버리는 것이 아니다. 기존 catalogue의 출처·검토 기록은 M04·M05에 연결할 대상으로 보존하고, 현재와 과거의 domain_choice 소비 계약은 호환 계층에서 유지한다.

<a id="impl-3"></a>

## 3. 기존 이름을 어디까지 바꾸는가

| 기존 표현·코드 | 바꿀 이름·분리 | 변경 이유 |
|---|---|---|
| 숏컷 | 사용자 표현은 유지 가능. 구현 설명은 조사경험 원장 + 근거경로 인덱스 | 경험을 보관하는 일과 유효한 근거 위치를 빠르게 찾는 일이 다름 |
| 리걸위키 컴파일러 | 지식 후보 생성기 + 지식 문서 렌더러 | 의미 후보를 만드는 처리와 승인 상태를 읽어 문서로 보여주는 처리를 분리 |
| 리걸위키 | 기업지식 콘솔의 문서 보기 | Markdown 또는 화면이 별도의 정본이 되지 않음 |
| 도메인 컨트롤 / `domain_control` | 조사 실행 정책 / `research_policy` | 현재 실행하는 책임은 단계별 방법 지정 |
| 온톨로지 평가 모듈 | 조건 평가기 / `condition_evaluator` | 현재 구현은 제한된 식·범위 평가이며 도메인 지식 전체의 관리가 아님 |
| `application.Service` | 호환 진입점 유지 + Registry/Lifecycle/Query/Impact로 내부 책임 분리 | 동일 클래스로 저장·게시·조회·영향을 모두 설명하던 모호함 해소 |
| `knowledge_bridge` | 지식 적용 서비스 / `knowledge_application` | 안내 전달에서 선택·적용·주장 연결·발행 재확인까지 책임을 확장 |
| `basis_links` | 근거관계 원장 / Basis Link Registry. 기존 패키지 유지 | 이미 구현된 내규–외규 관계의 승인·철회·개정 binding 책임 보존 |

기존 import·API를 바로 삭제하지 않는다. 예를 들어 `knowledge_bridge.prepare/augment/public_metadata/validate_publication`는 이행 중 M08로 위임하고, 외부 호출부는 같은 계약을 유지한다. 기존 `Service.command/plan/impact`와 CLI도 같은 방식으로 단일 구현에 위임한다. 호환 계층이 별도 저장·추론·재시도를 수행하게 만들지 않는다.

`ontology/`라는 단어를 모든 파일에서 지우는 작업도 아니다. 과거 데이터·명세·릴리스에는 당시 이름을 보존하고, 새 코드의 책임을 위 이름으로 명시한다.

<a id="impl-4"></a>

## 4. 목표 파일 구조

아래는 **구현 목표 트리**다. 이 문서를 쓰면서 빈 파일을 만들지는 않았다.

```text
02_BACKEND/
├─ lawrag/
│  ├─ pipeline/
│  │  ├─ knowledge_candidates.py       # M03 후보 생성
│  │  ├─ legal_wiki_compiler.py        # 기존 호출 호환, M03/M10으로 위임
│  │  └─ legal_knowledge.py            # 기존 CLI, 같은 애플리케이션 서비스 호출
│  ├─ legal_knowledge/
│  │  ├─ model.py                     # M04 지식·검토·적용 객체 계약
│  │  ├─ contracts.py                 # wire/명령 계약, 버전별 호환
│  │  ├─ registry.py                  # M05 지식 ID·revision·계보
│  │  ├─ lifecycle.py                 # M06 검토·게시·개별 사용 중단
│  │  ├─ query.py                     # M07 진입·근거 필요에 따른 조회
│  │  ├─ impact.py                    # M09 역의존·실제 사용 영향 조회
│  │  ├─ condition_evaluator.py       # M12 제한된 형식 조건 실행
│  │  ├─ views.py                     # M10 화면·문서용 projection
│  │  ├─ application/__init__.py      # 기존 Service facade
│  │  └─ adapters/                    # 기존 Oracle·원문·위키 참조 어댑터 확장
│  └─ api/
│     ├─ routers/legal_knowledge.py   # 기존 API 경로 확장
│     └─ viewer/legal_knowledge/      # M10 기존 관리 화면
└─ semantic_runtime/
   ├─ legal_agent/
   │  ├─ shortcut_cases.py           # M01 현재 요청·조사 경험 연결 유지
   │  ├─ shortcut_repository.py      # M01 현행 저장·legacy 위키 호환
   │  ├─ core_evidence_route.py      # M02 현재 근거 경로
   │  ├─ wiki_recall.py              # M02 legacy 카드·회수 호환
   │  ├─ research_policy.py          # M11 단계 정책
   │  ├─ knowledge_application.py    # M08 질의에서 지식 사용·기록
   │  ├─ domain_control.py           # 기존 catalogue·선택 계약 호환
   │  └─ knowledge_bridge.py         # 기존 호출 호환
   ├─ research_state.py              # 기존 조사 상태와 journal 소유
   └─ basis_links/                   # 기존 근거관계 원장
```

---

[목차](../IMPLEMENTATION_NAMES.md) · [다음: 데이터 객체와 함수 계약](CONTRACTS.md)

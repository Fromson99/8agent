# MAIN — 원문과 용어 기반 탐색

2026-09-15 사용자 지시로 법률 의미 상세 스키마를 RAG와 신규 데이터 생성에서 제거했다.
현행 계약은 [DATA_MODEL.md](DATA_MODEL.md), 엔진 선택은 [PIPELINE.json](PIPELINE.json)이다.
이전 Rule·SemanticClause·Proviso·조건식·템플릿 설계는 [변경 전 기록](../09_ARTIFACTS/AUDITS/20260915-term-only-schema-removal/before/00_SYSTEM-ARCHITECTURE.md)에 보존한다.

## 전체 흐름

```text
문서: 내부·외부 RAW → 전체 구조 복원 → 원문·좌표·버전 저장 → 명시 원문 통합
용어집: 기존 사전 + 통합 문서의 정의 후보 → 기존 미검토·신규 후보 통합 검토
  → 검토된 초안으로 전체 용어 출현 연결 + 문서 정의 + 명시 조문 참조 → 탐색 색인
  → 용어 탐색 → 원문 확인 → 부족한 근거에 따른 추가 탐색/질문 → 답변
  → 실행·원문 세대에 연결된 피드백 후보
```

의미 추출로 문장을 Rule·조건·효과로 재작성하는 단계는 없다. 에이전트는 원문을 읽고 판단 상태를 생성한다. 용어 관계와 정의는 탐색 단서이며 법적 결론을 자동 확정하지 않는다.

## 단계별 실제 연결

| 단계 | 진입점 | 출력·소비자 |
|---|---|---|
| 용어집 | `pipeline.py glossary …` | 출처별 사전·정의·관계. `GLOSSARY_SCHEMA.json`은 용어집 검토 계약만 소유 |
| 통합 구축 | `pipeline.py build-all --run-id NAME --execute` | 전체 문서 구조화 → 명시 원문 통합 → 기존·신규 후보 통합 검토 → 전체 연결·색인·서빙 후보 검증 |
| 입력·구조화 | `pipeline.py build-data-stages --stage structure --run-id NAME --execute` | `STRUCTURE/<fingerprint>/source.sqlite`; 문서·구조 마디·본문만 저장. PDF 구조 복원의 VLM은 유지 |
| 색인·적재 | 같은 명령의 `--stage index` 또는 `all` | `TERM/<run>/<document>/generation`: 원문 세대와 용어·정의·참조 탐색 색인. `term_generation.build_generation`이 같은 계약으로 생성 |
| RAG | `service.py` → `semantic_runtime.app` → PIPELINE의 `legal-rag` | 원문·용어 탐색 전용. QueryPlan/CardSet·규칙·조건 평가·의미 그래프 fallback 없음 |
| 피드백 | `/v1/rag/feedback` → `legal-feedback` | 답변·실행 해시·원문 세대를 가리키는 PROPOSED 후보. 자동 반영 없음 |
| 표현 학습·절차 재사용 | `pipeline.py glossary learn` + 선택형 `term_agent.learning` | 질문 구간 후보 → 운영자 검토 → 세대·해시 결속 번들 → 기존 NavigationSession. [작업 코드 계약](../07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_LEARNING.md). 기본 꺼짐, 활성 릴리스 미반영 |
| 개념 정의·범위 작업 하네스 | `pipeline.py task-harness` + 선택형 `definition-scope-harness-v1` | 검토된 DB 정의 → 원문 span 해석 → 후보 검토 → 의무별 원문·의미 검토 → 완료/미확인 → 개선 후보. [구현·실행 계약](../07_DOCS/REFERENCE/OPERATIONS/TASK_HARNESS.md). 작업 코드와 모의 계약 검사, 활성 릴리스·GENOS 미반영 |
| 골든 관리·평가 | `pipeline.py golden` | 원문 좌표 검증·suite 동결 → GENOS 코드스페이스의 같은 `/v1/rag/ask` 앱으로 배치 → 단계별 회수·인용 점수 + 사람 답변 검토. 제품 입력과 정답 분리, [운영 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_GOLDEN_EVALUATION.md). 현장 실행 미확인 |

현재 신규 문서 생성은 DRAFT를 만들며 MAIN을 자동 활성화하지 않는다. source-only 게시 API도 동일한 용어 색인 생성기를 사용한다. GENOS 현장 실행·반입·배포는 아직 확인하지 않았다.

GENOS 문서 구축의 PDF는 환경변수로 선택한 전처리기에 파싱을 맡긴다. `data.document`의
Docling JSON 또는 완전한 인덱스 청크 배열을 받아 기존 구조화·원문 SQLite·용어 색인으로 연결한다. 청크는 원문·순서·페이지 출처를 보존해 합치고, 전체 파싱 텍스트로 틀 생성 → 원본 PDF VLM 검수·틀 보정 → 최종 틀로 전체 재구조화한다. 청크 입력은 전 페이지 검수 필수이며 없는 표 셀·좌표를 생성하지 않는다. 전처리기 ID/URL과
선택적 배포 리비전, 공유 경로는 코드스페이스 환경 설정으로 지정한다. 코드스페이스에서 PDF용
Docling 모델을 다시 실행하지 않는다. [연결·실행 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_PREPROCESSOR_PARSING.md).
2026-09-16 현장 사진에서 기존 전처리기의 성공 청크 응답을 확인했다. 새 청크 수신·VLM 연결 및 별도 구조 응답 전처리기 수정본은 로컬 모의 계약 검증이며 현장 배포·품질은 미확인이다.

## 서빙과 이행

`PIPELINE.json`의 기본 RAG 모드는 `document-navigation-v1`이다. 질문을 목록·트리·목차·내용·매핑으로 먼저 해석한다.
문서 목록·폴더 트리·목차는 저장된 메타데이터로 답하고, 내용 질문만 여러 원문 읽기·검토·종합으로 넘긴다.
GENOS에서는 `GENOS_RAG_IMPLEMENTATION`으로도 명시 선택한다. [GENOS 반입·계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_TOOLS.md).

확인된 로컬 활성 릴리스는 `document-navigation-rag-20260917-v2`, 포인터 generation 16이다(2026-09-17 사용자 지시 전환 뒤 전수 조사·수정 재릴리스, 품질 인증 false).
내용 질문은 질문 개념별 후보(컷 없음, 개념 적중 순)를 3건씩 읽고 검토하며, 채택 근거가 있으면 후보를 다 읽지 않아도 종합·검증한다.
로컬 159문서 세대의 폴더는 해시로 검증한 출처 파일로 분류한다: kofia 72 · law 62 · krx 11 · internal/risk_team 10, 미확인 4.
[현재 배선·운영 계약](../07_DOCS/REFERENCE/OPERATIONS/NAVIGATION_MAIN.md).

로컬 MAIN 릴리스 및 포인터의 최종 상태는 [문서 탐색 배선 기록](../09_ARTIFACTS/AUDITS/20260917-document-navigation-main-wiring/README.md)과 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`을 따른다. 직전 탐색 루프 릴리스는 [탐색 루프 배선 기록](../09_ARTIFACTS/AUDITS/20260916-navigation-main-wiring/README.md)에 보존한다. 코드 변경·Git main 병합·데이터 세대 선택·로컬 MAIN 활성화·GENOS 배포는 각각 별도 상태다.

- 원문 159문서의 ID·본문·구조·해시를 그대로 새 원문 전용 세대로 옮겼다.
- 기존 의미 테이블·projection은 새 세대로 복사하지 않았다. 과거 세대·ADR·릴리스는 보존한다.
- 정의의 원문 블록과 해시를 검증하고, 인용·준용은 원문에 명시된 조문 표기를 색인한다. 범위·외부 문서·모호한 참조는 미확인으로 둔다.
- 원문·용어집·코드 변경은 새 세대와 색인을 만든다. 기존 파서 캐시는 사용한 파서 지문이 같을 때만 재사용한다.
- 품질 인증은 `false`다. 이번 변경의 검사는 구조·계약·배선 검사이며, 법률 답변 품질 통과를 의미하지 않는다.

전체 파이프라인 실험은 입력·설정·모델·프롬프트·코드와 변경하지 않은 단계도 함께 고정한다. 원문 근거·버전·감사·롤백·접근권한을 보존한다. 피드백에서 재구축·검증·MAIN 채택까지의 자동 루프는 미완성이다.

현행 구축 단위와 의존성은 `PIPELINE.json.authorities.document_build` 및 [실행 안내](../07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md)를 따른다. 내규도 `RAW/internal`에서 형식별 처리한다. 구조화 단독 실행은 용어집을 읽지 않는다.

추가 문서의 통합 서빙 후보는 `TERM_RELEASES/<run>`에 생성한다. `document-release`가 동일 실행 명세의 후속 단위이며 활성화는 명시적 CURRENT CAS/롤백 절차다. [추가 문서 연결 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md). 작업 코드의 이 연결은 기존 로컬 활성 릴리스나 GENOS 배포를 변경하지 않는다.

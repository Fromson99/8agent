# MAIN — 원문과 용어 기반 탐색

2026-09-15 사용자 지시로 법률 의미 상세 스키마를 RAG와 신규 데이터 생성에서 제거했다.
현행 계약은 [DATA_MODEL.md](DATA_MODEL.md), 엔진 선택은 [PIPELINE.json](PIPELINE.json)이다.
이전 Rule·SemanticClause·Proviso·조건식·템플릿 설계는 [변경 전 기록](../09_ARTIFACTS/AUDITS/20260915-term-only-schema-removal/before/00_SYSTEM-ARCHITECTURE.md)에 보존한다.

## 전체 흐름

```text
공통 용어집: 원천 표제어·출처별 정의·용어 관계 → 검토된 초안 선택
문서: RAW 입력 → 구조 복원 → 원문·좌표·버전 저장
  → 용어 출현 연결 + 문서 안의 정의 + 명시 조문 참조 → 탐색 색인
  → 용어 탐색 → 원문 확인 → 부족한 근거에 따른 추가 탐색/질문 → 답변
  → 실행·원문 세대에 연결된 피드백 후보
```

의미 추출로 문장을 Rule·조건·효과로 재작성하는 단계는 없다. 에이전트는 원문을 읽고 판단 상태를 생성한다. 용어 관계와 정의는 탐색 단서이며 법적 결론을 자동 확정하지 않는다.

## 단계별 실제 연결

| 단계 | 진입점 | 출력·소비자 |
|---|---|---|
| 용어집 | `pipeline.py glossary …` | 출처별 사전·정의·관계. `GLOSSARY_SCHEMA.json`은 용어집 검토 계약만 소유 |
| 통합 구축 | `pipeline.py build-all --run-id NAME --execute` | 용어집 검토 완료 후 아래 문서 구축 실행 |
| 입력·구조화 | `pipeline.py build-data-stages --stage structure --run-id NAME --execute` | `STRUCTURE/<fingerprint>/source.sqlite`; 문서·구조 마디·본문만 저장. PDF 구조 복원의 VLM은 유지 |
| 색인·적재 | 같은 명령의 `--stage index` 또는 `all` | `TERM/<run>/<document>/generation`: 원문 세대와 용어·정의·참조 탐색 색인. `term_generation.build_generation`이 같은 계약으로 생성 |
| RAG | `service.py` → `semantic_runtime.app` → PIPELINE의 `legal-rag` | 원문·용어 탐색 전용. QueryPlan/CardSet·규칙·조건 평가·의미 그래프 fallback 없음 |
| 피드백 | `/v1/rag/feedback` → `legal-feedback` | 답변·실행 해시·원문 세대를 가리키는 PROPOSED 후보. 자동 반영 없음 |

현재 신규 문서 생성은 DRAFT를 만들며 MAIN을 자동 활성화하지 않는다. source-only 게시 API도 동일한 용어 색인 생성기를 사용한다. GENOS 현장 실행·반입·배포는 아직 확인하지 않았다.

## 서빙과 이행

확인된 로컬 활성 릴리스는 `term-source-rag-20260915-v1`, 포인터 generation 13이다.

로컬 MAIN 릴리스 및 포인터의 최종 상태는 [제거·이행 기록](../09_ARTIFACTS/AUDITS/20260915-term-only-schema-removal/README.md)과 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`을 따른다. 코드 변경·Git main 병합·데이터 세대 선택·로컬 MAIN 활성화·GENOS 배포는 각각 별도 상태다.

- 원문 159문서의 ID·본문·구조·해시를 그대로 새 원문 전용 세대로 옮겼다.
- 기존 의미 테이블·projection은 새 세대로 복사하지 않았다. 과거 세대·ADR·릴리스는 보존한다.
- 정의의 원문 블록과 해시를 검증하고, 인용·준용은 원문에 명시된 조문 표기를 색인한다. 범위·외부 문서·모호한 참조는 미확인으로 둔다.
- 원문·용어집·코드 변경은 새 세대와 색인을 만든다. 기존 파서 캐시는 사용한 파서 지문이 같을 때만 재사용한다.
- 품질 인증은 `false`다. 이번 변경의 검사는 구조·계약·배선 검사이며, 법률 답변 품질 통과를 의미하지 않는다.

전체 파이프라인 실험은 입력·설정·모델·프롬프트·코드와 변경하지 않은 단계도 함께 고정한다. 원문 근거·버전·감사·롤백·접근권한을 보존한다. 피드백에서 재구축·검증·MAIN 채택까지의 자동 루프는 미완성이다.

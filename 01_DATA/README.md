# 데이터 입력·생성

현재 전체 흐름은 [ARCHITECTURE](../00_SYSTEM/ARCHITECTURE.md), 데이터 계약은 [DATA_MODEL](../00_SYSTEM/DATA_MODEL.md)을 따른다.
경로는 `lawrag.platform.workspace`의 논리 `data` root로 해결한다. 완료 세대·RAW·원문 해시는 보존한다.

## 현재 생성 경로

```text
RAW 입력 / 준비된 내부 PDF → STRUCTURE → 용어·정의·참조 색인 → TERM/<run>/<document>/generation
```

- `RAW/<source>`: 원본과 입력 출처·버전·해시. 내규의 준비된 PDF는 현행 입력 선택 정책에 따라 `PDF/internal`에서 선택한다.
- `STRUCTURE/<fingerprint>`: 원문 구조와 `source.sqlite`. 의미 추출 작업은 만들지 않는다. PDF 구조 복원·검수는 유지한다.
- `LEXICON`: 선택 용어집과 문서 출현·정의 연결. 용어 목록 수집과 정의·관계 수집 완료는 별개다.
- `TERM/<run>/<document>/generation`: 원문 전용 저장소와 `navigation` 색인. `result.json`은 입력·코드·결과를 결속한다.
- `LOGS/<run>`: 실행·입력·오류·진행 기록. 현재 단계 상태는 `term-document-status.sqlite`에 저장한다.
- `SEMANTIC/GENERATIONS`, `SEMANTIC/TERM_INDEX`: 이미 사용하던 세대 저장 위치. 이름과 무관하게 신규 선택 데이터의 manifest 계약이 기준이다. 과거 의미 세대는 복구용으로 보존한다.

기존 `LLM` 의미 추출 결과 및 VECTOR 산출물은 신규 생성·RAG의 필수 입력에서 제외했다. 신규 의미 추출/검토/재추출과 조건식·Rule 생성은 실행하지 않는다.

## 실행

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id term-build-001 --check-only
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id term-build-001 --stage all --execute
```

사전 검토까지 실행하려면 `build-all --run-id term-build-001 --execute`를 사용한다.
단계 실행·재개·GENOS 인계는 [운영 가이드](../07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md)를 따른다.

새 입력은 출처·문서 ID·버전·해시·공개/내부·실제/모의 구분을 기록하고 RAW에서 검증한다. 외부·내부 데이터는 DatasetPackage와 명시적 SourceSet 범위를 보존한다. DRAFT 생성은 배포 승인이나 데이터 반출 승인을 뜻하지 않는다. 내부 데이터 처리는 망분리 GENOS에서 수행한다.

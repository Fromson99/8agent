# 기본 파이프라인의 전체 용어·관계 데이터

2026-09-15 사용자 지시로, 수집된 Wikidata·FIBO·연결관계 전체를 기본 문서 작성 경로에서
소비하도록 연결했다. 새로운 모델 실험/의미 승인 없이, 기존 완료 원천과 관측을 새 DRAFT
세대로 묶는 결정적 반입·조회 배선이다. 기존 실험 DB와 앞서 만든 ZIP은 보존한다.

## 선택과 범위

선택 정본은 `00_SYSTEM/GLOSSARY_PIPELINE.json.knowledge_bundle`이다.
논리 data root 아래의 `LEXICON/knowledge-bundles/genos-full-20260915-v1/manifest.json`과
그 SHA256이 모든 소비자와 ZIP의 동일 입력을 고정한다. 원천 선택은
`00_SYSTEM/GLOSSARY_KNOWLEDGE_SOURCES.json`의 경로·SHA256 목록이다.

| 입력/원장 | 보존 내용 |
|---|---|
| 기존 기본 사전 | 113,458개 항목, 정의 후보, 공식 관계 95,043건, 문서 출현 및 근거 |
| 전체 원천 그래프 | FIBO 16,665 / Wikidata 22,562 / NLSH 445,605개 노드, 관계 원장 7,142,320건 |
| 한국어 번역 보정본 ADR-0406 | 원천/재사용 한국어 52,592단위, 모델 번역 43,349단위, 원어·언어·모델·호출 계보 |
| ID 관계 원장 ADR-0404 | 개념 대응 79,636건, URI 별칭 445,611건, 원천 관계·경로·14개 검토 작업과 결과/실패 |
| 법률용어 관계 DRAFT | 원천 95,043건의 판정, 연결 간선 48,581건과 보류·제외·동일항목 원장 전체 |
| 수집·해석 근거 | 원천 관계 수집 응답, 번역/검토 호출 기록, 로컬 해석 위키·원문·원장 |

관계 원장은 RDF 속성/라벨 진술과 매칭 후보를 포함한다. 714만 건 전부가 승인된 법률관계인
것은 아니다. 전 세계 Wikidata 덤프나 Wikipedia 본문 전체를 새로 수집한 범위도 아니다.
FIBO/Wikidata의 `shared_external_concept_candidate` 11,458건은 원천 선언과 구분한다.
데이터 간 겹치는 공식 관계는 원천/가공 원장별로 보존하며 건수를 단순 합산하지 않는다.

## 실제 호출 연결

```text
pipeline.py build-all
  → glossary knowledge check (선택 manifest와 전체 파일 해시)
  → 기존 glossary review complete (근거 결속 검토, 미완료 exit 3)
  → build-data-stages --stage all --glossary-dir <검토된 사전>
    → 원문 구조화 캐시
    → glossary_linking.project
      → 기본 사전 + knowledge lookup의 전체 표기에서 문서 출현 탐색
      → links.sqlite의 knowledge_catalogue_link에 대응 전체 기록
      → authoring_job.input_json.dictionary_lookup.matches[].definitions.knowledge
    → 기존 의미 추출/분할/검토 → 임베딩·문서별 DRAFT
```

`build-data-stages`를 직접 실행해도 동일 기본 사전의 binding/project가 이 묶음을 읽는다.
묶음의 base dictionary hash가 다른 사전이면 거부한다. 기존 사전에서 검토해 만든 새 초안은
`source_glossary_sha256`으로 결속한다. 명시된 루트 밖의 독립 테스트 사전은 별도 계약이다.

각 문서의 링크 캐시와 의미 구축 계획에 묶음 manifest/코드 해시를 기록한다.
변경된 관계/번역 세대는 링크·의미 작성부터 새 run-id로 재구축하며 원문 파싱 캐시는 유지한다.
묶음 파일 누락·손상은 모델 호출 전에 실패한다. 이전 원문 PC나 연구 실행기 import 없이 읽는다.

## 저장 계약과 모델 입력의 범위

`graph.sqlite`, `translations.sqlite`, `identity.sqlite`, `legal.sqlite`는 기존 원장을
새 디렉터리에 복사한 뒤 조회용 SQLite index만 추가한다. 원천 행/ID/predicate/payload는
변환하지 않는다. `lookup.sqlite`는 모든 원천 표기와 한국어 번역 명칭을 검색하기 위한
파생 색인이다. 명칭이 같아도 서로 다른 원천 ID를 합치지 않는다.

`manifest.json`의 입력 해시는 원본 파일, 출력 해시는 인덱스가 추가된 새 파일을 가리킨다.
추출/검토의 법률 의미 출력은 기존 `LEGAL_SCHEMA.json`의 단일 스키마를 그대로 사용한다.
이 묶음의 원천 predicate를 LegalRelation enum으로 조용히 변환하거나 canonical로 승인하지 않는다.

전체 데이터는 파일/조회 API에 유지한다. 모델 입력은 기존 문서 청크 예산에 맞춰 표기당
출처별 개념 최대 3개, 개념당 관계 6건, 정의·번역 일부와 원장 ID를 전달하고 전체 건수·잘림을
표시한다. 같은 표기에 연결된 후보 전체는 `knowledge_catalogue_link`에서 추적할 수 있다.
다른 문서의 정의를 해당 문서의 적용 규정으로 취급하지 않는다.
번역의 미검토 상태, 대응의 UNREVIEWED/DEFERRED, 법률 관계의 HELD 및 원천 관계를 구분한다.
로컬 해석 위키는 근거 자료로 함께 보관하며 Wikidata 개념으로 합치거나 법령 원문으로 취급하지 않는다.

## 확인 명령

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py glossary knowledge check
.venv/bin/python -B 06_TOOLS/pipeline.py glossary knowledge lookup --term 증권
.venv/bin/python -B 06_TOOLS/pipeline.py glossary knowledge inspect --source wikidata --node-id Q169489 --limit 100 --offset 0
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id genos-full-001 --check-only
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id genos-full-001 --max-review-jobs 100 --execute
```

`inspect`의 next_offset으로 양방향 원천 관계 전체를 조회할 수 있다. `lookup`의 출력 제한은
적재 누락이 아니다. 새로운 수집 범위로 재구축할 때는 새 입력 목록/새 output을 지정한다.

## GENOS 반입·검증·롤백

코드, 기본 사전, 미실행 검토 계획과 이 묶음을 모두 같은 ZIP에 담는다.
RAW 문서와 Python wheel/OCR 모델, 현장 모델 접속정보는 별도 준비한다.
현장에서는 새 디렉터리에 풀고 해시를 검증한 뒤 위 명령을 사용한다. 기존 결과를 덮어쓰지 않는다.
중단은 같은 명령으로 재개한다. 코드/데이터 변경에는 새 run-id를 쓴다.
롤백은 이전 코드 스냅샷/묶음 설정으로 복귀하고 기존 결과를 보존하는 방식이다.

통합 RAG 세대 활성화와 피드백 재구축은 이 문서 작성 배선과 별개다.
기존 `pipeline.py check`의 `semantic_runtime/moleg_links.py` 등록 해시 불일치 역시 이번
소스 데이터 소비 연결로 승인/해결된 것으로 처리하지 않는다.
GENOS 현장 모델·내규·배포 성공은 아직 미검증이다.

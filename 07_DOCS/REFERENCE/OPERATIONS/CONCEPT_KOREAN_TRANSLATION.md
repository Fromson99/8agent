# FIBO·Wikidata 한국어 번역 DB

상태: ADR-0405 격리 후보. 실제 처리 건수·완료 여부는 아래 DB와 실행 보고서를 따른다.
기본 MAIN CLI, 용어집 current_draft, 운영 RAG는 이 DB를 자동 선택하지 않는다.

## 입력과 역할

- 입력: ADR-0403의 hash 고정 `relations.sqlite`에서 FIBO 16,665개, Wikidata 22,562개 노드.
- 범위: 이미 수집한 공개 그래프. 전 세계 Wikidata 덤프나 Wikipedia 본문 수집이 아니다.
- 단계: 용어집 공통 기반의 외부 원천 구조화 후 번역 작성. 지식그래프 관계 원문은 그대로 보존한다.
- 출력: 논리 data root의 `LEXICON/concept-translations/adr-0405-run-001/translation.sqlite`.
- 소비자: 이 후보의 `lookup`, `inspect`. 후속 의미 매칭은 번역 검색 후보와 원문 정의를 함께 소비해야 하며 이번 실행은 의미 대응을 승인하지 않는다.

`security`라는 문자열을 전역 한국어 단어 하나로 매핑하지 않는다. `source + node_id`를 유지하고,
원천 정의의 각 단위를 독립 번역한다. 같은 한국어 명칭이 나와도 노드를 병합하지 않는다.
서로 다른 정의 단위는 자동으로 서로 다른 의미가 되지 않는다.

## 한국어 보존과 번역

1. ko 언어 태그가 있는 원천 이름·별칭은 모두 보존한다.
2. 원천에 한국어 이름이 없으면, 결정적으로 고른 대표 명칭 1개를 정의·전체 별칭 문맥과 함께 번역한다.
   모든 외국어 별칭을 별도로 번역하는 범위는 아니다. 외국어 별칭 원문은 label 표에 모두 남아 검색할 수 있다.
3. 정의별 원문과 배열 위치를 보존한다. 상위 수집 그래프는 정의 언어 태그를 보존하지 않았으므로,
   한글 포함 정의는 `Hangul presence heuristic`을 명시하고 원문 그대로 사용한다. 공식 언어 판정으로 바꾸지 않는다.
4. 나머지 정의는 각각 전문을 한국어로 번역한다. 번역문을 새 원천 정의로 덮어쓰지 않는다.
5. 이름만 있는 노드는 정의를 만들지 않고 검토 필요로 둔다. 이름·정의 모두 없는 207개 노드도 삭제하지 않는다.
6. 모델 번역은 모두 미검토 파생물이다. needs_review=false도 번역 품질·법률 의미 승인이 아니다.

영문·한국어 식별자가 섞인 정의의 자동 언어 판정과 원천의 label/alias 역할 소실은 현재 입력 계약의 한계다.
다국어 정의를 정확한 언어별 공식 번역으로 대응시키거나, 한국어 법령 개념에 자동 치환하지 않는다.

## 실행 명령

WSL 저장소 루트에서 실행한다. 실행기는 고정 후보 해시를 확인한 뒤 기존 pipeline.py의
`glossary translate` 분기를 주입한다. 기본 `06_TOOLS/pipeline.py`에는 아직 배선되지 않았다.

```bash
TRANSLATION_RUNNER=02_BACKEND/lawrag/research/experiments/concept_translation_0405.py
TRANSLATION_STATE=01_DATA/LEXICON/concept-translations/adr-0405-run-001

PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate prepare \
  --config 04_EXPERIMENTS/ADR/ADR-0405-glossary-korean-translation-db/artifacts/config.json

PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate run --state "$TRANSLATION_STATE"
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate status --state "$TRANSLATION_STATE"
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate lookup --state "$TRANSLATION_STATE" --term 증권
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate inspect \
  --state "$TRANSLATION_STATE" --source wikidata --node-id Q169489
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate finalize --state "$TRANSLATION_STATE"
```

모델은 공통 `GeminiExperimentClient`의 `gemini-3.1-flash-lite`이며 공개 자료만 입력한다.
실제 키는 `.env` 또는 환경에서 읽고 원장에 기록하지 않는다. provider 자동 전환은 없다.
24개 개념/14,000문자 기준 묶음, 작업자 6개, 묶음당 최대 3시도를 사전에 고정했다.
문자 상한은 묶음을 나누는 기준이며 하나의 긴 개념을 자르는 기준은 아니다.

실패·형식 오류는 원응답과 함께 보존하고 같은 고정 입력으로만 재시도한다.
정확한 요청 unit ID 집합과 응답이 다르면 해당 묶음 전체를 반영하지 않는다.
완료 작업은 재호출하지 않는다. 중단 직전 저장된 정상 응답은 로컬 검증 후 복원한다.
입력·코드·모델 정책·프롬프트가 달라지면 현재 DB를 재개하지 않고 새 세대를 사용해야 한다.
현재 다른 세대 사이의 번역 캐시 이관은 구현하지 않았으며 동일 동결 세대의 재개를 지원한다.

## DB 계약

| 표 | 내용 |
|---|---|
| concept | 원천 노드 ID, 원 payload, 해시, 정의 수 |
| label | 원천의 이름·별칭·언어 태그 |
| edge | 원천의 관계 ID·방향·predicate·한정/근거 payload |
| unit | 번역 대상 원문 단위, 위치, 처리 상태, 조회용 한국어 텍스트 |
| translation | 모델 번역 결과와 입력 해시·모델·프롬프트·호출 영수증 |
| batch / attempt | 동결 요청, 처리 상태, 시도별 원응답 경로·실패 |

원천 ko 텍스트는 unit에서 `NATIVE`, 모델 결과는 `TRANSLATED`다. 원문 없는 개념은
concept에 남고 unit이 없다. `translation_processing_complete`는 처리 작업 완료이며,
`semantic_review_complete`와 `runtime_promoted`는 false다.

`lookup`은 한국어/원문 명칭 정확 일치를 우선하고 없으면 정의·명칭 부분 검색을 제공한다.
검색 결과 수 제한은 화면 출력 제한이며 원천 적재 범위 제한이 아니다.
`inspect`는 해당 개념의 입력·출력 관계 전체와 이웃 한국어 이름을 보여준다.
없는 이웃 노드는 원래 ID로 남기며 관계를 삭제하지 않는다.

`subClassOf`, `P279`, `P31`, 부분·사용·반대 관계와 OWL 제한식은 원 predicate/payload를
그대로 보여준다. 상하위 관계 하나로 변환하거나 한국 법률 적용 관계로 승인하지 않는다.

기존 graph의 edge에는 원천 유래 관계 135,372건 외에 이전 매칭기가 만든
`shared_external_concept_candidate` 11,458건이 포함된다. 모두 원래 predicate로 보존하지만,
후자는 원천 기관이 선언한 동의어나 상하위 관계가 아니다. 조회에서도 자기 노드 후보 기록으로
읽어야 한다. 상하위 표지 관계는 FIBO subClassOf 4,222건과 Wikidata P279 14,854건이다.

## 검증과 롤백

원천 graph hash, 노드 payload, 관계 전체 ID·양 끝·predicate·payload 양방향 차집합,
SQLite 무결성과 외래키를 검사한다. 완료 영수증은 미완료·실패 묶음이 없을 때만 발행한다.
모델 번역의 정확도는 별도 원문 대조가 필요하며 처리 성공률과 다르다.
실행 상태는 progress.json, run-report.json, validation.json, completion.json으로 구분한다.

이 후보를 소비하지 않으면 이전 MAIN이 유지된다. 원문 그래프와 완료된 ADR·번역 DB는
삭제하거나 덮어쓰지 않는다. 제품 반영은 의미 검토·독립 검증·명시적 선택 절차가 별도로 필요하다.

[ADR-0405](../../../04_EXPERIMENTS/ADR/ADR-0405-glossary-korean-translation-db/README.md)

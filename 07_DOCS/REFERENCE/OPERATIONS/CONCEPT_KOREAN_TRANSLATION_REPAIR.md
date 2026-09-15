# FIBO·Wikidata 한국어 번역 DB — 보정 세대

2026-09-15: 이 완료본은 [전체 관계 묶음](GLOSSARY_KNOWLEDGE_BUNDLE.md)의 명시 입력으로
복사되어 기본 문서 작성 파이프라인에서 소비된다. 아래 격리 실행기는 기존 완료 이력을
보존하며, 새 기본 소비자는 외부 모델 실행기를 import하지 않는다.

ADR-0406은 ADR-0405의 성공 번역 42,163개와 원문 그래프를 재사용하고,
응답 실패 242개 단위 및 영어 설명에 한글이 섞여 번역에서 빠진 944개 정의를 보정한다.
301개 보정 요청을 모두 처리해 모델 번역 43,349개와 원천 한국어·표기 재사용 52,592개를
저장했다. 처리 상태와 보존 검증은 이 세대의 `repair-validation.json`과 `completion.json`으로 확인한다.

## 조회·재개

```bash
TRANSLATION_RUNNER=02_BACKEND/lawrag/research/experiments/concept_translation_0406.py
TRANSLATION_STATE=01_DATA/LEXICON/concept-translations/adr-0406-run-001

PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate status --state "$TRANSLATION_STATE"
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate lookup --state "$TRANSLATION_STATE" --term 증권
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate lookup --state "$TRANSLATION_STATE" --term 담보
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate inspect \
  --state "$TRANSLATION_STATE" --source wikidata --node-id Q169489

# 미완료 작업 재개. 완료 영수증이 있으면 hash 확인 후 호출 없이 반환한다.
PYTHONPATH=02_BACKEND .venv/bin/python -B "$TRANSLATION_RUNNER" glossary translate run --state "$TRANSLATION_STATE"
```

이 실행기는 고정 후보를 기존 pipeline.py의 glossary translate 분기에 명시적으로 주입한다.
기본 MAIN CLI·current_draft·RAG·GENOS 배포는 이 세대를 자동 선택하지 않는다.
상세 데이터 계약과 첫 세대 실행은 [원래 가이드](CONCEPT_KOREAN_TRANSLATION.md)를 참고한다.

## 언어 처리 보정

Wikidata 원응답 46개에서 정의 32,120건의 실제 `xml:lang`을 원문·응답 hash와 함께 복원했다.
한국어 문자가 포함됐다는 이유로 영어 정의를 그대로 두지 않는다. 원천 언어가 외국어인
944개 혼합 언어 정의를 새로 번역한다. ko 태그인데 실제 텍스트가 라틴 문자뿐인 기존 번역은
삭제하지 않고 원천 언어 태그를 함께 보존한다. 원천 태그 자체가 번역 품질 증명은 아니다.

`definition_language` 표는 각 unit ID의 언어 태그·원응답 위치·해시를 저장한다.
원문 정의, 배열 위치, 외부 개념 ID를 바꾸지 않는다. `repair_unit`에는 변경 전 파생 상태와
보정 이유가 남는다. 부모의 작업·시도 원장은 `inherited_batch`, `inherited_attempt`,
`inherited_meta`에 보존하며 새 `batch/attempt`는 보정 호출만 집계한다.
부모의 호출 원문도 새 세대에 동일 내용으로 보관하고 부모 DB는 그대로 보존한다.

실패 242개 단위는 각각 단독 요청으로 재시도한다. 언어 보정 944개는 16개 개념 단위로 묶는다.
모델·번역 프롬프트는 부모와 같다. 모든 응답은 정확한 unit ID 집합을 확인한 뒤 저장한다.
번역문을 근거로 의미 동일성을 승인하거나 원천 관계를 재분류하지 않는다.

## 원천 관계 활용

- FIBO·Wikidata 원천 노드 39,227개를 ID별로 유지한다.
- 기존 그래프 관계 원장 146,830건은 원천 유래 135,372건과 과거 같은 개념 대응 후보 11,458건을 구분한다.
- FIBO subClassOf 4,222건, Wikidata P279 14,854건은 원래 ID·방향·근거로 조회한다.
- 한국어 이름이 같아도 개념을 합치지 않는다. `Security`/`Collateral` 및 Wikidata의 증권·보안·담보는 각각 별도 ID다.
- 모델 명칭·정의 번역과 원천 한국어 텍스트를 구분한다. 원문 없는 207개 노드, 정의 없는 명칭과 불확실성도 보존한다.

한국어 조회 결과를 후속 의미 검토의 후보로 사용할 수 있지만, 현행 glossary review가
자동 소비하는 배선은 없다. 적용할 때는 원문 정의와 검토 근거를 다시 연결해야 한다.

## 검증·보존

최종 검사는 부모 성공 번역 불변, 보정 1,186개 단위 완료, 전체 unit의 미완료/실패 0,
원천 노드·관계 보존, DB 무결성·외래키, 재개 추가 호출 0을 확인한다.
번역 품질의 독립 평가나 한국 법률상 개념 동일성 검증과 다르다.
되돌릴 때는 이 후보의 소비를 중단한다. 부모 DB·원문·완료 ADR을 삭제하거나 덮어쓰지 않는다.

[ADR-0406](../../../04_EXPERIMENTS/ADR/ADR-0406-glossary-translation-language-repair/README.md)

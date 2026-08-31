# Opus 5 question-only Golden 61

검색·system prompt·조문·Wiki 없이 CM/FSC v2 골든 질문 문자열만 Opus 5에 넣는 격리형
최종답변 benchmark다. 모델의 내재 지식 상한을 보는 특이 benchmark이며 제품 후보 평가나
retrieval 성능 평가가 아니다.

- benchmark ID: `legal-final-answer-opus-question-only-golden-61-v1`
- 정의: [benchmark.json](benchmark.json)
- 최초 run: [run-001.json](runs/run-001.json)
- 결정·질문별 원문: [ADR-0100](../../docs/adr/ADR-0100-opus-question-only-golden-61/README.md)

최초 run의 strict dual-judge 결과는 33/61(54.1%)다. 이 숫자는 같은
`comparability_key`를 가진 후속 run과만 직접 비교한다.


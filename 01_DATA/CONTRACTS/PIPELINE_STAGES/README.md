# 다섯 단계 스키마의 합성 예시

실제 법률 원문, 사용자 답변, 승인 또는 모델 응답이 아니다. 정의한 필드와 단계 사이 연결을 확인하기 위한 예시다.

`examples.json`은 계약 이름과 파일을 연결한다. `context.json`은 검증 대상의 정확한 canonical/query/template/cards와
원문·참조 파일 바이트를 제공한다. 이 context는 검증용 묶음이며 새로운 제품 데이터 스키마가 아니다.
개별 `*.json`에서 실제 필드 값을 읽을 수 있다.

| 단계 | 파일 |
|---|---|
| 입력 | source.json, correction.json |
| 처리 | observation.json, review.json, canonical.json |
| 적재 | generation.json, projection.json |
| RAG | question.json, templates.json, query.json, hits.json, cards.json, answer.json |
| 피드백 | feedback_event.json, feedback_proposal.json |

`query.json`은 카드 두 개를 생성한 경우다. 첫 카드는 DB 근거를 조립하고, 두 번째는 필요한 사실이 없어
`bundle=null`로 반환한다. `answer.json`은 두 번째 카드의 미해결 상태까지 보존한다.

`correction.json`은 합성 OCR 오기 “기곤”을 “기관”으로 고친 전후 대응을 보인다.
`review.json`과 receipt 참조는 형식 예시이며 인증된 검토자의 승인이 아니다.

검증: `.venv/bin/python -B 06_TOOLS/AUDIT/pipeline_data_contract.py`
설명: [단계별 스키마](../../../00_SYSTEM/STAGE_SCHEMAS.md).

# 기존 용어 ID와 개념 대응을 이용한 관계 연결 계획

상태: 아래 설계를 바탕으로 [ADR-0404](../../../../04_EXPERIMENTS/ADR/ADR-0404-glossary-id-concept-linking/README.md)에서 ID·URI 별칭 해소, 대응 중복 정리, 근거 검토와 외부 관계 연결 게이트를 구현·실행했다. 공식 관계95,043건 보존, 고유 대응79,636건, 한자 충돌413건 보류. 공개 대응14건 검토는 SAME4/DIFFERENT7/UNKNOWN2/계약실패1이며 이번 표본의 새 외부 직접 관계는0건이다. 이웃을 이용한 새 대응 후보 확장은 미구현이며 제품 MAIN은 변경하지 않았다. 아래 단계 설명은 전체 설계이고 완료 범위는 ADR의 실행 기록을 따른다.

## 확인한 기준

- 작성 초안: `01_DATA/LEXICON/glossary-v1/boundary-20260914-v3/dictionary.sqlite`.
- 외부 원천: 완료된 ADR-0403의 `artifacts/run-001/relations.sqlite`. 완료 산출물은 수정하지 않는다.
- 기존 항목 113,458개 중 공식 관계의 양 끝에 등장하는 항목은 87,824개다.
- 공식 관계 95,043건은 이미 원천 ID에 연결되어 있다. 동의어 14,789, 반의어 2,799, 상위어 5,842, 하위어 7,716, 연관어 63,897건이다. 코드와 원래 방향을 보존한다.
- `definition_candidate.match_kind=SOURCE_ID` 연결은 20,907건 / 8,377항목이다. 이는 ID로 연결된 정의 후보 수이며 정의의 충실성·단일 의미·현재 법적 적용 승인 수가 아니다.
- 현재 초안의 `meaning`과 `membership`은 각각 0행이다. 이미 승인된 출처 간 의미 대응표가 있다고 전제할 수 없다.
- ADR-0403의 외부 `mapping`은 표기 일치 기반 `UNVERIFIED_MAPPING`이다. 원천의 관계가 정확해도 양 끝의 대응이 틀릴 수 있다.
- NLSH `owl:sameAs`에서 확인한 사례는 `resource/KSH...`와 같은 기관의 `subject/이름...` 주소를 연결한다. 이 사례만으로 MOLEG·NTS·Wikidata 사이의 대응이라고 해석할 수 없다.

## 이미 가능한 ID 탐색

현재 공식 관계를 ID로 조회하면 다음 원천 주장을 얻는다. 이름으로 새 관계를 추론한 결과가 아니다.

| 시작 ID / 표시 | 원천 관계 | 도착 ID / 표시 |
|---|---|---|
| `moleg:knowledge_terms:298317` / 전환사채 | 동의어 | `moleg:everyday_terms:73413` / CB |
| `moleg:knowledge_terms:298317` / 전환사채 | 상위어 | `moleg:everyday_terms:5389` / 사채 |
| `moleg:knowledge_terms:292371` / 자기주식 | 상위어 | `moleg:everyday_terms:1691` / 주식 |

`moleg:knowledge_terms:1465817` 보통주식과 주식의 원천 관계는 연관어다. 이름이나 상식만으로 이 관계를 하위어로 변경하지 않는다.

## 적용 순서

1. **기존 ID와 공식 관계를 탐색의 기준으로 사용한다.** 선택된 초안의 `entry.id`를 기준으로 `official_relation`의 양 끝을 조회하고 `SOURCE_ID` 정의 후보를 우선 제공한다. 항목 ID를 의미 ID로 간주하지 않는다.
2. **원천 URI의 별칭을 해소한다.** 출처·네임스페이스·원천 버전에 결속된 명시적 ID 링크를 별도 대응표에 보존한다. `sameAs` 양 끝의 자원 종류와 출처를 확인하고, 충돌하거나 대상이 없는 경우 미해결로 남긴다. 문자열에서 ID를 추측하거나 모든 URI를 일괄 소문자화하지 않는다.
3. **출처 간 개념 대응을 한 번 검토해서 재사용한다.** 원천에 제공된 공식 교차 ID를 우선 후보로 사용한다. 없는 경우 기존 표기 후보, 정의 검색, 확인된 이웃의 인접 개념을 모아 후보를 만든다. 이웃 관계의 일치는 후보 선정 근거이며 동일 의미의 증명은 아니다.
4. **대응이 검증된 양 끝에만 외부 관계를 연결한다.** 직접 원천 ID 관계와 검토된 출처 간 투영을 구분한다. 원천 predicate·방향·원문 edge ID와 양 끝 대응의 근거를 함께 저장한다. 하나라도 미확인이면 검토 후보로 남긴다.
5. **기존 검토 경로에 연결한다.** `pipeline.py glossary`와 `glossary_review.prepare`에 후보 입력 계약을 연결한다. 현재 이 함수는 ADR-0403 산출물을 자동 소비하지 않는다. 신규 대응 검토 결과는 기존 SAME/DIFFERENT/UNKNOWN 계약을 사용하고 정본 `meaning/membership` 자동 승인은 하지 않는다.

## 필요한 저장 계약

기존 `entry`, `official_relation`, 정의 후보는 보존하고 다음 역할을 추가한다. 아래는 제안 필드이며 현행 구현 완료를 뜻하지 않는다.

| 역할 | 필수 기록 |
|---|---|
| 원천 ID 별칭 | source, source_version, original_uri, canonical_uri, predicate, evidence_id, status |
| 항목·의미 후보와 외부 개념 대응 | entry_id, sense/evidence identifier, external_source, external_concept_id, mapping_basis, identity, evidence_hash, review_receipt |
| 외부 관계의 우리 항목 연결 | source_entry_id, target_entry_id, original_predicate, source_edge_id, left_mapping_id, right_mapping_id, status |
| 미해결 원장 | entry_id, candidate_concept_id, reason, missing_evidence, source_version |

대응 검토 결과는 항목·정의·원천 버전·모델/프롬프트/스키마 해시에 결속한다. 정의나 원천 개념이 바뀌면 기존 승인을 조용히 재사용하지 않는다. 같은 항목이 여러 의미를 가지면 의미 단위로 분리하거나 미확인으로 남긴다.

## 후보 수와 검토 비용

모든 항목쌍을 검토하지 않고, 우선 항목과 외부 개념의 대응을 검토한 뒤 원천의 인접 관계를 조회한다. 검토 단위는 관계쌍마다 중복 등장하는 동일 대응이 아니라 고유한 항목·의미 후보↔외부 개념이다. 확정 가능한 대응 수와 비용 감소량은 아직 측정하지 않았다.

## 검증·실행 경계

- 전환사채–CB, 전환사채–사채, 자기주식–주식의 기존 ID 관계와 근거 보존.
- 금융 감자↔potato, 담보↔보안과 같은 동음이의·영문 다의성 대응의 승인 차단. 한자 충돌을 별칭 하나가 아닌 개념 전체에서 검토.
- URI 별칭 해소를 새 용어 관계나 출처 간 의미 일치로 집계하지 않음.
- 관련어·상하위·부분 관계를 동일 개념으로 병합하지 않음. 여러 단계를 지난 관계를 직접 관계로 위장하지 않음.
- 미연결 항목과 미확인 대응을 보존하며, 정답 관계의 회수율 개선은 별도 고정 평가로 검증.
- 구현·효과 비교는 완료 ADR-0403을 부모로 새 ADR 선점과 후보 동결 후 진행. 기존 완료 자료와 MAIN 포인터는 보존.
- 실제 모델 검토는 환경별 정책을 따른다. 현재 Codex는 GENOS 접근 불가. 외부 공개 데이터 실험을 할 경우 전송 범위 확인 및 Gemini 공통 실험 클라이언트를 사용한다.

입출력 흐름: 선택된 용어집 + 고정 원천 그래프 → ID 별칭 해소 → 개념 대응 후보·검토 → 근거 있는 관계 연결 → 기존 용어 검토 초안. 후속 문서–용어 연결과 RAG 반영은 검증된 새 초안 선택 이후의 별도 단계다.

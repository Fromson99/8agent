# 코드 후보 추출 → LLM 의미 검토

새 오프라인 후보: ADR-0252 source-ids rev-001.
실행 묶음: `09_ARTIFACTS/HANDOFF/ADR-0252/genos-code-first.tar.gz`.
기존 [prepare/run/handoff 사용법](GENOS_GROUNDED_AUTHORING.md)을 새 묶음에서 사용한다.
모델·revision·endpoint와 새 큐 경로를 지정해야 한다. 구버전 큐를 덮어쓰거나 직접 열지 않는다.

```text
원문 DB 대조
 → 코드: 블록·용어·표면 패턴 구간, 정확한 인용/좌표, 고정 source_span_id
 → 코드: 정의/이하별칭/범위표현/단서표현/명시참조/수치 후보
 → LLM: 후보와 원문 대조, 의미 graph 구성, 근거 구간 ID 선택
 → 코드: 선택 ID를 원문 인용/좌표로 복원, SSOT 및 coverage 검증
 → 별도 LLM: 주체·조건·결과·단서·정의 범위/연결의 누락·왜곡 검토
 → DRAFT 인계/적재
```

LLM Evidence 출력은 `id`, `source_span_id`만 허용한다. coverage도 코드가 만든 블록 구간 ID를
선택한다. 인용문·start/end·문서 ID·해시는 모델이 만들지 않는다. 알 수 없는 ID는 거절한다.
정의 용어의 부분 구간 외에 모든 블록 원문 구간을 제공하므로 패턴 미탐지 의미도 모델이 원문으로 검토할 수 있다.

후보는 표면 패턴이며 법률적 정의·조건의 확정이 아니다. 정의 본문이 여러 호·목으로 이어지는 경우,
'이 장에서'와 같은 범위, 외부 법령 정의 인용, 포함/제외는 모델이 원문과 구조를 함께 검토해야 한다.
별칭을 전역 동의어로 자동 등록하지 않는다. 기존 정의 패턴을 재사용하고 한 글자 별칭 '법'을 추가 지원했다.

확인한 유사 코드: 이전 generation의 `lawrag/core/defpatterns.py`, `lawrag/core/rag/definitions.py`,
`lawrag/ontology/definition_projection.py`. 이들은 현재 semantic_runtime에 자동 연결된다는 뜻은 아니다.
후자의 projection은 검증된 graph를 소비하는 단계이며 원문 추출기를 대체하지 않는다.

검증: 합성13개 단위검증 통과. 실제 코스닥시장 상장규정 제2조103블록에서 인용정의 후보49건,
별칭 후보14건, 명시참조31건 탐지. 코드가 만든221개 구간은 모두 원문과 일치했다.
이는 탐지 건수이며 정답률/전수 recall이 아니다. 실제 LLM의 정의 의미 정확도는 아직 재측정하지 않았다.
MAIN 변경 없음. 이전 자동 재추출/누적예산/재시작 복구는 유지한다.

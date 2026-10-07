# A→B→C shortcut 사슬 재사용 가능성 감사 — 2026-09-30

이 문서는 기존 코드와 완료된 로컬 native journal의 저장 계약을 읽어 확인한 결과다.
새 모델 호출·replay·성능 비교는 하지 않았다. 실제 운영 실행 재개 기능의 검증 결과가
아니다.

## 실제 저장된 것

로컬 journal 29개는 모두 `COMPLETED`다. 그중 `SOURCE_RECALL_POOL`과
`BOUNDED_SOURCE_SELECTION`이 있는 18개를 확인했다. 회수 풀은 최소 2, 중앙값 2,
최대 237개 source이며, 18개 모두 기록된 `selected_for_read`가 `read_complete`에
포함됐다. `SOURCE_RECALL_POOL`에는 읽은 source ID, 경로, 질의 계획, 읽기 완료 여부가
남지만 fulltext가 반환한 **전체 순위 목록**은 18개 모두 없다. 첫 선별의 `model_view`에는
읽은 풀의 후보 카드 목록이 있고, `evidence_unit`/`evidence_span`에는 그 풀에서 완독한
원문이 있다. `model_attempt`에는 당시 실제 모델 요청·응답이 남는다.

`run.binding_json`은 원문 generation/store SHA, 색인·pipeline·profile hash, 허용 범위,
모델과 공개 반출 승인을 결속한다. `entity_version`/`dependency`의 무효화는 판단
entity에 적용된다. B 검색 순위·C 선택·후속 행동 각각을 독립적인 재사용 단계로
모델링한 사슬 DAG와 중간 단계부터 실행하는 API는 없다. `stage_artifact` 무효화도
일부 상황에서 retrieve/select/assemble/answer 전체를 무효화하므로 A→B→C만 정밀하게
되감는 계약을 대신하지 않는다.

## 네 가지 경로의 현재 판정

| 상황 | 현재 재료 | 아직 필요한 기능 |
|---|---|---|
| C가 틀리고 B의 **읽은 풀**은 충분 | 후보 카드·완독 원문·이전 선택 판단이 journal에 존재 | 같은 세대·범위·권한 검증 후 새 C 선별 view를 만들고 C 이후만 무효화하는 실행기 |
| 40개가 fulltext 순위에만 있었고 아직 읽지 않음 | 전체 순위 40개의 exact snapshot이 없음 | B 결과 ID·순위·query·코드/색인 hash를 새 불변 snapshot으로 저장하고 필요한 원문을 새 READ |
| B가 부족해 fulltext부터 다시 해야 함 | 기존 검색 계획과 읽은 풀은 있음 | B 재실행 사유·새 후보와 기존 후보의 합집합/폐기 근거·하위 무효화 |
| A 연결이 틀리거나 원문·권한이 바뀜 | 세대/범위/hash는 journal에 있음 | A부터 재매칭하고 영향받은 하위 단계를 정밀 무효화하는 의존 계약 |

따라서 “후보 40개 중 다시 선택”은 **그 40개가 당시 완독해 기록된 풀인지**와
**검색 순위에만 잠깐 존재했는지**에 따라 다르다. 앞 경우에는 원문 재사용 재료가 있고,
뒤 경우에는 현재 journal만으로 동일 후보 40개를 복원할 수 없다. 예전 답변이나 선택을
정답으로 자동 승인해서는 안 된다.

ADR-0576의 합성 GUIDE 직접 회수는 fulltext 0회라는 메커니즘을 보였고, ADR-0586의
공개 두 사례는 경로 단위 사전 읽기를 보였다. 어느 쪽도 임의의 B/C 중간 단계 재실행을
구현하거나 전체 시스템의 속도 개선을 입증하지 않았다. ADR-0575의 온라인 통합은
모델 호출 17→12에도 평균 지연 약 25.0→35.5초로 늘어 Rejected였다.

후속 구현의 최소 계약은 B 후보 snapshot에 `ranked IDs + 순위 + 질의/필터 + 각 source의
hash/세대 + 당시 내용 제시 여부`를 기록하고, C에는 `부모 B snapshot hash + 실제
제시 입력 + 선택/기각 사유`, D에는 `부모 C + 행동 결과`를 기록하는 것이다. 각 단계의
실패 사유를 `근거 불일치 / 요구 누락 / 후보 부족 / 연결 불일치 / 세대·권한 변화`로
구분해야 가장 가까운 유효 조상에서만 다시 실행할 수 있다.

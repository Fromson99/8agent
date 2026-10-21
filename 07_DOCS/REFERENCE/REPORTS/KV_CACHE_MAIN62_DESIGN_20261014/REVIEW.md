# KV 캐시 설계의 자체 검토

검토 대상은 [PLAN.md](PLAN.md)다. 같은 작성자가 선택 MAIN62의 코드·복구 기록과 설계를 대조했다. 독립 에이전트 검토나 실제 모델 성능 인증은 아니다.

판정은 **좁은 후보로 구현 가능하며, 품질·복구·시간 보존 검증 후에만 도입 가능**이다. 새 입력 순서의 실제 개선율은 미산정이다.

| ID | 발견사항 | 설계에 반영한 조치 | 남은 확인 |
|---|---|---|---|
| R01 | 이전 설명의 ID 안정화는 참조 mapping·schema·원장에 영향을 줌 | 첫 후보에서 ID/배열/원문 누적 변경 제외 | 현재 mapping으로 어느 길이까지 prefix가 유지되는지 후속 측정 |
| R02 | 보정 메시지를 새 role/다중 메시지로 나누면 원장 consumer와 교정 계약에 영향 | 기존 메시지 수·role·full correction 유지 | 동일 오류·재개·부분 성공의 실제 소비자 검사 |
| R03 | 의미가 같은 JSON도 모델의 주의·출력은 달라질 수 있음 | deterministic 동등성과 실제 모델 품질을 별도 gate로 구분 | 같은 모델·조건의 실제 비교 |
| R04 | schema 변경은 추론 엔진에 따라 prompt KV에 직접 영향을 주지 않을 수도 있음 | schema 고정·축소는 첫 후보 제외, 실제 template 확인 | GENOS 엔진/버전·schema 처리 방식 |
| R05 | 전역 encoded 수정은 모든 저장 hash와 다른 경로에 파급 | 전송용 명시 opt-in helper로 한정 | 구 경로 request 바이트와 canonical digest 동일성 |
| R06 | profile에 default key를 추가하면 기존 binding을 바꿀 수 있음 | 선택 항목을 별도 검증, 구 profile 정규화/digest 유지 | 실제 strict validator·재개 검사 |
| R07 | 순서별 문자열은 달라도 canonical 객체 hash는 같을 수 있음 | semantic hash와 실제 content hash/layout을 구분하고 원장에 결속 | 정확한 문자열 대조·변조 거부 |
| R08 | sources 내부 metadata·ID가 변하면 상위 키 순서만으로 효과가 작음 | 개선 한계 명시, 추가 변경으로 결과를 부풀리지 않음 | cache 지표와 full pipeline 시간 |
| R09 | 단계별 고정 system이 달라 ASSESS→COMPOSE 원문 공유를 보장 못 함 | 같은 탐색 단계 반복을 첫 대상으로 한정 | 추후 단계 간 재설계는 별도 ADR |
| R10 | 캐시 적중률은 긴 입력·빠른 실패로도 높이거나 속여 보일 수 있음 | 총 토큰·성공/제한/실패·보정·p50/p95 함께 판정 | 분모·미보고 usage·실패 표본 포함 |
| R11 | 서비스/서버 변경을 한 번에 하면 원인이 섞임 | 앱 B와 서버 S를 독립 후보로 구분 | cold/warm·동시성·cache 오염 통제 |
| R12 | 롤백이 최신 복구까지 제거할 위험 | rollback target을 검증 기준 MAIN62 및 현장 대응본으로 고정 | 현재 포인터·receipt 확인, 진행 요청 binding 유지 |
| R13 | 이전 410/817 결과를 현재 성능 인증처럼 쓰기 쉬움 | 과거 계약 검사임을 명시하고 미래 회귀 기준으로만 사용 | 새 후보의 실제 실행 결과 필요 |
| R14 | 정책 꺼짐 상태에서도 공통 helper/계측으로 지연이 늘 수 있음 | disabled/비대상 바이트 검사, 실시간 prefix 비교 금지, cold gate 포함 | 오버헤드·AD/구축 회귀 |
| R15 | source category·scope가 바뀌는데 캐시를 유지하려고 옛 입력을 쓸 위험 | 현재 scope/원문/revision에서 만든 view만 사용 | 권한/판본/상태 변경 시나리오 |
| R16 | repository에는 profile의 hash만 있고 layout 값 전달을 신뢰하면 검증 공백이 생김 | 명시 layout을 내부 run binding에 결속하고 예약 인자와 저장 binding을 대조 | 클라이언트 임의 layout 거부·비대상 canonical 기대값 검사 |
| R17 | PIPELINE의 profile-tools-v5 참조와 서비스의 실제 v6 override를 혼동할 수 있음 | service.application의 profile-unified-v6 선택과 effective binding을 함께 확인하도록 명시 | 실제 서비스 입구의 선택 증거 |

문서에서는 최근 H01~H17 이력을 현재 미구현으로 재분류하지 않았다. ADR0777 구현 결과와 현재 code를 우선했고, 옛 sparse patch·schema 축소 후보를 무조건 재도입하지 않았다.

수치 자체 검토: 302는 이번 파일 대조 수, 410/817/수집 제외1은 과거 계약 기록이다. 새 실제 모델 호출은 없다. N05/N06은 조건부 산식이고 실측 개선율이 아니다. G01~G08의 무회귀는 동결 평가 범위에서 확인할 조건이며 미래 모든 입력의 보장이 아니다. 판정이 불충분하면 현행 유지다.

이 검토는 설계 내용의 보완이다. 구현 검사·실제 모델 비교·MAIN 선택·GENOS 배포는 아직 수행하지 않았다.

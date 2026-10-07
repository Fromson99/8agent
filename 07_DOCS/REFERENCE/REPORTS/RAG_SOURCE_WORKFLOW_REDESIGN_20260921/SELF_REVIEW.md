# 재설계 자체 검토

2026-09-21 · 설계 작성자가 코드·스키마·기존 실행 기록에 다시 대조했다. 별도 에이전트나 외부 전문가의 독립 검토가 아니다. [검토 대상·해시](REVIEW_BINDING.json), [설계](DESIGN.md), [사례표](CASES.md)를 함께 본다.

**구현 가능성 판정: 조건부 타당.** 기존 요청 세션·StageRunner·원문 Store·원장·outbox에 연결할 위치와 계약 변경 범위를 지정했다. 새 세션의 분리된 항목 검증, SourceUnitRef/slice, 목표별 답변 진입, 정책·게시 버전 dispatch를 실제 구현해야 한다. 문서 작성으로 실제 오류가 해결된 것은 아니다.

**성능·비용 판정: 판단 유보.** 구조적으로 제거하는 불필요한 실패 조건은 명시했지만 모델의 의미 정확성·필요 호출 수·입력량·GENOS 지연은 측정하지 않았다. 비용식과 기존 기록의 산술을 점검했으며 개선률이나 일정은 산정하지 않았다.

| ID | 심각도 | 검토한 문제/직접 근거 | 보완·판정 | 문서 반영 | 구현·검증 상태 |
|---|---|---|---|---|---|
| SR01 | 높음 | 현행 gateway는 protocol.validate가 전체 응답을 거부하므로 ‘항목별 저장’만 세션에 추가해도 도달하지 못함 | R06에 envelope/operation 2단계 검증, known server-owned field 정규화 allowlist, 독립/원자적 변경 경계를 명시. T44로 검사 | 반영 | 미구현·미실행 |
| SR02 | 높음 | 조 전체 선택과 정확 인용/전체 읽음이 혼동될 수 있음 | R02/R06에 unit 선택, basis_delivered_ranges, read coverage, claim basis를 분리. 잘못된 강조와 조 선택을 독립 저장 | 반영 | 의미 선택 정확성 미검증 |
| SR03 | 높음 | 외부 Request/Result는 닫힌 schema. 새 goal/게시 필드를 임의 삽입하면 기존 포트 실패 | Request 변경 없음, GoalRecord 내부 상태, Result의 term_agent 확장, publication은 별도 PublishedEnvelope/receipt로 규정 | 반영 | 실제 schema·bridge 회귀 필요 |
| SR04 | 높음 | 게시 완료를 immutable Result에 덮어쓰면 저장 hash/현재 검증이 충돌 | R11에 결과 snapshot과 publication receipt 분리. 현재 outbox 멱등 보존 | 반영 | 새 envelope validator 미구현 |
| SR05 | 높음 | feedback Event/Proposal target은 닫힘. HTTP는 선언된 stage를 통하지 않고 record_feedback 직접 호출 | R12/R13에 source-feedback-v2 별도 계약과 record_feedback/proposal_for/reader/engine의 실제 dispatch 변경 명시 | 반영 | feedback v2 미구현 |
| SR06 | 높음 | 새 SourceUnitRef를 기존 answer.claims.source_ids에 넣으면 기존 원문 조회와 연결되지 않음 | R09/R13에 실제 navigation source_id 매핑 유지. 비법령/미확정 구조는 SOURCE_REGION과 판본별 identity 사용 | 반영 | SourceUnitRef 해소·coverage 연결 검사 필요 |
| SR07 | 높음 | 현재 scope가 사용자 ACL을 대신하지 못하며 권한 축소 뒤 카드만 정제하면 다른 결과 필드에 내용이 남을 수 있음 | R11에 AuthorizationProvider 선행 조건·service-owner 개발 범위·최초 v5 전체 outbox 차단 유지 명시 | 반영, 선행 조건 유지 | 사용자 ACL·GENOS 현장 미연결/미검증 |
| SR08 | 높음 | 본문·ID를 한 카드에 묶어도 자유문 설명과 법적 의미의 오류를 모두 결정론적으로 감지할 수는 없음 | R05/R14에 명시 좌표 충돌과 의미 정확성 구분. 항·호/관련성/해석 품질은 별도 평가 | 한계 반영 | 실제 모델 품질 미검증 |
| SR09 | 중간 | UNKNOWN 전송·만료 deadline 재개에서 중복 과금/예산 초기화 위험 | R07/R10에 물리시도 전량 기록, 중복 커밋 차단, 원래 한도 내 명시재개 또는 새 run 계보 규정. exactly-once 모델 실행 보장하지 않음 | 반영 | 중단·동시성·실제 transport 검사 필요 |
| SR10 | 중간 | 선택적 강조 실패까지 모두 GOAL_MET을 막으면 출처 보존 목적과 다시 충돌 | R03에 요청 목표를 막는 필수 작업과 선택적 작업 구분. 사용자가 강조를 요구했을 때만 필수 | 반영 | 목표 판별/전체 흐름 검사 필요 |
| SR11 | 중간 | 과거27회/6실행 평균을 정상 성공 비용이나 예상 절감 기준으로 쓰면 조기실패가 숨겨짐 | N02에 실패 포함 평균4.5와 해석 한계 명시. 비용·지연 상한과 실사용을 분리 | 반영 | 비용·지연·일정 미산정 |

실행 가능한 새 API가 이미 있다고 주장하지 않는지, v4 journal CHECK에 새 상태를 넣는 이행 누락이 없는지, 기존 v2/v3/v4 및 선택된 frozen release가 자동 전환되지 않는지를 대조했다. 제안 함수/파일/API는 미구현으로 표시했다. 요구 R01~R14와 E01~E40, 설계 이슈 D01~D08의 연결은 문서 검사로 확인한다.

후속 완료는 source 선택·입력 전달·오류 복구·답변 검토·게시/원문 열기의 실제 계약 검사와 사전 동결 품질 평가로 판단해야 한다. 이번 산출물의 검증은 문서 링크·식별자·원본 해시·수치 산술에 한정하며 제품 테스트·외부 모델·GENOS 실행은 하지 않았다.

# 재설계의 사례별 수용 기준

2026-09-21 · **설계 명세이며 구현·테스트 실행 결과가 아니다.** 기존 E01~E40을 빠짐없이 연결하고, 전체 실행 계약8개를 더해 총48개 시나리오를 정의했다. P0는 보존·권한·진행·게시 등 도입 전 필수, P1은 기능·안내·연속 처리의 필수 확인 항목이다. 둘 다 도입 검증 대상이다.

[전체 설계](DESIGN.md) · [JSON 원장](CASES.json) · [기존 E 사례](../SOURCE_TIERS_EDGE_CASES_20260921/README.md)

각 사례의 검사는 허용된 모의 입력으로 설계한다. 실제 모델 의미 정확성·품질 평가는 별도 사전 동결 실험이며 이 표의 항목 수를 실행/통과 건수로 사용하지 않는다.

## 기존 엣지케이스40개

| ID·근거·우선순위 | 조건 | 처리·복구 | 통과 기준 | 사용자 결과 | 요구 |
|---|---|---|---|---|---|
| T01 / E01 / P0 | EMPTY 뒤 canonical 후보40개, READ0, 예산 남음 | 새 결과 전달 작업 생성; 다음 view에서 OPEN 선택 기회 제공; 동일 no_progress로 종료하지 않음 | 후보→전달→READ→원문 전달 순서와 canonical progress receipt 확인 | 미열람 수와 실제 중단 이유; 부재로 표시하지 않음 | R03, R04, R08 |
| T02 / E02 / P1 | 제목 검색0건, 다른 검색 가능 | 검색 범위/방법 receipt와 locate 또는 다른 검색 action 제공 | 모델 다음 입력에 EMPTY 범위와 대안이 존재; 검색0건을 전체 부재로 승격하지 않음 | 이 검색 방식으로 찾지 못함 | R03, R04, R12 |
| T03 / E03 / P1 | 같은 조번호가 여러 문서에 존재 | 문서·판본 후보와 AMBIGUOUS 사유를 주고 scope를 좁힌 다음 READ | 모든 선택은 실제 document/branch/unit에 결속; 첫 후보 자동 확정 없음 | 대상 문서 확인 필요 | R02, R04, R12 |
| T04 / E04 / P1 | 선택 glossary/index에 요청한 조회 기능 없음 | UNAVAILABLE과 실제 가능한 대안만 제공 | 불가 도구를 성공처럼 실행하거나 가짜 action을 제시하지 않음 | 현재 기능 없음; 대안도 없으면 없음 | R04, R07, R12 |
| T05 / E05 / P0 | 다른 요청/권한 범위의 대상 참조 | 현재 scope에서 target 재조회 또는 ACCESS_RESTRICTED | 새 OPEN/선택/게시가 현재 principal scope를 넘지 않음 | 접근 제한 또는 현재 범위에서 확인 불가 | R02, R07, R11 |
| T06 / E06 / P1 | 빈 용어/정의 결과: 미구축과 실제 선택 범위0건 두 변형 | 기능 availability와 조회 coverage를 별도로 반환 | 동일 빈 배열이어도 reason과 가능한 대안이 다름 | 기능 미구축/현재 검색 미발견 구분 | R03, R04, R12 |
| T07 / E07 / P1 | 다른 operation에 cursor를 옮기는 레거시 요청 | v5는 서버 action으로 원래 args/cursor 결속; 잘못된 action은 현재 대안으로 수정 | REPAIR 입력과 수정 후 정상 다음 페이지 receipt를 확인 | 계속 읽기 또는 새 작업 안내 | R04, R07, R10 |
| T08 / E08 / P1 | 같은 READ와 이유 문구만 반복; 비교군은 새 source page | 중복은 REUSED; 새 page는 canonical coverage 진전; 미처리 대안 안내 후 제한 | 동일 범위는 새 읽기/진전으로 세지 않으며 새 page는 처리 | 반복 중단 이유와 남은 범위 | R03, R08, R10 |
| T09 / E09 / P1 | R/F를 READ하려는 선택 | 읽기 가능한 action만 제시; 잘못된 종류에는 locate/search 대안 후 재시도 | 오류 전달→유효 위치 탐색→READ 성공 경로까지 확인 | 대상 종류와 가능한 다음 동작 | R04, R07 |
| T10 / E10 / P0 | 형식상 정상이나 현재 view에 없는 source/action 별칭 | 현재 제시 ID로 REPAIR; 다른 요청 ID는 거부 | 실제 DELIVERED view와 선택 receipt 연결, 오래된 ID 채택0 | 다시 확인할 대상 안내 | R02, R05, R07 |
| T11 / E11 / P1 | 긴 조의 READ 첫 page만 존재 | PARTIAL coverage와 정확 다음 페이지 action 제공 | union 범위가 실제 source와 일치; 전체 열람으로 오표기하지 않음 | 일부 읽음·조 전체 열기 | R02, R04, R05 |
| T12 / E12 / P1 | 관계가 많은 원문과 작은 공유 도구/시간 예산 | 선택적 관계 확장; 필수 원문 전달·수정 예산 우선 | 자동 관계6종 일괄 호출이 v5 기본에서 발생하지 않음; 역할별 예산 기록 | 관계 확인 미완료와 원문 확보를 구분 | R04, R08 |
| T13 / E13 / P1 | 관계 스캔이 시간 초과하고 cursor 없음 | 스캔 PARTIAL과 더 좁힌 범위/재시작 또는 재개 불가 표시 | COMPLETE나 관계 없음으로 변환하지 않음; 재시도 횟수/대상 고정 | 관계 스캔 미완료 | R04, R07, R08 |
| T14 / E14 / P0 | 도구가 throw 대신 ERROR observation 반환 | 직전 모델 요청 결과 우선 제시; ErrorRecord OPEN과 수정 action 생성 | 자동 작업 결과가 오류를 밀어내지 않으며 복구/종료 receipt 존재 | 실패한 도구와 다음 가능한 행동 | R05, R07 |
| T15 / E15 / P0 | 원문은 fit하지만 최종 메타데이터/schema/provider 옵션 추가 후 초과 | 최종 payload를 줄여 재분할 후 재검사 | 실제 send payload bytes/문자 한도와 저장 request 동일; 초과 send0 | 복구되면 정상 진행; 불가하면 전달 실패 | R05, R07 |
| T16 / E16 / P0 | 서버 READ3, DELIVERED0 | 미제시 원문 전달 작업을 작게 재구성하고 선택으로 재진입 | READ와 DELIVERED 카운터 분리; 제시 없는 선택0; 예산 있으면 복구 진행 | 읽었지만 미전달 상태 구분 | R03, R05, R08 |
| T17 / E17 / P0 | 단일 block/E가 최소 입력보다 큼 | block 내부 exact slices로 분할; 프로토콜 자체가 크면 메뉴/schema 축소 | slice 누적 범위/원문hash 일치; 같은 oversized item 무한 page 금지 | 부분 원문 또는 최소 입력 구성 불가 | R02, R05, R07 |
| T18 / E18 / P1 | 이미 읽고 제시한 선택 대기 원문5개 이상 | 선택 대기 page 처리; 제한 시 기존 선택 보존과 정확 잔여 표시 | 마지막4개만 제시하고 나머지를 처리 완료로 기록하지 않음 | 선택 완료/미처리 수 구분 | R03, R05, R08 |
| T19 / E19 / P0 | 모델 READ 뒤 자동 관계 결과가 다수 발생 | 모델 action 결과를 고정하고 자동 결과를 별도 요약 | READ status/coverage/cursor와 오류가 다음 view에 존재 | READ 완료/부분 읽기 상태 정확 | R04, R05 |
| T20 / E20 / P1 | 검색 total과 반환 page 수가 다르고 scan 일부 미완료 | search_receipt/coverage/scan status를 축약 view에도 보존 | item_total과 전체 적중 total을 구분; 생략시 알려진 범위로만 표시 | 선택 범위·남은 결과·미완료 안내 | R04, R05, R12 |
| T21 / E21 / P1 | 해결된 오류2개 뒤 새 미해결 오류 발생 | OPEN 오류 우선; RESOLVED receipt 후 과거 오류 제거 | 현재 오류가 오래된 최근2개 제한에 밀리지 않음 | 현재 수정해야 할 항목만 안내 | R05, R07 |
| T22 / E22 / P0 | 큰 invalid output을 추가한 repair payload가 한도 초과 | 실패 항목과 필요한 view만 남겨 최종 payload 재검사 | 원래 요청 fit뿐 아니라 실제 repair wire fit 확인 | 수정 진행 또는 입력 구성 불가 | R05, R07 |
| T23 / E23 / P0 | 3호 설명에 실제 유효2호 강조 ID; 구조 라벨은 검증됨 | 조 선택 보존; 명시 라벨 충돌은 강조 수정 또는 미확정 | 조 선택/항호 강조 정확성을 따로 검사; free-text 의미 탐지 한계 표시 | 관련 조 유지·강조 미확정 또는 교정 | R02, R05, R06, R14 |
| T24 / E24 / P0 | 모델이 독립 검토 없는 REVIEWED를 포함 | v5 최소 선택에 해당 상태 없음; 불필요 속성 오류와 유효 source 선택 분리 가능한 계약 검사 | 검토 기록 없는 REVIEWED 생성0; 정상 source 보존/형식 복구 경계 확인 | 관련 원문 선택·해석 미확정 | R02, R06, R07, R09 |
| T25 / E25 / P0 | 2,241자 조 선택, 카드 표시1,600자 정책 | 조 선택은 정상 저장; 표시 범위만 줄이고 전체 열기 제공 | 선택 거부0; 카드 발췌는 실제 전달 범위와 일치 | 관련 조 전체 접근·발췌 일부 | R02, R06 |
| T26 / E26 / P0 | 한 응답에 정상 source 선택과 잘못된 강조/행동 | 동일 snapshot 검증 후 독립 source 커밋, 실패 항목별 오류 | 정상 선택 rollback0; 재시도는 실패 항목만; 충돌 교체는 원자적 | 보존된 선택과 수정 미완료 항목 | R06, R07, R10 |
| T27 / E27 / P0 | 관련 조 선택 이후 강조를 끝내 고치지 못함 | source 선택과 OPEN 유지; highlight UNRESOLVED | selection_id/version과 highlight 상태 분리; 주장 근거에는 잘못된 강조 미사용 | 조는 유지·강조 없음 | R02, R06 |
| T28 / E28 / P1 | 중복 tier/상한초과/선택-제외 충돌 | 정확 상한·충돌과 교체 action 제시; 기존 선택 유지; 초과 CAP_PENDING | 동일 source 이중 표시0; 기존 선택 생략으로 삭제0; 유효 교체 원자성 | 남은 채택 한도와 보류 수 | R06, R07, R10 |
| T29 / E29 / P0 | 유효 source 선택과 잘못된 법적 관계평가 동시 제출 | source와 claim/relation 검증 의존성 분리 | 정상 source 유지; 미확인 관계로 확정 claim 생성0 | 출처 확보·해석 검토 미완료 | R06, R09 |
| T30 / E30 / P0 | READ만 존재하거나 미리보기만 보고 선택 | 정확 source slice 전달 작업→유효 새 선택 | 제시 없는 KEEP와 인용 차단; 재전달 뒤 정상 선택 | 읽기/제시 대기 | R02, R05, R07 |
| T31 / E31 / P1 | 최상위 JSON/envelope 파싱 오류 | 전체 syntax repair; 파싱된 operation 의미 오류는 개별 repair | raw substring 추측 저장0; 실제 오류→수정 호출→유효 커밋 | 형식 수정 또는 수정 한도 종료 | R05, R07 |
| T32 / E32 / P0 | 같은 상태/같은 잘못된 선택 재제출 | 오류 signature·구체 대안·보존 상태 제공; 한도 후 fallback/EXHAUSTED | 무한 반복0; 실제 RESOLVED 또는 EXHAUSTED와 공유예산 확인 | 고치지 못한 항목과 보존 결과 | R07, R08 |
| T33 / E33 / P1 | 탐색에서 복구 단계로 이동하며 오류가 바뀜 | 요청 전체 물리예산·오류signature 카운터 유지 | 단계 전환으로 budget/repair 한도 초기화0 | 사용한 한도와 남은 작업 | R07, R08 |
| T34 / E34 / P0 | 무진전/입력/전송/시간/호출 한도 각 변형 | typed stop reason과 수행 가능한 최종화 | FINISHED와 GOAL_MET 구분; 게시 가능한 부분 결과 보존 | 정확한 종료 사유 | R03, R07, R08, R12 |
| T35 / E35 / P0 | 미발견/미열람/미전달/거부/검토후제외가 모두 빈 source로 귀결 | workflow 상태·reason·coverage로 분리 | 동일 NO_SELECTION에 원인별 사용자 문구가 다름 | 자료 없음과 처리 실패 구분 | R03, R12 |
| T36 / E36 / P0 | 원본 export false와 명시 공개 범위 요청 승인 true | 원본 정책과 SEND_MODEL decision 분리; PUBLISH 목적 검사 | 원본 플래그 불변; 승인 밖 전송0; 허용 범위 실제 게시/OPEN 확인 | 설정 연결 오류 또는 정상 게시 | R11, R13 |
| T37 / E37 / P0 | 선택 revision 바뀐 뒤 옛 bundle 게시 | 옛 bundle 거부; 새 snapshot 생성·검증 후 게시 | 이미 게시한 파일 덮어쓰기0; 새 선택과 bundle hash 동일 | 최신 유효 선택 결과 | R06, R10, R11 |
| T38 / E38 / P0 | source hash/판본/권한 변경 | stale/범위 차단; 축소 권한은 전체 outbox 검증 | 카드 밖 질문·후보·답변까지 권한 누출0; 단순 retry 통과0 | 자료 변경/접근 제한 | R10, R11 |
| T39 / E39 / P0 | COMMIT_READY 또는 RUNNING 중 프로세스 종료 | 전자는 현재guard로 멱등게시; 후자는 INTERRUPTED·조건부 명시재개 | 선택 보존, UNKNOWN 성공처리0, 만료budget 무단재설정0 | 게시 복구 또는 재개 필요 | R08, R10, R11 |
| T40 / E40 / P0 | 내부 bundle 존재, 게시 실패 또는 source URL 미설정 | 실제 publication receipt와 인증된 OPEN 결과 검사 | offline render를 사용자 게시 성공으로 집계0 | 저장됨/게시차단/열기불가 구분 | R11, R12, R14 |

## 전체 흐름의 추가 계약8개

| ID·근거·우선순위 | 조건 | 처리·복구 | 통과 기준 | 사용자 결과 | 요구 |
|---|---|---|---|---|---|
| T41 / D03 / P0 | 정상 source 선택만 있고 기존 packed.support 없음; 사용자는 답변 요청 | v5 AnswerEvidencePack→draft→review에 진입 | v3 사전ADOPT gate 때문에 compose 생략0; source와 answer 상태 독립 | 검토된 답변 또는 명시 부분 답변 | R03, R09 |
| T42 / D01,D03 / P1 | 원문만 요청과 법적 답변 요청, 괄호 업무문맥 포함 | 명시 SOURCES 이외 기본 ANSWER; 원질문/문맥 보존 | 모델이 어렵다는 이유로 목표 downgrade0; 새 외부Request 필드 없음 | 요청 목적에 맞는 결과 | R02, R03, R12 |
| T43 / D02 / P0 | 내규/별표/표/구조 미확정 block 및 다른 판본의 동명 조 | 검증 단위 또는 SOURCE_REGION으로 결속 | 가짜 조항 생성0; 판본/branch 잘못 합침0; 원문 재작성0 | 실제 구조 라벨·미확정 표시 | R01, R02, R13 |
| T44 / D01,D06 / P0 | strict model schema에 맞지 않는 한 operation과 유효 selection 포함 | envelope와 operation 검증 분리 후 독립 항목 처리 | full-protocol.validate가 정상 sibling을 버리지 않음; 임의raw 권한검증 우회0 | 유효 선택과 실패 항목별 결과 | R02, R05, R06, R07 |
| T45 / D03,D04 / P0 | 주장 하나는 검토완료, 다른 주장은 예외/사실부족; 새 반론 도착 | 영향받은 claim만 재검토, 실제 basis/공통문맥 확인 | 조 전체 REVIEWED 오표기0; 표시 발췌를 legal pack으로 사용0 | 완료 부분·필요 사실·원문 함께 제공 | R04, R09, R10 |
| T46 / D07,D08 / P0 | v1/v4 과거결과와 v5 HTTP→StageRunner→outbox→renderer→OPEN | 버전별 reader/validator와 원문 source_id 매핑 | 닫힌 Result 최상위 추가필드0; legacy OPEN 유지; v5 실제 전체 원문 열기 | 하위호환된 실제 사용자 결과 | R01, R11, R12, R13 |
| T47 / D07,D08 / P0 | 결과 저장 뒤 게시완료 및 해당 source선택에 feedback | 불변Result hash+별도publication receipt; source-feedback-v2 검증 | result 재해시/덮어쓰기0; 닫힌v1 target에 새필드 무검증 삽입0 | 게시상태·대상에 연결된 피드백 | R10, R11, R12 |
| T48 / D05,D06 / P0 | 동시동일run·중복resume·UNKNOWN 응답·늦은응답·만료deadline | owner/revision/idempotency 확인; 모델resume 조건 점검 | 중복commit0; 다른요청상태공유0; 새run 계보/새budget 명시 | 중복 없이 현재 상태 또는 새 실행 안내 | R07, R08, R10, R11 |


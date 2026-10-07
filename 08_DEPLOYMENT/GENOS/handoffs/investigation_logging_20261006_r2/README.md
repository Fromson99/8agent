# 연결 조사·선별·요청 실패의 원인별 로그

사진의 `REQUIRED_CONNECTION_PENDING → MemoryError → HTTP 422`는 저장된 참조 해석 실패,
모델 보류, 미처리 연결, 실행 한도를 같은 상태로 표시했다. 작업 코드와 R3 누적 반입본에
원인별 기록을 연결했다. 기존 조사 완료 기준과 HTTP 종료 동작은 유지한다.

`unit_relations.catalog/navigate → unit_selection → memory_rag → unified_runtime → app`
전체 전달 경로에서 원인을 보존한다. `investigation-diagnostics-v1`의 `blockers`는 현재
완료를 막는 사유, `observations`는 관측됐지만 현재 정책상 완료를 막지 않는 항목이다.
`counts`는 사유 기록 수이며 서로 독립된 법적 의무 수나 결함 건수를 뜻하지 않는다.

| 기록 분류 | 실제 근거와 남기는 내용 |
| --- | --- |
| DATA_REFERENCE | 저장된 참조의 ID·resolution·locator·해석 사유·원본 문서/조항·읽기 의무 |
| MODEL_DECISION | 수락한 DEFER/needs_more, 모델의 선택·보류 이유·적용 판단과 정확한 연결 ID |
| UNPROCESSED_WORK | 미처리 메뉴·미스캔 채택 범위·이어읽기 참조 커서 |
| EXECUTION_LIMIT | 실제 문맥 문자 수/한도·사용 횟수/한도·탐색 깊이/한도 |
| EXECUTION_FAILURE | 실제 예외 코드·메시지·모델 단계와 중단 당시 연결 상태 |
| SOURCE_SELECTION | 다음 후보·새 검색·근거 부족 등 선별 결과와 충분성 판단 이유 |
| DIAGNOSTIC_GAP | 과거 체크포인트/어댑터가 pending만 기록한 경우. 데이터 문제로 추정하지 않음 |

선별 중단의 새 표시 코드는 `REFERENCE_NAVIGATION_INCOMPLETE`다.
`SourceInvestigationIncomplete`는 기존 `corrected_memory.MemoryError`의 하위 예외로
기존 호출 호환성을 유지하면서 `SOURCE_INVESTIGATION_INCOMPLETE`와 세부 원인 코드를
남긴다. RAM 부족으로 읽히는 예외 이름 단독 표시를 대체한다.

`REFERENCE_NAVIGATION_STATUS/FAILED`, `SOURCE_INVESTIGATION_INCOMPLETE`,
`UNIT_CANDIDATE_ACQUISITION_STOPPED`, `RUN_FAILED`, `UNASSESSED_AT_STOP`과
`ask.failed.failure_diagnostics`를 실제 journal·컨테이너 JSON·요청 .log/보고서에 연결했다.
요청 실패는 단계·예외의 실제 모듈/이름·메시지·마지막 발생 파일/행/함수를 보존한다.
미평가 근거는 마지막 처리 상태별 현황이며 중단 원인과 구분한다.
진단 이벤트의 참조 ID·중첩 세부 사유를 텍스트 변환 과정에서 지우거나 단순 건수로 바꾸지 않는다.
화면 요약은 문서 접근 범위를 검증하고 표시에서 생략한 행 수와 전체 journal 이벤트 번호를 명시한다.
요청 .log와 journal에는 전체 상세를 남긴다. 환경 인증값 마스킹을 유지하며 원문 본문·프롬프트를
새 진단 객체에 복사하지 않는다. 추가 진단 메타데이터는 기존 모델 입력에서 제외한다.

발송 ZIP에서 복원한 코드의 확대 계약 검사 212개 중 199개 PASS, 기존 실패 13개다.
새 원인 구분/마스킹/권한/HTTP/journal 전달 검사 9개는 모두 PASS다.
기존 실패 13개는 변경 전 R3의 정확한 코드에서도 동일 항목·같은 사유로 재현했다.
과거 AD 진입 전 관리 허용·v3 응답/DB·재검색·오류 문구 기대와 현행 계약 차이이며
이번 작업에서 해결하거나 전체 검사 통과로 보고하지 않는다.
14개 알려진 predecessor의 적용·재실행·원복·변조 거부와 Git/ZIP/모의 세대 gate 등
인계 검사 17개 PASS다. 외부 모델 호출은 0회다.
검증 산출물은 `CANDIDATE_TESTS.xml`, `DELIVERY_TESTS.xml`,
`BASELINE_KNOWN_FAILURES.xml`, `HANDOFF.json`이다.
발송하지 않은 R1의 시험 설정 오류와 읽기 위치 로그 의존성 누락은 R1 검사 기록에
보존했다. R2는 unit_reading의 실제 읽기 좌표 함수와 source_recall의 검색 위치 로그까지
같은 코드에 결속한다. 원문 데이터가 포함된 전체 현장 세대 검증으로 이 모의 검사를 해석하지 않는다.

코드 ZIP은 기존 R3의 정확한 코드·compact 용어집 reader·AD·워크플로우를 보존하고
선언한 14개 로그 관련 파일만 교체/추가한다. 관련 30개 engine pin을 결속했다.
로컬 frozen MAIN·NFS generation/CURRENT·GENOS 현장 리비전은 별도 상태다.
실제 선택된 현장 generation 경로/manifest 해시·push commit·리비전은 미확인이다.
반입과 원복 명령은 [GUIDE_UTF8.txt](GUIDE_UTF8.txt)를 따른다.

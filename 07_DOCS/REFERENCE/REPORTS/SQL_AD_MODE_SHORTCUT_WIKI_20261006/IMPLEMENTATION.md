# 구현·이행·검증·복구

## 연결 지점

| 실행 입구 | 연결 | 소비자 |
|---|---|---|
| GENOS workflow/genos_rag_chat.py | chatId/channel/request_id를 AD_PROBE에 전달, 응답 표 보존 | 기존 코드서빙 service |
| main.py /chat | 플랫폼 게이트웨이 확인, startup 복구 | chat_adapter.py |
| chat_adapter.py | 동일 릴리스의 workflow helper를 정확 경로로 로드 | AD면 그대로 출력, 일반 질문이면 기존 법률 경로 |
| service/service.py → service.py | 선택된 릴리스의 AD 모듈을 법률 초기화/로그보다 먼저 호출 | ad_gateway.py |
| ad_gateway.py | 서버 TEAM_ID, 선택된 상태 DB, 내부 모델 작업자 | ad_mode / ad_jobs |
| ad_mode.py | 정확한 모드 경계, 한국어 명령, 선택·페이지·오류 | ad_store / ad_backend |
| ad_backend.py | 허용 SQL 조회·변경·revision·휴지통·근거 검사 | 기존 shortcut repository·위키 정본 |
| ad_jobs.py | SQL 예약·lease·개별 입력·중단 fence | 기존 legal_wiki_compiler |
| shortcut_ingress / unified_runtime / procedure_memory | 스위치와 현재 재사용 자격 확인 | 기존 법률 실행 경로 |
| control.py / PIPELINE.json / engine manifests | 관리 모듈·채팅 진입·workflow의 배포 복사 및 해시 | MAIN 게시기·실행기 |

새 최상위 실행기를 만들지 않는다. 기존 서비스 진입과 구성기를 사용한다. AD 관리 요청을 법률 command resolver에 전달하지 않는다. 원문·색인·모델·법률 프롬프트는 이 작업의 변경 대상이 아니다.

## 이행

1. 검증된 누적 ZIP의 실제 manifest와 파일 hash를 확인한다. `~/DEV` 파일별 백업 후 적용한다. 실행 TXT는 시작부터 stdout/stderr/종료 상태를 남긴다.
2. GENOS_STATE_DIR은 영속 로컬 볼륨의 기존 상태 위치를 명시한다. 기존 v4 DB가 있다면 서비스를 중지하고 SQLite backup API로 새 위치에 복사·integrity_check·행수 대조 후 선택한다. 원본/이전 pointer/receipt를 보존한다. WAL 사용 중 파일 하나만 복사하지 않는다.
3. ad_* 스키마는 같은 선택 v4 DB에 가산한다. v4 원문·과거 revision을 덮어쓰지 않는다. 관리 스키마 version이 다르면 실패한다. 기존 v3 사건의 이행은 기존 shortcut migration 경로와 별도 receipt를 사용한다. 빈 v4를 과거 기록 이행 완료로 보고하지 않는다.
4. 코드 적용, 상태 DB 위치 선택, NFS 데이터 generation, Git push, 코드서빙 revision 배포, workflow 편집기 반영은 각각 별도 상태다. 이번 AD 기능은 워크플로우 Python 코드도 교체해야 한다.
5. 예약 실행을 위해 code-serving 프로세스가 상주해야 한다. `현재 상태`에서 worker heartbeat 및 마지막 오류를 본다. 프로세스가 죽었으면 채팅만으로 죽은 프로세스를 되살릴 수는 없으며 플랫폼에서 재시작한다. 예약은 SQL에 보존된다.

## 검증

정확 모드 진입·종료/문장 내 진입 무효/다른 대화 분리/법률 호출 차단, 25건 표의 다중 페이지, 오래된 선택과 동시 수정, 승인·반려·수정·불변 이벤트, 휴지통·복구·위키 재사용 제외, independent OFF, 명시 시간과 모호한 12시 후속 응답, 중복 예약, 프로세스 재시작·lease·중단 fence, 오류 본문·스키마·SQL 제약을 검사한다.

실제 서비스·/chat 어댑터·workflow 수신 입구와 배포용 복사본의 엔진 pin 전체를 검사한다. 이전 shortcut 회귀도 새 계약의 AD 접근 조건 아래 실행한다. 고정 명령에는 모델을 부르지 않는다. 구성기의 입력 계약은 모의 자료로 검사하며 실제 GENOS 모델 생성·자정 상주 실행은 현장에서 워크플로우 테스트 화면으로 확인한다.

## 복구

AD 관리 데이터와 감사 기록은 코드 롤백으로 삭제하지 않는다. 변경 후 문제가 생기면 먼저 작업 중지·예약 취소/위키 OFF를 적용하고 작업/오류 리포트를 보존한다. 개별 자료는 휴지통 복구 또는 새 수정 revision으로 되돌린다.

새 관리 스키마를 모르는 구 코드로 돌아가면 휴지통과 OFF를 무시할 수 있다. 따라서 상태 DB를 연결한 채 구 코드만 되돌리는 운영을 금지한다. 서비스를 중지하고 신규 DB를 보존한 뒤 **이행 전 DB와 이전 선택 포인터**를 함께 복원하거나, 이번 관리 정책을 읽는 호환 코드로 복구한다. 이행 후 기록은 별도 보존·재조정하며 덮어쓰지 않는다. 패키지의 파일 복구는 코드만 복원하며 DB 복구 완료로 보고하지 않는다.

MAIN 활성 포인터는 표준 hash 고정 plan/--confirm-main으로 변경한다. 실패한 후보를 우회 승격하지 않는다. GENOS 현장 성능이나 실제 배포는 이 로컬 승인과 구분한다.

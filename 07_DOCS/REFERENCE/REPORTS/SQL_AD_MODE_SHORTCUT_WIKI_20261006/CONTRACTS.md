# SQL 계약과 상태 전이

## 관계와 인덱스

| 테이블 | 정본 책임 | 주요 검색/정합성 |
|---|---|---|
| ad_session | 공간/채널/대화별 모드·선택 위치 | UNIQUE(workspace,channel,chat) |
| ad_view / ad_view_row | 조회 시점의 행 ID·revision·순서 | (view,ordinal) PK; 대상 역조회 |
| ad_selection | 여러 턴의 선택 집합 | session FK, ordinal PK |
| ad_operation / ad_change | 요청 멱등성과 변경 전후 감사 | UNIQUE(session,request); 대상별 변경 이력 |
| ad_object | 검토·휴지통·관리 revision | workspace/trashed/review/kind 복합 인덱스 |
| ad_feature | 공간별 독립 shortcut/wiki 스위치 | bool CHECK, revision |
| ad_schedule | 실행 시각·반복·취소 | enabled,due_at 인덱스 |
| ad_job / ad_job_item | 작업/입력별 진행·lease·오류 | 상태 enum; workspace당 RUNNING 하나; 예약 시각 UNIQUE |
| ad_worker | 프로세스 heartbeat와 poll 실패 | pid 정수·heartbeat 숫자·상태 enum |
| ad_error | 단계·유형·원인·traceback | session/job + created_at 인덱스 |
| ad_exclusion | 동일 근거 위키 재생성 제외 | workspace/signature/active 인덱스 |
| ad_wiki_index | 위키 제목/질문·현재 revision | workspace/topic 인덱스; 원문 payload 추출은 write 때 수행 |
| ad_detail | 상세 전체 내용과 다음 출력 위치 | session/created_at; 10,000문자씩 제공 |

원문 사건/근거 sw_* 계약은 보존한다. JSON은 불변 payload와 상세 응답에 사용하며 작업 상태·대상·시간을 JSON 안에 숨기지 않는다. SQL 식별자는 실제 허용 테이블 목록과 대조하고 값은 파라미터로 전달한다. 기존 증거 원문을 정규화하면서 잃어버리지 않는다.

## 트랜잭션

BEGIN IMMEDIATE → 요청 ID/입력 hash 검사 → 현재 대화의 선택 ID/revision 확인 → 모든 대상 변경 → 원본/감사/위키 무효화/큐 갱신 → 응답 캐시 → COMMIT. 중간 실패는 전체 ROLLBACK 후 별도 오류 기록을 남긴다. 동일 요청·동일 본문은 저장한 결과를 반환한다. 같은 요청 번호에 다른 본문은 거절한다. 실패 요청을 재시도할 때는 새 request_id를 사용한다.

행 revision은 콘텐츠 revision과 관리 revision을 결합한 정수 CAS다. 관리 revision 1,000,000회 도달 전 명시적 스키마 이행 오류를 낸다. 무한 증가에 따른 충돌을 허용하지 않는다. 다른 대화가 고친 행을 오래된 표에서 덮어쓰지 않는다.

## 상태

- 모드: OFF → exact ENTER → ON → exact EXIT → OFF. 작업·예약 생명주기와 독립.
- 검토: PENDING/APPROVED/REJECTED. 콘텐츠를 수정하면 PENDING. 승인 revision이 현재 콘텐츠와 달라지면 재사용 불가.
- 휴지통: trashed 0/1. 삭제 없이 복구. 재사용 시 매번 현재 상태 검사.
- 작업: QUEUED → RUNNING → QUEUED(다음 입력/페이지) → SUCCEEDED/PARTIAL/FAILED. 사용자 의도는 RUN/PAUSE/CANCEL 별도 열.
- 중단: 커밋 fence 검사. 오래된 작업자의 lease 토큰으로는 커밋 불가. 360초 lease 만료 후 다른 프로세스가 미완료 입력을 회수.
- 위키 작업: 분할 페이지 CONTINUE는 DONE이 아니다. 입력/완료/실패 수를 SQL 항목 상태로 계산한다. 빈 큐도 0건 완료로 기록한다.
- 예약: due_at 실수형 epoch, timezone Asia/Seoul. 매일/일회만 지원. 중복 발생 UNIQUE(schedule,scheduled_for).

스위치: shortcut OFF는 자동 캡처와 저장 경험 재사용을 중단한다. 법률 답변의 기본 실행·세션 기능은 유지한다. wiki OFF는 생성 작업을 멈추고 위키 힌트·절차·판단 소비를 막는다. SQL 자료와 AD 관리·복구는 유지한다. ON은 취소/일시중지된 작업을 임의 재개하지 않는다.

## 실제 DDL

아래는 후보 코드에서 직접 추출한 DDL이다. schema version 1 외의 관리 스키마는 자동 덮어쓰지 않고 오류를 반환한다.

```sql

CREATE TABLE IF NOT EXISTS ad_schema(version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO ad_schema VALUES(1);
CREATE TABLE IF NOT EXISTS ad_session(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, channel TEXT NOT NULL, chat TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN(0,1)), revision INTEGER NOT NULL DEFAULT 0,
 active_view TEXT, last_operation TEXT, last_job TEXT, pending_action TEXT, pending_field TEXT,
 updated_at REAL NOT NULL, UNIQUE(workspace,channel,chat));
CREATE TABLE IF NOT EXISTS ad_view(
 id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES ad_session(id), kind TEXT NOT NULL,
 position INTEGER NOT NULL DEFAULT 0 CHECK(position>=0), total INTEGER NOT NULL CHECK(total>=0),
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_view_session ON ad_view(session,created_at);
CREATE TABLE IF NOT EXISTS ad_view_row(
 view TEXT NOT NULL REFERENCES ad_view(id), ordinal INTEGER NOT NULL CHECK(ordinal>0),
 kind TEXT NOT NULL, entity TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
 status TEXT NOT NULL, PRIMARY KEY(view,ordinal));
CREATE INDEX IF NOT EXISTS ad_view_entity ON ad_view_row(kind,entity,revision);
CREATE TABLE IF NOT EXISTS ad_selection(
 session TEXT NOT NULL REFERENCES ad_session(id), ordinal INTEGER NOT NULL,
 kind TEXT NOT NULL, entity TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(session,ordinal));
CREATE TABLE IF NOT EXISTS ad_operation(
 id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES ad_session(id), request TEXT NOT NULL,
 input_hash TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN('RUNNING','SUCCEEDED','FAILED')),
 created_at REAL NOT NULL, finished_at REAL, response TEXT,
 UNIQUE(session,request));
CREATE INDEX IF NOT EXISTS ad_operation_session ON ad_operation(session,created_at);
CREATE TABLE IF NOT EXISTS ad_change(
 operation TEXT NOT NULL REFERENCES ad_operation(id), ordinal INTEGER NOT NULL,
 kind TEXT NOT NULL, entity TEXT NOT NULL, before_revision INTEGER NOT NULL,
 after_revision INTEGER NOT NULL, action TEXT NOT NULL, field TEXT, before_value TEXT, after_value TEXT,
 PRIMARY KEY(operation,ordinal));
CREATE INDEX IF NOT EXISTS ad_change_entity ON ad_change(kind,entity,operation);
CREATE TABLE IF NOT EXISTS ad_object(
 kind TEXT NOT NULL, entity TEXT NOT NULL, workspace TEXT NOT NULL,
 review TEXT NOT NULL DEFAULT 'PENDING' CHECK(review IN('PENDING','APPROVED','REJECTED')),
 reviewed_revision INTEGER, trashed INTEGER NOT NULL DEFAULT 0 CHECK(trashed IN(0,1)),
 revision INTEGER NOT NULL DEFAULT 0, changed_at REAL NOT NULL,
 PRIMARY KEY(kind,entity));
CREATE INDEX IF NOT EXISTS ad_object_status ON ad_object(workspace,trashed,review,kind,entity);
CREATE TABLE IF NOT EXISTS ad_feature(
 workspace TEXT PRIMARY KEY, shortcut INTEGER NOT NULL DEFAULT 1 CHECK(shortcut IN(0,1)),
 wiki INTEGER NOT NULL DEFAULT 1 CHECK(wiki IN(0,1)), revision INTEGER NOT NULL DEFAULT 0,
 changed_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ad_schedule(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, session TEXT NOT NULL REFERENCES ad_session(id),
 due_at REAL NOT NULL, timezone TEXT NOT NULL DEFAULT 'Asia/Seoul',
 repeat_seconds INTEGER NOT NULL DEFAULT 0 CHECK(repeat_seconds IN(0,86400)),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN(0,1)), last_due_at REAL,
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_schedule_due ON ad_schedule(enabled,due_at);
CREATE TABLE IF NOT EXISTS ad_job(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, session TEXT NOT NULL REFERENCES ad_session(id),
 schedule TEXT REFERENCES ad_schedule(id), scheduled_for REAL,
 status TEXT NOT NULL CHECK(status IN('QUEUED','RUNNING','PAUSED','CANCELLED','SUCCEEDED','FAILED','PARTIAL')),
 desired TEXT NOT NULL DEFAULT 'RUN' CHECK(desired IN('RUN','PAUSE','CANCEL')),
 created_at REAL NOT NULL, started_at REAL, finished_at REAL, heartbeat REAL,
 lease TEXT, lease_until REAL, completed INTEGER NOT NULL DEFAULT 0,
 failed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
 UNIQUE(schedule,scheduled_for));
CREATE INDEX IF NOT EXISTS ad_job_ready ON ad_job(status,created_at);
CREATE INDEX IF NOT EXISTS ad_job_workspace ON ad_job(workspace,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ad_job_one_running ON ad_job(workspace) WHERE status='RUNNING';
CREATE TABLE IF NOT EXISTS ad_job_item(
 job TEXT NOT NULL REFERENCES ad_job(id), queue_id INTEGER NOT NULL, scope TEXT NOT NULL,
 investigation TEXT NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN('PENDING','RUNNING','DONE','FAILED')), attempts INTEGER NOT NULL DEFAULT 0,
 started_at REAL, finished_at REAL, detail TEXT,
 PRIMARY KEY(job,queue_id));
CREATE INDEX IF NOT EXISTS ad_job_item_ready ON ad_job_item(job,status,queue_id);
CREATE TABLE IF NOT EXISTS ad_error(
 id TEXT PRIMARY KEY, session TEXT REFERENCES ad_session(id), job TEXT REFERENCES ad_job(id),
 operation TEXT REFERENCES ad_operation(id), stage TEXT NOT NULL, error_type TEXT NOT NULL,
 message TEXT NOT NULL, detail TEXT NOT NULL, retryable INTEGER NOT NULL CHECK(retryable IN(0,1)),
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_error_session ON ad_error(session,created_at);
CREATE INDEX IF NOT EXISTS ad_error_job ON ad_error(job,created_at);
CREATE TABLE IF NOT EXISTS ad_exclusion(
 workspace TEXT NOT NULL, unit TEXT NOT NULL, signature TEXT NOT NULL,
 active INTEGER NOT NULL CHECK(active IN(0,1)), PRIMARY KEY(workspace,unit));
CREATE INDEX IF NOT EXISTS ad_exclusion_input ON ad_exclusion(workspace,signature,active);
CREATE TABLE IF NOT EXISTS ad_wiki_index(
 unit TEXT PRIMARY KEY, workspace TEXT NOT NULL, revision INTEGER NOT NULL,
 topic TEXT NOT NULL, question TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ad_wiki_topic ON ad_wiki_index(workspace,topic,unit);
CREATE TABLE IF NOT EXISTS ad_worker(id TEXT PRIMARY KEY, pid INTEGER NOT NULL, heartbeat REAL NOT NULL, status TEXT NOT NULL CHECK(status IN('POLLING','FAILED')), error TEXT);
CREATE TABLE IF NOT EXISTS ad_detail(
 id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES ad_session(id),
 entity TEXT NOT NULL, content TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_detail_session ON ad_detail(session,created_at);
```

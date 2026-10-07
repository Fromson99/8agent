-- 전체 기억 설계의 사건·사용자 저장 계약 초안. 실제 DB에 적용하지 않는다.
-- 별도 live context DB용. shortcut-experience-v1.draft.sql은 오프라인 경험 DB용이다.
-- 이 SQL은 연결 제약을 검사하며 ACL/의미 판단/지문 계산/원자적 head 이동은 소비 코드 책임이다.
PRAGMA foreign_keys=ON;
PRAGMA recursive_triggers=ON;

CREATE TABLE cm_schema(version TEXT PRIMARY KEY CHECK(version='legal-agent-case-memory-v1-draft-r2'), created_at TEXT NOT NULL);

-- 대화와 사건은 다르다. 한 대화가 여러 사건을 다룰 수 있다.
CREATE TABLE cm_conversation(
 conversation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, owner_id TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(conversation_id,tenant_id)
);
-- 신뢰된 adapter가 외부 식별자를 내부 대화에 연결한다. 원 ID를 자르거나 치환하지 않는다.
CREATE TABLE cm_session_binding(
 provider TEXT NOT NULL, namespace TEXT NOT NULL, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
 external_session_id TEXT NOT NULL CHECK(length(external_session_id)>0),
 conversation_id TEXT NOT NULL UNIQUE,
 identity_receipt_ref TEXT NOT NULL, identity_receipt_hash TEXT NOT NULL CHECK(length(identity_receipt_hash)=64),
 created_at TEXT NOT NULL,
 PRIMARY KEY(provider,namespace,tenant_id,user_id,external_session_id),
 FOREIGN KEY(conversation_id,tenant_id) REFERENCES cm_conversation(conversation_id,tenant_id)
);
CREATE TABLE cm_case(
 case_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, owner_id TEXT NOT NULL,
 title TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(case_id,tenant_id)
);
CREATE TABLE cm_access_event(
 event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cm_case(case_id),
 principal_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=1),
 permission TEXT NOT NULL CHECK(permission IN ('READ','WRITE','REVOKED')),
 actor_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(case_id,principal_id,revision)
);

-- 실제 사건과 '만약' 가정은 별개 branch. 부모는 당시 상태 버전으로 고정한다.
CREATE TABLE cm_branch(
 case_id TEXT NOT NULL REFERENCES cm_case(case_id), branch_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('ACTUAL','HYPOTHETICAL')),
 parent_branch_id TEXT, parent_revision INTEGER,
 created_at TEXT NOT NULL, PRIMARY KEY(case_id,branch_id),
 FOREIGN KEY(case_id,parent_branch_id,parent_revision) REFERENCES cm_state(case_id,branch_id,revision),
 CHECK((parent_branch_id IS NULL)=(parent_revision IS NULL)),
 CHECK(parent_branch_id IS NULL OR parent_branch_id!=branch_id),
 CHECK(kind!='HYPOTHETICAL' OR parent_branch_id IS NOT NULL)
);
CREATE UNIQUE INDEX cm_actual_branch ON cm_branch(case_id) WHERE kind='ACTUAL';

CREATE TABLE cm_state(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=0),
 parent_revision INTEGER, source_turn_id TEXT,
 state_json TEXT NOT NULL CHECK(json_valid(state_json)),
 state_hash TEXT NOT NULL CHECK(length(state_hash)=64), created_at TEXT NOT NULL,
 PRIMARY KEY(case_id,branch_id,revision),
 FOREIGN KEY(case_id,branch_id) REFERENCES cm_branch(case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,parent_revision) REFERENCES cm_state(case_id,branch_id,revision),
 FOREIGN KEY(source_turn_id,case_id,branch_id) REFERENCES cm_turn(turn_id,case_id,branch_id),
 CHECK((revision=0 AND parent_revision IS NULL AND source_turn_id IS NULL)
    OR (revision>0 AND parent_revision=revision-1 AND source_turn_id IS NOT NULL))
);

-- 유일한 가변 포인터. writer는 이전 revision 조건의 UPDATE와 행수=1을 확인해야 한다.
CREATE TABLE cm_head(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,revision) REFERENCES cm_state(case_id,branch_id,revision)
);

CREATE TABLE cm_turn(
 turn_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
 turn_number INTEGER NOT NULL CHECK(turn_number>=1),
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, base_revision INTEGER NOT NULL,
 actor_id TEXT NOT NULL, client_request_id TEXT NOT NULL,
 original_text TEXT NOT NULL, input_json TEXT NOT NULL CHECK(json_valid(input_json)),
 input_hash TEXT NOT NULL CHECK(length(input_hash)=64), created_at TEXT NOT NULL,
 FOREIGN KEY(conversation_id,tenant_id) REFERENCES cm_conversation(conversation_id,tenant_id),
 FOREIGN KEY(case_id,tenant_id) REFERENCES cm_case(case_id,tenant_id),
 FOREIGN KEY(case_id,branch_id,base_revision) REFERENCES cm_state(case_id,branch_id,revision),
 UNIQUE(conversation_id,actor_id,client_request_id), UNIQUE(turn_id,case_id,branch_id),
 UNIQUE(conversation_id,turn_number)
);

-- 값이 같아도 사실 출처·확인 수준이 달라지면 새 버전. 사용자 주장과 검증을 구분한다.
CREATE TABLE cm_fact(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, fact_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1), previous_revision INTEGER,
 fact_key TEXT NOT NULL, goal_id TEXT, value_json TEXT NOT NULL CHECK(json_valid(value_json)),
 basis TEXT NOT NULL CHECK(basis IN ('USER_ASSERTED','SOURCE_VERIFIED','ASSUMPTION','UNKNOWN','RETRACTED')),
 source_turn_id TEXT NOT NULL, origin_ref TEXT NOT NULL,
 origin_hash TEXT NOT NULL CHECK(length(origin_hash)=64),
 verification_ref TEXT, verification_hash TEXT CHECK(verification_hash IS NULL OR length(verification_hash)=64),
 PRIMARY KEY(case_id,branch_id,fact_id,revision),
 FOREIGN KEY(source_turn_id,case_id,branch_id) REFERENCES cm_turn(turn_id,case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,fact_id,previous_revision) REFERENCES cm_fact(case_id,branch_id,fact_id,revision),
 CHECK((revision=1 AND previous_revision IS NULL) OR (revision>1 AND previous_revision=revision-1)),
 CHECK((verification_ref IS NULL)=(verification_hash IS NULL)),
 CHECK(basis!='SOURCE_VERIFIED' OR verification_ref IS NOT NULL)
);

-- 상태 하나가 채택한 사실의 정확한 버전. 이전 snapshot의 값은 바꾸지 않는다.
CREATE TABLE cm_state_fact(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, state_revision INTEGER NOT NULL,
 fact_id TEXT NOT NULL, fact_branch_id TEXT NOT NULL, fact_revision INTEGER NOT NULL,
 PRIMARY KEY(case_id,branch_id,state_revision,fact_id),
 FOREIGN KEY(case_id,branch_id,state_revision) REFERENCES cm_state(case_id,branch_id,revision),
 FOREIGN KEY(case_id,fact_branch_id,fact_id,fact_revision) REFERENCES cm_fact(case_id,branch_id,fact_id,revision)
);

-- 매 턴 새 native run. 첫 model view에는 base 상태, 해석 확정 후 view에는 새 상태를 연결한다.
CREATE TABLE cm_run_binding(
 run_id TEXT PRIMARY KEY, turn_id TEXT NOT NULL, case_id TEXT NOT NULL, branch_id TEXT NOT NULL,
 base_revision INTEGER NOT NULL, journal_ref TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(turn_id,case_id,branch_id) REFERENCES cm_turn(turn_id,case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,base_revision) REFERENCES cm_state(case_id,branch_id,revision),
 UNIQUE(run_id,case_id,branch_id)
);
CREATE TABLE cm_run_state(
 run_id TEXT NOT NULL, case_id TEXT NOT NULL, branch_id TEXT NOT NULL,
 seq INTEGER NOT NULL CHECK(seq>=1), state_revision INTEGER NOT NULL,
 native_event_ref TEXT NOT NULL, native_event_hash TEXT NOT NULL CHECK(length(native_event_hash)=64),
 PRIMARY KEY(run_id,seq),
 FOREIGN KEY(run_id,case_id,branch_id) REFERENCES cm_run_binding(run_id,case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,state_revision) REFERENCES cm_state(case_id,branch_id,revision)
);

-- 판단의 원본은 journal이다. 이 표는 다음 대화에서 찾기 위한 색인과 설명이다.
CREATE TABLE cm_decision(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, decision_id TEXT NOT NULL,
 run_id TEXT NOT NULL, entity_kind TEXT NOT NULL, entity_id TEXT NOT NULL, entity_revision INTEGER NOT NULL CHECK(entity_revision>=1),
 entity_ref TEXT NOT NULL, entity_hash TEXT NOT NULL CHECK(length(entity_hash)=64),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)), supersedes_decision_id TEXT,
 PRIMARY KEY(case_id,branch_id,decision_id),
 FOREIGN KEY(run_id,case_id,branch_id) REFERENCES cm_run_binding(run_id,case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,supersedes_decision_id) REFERENCES cm_decision(case_id,branch_id,decision_id),
 CHECK(supersedes_decision_id IS NULL OR supersedes_decision_id!=decision_id),
 UNIQUE(run_id,entity_kind,entity_id,entity_revision)
);
CREATE TABLE cm_decision_fact(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, decision_id TEXT NOT NULL,
 fact_id TEXT NOT NULL, fact_branch_id TEXT NOT NULL, fact_revision INTEGER NOT NULL,
 PRIMARY KEY(case_id,branch_id,decision_id,fact_id),
 FOREIGN KEY(case_id,branch_id,decision_id) REFERENCES cm_decision(case_id,branch_id,decision_id),
 FOREIGN KEY(case_id,fact_branch_id,fact_id,fact_revision) REFERENCES cm_fact(case_id,branch_id,fact_id,revision)
);
CREATE INDEX cm_fact_dependents ON cm_decision_fact(case_id,fact_branch_id,fact_id,fact_revision);
CREATE TABLE cm_decision_parent(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, decision_id TEXT NOT NULL, parent_id TEXT NOT NULL,
 PRIMARY KEY(case_id,branch_id,decision_id,parent_id), CHECK(decision_id!=parent_id),
 FOREIGN KEY(case_id,branch_id,decision_id) REFERENCES cm_decision(case_id,branch_id,decision_id),
 FOREIGN KEY(case_id,branch_id,parent_id) REFERENCES cm_decision(case_id,branch_id,decision_id)
);
CREATE INDEX cm_parent_dependents ON cm_decision_parent(case_id,branch_id,parent_id);
CREATE TABLE cm_decision_check(
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, state_revision INTEGER NOT NULL,
 decision_id TEXT NOT NULL, check_no INTEGER NOT NULL CHECK(check_no>=1),
 status TEXT NOT NULL CHECK(status IN ('APPLICABLE','NEEDS_CHECK','NOT_APPLICABLE','DISPUTED')),
 reason TEXT NOT NULL, receipt_ref TEXT NOT NULL, receipt_hash TEXT NOT NULL CHECK(length(receipt_hash)=64),
 PRIMARY KEY(case_id,branch_id,state_revision,decision_id,check_no),
 FOREIGN KEY(case_id,branch_id,state_revision) REFERENCES cm_state(case_id,branch_id,revision),
 FOREIGN KEY(case_id,branch_id,decision_id) REFERENCES cm_decision(case_id,branch_id,decision_id)
);

-- 표시한 답변의 문단/판단 설명에서 실제 판단을 찾는다. 한 문단은 여러 판단을 가질 수 있다.
CREATE TABLE cm_answer_anchor(
 publication_ref TEXT NOT NULL, publication_hash TEXT NOT NULL CHECK(length(publication_hash)=64),
 anchor_id TEXT NOT NULL, anchor_text TEXT NOT NULL,
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, run_id TEXT NOT NULL, decision_id TEXT NOT NULL,
 PRIMARY KEY(publication_ref,anchor_id,decision_id),
 FOREIGN KEY(run_id,case_id,branch_id) REFERENCES cm_run_binding(run_id,case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,decision_id) REFERENCES cm_decision(case_id,branch_id,decision_id)
);

-- 대상이 유일하게 해석·검증된 수정 요청만 기록한다. 모호한 발언은 turn에만 남긴다.
-- patch의 값은 사용자 요청이며 법률 정확성 승인이 아니다. 정정·재판단 결과는 새 상태/판단이다.
CREATE TABLE cm_edit(
 edit_id TEXT PRIMARY KEY, source_turn_id TEXT NOT NULL, case_id TEXT NOT NULL, branch_id TEXT NOT NULL,
 base_revision INTEGER NOT NULL, target_turn_id TEXT NOT NULL, target_decision_id TEXT NOT NULL,
 target_goal_id TEXT NOT NULL, extent TEXT NOT NULL CHECK(extent IN ('TARGET_GOAL','CURRENT_CASE')),
 operation TEXT NOT NULL CHECK(operation IN ('CORRECT_FACT','CHANGE_SCOPE','RECONSIDER_DECISION','RETRACT_FACT')),
 target_fact_id TEXT, target_fact_branch_id TEXT, target_fact_revision INTEGER,
 patch_json TEXT NOT NULL CHECK(json_valid(patch_json)),
 interpretation_ref TEXT NOT NULL, interpretation_hash TEXT NOT NULL CHECK(length(interpretation_hash)=64),
 created_at TEXT NOT NULL,
 FOREIGN KEY(source_turn_id,case_id,branch_id) REFERENCES cm_turn(turn_id,case_id,branch_id),
 FOREIGN KEY(target_turn_id,case_id,branch_id) REFERENCES cm_turn(turn_id,case_id,branch_id),
 FOREIGN KEY(case_id,branch_id,base_revision) REFERENCES cm_state(case_id,branch_id,revision),
 FOREIGN KEY(case_id,branch_id,target_decision_id) REFERENCES cm_decision(case_id,branch_id,decision_id),
 FOREIGN KEY(case_id,target_fact_branch_id,target_fact_id,target_fact_revision) REFERENCES cm_fact(case_id,branch_id,fact_id,revision),
 CHECK(source_turn_id!=target_turn_id),
 CHECK((target_fact_id IS NULL)=(target_fact_branch_id IS NULL) AND (target_fact_id IS NULL)=(target_fact_revision IS NULL)),
 CHECK(operation NOT IN ('CORRECT_FACT','RETRACT_FACT') OR target_fact_id IS NOT NULL)
);
CREATE TABLE cm_edit_application(
 edit_id TEXT PRIMARY KEY REFERENCES cm_edit(edit_id),
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, state_revision INTEGER NOT NULL,
 receipt_ref TEXT NOT NULL, receipt_hash TEXT NOT NULL CHECK(length(receipt_hash)=64),
 FOREIGN KEY(case_id,branch_id,state_revision) REFERENCES cm_state(case_id,branch_id,revision)
);

-- user_wiki 개인 설정의 정본. 질문·판단·정정 이력은 위 표들에서 같은 화면으로 투영한다.
CREATE TABLE cm_user_memory(
 tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, memory_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1), previous_revision INTEGER,
 kind TEXT NOT NULL CHECK(kind IN ('PREFERENCE','WORK_CONTEXT','CASE_BOOKMARK')),
 content_json TEXT NOT NULL CHECK(json_valid(content_json)),
 status TEXT NOT NULL CHECK(status IN ('PROPOSED','CONFIRMED','RETRACTED')),
 origin_ref TEXT NOT NULL, origin_hash TEXT NOT NULL CHECK(length(origin_hash)=64),
 confirmation_ref TEXT, expires_at TEXT, created_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,user_id,memory_id,revision),
 FOREIGN KEY(tenant_id,user_id,memory_id,previous_revision) REFERENCES cm_user_memory(tenant_id,user_id,memory_id,revision),
 CHECK((revision=1 AND previous_revision IS NULL) OR (revision>1 AND previous_revision=revision-1)),
 CHECK(status!='CONFIRMED' OR confirmation_ref IS NOT NULL)
);

-- DB 간 전달을 재개 가능하게 한다. 기존 finalizer/intake가 소비한다.
CREATE TABLE cm_outbox(
 event_id TEXT PRIMARY KEY, aggregate_key TEXT NOT NULL,
 destination TEXT NOT NULL CHECK(destination IN ('RUN_JOURNAL','SHORTCUT_INTAKE','WIKI_PROJECTION')),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 created_at TEXT NOT NULL
);
CREATE TABLE cm_delivery(
 event_id TEXT NOT NULL REFERENCES cm_outbox(event_id), attempt INTEGER NOT NULL CHECK(attempt>=1),
 status TEXT NOT NULL CHECK(status IN ('DELIVERED','FAILED')), receipt_ref TEXT NOT NULL,
 PRIMARY KEY(event_id,attempt)
);

CREATE TRIGGER cm_head_forward BEFORE UPDATE ON cm_head
WHEN NEW.case_id!=OLD.case_id OR NEW.branch_id!=OLD.branch_id OR NEW.revision!=OLD.revision+1
BEGIN SELECT RAISE(ABORT,'head must advance one revision'); END;
CREATE TRIGGER cm_session_owner BEFORE INSERT ON cm_session_binding
WHEN NEW.user_id!=(SELECT owner_id FROM cm_conversation WHERE conversation_id=NEW.conversation_id)
BEGIN SELECT RAISE(ABORT,'session binding must match conversation owner'); END;
CREATE TRIGGER cm_turn_sequence BEFORE INSERT ON cm_turn
WHEN NEW.turn_number!=COALESCE((SELECT MAX(turn_number)+1 FROM cm_turn WHERE conversation_id=NEW.conversation_id),1)
BEGIN SELECT RAISE(ABORT,'turn numbers must be contiguous'); END;
CREATE TRIGGER cm_fact_goal_stable BEFORE INSERT ON cm_fact
WHEN NEW.previous_revision IS NOT NULL AND NEW.goal_id IS NOT
 (SELECT goal_id FROM cm_fact WHERE case_id=NEW.case_id AND branch_id=NEW.branch_id
  AND fact_id=NEW.fact_id AND revision=NEW.previous_revision)
BEGIN SELECT RAISE(ABORT,'fact goal scope cannot change across revisions'); END;
CREATE TRIGGER cm_anchor_run BEFORE INSERT ON cm_answer_anchor
WHEN NEW.run_id!=(SELECT run_id FROM cm_decision WHERE case_id=NEW.case_id
 AND branch_id=NEW.branch_id AND decision_id=NEW.decision_id)
BEGIN SELECT RAISE(ABORT,'answer anchor must identify decision from its run'); END;
CREATE TRIGGER cm_edit_target BEFORE INSERT ON cm_edit
WHEN NEW.base_revision!=(SELECT base_revision FROM cm_turn WHERE turn_id=NEW.source_turn_id)
 OR NEW.target_turn_id!=(SELECT r.turn_id FROM cm_decision d JOIN cm_run_binding r ON d.run_id=r.run_id
 WHERE d.case_id=NEW.case_id AND d.branch_id=NEW.branch_id AND d.decision_id=NEW.target_decision_id)
BEGIN SELECT RAISE(ABORT,'edit must identify the exact turn and decision at its base revision'); END;
CREATE TRIGGER cm_edit_fact_target BEFORE INSERT ON cm_edit
WHEN NEW.target_fact_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM cm_decision_fact WHERE case_id=NEW.case_id AND branch_id=NEW.branch_id
 AND decision_id=NEW.target_decision_id AND fact_id=NEW.target_fact_id
 AND fact_branch_id=NEW.target_fact_branch_id AND fact_revision=NEW.target_fact_revision)
BEGIN SELECT RAISE(ABORT,'edit fact must be a dependency of the target decision'); END;
CREATE TRIGGER cm_edit_applied_state BEFORE INSERT ON cm_edit_application
WHEN NOT EXISTS(SELECT 1 FROM cm_edit e JOIN cm_state s ON s.case_id=e.case_id
 AND s.branch_id=e.branch_id AND s.revision=e.base_revision+1 AND s.source_turn_id=e.source_turn_id
 WHERE e.edit_id=NEW.edit_id AND e.case_id=NEW.case_id AND e.branch_id=NEW.branch_id
 AND s.revision=NEW.state_revision)
BEGIN SELECT RAISE(ABORT,'edit application must use the state created by its turn'); END;
CREATE TRIGGER cm_run_base BEFORE INSERT ON cm_run_binding
WHEN NEW.base_revision!=(SELECT base_revision FROM cm_turn WHERE turn_id=NEW.turn_id)
BEGIN SELECT RAISE(ABORT,'run must start at turn base revision'); END;
CREATE TRIGGER cm_parent_cycle BEFORE INSERT ON cm_decision_parent
WHEN EXISTS(WITH RECURSIVE ancestors(id) AS (
 SELECT NEW.parent_id UNION SELECT p.parent_id FROM cm_decision_parent p JOIN ancestors a ON p.decision_id=a.id
 WHERE p.case_id=NEW.case_id AND p.branch_id=NEW.branch_id)
 SELECT 1 FROM ancestors WHERE id=NEW.decision_id)
BEGIN SELECT RAISE(ABORT,'decision cycle'); END;

-- 이력의 UPDATE/DELETE는 금지한다. cm_head만 앞으로 이동한다.

CREATE TRIGGER cm_head_initial BEFORE INSERT ON cm_head WHEN NEW.revision!=0
BEGIN SELECT RAISE(ABORT,'head starts at revision zero'); END;
CREATE TRIGGER cm_head_no_delete BEFORE DELETE ON cm_head
BEGIN SELECT RAISE(ABORT,'head cannot be removed'); END;
CREATE TRIGGER cm_state_members_sealed BEFORE INSERT ON cm_state_fact
WHEN EXISTS(SELECT 1 FROM cm_head WHERE case_id=NEW.case_id AND branch_id=NEW.branch_id AND revision>=NEW.state_revision)
BEGIN SELECT RAISE(ABORT,'committed state membership is sealed'); END;
CREATE TRIGGER cm_access_sequence BEFORE INSERT ON cm_access_event
WHEN NEW.revision!=COALESCE((SELECT MAX(revision)+1 FROM cm_access_event WHERE case_id=NEW.case_id AND principal_id=NEW.principal_id),1)
BEGIN SELECT RAISE(ABORT,'access events must be contiguous'); END;

CREATE TRIGGER cm_session_binding_no_update BEFORE UPDATE ON cm_session_binding
BEGIN SELECT RAISE(ABORT,'append-only cm_session_binding'); END;
CREATE TRIGGER cm_session_binding_no_delete BEFORE DELETE ON cm_session_binding
BEGIN SELECT RAISE(ABORT,'append-only cm_session_binding'); END;

CREATE TRIGGER cm_answer_anchor_no_update BEFORE UPDATE ON cm_answer_anchor
BEGIN SELECT RAISE(ABORT,'append-only cm_answer_anchor'); END;
CREATE TRIGGER cm_answer_anchor_no_delete BEFORE DELETE ON cm_answer_anchor
BEGIN SELECT RAISE(ABORT,'append-only cm_answer_anchor'); END;

CREATE TRIGGER cm_edit_no_update BEFORE UPDATE ON cm_edit
BEGIN SELECT RAISE(ABORT,'append-only cm_edit'); END;
CREATE TRIGGER cm_edit_no_delete BEFORE DELETE ON cm_edit
BEGIN SELECT RAISE(ABORT,'append-only cm_edit'); END;

CREATE TRIGGER cm_edit_application_no_update BEFORE UPDATE ON cm_edit_application
BEGIN SELECT RAISE(ABORT,'append-only cm_edit_application'); END;
CREATE TRIGGER cm_edit_application_no_delete BEFORE DELETE ON cm_edit_application
BEGIN SELECT RAISE(ABORT,'append-only cm_edit_application'); END;

CREATE TRIGGER cm_schema_no_update BEFORE UPDATE ON cm_schema
BEGIN SELECT RAISE(ABORT,'append-only cm_schema'); END;

CREATE TRIGGER cm_schema_no_delete BEFORE DELETE ON cm_schema
BEGIN SELECT RAISE(ABORT,'append-only cm_schema'); END;

CREATE TRIGGER cm_conversation_no_update BEFORE UPDATE ON cm_conversation
BEGIN SELECT RAISE(ABORT,'append-only cm_conversation'); END;

CREATE TRIGGER cm_conversation_no_delete BEFORE DELETE ON cm_conversation
BEGIN SELECT RAISE(ABORT,'append-only cm_conversation'); END;

CREATE TRIGGER cm_case_no_update BEFORE UPDATE ON cm_case
BEGIN SELECT RAISE(ABORT,'append-only cm_case'); END;

CREATE TRIGGER cm_case_no_delete BEFORE DELETE ON cm_case
BEGIN SELECT RAISE(ABORT,'append-only cm_case'); END;

CREATE TRIGGER cm_access_event_no_update BEFORE UPDATE ON cm_access_event
BEGIN SELECT RAISE(ABORT,'append-only cm_access_event'); END;

CREATE TRIGGER cm_access_event_no_delete BEFORE DELETE ON cm_access_event
BEGIN SELECT RAISE(ABORT,'append-only cm_access_event'); END;

CREATE TRIGGER cm_branch_no_update BEFORE UPDATE ON cm_branch
BEGIN SELECT RAISE(ABORT,'append-only cm_branch'); END;

CREATE TRIGGER cm_branch_no_delete BEFORE DELETE ON cm_branch
BEGIN SELECT RAISE(ABORT,'append-only cm_branch'); END;

CREATE TRIGGER cm_state_no_update BEFORE UPDATE ON cm_state
BEGIN SELECT RAISE(ABORT,'append-only cm_state'); END;

CREATE TRIGGER cm_state_no_delete BEFORE DELETE ON cm_state
BEGIN SELECT RAISE(ABORT,'append-only cm_state'); END;

CREATE TRIGGER cm_turn_no_update BEFORE UPDATE ON cm_turn
BEGIN SELECT RAISE(ABORT,'append-only cm_turn'); END;

CREATE TRIGGER cm_turn_no_delete BEFORE DELETE ON cm_turn
BEGIN SELECT RAISE(ABORT,'append-only cm_turn'); END;

CREATE TRIGGER cm_fact_no_update BEFORE UPDATE ON cm_fact
BEGIN SELECT RAISE(ABORT,'append-only cm_fact'); END;

CREATE TRIGGER cm_fact_no_delete BEFORE DELETE ON cm_fact
BEGIN SELECT RAISE(ABORT,'append-only cm_fact'); END;

CREATE TRIGGER cm_state_fact_no_update BEFORE UPDATE ON cm_state_fact
BEGIN SELECT RAISE(ABORT,'append-only cm_state_fact'); END;

CREATE TRIGGER cm_state_fact_no_delete BEFORE DELETE ON cm_state_fact
BEGIN SELECT RAISE(ABORT,'append-only cm_state_fact'); END;

CREATE TRIGGER cm_run_binding_no_update BEFORE UPDATE ON cm_run_binding
BEGIN SELECT RAISE(ABORT,'append-only cm_run_binding'); END;

CREATE TRIGGER cm_run_binding_no_delete BEFORE DELETE ON cm_run_binding
BEGIN SELECT RAISE(ABORT,'append-only cm_run_binding'); END;

CREATE TRIGGER cm_run_state_no_update BEFORE UPDATE ON cm_run_state
BEGIN SELECT RAISE(ABORT,'append-only cm_run_state'); END;

CREATE TRIGGER cm_run_state_no_delete BEFORE DELETE ON cm_run_state
BEGIN SELECT RAISE(ABORT,'append-only cm_run_state'); END;

CREATE TRIGGER cm_decision_no_update BEFORE UPDATE ON cm_decision
BEGIN SELECT RAISE(ABORT,'append-only cm_decision'); END;

CREATE TRIGGER cm_decision_no_delete BEFORE DELETE ON cm_decision
BEGIN SELECT RAISE(ABORT,'append-only cm_decision'); END;

CREATE TRIGGER cm_decision_fact_no_update BEFORE UPDATE ON cm_decision_fact
BEGIN SELECT RAISE(ABORT,'append-only cm_decision_fact'); END;

CREATE TRIGGER cm_decision_fact_no_delete BEFORE DELETE ON cm_decision_fact
BEGIN SELECT RAISE(ABORT,'append-only cm_decision_fact'); END;

CREATE TRIGGER cm_decision_parent_no_update BEFORE UPDATE ON cm_decision_parent
BEGIN SELECT RAISE(ABORT,'append-only cm_decision_parent'); END;

CREATE TRIGGER cm_decision_parent_no_delete BEFORE DELETE ON cm_decision_parent
BEGIN SELECT RAISE(ABORT,'append-only cm_decision_parent'); END;

CREATE TRIGGER cm_decision_check_no_update BEFORE UPDATE ON cm_decision_check
BEGIN SELECT RAISE(ABORT,'append-only cm_decision_check'); END;

CREATE TRIGGER cm_decision_check_no_delete BEFORE DELETE ON cm_decision_check
BEGIN SELECT RAISE(ABORT,'append-only cm_decision_check'); END;

CREATE TRIGGER cm_user_memory_no_update BEFORE UPDATE ON cm_user_memory
BEGIN SELECT RAISE(ABORT,'append-only cm_user_memory'); END;

CREATE TRIGGER cm_user_memory_no_delete BEFORE DELETE ON cm_user_memory
BEGIN SELECT RAISE(ABORT,'append-only cm_user_memory'); END;

CREATE TRIGGER cm_outbox_no_update BEFORE UPDATE ON cm_outbox
BEGIN SELECT RAISE(ABORT,'append-only cm_outbox'); END;

CREATE TRIGGER cm_outbox_no_delete BEFORE DELETE ON cm_outbox
BEGIN SELECT RAISE(ABORT,'append-only cm_outbox'); END;

CREATE TRIGGER cm_delivery_no_update BEFORE UPDATE ON cm_delivery
BEGIN SELECT RAISE(ABORT,'append-only cm_delivery'); END;

CREATE TRIGGER cm_delivery_no_delete BEFORE DELETE ON cm_delivery
BEGIN SELECT RAISE(ABORT,'append-only cm_delivery'); END;

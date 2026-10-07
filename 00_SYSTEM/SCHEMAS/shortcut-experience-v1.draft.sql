-- DESIGN DRAFT r2: 판단 경험 저장 설계. 실제 DB 이행 스크립트가 아님.
-- 한국어 설명: 07_DOCS/REFERENCE/REPORTS/SHORTCUT_EXPERIENCE_SCHEMA_DESIGN_20261001.md
-- Proposed additive tables in action-memory/memory.sqlite.
-- Keep its existing PRAGMA user_version and episode/concept/observation intact.
-- Turn foreign_keys ON on every connection before using this schema.
PRAGMA foreign_keys = ON;
PRAGMA recursive_triggers = ON;

CREATE TABLE shortcut_schema (
 schema_version TEXT PRIMARY KEY CHECK(schema_version='shortcut-experience-v1-draft-r2'),
 created_at TEXT NOT NULL
);

-- Same question text may have different facts, scope, permissions or attachments.
-- Do not use text hash as a global identity or a cross-tenant deduplication key.
CREATE TABLE shortcut_question (
 question_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 visibility TEXT NOT NULL CHECK(visibility IN ('OWNER','TENANT_REVIEWED')),
 sensitivity TEXT NOT NULL CHECK(sensitivity IN ('PUBLIC','INTERNAL','RESTRICTED','UNKNOWN')),
 question_text TEXT NOT NULL,
 request_json TEXT NOT NULL CHECK(json_valid(request_json)),
 request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
 received_at TEXT NOT NULL,
 UNIQUE(question_id,tenant_id)
);

-- A completed immutable package, not a live mutable SQLite file hash.
-- Failed/interrupted runs are retained as experience; they are not auto-approved.
CREATE TABLE shortcut_run (
 run_snapshot_id TEXT PRIMARY KEY,
 question_id TEXT NOT NULL,
 tenant_id TEXT NOT NULL,
 native_run_id TEXT NOT NULL,
 journal_schema TEXT NOT NULL,
 package_ref TEXT NOT NULL,
 package_hash TEXT NOT NULL CHECK(length(package_hash)=64),
 binding_json TEXT NOT NULL CHECK(json_valid(binding_json)),
 binding_hash TEXT NOT NULL CHECK(length(binding_hash)=64),
 data_key TEXT NOT NULL CHECK(length(data_key)=64),
 run_status TEXT NOT NULL CHECK(run_status IN ('COMPLETED','FAILED','INTERRUPTED')),
 recorded_at TEXT NOT NULL,
 FOREIGN KEY(question_id,tenant_id) REFERENCES shortcut_question(question_id,tenant_id),
 UNIQUE(tenant_id,native_run_id,package_hash),
 UNIQUE(run_snapshot_id,question_id,tenant_id)
);
CREATE INDEX shortcut_run_question ON shortcut_run(tenant_id,question_id,data_key);

-- Explicit product decisions/reasons. Not the model's hidden chain of thought.
-- Full input/output stay in the immutable package, addressed by ref+hash.
CREATE TABLE shortcut_step (
 step_id TEXT PRIMARY KEY,
 run_snapshot_id TEXT NOT NULL REFERENCES shortcut_run(run_snapshot_id),
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 stage TEXT NOT NULL CHECK(stage IN ('ROUTE','SEARCH_PLAN','SEARCH_RESULT','READ','SOURCE_SELECT','QUESTION_PLAN','CLAIM','ANSWER')),
 record_kind TEXT NOT NULL CHECK(record_kind IN ('DECISION','TOOL_RESULT')),
 operation TEXT NOT NULL,
 outcome TEXT NOT NULL CHECK(outcome IN ('OK','PARTIAL','FAILED','UNKNOWN')),
 input_ref TEXT NOT NULL,
 input_hash TEXT NOT NULL CHECK(length(input_hash)=64),
 result_ref TEXT NOT NULL,
 result_hash TEXT NOT NULL CHECK(length(result_hash)=64),
 reason TEXT NOT NULL,
 applicability_json TEXT NOT NULL CHECK(json_valid(applicability_json)),
 native_event_refs_json TEXT NOT NULL CHECK(json_valid(native_event_refs_json)),
 created_at TEXT NOT NULL,
 UNIQUE(run_snapshot_id,ordinal)
);
CREATE INDEX shortcut_step_stage ON shortcut_step(run_snapshot_id,stage,operation,ordinal);

-- Writer must additionally enforce acyclicity and actual parent/input matching.
CREATE TABLE shortcut_step_dependency (
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 prerequisite_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 prerequisite_result_hash TEXT NOT NULL CHECK(length(prerequisite_result_hash)=64),
 PRIMARY KEY(step_id,prerequisite_id),
 CHECK(step_id!=prerequisite_id)
);
CREATE INDEX shortcut_dependency_parent ON shortcut_step_dependency(prerequisite_id);

-- Store exact ranked snapshots only when actually recorded. READ_POOL_ONLY
-- cannot be used to reconstruct or certify the complete search ranking.
CREATE TABLE shortcut_candidate_pool (
 pool_id TEXT PRIMARY KEY,
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 coverage TEXT NOT NULL CHECK(coverage IN ('RANKED_COMPLETE','RANKED_PARTIAL','READ_POOL_ONLY')),
 query_filters_ref TEXT NOT NULL,
 query_filters_hash TEXT NOT NULL CHECK(length(query_filters_hash)=64),
 index_binding_hash TEXT NOT NULL CHECK(length(index_binding_hash)=64),
 payload_ref TEXT NOT NULL,
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 candidate_count INTEGER NOT NULL CHECK(candidate_count>=0),
 complete INTEGER NOT NULL CHECK(complete IN (0,1)),
 CHECK(coverage!='RANKED_COMPLETE' OR complete=1)
);

CREATE TABLE shortcut_evidence_ref (
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 evidence_key TEXT NOT NULL,
 document_id TEXT NOT NULL,
 source_id TEXT NOT NULL,
 unit_id TEXT,
 generation_id TEXT NOT NULL,
 origin_hash TEXT NOT NULL CHECK(length(origin_hash)=64),
 span_refs_json TEXT NOT NULL CHECK(json_valid(span_refs_json)),
 read_receipt_ref TEXT NOT NULL,
 read_receipt_hash TEXT NOT NULL CHECK(length(read_receipt_hash)=64),
 delivered_view_ref TEXT,
 delivered_text_hash TEXT CHECK(delivered_text_hash IS NULL OR length(delivered_text_hash)=64),
 acquired_complete INTEGER NOT NULL CHECK(acquired_complete IN (0,1)),
 PRIMARY KEY(step_id,evidence_key),
 CHECK((delivered_view_ref IS NULL)=(delivered_text_hash IS NULL))
);

-- Small derived prompt projection. Full reasons, conditions and proofs remain
-- addressable. Every summary must be checked against its referenced originals.
CREATE TABLE shortcut_capsule (
 capsule_id TEXT PRIMARY KEY,
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 revision INTEGER NOT NULL CHECK(revision>=1),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)),
 body_hash TEXT NOT NULL CHECK(length(body_hash)=64),
 source_result_hash TEXT NOT NULL CHECK(length(source_result_hash)=64),
 compiler_binding_json TEXT NOT NULL CHECK(json_valid(compiler_binding_json)),
 created_at TEXT NOT NULL,
 UNIQUE(step_id,revision),
 UNIQUE(capsule_id,step_id)
);

-- Integrity, task relevance and legal correctness are independent reviews.
-- A recent hash/integrity PASS does not supersede a legal FAIL.
CREATE TABLE shortcut_review (
 review_id TEXT PRIMARY KEY,
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 capsule_id TEXT,
 review_kind TEXT NOT NULL CHECK(review_kind IN ('SOURCE_INTEGRITY','TASK_RELEVANCE','LEGAL_CORRECTNESS','CAPSULE_FIDELITY')),
 verdict TEXT NOT NULL CHECK(verdict IN ('PASS','FAIL','UNKNOWN')),
 reviewer_kind TEXT NOT NULL CHECK(reviewer_kind IN ('HUMAN','MODEL','CODE')),
 reviewer_id TEXT NOT NULL,
 reason TEXT NOT NULL,
 proof_ref TEXT NOT NULL,
 proof_hash TEXT NOT NULL CHECK(length(proof_hash)=64),
 policy_version TEXT NOT NULL,
 supersedes_review_id TEXT REFERENCES shortcut_review(review_id),
 created_at TEXT NOT NULL,
 FOREIGN KEY(capsule_id,step_id) REFERENCES shortcut_capsule(capsule_id,step_id),
 CHECK(review_kind!='LEGAL_CORRECTNESS' OR reviewer_kind!='CODE'),
 CHECK((review_kind='CAPSULE_FIDELITY')=(capsule_id IS NOT NULL))
);

-- Append-only lifecycle. OBSERVED and HINT_ONLY never mean approved replay.
-- Service must honor existing abstraction_state and review failures as well.
CREATE TABLE shortcut_step_event (
 event_id TEXT PRIMARY KEY,
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 revision INTEGER NOT NULL CHECK(revision>=1),
 state TEXT NOT NULL CHECK(state IN ('OBSERVED','HINT_ONLY','REUSABLE','DISPUTED','STALE','RETRACTED')),
 reason TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 policy_version TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(step_id,revision)
);
CREATE VIEW shortcut_step_head AS
 SELECT e.* FROM shortcut_step_event e
 WHERE NOT EXISTS(SELECT 1 FROM shortcut_step_event later
                  WHERE later.step_id=e.step_id AND later.revision>e.revision);

-- Opaque handoff from the OTHER question-grouping wiki. Do not duplicate
-- that system's concept/cluster authority here. Selection is not legal review.
CREATE TABLE shortcut_route_selection (
 selection_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 current_question_id TEXT NOT NULL,
 past_question_id TEXT NOT NULL,
 wiki_provider TEXT NOT NULL,
 wiki_group_ref TEXT NOT NULL,
 wiki_revision TEXT NOT NULL,
 selector_id TEXT NOT NULL,
 selection_reason TEXT NOT NULL,
 selected_at TEXT NOT NULL,
 FOREIGN KEY(current_question_id,tenant_id) REFERENCES shortcut_question(question_id,tenant_id),
 FOREIGN KEY(past_question_id,tenant_id) REFERENCES shortcut_question(question_id,tenant_id),
 CHECK(current_question_id!=past_question_id),
 UNIQUE(selection_id,past_question_id,tenant_id)
);

-- 선택 실행: 사용자가 고른 질문 아래에서 서버가 사용할 실행을 한 번 고정한다.
CREATE TABLE shortcut_run_binding (
 binding_id TEXT PRIMARY KEY,
 selection_id TEXT NOT NULL UNIQUE,
 past_question_id TEXT NOT NULL,
 tenant_id TEXT NOT NULL,
 run_snapshot_id TEXT NOT NULL,
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL,
 FOREIGN KEY(selection_id,past_question_id,tenant_id)
   REFERENCES shortcut_route_selection(selection_id,past_question_id,tenant_id),
 FOREIGN KEY(run_snapshot_id,past_question_id,tenant_id)
   REFERENCES shortcut_run(run_snapshot_id,question_id,tenant_id),
 UNIQUE(binding_id,selection_id)
);

-- 재사용 규칙: 단계/동작별 검토 요건·입출력 계약·복구 방법을 버전 고정한다.
CREATE TABLE shortcut_reuse_policy (
 policy_id TEXT PRIMARY KEY,
 stage TEXT NOT NULL,
 operation TEXT NOT NULL,
 contract_json TEXT NOT NULL CHECK(json_valid(contract_json)),
 contract_hash TEXT NOT NULL CHECK(length(contract_hash)=64),
 created_at TEXT NOT NULL
);

-- Exact memory projection sent in ONE current model attempt. request_hash
-- links back to the native journal's complete final wire request.
CREATE TABLE shortcut_prompt_packet (
 packet_id TEXT PRIMARY KEY,
 selection_id TEXT NOT NULL REFERENCES shortcut_route_selection(selection_id),
 binding_id TEXT NOT NULL,
 current_run_id TEXT NOT NULL,
 model_attempt_id TEXT NOT NULL,
 phase TEXT NOT NULL,
 current_state_revision INTEGER NOT NULL CHECK(current_state_revision>=0),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)),
 body_hash TEXT NOT NULL CHECK(length(body_hash)=64),
 request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
 byte_count INTEGER NOT NULL CHECK(byte_count>=0),
 token_count INTEGER NOT NULL CHECK(token_count>=0),
 request_byte_count INTEGER NOT NULL CHECK(request_byte_count>=byte_count),
 request_token_count INTEGER NOT NULL CHECK(request_token_count>=token_count),
 token_counter_binding TEXT NOT NULL,
 budget_policy_json TEXT NOT NULL CHECK(json_valid(budget_policy_json)),
 delivery_ref TEXT NOT NULL,
 created_at TEXT NOT NULL,
 FOREIGN KEY(binding_id,selection_id) REFERENCES shortcut_run_binding(binding_id,selection_id),
 UNIQUE(current_run_id,model_attempt_id)
);

-- 전달 목록: 실제 프롬프트의 짧은 번호와 원본 기록을 연결한다.
CREATE TABLE shortcut_packet_item (
 packet_id TEXT NOT NULL REFERENCES shortcut_prompt_packet(packet_id),
 memory_ref INTEGER NOT NULL CHECK(memory_ref>0),
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 capsule_id TEXT NOT NULL,
 PRIMARY KEY(packet_id,memory_ref),
 UNIQUE(packet_id,step_id,capsule_id),
 FOREIGN KEY(capsule_id,step_id) REFERENCES shortcut_capsule(capsule_id,step_id)
);

CREATE TABLE shortcut_reuse_event (
 reuse_event_id TEXT PRIMARY KEY,
 packet_id TEXT NOT NULL REFERENCES shortcut_prompt_packet(packet_id),
 step_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 capsule_id TEXT NOT NULL,
 policy_id TEXT NOT NULL REFERENCES shortcut_reuse_policy(policy_id),
 action TEXT NOT NULL CHECK(action IN ('HINT_USED','ADOPTED','REVISED','REJECTED','BLOCKED')),
 reason TEXT NOT NULL,
 preflight_json TEXT NOT NULL CHECK(json_valid(preflight_json)),
 current_result_ref TEXT,
 current_result_hash TEXT CHECK(current_result_hash IS NULL OR length(current_result_hash)=64),
 created_at TEXT NOT NULL,
 FOREIGN KEY(capsule_id,step_id) REFERENCES shortcut_capsule(capsule_id,step_id),
 FOREIGN KEY(packet_id,step_id,capsule_id) REFERENCES shortcut_packet_item(packet_id,step_id,capsule_id),
 UNIQUE(packet_id,step_id,capsule_id),
 CHECK((current_result_ref IS NULL)=(current_result_hash IS NULL)),
 CHECK(action NOT IN ('ADOPTED','REVISED') OR current_result_ref IS NOT NULL)
);

-- 부모 대응: 과거의 필수 부모 각각이 현재 어떤 결과로 확인됐는지 기록한다.
-- 현재 새로 판단한 부모는 parent_reuse_event_id=NULL이고 결과 참조를 반드시 남긴다.
CREATE TABLE shortcut_reuse_dependency (
 reuse_event_id TEXT NOT NULL REFERENCES shortcut_reuse_event(reuse_event_id),
 past_prerequisite_id TEXT NOT NULL REFERENCES shortcut_step(step_id),
 current_result_ref TEXT NOT NULL,
 current_result_hash TEXT NOT NULL CHECK(length(current_result_hash)=64),
 parent_reuse_event_id TEXT REFERENCES shortcut_reuse_event(reuse_event_id),
 compatibility TEXT NOT NULL CHECK(compatibility IN ('MATCH','CHANGED','UNKNOWN')),
 reason TEXT NOT NULL,
 check_ref TEXT NOT NULL,
 check_hash TEXT NOT NULL CHECK(length(check_hash)=64),
 PRIMARY KEY(reuse_event_id,past_prerequisite_id),
 CHECK(parent_reuse_event_id IS NULL OR parent_reuse_event_id!=reuse_event_id)
);

-- 작업 처리 기록: 판단 채택과 실제 작업 생략은 별도로 보존한다.
-- task_key는 단계 전체가 아닌 개별 작업(예: 후보 3의 선별)을 식별한다.
CREATE TABLE shortcut_work_receipt (
 receipt_id TEXT PRIMARY KEY,
 reuse_event_id TEXT NOT NULL REFERENCES shortcut_reuse_event(reuse_event_id),
 current_run_id TEXT NOT NULL,
 task_key TEXT NOT NULL,
 attempt_no INTEGER NOT NULL CHECK(attempt_no>=1),
 operation TEXT NOT NULL,
 outcome TEXT NOT NULL CHECK(outcome IN ('SKIPPED','EXECUTED','FALLBACK','FAILED')),
 result_ref TEXT,
 result_hash TEXT CHECK(result_hash IS NULL OR length(result_hash)=64),
 native_event_ref TEXT NOT NULL,
 native_event_hash TEXT NOT NULL CHECK(length(native_event_hash)=64),
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(current_run_id,task_key,attempt_no),
 CHECK((result_ref IS NULL)=(result_hash IS NULL)),
 CHECK(outcome NOT IN ('SKIPPED','EXECUTED') OR result_ref IS NOT NULL)
);
CREATE INDEX shortcut_work_task ON shortcut_work_receipt(current_run_id,task_key,attempt_no);

CREATE TRIGGER shortcut_packet_selected_run BEFORE INSERT ON shortcut_packet_item
WHEN (SELECT run_snapshot_id FROM shortcut_step WHERE step_id=NEW.step_id) !=
 (SELECT b.run_snapshot_id FROM shortcut_prompt_packet p JOIN shortcut_run_binding b
  ON b.binding_id=p.binding_id WHERE p.packet_id=NEW.packet_id)
BEGIN SELECT RAISE(ABORT,'memory must belong to selected run'); END;

CREATE TRIGGER shortcut_policy_stage BEFORE INSERT ON shortcut_reuse_event
WHEN NOT EXISTS(SELECT 1 FROM shortcut_step s JOIN shortcut_reuse_policy p
 ON p.stage=s.stage AND p.operation=s.operation WHERE s.step_id=NEW.step_id AND p.policy_id=NEW.policy_id)
BEGIN SELECT RAISE(ABORT,'reuse policy stage/operation mismatch'); END;

CREATE TRIGGER shortcut_parent_mapping BEFORE INSERT ON shortcut_reuse_dependency
WHEN NOT EXISTS(SELECT 1 FROM shortcut_reuse_event r JOIN shortcut_step_dependency d
 ON d.step_id=r.step_id WHERE r.reuse_event_id=NEW.reuse_event_id AND d.prerequisite_id=NEW.past_prerequisite_id)
BEGIN SELECT RAISE(ABORT,'not a prerequisite of this step'); END;

CREATE TRIGGER shortcut_parent_reuse BEFORE INSERT ON shortcut_reuse_dependency
WHEN NEW.parent_reuse_event_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM shortcut_reuse_event parent JOIN shortcut_prompt_packet pp ON pp.packet_id=parent.packet_id
 JOIN shortcut_reuse_event child ON child.reuse_event_id=NEW.reuse_event_id
 JOIN shortcut_prompt_packet cp ON cp.packet_id=child.packet_id
 WHERE parent.reuse_event_id=NEW.parent_reuse_event_id AND parent.step_id=NEW.past_prerequisite_id
 AND parent.action IN ('ADOPTED','REVISED') AND pp.current_run_id=cp.current_run_id
 AND parent.current_result_ref=NEW.current_result_ref AND parent.current_result_hash=NEW.current_result_hash)
BEGIN SELECT RAISE(ABORT,'parent reuse result/run mismatch'); END;

CREATE TRIGGER shortcut_work_run BEFORE INSERT ON shortcut_work_receipt
WHEN NEW.current_run_id!=(SELECT p.current_run_id FROM shortcut_reuse_event r
 JOIN shortcut_prompt_packet p ON p.packet_id=r.packet_id WHERE r.reuse_event_id=NEW.reuse_event_id)
BEGIN SELECT RAISE(ABORT,'work receipt run mismatch'); END;

CREATE TRIGGER shortcut_skip_guard BEFORE INSERT ON shortcut_work_receipt
WHEN NEW.outcome='SKIPPED' AND (
 NOT EXISTS(SELECT 1 FROM shortcut_reuse_event r WHERE r.reuse_event_id=NEW.reuse_event_id
 AND r.action IN ('ADOPTED','REVISED') AND r.current_result_ref=NEW.result_ref AND r.current_result_hash=NEW.result_hash)
 OR EXISTS(SELECT 1 FROM shortcut_reuse_event r JOIN shortcut_step_dependency d ON d.step_id=r.step_id
 WHERE r.reuse_event_id=NEW.reuse_event_id AND NOT EXISTS(
 SELECT 1 FROM shortcut_reuse_dependency m WHERE m.reuse_event_id=r.reuse_event_id
 AND m.past_prerequisite_id=d.prerequisite_id AND m.compatibility='MATCH')))
BEGIN SELECT RAISE(ABORT,'skip requires adopted result and all matching parents'); END;

-- Immutable fact rows: lifecycle and corrections append new identities/events.
-- Lifecycle and capsule checks supplement the application writer policy.
CREATE TRIGGER shortcut_event_sequence BEFORE INSERT ON shortcut_step_event
WHEN NEW.revision!=COALESCE((SELECT MAX(revision)+1 FROM shortcut_step_event WHERE step_id=NEW.step_id),1)
BEGIN SELECT RAISE(ABORT,'step events must be contiguous'); END;

CREATE TRIGGER shortcut_event_no_resurrection BEFORE INSERT ON shortcut_step_event
WHEN NEW.state!='RETRACTED' AND EXISTS(SELECT 1 FROM shortcut_step_event WHERE step_id=NEW.step_id AND state='RETRACTED')
BEGIN SELECT RAISE(ABORT,'retracted step needs a new identity'); END;

CREATE TRIGGER shortcut_capsule_parent BEFORE INSERT ON shortcut_capsule
WHEN NEW.source_result_hash!=(SELECT result_hash FROM shortcut_step WHERE step_id=NEW.step_id)
BEGIN SELECT RAISE(ABORT,'capsule parent result mismatch'); END;

CREATE TRIGGER shortcut_dependency_hash BEFORE INSERT ON shortcut_step_dependency
WHEN NEW.prerequisite_result_hash!=(SELECT result_hash FROM shortcut_step WHERE step_id=NEW.prerequisite_id)
BEGIN SELECT RAISE(ABORT,'dependency result mismatch'); END;

CREATE TRIGGER shortcut_dependency_cycle BEFORE INSERT ON shortcut_step_dependency
WHEN EXISTS(
 WITH RECURSIVE ancestors(id) AS (
  SELECT NEW.prerequisite_id UNION
  SELECT d.prerequisite_id FROM shortcut_step_dependency d JOIN ancestors a ON d.step_id=a.id
 ) SELECT 1 FROM ancestors WHERE id=NEW.step_id
)
BEGIN SELECT RAISE(ABORT,'cyclic step dependency'); END;
CREATE TRIGGER shortcut_question_immutable_update BEFORE UPDATE ON shortcut_question
BEGIN SELECT RAISE(ABORT,'append-only shortcut_question'); END;
CREATE TRIGGER shortcut_question_immutable_delete BEFORE DELETE ON shortcut_question
BEGIN SELECT RAISE(ABORT,'append-only shortcut_question'); END;

CREATE TRIGGER shortcut_run_immutable_update BEFORE UPDATE ON shortcut_run
BEGIN SELECT RAISE(ABORT,'append-only shortcut_run'); END;
CREATE TRIGGER shortcut_run_immutable_delete BEFORE DELETE ON shortcut_run
BEGIN SELECT RAISE(ABORT,'append-only shortcut_run'); END;

CREATE TRIGGER shortcut_step_immutable_update BEFORE UPDATE ON shortcut_step
BEGIN SELECT RAISE(ABORT,'append-only shortcut_step'); END;
CREATE TRIGGER shortcut_step_immutable_delete BEFORE DELETE ON shortcut_step
BEGIN SELECT RAISE(ABORT,'append-only shortcut_step'); END;

CREATE TRIGGER shortcut_step_dependency_immutable_update BEFORE UPDATE ON shortcut_step_dependency
BEGIN SELECT RAISE(ABORT,'append-only shortcut_step_dependency'); END;
CREATE TRIGGER shortcut_step_dependency_immutable_delete BEFORE DELETE ON shortcut_step_dependency
BEGIN SELECT RAISE(ABORT,'append-only shortcut_step_dependency'); END;

CREATE TRIGGER shortcut_candidate_pool_immutable_update BEFORE UPDATE ON shortcut_candidate_pool
BEGIN SELECT RAISE(ABORT,'append-only shortcut_candidate_pool'); END;
CREATE TRIGGER shortcut_candidate_pool_immutable_delete BEFORE DELETE ON shortcut_candidate_pool
BEGIN SELECT RAISE(ABORT,'append-only shortcut_candidate_pool'); END;

CREATE TRIGGER shortcut_evidence_ref_immutable_update BEFORE UPDATE ON shortcut_evidence_ref
BEGIN SELECT RAISE(ABORT,'append-only shortcut_evidence_ref'); END;
CREATE TRIGGER shortcut_evidence_ref_immutable_delete BEFORE DELETE ON shortcut_evidence_ref
BEGIN SELECT RAISE(ABORT,'append-only shortcut_evidence_ref'); END;

CREATE TRIGGER shortcut_capsule_immutable_update BEFORE UPDATE ON shortcut_capsule
BEGIN SELECT RAISE(ABORT,'append-only shortcut_capsule'); END;
CREATE TRIGGER shortcut_capsule_immutable_delete BEFORE DELETE ON shortcut_capsule
BEGIN SELECT RAISE(ABORT,'append-only shortcut_capsule'); END;

CREATE TRIGGER shortcut_review_immutable_update BEFORE UPDATE ON shortcut_review
BEGIN SELECT RAISE(ABORT,'append-only shortcut_review'); END;
CREATE TRIGGER shortcut_review_immutable_delete BEFORE DELETE ON shortcut_review
BEGIN SELECT RAISE(ABORT,'append-only shortcut_review'); END;

CREATE TRIGGER shortcut_step_event_immutable_update BEFORE UPDATE ON shortcut_step_event
BEGIN SELECT RAISE(ABORT,'append-only shortcut_step_event'); END;
CREATE TRIGGER shortcut_step_event_immutable_delete BEFORE DELETE ON shortcut_step_event
BEGIN SELECT RAISE(ABORT,'append-only shortcut_step_event'); END;

CREATE TRIGGER shortcut_route_selection_immutable_update BEFORE UPDATE ON shortcut_route_selection
BEGIN SELECT RAISE(ABORT,'append-only shortcut_route_selection'); END;
CREATE TRIGGER shortcut_route_selection_immutable_delete BEFORE DELETE ON shortcut_route_selection
BEGIN SELECT RAISE(ABORT,'append-only shortcut_route_selection'); END;

CREATE TRIGGER shortcut_prompt_packet_immutable_update BEFORE UPDATE ON shortcut_prompt_packet
BEGIN SELECT RAISE(ABORT,'append-only shortcut_prompt_packet'); END;
CREATE TRIGGER shortcut_prompt_packet_immutable_delete BEFORE DELETE ON shortcut_prompt_packet
BEGIN SELECT RAISE(ABORT,'append-only shortcut_prompt_packet'); END;

CREATE TRIGGER shortcut_reuse_event_immutable_update BEFORE UPDATE ON shortcut_reuse_event
BEGIN SELECT RAISE(ABORT,'append-only shortcut_reuse_event'); END;
CREATE TRIGGER shortcut_reuse_event_immutable_delete BEFORE DELETE ON shortcut_reuse_event
BEGIN SELECT RAISE(ABORT,'append-only shortcut_reuse_event'); END;

-- 과거 단계의 부모는 같은 실행 안에 둔다. 실행 간 재사용은 reuse_dependency로 기록한다.
CREATE TRIGGER shortcut_dependency_run BEFORE INSERT ON shortcut_step_dependency
WHEN (SELECT run_snapshot_id FROM shortcut_step WHERE step_id=NEW.step_id) !=
     (SELECT run_snapshot_id FROM shortcut_step WHERE step_id=NEW.prerequisite_id)
BEGIN SELECT RAISE(ABORT,'step dependencies must stay in one run'); END;

CREATE TRIGGER shortcut_review_supersedes BEFORE INSERT ON shortcut_review
WHEN NEW.supersedes_review_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM shortcut_review r WHERE r.review_id=NEW.supersedes_review_id
 AND r.step_id=NEW.step_id AND r.review_kind=NEW.review_kind AND r.capsule_id IS NEW.capsule_id)
BEGIN SELECT RAISE(ABORT,'review replacement must have same target/kind'); END;

CREATE TRIGGER shortcut_schema_immutable_update BEFORE UPDATE ON shortcut_schema
BEGIN SELECT RAISE(ABORT,'append-only shortcut_schema'); END;

CREATE TRIGGER shortcut_schema_immutable_delete BEFORE DELETE ON shortcut_schema
BEGIN SELECT RAISE(ABORT,'append-only shortcut_schema'); END;

CREATE TRIGGER shortcut_run_binding_immutable_update BEFORE UPDATE ON shortcut_run_binding
BEGIN SELECT RAISE(ABORT,'append-only shortcut_run_binding'); END;

CREATE TRIGGER shortcut_run_binding_immutable_delete BEFORE DELETE ON shortcut_run_binding
BEGIN SELECT RAISE(ABORT,'append-only shortcut_run_binding'); END;

CREATE TRIGGER shortcut_reuse_policy_immutable_update BEFORE UPDATE ON shortcut_reuse_policy
BEGIN SELECT RAISE(ABORT,'append-only shortcut_reuse_policy'); END;

CREATE TRIGGER shortcut_reuse_policy_immutable_delete BEFORE DELETE ON shortcut_reuse_policy
BEGIN SELECT RAISE(ABORT,'append-only shortcut_reuse_policy'); END;

CREATE TRIGGER shortcut_packet_item_immutable_update BEFORE UPDATE ON shortcut_packet_item
BEGIN SELECT RAISE(ABORT,'append-only shortcut_packet_item'); END;

CREATE TRIGGER shortcut_packet_item_immutable_delete BEFORE DELETE ON shortcut_packet_item
BEGIN SELECT RAISE(ABORT,'append-only shortcut_packet_item'); END;

CREATE TRIGGER shortcut_reuse_dependency_immutable_update BEFORE UPDATE ON shortcut_reuse_dependency
BEGIN SELECT RAISE(ABORT,'append-only shortcut_reuse_dependency'); END;

CREATE TRIGGER shortcut_reuse_dependency_immutable_delete BEFORE DELETE ON shortcut_reuse_dependency
BEGIN SELECT RAISE(ABORT,'append-only shortcut_reuse_dependency'); END;

CREATE TRIGGER shortcut_work_receipt_immutable_update BEFORE UPDATE ON shortcut_work_receipt
BEGIN SELECT RAISE(ABORT,'append-only shortcut_work_receipt'); END;

CREATE TRIGGER shortcut_work_receipt_immutable_delete BEFORE DELETE ON shortcut_work_receipt
BEGIN SELECT RAISE(ABORT,'append-only shortcut_work_receipt'); END;

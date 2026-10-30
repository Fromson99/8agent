-- Per-request legal-agent journal. Product schema version 3.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
PRAGMA user_version = 4;

CREATE TABLE run (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 run_id TEXT NOT NULL UNIQUE,
 query_id TEXT NOT NULL UNIQUE,
 binding_hash TEXT NOT NULL CHECK(length(binding_hash)=64),
 binding_json TEXT NOT NULL CHECK(json_valid(binding_json)),
 request_json TEXT NOT NULL CHECK(json_valid(request_json)),
 status TEXT NOT NULL CHECK(status IN ('RUNNING','COMMIT_READY','COMPLETED','INTERRUPTED','FAILED')),
 phase TEXT NOT NULL CHECK(phase IN ('INVESTIGATE','SELECT','ASSEMBLE','ANSWER','REVIEW','PUBLISH','END')),
 state_revision INTEGER NOT NULL DEFAULT 0 CHECK(state_revision>=0),
 evidence_revision INTEGER NOT NULL DEFAULT 0 CHECK(evidence_revision>=0),
 cycle INTEGER NOT NULL DEFAULT 0 CHECK(cycle>=0),
 next_event_seq INTEGER NOT NULL DEFAULT 1 CHECK(next_event_seq>=1),
 gate TEXT CHECK(gate IN ('READY','BOUNDED','CLARIFY')),
 owner_boot_id TEXT NOT NULL,
 started_at TEXT NOT NULL,
 deadline_at TEXT NOT NULL
);

CREATE TABLE event (
 seq INTEGER PRIMARY KEY CHECK(seq>=1),
 event_id TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL,
 state_before INTEGER NOT NULL CHECK(state_before>=0),
 state_after INTEGER NOT NULL CHECK(state_after>=state_before),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 created_at TEXT NOT NULL
);

CREATE TABLE entity_version (
 kind TEXT NOT NULL CHECK(kind IN ('intent','fact','issue','assessment','finding','claim','challenge','review','relation','relation_set','relation_assessment','source_selection','source_bundle')),
 entity_id TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version>=1),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 created_seq INTEGER NOT NULL REFERENCES event(seq),
 PRIMARY KEY(kind,entity_id,version)
);

CREATE TABLE entity_head (
 kind TEXT NOT NULL,
 entity_id TEXT NOT NULL,
 version INTEGER NOT NULL,
 validity TEXT NOT NULL CHECK(validity IN ('CURRENT','STALE','CONTESTED','RETRACTED')),
 PRIMARY KEY(kind,entity_id),
 FOREIGN KEY(kind,entity_id,version) REFERENCES entity_version(kind,entity_id,version)
);

CREATE TABLE dependency (
 dependent_kind TEXT NOT NULL,
 dependent_id TEXT NOT NULL,
 dependent_version INTEGER NOT NULL,
 prerequisite_kind TEXT NOT NULL,
 prerequisite_id TEXT NOT NULL,
 prerequisite_version INTEGER NOT NULL,
 PRIMARY KEY(dependent_kind,dependent_id,dependent_version,prerequisite_kind,prerequisite_id,prerequisite_version),
 FOREIGN KEY(dependent_kind,dependent_id,dependent_version) REFERENCES entity_version(kind,entity_id,version),
 FOREIGN KEY(prerequisite_kind,prerequisite_id,prerequisite_version) REFERENCES entity_version(kind,entity_id,version),
 CHECK(NOT(dependent_kind=prerequisite_kind AND dependent_id=prerequisite_id AND dependent_version=prerequisite_version))
);
CREATE INDEX dependency_prerequisite ON dependency(prerequisite_kind,prerequisite_id,prerequisite_version);

CREATE TABLE evidence_unit (
 evidence_id TEXT PRIMARY KEY,
 source_id TEXT NOT NULL,
 document_id TEXT NOT NULL,
 unit_id TEXT,
 generation_id TEXT NOT NULL,
 source_artifact_hash TEXT NOT NULL CHECK(length(source_artifact_hash)=64),
 text_hash TEXT NOT NULL CHECK(length(text_hash)=64),
 role TEXT NOT NULL CHECK(role IN ('normative','interpretive','reference')),
 temporal_status TEXT NOT NULL CHECK(temporal_status IN ('verified','unknown')),
 metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
 created_seq INTEGER NOT NULL REFERENCES event(seq)
);

CREATE TABLE evidence_span (
 evidence_id TEXT NOT NULL REFERENCES evidence_unit(evidence_id),
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 block_id TEXT NOT NULL,
 start_cp INTEGER NOT NULL CHECK(start_cp>=0),
 end_cp INTEGER NOT NULL CHECK(end_cp>start_cp),
 text TEXT NOT NULL,
 block_hash TEXT NOT NULL CHECK(length(block_hash)=64),
 span_hash TEXT NOT NULL CHECK(length(span_hash)=64),
 PRIMARY KEY(evidence_id,ordinal)
);

CREATE TABLE observation (
 observation_id TEXT PRIMARY KEY,
 tool TEXT NOT NULL,
 request_key TEXT NOT NULL,
 request_json TEXT NOT NULL CHECK(json_valid(request_json)),
 result_json TEXT NOT NULL CHECK(json_valid(result_json)),
 result_hash TEXT NOT NULL CHECK(length(result_hash)=64),
 status TEXT NOT NULL CHECK(status IN ('OK','NOT_FOUND','UNRESOLVED','DENIED','ERROR','TRUNCATED','EMPTY','PARTIAL','REUSED')),
 created_seq INTEGER NOT NULL REFERENCES event(seq)
);
CREATE INDEX observation_request ON observation(request_key);
CREATE TABLE observation_evidence (
 observation_id TEXT NOT NULL REFERENCES observation(observation_id),
 evidence_id TEXT NOT NULL REFERENCES evidence_unit(evidence_id),
 PRIMARY KEY(observation_id,evidence_id)
);

CREATE TABLE evidence_dependency (
 kind TEXT NOT NULL,
 entity_id TEXT NOT NULL,
 version INTEGER NOT NULL,
 evidence_id TEXT NOT NULL REFERENCES evidence_unit(evidence_id),
 PRIMARY KEY(kind,entity_id,version,evidence_id),
 FOREIGN KEY(kind,entity_id,version) REFERENCES entity_version(kind,entity_id,version)
);

CREATE TABLE frontier (
 item_id TEXT PRIMARY KEY,
 issue_id TEXT,
 operation_json TEXT NOT NULL CHECK(json_valid(operation_json)),
 dedupe_key TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','DONE','EXHAUSTED','BLOCKED')),
 priority INTEGER NOT NULL,
 reason TEXT NOT NULL,
 last_observation_id TEXT REFERENCES observation(observation_id),
 created_seq INTEGER NOT NULL REFERENCES event(seq)
);
CREATE INDEX frontier_pending ON frontier(status,priority,item_id);

CREATE TABLE model_view (
 view_id TEXT PRIMARY KEY,
 phase TEXT NOT NULL CHECK(phase IN ('investigate','review','compose','repair','rebuttal','select_sources')),
 base_state_revision INTEGER NOT NULL CHECK(base_state_revision>=0),
 evidence_revision INTEGER NOT NULL CHECK(evidence_revision>=0),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)),
 body_hash TEXT NOT NULL CHECK(length(body_hash)=64),
 created_seq INTEGER NOT NULL REFERENCES event(seq)
);

CREATE TABLE presentation (
 view_id TEXT NOT NULL REFERENCES model_view(view_id),
 evidence_id TEXT NOT NULL REFERENCES evidence_unit(evidence_id),
 delivered_text_hash TEXT NOT NULL CHECK(length(delivered_text_hash)=64),
 PRIMARY KEY(view_id,evidence_id)
);

CREATE TABLE model_attempt (
 attempt_id TEXT PRIMARY KEY,
 logical_call_id TEXT NOT NULL,
 attempt_no INTEGER NOT NULL CHECK(attempt_no>=1),
 view_id TEXT NOT NULL REFERENCES model_view(view_id),
 request_json TEXT NOT NULL CHECK(json_valid(request_json)),
 request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
 status TEXT NOT NULL CHECK(status IN ('PREPARED','SENT','SUCCEEDED','FAILED','UNKNOWN','IGNORED_LATE')),
 response_json TEXT CHECK(response_json IS NULL OR json_valid(response_json)),
 response_hash TEXT CHECK(response_hash IS NULL OR length(response_hash)=64),
 receipt_json TEXT CHECK(receipt_json IS NULL OR json_valid(receipt_json)),
 input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens>=0),
 output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens>=0),
 cost_usd REAL CHECK(cost_usd IS NULL OR cost_usd>=0),
 started_at TEXT,
 finished_at TEXT,
 created_seq INTEGER NOT NULL REFERENCES event(seq),
 UNIQUE(logical_call_id,attempt_no)
);

CREATE TABLE budget (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 model_limit INTEGER NOT NULL CHECK(model_limit>0),
 model_reserved INTEGER NOT NULL DEFAULT 0 CHECK(model_reserved>=0 AND model_reserved<=model_limit),
 finalization_reserve INTEGER NOT NULL CHECK(finalization_reserve>=0 AND finalization_reserve<=model_limit),
 tool_limit INTEGER NOT NULL CHECK(tool_limit>0),
 tool_used INTEGER NOT NULL DEFAULT 0 CHECK(tool_used>=0 AND tool_used<=tool_limit)
);

CREATE TABLE stage_artifact (
 artifact_id TEXT PRIMARY KEY,
 stage TEXT NOT NULL CHECK(stage IN ('retrieve','select','assemble','answer')),
 artifact_revision INTEGER NOT NULL CHECK(artifact_revision>=1),
 evidence_revision INTEGER NOT NULL CHECK(evidence_revision>=0),
 dependency_hash TEXT NOT NULL CHECK(length(dependency_hash)=64),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 valid INTEGER NOT NULL CHECK(valid IN (0,1)),
 created_seq INTEGER NOT NULL REFERENCES event(seq),
 UNIQUE(stage,artifact_revision)
);
CREATE INDEX stage_current ON stage_artifact(stage,valid,artifact_revision);

CREATE TABLE publication (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 result_json TEXT NOT NULL CHECK(json_valid(result_json)),
 result_hash TEXT NOT NULL CHECK(length(result_hash)=64),
 destination_key TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PENDING','PUBLISHED')),
 created_seq INTEGER NOT NULL REFERENCES event(seq),
 published_at TEXT
);

CREATE TABLE navigation_handle (
 handle TEXT PRIMARY KEY, kind TEXT NOT NULL,
 identity_json TEXT NOT NULL CHECK(json_valid(identity_json)), binding_hash TEXT NOT NULL
);
CREATE INDEX navigation_handle_identity ON navigation_handle(kind,binding_hash,identity_json);
CREATE TABLE navigation_cursor (
 cursor TEXT PRIMARY KEY, operation_hash TEXT NOT NULL,
 position_json TEXT NOT NULL CHECK(json_valid(position_json)), binding_hash TEXT NOT NULL
);
CREATE TRIGGER handle_no_update BEFORE UPDATE ON navigation_handle BEGIN SELECT RAISE(ABORT,'immutable handle'); END;
CREATE TRIGGER handle_no_delete BEFORE DELETE ON navigation_handle BEGIN SELECT RAISE(ABORT,'immutable handle'); END;
CREATE TRIGGER cursor_no_update BEFORE UPDATE ON navigation_cursor BEGIN SELECT RAISE(ABORT,'immutable cursor'); END;
CREATE TRIGGER cursor_no_delete BEFORE DELETE ON navigation_cursor BEGIN SELECT RAISE(ABORT,'immutable cursor'); END;

-- The application still validates exact spans/hashes, current revisions, scope,
-- transitions, and dependency cycles. SQL alone does not validate semantics.

CREATE TRIGGER event_no_update BEFORE UPDATE ON event BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER event_no_delete BEFORE DELETE ON event BEGIN SELECT RAISE(ABORT,'immutable event'); END;

CREATE TRIGGER entity_version_no_update BEFORE UPDATE ON entity_version BEGIN SELECT RAISE(ABORT,'immutable entity_version'); END;
CREATE TRIGGER entity_version_no_delete BEFORE DELETE ON entity_version BEGIN SELECT RAISE(ABORT,'immutable entity_version'); END;

CREATE TRIGGER dependency_no_update BEFORE UPDATE ON dependency BEGIN SELECT RAISE(ABORT,'immutable dependency'); END;
CREATE TRIGGER dependency_no_delete BEFORE DELETE ON dependency BEGIN SELECT RAISE(ABORT,'immutable dependency'); END;

CREATE TRIGGER evidence_unit_no_update BEFORE UPDATE ON evidence_unit BEGIN SELECT RAISE(ABORT,'immutable evidence_unit'); END;
CREATE TRIGGER evidence_unit_no_delete BEFORE DELETE ON evidence_unit BEGIN SELECT RAISE(ABORT,'immutable evidence_unit'); END;

CREATE TRIGGER evidence_span_no_update BEFORE UPDATE ON evidence_span BEGIN SELECT RAISE(ABORT,'immutable evidence_span'); END;
CREATE TRIGGER evidence_span_no_delete BEFORE DELETE ON evidence_span BEGIN SELECT RAISE(ABORT,'immutable evidence_span'); END;

CREATE TRIGGER observation_no_update BEFORE UPDATE ON observation BEGIN SELECT RAISE(ABORT,'immutable observation'); END;
CREATE TRIGGER observation_no_delete BEFORE DELETE ON observation BEGIN SELECT RAISE(ABORT,'immutable observation'); END;

CREATE TRIGGER observation_evidence_no_update BEFORE UPDATE ON observation_evidence BEGIN SELECT RAISE(ABORT,'immutable observation_evidence'); END;
CREATE TRIGGER observation_evidence_no_delete BEFORE DELETE ON observation_evidence BEGIN SELECT RAISE(ABORT,'immutable observation_evidence'); END;

CREATE TRIGGER evidence_dependency_no_update BEFORE UPDATE ON evidence_dependency BEGIN SELECT RAISE(ABORT,'immutable evidence_dependency'); END;
CREATE TRIGGER evidence_dependency_no_delete BEFORE DELETE ON evidence_dependency BEGIN SELECT RAISE(ABORT,'immutable evidence_dependency'); END;

CREATE TRIGGER model_view_no_update BEFORE UPDATE ON model_view BEGIN SELECT RAISE(ABORT,'immutable model_view'); END;
CREATE TRIGGER model_view_no_delete BEFORE DELETE ON model_view BEGIN SELECT RAISE(ABORT,'immutable model_view'); END;

CREATE TRIGGER presentation_no_update BEFORE UPDATE ON presentation BEGIN SELECT RAISE(ABORT,'immutable presentation'); END;
CREATE TRIGGER presentation_no_delete BEFORE DELETE ON presentation BEGIN SELECT RAISE(ABORT,'immutable presentation'); END;

CREATE TRIGGER publication_content_immutable BEFORE UPDATE OF result_json,result_hash,destination_key ON publication
BEGIN SELECT RAISE(ABORT,'immutable publication content'); END;
CREATE TRIGGER run_binding_immutable BEFORE UPDATE OF run_id,query_id,binding_hash,binding_json,request_json ON run
BEGIN SELECT RAISE(ABORT,'immutable request binding'); END;

CREATE TABLE action_receipt (action_id TEXT PRIMARY KEY, args_hash TEXT NOT NULL, result_json TEXT NOT NULL CHECK(json_valid(result_json)));
CREATE TABLE candidate_route (candidate TEXT NOT NULL, route TEXT NOT NULL, PRIMARY KEY(candidate,route));
CREATE TABLE read_coverage (target_hash TEXT NOT NULL, evidence_id TEXT NOT NULL REFERENCES evidence_unit(evidence_id), PRIMARY KEY(target_hash,evidence_id));
CREATE TRIGGER action_no_update BEFORE UPDATE ON action_receipt BEGIN SELECT RAISE(ABORT,'immutable action'); END;
CREATE TRIGGER action_no_delete BEFORE DELETE ON action_receipt BEGIN SELECT RAISE(ABORT,'immutable action'); END;

CREATE TABLE action_context (
 action_id TEXT PRIMARY KEY, proposal_hash TEXT NOT NULL, proposed_json TEXT NOT NULL,
 actor TEXT NOT NULL CHECK(actor IN ('MODEL','SYSTEM_POLICY','REVIEWER')),
 parent_action_id TEXT, trigger_reference_id TEXT, policy_hash TEXT,
 input_view_id TEXT, status TEXT NOT NULL, result_json TEXT,
 created_seq INTEGER NOT NULL REFERENCES event(seq)
);
CREATE TABLE system_task (
 task_id TEXT PRIMARY KEY, parent_action_id TEXT NOT NULL, evidence_id TEXT,
 operation_json TEXT NOT NULL, depth INTEGER NOT NULL, status TEXT NOT NULL,
 result_json TEXT, created_seq INTEGER NOT NULL REFERENCES event(seq)
);
CREATE TABLE item_presentation (
 view_id TEXT NOT NULL REFERENCES model_view(view_id), kind TEXT NOT NULL,
 item_id TEXT NOT NULL, content_hash TEXT NOT NULL,
 PRIMARY KEY(view_id,kind,item_id)
);
CREATE TABLE auto_visit (extent_hash TEXT PRIMARY KEY, action_id TEXT NOT NULL);
CREATE TABLE evidence_origin (evidence_id TEXT PRIMARY KEY REFERENCES evidence_unit(evidence_id),
 action_id TEXT NOT NULL, automatic_depth INTEGER NOT NULL);
CREATE TABLE auto_budget (singleton INTEGER PRIMARY KEY CHECK(singleton=1), reads INTEGER NOT NULL, chars INTEGER NOT NULL);
INSERT INTO auto_budget VALUES(1,0,0);
CREATE TRIGGER item_presentation_no_update BEFORE UPDATE ON item_presentation BEGIN SELECT RAISE(ABORT,'immutable presentation'); END;
CREATE TRIGGER item_presentation_no_delete BEFORE DELETE ON item_presentation BEGIN SELECT RAISE(ABORT,'immutable presentation'); END;
CREATE TRIGGER action_purpose_immutable BEFORE UPDATE OF proposal_hash,proposed_json,actor,parent_action_id,trigger_reference_id,policy_hash,input_view_id ON action_context BEGIN SELECT RAISE(ABORT,'immutable purpose'); END;
CREATE TABLE relation_scan (anchor TEXT NOT NULL,family TEXT NOT NULL,status TEXT NOT NULL,
 next_cursor TEXT,action_id TEXT NOT NULL,PRIMARY KEY(anchor,family));

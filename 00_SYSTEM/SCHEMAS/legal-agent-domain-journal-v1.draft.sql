-- DESIGN DRAFT fragment for NEW native journals only.
-- Scratch validation order: journal-v5.sql, then this file. Never run on a live
-- or completed journal. Proposed DomainRepository VERSION=6 needs new-run
-- initialization, publication and recovery support before runtime use.
PRAGMA foreign_keys=ON;
PRAGMA user_version=6;

CREATE TABLE dq_binding(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 catalogue_id TEXT NOT NULL, ontology_version TEXT NOT NULL,
 catalogue_manifest_hash TEXT NOT NULL CHECK(length(catalogue_manifest_hash)=64),
 source_binding_hash TEXT NOT NULL CHECK(length(source_binding_hash)=64),
 method_policy_hash TEXT NOT NULL CHECK(length(method_policy_hash)=64),
 case_id TEXT NOT NULL, branch_id TEXT NOT NULL, question_id TEXT NOT NULL,
 case_revision INTEGER NOT NULL CHECK(case_revision>=0),
 created_seq INTEGER NOT NULL REFERENCES event(seq)
);
CREATE TABLE dq_offer(
 offer_id TEXT PRIMARY KEY,
 view_id TEXT REFERENCES model_view(view_id),
 actor TEXT NOT NULL CHECK(actor IN ('MODEL','SYSTEM')),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)),
 body_hash TEXT NOT NULL CHECK(length(body_hash)=64),
 created_seq INTEGER NOT NULL REFERENCES event(seq),
 CHECK((actor='MODEL' AND view_id IS NOT NULL) OR (actor='SYSTEM' AND view_id IS NULL))
);
CREATE TABLE dq_choice(
 choice_id TEXT PRIMARY KEY, offer_id TEXT NOT NULL REFERENCES dq_offer(offer_id),
 stage TEXT NOT NULL CHECK(stage IN ('INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE')),
 purpose_id TEXT NOT NULL,
 use_role TEXT NOT NULL CHECK(use_role IN ('DISCOVERY','NAVIGATION','APPLICATION','PRESENTATION')),
 method_id TEXT NOT NULL, path_template_id TEXT NOT NULL, path_instance_id TEXT NOT NULL,
 step_id TEXT NOT NULL,
 action_json TEXT NOT NULL CHECK(json_valid(action_json)),
 action_hash TEXT NOT NULL CHECK(length(action_hash)=64),
 reason TEXT NOT NULL CHECK(length(trim(reason))>0),
 created_seq INTEGER NOT NULL REFERENCES event(seq)
);
CREATE TABLE dq_execution(
 choice_id TEXT NOT NULL REFERENCES dq_choice(choice_id),
 attempt INTEGER NOT NULL CHECK(attempt>=1),
 observation_id TEXT REFERENCES observation(observation_id),
 status TEXT NOT NULL CHECK(status IN ('SUCCEEDED','FAILED','INTERRUPTED','UNKNOWN')),
 receipt_json TEXT NOT NULL CHECK(json_valid(receipt_json)),
 receipt_hash TEXT NOT NULL CHECK(length(receipt_hash)=64),
 created_seq INTEGER NOT NULL REFERENCES event(seq),
 PRIMARY KEY(choice_id,attempt),
 CHECK(status!='SUCCEEDED' OR observation_id IS NOT NULL)
);
CREATE TABLE dq_proof(
 kind TEXT NOT NULL, entity_id TEXT NOT NULL, version INTEGER NOT NULL,
 choice_id TEXT NOT NULL REFERENCES dq_choice(choice_id),
 disposition TEXT NOT NULL CHECK(disposition IN ('ADOPT','REJECT','DEFER')),
 proof_json TEXT NOT NULL CHECK(json_valid(proof_json)),
 proof_hash TEXT NOT NULL CHECK(length(proof_hash)=64),
 created_seq INTEGER NOT NULL REFERENCES event(seq),
 PRIMARY KEY(kind,entity_id,version),
 FOREIGN KEY(kind,entity_id,version) REFERENCES entity_version(kind,entity_id,version)
);
CREATE TABLE dq_proof_fact(
 kind TEXT NOT NULL, entity_id TEXT NOT NULL, version INTEGER NOT NULL,
 fact_kind TEXT NOT NULL DEFAULT 'fact' CHECK(fact_kind='fact'),
 fact_id TEXT NOT NULL, fact_version INTEGER NOT NULL,
 PRIMARY KEY(kind,entity_id,version,fact_id,fact_version),
 FOREIGN KEY(kind,entity_id,version) REFERENCES dq_proof(kind,entity_id,version),
 FOREIGN KEY(fact_kind,fact_id,fact_version) REFERENCES entity_version(kind,entity_id,version)
);
CREATE INDEX dq_fact_dependents ON dq_proof_fact(fact_id,fact_version);
CREATE TABLE dq_guard_dependency(
 kind TEXT NOT NULL, entity_id TEXT NOT NULL, version INTEGER NOT NULL,
 guard_key TEXT NOT NULL,
 inspected_value_hash TEXT NOT NULL CHECK(length(inspected_value_hash)=64),
 PRIMARY KEY(kind,entity_id,version,guard_key),
 FOREIGN KEY(kind,entity_id,version) REFERENCES dq_proof(kind,entity_id,version)
);
CREATE INDEX dq_guard_dependents ON dq_guard_dependency(guard_key);
CREATE TABLE dq_answer_anchor(
 answer_artifact_id TEXT NOT NULL REFERENCES stage_artifact(artifact_id),
 paragraph_id TEXT NOT NULL,
 kind TEXT NOT NULL, entity_id TEXT NOT NULL, version INTEGER NOT NULL,
 PRIMARY KEY(answer_artifact_id,paragraph_id,kind,entity_id,version),
 FOREIGN KEY(kind,entity_id,version) REFERENCES dq_proof(kind,entity_id,version)
);

CREATE TRIGGER dq_binding_no_update BEFORE UPDATE ON dq_binding BEGIN SELECT RAISE(ABORT,'immutable domain binding'); END;
CREATE TRIGGER dq_binding_no_delete BEFORE DELETE ON dq_binding BEGIN SELECT RAISE(ABORT,'immutable domain binding'); END;
CREATE TRIGGER dq_offer_no_update BEFORE UPDATE ON dq_offer BEGIN SELECT RAISE(ABORT,'immutable domain offer'); END;
CREATE TRIGGER dq_offer_no_delete BEFORE DELETE ON dq_offer BEGIN SELECT RAISE(ABORT,'immutable domain offer'); END;
CREATE TRIGGER dq_choice_no_update BEFORE UPDATE ON dq_choice BEGIN SELECT RAISE(ABORT,'immutable domain choice'); END;
CREATE TRIGGER dq_choice_no_delete BEFORE DELETE ON dq_choice BEGIN SELECT RAISE(ABORT,'immutable domain choice'); END;
CREATE TRIGGER dq_execution_no_update BEFORE UPDATE ON dq_execution BEGIN SELECT RAISE(ABORT,'immutable domain execution'); END;
CREATE TRIGGER dq_execution_no_delete BEFORE DELETE ON dq_execution BEGIN SELECT RAISE(ABORT,'immutable domain execution'); END;
CREATE TRIGGER dq_proof_no_update BEFORE UPDATE ON dq_proof BEGIN SELECT RAISE(ABORT,'immutable domain proof'); END;
CREATE TRIGGER dq_proof_no_delete BEFORE DELETE ON dq_proof BEGIN SELECT RAISE(ABORT,'immutable domain proof'); END;
CREATE TRIGGER dq_fact_no_update BEFORE UPDATE ON dq_proof_fact BEGIN SELECT RAISE(ABORT,'immutable domain fact dependency'); END;
CREATE TRIGGER dq_fact_no_delete BEFORE DELETE ON dq_proof_fact BEGIN SELECT RAISE(ABORT,'immutable domain fact dependency'); END;
CREATE TRIGGER dq_guard_no_update BEFORE UPDATE ON dq_guard_dependency BEGIN SELECT RAISE(ABORT,'immutable domain guard'); END;
CREATE TRIGGER dq_guard_no_delete BEFORE DELETE ON dq_guard_dependency BEGIN SELECT RAISE(ABORT,'immutable domain guard'); END;
CREATE TRIGGER dq_anchor_no_update BEFORE UPDATE ON dq_answer_anchor BEGIN SELECT RAISE(ABORT,'immutable domain anchor'); END;
CREATE TRIGGER dq_anchor_no_delete BEFORE DELETE ON dq_answer_anchor BEGIN SELECT RAISE(ABORT,'immutable domain anchor'); END;

-- Proof payload source spans must resolve to existing evidence_unit/span and
-- successful presentation receipts; membership/semantics require host checks.
-- Parent edges remain in native dependency; sidecar facts must also have native
-- dependency edges. Keep heads/validity in entity_head, not a second proof head.
-- Cross-run refs stay in case/route indexes; never use foreign-run E aliases here.

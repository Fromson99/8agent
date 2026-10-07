-- DESIGN DRAFT. A new, immutable catalogue package; not a live DB migration.
-- Consume after validating the entire source/policy/review binding in the host.
-- No automatic conversion of lexical observations into legal interpretation.
PRAGMA foreign_keys=ON;

CREATE TABLE dc_schema(
 version TEXT PRIMARY KEY CHECK(version='legal-agent-domain-catalogue-v1-draft')
);
CREATE TABLE dc_binding(
 catalogue_id TEXT PRIMARY KEY, ontology_version TEXT NOT NULL,
 source_generation_id TEXT NOT NULL,
 source_manifest_hash TEXT NOT NULL CHECK(length(source_manifest_hash)=64),
 navigation_manifest_hash TEXT NOT NULL CHECK(length(navigation_manifest_hash)=64),
 glossary_binding_hash TEXT NOT NULL CHECK(length(glossary_binding_hash)=64),
 method_policy_hash TEXT NOT NULL CHECK(length(method_policy_hash)=64)
);
CREATE TABLE dc_object(
 catalogue_id TEXT NOT NULL REFERENCES dc_binding(catalogue_id), id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('TERM','SCOPED_DEFINITION','SOURCE_LOCATION','INTERPRETIVE_CONCEPT')),
 scope_document_id TEXT,
 approval TEXT NOT NULL CHECK(approval IN ('NAVIGATION_REVIEWED','DOMAIN_REVIEWED')),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 origin_refs_json TEXT NOT NULL CHECK(json_valid(origin_refs_json)),
 PRIMARY KEY(catalogue_id,id)
);
CREATE TABLE dc_relation(
 catalogue_id TEXT NOT NULL, id TEXT NOT NULL,
 relation_type TEXT NOT NULL CHECK(relation_type IN
  ('DEFINITION_OF','EXPLICIT_REFERENCE_TO','OCCURRENCE_OF','STRUCTURE_CHILD_OF',
   'SUBTYPE_OF','SCOPE_OF','EXCEPTION_TO','CONDITION_FOR')),
 source_object_id TEXT NOT NULL, target_object_id TEXT NOT NULL,
 approval TEXT NOT NULL CHECK(approval IN ('NAVIGATION_REVIEWED','DOMAIN_REVIEWED')),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 origin_refs_json TEXT NOT NULL CHECK(json_valid(origin_refs_json)),
 PRIMARY KEY(catalogue_id,id),
 FOREIGN KEY(catalogue_id,source_object_id) REFERENCES dc_object(catalogue_id,id),
 FOREIGN KEY(catalogue_id,target_object_id) REFERENCES dc_object(catalogue_id,id),
 CHECK(source_object_id!=target_object_id),
 CHECK(relation_type NOT IN ('SUBTYPE_OF','SCOPE_OF','EXCEPTION_TO','CONDITION_FOR')
       OR approval='DOMAIN_REVIEWED')
);
CREATE INDEX dc_relation_source ON dc_relation(catalogue_id,source_object_id,relation_type);
CREATE INDEX dc_relation_target ON dc_relation(catalogue_id,target_object_id,relation_type);
CREATE TABLE dc_method(
 catalogue_id TEXT NOT NULL REFERENCES dc_binding(catalogue_id), id TEXT NOT NULL,
 purpose_object_id TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version>=1),
 allowed_stages_json TEXT NOT NULL CHECK(json_valid(allowed_stages_json)),
 steps_json TEXT NOT NULL CHECK(json_valid(steps_json)),
 completion_checks_json TEXT NOT NULL CHECK(json_valid(completion_checks_json)),
 review_receipt_ref TEXT NOT NULL,
 review_receipt_hash TEXT NOT NULL CHECK(length(review_receipt_hash)=64),
 PRIMARY KEY(catalogue_id,id),
 FOREIGN KEY(catalogue_id,purpose_object_id) REFERENCES dc_object(catalogue_id,id)
);
CREATE TABLE dc_path_template(
 catalogue_id TEXT NOT NULL, id TEXT NOT NULL, method_id TEXT NOT NULL,
 slot_kinds_json TEXT NOT NULL CHECK(json_valid(slot_kinds_json)),
 scope_check_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 review_receipt_ref TEXT NOT NULL,
 review_receipt_hash TEXT NOT NULL CHECK(length(review_receipt_hash)=64),
 PRIMARY KEY(catalogue_id,id),
 FOREIGN KEY(catalogue_id,method_id) REFERENCES dc_method(catalogue_id,id)
);

-- Published package immutability. Draft authoring/admin workflows are separate.
CREATE TRIGGER dc_schema_no_update BEFORE UPDATE ON dc_schema BEGIN SELECT RAISE(ABORT,'immutable dc_schema'); END;
CREATE TRIGGER dc_schema_no_delete BEFORE DELETE ON dc_schema BEGIN SELECT RAISE(ABORT,'immutable dc_schema'); END;
CREATE TRIGGER dc_binding_no_update BEFORE UPDATE ON dc_binding BEGIN SELECT RAISE(ABORT,'immutable catalogue binding'); END;
CREATE TRIGGER dc_binding_no_delete BEFORE DELETE ON dc_binding BEGIN SELECT RAISE(ABORT,'immutable catalogue binding'); END;
CREATE TRIGGER dc_object_no_update BEFORE UPDATE ON dc_object BEGIN SELECT RAISE(ABORT,'immutable domain object'); END;
CREATE TRIGGER dc_object_no_delete BEFORE DELETE ON dc_object BEGIN SELECT RAISE(ABORT,'immutable domain object'); END;
CREATE TRIGGER dc_relation_no_update BEFORE UPDATE ON dc_relation BEGIN SELECT RAISE(ABORT,'immutable domain relation'); END;
CREATE TRIGGER dc_relation_no_delete BEFORE DELETE ON dc_relation BEGIN SELECT RAISE(ABORT,'immutable domain relation'); END;
CREATE TRIGGER dc_method_no_update BEFORE UPDATE ON dc_method BEGIN SELECT RAISE(ABORT,'immutable domain method'); END;
CREATE TRIGGER dc_method_no_delete BEFORE DELETE ON dc_method BEGIN SELECT RAISE(ABORT,'immutable domain method'); END;
CREATE TRIGGER dc_path_no_update BEFORE UPDATE ON dc_path_template BEGIN SELECT RAISE(ABORT,'immutable domain path'); END;
CREATE TRIGGER dc_path_no_delete BEFORE DELETE ON dc_path_template BEGIN SELECT RAISE(ABORT,'immutable domain path'); END;

-- SQL does not validate origin receipts, SHA-256 contents, reviewed meanings,
-- source scopes, operation registry, allowed step transitions or semantic truth.
-- Open the completed package read-only and pin its external manifest hash.

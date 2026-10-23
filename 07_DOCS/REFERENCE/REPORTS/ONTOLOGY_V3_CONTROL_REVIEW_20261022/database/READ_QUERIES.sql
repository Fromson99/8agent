-- READ-ONLY DESIGN SKELETONS, not wired to an API and not executed.
-- All binds come from validated service code. Never accept SQL from an LLM.
-- Authorize principal + documents + every reference before returning results.
-- Enforce page_size, shared deadline/call budget and exact release/hash pins.
-- The SQL filters below are necessary coarse filters, not a complete ACL system.
-- Return candidate rows; current facts/applicability and semantic support are
-- assessed by the existing agent. Unknown dates do not establish applicability.

-- Q1: One typed entry key within the request-pinned knowledge/source release.
SELECT e.OBJECT_ID, e.REVISION, o.OBJECT_KIND, v.PAYLOAD_HASH,
       v.VALIDITY_KIND, v.VALID_FROM, v.VALID_TO,
       c.CONTROL_REVISION, e.KEY_TEXT
FROM LK_ENTRY e
JOIN LK_RELEASE r ON r.RELEASE_ID=e.RELEASE_ID
                 AND r.RELEASE_REVISION=e.RELEASE_REVISION
JOIN LK_OBJECT o ON o.OBJECT_ID=e.OBJECT_ID
JOIN LK_KREV v ON v.OBJECT_ID=e.OBJECT_ID AND v.REVISION=e.REVISION
JOIN LK_CONTROL c ON c.OBJECT_ID=e.OBJECT_ID AND c.REVISION=e.REVISION
WHERE r.TENANT_ID=:tenant_id AND r.SCOPE_ID=:scope_id
  AND o.TENANT_ID=:tenant_id AND o.SCOPE_ID=:scope_id
  AND r.RELEASE_ID=:release_id AND r.RELEASE_REVISION=:release_revision
  AND r.SOURCE_QUERY_RELEASE=:source_query_release
  AND r.SOURCE_BINDING_HASH=:source_binding_hash
  AND e.KEY_KIND=:key_kind AND e.KEY_HASH=:key_hash
  AND c.USE_STATE='ENABLED'
  AND (:as_of IS NULL OR v.VALIDITY_KIND<>'KNOWN'
       OR ((v.VALID_FROM IS NULL OR v.VALID_FROM<=:as_of)
       AND (v.VALID_TO IS NULL OR v.VALID_TO>:as_of)))
  AND (:after_object_id IS NULL OR e.OBJECT_ID>:after_object_id)
ORDER BY e.OBJECT_ID
FETCH FIRST :page_size ROWS ONLY;
-- Check normalized KEY_TEXT against the input key after hash lookup.
-- Validate exact selected review target/scope and current source access.
-- Unknown validity/facts can be shown as an unresolved candidate, not applied.

-- Q2: Steps for a selected route. Validate this route's content hash too.
SELECT s.STEP_NO, s.NEED_ROLE, s.ACTION_KIND, f.REF_ID, f.REF_KIND,
       f.OWNER_PORT, f.CONTENT_HASH, f.LOCATOR_JSON
FROM LK_ROUTE_STEP s
JOIN LK_OBJECT o ON o.OBJECT_ID=s.OBJECT_ID
JOIN LK_CONTROL c ON c.OBJECT_ID=s.OBJECT_ID AND c.REVISION=s.REVISION
JOIN LK_RELEASE_ITEM m ON m.OBJECT_ID=s.OBJECT_ID AND m.REVISION=s.REVISION
JOIN LK_RELEASE r ON r.RELEASE_ID=m.RELEASE_ID
                 AND r.RELEASE_REVISION=m.RELEASE_REVISION
JOIN LK_REF f ON f.REF_ID=s.REF_ID
WHERE o.TENANT_ID=:tenant_id AND o.SCOPE_ID=:scope_id
  AND r.TENANT_ID=:tenant_id AND r.SCOPE_ID=:scope_id
  AND f.TENANT_ID=:tenant_id
  AND o.OBJECT_KIND='EVIDENCE_ROUTE' AND c.USE_STATE='ENABLED'
  AND m.RELEASE_ID=:release_id AND m.RELEASE_REVISION=:release_revision
  AND r.SOURCE_QUERY_RELEASE=:source_query_release
  AND r.SOURCE_BINDING_HASH=:source_binding_hash
  AND s.OBJECT_ID=:route_id AND s.REVISION=:route_revision
  AND s.NEED_ROLE=:need_role AND s.STEP_NO>:after_step
ORDER BY s.STEP_NO
FETCH FIRST :page_size ROWS ONLY;
-- Current conditions, review scope and dates are revalidated by M07/M08.
-- Existing source port reads only authorized spans; this is not source absence proof.

-- Q3: One semantic hop. Predicate is selected from the versioned allowlist.
SELECT g.OBJECT_ID, g.REVISION, g.PREDICATE,
       g.SUBJECT_REF_ID, g.TARGET_REF_ID, g.RELATION_SCHEMA_HASH
FROM LK_EDGE g
JOIN LK_OBJECT o ON o.OBJECT_ID=g.OBJECT_ID
JOIN LK_CONTROL c ON c.OBJECT_ID=g.OBJECT_ID AND c.REVISION=g.REVISION
JOIN LK_RELEASE_ITEM m ON m.OBJECT_ID=g.OBJECT_ID AND m.REVISION=g.REVISION
JOIN LK_RELEASE r ON r.RELEASE_ID=m.RELEASE_ID
                 AND r.RELEASE_REVISION=m.RELEASE_REVISION
JOIN LK_REF s ON s.REF_ID=g.SUBJECT_REF_ID
JOIN LK_REF t ON t.REF_ID=g.TARGET_REF_ID
WHERE o.TENANT_ID=:tenant_id AND o.SCOPE_ID=:scope_id
  AND r.TENANT_ID=:tenant_id AND r.SCOPE_ID=:scope_id
  AND s.TENANT_ID=:tenant_id AND t.TENANT_ID=:tenant_id
  AND o.OBJECT_KIND='RELATION' AND c.USE_STATE='ENABLED'
  AND m.RELEASE_ID=:release_id AND m.RELEASE_REVISION=:release_revision
  AND r.SOURCE_QUERY_RELEASE=:source_query_release
  AND r.SOURCE_BINDING_HASH=:source_binding_hash
  AND g.SUBJECT_REF_ID=:subject_ref_id AND g.PREDICATE=:predicate
  AND (:after_object_id IS NULL OR g.OBJECT_ID>:after_object_id)
ORDER BY g.OBJECT_ID
FETCH FIRST :page_size ROWS ONLY;
-- Reverse hop uses TARGET_REF_ID and LK_EDGE_REVERSE_IX in a separate maintained query.
-- Each hop retains object/revision + conditions/evidence. No blanket transitivity.

-- Q4: Direct reverse dependencies, including historical/withdrawn consumers.
-- Re-authorize each consumer and target. Do not expose unauthorized IDs/counts.
SELECT d.DEPENDENCY_ID, d.DEPENDENT_KIND, d.OBJECT_ID, d.REVISION,
       d.RUN_ID, d.DECISION_ID, d.CLAIM_ID, d.DEPENDENCY_ROLE, d.USE_ID
FROM LK_DEPENDENCY d
JOIN LK_REF f ON f.REF_ID=d.TARGET_REF_ID
LEFT JOIN LK_OBJECT o ON o.OBJECT_ID=d.OBJECT_ID
LEFT JOIN LK_RUN r ON r.RUN_ID=d.RUN_ID
WHERE d.TARGET_REF_ID=:changed_ref_id AND f.TENANT_ID=:tenant_id
  AND ((d.DEPENDENT_KIND='KNOWLEDGE'
        AND o.TENANT_ID=:tenant_id AND o.SCOPE_ID=:scope_id)
       OR (d.DEPENDENT_KIND='CLAIM'
        AND r.TENANT_ID=:tenant_id AND r.SCOPE_ID=:scope_id))
  AND (:after_dependency_id IS NULL OR d.DEPENDENCY_ID>:after_dependency_id)
ORDER BY d.DEPENDENCY_ID
FETCH FIRST :page_size ROWS ONLY;
-- For each authorized consumer, resolve its exact LK_REF and continue if budget permits.
-- Visited keys prevent cycles. Record depth/budget/ACL/index coverage in ImpactReport.
-- Do not filter by ENABLED here: past use of a withdrawn object is relevant.

-- Q5: Which recorded events used a knowledge version?
SELECT u.USE_ID, u.RUN_ID, u.DECISION_ID, u.CLAIM_ID, u.EVENT_KIND,
       u.ORIGIN_KIND, u.SUPPORT_STATE, u.JOURNAL_SEQ, u.EVENT_HASH
FROM LK_USE u
JOIN LK_RUN r ON r.RUN_ID=u.RUN_ID
JOIN LK_OBJECT o ON o.OBJECT_ID=u.OBJECT_ID
WHERE r.TENANT_ID=:tenant_id AND r.SCOPE_ID=:scope_id
  AND o.TENANT_ID=:tenant_id
  AND u.OBJECT_ID=:object_id AND u.REVISION=:revision
  AND u.EVENT_KIND IN ('APPLIED','CALCULATED')
  AND (:after_use_id IS NULL OR u.USE_ID>:after_use_id)
ORDER BY u.USE_ID
FETCH FIRST :page_size ROWS ONLY;
-- OFFERED/SELECTED/POSTHOC_REVIEW are not counted as applied.
-- Use the original journal publication receipt to distinguish partial, failed
-- and committed answers. LK_USE alone does not certify a completed answer.

-- Q6: Resolve explicit old/new document-family references for change analysis.
SELECT REF_ID, EXTERNAL_ID, EXTERNAL_REVISION, CONTENT_HASH, LOCATOR_JSON
FROM LK_REF
WHERE TENANT_ID=:tenant_id AND REF_KIND=:ref_kind
  AND FAMILY_KEY_HASH=:family_key_hash
  AND (:after_ref_id IS NULL OR REF_ID>:after_ref_id)
ORDER BY REF_ID
FETCH FIRST :page_size ROWS ONLY;
-- Family matching is an explicit owner-port lineage mapping, never title equality.
-- An unknown lineage means incomplete change coverage, not no affected knowledge.

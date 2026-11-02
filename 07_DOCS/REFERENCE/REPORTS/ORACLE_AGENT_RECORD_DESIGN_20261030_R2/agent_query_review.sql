-- DESIGN ONLY: SELECT templates, never executed against Oracle.
-- Binds are maintained adapter inputs after authentication/authorization.
-- Replace __AGENT_OWNER__ only in the reviewed deployment artifact.
-- Hashes identify objects; they do not authorize reads.
-- :page_limit is a validated positive integer within a server-side limit.
-- See QUERY_CONTRACTS.md for cursor, consistency and recovery semantics.

-- Q01: Session run list, newest first; metadata only.
SELECT * FROM (
  SELECT RUN_KEY_HASH_VAL, REQ_KEY_HASH_VAL, PRNT_RUN_KEY_HASH_VAL,
         ST_CD, STRT_DTTM, CHG_DTTM, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_RUN_A
  WHERE SCOPE_HASH_VAL = :scope AND SESS_KEY_HASH_VAL = :session_key
    AND (STRT_DTTM < :before_time OR
         (STRT_DTTM = :before_time AND RUN_KEY_HASH_VAL < :before_run))
  ORDER BY STRT_DTTM DESC, RUN_KEY_HASH_VAL DESC
) WHERE ROWNUM <= :page_limit;

-- Q02: Existing runs of one request. Not an idempotent ownership claim.
SELECT * FROM (
  SELECT RUN_KEY_HASH_VAL, ST_CD, STRT_DTTM, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_RUN_A
  WHERE SCOPE_HASH_VAL = :scope AND REQ_KEY_HASH_VAL = :request_key
    AND RUN_KEY_HASH_VAL > :after_run
  ORDER BY RUN_KEY_HASH_VAL
) WHERE ROWNUM <= :page_limit;

-- Q03: Recovery candidates in one status; never a dispatch authorization.
SELECT * FROM (
  SELECT RUN_KEY_HASH_VAL, ST_CD, CHG_DTTM, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_RUN_A
  WHERE SCOPE_HASH_VAL = :scope AND ST_CD = :status
    AND CHG_DTTM <= :scan_cutoff
    AND (CHG_DTTM > :after_time OR
         (CHG_DTTM = :after_time AND RUN_KEY_HASH_VAL > :after_run))
  ORDER BY CHG_DTTM, RUN_KEY_HASH_VAL
) WHERE ROWNUM <= :page_limit;

-- Q04: All original event kinds in owner-local append order.
SELECT * FROM (
  SELECT REC_KEY_HASH_VAL, ORD_SEQ_NO, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_REC_A
  WHERE SCOPE_HASH_VAL = :scope AND OWNER_KEY_HASH_VAL = :owner_key
    AND REC_KIND_CD = 'EVENT' AND REC_REV_NO = 1
    AND ORD_SEQ_NO > :after_seq AND ORD_SEQ_NO <= :event_watermark
  ORDER BY ORD_SEQ_NO, REC_KEY_HASH_VAL
) WHERE ROWNUM <= :page_limit;

-- Q05: Preserved revisions of a judgment/entity, excluding projection 0.
SELECT * FROM (
  SELECT REC_REV_NO, ORD_SEQ_NO, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_REC_A
  WHERE SCOPE_HASH_VAL = :scope AND OWNER_KEY_HASH_VAL = :owner_key
    AND REC_KIND_CD = :registered_kind AND REC_KEY_HASH_VAL = :record_key
    AND REC_REV_NO >= 1 AND REC_REV_NO > :after_revision
  ORDER BY REC_REV_NO
) WHERE ROWNUM <= :page_limit;

-- Q06: Calls in a known status inside one run/owner; metadata only.
SELECT * FROM (
  SELECT REC_KEY_HASH_VAL, ORD_SEQ_NO, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_REC_A
  WHERE SCOPE_HASH_VAL = :scope AND OWNER_KEY_HASH_VAL = :owner_key
    AND REC_KIND_CD = 'CALL' AND REC_REV_NO = 0
    AND LOOKUP_HASH_VAL = :call_status_key
    AND (ORD_SEQ_NO > :after_seq OR
         (ORD_SEQ_NO = :after_seq AND REC_KEY_HASH_VAL > :after_record))
  ORDER BY ORD_SEQ_NO, REC_KEY_HASH_VAL
) WHERE ROWNUM <= :page_limit;

-- Q07: Forward/reverse reference projection for an exact endpoint version.
-- :direction_kind is restricted by maintained code to REF_OUT or REF_IN.
SELECT * FROM (
  SELECT REC_KEY_HASH_VAL, ORD_SEQ_NO, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_REC_A
  WHERE SCOPE_HASH_VAL = :scope AND OWNER_KEY_HASH_VAL = :graph_owner_key
    AND REC_KIND_CD = :direction_kind AND REC_REV_NO = 0
    AND LOOKUP_HASH_VAL = :endpoint_key
    AND (ORD_SEQ_NO > :after_seq OR
         (ORD_SEQ_NO = :after_seq AND REC_KEY_HASH_VAL > :after_record))
  ORDER BY ORD_SEQ_NO, REC_KEY_HASH_VAL
) WHERE ROWNUM <= :page_limit;

-- Q08: Current exact record. Head/revision check is still required by caller.
SELECT REC_REV_NO, ORD_SEQ_NO, LOOKUP_HASH_VAL, BODY_HASH_VAL
FROM __AGENT_OWNER__.LGL_AGT_REC_A
WHERE SCOPE_HASH_VAL = :scope AND OWNER_KEY_HASH_VAL = :owner_key
  AND REC_KIND_CD = :registered_kind AND REC_KEY_HASH_VAL = :record_key
  AND REC_REV_NO = 0;

-- Q09: Cross-owner lookup projection, e.g. a registered term lookup.
-- Every returned owner must pass current authorization before body loading.
SELECT * FROM (
  SELECT OWNER_KEY_HASH_VAL, REC_KEY_HASH_VAL, BODY_HASH_VAL
  FROM __AGENT_OWNER__.LGL_AGT_REC_A
  WHERE SCOPE_HASH_VAL = :scope AND REC_KIND_CD = :registered_index_kind
    AND REC_REV_NO = 0 AND LOOKUP_HASH_VAL = :lookup_key
    AND (REC_KEY_HASH_VAL > :after_record OR
         (REC_KEY_HASH_VAL = :after_record AND OWNER_KEY_HASH_VAL > :after_owner))
  ORDER BY REC_KEY_HASH_VAL, OWNER_KEY_HASH_VAL
) WHERE ROWNUM <= :page_limit;

-- Q10: Body completion manifest, only after an authorized record lookup.
SELECT PART_JSON_CN
FROM __AGENT_OWNER__.LGL_AGT_BODY_A
WHERE SCOPE_HASH_VAL = :scope AND BODY_HASH_VAL = :body_hash
  AND PART_SEQ_NO = 0;

-- Q11: Data chunks in bounded pages; validate count, codec and all hashes.
SELECT * FROM (
  SELECT PART_SEQ_NO, PART_JSON_CN
  FROM __AGENT_OWNER__.LGL_AGT_BODY_A
  WHERE SCOPE_HASH_VAL = :scope AND BODY_HASH_VAL = :body_hash
    AND PART_SEQ_NO >= 1 AND PART_SEQ_NO > :after_part
    AND PART_SEQ_NO <= :manifest_part_count
  ORDER BY PART_SEQ_NO
) WHERE ROWNUM <= :page_limit;

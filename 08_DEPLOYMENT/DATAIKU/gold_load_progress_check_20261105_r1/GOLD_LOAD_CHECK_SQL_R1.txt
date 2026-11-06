-- Dataiku Oracle SQL notebook / connection AIDP. SELECT only.
-- Run each numbered statement separately. Default owner SIDDG is from the photo.
-- If the running PARAMS uses another owner/table, use that actual value instead.
-- Photo: run 20261105-092931-702353cf, current-file rows 6981746.
-- This is a per-file counter, NOT the entire SRCH_ROW table count.

-- 0. Confirm the connection and visible table owner.
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS LOGIN_USER,
       SYS_CONTEXT('USERENV', 'DB_UNIQUE_NAME') AS DB_NAME,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS SERVICE_NAME,
       SYSTIMESTAMP AS CHECKED_AT
FROM DUAL;

SELECT OWNER, TABLE_NAME
FROM ALL_TABLES
WHERE TABLE_NAME = 'IDD_B003_LGL_SRCH_ROW'
ORDER BY OWNER;

-- 1. Immediate check: exact committed row counts for EACH release.
-- Repeat after 2-5 minutes; compare the SAME release ID.
-- An increase shows committed rows were added during that interval.
-- A count > 6981746 alone does NOT prove progress after the photo:
-- earlier input files and other releases must not be confused with that baseline.
SELECT SYSTIMESTAMP AS CHECKED_AT,
       RFRN_POST_HASH_VALU AS QUERY_RELEASE_ID,
       COUNT(*) AS COMMITTED_SEARCH_ROWS
FROM SIDDG.IDD_B003_LGL_SRCH_ROW
GROUP BY RFRN_POST_HASH_VALU
ORDER BY COMMITTED_SEARCH_ROWS DESC, QUERY_RELEASE_ID;

-- 2. Exact remaining amount for the CURRENT release.
-- Preferred: use the already-filled SQL printed by GOLD_LOAD_PLAN_READONLY_R1.txt.
-- Manual alternative: replace the hash below with the current query_release_id.
-- Fill EXPECTED_ROWS with sum(prepared.json.query.tables[*].rows).
-- PHOTO_TOTAL_ROWS = all earlier completed input files + 6981746, at photo time.
-- Leave unknown numbers NULL. Never substitute 6981746 as a whole-job baseline.
-- PREVIOUS_CHECK_ROWS is the committed count from the previous SQL check.
WITH P AS (
    SELECT 'PASTE_CURRENT_64_CHAR_QUERY_RELEASE_ID' AS QUERY_RELEASE_ID,
           CAST(NULL AS NUMBER) AS EXPECTED_ROWS,
           CAST(NULL AS NUMBER) AS PHOTO_TOTAL_ROWS,
           CAST(NULL AS NUMBER) AS PREVIOUS_CHECK_ROWS
    FROM DUAL
), C AS (
    SELECT COUNT(*) AS N
    FROM SIDDG.IDD_B003_LGL_SRCH_ROW R
    CROSS JOIN P
    WHERE R.RFRN_POST_HASH_VALU = P.QUERY_RELEASE_ID
)
SELECT SYSTIMESTAMP AS CHECKED_AT,
       P.QUERY_RELEASE_ID,
       C.N AS COMMITTED_SEARCH_ROWS,
       P.EXPECTED_ROWS AS PLANNED_SEARCH_ROWS,
       P.EXPECTED_ROWS - C.N AS REMAINING_SEARCH_ROWS,
       ROUND(100 * C.N / NULLIF(P.EXPECTED_ROWS, 0), 2) AS SEARCH_PERCENT,
       P.PHOTO_TOTAL_ROWS,
       C.N - P.PHOTO_TOTAL_ROWS AS ADDED_AFTER_PHOTO,
       C.N - P.PREVIOUS_CHECK_ROWS AS ADDED_SINCE_LAST_CHECK,
       CASE
           WHEN NOT REGEXP_LIKE(P.QUERY_RELEASE_ID, '^[0-9a-f]{64}$') THEN 'FILL_CURRENT_RELEASE_ID'
           WHEN P.EXPECTED_ROWS IS NULL THEN 'TARGET_NOT_SUPPLIED'
           WHEN C.N > P.EXPECTED_ROWS THEN 'ROW_COUNT_EXCEEDS_PLAN'
           WHEN C.N = P.EXPECTED_ROWS THEN 'SEARCH_ROWS_MATCH_PLAN'
           ELSE 'SEARCH_ROWS_REMAIN'
       END AS SEARCH_STATUS
FROM P CROSS JOIN C;

-- SEARCH_ROWS_MATCH_PLAN is a row-count check, not full job success.
-- Publication, embedding/vector loading and final report still follow search.
-- No growth for one interval does not by itself prove the loader is stopped.
-- Separate sessions see committed rows as of each SELECT's snapshot.

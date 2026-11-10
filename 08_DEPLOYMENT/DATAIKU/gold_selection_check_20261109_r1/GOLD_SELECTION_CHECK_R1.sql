-- Prod Gold release manifest check (READ ONLY, SELECT only). Run each query separately.
-- Owner SIDDG as in the SRCH_CHNL query of 2026-11-09.

-- [1] Does the published manifest have the latest-version selection mark?
SELECT c.RFRN_CHNL_NAME,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.search_selection.schema_version') AS SEL_VER,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.selection_proof.native_latest_verified') AS PROOF,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.dataset_version') AS DATASET_VERSION,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.source_manifest.generation_id') AS GEN_ID,
       DBMS_LOB.GETLENGTH(p.RFRN_POST_IFMN_CTNT) AS LEN,
       DBMS_LOB.SUBSTR(p.RFRN_POST_IFMN_CTNT, 300, 1) AS HEAD
FROM SIDDG.IDD_B003_LGL_SRCH_CHNL c
JOIN SIDDG.IDD_B003_LGL_SRCH_POST p ON p.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU;

-- [2] Search rows tied to this release (size of any re-publish work)
SELECT COUNT(*) AS SRCH_ROWS
FROM SIDDG.IDD_B003_LGL_SRCH_ROW
WHERE RFRN_POST_HASH_VALU = (SELECT RFRN_POST_HASH_VALU FROM SIDDG.IDD_B003_LGL_SRCH_CHNL);

-- [3] Number of documents loaded
SELECT COUNT(*) AS DOCS FROM SIDDG.IDD_B003_LGL_DOC_VER;

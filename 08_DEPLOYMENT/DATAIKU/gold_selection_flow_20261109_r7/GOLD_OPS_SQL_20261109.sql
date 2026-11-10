-- =====================================================================
-- 운영 Gold 판본 선택 보완 관련 SQL 모음 (2026-11-09)
-- Gold owner SIDDG / 채널 g19_252f50906fa00e444b543cec
-- 각 문장을 Dataiku SQL 노트북에서 따로 실행한다. [읽기] = SELECT만, [DBA] = DBA 실행, [참고] = 레시피가 실행하는 문장
-- =====================================================================


-- ---------------------------------------------------------------------
-- A. 지금 상태: 끝났나, 진행 중인가 [읽기]
--    SEL_VER=filename-search-selection-v2 · CHAN_NO=2 · ROWS_ON_CHANNEL=60971724  → 완료(코드서빙 재기동)
--    SEL_VER 비어 있음 · CHAN_NO=1 → 진행 중/중단. ROWS_ON_CHANNEL = 아직 안 옮긴 행 수
-- ---------------------------------------------------------------------
SELECT c.RFRN_CHNL_NAME, c.CHAN_NO,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.search_selection.schema_version') AS SEL_VER,
       (SELECT COUNT(*) FROM SIDDG.IDD_B003_LGL_SRCH_ROW r
         WHERE r.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU) AS ROWS_ON_CHANNEL,
       TO_CHAR(SYSDATE,'HH24:MI:SS') AS T
FROM SIDDG.IDD_B003_LGL_SRCH_CHNL c
JOIN SIDDG.IDD_B003_LGL_SRCH_POST p ON p.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU;


-- ---------------------------------------------------------------------
-- B. 진행 중일 때 남은 행 수(5분 간격 두 번 → 줄어든 행/초 = 속도) [읽기]
-- ---------------------------------------------------------------------
SELECT COUNT(*) AS REMAINING, TO_CHAR(SYSDATE,'HH24:MI:SS') AS T
FROM SIDDG.IDD_B003_LGL_SRCH_ROW
WHERE RFRN_POST_HASH_VALU = (SELECT RFRN_POST_HASH_VALU FROM SIDDG.IDD_B003_LGL_SRCH_CHNL);


-- ---------------------------------------------------------------------
-- C. 완료 검증 [읽기]
--    기대: SEL_VER=filename-search-selection-v2, ROWS_NEW=60971724, VHEAD=1, CHAN_NO=2 (PROOF=false 는 정상)
-- ---------------------------------------------------------------------
SELECT c.RFRN_CHNL_NAME, c.CHAN_NO,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.search_selection.schema_version') AS SEL_VER,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.selection_proof.native_latest_verified') AS PROOF,
       (SELECT COUNT(*) FROM SIDDG.IDD_B003_LGL_SRCH_ROW r WHERE r.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU) AS ROWS_NEW,
       (SELECT COUNT(*) FROM SIDDG.IDD_B003_LGL_VCTR_HEAD h WHERE h.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU) AS VHEAD
FROM SIDDG.IDD_B003_LGL_SRCH_CHNL c
JOIN SIDDG.IDD_B003_LGL_SRCH_POST p ON p.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU;


-- ---------------------------------------------------------------------
-- D. 게시된 벡터 임베딩 모델 확인 [읽기]
--    운영 GENOS 임베딩 서빙(GENOS_EMBED_ID=142)이 이 모델(kure-v1, 1024차원)과 같은지 확인
-- ---------------------------------------------------------------------
SELECT JSON_VALUE(p.VCTR_POST_IFMN_CTNT,'$.manifest.profile.model') AS MODEL,
       JSON_VALUE(p.VCTR_POST_IFMN_CTNT,'$.manifest.profile.dimensions') AS DIM,
       JSON_VALUE(p.VCTR_POST_IFMN_CTNT,'$.manifest.profile.revision') AS REV,
       JSON_VALUE(p.VCTR_POST_IFMN_CTNT,'$.completion.count') AS VECTORS
FROM SIDDG.IDD_B003_LGL_VCTR_POST p
WHERE p.VCTR_POST_ID = (SELECT h.VCTR_POST_ID FROM SIDDG.IDD_B003_LGL_VCTR_HEAD h
                        JOIN SIDDG.IDD_B003_LGL_SRCH_CHNL c ON h.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU);


-- ---------------------------------------------------------------------
-- E. 개발계 ↔ 운영계 대조 [읽기] — 두 결과의 DV·SEL·SRCH_ROWS·VECTOR가 같아야 한다
-- ---------------------------------------------------------------------
-- E-1 운영계
SELECT JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.dataset_version') AS DV,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.search_selection.schema_version') AS SEL,
       (SELECT COUNT(*) FROM SIDDG.IDD_B003_LGL_SRCH_ROW r WHERE r.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU) AS SRCH_ROWS,
       (SELECT JSON_VALUE(v.VCTR_POST_IFMN_CTNT,'$.manifest.profile.model')||' / '||JSON_VALUE(v.VCTR_POST_IFMN_CTNT,'$.completion.count')
          FROM SIDDG.IDD_B003_LGL_VCTR_HEAD h JOIN SIDDG.IDD_B003_LGL_VCTR_POST v ON v.VCTR_POST_ID=h.VCTR_POST_ID
         WHERE h.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU) AS VECTOR
FROM SIDDG.IDD_B003_LGL_SRCH_CHNL c JOIN SIDDG.IDD_B003_LGL_SRCH_POST p ON p.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU;

-- E-2 개발계
SELECT JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.dataset_version') AS DV,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.search_selection.schema_version') AS SEL,
       (SELECT COUNT(*) FROM SIDDS.LGL_G19_SRCH_ROW_S_1 r WHERE r.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU) AS SRCH_ROWS,
       (SELECT JSON_VALUE(v.VCTR_POST_IFMN_CTNT,'$.manifest.profile.model')||' / '||JSON_VALUE(v.VCTR_POST_IFMN_CTNT,'$.completion.count')
          FROM SIDDS.LGL_G19_VCTR_HEAD_S_1 h JOIN SIDDS.LGL_G19_VCTR_POST_S_1 v ON v.VCTR_POST_ID=h.VCTR_POST_ID
         WHERE h.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU) AS VECTOR
FROM SIDDS.LGL_G19_SRCH_CHNL_S_1 c JOIN SIDDS.LGL_G19_SRCH_POST_S_1 p ON p.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU
WHERE c.RFRN_CHNL_NAME='g19_7c1f8f4931c8be61b914f5bc';


-- ---------------------------------------------------------------------
-- F. 실행 계획 확인 — RUN 아님, EXPLAIN PLAN 버튼으로만 [읽기]
--    TABLE ACCESS FULL 이면 기존 방식이 갈수록 느려진다(R7f는 인덱스 구간 방식)
-- ---------------------------------------------------------------------
UPDATE SIDDG.IDD_B003_LGL_SRCH_ROW SET RFRN_POST_HASH_VALU = RFRN_POST_HASH_VALU
WHERE RFRN_POST_HASH_VALU = (SELECT RFRN_POST_HASH_VALU FROM SIDDG.IDD_B003_LGL_SRCH_CHNL) AND ROWNUM <= 20000;


-- ---------------------------------------------------------------------
-- G. 통계 갱신 — UPDATE 끝난 뒤 [DBA] (서빙 SQL 느려짐 방지, 수십 분 걸릴 수 있음)
-- ---------------------------------------------------------------------
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS('SIDDG','IDD_B003_LGL_SRCH_ROW', cascade=>TRUE, degree=>4);
  DBMS_STATS.GATHER_TABLE_STATS('SIDDG','IDD_B003_LGL_VCTR_ITEM', cascade=>TRUE, degree=>4);
END;


-- ---------------------------------------------------------------------
-- H. 아카이브 로그 공간 [DBA]
-- ---------------------------------------------------------------------
SELECT NAME, SPACE_LIMIT/1024/1024/1024 AS LIMIT_GB, SPACE_USED/1024/1024/1024 AS USED_GB,
       SPACE_RECLAIMABLE/1024/1024/1024 AS RECLAIMABLE_GB FROM V$RECOVERY_FILE_DEST;
SELECT FILE_TYPE, PERCENT_SPACE_USED, PERCENT_SPACE_RECLAIMABLE FROM V$RECOVERY_AREA_USAGE;


-- ---------------------------------------------------------------------
-- I. ORDS 접속 계정의 Agent 기록 표 권한 [DBA] — '<ORDS계정>'을 운영 ORDS 계정으로
--    필요: RUN_A SELECT·INSERT·UPDATE / REC_A SELECT·INSERT·DELETE / BODY_A SELECT·INSERT / EXEC_ST_A SELECT·INSERT·UPDATE·DELETE
--          + SIDDG Gold 13개 표 SELECT
-- ---------------------------------------------------------------------
SELECT GRANTEE, OWNER, TABLE_NAME, PRIVILEGE FROM DBA_TAB_PRIVS
WHERE GRANTEE = '<ORDS계정>' AND OWNER IN ('SIDDA','SIDDG')
ORDER BY OWNER, TABLE_NAME, PRIVILEGE;


-- ---------------------------------------------------------------------
-- J. 처음 원인 확인에 쓴 SQL [읽기] (기록용)
-- ---------------------------------------------------------------------
SELECT c.RFRN_CHNL_NAME,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.search_selection.schema_version') AS SEL_VER,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.selection_proof.native_latest_verified') AS PROOF,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.dataset_version') AS DATASET_VERSION,
       JSON_VALUE(p.RFRN_POST_IFMN_CTNT, '$.source_manifest.generation_id') AS GEN_ID,
       DBMS_LOB.GETLENGTH(p.RFRN_POST_IFMN_CTNT) AS LEN
FROM SIDDG.IDD_B003_LGL_SRCH_CHNL c
JOIN SIDDG.IDD_B003_LGL_SRCH_POST p ON p.RFRN_POST_HASH_VALU = c.RFRN_POST_HASH_VALU;

SELECT COUNT(*) AS DOCS, COUNT(DISTINCT RGLT_DOC_NAME) AS NAMES FROM SIDDG.IDD_B003_LGL_DOC_VER;


-- ---------------------------------------------------------------------
-- K. [참고] R7f 레시피가 실제로 보내는 쓰기 SQL (직접 실행하지 말 것. JSON·번호는 레시피가 계산)
--     <q0>=옛 검색 게시본, <q1>=새 검색 게시본, <s1>=새 원문 게시본, <v0>/<v1>=옛/새 벡터 게시본 (로그 PLAN 줄)
-- ---------------------------------------------------------------------
-- K-1 새 게시본 3행
-- INSERT INTO SIDDG.IDD_B003_LGL_SRC_POST (BODY_POST_HASH_VALU, DTLS_HASH_VALU, BODY_POST_IFMN_CTNT, RGSN_ASTM) VALUES ('<s1>', '<dataset_version>', <원문 게시본 JSON>, SYSTIMESTAMP);
-- INSERT INTO SIDDG.IDD_B003_LGL_SRCH_POST (RFRN_POST_HASH_VALU, RFRN_POST_IFMN_CTNT) VALUES ('<q1>', <검색 명세 JSON>);
-- INSERT INTO SIDDG.IDD_B003_LGL_VCTR_POST (VCTR_POST_ID, VCTR_POST_IFMN_CTNT) VALUES ('<v1>', <벡터 게시본 JSON>);
-- K-2 벡터 행(0행 될 때까지 반복, 매번 COMMIT)
-- UPDATE SIDDG.IDD_B003_LGL_VCTR_ITEM SET VCTR_POST_ID='<v1>' WHERE VCTR_POST_ID='<v0>' AND ROWNUM<=50000;
-- K-3 검색 행: 종류별로 (가) 다음 5만 행 끝 ID 찾기 → (나) 그 구간 UPDATE·COMMIT 반복
-- SELECT ID FROM (SELECT ID, ROWNUM RN FROM (SELECT /*+ INDEX_ASC(t (RFRN_POST_HASH_VALU RFRN_DTA_TYPE_VALU RFRN_DTA_ID)) */ RFRN_DTA_ID AS ID
--   FROM SIDDG.IDD_B003_LGL_SRCH_ROW t WHERE RFRN_POST_HASH_VALU='<q0>' AND RFRN_DTA_TYPE_VALU='<종류>' AND RFRN_DTA_ID>'<지난 끝>' ORDER BY RFRN_DTA_ID)
--   WHERE ROWNUM<=50000) WHERE RN=50000;
-- UPDATE /*+ INDEX_ASC(t (RFRN_POST_HASH_VALU RFRN_DTA_TYPE_VALU RFRN_DTA_ID)) */ SIDDG.IDD_B003_LGL_SRCH_ROW t SET RFRN_POST_HASH_VALU='<q1>'
--   WHERE RFRN_POST_HASH_VALU='<q0>' AND RFRN_DTA_TYPE_VALU='<종류>' AND RFRN_DTA_ID>'<지난 끝>' AND RFRN_DTA_ID<='<이번 끝>'; COMMIT;
-- K-4 벡터 연결·채널(마지막)
-- UPDATE SIDDG.IDD_B003_LGL_VCTR_HEAD SET RFRN_POST_HASH_VALU='<q1>', VCTR_POST_ID='<v1>', CHAN_NO=CHAN_NO+1 WHERE RFRN_POST_HASH_VALU='<q0>' AND VCTR_POST_ID='<v0>';
-- UPDATE SIDDG.IDD_B003_LGL_SRCH_CHNL SET RFRN_POST_HASH_VALU='<q1>', CHAN_NO=CHAN_NO+1 WHERE RFRN_CHNL_NAME='g19_252f50906fa00e444b543cec' AND RFRN_POST_HASH_VALU='<q0>'; COMMIT;
--
-- K-5 [DBA 선택] 검색 행을 병렬 한 문장으로 (레시피 작업을 먼저 멈춘 뒤에만. undo 크게 씀)
-- ALTER SESSION ENABLE PARALLEL DML;
-- UPDATE /*+ PARALLEL(t 8) */ SIDDG.IDD_B003_LGL_SRCH_ROW t SET RFRN_POST_HASH_VALU='<q1>' WHERE RFRN_POST_HASH_VALU='<q0>'; COMMIT;
-- → 끝나면 레시피를 다시 RUN (검색 행은 건너뛰고 K-4와 검증을 레시피가 마무리)

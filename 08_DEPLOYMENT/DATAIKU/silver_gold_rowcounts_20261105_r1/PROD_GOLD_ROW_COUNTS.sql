-- 운영계 Dataiku의 현재 Gold 적재 Oracle 연결에서 실행합니다.
-- 1번과 2번 SELECT는 각각 별도로 실행합니다.
-- 1번: SIDDG.IDD_B003_LGL_* 전체 테이블별 실제 COUNT(*)와 합계.
-- 모든 저장 판본을 포함하며 *_COMMA 열은 쉼표 표시입니다.
-- 실버와 골드는 파일조각/판본/벡터 등 구성 차이가 있어 총합이 같아야 하는 것은 아닙니다.
-- 각 테이블 COUNT는 확정된 행을 읽으며 적재 중에는 테이블별 조회 시점이 다를 수 있습니다.
-- Oracle DBMS_XMLGEN / XMLTABLE을 사용합니다. 조회 권한이 없는 표는 오류로 표시됩니다.
-- 행 수가 많으면 완료까지 시간이 걸립니다. 재조회는 첫 조회 완료 후 실행합니다.
-- https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XMLGEN.html
WITH TARGET_TABLES AS (
    SELECT /*+ MATERIALIZE */ T.OWNER, T.TABLE_NAME
    FROM ALL_TABLES T
    WHERE T.OWNER = 'SIDDG'
      AND T.TABLE_NAME LIKE 'IDD\_B003\_LGL\_%' ESCAPE '\'
      AND T.NESTED = 'NO'
      AND (T.IOT_TYPE IS NULL OR T.IOT_TYPE = 'IOT')
), ROW_COUNTS AS (
    SELECT /*+ MATERIALIZE */ T.OWNER, T.TABLE_NAME, X.N AS ROW_COUNT
    FROM TARGET_TABLES T,
         XMLTABLE(
             '/ROWSET/ROW'
             PASSING DBMS_XMLGEN.GETXMLTYPE(
                 'SELECT COUNT(*) AS N FROM "'
                 || REPLACE(T.OWNER, '"', '""') || '"."'
                 || REPLACE(T.TABLE_NAME, '"', '""') || '"'
             )
             COLUMNS N NUMBER PATH 'N'
         ) X
)
SELECT SYSTIMESTAMP AS CHECKED_AT,
       'PROD_GOLD' AS LAYER_NAME,
       OWNER,
       TABLE_NAME,
       ROW_COUNT,
       TO_CHAR(ROW_COUNT, 'FM999,999,999,999,999,999,990') AS ROW_COUNT_COMMA,
       COUNT(*) OVER () AS TABLE_COUNT,
       SUM(ROW_COUNT) OVER () AS TOTAL_ROWS,
       TO_CHAR(SUM(ROW_COUNT) OVER (), 'FM999,999,999,999,999,999,990') AS TOTAL_ROWS_COMMA
FROM ROW_COUNTS
ORDER BY ROW_COUNT DESC, TABLE_NAME;

-- 2번: 현재 적재 중인 검색자료의 판본별 실제 확정 행 수.
-- 첫 조회 완료 후 2~5분 뒤 같은 SELECT를 다시 실행합니다.
-- 같은 QUERY_RELEASE_ID의 COMMITTED_SEARCH_ROWS가 늘면 그 사이 확정 적재가 진행된 것입니다.
-- 한 번 값이 같다는 사실만으로 적재 정지로 판정하지 않습니다.
-- 모든 판본 합계와 한 판본의 행 수를 혼동하지 않습니다.
SELECT SYSTIMESTAMP AS CHECKED_AT,
       RFRN_POST_HASH_VALU AS QUERY_RELEASE_ID,
       COUNT(*) AS COMMITTED_SEARCH_ROWS,
       TO_CHAR(COUNT(*), 'FM999,999,999,999,999,999,990') AS COMMITTED_ROWS_COMMA
FROM SIDDG.IDD_B003_LGL_SRCH_ROW
GROUP BY RFRN_POST_HASH_VALU
ORDER BY COMMITTED_SEARCH_ROWS DESC, QUERY_RELEASE_ID;

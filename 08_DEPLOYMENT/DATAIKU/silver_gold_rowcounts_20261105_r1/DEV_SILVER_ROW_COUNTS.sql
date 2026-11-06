-- 개발계 Dataiku의 Oracle 연결에서 이 SELECT 한 문장 전체를 실행합니다.
-- 대상: SIDDS의 우리 LGL_* / IDD_B03_LGL_* / IDD_B003_LGL_* 실제 테이블 전체.
-- 기존 *_S와 새 *_S_1 등 모든 판본을 포함합니다. SIDDA 에이전트 표는 제외합니다.
-- ROW_COUNT = 테이블별 실제 COUNT(*), TOTAL_ROWS = 조회 대상 테이블 행 수 합계.
-- *_COMMA 열은 쉼표 표시입니다. NUM_ROWS 통계값을 사용하지 않습니다.
-- 합계는 원문/검색/게시/파일조각/벡터 등 모든 종류의 합이며 고유 문서 수가 아닙니다.
-- 각 테이블 COUNT는 확정된 행을 읽으며 적재 중에는 테이블별 조회 시점이 다를 수 있습니다.
-- Oracle DBMS_XMLGEN / XMLTABLE을 사용합니다. 조회 권한이 없는 표는 오류로 표시됩니다.
-- 행 수가 많으면 완료까지 시간이 걸립니다. 재조회는 첫 조회 완료 후 실행합니다.
-- https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XMLGEN.html
WITH TARGET_TABLES AS (
    SELECT /*+ MATERIALIZE */ T.OWNER, T.TABLE_NAME
    FROM ALL_TABLES T
    WHERE T.OWNER = 'SIDDS'
      AND (T.TABLE_NAME LIKE 'LGL\_%' ESCAPE '\'
           OR REGEXP_LIKE(T.TABLE_NAME, '^IDD_B0?03_LGL_'))
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
       'DEV_SILVER' AS LAYER_NAME,
       OWNER,
       TABLE_NAME,
       ROW_COUNT,
       TO_CHAR(ROW_COUNT, 'FM999,999,999,999,999,999,990') AS ROW_COUNT_COMMA,
       COUNT(*) OVER () AS TABLE_COUNT,
       SUM(ROW_COUNT) OVER () AS TOTAL_ROWS,
       TO_CHAR(SUM(ROW_COUNT) OVER (), 'FM999,999,999,999,999,999,990') AS TOTAL_ROWS_COMMA
FROM ROW_COUNTS
ORDER BY ROW_COUNT DESC, TABLE_NAME;

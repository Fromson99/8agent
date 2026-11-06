-- 개발계 Dataiku Oracle SQL 노트북에서 SELECT 한 문장 전체를 실행합니다.
-- SIDDS.LGL_G19_*_S_1 현 개발 적재 대상 10개 표만 집계합니다.
-- 기존 LGL_*_S, LGL_G19_*_S 및 SIDDA 에이전트 표는 포함하지 않습니다.
-- POST/CHNL/HEAD는 게시 명세·연결 표이므로 1행도 정상일 수 있습니다.
-- 전체 합계는 문서 수가 아니라 선택된 표의 모든 행 수 합계입니다.
WITH TARGET_TABLES AS (
    SELECT /*+ MATERIALIZE */ T.OWNER, T.TABLE_NAME
    FROM ALL_TABLES T
    WHERE T.OWNER = 'SIDDS'
      AND T.TABLE_NAME LIKE 'LGL\_G19\_%\_S\_1' ESCAPE '\'
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
       'DEV_SILVER_G19_1' AS LAYER_NAME,
       OWNER,
       TABLE_NAME,
       ROW_COUNT,
       TO_CHAR(ROW_COUNT, 'FM999,999,999,999,999,999,990') AS ROW_COUNT_COMMA,
       COUNT(*) OVER () AS TABLE_COUNT,
       SUM(ROW_COUNT) OVER () AS TOTAL_ROWS,
       TO_CHAR(SUM(ROW_COUNT) OVER (), 'FM999,999,999,999,999,999,990') AS TOTAL_ROWS_COMMA
FROM ROW_COUNTS
ORDER BY ROW_COUNT DESC, TABLE_NAME;

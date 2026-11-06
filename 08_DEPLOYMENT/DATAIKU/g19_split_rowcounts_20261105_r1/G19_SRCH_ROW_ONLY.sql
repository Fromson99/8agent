-- 개발계 Dataiku Oracle 연결에서 이 SELECT 한 문장 전체를 별도로 실행합니다.
-- 현재 검색자료 테이블의 실제 전체 행 수입니다. 모든 저장 판본을 포함합니다.
SELECT 'LGL_G19_SRCH_ROW_S_1' AS TABLE_NAME,
       COUNT(*) AS ROW_COUNT,
       TO_CHAR(COUNT(*), 'FM999,999,999,999,990') AS ROW_COUNT_COMMA
FROM SIDDS.LGL_G19_SRCH_ROW_S_1;

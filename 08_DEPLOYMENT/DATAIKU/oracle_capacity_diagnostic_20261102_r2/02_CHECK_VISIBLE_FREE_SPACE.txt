-- Oracle 용량 추가 확인 R2 / 2026-11-02
-- 기존 AIDP 연결의 Dataiku SQL 노트북에서 아래 SELECT 1개만 실행하세요.
-- 현재 계정에 공개된 테이블스페이스 여유 공간을 조회합니다.
-- 조회 결과는 0~1행입니다. 실데이터 전체 COUNT나 쓰기를 하지 않습니다.
-- 결과가 0행이면 정보 비노출 또는 여유 extent 없음 등을 구별할 수 없습니다.
-- 0행을 용량0 또는 무제한으로 해석하지 마세요.
-- 숫자가 나와도 SIDDS의 Quota, 자동 확장 한도, 실제 디스크 여유는 별도입니다.

SELECT TABLESPACE_NAME,
       ROUND(SUM(BYTES) / POWER(1024, 3), 3)
         AS VISIBLE_FREE_GIB,
       ROUND(MAX(BYTES) / POWER(1024, 2), 3)
         AS MAX_FREE_EXTENT_MIB
FROM USER_FREE_SPACE
WHERE TABLESPACE_NAME IN (
    SELECT TABLESPACE_NAME
    FROM ALL_TABLES
    WHERE OWNER = 'SIDDS'
      AND TABLE_NAME = 'LGL_SRCH_ROW_S'
)
GROUP BY TABLESPACE_NAME;

-- 정적 문법/읽기 전용 구성을 점검한 준비본이며 현장 실행 결과는 아직 없습니다.
-- 출처: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_FREE_SPACE.html

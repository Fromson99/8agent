-- Oracle 용량 확인 / 2026-11-02
-- Dataiku SQL 노트북에서 기존 적재와 같은 AIDP 연결을 선택하세요.
-- Q1~Q4를 각각 별도 SQL 셀에서 실행합니다. 모두 읽기 전용 SELECT입니다.
-- 기존 적재/재개/임베딩 셀을 다시 실행할 필요가 없습니다.
-- 실데이터 행수 COUNT나 JSON 본문 조회를 하지 않습니다.
-- 용량 단위는 GiB(1024^3 bytes)입니다.

-- Q1. 접속 계정과 확인 대상 테이블: 보통 1행
-- TABLE_NAME이 NULL이면 현재 연결에서 대상 테이블을 확인하지 못한 것입니다.
-- SCHEMA_AS가 SIDDS여도 CONNECTED_AS(실제 접속 계정)는 다른 계정일 수 있습니다.
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS CONNECTED_AS,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS SCHEMA_AS,
       t.OWNER, t.TABLE_NAME, t.TABLESPACE_NAME, t.PARTITIONED
FROM DUAL
LEFT JOIN ALL_TABLES t
  ON t.OWNER = 'SIDDS' AND t.TABLE_NAME = 'LGL_SRCH_ROW_S';

-- Q2. SIDDS 계정의 등록된 tablespace Quota: 대상 테이블스페이스 0~1행
-- ORA-00942/ORA-01031이면 해당 DBA 메타데이터 조회 권한 확인이 필요합니다.
-- 0행은 무제한/용량0이라는 뜻이 아닙니다. 별도 UNLIMITED TABLESPACE 권한도 있습니다.
-- QUOTA_GIB=-1은 해당 등록 Quota가 무제한이라는 뜻이며, 디스크 무제한은 아닙니다.
SELECT q.USERNAME, q.TABLESPACE_NAME,
       ROUND(q.BYTES / POWER(1024, 3), 3) AS CHARGED_GIB,
       CASE WHEN q.MAX_BYTES = -1 THEN -1
            ELSE ROUND(q.MAX_BYTES / POWER(1024, 3), 3) END AS QUOTA_GIB
FROM DBA_TS_QUOTAS q
WHERE q.USERNAME = 'SIDDS'
  AND q.TABLESPACE_NAME IN (
    SELECT TABLESPACE_NAME FROM ALL_TABLES
    WHERE OWNER = 'SIDDS' AND TABLE_NAME = 'LGL_SRCH_ROW_S'
  );

-- Q3. 대상 테이블스페이스의 여유 공간/확장 설정: 보통 1행
-- FREE_GIB는 현재 파일 안의 미할당 extent 합계입니다.
-- AUTO_GROW_LIMIT_GIB는 자동 확장 설정상 추가 가능량이며 실제 디스크 여유 보장이 아닙니다.
-- MAX_FREE_EXTENT_MIB는 현재 가장 큰 미할당 extent의 MiB 값입니다.
-- NOT_ONLINE_FILES가 0보다 크면 DBA 확인 전 여유 공간을 확정 해석하지 마세요.
-- Q1의 TABLESPACE_NAME이 NULL이면 이 결과가 0행일 수 있습니다.
WITH target_ts AS (
  SELECT TABLESPACE_NAME FROM ALL_TABLES
  WHERE OWNER = 'SIDDS' AND TABLE_NAME = 'LGL_SRCH_ROW_S'
), free_by_file AS (
  SELECT FILE_ID, SUM(BYTES) AS FREE_BYTES, MAX(BYTES) AS MAX_EXTENT
  FROM DBA_FREE_SPACE
  WHERE TABLESPACE_NAME IN (SELECT TABLESPACE_NAME FROM target_ts)
  GROUP BY FILE_ID
)
SELECT d.TABLESPACE_NAME,
       ROUND(SUM(d.BYTES) / POWER(1024, 3), 3) AS FILE_GIB,
       ROUND(SUM(NVL(f.FREE_BYTES, 0)) / POWER(1024, 3), 3) AS FREE_GIB,
       ROUND(SUM(CASE WHEN d.AUTOEXTENSIBLE = 'YES'
                      THEN GREATEST(NVL(d.MAXBYTES, d.BYTES) - d.BYTES, 0)
                      ELSE 0 END) / POWER(1024, 3), 3) AS AUTO_GROW_LIMIT_GIB,
       ROUND(MAX(NVL(f.MAX_EXTENT, 0)) / POWER(1024, 2), 3) AS MAX_FREE_EXTENT_MIB,
       SUM(CASE WHEN d.AUTOEXTENSIBLE = 'YES' THEN 1 ELSE 0 END) AS AUTO_FILES,
       SUM(CASE WHEN d.ONLINE_STATUS = 'ONLINE' THEN 0 ELSE 1 END) AS NOT_ONLINE_FILES
FROM DBA_DATA_FILES d
LEFT JOIN free_by_file f ON f.FILE_ID = d.FILE_ID
WHERE d.TABLESPACE_NAME IN (SELECT TABLESPACE_NAME FROM target_ts)
GROUP BY d.TABLESPACE_NAME;

-- Q4. 테이블 본체·일반 인덱스·CLOB/LOB의 물리 할당: 큰 순서 상위5개 그룹
-- 원문 논리 크기나 여유 공간이 아닌, 확보된 세그먼트의 할당량입니다.
-- 아래 결과는 이 테이블에 직접 연결된 세그먼트이며 SIDDS 전체 사용량이 아닙니다.
WITH target_segments AS (
  SELECT OWNER, TABLE_NAME AS SEGMENT_NAME FROM ALL_TABLES
  WHERE OWNER = 'SIDDS' AND TABLE_NAME = 'LGL_SRCH_ROW_S'
  UNION
  SELECT OWNER, INDEX_NAME FROM ALL_INDEXES
  WHERE TABLE_OWNER = 'SIDDS' AND TABLE_NAME = 'LGL_SRCH_ROW_S'
  UNION
  SELECT OWNER, SEGMENT_NAME FROM ALL_LOBS
  WHERE OWNER = 'SIDDS' AND TABLE_NAME = 'LGL_SRCH_ROW_S'
  UNION
  SELECT OWNER, INDEX_NAME FROM ALL_LOBS
  WHERE OWNER = 'SIDDS' AND TABLE_NAME = 'LGL_SRCH_ROW_S'
)
SELECT s.TABLESPACE_NAME, s.SEGMENT_TYPE,
       ROUND(SUM(s.BYTES) / POWER(1024, 3), 3) AS ALLOCATED_GIB
FROM DBA_SEGMENTS s
JOIN target_segments t ON t.OWNER = s.OWNER AND t.SEGMENT_NAME = s.SEGMENT_NAME
GROUP BY s.TABLESPACE_NAME, s.SEGMENT_TYPE
ORDER BY ALLOCATED_GIB DESC
FETCH FIRST 5 ROWS ONLY;

-- Q2 권한이 없고 Q1 CONNECTED_AS가 SIDDS일 때만 쓰는 보조 쿼리
-- 다른 계정으로 실행한 USER_TS_QUOTAS/SESSION_PRIVS를 SIDDS 결과로 해석하지 마세요.
-- 보조 Q5: 보통 0~1행
SELECT USER AS QUOTA_USER, TABLESPACE_NAME,
       ROUND(BYTES / POWER(1024, 3), 3) AS CHARGED_GIB,
       CASE WHEN MAX_BYTES = -1 THEN -1
            ELSE ROUND(MAX_BYTES / POWER(1024, 3), 3) END AS QUOTA_GIB
FROM USER_TS_QUOTAS
WHERE SYS_CONTEXT('USERENV', 'SESSION_USER') = 'SIDDS'
  AND TABLESPACE_NAME IN (
    SELECT TABLESPACE_NAME FROM ALL_TABLES
    WHERE OWNER = 'SIDDS' AND TABLE_NAME = 'LGL_SRCH_ROW_S'
  );

-- 보조 Q6: 1행. YES여도 tablespace/디스크 여유는 별도입니다.
SELECT CASE WHEN SYS_CONTEXT('USERENV', 'SESSION_USER') <> 'SIDDS' THEN 'NOT_SIDDS'
            WHEN EXISTS (SELECT 1 FROM SESSION_PRIVS WHERE PRIVILEGE = 'UNLIMITED TABLESPACE')
            THEN 'YES' ELSE 'NO' END AS SESSION_UNLIMITED_TABLESPACE
FROM DUAL;

-- 결과 Q1~Q4 또는 권한 오류 코드를 캡처하면 됩니다.
-- ORA-00942/ORA-01031은 용량0을 뜻하지 않습니다. Q3/Q4가 막히면 DBA가 실행해야 합니다.
-- 현재 실제 디스크 여유와 실패 ORA-01653에 명시된 테이블/테이블스페이스는 별도 대조 대상입니다.
-- 이 파일은 코드 준비본이며 현장 DB에서 실행/검증한 결과가 아닙니다.
-- 출처:
-- https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TS_QUOTAS.html
-- https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DATA_FILES.html
-- https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_FREE_SPACE.html

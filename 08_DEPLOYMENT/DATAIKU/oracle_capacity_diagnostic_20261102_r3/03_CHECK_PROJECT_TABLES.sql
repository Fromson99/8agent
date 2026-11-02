-- 우리 개발 테이블 목록/할당량 확인 R3 / 2026-11-02
-- AIDP SQL 노트북에서 Q1, Q2를 각각 별도 셀로 실행합니다.
-- R11 전달본의9개 대상 + 후속 벡터2개 대상에 이름을 제한합니다.
-- 최대11개 테이블입니다. 아직 만들지 않았거나 접근 권한이 없는 표는 안 보일 수 있습니다.
-- 공용 계정에서 생성/적재한 사람을 식별하는 감사 조회는 아닙니다.
-- 읽기 전용 관리 정보 조회이며 실데이터 전체 COUNT/통계 수집/변경은 하지 않습니다.

-- Q1. 테이블 목록·생성 시각·마지막 통계의 행 수 (최대11행)
-- STATS_ROWS는 마지막 통계 수집 시점의 값이며 현재 실제 행 수가 아닙니다.
-- NULL은 통계 미확인이며 0행이라는 뜻이 아닙니다.
-- CREATED_AT은 객체 생성 시각이며 사람 이름/최종 INSERT 시각을 나타내지 않습니다.
SELECT t.OWNER, t.TABLE_NAME, t.TABLESPACE_NAME,
       TO_CHAR(o.CREATED, 'YYYY-MM-DD HH24:MI:SS') AS CREATED_AT,
       t.NUM_ROWS AS STATS_ROWS,
       TO_CHAR(t.LAST_ANALYZED, 'YYYY-MM-DD HH24:MI:SS') AS STATS_AT
FROM ALL_TABLES t
LEFT JOIN ALL_OBJECTS o
  ON o.OWNER = t.OWNER AND o.OBJECT_NAME = t.TABLE_NAME
 AND o.OBJECT_TYPE = 'TABLE' AND o.SUBOBJECT_NAME IS NULL
WHERE (t.OWNER = 'SIDDS' AND t.TABLE_NAME IN (
  'LGL_DOC_VER_S', 'LGL_DOC_UNIT_S', 'LGL_DOC_BLK_S',
  'LGL_SRCH_ROW_S', 'LGL_SRC_PBLS_S', 'LGL_SRCH_PBLS_S',
  'LGL_SRCH_CHNL_S', 'LGL_FILE_PART_S',
  'LGL_VCTR_SET_S', 'LGL_VCTR_ITEM_S'
)) OR (t.OWNER = 'SIDDA' AND t.TABLE_NAME = 'LGL_EXEC_ST_A')
ORDER BY t.OWNER, t.TABLE_NAME;

-- Q2. 테이블별 물리 할당 용량 (최대11행, DBA_SEGMENTS 읽기 권한 필요)
-- R1에서 DBA_TS_QUOTAS가 막힌 것과 이 뷰의 권한은 별개이므로 조회 가능 여부는 미확인입니다.
-- ORA-00942/ORA-01031이면 현재 계정으로 정확한 할당량을 확인하지 못한 것입니다.
-- USER_SEGMENTS로 단순 교체하면 PIDD2APP 소유 객체를 보게 되므로 대체하지 마세요.
-- TABLE_GIB: 테이블 본체 / INDEX_GIB: 일반 인덱스 / LOB_GIB: LOB 데이터·LOB 인덱스.
-- ALLOCATED_GIB는 본체·인덱스·LOB 등을 모두 포함한 세그먼트 할당량입니다.
-- 원문 파일 크기, 이번 실행이 추가한 바이트, 개인 사용량, 회수 가능한 공간과 다릅니다.
WITH target_tables AS (
  SELECT OWNER, TABLE_NAME FROM ALL_TABLES
  WHERE (OWNER = 'SIDDS' AND TABLE_NAME IN (
    'LGL_DOC_VER_S', 'LGL_DOC_UNIT_S', 'LGL_DOC_BLK_S',
    'LGL_SRCH_ROW_S', 'LGL_SRC_PBLS_S', 'LGL_SRCH_PBLS_S',
    'LGL_SRCH_CHNL_S', 'LGL_FILE_PART_S',
    'LGL_VCTR_SET_S', 'LGL_VCTR_ITEM_S'
  )) OR (OWNER = 'SIDDA' AND TABLE_NAME = 'LGL_EXEC_ST_A')
), segment_map AS (
  SELECT OWNER AS TABLE_OWNER, TABLE_NAME,
         OWNER AS SEGMENT_OWNER, TABLE_NAME AS SEGMENT_NAME
  FROM target_tables
  UNION
  SELECT i.TABLE_OWNER, i.TABLE_NAME, i.OWNER, i.INDEX_NAME
  FROM ALL_INDEXES i
  JOIN target_tables t ON t.OWNER = i.TABLE_OWNER AND t.TABLE_NAME = i.TABLE_NAME
  UNION
  SELECT l.OWNER, l.TABLE_NAME, l.OWNER, l.SEGMENT_NAME
  FROM ALL_LOBS l
  JOIN target_tables t ON t.OWNER = l.OWNER AND t.TABLE_NAME = l.TABLE_NAME
  UNION
  SELECT l.OWNER, l.TABLE_NAME, l.OWNER, l.INDEX_NAME
  FROM ALL_LOBS l
  JOIN target_tables t ON t.OWNER = l.OWNER AND t.TABLE_NAME = l.TABLE_NAME
), allocated AS (
  SELECT m.TABLE_OWNER, m.TABLE_NAME,
         SUM(CASE WHEN s.SEGMENT_TYPE LIKE 'TABLE%' THEN s.BYTES ELSE 0 END) AS TABLE_BYTES,
         SUM(CASE WHEN s.SEGMENT_TYPE LIKE 'INDEX%' THEN s.BYTES ELSE 0 END) AS INDEX_BYTES,
         SUM(CASE WHEN s.SEGMENT_TYPE LIKE 'LOB%' THEN s.BYTES ELSE 0 END) AS LOB_BYTES,
         SUM(s.BYTES) AS TOTAL_BYTES
  FROM segment_map m
  JOIN DBA_SEGMENTS s ON s.OWNER = m.SEGMENT_OWNER AND s.SEGMENT_NAME = m.SEGMENT_NAME
  GROUP BY m.TABLE_OWNER, m.TABLE_NAME
)
SELECT t.OWNER, t.TABLE_NAME,
       ROUND(a.TABLE_BYTES / POWER(1024, 3), 3) AS TABLE_GIB,
       ROUND(a.INDEX_BYTES / POWER(1024, 3), 3) AS INDEX_GIB,
       ROUND(a.LOB_BYTES / POWER(1024, 3), 3) AS LOB_GIB,
       ROUND(a.TOTAL_BYTES / POWER(1024, 3), 3) AS ALLOCATED_GIB,
       CASE WHEN a.TOTAL_BYTES IS NULL THEN 'NO_SEGMENT_INFO'
            ELSE 'ALLOCATED' END AS SIZE_STATE
FROM target_tables t
LEFT JOIN allocated a ON a.TABLE_OWNER = t.OWNER AND a.TABLE_NAME = t.TABLE_NAME
ORDER BY a.TOTAL_BYTES DESC NULLS LAST, t.OWNER, t.TABLE_NAME;

-- 대상은 위 전달본의 일반 테이블 구조입니다. 별도 IOT/클러스터/파티션 변경은 추가 확인합니다.
-- NO_SEGMENT_INFO/NULL은 용량0이 아닙니다. 세그먼트 미생성 등의 구별이 필요합니다.
-- 정적 문법 검사를 한 준비본이며 현장 DB에서 실행한 결과가 아닙니다.

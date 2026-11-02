-- AIDP SQL notebook: current _1 SRCH_ROW allocation only. Read-only.
-- Requires DBA_SEGMENTS read access. PIDD2APP USER_SEGMENTS is not SIDDS usage.
-- ORA-00942/01031 means unavailable, not zero bytes. No fallback or DDL.
-- Includes PK, four secondary indexes, LOB segment and LOB index once each.
WITH targets AS (
  SELECT OWNER, TABLE_NAME FROM ALL_TABLES
  WHERE OWNER='SIDDS' AND TABLE_NAME='LGL_G19_SRCH_ROW_S_1'
), names AS (
  SELECT OWNER AS SEGMENT_OWNER,TABLE_NAME AS SEGMENT_NAME FROM targets
  UNION
  SELECT i.OWNER,i.INDEX_NAME FROM ALL_INDEXES i JOIN targets t
    ON i.TABLE_OWNER=t.OWNER AND i.TABLE_NAME=t.TABLE_NAME
  UNION
  SELECT l.OWNER,l.SEGMENT_NAME FROM ALL_LOBS l JOIN targets t
    ON l.OWNER=t.OWNER AND l.TABLE_NAME=t.TABLE_NAME
  UNION
  SELECT l.OWNER,l.INDEX_NAME FROM ALL_LOBS l JOIN targets t
    ON l.OWNER=t.OWNER AND l.TABLE_NAME=t.TABLE_NAME
)
SELECT s.SEGMENT_TYPE, COUNT(*) AS SEGMENTS, SUM(s.BYTES) AS ALLOCATED_BYTES,
       ROUND(SUM(s.BYTES)/POWER(1024,3),3) AS ALLOCATED_GIB
FROM names n JOIN DBA_SEGMENTS s
  ON s.OWNER=n.SEGMENT_OWNER AND s.SEGMENT_NAME=n.SEGMENT_NAME
GROUP BY s.SEGMENT_TYPE ORDER BY s.SEGMENT_TYPE;

-- Sum ALLOCATED_BYTES for current physical allocation, not payload bytes.
-- Dividing by acknowledged rows then multiplying by 60,971,724 is only a rough
-- extrapolation: initial row kinds may not represent later kinds, segments have
-- free space, and in-flight commits can be ahead of the saved checkpoint.
-- This excludes original tables, vectors, undo/redo, temp and recovery space.

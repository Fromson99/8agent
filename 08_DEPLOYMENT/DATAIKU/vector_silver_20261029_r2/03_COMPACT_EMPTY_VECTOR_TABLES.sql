-- 이전 18컬럼 테이블을 이미 만들었지만 벡터 적재 전일 때만 사용합니다.
-- 3테이블 중 한 곳이라도 데이터가 있으면 변경 전에 중단합니다.
-- 실행 전 기존/신규 벡터 적재 레시피를 모두 중지하세요. Oracle DDL은 자동 COMMIT입니다.
-- 처음부터 14컬럼으로 생성했으면 실행할 필요 없습니다.
DECLARE
  n NUMBER;
  PROCEDURE remove_column(t VARCHAR2, c VARCHAR2) IS
    found NUMBER;
  BEGIN
    SELECT COUNT(*) INTO found FROM ALL_TAB_COLUMNS
      WHERE OWNER='SIDDS' AND TABLE_NAME=t AND COLUMN_NAME=c;
    IF found=1 THEN
      EXECUTE IMMEDIATE 'ALTER TABLE SIDDS.'||t||' DROP COLUMN '||c||' CASCADE CONSTRAINTS';
    END IF;
  END;
BEGIN
  SELECT (SELECT COUNT(*) FROM SIDDS.LGL_VCTR_PBLS_S)
       + (SELECT COUNT(*) FROM SIDDS.LGL_VCTR_SEG_S)
       + (SELECT COUNT(*) FROM SIDDS.LGL_VCTR_ACT_S) INTO n FROM DUAL;
  IF n<>0 THEN RAISE_APPLICATION_ERROR(-20010,'VECTOR_TABLES_NOT_EMPTY: preserve existing data; do not drop columns'); END IF;
  remove_column('LGL_VCTR_PBLS_S','PROFILE_JSON');
  remove_column('LGL_VCTR_PBLS_S','EXPECTED_COUNT');
  remove_column('LGL_VCTR_PBLS_S','ACTUAL_COUNT');
  remove_column('LGL_VCTR_SEG_S','INPUT_HASH');
END;
/
-- 이후 Python check로 5/6/3컬럼·PK/FK/JSON/색인 검사를 통과해야 적재합니다.

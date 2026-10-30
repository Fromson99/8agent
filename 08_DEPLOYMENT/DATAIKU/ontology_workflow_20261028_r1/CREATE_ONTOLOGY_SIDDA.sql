-- 온톨로지 MVP 테이블 생성 — 개발계 SIDDA
-- 기준: 로컬 MAIN111 / ontology-workflow-20261028-r1 / 2026-10-28
-- 대상: SIDDA 테이블 5개 + 원문 좌표 인덱스 1개 + 테이블/컬럼 설명
-- 실행: SIDDA 소유 계정 또는 해당 스키마의 생성 권한을 가진 계정에서 실행.
-- 이 파일은 01_CREATE_TABLES.sql + 02_COMMENTS.sql의 통합본이다.
-- 둘을 이미 실행했다면 이 파일을 추가로 실행하지 않는다.
-- 기존 테이블을 삭제/변경하지 않으며 데이터 적재·권한 부여·RAG ON은 수행하지 않는다.
-- 같은 이름의 객체가 있으면 먼저 기존 정의를 확인한다. 오류를 무시하고 계속 실행하지 않는다.
-- 운영 골드의 메타 등록/DBA 생성 신청과 실제 현장 실행 여부는 별도다.
-- Oracle DDL은 자동 커밋되므로 전체 파일이 하나의 트랜잭션으로 롤백되지 않는다.

-- 1. 테이블과 인덱스 생성

-- Development SIDDA agent layer. Metadata/DBA approval is separate. No DROP or data migration.
CREATE TABLE SIDDA.LGL_ONT_WORK_A (
  BNDL_ID VARCHAR2(84 BYTE) NOT NULL,
  REV_NO NUMBER(18) NOT NULL,
  WORK_HASH_VAL VARCHAR2(64 BYTE) NOT NULL,
  ST_CD VARCHAR2(32 BYTE) NOT NULL,
  RVWR_ID VARCHAR2(512 BYTE),
  APRV_HASH_VAL VARCHAR2(64 BYTE),
  PRIMARY KEY (BNDL_ID,REV_NO),
  CHECK (ST_CD IN ('INPUT','DRAFT','APPROVED','REJECTED')),
  CHECK (REV_NO>=1)
);

CREATE TABLE SIDDA.LGL_ONT_EVT_A (
  EVT_ID VARCHAR2(64 BYTE) NOT NULL,
  BNDL_ID VARCHAR2(84 BYTE) NOT NULL,
  REV_NO NUMBER(18) NOT NULL,
  EVT_JSON_CN CLOB NOT NULL,
  PRIMARY KEY (EVT_ID),
  CHECK (EVT_JSON_CN IS JSON)
);

CREATE TABLE SIDDA.LGL_ONT_PUB_A (
  PUB_ID VARCHAR2(64 BYTE) NOT NULL,
  BNDL_ID VARCHAR2(84 BYTE) NOT NULL,
  REV_NO NUMBER(18) NOT NULL,
  PKG_HASH_VAL VARCHAR2(64 BYTE) NOT NULL,
  PKG_JSON_CN CLOB NOT NULL,
  PRIMARY KEY (PUB_ID),
  CHECK (PKG_JSON_CN IS JSON)
);

CREATE TABLE SIDDA.LGL_ONT_HEAD_A (
  BNDL_ID VARCHAR2(84 BYTE) NOT NULL,
  PUB_ID VARCHAR2(64 BYTE),
  CHG_SEQ_NO NUMBER(18) NOT NULL,
  PRIMARY KEY (BNDL_ID),
  CHECK (CHG_SEQ_NO>=0),
  FOREIGN KEY (PUB_ID) REFERENCES SIDDA.LGL_ONT_PUB_A(PUB_ID)
);

CREATE TABLE SIDDA.LGL_ONT_ANC_A (
  PUB_ID VARCHAR2(64 BYTE) NOT NULL,
  ANC_HASH_VAL VARCHAR2(64 BYTE) NOT NULL,
  DOC_ID VARCHAR2(512 BYTE) NOT NULL,
  SRC_VER_ID VARCHAR2(512 BYTE) NOT NULL,
  UNIT_ID VARCHAR2(512 BYTE) NOT NULL,
  PRIMARY KEY (PUB_ID,ANC_HASH_VAL),
  FOREIGN KEY (PUB_ID) REFERENCES SIDDA.LGL_ONT_PUB_A(PUB_ID)
);

CREATE INDEX SIDDA.LGL_ONT_ANC_IX_A ON SIDDA.LGL_ONT_ANC_A(ANC_HASH_VAL);

-- 2. 테이블 및 컬럼 설명

-- Descriptions only. Candidate terms; metadata/DBA approval remains separate.

COMMENT ON TABLE SIDDA.LGL_ONT_WORK_A IS '온톨로지 작업 판본 상태. 한 행 키 BNDL_ID,REV_NO. 검증된 입력/초안 객체를 내용해시로 저장하고 판본별 상태/승인 영수증을 기록. 생성·수정·승인·반려 시. 보존기간·업무오너 현장 정책 확정 필요. 원문 전체 복사·질문별 정답·수치 실행 결과는 제외. 출처: Dataiku S3 원문·판단 작업JSON. 승인과 게시/활성을 구분하며 해시와 변경순번 검사. 조회 예: SELECT * FROM SIDDA.LGL_ONT_WORK_A WHERE BNDL_ID=:bundle_id';

COMMENT ON COLUMN SIDDA.LGL_ONT_WORK_A.BNDL_ID IS '묶음 ID; VARCHAR2(84 BYTE); 행 식별 키. 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_WORK_A.REV_NO IS '작업 판본; NUMBER(18); 행 식별 키. 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_WORK_A.WORK_HASH_VAL IS 'S3 작업 JSON 해시; VARCHAR2(64 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_WORK_A.ST_CD IS '검토 상태; VARCHAR2(32 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도. INPUT=생성대기, DRAFT=검토대기, APPROVED=승인, REJECTED=반려. 게시 여부는 HEAD/PUB로 확인.';

COMMENT ON COLUMN SIDDA.LGL_ONT_WORK_A.RVWR_ID IS '승인자; VARCHAR2(512 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_WORK_A.APRV_HASH_VAL IS '승인 영수증 해시; VARCHAR2(64 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON TABLE SIDDA.LGL_ONT_EVT_A IS '온톨로지 운영 행위 이력. 한 행 키 EVT_ID. 실제 DB 트랜잭션과 함께 행위자·UTC시각·작업/게시 식별자를 기록. 각 명령 성공 시. 보존기간·업무오너 현장 정책 확정 필요. 감사 정보만 포함하며 원문 본문과 모델 원응답은 해당 저장 경로를 참조. 출처: 생성/검토/게시/중지/롤백 명령. 승인과 게시/활성을 구분하며 해시와 변경순번 검사. 조회 예: SELECT * FROM SIDDA.LGL_ONT_EVT_A WHERE BNDL_ID=:bundle_id';

COMMENT ON COLUMN SIDDA.LGL_ONT_EVT_A.EVT_ID IS '이벤트 영수증 ID; VARCHAR2(64 BYTE); 행 식별 키. 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_EVT_A.BNDL_ID IS '묶음 ID; VARCHAR2(84 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_EVT_A.REV_NO IS '작업 판본; NUMBER(18); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_EVT_A.EVT_JSON_CN IS '행위자·시간·상태 JSON; CLOB; 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON TABLE SIDDA.LGL_ONT_PUB_A IS '온톨로지 승인 시나리오 게시본. 한 행 키 PUB_ID. 원문 재검증 후 명시적 의존을 펼친 시나리오와 원문좌표를 불변 JSON으로 게시. 승인 판본 게시 시. 보존기간·업무오너 현장 정책 확정 필요. 원문 전체 복사·질문별 정답·수치 실행 결과는 제외. 출처: 승인 작업JSON·검토 영수증·SIDDS 원문 판본. 승인과 게시/활성을 구분하며 해시와 변경순번 검사. 조회 예: SELECT * FROM SIDDA.LGL_ONT_PUB_A WHERE BNDL_ID=:bundle_id';

COMMENT ON COLUMN SIDDA.LGL_ONT_PUB_A.PUB_ID IS '게시 ID; VARCHAR2(64 BYTE); 행 식별 키. 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_PUB_A.BNDL_ID IS '묶음 ID; VARCHAR2(84 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_PUB_A.REV_NO IS '승인 작업 판본; NUMBER(18); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_PUB_A.PKG_HASH_VAL IS '게시 JSON 해시; VARCHAR2(64 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_PUB_A.PKG_JSON_CN IS '사전 조립 게시 JSON; CLOB; 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON TABLE SIDDA.LGL_ONT_HEAD_A IS '온톨로지 현재 게시 선택. 한 행 키 BNDL_ID. 묶음별 활성 게시 ID와 변경순번을 트랜잭션으로 갱신. 게시·중지·롤백 시. 보존기간·업무오너 현장 정책 확정 필요. 원문 전체 복사·질문별 정답·수치 실행 결과는 제외. 출처: 게시본과 운영자 활성 변경. 승인과 게시/활성을 구분하며 해시와 변경순번 검사. 조회 예: SELECT * FROM SIDDA.LGL_ONT_HEAD_A WHERE BNDL_ID=:bundle_id';

COMMENT ON COLUMN SIDDA.LGL_ONT_HEAD_A.BNDL_ID IS '묶음 ID; VARCHAR2(84 BYTE); 행 식별 키. 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_HEAD_A.PUB_ID IS '활성 게시 ID; VARCHAR2(64 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_HEAD_A.CHG_SEQ_NO IS '활성 포인터 변경 순번; NUMBER(18); 표준용어·도메인·인포타입 대조와 운영 승인 별도. 0부터 시작, 활성 변경 시 증가. 과거 값으로 변경하면 거절.';

COMMENT ON TABLE SIDDA.LGL_ONT_ANC_A IS '온톨로지 게시 원문 좌표 색인. 한 행 키 PUB_ID,ANC_HASH_VAL. 문서 ID·판본·조항의 좌표해시로 현재 게시본을 찾는 색인 작성. 원문 내용은 SIDDS에서 검증. ACL은 조회자의 문서 범위로 검사. 보존기간·업무오너 현장 정책 확정 필요. 조회 예: SELECT PUB_ID FROM SIDDA.LGL_ONT_ANC_A WHERE ANC_HASH_VAL=:anchor_hash';

COMMENT ON COLUMN SIDDA.LGL_ONT_ANC_A.PUB_ID IS '게시 ID; VARCHAR2(64 BYTE); 행 식별 키. 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_ANC_A.ANC_HASH_VAL IS '원문 좌표 해시; VARCHAR2(64 BYTE); 행 식별 키. 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_ANC_A.DOC_ID IS '문서 ID; VARCHAR2(512 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_ANC_A.SRC_VER_ID IS '문서 판본; VARCHAR2(512 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

COMMENT ON COLUMN SIDDA.LGL_ONT_ANC_A.UNIT_ID IS '조항 ID; VARCHAR2(512 BYTE); 표준용어·도메인·인포타입 대조와 운영 승인 별도.';

-- 3. 생성 결과 확인: 테이블 5개와 별도 조회 인덱스 1개가 보여야 한다.
-- PK용 인덱스는 Oracle이 추가 생성한다.
SELECT OWNER, TABLE_NAME
  FROM ALL_TABLES
 WHERE OWNER = 'SIDDA'
   AND TABLE_NAME IN (
       'LGL_ONT_WORK_A', 'LGL_ONT_EVT_A', 'LGL_ONT_PUB_A',
       'LGL_ONT_HEAD_A', 'LGL_ONT_ANC_A'
   )
 ORDER BY TABLE_NAME;

SELECT OWNER, INDEX_NAME, TABLE_NAME, STATUS
  FROM ALL_INDEXES
 WHERE OWNER = 'SIDDA'
   AND INDEX_NAME = 'LGL_ONT_ANC_IX_A';

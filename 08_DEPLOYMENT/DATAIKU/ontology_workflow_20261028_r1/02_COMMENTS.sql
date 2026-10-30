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

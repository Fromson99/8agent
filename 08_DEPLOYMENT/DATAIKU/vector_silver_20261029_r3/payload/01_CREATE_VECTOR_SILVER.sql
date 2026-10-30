-- 개발 SIDDS: 신규 벡터 2테이블 / 6컬럼. 기존 원문 테이블 변경·삭제 없음.

-- Oracle native VECTOR 필요. SQL Developer/SQLcl 스크립트 실행(F5). ORDS는 / 구분 없이 블록별 실행.

-- CREATE 권한이 없으면 이 파일로 DBA에게 생성 요청. 운영 Gold 승인 DDL이 아님.

BEGIN
  EXECUTE IMMEDIATE 'CREATE TABLE SIDDS.LGL_VCTR_SET_S (PUB_ID VARCHAR2(64 BYTE) PRIMARY KEY, PAYLOAD_JSON CLOB NOT NULL, CONSTRAINT LVM_SET_JSON CHECK(PAYLOAD_JSON IS JSON WITH UNIQUE KEYS))';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE TABLE SIDDS.LGL_VCTR_ITEM_S (PUB_ID VARCHAR2(64 BYTE) NOT NULL, SEG_ID VARCHAR2(64 BYTE) NOT NULL, META_JSON CLOB NOT NULL, EMBEDDING VECTOR(*,FLOAT32) NOT NULL, CONSTRAINT LVM_ITEM_PK PRIMARY KEY(PUB_ID,SEG_ID), CONSTRAINT LVM_ITEM_FK FOREIGN KEY(PUB_ID) REFERENCES SIDDS.LGL_VCTR_SET_S(PUB_ID), CONSTRAINT LVM_ITEM_JSON CHECK(META_JSON IS JSON WITH UNIQUE KEYS))';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX SIDDS.LGL_VCTR_ITEM_IX_S ON SIDDS.LGL_VCTR_ITEM_S(PUB_ID,JSON_VALUE(META_JSON, ''$.document_id'' RETURNING VARCHAR2(512) ERROR ON ERROR),JSON_VALUE(META_JSON, ''$.source_id'' RETURNING VARCHAR2(512) ERROR ON ERROR))';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX SIDDS.LGL_VCTR_SET_ACT_IX_S ON SIDDS.LGL_VCTR_SET_S(CASE WHEN JSON_VALUE(PAYLOAD_JSON, ''$.active_revision'' RETURNING NUMBER ERROR ON ERROR NULL ON EMPTY) IS NOT NULL THEN JSON_VALUE(PAYLOAD_JSON, ''$.manifest.query_id'' RETURNING VARCHAR2(64) ERROR ON ERROR) END)';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE SIDDS.LGL_VCTR_SET_S IS '논리명(미승인 후보): 벡터게시정보. 유형: MASTER/SNAPSHOT. 행단위/PK: 게시본 1건 / PUB_ID. 질문: 어느 원문·모델의 벡터이며 완료·활성 상태인가? 포함/제외: manifest 불변, 적재 잠금·활성 순번만 변경. 상세 로그 제외. 원천: SIDDS 완료 원문·조회 게시본. 갱신: 원문 이관 완료 후 Dataiku LEGAL_04_VECTOR_SILVER_R4 실행, 전량 검증 뒤 활성화. 보유기간·관리부서: 확인 필요, 기존 게시본 자동 삭제 없음. 산식: 컬럼 설명 참조. 주의: 권한·원문 판본·모델 바인딩 유지. 개발 SIDDS.*_S, 운영 Gold 표준용어·도메인·인포타입·JSON/VECTOR 승인·DBA 생성 미완료.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SET_S.PUB_ID IS '논리명(미승인 후보): 벡터게시식별값. 불변 manifest의 SHA-256. PK. 작업 상태와 활성 순번은 hash 계산에서 제외. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SET_S.PAYLOAD_JSON IS '논리명(미승인 후보): 벡터게시메타내용. manifest에 원문/조회 판본·문서 범위·모델·차원·분할 기준, status에 BUILDING/READY, lease에 현재 적재 잠금, active_revision에 활성 순번. 상세 실행 기록은 Dataiku에 저장. 타입: CLOB; NULL: False. 표준매핑 미확인.';

COMMENT ON TABLE SIDDS.LGL_VCTR_ITEM_S IS '논리명(미승인 후보): 원문구역벡터. 유형: SNAPSHOT. 행단위/PK: 게시본 내 구간 1건 / PUB_ID, SEG_ID. 질문: 질문과 가까운 원문의 위치는 어디인가? 포함/제외: 800자/100자 겹침 파생 벡터와 원문 좌표. 원문·질문·정답 본문 제외. 원천: SIDDS 완료 원문·조회 게시본. 갱신: 원문 이관 완료 후 Dataiku LEGAL_04_VECTOR_SILVER_R4 실행, 전량 검증 뒤 활성화. 보유기간·관리부서: 확인 필요, 기존 게시본 자동 삭제 없음. 산식: 컬럼 설명 참조. 주의: 권한·원문 판본·모델 바인딩 유지. 개발 SIDDS.*_S, 운영 Gold 표준용어·도메인·인포타입·JSON/VECTOR 승인·DBA 생성 미완료.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_ITEM_S.PUB_ID IS '논리명(미승인 후보): 벡터게시식별값. 같은 모델·원문 판본으로 만든 게시본. 게시 정보 FK, SEG_ID와 복합 PK. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_ITEM_S.SEG_ID IS '논리명(미승인 후보): 벡터구역식별값. 조회 릴리스와 원문 좌표·내용 해시로 만든 SHA-256. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_ITEM_S.META_JSON IS '논리명(미승인 후보): 벡터구역메타내용. document_id·source_id·unit_id·block_id·start/end·원문/블록/입력 해시. 원문 본문은 기존 테이블 참조. 문서/원문 ID 속성에 함수 색인 적용. 타입: CLOB; NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_ITEM_S.EMBEDDING IS '논리명(미승인 후보): 임베딩벡터값. GENOS 내부 임베딩 모델의 L2 정규화 숫자 배열. 게시 정보의 모델·버전·차원과 일치해야 함. 타입: VECTOR(*,FLOAT32); NULL: False. 표준매핑 미확인.';

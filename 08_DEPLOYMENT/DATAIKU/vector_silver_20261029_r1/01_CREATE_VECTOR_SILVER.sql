-- 개발 SIDDS: 신규 벡터 3테이블 / 18컬럼. 기존 원문 테이블 변경·삭제 없음.

-- Oracle native VECTOR 필요. SQL Developer/SQLcl 스크립트 실행(F5). ORDS는 / 구분 없이 블록별 실행.

-- CREATE 권한이 없으면 이 파일로 DBA에게 생성 요청. 운영 Gold 승인 DDL이 아님.

BEGIN
  EXECUTE IMMEDIATE 'CREATE TABLE SIDDS.LGL_VCTR_PBLS_S (PUB_ID VARCHAR2(64 BYTE) PRIMARY KEY, QUERY_ID VARCHAR2(64 BYTE) NOT NULL, PROFILE_JSON CLOB NOT NULL, MANIFEST_JSON CLOB NOT NULL, STATUS VARCHAR2(16 BYTE) NOT NULL, LEASE_ID VARCHAR2(64 BYTE), EXPECTED_COUNT NUMBER, ACTUAL_COUNT NUMBER DEFAULT 0, CONSTRAINT LV_PROFILE_JSON CHECK(PROFILE_JSON IS JSON), CONSTRAINT LV_MANIFEST_JSON CHECK(MANIFEST_JSON IS JSON))';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE TABLE SIDDS.LGL_VCTR_SEG_S (PUB_ID VARCHAR2(64 BYTE) NOT NULL, SEG_ID VARCHAR2(64 BYTE) NOT NULL, DOC_ID VARCHAR2(512 BYTE) NOT NULL, SOURCE_ID VARCHAR2(512 BYTE) NOT NULL, INPUT_HASH VARCHAR2(64 BYTE) NOT NULL, META_JSON CLOB NOT NULL, EMBEDDING VECTOR(*,FLOAT32) NOT NULL, CONSTRAINT LV_SEG_PK PRIMARY KEY(PUB_ID,SEG_ID), CONSTRAINT LV_SEG_FK FOREIGN KEY(PUB_ID) REFERENCES SIDDS.LGL_VCTR_PBLS_S(PUB_ID), CONSTRAINT LV_META_JSON CHECK(META_JSON IS JSON))';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX SIDDS.LGL_VCTR_ROOT_IX_S ON SIDDS.LGL_VCTR_SEG_S(PUB_ID,DOC_ID,SOURCE_ID)';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE TABLE SIDDS.LGL_VCTR_ACT_S (QUERY_ID VARCHAR2(64 BYTE) PRIMARY KEY, PUB_ID VARCHAR2(64 BYTE) NOT NULL, REVISION NUMBER NOT NULL, CONSTRAINT LV_ACT_FK FOREIGN KEY(PUB_ID) REFERENCES SIDDS.LGL_VCTR_PBLS_S(PUB_ID))';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE <> -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE SIDDS.LGL_VCTR_PBLS_S IS '논리명(표준미확인 후보): 벡터게시정보
요약: 법률 RAG 초기 원문 검색용 파생 벡터 벡터게시정보. 행단위와PK: 게시본 1건 / PUB_ID. 질문: 어떤 원문과 임베딩 모델로 생성되었고 전량 적재가 완료되었는가? 포함·제외: 게시 명세·건수·작업 잠금 포함; 상세 실행 로그·질문 답변 제외. 원천: SIDDS의 완료된 문서·원문·조회 게시 릴리스. 갱신: 원문 이관 완료 후 Dataiku LEGAL_04_VECTOR_SILVER_R2 실행; 전량 검증 후 READY/활성 선택. 보유기간: 기존 게시본 보존; 공식 보유기간과 관리 부서는 확인 필요. 산식: 개별 컬럼 설명 참조; 금액 집계 해당 없음. 주의: 문서 권한·판본·모델/가중치/차원 일치 필수, 게시본 간 중복 집계 금지. 개발: SIDDS.*_S. 운영 Gold 후보이며 표준단어·도메인·인포타입·JSON/VECTOR 승인 및 DBA 생성은 미완료.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.PUB_ID IS '논리명(미승인 후보): 벡터게시식별값. 게시 manifest의 canonical JSON SHA-256. 소문자 16진수 64자리. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.QUERY_ID IS '논리명(미승인 후보): 조회게시식별값. 원천 COMPLETE 조회 릴리스의 SHA-256 식별값. 원문 판본과 결속. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.PROFILE_JSON IS '논리명(미승인 후보): 임베딩설정내용. 모델명·불변 revision·차원·접속점 해시·800자 분할·100자 겹침·l2·COSINE JSON. 인증키 제외. 타입: CLOB; NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.MANIFEST_JSON IS '논리명(미승인 후보): 벡터게시명세내용. 원천·조회 릴리스·데이터세대·문서범위·설정·분할 버전을 담은 불변 JSON. 타입: CLOB; NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.STATUS IS '논리명(미승인 후보): 벡터게시상태코드. BUILDING 또는 READY. 실패 세부 이력은 Dataiku에 보관하며 불완전 게시본은 BUILDING으로 유지. 타입: VARCHAR2(16 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.LEASE_ID IS '논리명(미승인 후보): 적재잠금식별값. 동시 적재 차단용 임시 난수. 현재 생성값은 48자리 16진수. 완료·정상 종료 시 NULL. 타입: VARCHAR2(64 BYTE); NULL: True. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.EXPECTED_COUNT IS '논리명(미승인 후보): 예정벡터건수. 검증 완료 시 원천 구역 총건수. BUILDING에서는 NULL 가능. 정수 건수. 타입: NUMBER; NULL: True. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_PBLS_S.ACTUAL_COUNT IS '논리명(미승인 후보): 저장벡터건수. 검증 완료된 벡터 행 수. DEFAULT 0. READY 전 COUNT(*)와 대조. 기존 DDL의 nullable 보존. 타입: NUMBER; NULL: True. 표준매핑 미확인.';

COMMENT ON TABLE SIDDS.LGL_VCTR_SEG_S IS '논리명(표준미확인 후보): 원문구역벡터
요약: 법률 RAG 초기 원문 검색용 파생 벡터 원문구역벡터. 행단위와PK: 게시본 내 원문 구역 1건 / PUB_ID, SEG_ID. 질문: 질문과 의미가 가까운 원문 조항의 좌표는 무엇인가? 포함·제외: 제목과 원문 블록을 800자·100자 겹침으로 분할한 파생 벡터. 원문·정답 본문은 제외. 원천: SIDDS의 완료된 문서·원문·조회 게시 릴리스. 갱신: 원문 이관 완료 후 Dataiku LEGAL_04_VECTOR_SILVER_R2 실행; 전량 검증 후 READY/활성 선택. 보유기간: 기존 게시본 보존; 공식 보유기간과 관리 부서는 확인 필요. 산식: 개별 컬럼 설명 참조; 금액 집계 해당 없음. 주의: 문서 권한·판본·모델/가중치/차원 일치 필수, 게시본 간 중복 집계 금지. 개발: SIDDS.*_S. 운영 Gold 후보이며 표준단어·도메인·인포타입·JSON/VECTOR 승인 및 DBA 생성은 미완료.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SEG_S.PUB_ID IS '논리명(미승인 후보): 벡터게시식별값. 게시정보 PUB_ID 외래키. SEG_ID와 복합 PK. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SEG_S.SEG_ID IS '논리명(미승인 후보): 벡터구역식별값. 조회 릴리스와 원문 좌표·내용 해시 메타의 canonical JSON SHA-256. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SEG_S.DOC_ID IS '논리명(미승인 후보): 문서식별값. 해당 판본의 원천 문서 식별값. 512바이트 이내. 문자열·선행 0 유지. 타입: VARCHAR2(512 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SEG_S.SOURCE_ID IS '논리명(미승인 후보): 원문위치식별값. 조회 릴리스의 원문 구조 항목 식별값. 본문·부칙·별표 등 분리된 좌표 유지. 타입: VARCHAR2(512 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SEG_S.INPUT_HASH IS '논리명(미승인 후보): 임베딩입력해시값. 실제 임베딩 입력(문서명·표제·구역본문)의 digest(str), 즉 canonical JSON 문자열 SHA-256. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SEG_S.META_JSON IS '논리명(미승인 후보): 벡터구역메타내용. 문서·구조·블록 ID, start/end 문자좌표, 원문·블록·입력 해시 JSON. 원문 본문은 원천 테이블 참조. 타입: CLOB; NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_SEG_S.EMBEDDING IS '논리명(미승인 후보): 임베딩벡터값. GENOS 내부 모델이 생성한 숫자 배열을 L2 정규화. 차원은 게시 PROFILE_JSON으로 검증. 모델 간 혼용 금지. 타입: VECTOR(*,FLOAT32); NULL: False. 표준매핑 미확인.';

COMMENT ON TABLE SIDDS.LGL_VCTR_ACT_S IS '논리명(표준미확인 후보): 활성벡터게시정보
요약: 법률 RAG 초기 원문 검색용 파생 벡터 활성벡터게시정보. 행단위와PK: 조회 릴리스 1건 / QUERY_ID. 질문: 해당 원문 조회 릴리스에 사용할 READY 벡터 게시본은 무엇인가? 포함·제외: 현재 벡터 선택 정보. 원문 조회채널 변경·과거 전환 이력은 제외; 이력은 Dataiku 보관. 원천: SIDDS의 완료된 문서·원문·조회 게시 릴리스. 갱신: 원문 이관 완료 후 Dataiku LEGAL_04_VECTOR_SILVER_R2 실행; 전량 검증 후 READY/활성 선택. 보유기간: 기존 게시본 보존; 공식 보유기간과 관리 부서는 확인 필요. 산식: 개별 컬럼 설명 참조; 금액 집계 해당 없음. 주의: 문서 권한·판본·모델/가중치/차원 일치 필수, 게시본 간 중복 집계 금지. 개발: SIDDS.*_S. 운영 Gold 후보이며 표준단어·도메인·인포타입·JSON/VECTOR 승인 및 DBA 생성은 미완료.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_ACT_S.QUERY_ID IS '논리명(미승인 후보): 조회게시식별값. 조회 릴리스마다 한 행. 원문 조회채널 자체를 변경하는 테이블은 아님. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_ACT_S.PUB_ID IS '논리명(미승인 후보): 활성벡터게시식별값. 동일 QUERY_ID의 READY 게시본만 선택. 게시정보 PUB_ID 외래키. 타입: VARCHAR2(64 BYTE); NULL: False. 표준매핑 미확인.';

COMMENT ON COLUMN SIDDS.LGL_VCTR_ACT_S.REVISION IS '논리명(미승인 후보): 활성버전순번. 최초 1, 교체 때 1 증가. 현재 값 조건부 UPDATE로 동시 교체 충돌 차단. 타입: NUMBER; NULL: False. 표준매핑 미확인.';

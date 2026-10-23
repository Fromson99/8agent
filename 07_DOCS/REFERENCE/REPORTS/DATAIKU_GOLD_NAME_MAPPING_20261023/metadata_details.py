"""Evidence-based registration descriptions for the existing nine-table design."""

RULES = '00_SYSTEM/ARCHITECTURE.md#dataiku-gold-schema-convention'
WORKBOOK = '07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/TABLE_SCHEMA_WORKBOOK.md'
IO = '02_BACKEND/semantic_runtime/oracle_dp_io.py'
MIG = '02_BACKEND/lawrag/pipeline/oracle_migration.py'
ASSET = '02_BACKEND/semantic_runtime/oracle_dp_assets.py'
CAT = '02_BACKEND/semantic_runtime/oracle_query_catalog.py'
STATE = '02_BACKEND/semantic_runtime/oracle_query_state.py'

# Business meaning, naming rationale, classification rationale, storage rationale,
# completion boundary, and a bounded example matching the described business question.
TABLE_DETAILS = {
 'document': (
  '검증한 데이터 구축 세대 안에서 내규·외규 문서의 식별값, 문서명, 원본자료 해시와 원문 객체 정보를 보존한다. 법령 개정 판본과 데이터 구축 세대는 구분한다.',
  '기존 SRC_DOCUMENT의 역할을 문서 판본·출처 관리로 설명한다. LGL은 법규 업무, DOC는 문서, VER는 판본을 뜻하는 약어 후보이며 승인 표준단어 대조가 필요하다.',
  'SNAPSHOT 후보: 데이터 구축 세대별 문서 행을 불변 적재한다. 같은 문서가 다른 세대에 반복돼도 최신 한 행으로 덮어쓰지 않는다.',
  '원문과 출처를 조회하는 지식 정본이므로 Gold 지식 후보로 선정한다.',
  '세대·문서 PK별 메타데이터를 다시 읽어 원천과 대조한다. 테이블 일부 적재만으로 전체 조회 릴리스 완료를 선언하지 않는다.',
  'SELECT DOC_ID, DOC_NM, SRC_DATA_HASH_VAL FROM <승인스키마>.LGL_DOC_VER WHERE DATA_VER_ID=:data_ver_id AND DOC_ID=:doc_id', MIG+'; '+IO),
 'source_unit': (
  '문서의 편·장·절·관·조·항·호·목 등 구조 단위와 상위 단위 관계를 데이터 세대·문서 범위 안에서 보존한다.',
  'SOURCE_UNIT을 문서 안의 구조 단위로 명확히 표현한다. DOC와 UNIT은 약어 후보이며 특정 조항 유형 하나로 범위를 제한하지 않는다.',
  'SNAPSHOT 후보: 동일 세대·문서의 구조와 부모 관계를 고정한다. 이후 변경은 다른 데이터 세대로 구분한다.',
  '조항 탐색과 원문 범위 확인에 직접 사용하므로 Gold 지식 후보로 선정한다.',
  'PK별 구조 JSON과 부모값을 원천과 대조한다. 부모 관계의 정합성은 별도 문서·세대 검증으로 확인한다.',
  'SELECT UNIT_ID, PRNT_UNIT_ID, UNIT_JSON_CN FROM <승인스키마>.LGL_DOC_UNIT WHERE DATA_VER_ID=:data_ver_id AND DOC_ID=:doc_id AND UNIT_ID=:unit_id', MIG+'; '+IO),
 'block_payload': (
  '인용·대사에 사용하는 정확한 원문 블록을 문서와 구조 단위에 연결하고, 원본자료 해시 및 JSON 본문 중복 생략 표시를 함께 보존한다.',
  'PAYLOAD 같은 구현 용어보다 문서 본문 블록이라는 행 단위를 드러낸다. DOC/BLK는 승인 전 약어 후보다.',
  'SNAPSHOT 후보: 세대·문서·블록 키별 원문을 고정하고 기존 행과 다른 본문을 덮어쓰지 않는다.',
  '실제 인용·검토의 근거 본문이므로 Gold 지식 후보로 선정한다.',
  '블록 PK별 TEXT·SOURCE_JSON·생략 표시·해시를 다시 읽어 원천과 대조한다. 빈 CLOB과 NULL을 구분한다.',
  'SELECT BLK_ID, UNIT_ID, BLK_TXT_CN, JSON_TXT_OMIT_YN FROM <승인스키마>.LGL_DOC_BLK WHERE DATA_VER_ID=:data_ver_id AND DOC_ID=:doc_id AND BLK_ID=:blk_id', MIG+'; '+IO),
 'query_row': (
  '문서 구조·용어·정의·참조·검색·무결성 등 릴리스에 선언된 여러 논리 데이터를 조건별 조회 가능한 행으로 투영해 저장한다.',
  'QUERY_ROW를 지식 조회용 행으로 표현한다. SRCH는 검색·조회, ROW는 투영 행을 뜻하는 후보다. 한 종류의 개념이나 관계만 저장하는 테이블로 이름을 좁히지 않는다.',
  'SNAPSHOT 후보: 완료 조회 릴리스와 종류·행 ID에 결속된 불변 투영이다. 요청별 실행 이력 테이블이 아니다.',
  '원문·용어·관계의 직접 조회 데이터이므로 Gold 지식 후보다. KIND별 의미는 동일 릴리스 manifest에 연결한다.',
  '조회 행의 PK·내용 hash·본문·조회키를 대조하고 완료 manifest의 종류별 건수를 확인한다. 전체 완료 뒤 별도 활성화를 수행한다.',
  'SELECT ROW_ID, ROW_JSON_CN FROM <승인스키마>.LGL_SRCH_ROW WHERE SRCH_PBLS_ID=:srch_pbls_id AND ROW_KIND_CD=:row_kind_cd AND SRCH_KEY_ID=:srch_key_id AND ROWNUM<=20', CAT),
 'source_release': (
  '구조화 원문 세대와 navigation·fulltext·glossary 등 자산, 검색 선택 정보를 하나의 완료 게시 명세에 결속해 보존한다.',
  '광범위한 RAG_RELEASE 대신 원문과 자산 게시라는 책임을 표현한다. SRC/PBLS는 원문/게시 약어 후보이며 조회 게시와 구분한다.',
  'SNAPSHOT 후보: 완료 manifest 내용에 따른 식별값으로 불변 게시본을 관리한다. CREATED_AT은 DB 등록시각이다.',
  '직접 조회가 원문 세대를 검증할 때 필요한 지원 정보이므로 Gold 지원 후보다. 실제 Gold 등록 범위는 거버넌스 확인이 필요하다.',
  '원문·자산 검증 뒤 완료 명세를 저장하고 release hash와 저장 내용을 다시 확인한다. 자산 조각 테이블 자체를 지식 조회 대상으로 사용하지 않는다.',
  'SELECT SRC_PBLS_ID, DATA_VER_ID, PBLS_JSON_CN, REG_DTM FROM <승인스키마>.LGL_SRC_PBLS WHERE SRC_PBLS_ID=:src_pbls_id', ASSET),
 'query_release': (
  '조회 가능한 릴리스의 원문 게시본, 데이터 세대, 투영 종류·건수·hash 등을 manifest로 고정해 요청 전체가 같은 데이터 조합을 사용하도록 한다.',
  '원문 게시와 별도의 조회 게시임을 SRCH_PBLS로 표현한다. 기존 release 식별값의 의미·생성법은 유지한다.',
  'SNAPSHOT 후보: 완료 조회 manifest를 불변 보존하며 새 내용은 새로운 조회 게시 ID로 구분한다.',
  '지식 조회의 판본 결속에 필요하므로 Gold 지원 후보다. 등록 대상 선정과 운영 승인을 구분한다.',
  '조회 데이터의 검증 후 완료 manifest를 저장하고 hash·원문 게시 참조를 다시 읽어 확인한다.',
  'SELECT SRCH_PBLS_ID, MNFST_JSON_CN FROM <승인스키마>.LGL_SRCH_PBLS WHERE SRCH_PBLS_ID=:srch_pbls_id', CAT),
 'query_active': (
  '조회 채널이 선택한 완료 조회 게시본과 변경 순번을 저장한다. 동시 변경 시 이전 선택과 revision을 비교해 충돌을 방지한다.',
  'ACTIVE라는 상태 표현 대신 채널별 조회 게시 선택이라는 책임을 표현한다. SRCH_CHNL은 승인 전 약어 후보다.',
  'MASTER 후보: 채널당 현재 선택 한 행을 관리한다. 과거 선택 이력 전체를 이 테이블이 저장하는 것은 아니다.',
  '지식 게시 선택을 위한 Gold 지원 후보다. 고정 release 모드는 생략 가능하며 기본 채널 모드의 의존성을 유지한다.',
  '완료 조회 release를 확인한 뒤 이전 release·revision 조건으로 변경하고 새 revision·선택값을 다시 읽어 확인한다.',
  'SELECT CHNL_NM, SRCH_PBLS_ID, CHG_SEQ_NO FROM <승인스키마>.LGL_SRCH_CHNL WHERE CHNL_NM=:chnl_nm', CAT),
 'query_state': (
  '범위별 요청·세션의 작은 상태 객체와 변경 순번·내용 hash를 저장하는 Oracle 상태 포트다. 모든 기존 실행 이력이 이 포트로 이행됐다는 뜻은 아니다.',
  'QUERY_STATE를 에이전트 실행 상태로 명확히 표현한다. EXEC/ST는 실행/상태 약어 후보이며 지식 원문과 구분한다.',
  'MASTER 후보: 범위·상태키당 현재 상태와 revision을 갱신한다. 이 테이블 단독으로 과거 상태 전체 이력을 보존하지 않는다.',
  '질의·실행 상태 책임이므로 Agent 대상이다. Gold 등록 제외 제안이며 기존 테이블 삭제를 뜻하지 않는다.',
  '기대 revision으로 쓰기 후 scope·key·revision·value hash를 재조회한다. 응답 불명은 성공으로 확정하지 않는다.',
  'SELECT ST_KEY_ID, CHG_SEQ_NO, ST_HASH_VAL FROM <승인스키마>.LGL_EXEC_ST WHERE SCOPE_HASH_VAL=:scope_hash_val AND ST_KEY_ID=:st_key_id', STATE),
 'asset_part': (
  '기존 색인·용어집 등 파일 자산을 분할해 압축·Base64 문자열과 조각 크기·hash로 보관한다. 직접 지식 조회 경로의 원문 테이블이 아니다.',
  'ASSET_PART를 파일 분할 보관이라는 업무 대상으로 표현한다. FILE/PART는 승인 전 약어 후보다.',
  'SNAPSHOT 후보: 전체 파일 hash·분할 순번별 불변 조각을 저장한다. 같은 파일 조각은 재사용하고 다른 바이트로 덮어쓰지 않는다.',
  '이관·보관 영역으로 분류한다. 기존 게시 검증에서 사용하므로 Gold 제외 제안을 곧바로 제거로 해석하지 않는다.',
  '압축 해제한 조각 크기·조각 hash와 전체 자산 hash를 대조한다. 조각 하나의 적재 완료와 전체 게시 완료는 구분한다.',
  'SELECT PART_SEQ_NO, ORG_BYTE_CNT, PART_HASH_VAL FROM (SELECT PART_SEQ_NO, ORG_BYTE_CNT, PART_HASH_VAL FROM <승인스키마>.LGL_FILE_PART WHERE FILE_HASH_VAL=:file_hash_val ORDER BY PART_SEQ_NO) WHERE ROWNUM<=20', ASSET),
}

# One explanation per existing source column; table-specific cases are resolved below.
COLUMN_DETAILS = {
 'DATASET_VERSION': ('동일한 구조화 원문·목차·용어 결속을 재현하기 위한 데이터 구축 세대 식별값이다. 법령 시행일이나 개정번호와 다르다.',
                     '이 경로의 생성값은 manifest 원시 바이트 SHA-256의 64자리 소문자 16진 문자열. 원문 writer는 문자열 길이·NULL/키 계약을 별도로 검사한다.',
                     'sha256(선택 generation/manifest.json 원시 바이트).hexdigest(); JSON 재직렬화 후 hash로 대체하지 않음.',
                     '판본을 고정하는 식별값임을 DATA_VER_ID로 표현한다. 숫자 버전으로 변환하지 않는다.', MIG+':source_binding'),
 'DOCUMENT_ID': ('세대 안에서 원문 문서를 식별하고 원문·구조·조회 행을 연결하는 값이다.',
                 '값이 있으면 비어 있지 않은 문자열, UTF-8 512바이트 이내. 원문 테이블은 PK 필수; 조회 투영의 문서 비소속 행은 NULL 허용.',
                 '해당 없음: 구조화 원문의 document_id를 보존한다. 조회키 hash로 치환하지 않음.',
                 'DOCUMENT를 DOC로 축약하고 기존 ID 계약을 유지한다. ID 예외는 표준 승인 확인 대상이다.', IO+':validate_row; '+CAT+':record/Records.page'),
 'NAME': ('원문 문서의 표시 이름이다. 문서 ID와 구분하고 법령·내규 제목을 있는 그대로 보존한다.',
          '문자열·빈 CLOB·NULL. 현행 원문 전송 상한은 UTF-8 64MiB이며 DB나 표준 인포타입의 최대 길이를 뜻하지 않음.',
          '해당 없음: 구조화 document.name을 보존한다.',
          '일반 NAME 대신 문서명을 나타내는 DOC_NM을 사용한다.', IO+':validate_row/bind_row'),
 'SOURCE_ARTIFACT_SHA256': ('구조화 결과가 참조하는 원본 출처 자료의 무결성 hash다. 구조화 본문 문자열 자체의 hash와 구분한다.',
                           '원본 자료 SHA-256 계약의 문자열 또는 NULL. 원문 이관 검사는 비어 있지 않은 문자열·64바이트 이하만 강제하므로 16진 형식 검증이 항상 수행됐다고 보지 않음.',
                           '원천이 기록한 source_artifact_sha256을 그대로 이관; 여기서 다른 대상의 hash를 새로 계산하지 않음.',
                           '원본자료 해시값이라는 의미를 SRC_DATA_HASH_VAL로 드러낸다.', MIG+':source_batch; '+IO+':validate_row'),
 'SOURCE_JSON': ('해당 구조화 원문 객체의 JSON 직렬화 정보를 보존한다.',
                 '문자열·빈 CLOB·NULL; 원문 전송 상한 UTF-8 64MiB. 현행 원문 DDL에는 IS JSON CHECK가 없고 원문 소비자의 별도 계약을 따른다.',
                 '해당 없음: 원천 SQLite json 값을 그대로 이관한다. 내부 JSON 키·원문 좌표·값을 개명하지 않음.',
                 '원천 객체 종류가 문서·구조 단위·블록 중 무엇인지 컬럼명에서 구분한다.', MIG+':source_batch; '+IO),
 'UNIT_ID': ('문서 내부의 구조 단위 식별값이다. 조문 번호 문자열만으로 전 문서에서 유일한 것으로 해석하지 않는다.',
             '값이 있으면 비어 있지 않은 문자열, UTF-8 512바이트 이내. 구조 단위 테이블에서는 PK 필수, 본문 블록에서는 NULL 허용.',
             '해당 없음: 원문의 unit_id를 데이터 세대·문서 범위와 함께 보존한다.',
             '기존 UNIT_ID가 구조 단위를 나타내므로 유지한다. 한글 논리명에 구조 의미를 명시한다.', IO+':COLUMNS/KEYS/validate_row'),
 'PARENT_ID': ('같은 데이터 세대·문서에서 상위 구조 단위를 가리키는 값이다. 루트 등 상위 관계가 없는 경우를 구분한다.',
               'NULL 또는 비어 있지 않은 문자열, UTF-8 512바이트 이내. 부모의 실재·같은 문서 여부는 별도 구조 검사 대상이며 현재 물리 FK 없음.',
               '해당 없음: 원문의 parent_id를 보존한다.',
               '부모가 문서 구조 단위라는 점을 PRNT_UNIT_ID에 명시한다.', IO+':COLUMNS/validate_row'),
 'BLOCK_ID': ('정확한 원문을 담는 블록의 식별값으로 데이터 세대·문서와 함께 PK를 구성한다.',
              '비어 있지 않은 문자열, UTF-8 512바이트 이내. 모양이 숫자여도 문자열 계약을 보존한다.',
              '해당 없음: 원문의 block_id를 보존한다.',
              '본문 블록이라는 의미를 BLK_ID로 표현한다. 기존 값과 순서 해석은 바꾸지 않는다.', IO+':KEYS/validate_row'),
 'TEXT': ('인용·대사에서 실제로 읽는 원문 본문이다. 생성된 요약이나 답변을 저장하는 필드가 아니다.',
          '문자열·빈 CLOB·NULL; 현행 전송 상한 UTF-8 64MiB. NULL과 길이 0 CLOB을 구분해 보존한다.',
          '해당 없음: 원문 block_payload.text를 그대로 이관한다.',
          '일반 TEXT 대신 블록 본문 내용이라는 BLK_TXT_CN을 사용한다.', IO+':validate_row/bind_row/read_rows'),
 'JSON_TEXT_ELIDED': ('블록 JSON에서 중복 본문을 생략해 별도 TEXT 값으로 복원해야 하는지를 표시한다. 문서의 원문이 없다는 표시가 아니다.',
                      '코드 허용값 0, 1, NULL. 1은 JSON 본문 생략·별도 본문 사용, 0은 미생략. NULL은 0으로 추정하지 않고 보존. 현재 DDL은 값 CHECK 없음.',
                      '해당 없음: 원천의 json_text_elided 값을 보존한다.',
                      'JSON 본문의 생략 여부라는 의미를 명시한다. 후보 YN 도메인이 문자형이면 별도 변환 승인 필요.', IO+':validate_row'),
 'KIND': ('조회 행의 논리 종류로, 같은 릴리스 manifest의 tables에 선언된 투영 스키마를 선택한다.',
          '게시기 패턴 [a-z][a-z0-9_.]{0,63}; 실제 조회 때 완료 manifest의 tables에 있는 종류만 허용. 전사 숫자 코드로 자동 재번호화하지 않음.',
          '해당 없음: 게시기가 지정한 투영 종류 문자열을 사용한다.',
          'KIND가 조회 행 종류임을 ROW_KIND_CD로 명시한다.', CAT+':record/Records.page'),
 'ROW_ID': ('한 조회 종류 안에서 행을 재현하고 중복을 판별하는 key의 digest다.',
            '64자리 소문자 16진 hash, NULL 불가. 단독 전역 키가 아니라 release·kind와 함께 PK를 이룬다.',
            'digest(key): JSON 정규 직렬화(키 정렬·고정 구분자·NaN 금지)의 UTF-8 SHA-256.',
            '기존 ROW_ID 유지. 한글 설명에 조회 행과 digest 의미를 보충한다.', CAT+':record/insert_records; '+IO+':canonical/digest'),
 'LOOKUP_ID': ('표면형·논리 ID 등 후보를 빠르게 찾는 보조 조회키다. 전체 논리 값은 JSON에 보존한다.',
               'NULL 또는 비어 있지 않은 UTF-8 512바이트 이하 문자열. 긴 보조키는 호출자가 lookup_key()를 적용한 경우 sha256: 접두 digest로 인코딩한다.',
               'lookup_key(v)는 NULL/512바이트 이하 v를 유지, 초과 시 sha256: + digest(v). 원문 DOCUMENT_ID에는 이 인코딩을 적용하지 않음.',
               '검색용 키임을 SRCH_KEY_ID로 표시한다. 원문 문서 식별자와 구분한다.', CAT+':lookup_key/record'),
 'OWNER_ID': ('조회 투영 종류별 소유 단위·정의·참조 등을 찾는 보조키다. DB owner나 사용자 계정 ID가 아니다.',
              'NULL 또는 비어 있지 않은 UTF-8 512바이트 이하 문자열. 전체 의미는 KIND·manifest와 원본 JSON으로 해석한다.',
              '해당 없음: 종류별 게시기가 정한 owner_id; 긴 보조키 인코딩을 사용한 경우 lookup_key 계약 유지.',
              '스키마 owner와 혼동하지 않도록 소유 참조 키 OWNR_REF_ID로 표현한다.', CAT+':lookup_key/record'),
 'TARGET_ID': ('조회 투영 종류별 관계 대상 또는 부모를 찾는 보조키다.',
               'NULL 또는 비어 있지 않은 UTF-8 512바이트 이하 문자열. 모든 종류에서 같은 엔터티를 가리킨다고 보지 않음.',
               '해당 없음: 종류별 게시기의 target_id; 보조키 인코딩 사용 여부는 해당 게시 계약 유지.',
               '참조 대상 키라는 역할을 TGT_REF_ID로 표현한다.', CAT+':lookup_key/record'),
 'ROW_SHA256': ('조회 행의 종류·키·문서 및 보조키·JSON 값이 변하지 않았는지 확인하는 digest다.',
                '64자리 소문자 16진 hash, NULL 불가. JSON 본문만의 hash로 대체할 수 없음.',
                'digest({kind,row_id,document_id,lookup_id,owner_id,target_id,value}); sha256 필드 자체는 제외.',
                '조회 행 전체의 해시값임을 ROW_HASH_VAL로 표현한다.', CAT+':record/insert_records'),
 'CREATED_AT': ('원문 게시 행이 DB에 등록된 시각이다. 문서 작성일·법령 시행일·GENOS 처리 시작시각과 다르다.',
                'TIMESTAMP WITH TIME ZONE, NULL 불가. 기본값 SYSTIMESTAMP; 시간대 정보 보존.',
                '신규 INSERT에서 생략 시 DB SYSTIMESTAMP. 기존 행 이행은 원 등록시각 보존 대상으로 설계.',
                '등록시각을 날짜와 시간이 포함된 일시 도메인 REG_DTM으로 표현한다.', '08_DEPLOYMENT/DATAIKU/legal_oracle_all_tables_20261019_r1/LEGAL_ORACLE_ALL_9_TABLES_20261019_R1.sql'),
 'CHANNEL': ('요청 시작 시 사용할 완료 조회 릴리스를 선택하는 게시 채널 이름이다.',
             '패턴 [a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}, NULL 불가. 실제 채널 목록은 환경 설정으로 별도 확정.',
             '해당 없음: 명시한 게시 채널명을 저장한다.',
             '채널을 이름 도메인으로 표현한 CHNL_NM 후보다.', CAT+':channel_name/activate'),
 'REVISION': ('같은 채널 또는 상태 객체의 동시 수정 충돌을 확인하는 변경 순번이다.',
              'NUMBER(18), 정수 1 이상, NULL 불가. 생성 1, 성공 변경 때 1 증가. 원문 개정번호와 다름.',
              '새 revision = expected_revision + 1. 기대 revision과 기존 값 확인 후 CAS 갱신.',
              'REVISION을 변경순번 CHG_SEQ_NO로 표현해 법령 판본과 구분한다.', CAT+':activate; '+STATE+':State.put'),
 'SCOPE_HASH': ('상태 객체가 속한 범위를 결속하는 hash다. hash 값 자체로 접근권한이 승인되지는 않는다.',
                '64자리 소문자 16진 hash, NULL 불가. 실제 입력 범위 구성은 상태 포트 호출자의 계약으로 고정.',
                '해당 없음: 호출자가 제공한 scope_hash를 pin 검증 후 보존; 포트가 임의 사용자 범위를 생성하지 않음.',
                '범위를 결속하는 해시값임을 SCOPE_HASH_VAL로 표시한다.', STATE+':State.__init__'),
 'STATE_KEY': ('같은 범위 안의 개별 상태 객체를 찾는 키다.',
               '패턴 [A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}, NULL 불가. 허용 구체 키 목록은 소비자 계약에 따름.',
               '해당 없음: 상태 소비자가 지정한 key를 보존한다.',
               '상태키 ID의 역할을 ST_KEY_ID로 나타낸다.', STATE+':State._binds'),
 'VALUE_SHA256': ('상태의 범위·키·revision·내용이 하나의 갱신에 속하는지 확인하는 hash다.',
                  '64자리 소문자 16진 hash, NULL 불가. VALUE_JSON만 hash한 값과 다름.',
                  'digest({scope_hash,key,revision,value}). 읽기 시 같은 조합으로 재계산한다.',
                  '상태 내용 결속 해시임을 ST_HASH_VAL로 나타낸다.', STATE+':State.read/put'),
 'ASSET_SHA256': ('조각으로 나누기 전 전체 파일 자산의 SHA-256이다. 여러 조각을 같은 원본 파일로 묶는 키다.',
                  '생성 계약상 64자리 소문자 16진 SHA-256, NULL 불가. DB DDL은 VARCHAR2(64 BYTE)·PK를 강제하며 16진 CHECK는 없음.',
                  'sha256(전체 원본 파일 바이트).hexdigest(); 조각 해시와 구분.',
                  '전체 파일 해시값 FILE_HASH_VAL로 조각 해시와 구분한다.', ASSET+':inventory'),
 'PART_NO': ('전체 파일을 순서대로 나눈 조각의 0 기반 순번이다.',
             'NUMBER(12) 정수, 0 이상, NULL 불가. 전체 파일 hash와 함께 PK.',
             'PART_BYTES=1,048,576바이트 단위로 분할할 때의 0 기반 순번. 번호 기준을 1로 바꾸지 않음.',
             '임의 업무 번호가 아닌 분할 순번 PART_SEQ_NO로 표시한다.', ASSET+'; 02_BACKEND/lawrag/pipeline/oracle_publish.py'),
 'RAW_BYTES': ('압축·Base64 처리 전 원본 조각의 바이트 수다. 인코딩된 문자열 길이가 아니다.',
               'NUMBER(12), 정수 1~1,048,576, NULL 불가. DDL CHECK와 읽기 후 실제 바이트 길이 대조.',
               'len(raw_part_bytes).',
               '원본 바이트 수 ORG_BYTE_CNT로 단위를 이름에 명시한다.', ASSET+':put_part/get_part'),
 'PART_SHA256': ('압축 전 원본 조각의 SHA-256이다. 전체 파일 hash와 별개로 전송·보관 조각을 검증한다.',
                 '생성 계약상 64자리 소문자 16진 SHA-256, NULL 불가. get_part에서 실제 원본 조각 hash와 대조.',
                 'sha256(raw_part_bytes).hexdigest().',
                 '분할 조각의 해시값 PART_HASH_VAL로 전체 파일 해시와 구분한다.', ASSET+':put_part/get_part'),
 'DATA_B64': ('원본 파일 조각을 zlib 압축한 바이트의 Base64 문자열이다. 사람이 읽는 문서 본문이 아니다.',
              'NULL 불가 CLOB. Base64·zlib 형식 및 복원 크기·hash를 검사; 복원 결과는 PART_BYTES 이하여야 함.',
              'base64.b64encode(zlib.compress(raw_part,6)).decode(); 역변환 후 RAW_BYTES·PART_SHA256 검증.',
              '분할된 인코딩 내용 PART_B64_CN으로 일반 데이터·원문 텍스트와 구분한다.', ASSET+':put_part/get_part'),
}

def column_metadata(table, name, item, existing):
    if name == 'RELEASE_ID':
        if table == 'source_release':
            values=('완료 원문·자산 게시 명세를 불변 식별하는 값이다.', '64자리 소문자 16진 digest; NULL 불가.',
                    'digest(원문·자산 완료 release 객체). 직렬화 저장 형식과 논리 digest 계산을 구분.',
                    '원문 게시 SRC_PBLS_ID로 조회 게시 식별값과 구분한다.', ASSET+':get_release/put_release')
        else:
            values=('완료 조회 manifest를 식별한다. 조회 행과 채널이 어떤 조회 게시본에 속하는지 연결한다.',
                    '64자리 소문자 16진 digest; NULL 불가. 채널의 값은 조회 게시 테이블을 참조한다.',
                    '조회 게시 생성 시 digest(완료 query manifest). 조회 행·채널은 그 값을 참조·보존한다.',
                    '조회 게시 SRCH_PBLS_ID로 원문 게시와 구분하고 참조 컬럼 이름을 맞춘다.', CAT+':read_release/insert_records/activate')
    elif name in {'VALUE_JSON','MANIFEST_JSON','RELEASE_JSON'}:
        if table=='query_state':
            values=('소비자가 정한 작은 실행 상태 객체의 JSON이다. 질문 답변을 재사용 지식으로 승인하는 필드가 아니다.',
                    'NULL 불가, DDL IS JSON. json_body 직렬화 결과 상한 8MiB; 소비자의 추가 상태 스키마·예산 검증 필요.',
                    'json_body(value): ASCII JSON·키 정렬·고정 구분자·NaN 금지. 상태 hash는 scope/key/revision까지 포함.',
                    '상태 JSON 내용 ST_JSON_CN으로 지식 조회 행과 구분한다.', STATE+':State.put/read; '+CAT+':json_body')
        elif table=='query_row':
            values=('KIND와 완료 manifest가 정의하는 조회 행의 논리 값 JSON이다. 원문 좌표·용어·정의 등 종류별 구조가 다르다.',
                    'NULL 불가, DDL IS JSON. 게시기 json_body의 직렬화 상한 8MiB; KIND별 의미 검증은 별도.',
                    'json_body(value): ASCII JSON·키 정렬·고정 구분자·NaN 금지. 내부 필드명은 개명하지 않음.',
                    '조회 행 JSON 내용 ROW_JSON_CN으로 상태 객체와 구분한다.', CAT+':json_body/record/insert_records')
        elif table=='query_release':
            values=('완료 조회 릴리스의 원문 게시 참조·데이터 세대·종류별 투영·검증 정보를 담은 manifest다.',
                    'NULL 불가 JSON, DDL IS JSON. 코드가 schema_version·COMPLETE·manifest digest와 참조 pin을 검증.',
                    '완료 조회 manifest를 직렬화한다. 집계 산식은 해당 없음; 조회 릴리스 ID는 해당 객체의 digest.',
                    '명세 JSON 내용 MNFST_JSON_CN으로 일반 조회 행 JSON과 구분한다.', CAT+':read_release')
        else:
            values=('완료 원문 세대·자산 inventory·검색 선택 등에 대한 원문 게시 명세다.',
                    'NULL 불가 JSON 문자열. 현재 DDL에는 IS JSON CHECK 없음; get_release가 JSON·schema_version·COMPLETE·digest 확인.',
                    'ASCII JSON·키 정렬·고정 구분자로 완료 release 객체 직렬화. 집계 산식 해당 없음.',
                    '원문 게시 JSON 내용 PBLS_JSON_CN으로 의미를 드러낸다.', ASSET+':get_release/put_release')
    else:
        values=COLUMN_DETAILS[name]
    meaning, allowed, formula, reason, evidence = values
    if name=='SOURCE_JSON':
        owner={'document':'문서 메타정보','source_unit':'문서 구조 단위','block_payload':'본문 블록'}[table]
        meaning=owner+' 원천 객체의 JSON 직렬화 값이다. '+('JSON 본문 생략 여부는 별도 표시와 TEXT를 함께 확인한다.' if table=='block_payload' else '기존 필드·판본·출처 정보를 그대로 보존한다.')
    if name=='DOCUMENT_ID' and table=='query_row':
        meaning='조회 행의 소속 문서를 표시하는 권한 필터용 원문 ID다. 문서에 소속되지 않은 공통 용어집 행은 NULL일 수 있다. NULL을 모든 권한 검사가 불필요하다는 의미로 해석하지 않는다.'
    dtype=item['current_type']
    if dtype=='CLOB':
        type_reason='원문·메타/JSON·인코딩 내용의 가변 길이와 무손실 전송을 보존하기 위해 현행 CLOB 유지. 실측과 승인 인포타입 확인 전 길이 제한 문자열로 축소하지 않음.'
    elif dtype.startswith('VARCHAR2'):
        type_reason='문자 식별값·코드·hash 및 선행 0을 보존하기 위해 현행 VARCHAR2 BYTE 계약 유지. 승인 도메인·문자셋과 실제 최대 길이는 추가 확인.'
    elif dtype.startswith('TIMESTAMP'):
        type_reason='등록 날짜·시간·시간대와 DB 기본값을 보존하기 위해 현행 타입 유지. 법령 시행일로 변환하지 않음.'
    else:
        type_reason='현재 정수 범위·정밀도와 동시성/크기/표시 계약을 보존하기 위해 현행 NUMBER 유지.'
    if name=='JSON_TEXT_ELIDED':
        type_reason+=' 후보 여부 도메인이 문자형이면 0/1/NULL 변환을 별도 승인·검증하며 이번에는 자동 변경하지 않음.'
    nullable='허용' if item['nullable'] else '불가'
    description='\n'.join([
        '논리명(미승인 후보): '+item['logical_name_ko_candidate'],
        '업무 의미: '+meaning, '허용값·코드·범위: '+allowed,
        '산식·생성 규칙: '+formula,
        '타입·NULL·기본값: '+dtype+' / NULL '+nullable+' / '+str(item['default'] or '없음'),
        '명칭 선정 이유: '+reason, '타입 유지·변경 이유: '+type_reason,
        '표준 매핑 상태: 표준단어·용어·도메인·인포타입 미확인; 승인 필요.',
        '확인 근거: '+evidence,
    ])
    return {'business_meaning':meaning,'allowed_values':allowed,'derivation':formula,
            'naming_rationale':reason,'type_rationale':type_reason,
            'description_plain_text':description,'evidence':evidence,
            'evidence_status':'로컬 DDL/코드 계약 대조; 현장 데이터 전수 확인 아님'}

def table_metadata(key, spec, row, question, inclusion, caution):
    summary, naming, classification, selection, completion, sql, evidence=TABLE_DETAILS[key]
    pk=' + '.join(spec['columns'][c]['candidate_name'] for c in spec['primary_key'])
    required={
        '요약':summary, '행단위와PK':row['행단위']+' / PK '+pk,
        '답할수있는질문':question,'포함제외':inclusion,
        '보유기간과기준시점':'기존 원문·완료 이력은 보존한다. 공식 보유기간·삭제 기준은 담당자 확인 필요. 조회 범위는 데이터 세대/게시 릴리스 또는 현재 상태 기준.',
        '갱신주기와완료기준':row['생성시각계획']+' / 완료 기준: '+completion,
        '산식과단위':'업무 집계 산식 해당 없음. 식별값·hash·순번·바이트 수의 계산은 컬럼별 생성 규칙에 명시.',
        '원천과결합':row['데이터출처']+' / '+row['가공프로세스'],
        '주의':caution,'오너':'관리 부서·담당자 미확정; 담당자 확인 필요.',
        '예시질의':question+'\n'+sql+'\n<승인스키마>와 bind 값 확인 전 실행하지 않는 검토 예시.',
    }
    description='논리명(미승인 후보): '+spec['logical_name_ko']+'\n'+'\n'.join(k+': '+v for k,v in required.items())
    description+='\n명칭 선정 이유: '+naming+'\n데이터유형 선정 이유: '+classification+'\n레이어 선정 이유: '+selection
    metadata={
        'business_description':summary,'naming_rationale':naming,
        'data_type_classification_rationale':classification,'layer_selection_rationale':selection,
        'description_fields':required,'description_plain_text':description,
        'bizmeta':{'logical_description':summary,'data_source':row['데이터출처'],
                   'data_classification':row['데이터유형제안'],'processing':row['가공프로세스'],
                   'creation_schedule':row['생성시각계획']},
        'evidence':evidence,'registration_status':'CANDIDATE_NOT_SUBMITTED',
        'unresolved':{'agent_number':'미확정','dev_owner':'미확정','prod_owner':'미확정',
                      'business_owner':'미확정','retention':'승인 보유기간 미확정',
                      'schedule':'목표 흐름만 확인; 운영 완료시각 미확정',
                      'standard_dictionary':'표준단어·용어·도메인·인포타입 미확인'},
    }
    return metadata,sql,completion

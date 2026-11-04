# 개발계에 빈 프로젝트 LEGAL_RAG_DEV_TEST를 만들고 실행하세요.
# 그 프로젝트의 Managed Folder GOLD_TEST_CODE에 코드 ZIP을 그대로 업로드합니다.
# 아래 네 값은 실제 개발계 값으로 입력합니다. 나머지는 모델/실행환경이 다를 때만 변경합니다.
PARAMS = {
    'CODE_FOLDER_ID': '',        # GOLD_TEST_CODE의 ID (표시 이름 아님)
    'ORACLE_CONNECTION': '',     # 개발계 Oracle 연결명
    'EXPECTED_DB_USER': '',      # 그 연결의 실제 접속 계정, 대문자
    'GOLD_OWNER': '',            # 테스트 테이블을 만들 스키마, 대문자
    'WORK_DIR': '',              # 빈 값: 같은 DSS 호스트 /tmp. 컨테이너 실행은 공유 영속경로 필수.
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,    # 실제 개발계 임베딩 모델의 차원과 같아야 함
    'DEVELOPMENT_ONLY': True,
    'TARGET_MODE': 'GOLD',
    'TABLE_PREFIX': 'TST_B003_LGL_',
    'TABLE_NAMES': {},
    'EXPECTED_ARCHIVE': 'gold-dev-sample.zip',
    'EXPECTED_PARTS': 2,
    'ACTIVATE_NEW_VECTOR_HEAD': True,
    'RUN_AFTER_INSTALL': False,
}

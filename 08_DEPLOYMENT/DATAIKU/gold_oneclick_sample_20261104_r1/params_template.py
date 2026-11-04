# 기존 개발계 프로젝트의 Python 노트북에서 셀 하나로 실행합니다.
# 아래 폴더에 DATAIKU_GOLD_ONECLICK_SAMPLE_20261104_R1.zip 하나만 올려두세요.
PARAMS = {
    'CODE_FOLDER_ID': '',         # 이미 업로드/저장이 되는 기존 Managed Folder ID
    'ORACLE_CONNECTION': 'AIDP',  # 기존 값. 실제 개발계 연결명과 다르면 변경
    'EXPECTED_DB_USER': 'PIDD2APP',# 기존 값. 실제 개발계 접속 계정과 다르면 변경
    'GOLD_OWNER': '',             # 테스트 테이블을 생성할 실제 개발계 스키마
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,
    'WORK_DIR': '',               # 기본 자동 지정. 중단 후 재개하려면 이 작업 경로 보존
}

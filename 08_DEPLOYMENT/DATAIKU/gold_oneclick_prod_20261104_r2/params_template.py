# 운영계 Dataiku: 아래 설정을 확인하고 이 TXT 전체를 Python 노트북 셀 하나에서 실행합니다.
# 코드 ZIP + 기존 데이터 34조각 + PARTS.sha256 + ORIGINAL.sha256을 업로드합니다.
# CODE_FOLDER_ID는 표시 이름이 아니라 실제 Managed Folder ID입니다.
PARAMS = {
    'CODE_FOLDER_ID': '',          # 필수: 정상 업로드/다운로드되는 기존 폴더 ID
    'INPUT_FOLDER_ID': '',         # 같은 폴더면 빈 값. 별도 데이터 폴더면 그 ID
    'ORACLE_CONNECTION': 'AIDP',    # 기존 운영계 Oracle 연결 이름
    'EXPECTED_DB_USER': 'PIDD2APP', # Oracle 접속 계정. owner와 구분
    'GOLD_OWNER': 'SIDDS',          # 사용자 확인값. 운영 등록 테이블도 SIDDS인지 확인
    'TABLE_PREFIX': 'IDD_B003_LGL_',
    'TABLE_NAMES': {},             # 등록명이 다른 경우에만 {'DOC_VER':'실제이름', ...}
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,
    'WORK_DIR': '',                # 선택: DSS에서 쓰기 가능한 영속 Linux 절대경로(기준 폴더)
}

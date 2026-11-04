# Dataiku 새 Python 노트북: 설정은 이 블록에서 한 번만 입력합니다.
# 먼저 코드 ZIP을 CODE_FOLDER_ID에 업로드하고 이 셀 전체를 실행하세요.
# 설치 후 표시되는 INPUT 폴더에 데이터 조각34개와 SHA파일2개를 올린 뒤 Scenario Run.
PARAMS = {
    'CODE_FOLDER_ID': 'ehA8dpVm',
    'INPUT_FOLDER_ID': '',        # 비우면 조각 업로드 폴더를 자동 생성. 이미 올렸다면 그 폴더 ID.
    'ORACLE_CONNECTION': 'AIDP',
    'EXPECTED_DB_USER': 'PIDD2APP',
    'TARGET_MODE': 'GOLD',        # GOLD: 등록명 / DEV_1: 기존 SIDDS·SIDDA의 *_1
    'GOLD_OWNER': '',             # GOLD일 때 실제 현장 스키마명 필수. 로컬 시험 owner를 쓰지 않습니다.
    'TABLE_PREFIX': 'IDD_B003_LGL_', # 사용자 숫자003 지시 반영. 현장 접두어가 다르면 이 한 곳만 변경.
    'TABLE_NAMES': {},            # 이름이 다르면 {'DOC_VER':'실제_테이블명', ...}만 지정
    'WORK_DIR': '',               # 선택: 모든 레시피가 공유하는 영속 작업 경로. 빈 값은 동일 DSS 호스트 /tmp.
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,
    'ACTIVATE_NEW_VECTOR_HEAD': True, # 이번 검색 게시본의 벡터 연결만 등록. 기존 서비스 채널은 유지.
    'EXPECTED_ARCHIVE': 'genos-rag-data-20261007T002029Z-7c0b050f.zip',
    'EXPECTED_PARTS': 34,
    'ORIGINAL_SHA_FILE': '',       # 비우면 ORIGINAL.sha256 및 동일 내용 복사본 자동 탐색
    'PARTS_SHA_FILE': '',          # 비우면 PARTS.sha256 및 동일 내용 복사본 자동 탐색
    'RUN_AFTER_INSTALL': False,   # 파일 업로드 완료 후 True로 같은 셀 재실행하면 Scenario를 1회 시작
}

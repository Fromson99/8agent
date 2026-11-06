# 새 Dataiku 실험 프로젝트의 Python 노트북. 공유 WORK_DIR는 레시피 사이에 보존되어야 합니다.
PARAMS = {
    'ENVIRONMENT': 'DEV',       # DEV = SIDDS 개발 Silver, PROD = 사전 생성한 운영 Gold
    'CODE_FOLDER_ID': '',       # FLOW ZIP 업로드 위치
    'INPUT_FOLDER_ID': '',      # 낱개 원문 전용 Managed Folder (읽기 전용)
    'DOCUMENT_PREFIX': '',      # 평면 내규 폴더는 internal/실제팀, 외규는 law 등 실제 출처, RAW 하위 구조면 빈 값
    'SUPPORT_FOLDER_ID': '',    # GENOS에 지원 ZIP을 마운트하면 빈 값. 또는 기존 R10 지원 ZIP·영수증 폴더 ID
    'WORK_DIR': '',             # DSS 레시피들이 공유하는 영속 POSIX 작업 디렉터리
    'AGENT_CONNECTION': 'AIDP', # SIDDA 실험 결과 SELECT
    'TARGET_CONNECTION': 'AIDP',
    'EXPECTED_DB_USER': 'PIDD2APP',
    'GOLD_OWNER': '',           # PROD에서 실제 등록 owner 필수
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,
}

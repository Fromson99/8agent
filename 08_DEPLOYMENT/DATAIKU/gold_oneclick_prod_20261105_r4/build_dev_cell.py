from pathlib import Path

HERE = Path(__file__).resolve().parent
params = """# 사내 개발계 Dataiku Python 노트북 전용. 아래 네 값은 개발계 실제 값을 입력합니다.
PARAMS = {
    'CODE_FOLDER_ID': '',       # 코드 ZIP을 업로드한 개발계 Managed Folder ID
    'ORACLE_CONNECTION': '',    # 개발계 Oracle 연결 이름
    'EXPECTED_DB_USER': '',     # 해당 연결의 Oracle 접속 계정 (대문자)
    'DEV_OWNER': '',            # 시험 테이블 생성 또는 적재가 허용된 개발 스키마 (대문자)
}
if any(not value.strip() for value in PARAMS.values()):
    raise ValueError('개발계 설정 네 값을 모두 입력하세요.')
"""
runner = (HERE/'DATAIKU_GOLD_PROD_RUN_R4.txt').read_text()
bootstrap = runner[runner.index('import hashlib'):runner.index('from prod_run import run')]
implementation = (HERE/'dev_one_table.py').read_text()
code = params + '\n' + bootstrap + '\n' + implementation + '''
RESULT = run_one_table(PARAMS, FLOW_PACKAGE)
print(json.dumps(RESULT, ensure_ascii=False, indent=2))
'''
compile(code, 'DEV_ONE_TABLE_RUN_R4', 'exec')
(HERE/'DATAIKU_GOLD_DEV_ONE_TABLE_RUN_R4.txt').write_text(code, encoding='utf-8')

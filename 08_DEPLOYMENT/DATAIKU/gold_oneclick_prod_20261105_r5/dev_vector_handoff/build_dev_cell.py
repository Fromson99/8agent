"""Combine the verified R5 extraction bootstrap and the three-table development test."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
prod = (HERE.parent/'DATAIKU_GOLD_PROD_RUN_R5.txt').read_text()
bootstrap = prod[prod.index('import hashlib'):prod.index('from prod_run import run')]
params = """# 개발계 LEGAL_RAG. 지난 R4 시험이 성공한 SIDDA에 R5 전용 벡터 시험 표 3개를 사용합니다.
PARAMS = {
    'CODE_FOLDER_ID': 'ehA8dpVm',
    'ORACLE_CONNECTION': 'AIDP',
    'EXPECTED_DB_USER': 'PIDD2APP',
    'DEV_OWNER': 'SIDDA',
}
"""
source = params + '\n' + bootstrap + '\n' + (HERE/'dev_vectors.py').read_text()
source += '\nRESULT = run_dev_vectors(PARAMS, FLOW_PACKAGE)\nprint(json.dumps(RESULT, ensure_ascii=False, indent=2))\n'
compile(source, '<R5-dev-vector-cell>', 'exec')
(HERE/'DATAIKU_GOLD_DEV_VECTOR_3TABLES_R5.txt').write_text(source)

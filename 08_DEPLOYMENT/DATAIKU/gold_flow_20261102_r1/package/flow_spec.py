"""One stage specification drives installation, execution and the display."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / 'engine'
PREFIX = 'G19F1'
INSIGHT = 'g19f1_pipeline_status'
STAGES = [
    ('receive', '00_NFS', 'NFS 데이터 준비', '01 · 데이터 준비', []),
    ('prepare', '01_PREPARE', '적재 자료 준비', '01 · 데이터 준비', []),
    ('schema', '02_TABLES', '_1 테이블 준비', '02 · DB 테이블',
     ['AGT_RUN', 'AGT_REC', 'AGT_BODY', 'EXEC_ST', 'ONTL_POST', 'ONTL_HEAD', 'ONTL_ANC', 'VCTR_HEAD']),
    ('source', '03_SOURCE', '원문 DB 적재', '03 · 원문 적재', ['DOC_VER', 'DOC_UNIT', 'DOC_BLK']),
    ('query', '04_SEARCH', '검색 자료 DB 적재', '04 · 검색 적재', ['SRCH_ROW']),
    ('verify', '05_VERIFY', '원문·검색 검증', '05 · 검증', ['SRC_POST', 'SRCH_POST', 'SRCH_CHNL']),
    ('vector', '06_VECTOR', '벡터 생성·DB 저장', '06 · 벡터', ['VCTR_POST', 'VCTR_ITEM']),
    ('report', '07_RESULT', 'DB 저장 결과 확인', '07 · 결과 모니터', []),
]

def contract():
    return json.loads((ENGINE / 'contract.json').read_text())

def recipe_name(stage):
    return PREFIX + '_' + next(s[1] for s in STAGES if s[0] == stage)

def validate_spec():
    keys = [k for s in STAGES for k in s[4]]
    if len(keys) != len(set(keys)) or set(keys) != set(contract()['tables']):
        raise ValueError('FLOW_TABLE_OWNERSHIP')


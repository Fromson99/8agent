"""Explicit target mapping, without interpreting local-test owner as production."""
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / 'engine'
PREFIX = 'G19ZIP'
STAGES = [
    ('inspect', '00_INPUT', '조각·Gold 스키마 확인', []),
    ('restore', '01_RESTORE', 'ZIP 병합·세대 복원', []),
    ('prepare', '02_PREPARE', '원문·검색 적재 자료 준비', []),
    ('source', '03_SOURCE', 'Gold 원문 적재', ['DOC_VER','DOC_UNIT','DOC_BLK']),
    ('search', '04_SEARCH', 'Gold 검색 자료 적재', ['SRCH_ROW']),
    ('publish', '05_PUBLISH', '원문·검색 게시 기록', ['SRC_POST','SRCH_POST','SRCH_CHNL']),
    ('vector', '06_VECTOR', '구조 단위 임베딩·벡터 적재', ['VCTR_POST','VCTR_ITEM','VCTR_HEAD']),
    ('report', '07_REPORT', '현재 판본 적재 결과 확인', []),
]


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', value):
        raise ValueError('ORACLE_IDENTIFIER_REQUIRED:'+str(value))
    return value


def target(params):
    registered = json.loads((ROOT/'registration_current.json').read_text())
    mode = params['TARGET_MODE']
    if mode not in {'GOLD', 'DEV_1'}: raise ValueError('TARGET_MODE_MUST_BE_GOLD_OR_DEV_1')
    development = json.loads((ENGINE/'contract.json').read_text()) if mode == 'DEV_1' else None
    tables = {}
    for key, table in registered['tables'].items():
        t = copy.deepcopy(table)
        t['group'] = 'GOLD_R19'
        if mode == 'GOLD':
            t['owner'] = identifier(params.get('GOLD_OWNER',''))
            t['name'] = identifier(params.get('TABLE_PREFIX','IDD_B003_LGL_')+key)
        else:
            d = development['tables'][key]
            t = copy.deepcopy(d)
        override = params.get('TABLE_NAMES', {}).get(key)
        if override: t['name'] = identifier(override)
        identifier(t['name']); tables[key] = t
    if set(params.get('TABLE_NAMES',{})) - set(tables): raise ValueError('UNKNOWN_TABLE_OVERRIDE')
    if len({(t['owner'],t['name']) for t in tables.values()}) != len(tables): raise ValueError('TABLE_NAME_COLLISION')
    return {'version':'gold-zip-flow-r19-v1','target_mode':mode,'tables':tables}


def validate(params):
    target(params)
    for name in ('CODE_FOLDER_ID','ORACLE_CONNECTION','EXPECTED_DB_USER','EMBED_MODEL'):
        if not isinstance(params.get(name),str) or not params[name].strip(): raise ValueError(name+'_REQUIRED')
    identifier(params['EXPECTED_DB_USER'])
    if type(params.get('EMBED_DIMENSIONS')) is not int or not 1 <= params['EMBED_DIMENSIONS'] <= 4096:
        raise ValueError('EMBED_DIMENSIONS_INVALID')
    if type(params.get('EXPECTED_PARTS')) is not int or params['EXPECTED_PARTS'] < 1: raise ValueError('EXPECTED_PARTS_INVALID')
    return params

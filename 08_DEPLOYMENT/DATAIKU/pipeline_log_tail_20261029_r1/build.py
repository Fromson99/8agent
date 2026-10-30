import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = '''# 상태 조회/허용 TXT를 실행했던 같은 LEGAL_RAG 노트북의 새 셀에서 전체 실행.
# 저장 로그 읽기 전용. 새 허용/02 시작/취소/GENOS 호출/데이터 쓰기 없음.
'''+(HERE/'tail_reader.py').read_text()+'''

import dataiku
import controller as c
from updater import config

if dataiku.default_project_key() != 'LEGAL_RAG':
    raise ValueError('LEGAL_RAG 프로젝트에서 실행하세요.')
project = dataiku.api_client().get_project('LEGAL_RAG')
cfg = config(project.get_recipe('LEGAL_02_STRUCTURE_GENOS_R1').get_settings().get_code(), 'structure')
folder = dataiku.Folder(cfg['structured'])
job_name = dataiku.get_custom_variables().get('LEGAL_RECIPE_JOB_NAME', 'recipes_20261027_r1')
latest = c.legacy_state(c.Scope(folder), job_name)
handle = ((latest or {}).get('value', {}).get('compute') or {}).get('handle', '')
if not re.fullmatch(r'[0-9a-f]{32}', handle):
    raise ValueError('현재 실행 핸들이 없습니다. 02 시작 상태를 확인하세요.')
print('현재 저장 상태:', latest['value'].get('phase'), flush=True)
follow(folder, c.NAMESPACE + 'attempts/' + handle + '/logs/')
'''
ast.parse(source,feature_version=(3,9))
(HERE/'DATAIKU_LOG_TAIL.txt').write_text(source)
print('READ_ONLY_TAIL_PREPARED')

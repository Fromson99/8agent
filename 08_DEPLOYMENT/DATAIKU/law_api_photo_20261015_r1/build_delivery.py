import ast
import hashlib
import json
from pathlib import Path
import pprint

HERE = Path(__file__).resolve().parent
OUT = HERE / 'private_delivery'
OUT.mkdir(exist_ok=True, mode=0o700)
INPUTS_PATH = Path('/tmp/dataiku_photo_inspect/photo_inputs.json')
photo = json.loads(INPUTS_PATH.read_text())
assert set(photo) == {'relay_origin', 'method', 'target_url', 'OC', 'Cookie', 'params'}
assert photo['relay_origin'] == 'https://45.101.64.86:8443'
parent = HERE.parent / 'law_api_network_20261015_r1' / 'DATAIKU_NETWORK_EVIDENCE_20261015_R1_CELL.txt'
source = parent.read_text()
names = {'evidence_clock', 'evidence_scrub', 'evidence_config_value', 'evidence_curl'}
nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
assert len(nodes) == 4
helpers = '\n\n'.join(ast.get_source_segment(source, n) for n in nodes)
config = '''# 사용자 요청에 따라 최초 curl 사진의 값을 미리 채웠습니다. 추가 입력창은 없습니다.
# Python/Jupyter 셀용입니다. bash 파일이 아닙니다.
# 인증값이 소스에 포함됩니다. 실행 결과 JSON/메일 본문에는 인증값을 출력하지 않습니다.
# 사진 전사값의 문자 단위 일치 및 현재 세션 유효성은 미검증입니다.
PHOTO_INPUTS = ''' + pprint.pformat(photo, width=110, sort_dicts=False) + '\n'
imports = '''import datetime
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
from urllib.parse import quote, quote_plus, urlencode, urlsplit
import requests

PHOTO_HOST = "45.101.64.86"
PHOTO_PORT = 8443
PHOTO_TARGET = PHOTO_INPUTS["target_url"]
PHOTO_PARAMS = PHOTO_INPUTS["params"]
'''
runner = (HERE / 'replay_runner.py').read_text()
complete = config + '\n' + imports + '\n' + helpers + '\n\n' + runner
ast.parse(complete, feature_version=(3, 9))
name = 'DATAIKU_PHOTO_INPUTS_20261015_R1_CELL.txt'
(OUT / name).write_text(complete)
(OUT / name).chmod(0o600)
notebook = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}, 'language_info': {'name': 'python', 'version': '3.9'}},
            'cells': [{'cell_type': 'markdown', 'id': 'instructions', 'metadata': {}, 'source': ['사진 입력값을 채운 curl 확인\n', '\n', '아래 1번 셀에 사진의 URL·OC·Cookie·검색 조건이 이미 들어 있습니다. 1번 → 2번 순서로 실행하세요. 추가 입력창은 없습니다. 최초 curl 요청 1회만 수행하며 세션 유효성은 미확인입니다. 기존 Notebook에 추가하려면 별도 CELL.txt 전체를 새 Code 셀에 붙여 넣으세요.\n']},
                      {'cell_type': 'code', 'id': 'photo-inputs', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': config.splitlines(keepends=True)},
                      {'cell_type': 'code', 'id': 'execute', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': (imports + '\n' + helpers + '\n\n' + runner).splitlines(keepends=True)}]}
(OUT / 'DATAIKU_PHOTO_INPUTS_20261015_R1.ipynb').write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + '\n')
(OUT / 'DATAIKU_PHOTO_INPUTS_20261015_R1.ipynb').chmod(0o600)
binding = {'version': 'dataiku-photo-inputs-20261015-r1', 'parent_helpers_sha256': hashlib.sha256(parent.read_bytes()).hexdigest(),
           'reused_functions': sorted(names), 'cell_sha256': hashlib.sha256(complete.encode()).hexdigest(),
           'source_photo': 'F5F977E2-AF87-4F71-8109-303731123253/1-사진-1.jpg',
           'request_inputs_prefilled': ['relay_origin', 'method', 'target_url', 'OC', 'Cookie', 'lsClsCd', 'closing', 'asndOfiNm', 'admRulNm'],
           'photo_transcription_byte_identity_verified': False, 'credential_validity': 'UNKNOWN',
           'samsung_internal_calls_by_author': 0, 'generated_outputs_ignored_by_git': True}
(HERE / 'SOURCE_BINDING.json').write_text(json.dumps(binding, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'files_created': [name, 'DATAIKU_PHOTO_INPUTS_20261015_R1.ipynb'], 'credentials_printed': False}))

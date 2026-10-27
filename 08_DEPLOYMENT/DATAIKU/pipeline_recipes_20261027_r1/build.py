"""Reproducible recipe delivery; preserve the previously mailed files byte-for-byte."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
import yaml

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'pipeline_layers_20261027_r1'
NAME = 'DATAIKU_RECIPE_PACKAGE_20261027_R1.zip'
files = {name:(HERE/name).read_bytes() for name in ('recipes_runtime.py','install_flow.py','bootstrap.py','GUIDE.txt','WORK_CONTRACT.txt')}
files['legacy_runner.py'] = (BASE/'DATAIKU_PIPELINE_RUN_20261027_R1.txt').read_bytes()
with zipfile.ZipFile(BASE/'DATAIKU_PIPELINE_CLIENT_20261027_R1.zip') as source:
    for name in source.namelist(): files['client/'+name.split('/',1)[1]] = source.read(name)
for name in ('00_CHECK_TARGET.sql','01_CREATE_TABLES.sql','02_COMMENTS.sql','03_CHECK_LOADED.sql'):
    files[name] = (BASE/name).read_bytes()
mapping = yaml.safe_load(files['client/physical_mapping.yaml'])
datasets = []
for key, table in mapping['tables'].items():
    if key in ('query_active','query_state'): continue
    columns = []
    for spec in table['columns'].values():
        kind = spec['type']
        col = {'name':spec['name'], 'type':'bigint' if kind.startswith('NUMBER') else 'string',
               'originalType':kind.split('(')[0].split()[0]}
        if col['type'] == 'string':
            sizes = re.findall(r'\((\d+)', kind)
            col['maxLength'] = int(sizes[0]) if sizes else 2147483647
        columns.append(col)
    datasets.append({'name':'LEGAL_OUT_'+table['name'], 'params':{
        'connection':'AIDP','schema':'SIDDS','table':table['name'],'mode':'table',
        'noDropOnSchemaMismatch':True}, 'schema':{'columns':columns}})
files['oracle_datasets.json'] = (json.dumps(datasets, ensure_ascii=False, indent=2)+'\n').encode()
(HERE/'oracle_datasets.json').write_bytes(files['oracle_datasets.json'])
pins = {name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
files['PACKAGE_FILES.json'] = (json.dumps(pins, indent=2)+'\n').encode()
with zipfile.ZipFile(HERE/NAME, 'w', zipfile.ZIP_DEFLATED) as z:
    for name,data in sorted(files.items()):
        info = zipfile.ZipInfo(name, (2026,10,27,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, data)
archive = (HERE/NAME).read_bytes()
constants = ('LANDING_ID = "ehA8dpVm"\nPACKAGE_NAME = '+repr(NAME)+'\nPACKAGE_SHA256 = '
             +repr(hashlib.sha256(archive).hexdigest())+'\nPACKAGE_BYTES = '+str(len(archive))+'\n')
bootstrap = constants + files['bootstrap.py'].decode()
install = ('# LEGAL_RAG의 새 Python 노트북 한 셀에 전체를 붙여 실행합니다.\n'
           '# Flow만 생성합니다. GENOS 처리/DB 적재는 자동 시작하지 않습니다.\n'+bootstrap+'''
work, code_root = verified_package()
spec = importlib.util.spec_from_file_location('legal_recipe_install', code_root/'install_flow.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:
    FLOW_IDS = module.install(dataiku.api_client().get_project('LEGAL_RAG'),
                             '''+repr(bootstrap)+''', LANDING_ID)
except BaseException:
    print('설치 실패 기록 디렉터리:', str(work))
    raise
else:
    shutil.rmtree(work)
''')
(HERE/'DATAIKU_RECIPE_INSTALL_20261027_R1.txt').write_text(install)
# A standalone immediate check uses the same package and existing project variables.
# Full Flow installation also produces the durable connection-check recipe.
check = bootstrap + '''
work, code_root = verified_package()
sys.path[:0] = [str(code_root), str(code_root/'client'), str(code_root/'client/02_BACKEND')]
import recipes_runtime
result = recipes_runtime.connection(dataiku.get_custom_variables(), dataiku.Folder(LANDING_ID), work)
shutil.rmtree(work)
'''
(HERE/'DATAIKU_GENOS_CONNECTION_CHECK_20261027_R1.txt').write_text(check)
manifest = {'package':NAME, 'package_sha256':hashlib.sha256(archive).hexdigest(), 'package_bytes':len(archive),
            'service_code_sha256':files['client/SERVICE_CODE_SHA256.txt'].decode().strip(),
            'worker_modified':False, 'field_verified':False,
            'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     [HERE/NAME,HERE/'DATAIKU_RECIPE_INSTALL_20261027_R1.txt',HERE/'DATAIKU_GENOS_CONNECTION_CHECK_20261027_R1.txt',HERE/'GUIDE.txt']}}
(HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:v for k,v in manifest.items() if k != 'files'}))

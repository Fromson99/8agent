"""Build one complete Dataiku notebook cell, ZIP and the same standalone TXT."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'pipeline_recipes_20261027_r1'
REF = json.loads((HERE.parent/'pipeline_input_selection_20261027_r2/REFERENCE.json').read_text())
manifest = json.loads((BASE/'DELIVERY_MANIFEST.json').read_text())
for name, sha in manifest['files'].items():
    assert hashlib.sha256((BASE/name).read_bytes()).hexdigest() == sha, name
assert REF['old_package_sha256'] == manifest['package_sha256']
source = (BASE/'recipes_runtime.py').read_text()
tree = ast.parse(source)
classes = [ast.get_source_segment(source,n) for n in tree.body
           if isinstance(n,ast.ClassDef) and n.name in ('NoRedirect','CheckedClient')]
http = '\n\n'.join(classes).replace('class CheckedClient(client.Client):',
    'class CheckedClient:\n    def __init__(self, url, token):\n        self.url, self.token = url, token\n'
    '        self.deadline, self.calls = time.monotonic()+120, 0\n')
http = http.replace('    def call(self, operation, **fields):\n',
    '    def call(self, operation, **fields):\n'
    "        if operation not in {'HEALTH','STATUS'}:\n            raise ValueError('INSPECTION_ONLY')\n"
    "        if time.monotonic() >= self.deadline or self.calls >= 21:\n            raise ValueError('INSPECTION_BUDGET')\n"
    '        self.calls += 1\n')
http = http.replace('timeout=120','timeout=min(15, max(0.001, self.deadline-time.monotonic()))')
http = http.replace('4*t.CHUNK','4*1024*1024').replace(
    "{'BUSY', 'INSTANCE_MISMATCH', 'CODE_MISMATCH', 'UNKNOWN_JOB'}",
    "{'BUSY', 'INSTANCE_MISMATCH', 'CODE_MISMATCH', 'UNKNOWN_JOB', 'JOB_LOST', "
    "'INSTANCE_CHANGED', 'CODE_BINDING_CHANGED', 'JOB_AUTH', 'JOB_CODE_CHANGED', 'DEADLINE_EXHAUSTED'}")
bounded_source = (HERE.parent/'pipeline_mapped_20261023_r1/src/managed_job.py').read_text()
bounded = next(ast.get_source_segment(bounded_source,n) for n in ast.parse(bounded_source).body
               if isinstance(n,ast.FunctionDef) and n.name=='bounded_read').replace('t.CHUNK','1024*1024')
helpers = '''import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace
'''+bounded+'\n\n'+http+'\n'
resume = (HERE/'resume.py').read_text()
script = '''# LEGAL_RAG Python 노트북의 한 셀에서 전체 실행합니다.
# 실패한 02가 종료된 상태에서 실행. 자동 배치 실행/취소/ACK 없음.
ACTION = 'apply'  # apply / inspect / rollback
'''+(HERE/'update.py').read_text()+'\n'+helpers+'\n'+resume+'''
import dataiku
if dataiku.default_project_key() != 'LEGAL_RAG':
    raise ValueError('LEGAL_RAG 프로젝트에서 실행하세요.')
'''+ 'BASELINE = '+repr(REF['baseline_bootstrap'])+'\nNAMED_INPUT = '+repr(REF['adapter_source'])+'\nRESUME_SOURCE = '+repr(resume)+'''
CFG = update(dataiku.api_client().get_project('LEGAL_RAG'), BASELINE, NAMED_INPUT,
             RESUME_SOURCE, 'legal_recipe_resume_20261027_r3_backup', ACTION)
VARIABLES = dataiku.get_custom_variables()
def diagnostic_remote(variables):
    for name in ('LEGAL_PIPELINE_URL','LEGAL_PIPELINE_TOKEN'):
        if not isinstance(variables.get(name),str) or not variables[name].strip():
            raise ValueError('PROJECT_VARIABLE_REQUIRED: '+name)
    return CheckedClient(variables['LEGAL_PIPELINE_URL'],variables['LEGAL_PIPELINE_TOKEN'])
DIAG = SimpleNamespace(EXPECTED='771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46',
    remote_client=diagnostic_remote, bounded_read=bounded_read,
    t=SimpleNamespace(digest=lambda value: hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()))
FOLDERS = {CFG[role]:dataiku.Folder(CFG[role]) for role in ('landing','structured','load')}
JOB_STATUS = inspect_jobs(DIAG, FOLDERS, VARIABLES)
'''
name = 'DATAIKU_RESUME_FIX_20261027_R3.txt'
compile(script,name,'exec')
ast.parse(script,feature_version=(3,9))
(HERE/name).write_text(script,encoding='utf-8')
archive = 'DATAIKU_RESUME_FIX_20261027_R3.zip'
members = [name,'GUIDE.txt','WORK_CONTRACT.txt','resume.py','update.py']
with zipfile.ZipFile(HERE/archive,'w',zipfile.ZIP_DEFLATED) as z:
    for member in members:
        info=zipfile.ZipInfo(member,(2026,10,27,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(HERE/member).read_bytes())
with zipfile.ZipFile(HERE/archive) as z:
    assert z.read(name)==(HERE/name).read_bytes()
    assert all(Path(p).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
out={'version':'resume-20261027-r3','baseline_package_sha256':manifest['package_sha256'],
     'service_code_sha256':'771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46',
     'changed_recipe':'LEGAL_02_STRUCTURE_GENOS_R1','worker_changed':False,'oracle_changed':False,
     'files':{n:{'sha256':hashlib.sha256((HERE/n).read_bytes()).hexdigest(),'bytes':(HERE/n).stat().st_size}
              for n in [name,archive,'GUIDE.txt']}}
(HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

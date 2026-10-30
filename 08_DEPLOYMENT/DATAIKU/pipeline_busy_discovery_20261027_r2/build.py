import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_busy_inspection_20261027_r1'
original=(BASE/'inspect_jobs.py').read_bytes()
pin=json.loads((BASE/'DELIVERY_MANIFEST.json').read_text())['inspect_jobs.py']['sha256']
assert hashlib.sha256(original).hexdigest()==pin
script='''# LEGAL_RAG Python 노트북 새 셀에서 전체 실행. 조회만 하며 배치를 실행/취소/해제하지 않습니다.
'''+(HERE/'discovery.py').read_text()+'''
import types
BASE_INSPECTION = '''+repr(original.decode())+'''
_discovery_base = types.ModuleType('verified_busy_inspection_r1')
exec(compile(BASE_INSPECTION, '<verified-busy-inspection-r1>', 'exec'), _discovery_base.__dict__)
import dataiku
_known_local_roots = ['./legal_pipeline_work']
if isinstance(globals().get('WORK_DIR'), str) and WORK_DIR.strip():
    _known_local_roots.append(WORK_DIR)
try:
    DISCOVERY_ROWS, DISCOVERY_SUMMARY = discover(_discovery_base, dataiku, _known_local_roots)
except _discovery_base.InspectionError as exc:
    print('DISCOVERY_STOPPED',str(exc),flush=True)
except Exception as exc:
    print('DISCOVERY_STOPPED',type(exc).__name__,flush=True)
'''
import ast
ast.parse(script,feature_version=(3,9))
name='DATAIKU_GENOS_BUSY_DISCOVERY_20261027_R2.txt'
(HERE/name).write_text(script,encoding='utf-8')
archive=name.replace('.txt','.zip')
with zipfile.ZipFile(HERE/archive,'w',zipfile.ZIP_DEFLATED) as z:
    for member in [name,'GUIDE.txt','discovery.py']:
        info=zipfile.ZipInfo(member,(2026,10,27,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(HERE/member).read_bytes())
with zipfile.ZipFile(HERE/archive) as z:
    assert z.read(name)==(HERE/name).read_bytes()
    assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
result={'baseline_inspector_sha256':pin,'files':{n:{'sha256':hashlib.sha256((HERE/n).read_bytes()).hexdigest(),
    'bytes':(HERE/n).stat().st_size} for n in [name,archive,'GUIDE.txt']}}
(HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))

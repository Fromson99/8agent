"""Build isolated R6 delivery, preserving sealed R5 and all working product code."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.with_name('existing_nfs_bulk_verify_20261030_r5')
PACKAGE = 'DATAIKU_EXISTING_NFS_CLIENT_20261030_R6.zip'
NOTEBOOK = 'DATAIKU_EXISTING_NFS_RUN_R6.txt'
def sha(raw): return hashlib.sha256(raw).hexdigest()

def build():
    if (HERE/'SEALED.json').exists():
        raise RuntimeError('Preserve sealed delivery')
    base = BASE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R5.zip'
    assert sha(base.read_bytes()) == 'f1284bd750d8a61b6354609842de71e999470ecef875a6769f7016abdbdc5866'
    with zipfile.ZipFile(base) as z:
        old = {n:z.read(n) for n in z.namelist()}
    names = set(old) | {'client/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py'}
    files = {n:(HERE/'candidate'/n).read_bytes() for n in names}
    pins = json.loads(files['client/CODE_PINS.json'])
    pins['files']['02_BACKEND/lawrag/pipeline/oracle_deferred_import.py'] = ''
    for n in pins['files']: pins['files'][n] = sha(files['client/'+n])
    files['client/CODE_PINS.json'] = (json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
    files['PACKAGE_FILES.json'] = (json.dumps({n:sha(b) for n,b in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    for n in ['client/CODE_PINS.json','PACKAGE_FILES.json']:
        (HERE/'candidate'/n).write_bytes(files[n])
    changed = sorted(n for n in files if files[n] != old.get(n))
    allowed = {'existing_client.py','client/02_BACKEND/lawrag/pipeline/oracle_full_package.py',
               'client/02_BACKEND/lawrag/pipeline/oracle_migration.py',
               'client/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py',
               'client/CODE_PINS.json','PACKAGE_FILES.json'}
    assert set(changed) == allowed
    with zipfile.ZipFile(HERE/PACKAGE,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            assert not n.lower().endswith(('.zip','.js','.jsx','.mjs','.cjs'))
            if n.endswith('.py'): ast.parse(b,feature_version=(3,9))
            info=zipfile.ZipInfo(n,(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,b)
    notebook=(BASE/'DATAIKU_EXISTING_NFS_RUN_R5.txt').read_text()
    notebook=notebook.replace('DATAIKU_EXISTING_NFS_CLIENT_20261030_R5.zip',PACKAGE)
    notebook=notebook.replace(sha(base.read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    notebook=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),notebook)
    notebook=notebook.replace('# R5: 원문 CLOB 묶음 읽기 + 검증 최대100행. 전수 대조/기존 기한/예산 유지.',
        '# R6: load_only 적재만 → 나중에 verify 전수검증. 완료 전 조회 게시 명세를 생성하지 않습니다.')
    notebook=notebook.replace("ACTION = 'check' # 기존 이관 재개: check 확인 후 load. transfer 재실행 불필요",
        "ACTION = 'check' # check → load_only (적재) → 나중에 verify (검증). load는 두 단계를 연속 실행")
    notebook=notebook.replace("    'existing_client': 'existing_client.py',",
        "    'lawrag.pipeline.oracle_deferred_import': 'client/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py',\n"
        "    'existing_client': 'existing_client.py',")
    notebook=notebook.replace('이 R5 셀만 실행하세요.', '이 R6 셀만 실행하세요.')
    ast.parse(notebook,feature_version=(3,9))
    (HERE/NOTEBOOK).write_text(notebook)
    report={'base_zip_sha256':sha(base.read_bytes()),'changed_files':changed,'preserved_files':len(files)-len(changed),
            'checkpoint_directory':'oracle-import-r2','source_validation':'explicit verify once; load_only preserves transactional checks without full readback',
            'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in [PACKAGE,NOTEBOOK]}}
    (HERE/'BUILD.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({n:sha(b) for n,b in sorted(files.items())},indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__': build()

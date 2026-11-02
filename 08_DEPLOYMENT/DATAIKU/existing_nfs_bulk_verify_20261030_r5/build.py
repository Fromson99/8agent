"""Build isolated R5 delivery, preserving sealed R4 and all working product code."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.with_name('existing_nfs_continuous_20261030_r4')
PACKAGE = 'DATAIKU_EXISTING_NFS_CLIENT_20261030_R5.zip'
NOTEBOOK = 'DATAIKU_EXISTING_NFS_RUN_R5.txt'
def sha(raw): return hashlib.sha256(raw).hexdigest()

def build():
    if (HERE/'SEALED.json').exists():
        raise RuntimeError('Preserve sealed delivery')
    base = BASE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R4.zip'
    assert sha(base.read_bytes()) == '4bc4304037dfbc8ba61022d251cf5181cb4807275db38bacc65348e9b7aa994d'
    with zipfile.ZipFile(base) as z:
        old = {n:z.read(n) for n in z.namelist()}
    names = set(old) | {'client/02_BACKEND/semantic_runtime/oracle_dp_native_read.py'}
    files = {n:(HERE/'candidate'/n).read_bytes() for n in names}
    pins = json.loads(files['client/CODE_PINS.json'])
    pins['files']['02_BACKEND/semantic_runtime/oracle_dp_native_read.py'] = ''
    for n in pins['files']: pins['files'][n] = sha(files['client/'+n])
    files['client/CODE_PINS.json'] = (json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
    files['PACKAGE_FILES.json'] = (json.dumps({n:sha(b) for n,b in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    for n in ['client/CODE_PINS.json','PACKAGE_FILES.json']:
        (HERE/'candidate'/n).write_bytes(files[n])
    changed = sorted(n for n in files if files[n] != old.get(n))
    allowed = {'existing_client.py','client/02_BACKEND/lawrag/pipeline/oracle_full_package.py',
               'client/02_BACKEND/lawrag/pipeline/oracle_migration.py',
               'client/02_BACKEND/semantic_runtime/oracle_dp_io.py',
               'client/02_BACKEND/semantic_runtime/oracle_dp_native_read.py',
               'client/CODE_PINS.json','PACKAGE_FILES.json'}
    assert set(changed) == allowed
    with zipfile.ZipFile(HERE/PACKAGE,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            assert not n.lower().endswith(('.zip','.js','.jsx','.mjs','.cjs'))
            if n.endswith('.py'): ast.parse(b,feature_version=(3,9))
            info=zipfile.ZipInfo(n,(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,b)
    notebook=(BASE/'DATAIKU_EXISTING_NFS_RUN_R4.txt').read_text()
    notebook=notebook.replace('DATAIKU_EXISTING_NFS_CLIENT_20261030_R4.zip',PACKAGE)
    notebook=notebook.replace(sha(base.read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    notebook=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),notebook)
    notebook=notebook.replace('# R4: 적재 1회 6시간 제한 없음. 기존 최초 작업 기한/누적 호출 예산은 유지합니다.',
        '# R5: 원문 CLOB 묶음 읽기 + 검증 최대100행. 전수 대조/기존 기한/예산 유지.')
    notebook=notebook.replace("CLOB_BATCH_READS = 32  # 1이면 기존 직렬 조회로 같은 체크포인트에서 재개",
        "CLOB_BATCH_READS = 32  # 잘린/미지원 CLOB의 원래 조각 조회\nNATIVE_CLOB_READS = True  # 호환 문제 시 False: 같은 R5의 원래 조각 조회\nVERIFY_BATCH_ROWS = 100  # 검증만 최대100행; 쓰기는 기존20행")
    notebook=notebook.replace('# R2 적재가 끝나거나 PAUSED인 것을 확인한 뒤 커널을 재시작하여 R4를 읽습니다.',
        '# 이전 실행 종료/PAUSED/STOPPED와 커널 Idle 확인 후 Kernel Restart. 검증 중단 위치는 재사용하지 않습니다.')
    notebook=notebook.replace("    'existing_client': 'existing_client.py',", 
        "    'semantic_runtime.oracle_dp_native_read': 'client/02_BACKEND/semantic_runtime/oracle_dp_native_read.py',\n"
        "    'lawrag.pipeline.oracle_migration': 'client/02_BACKEND/lawrag/pipeline/oracle_migration.py',\n"
        "    'existing_client': 'existing_client.py',")
    notebook=notebook.replace('이 R4 셀만 실행하세요.', '이 R5 셀만 실행하세요.')
    notebook=notebook.replace('existing_client.run(ACTION, clob_batch_size=CLOB_BATCH_READS)',
        'existing_client.run(ACTION, clob_batch_size=CLOB_BATCH_READS, native_clob=NATIVE_CLOB_READS, verify_batch_rows=VERIFY_BATCH_ROWS)')
    ast.parse(notebook,feature_version=(3,9))
    (HERE/NOTEBOOK).write_text(notebook)
    report={'base_zip_sha256':sha(base.read_bytes()),'changed_files':changed,'preserved_files':len(files)-len(changed),
            'checkpoint_directory':'oracle-import-r2','source_checks_retained':['readback','verify','final_source'],
            'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in [PACKAGE,NOTEBOOK]}}
    (HERE/'BUILD.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({n:sha(b) for n,b in sorted(files.items())},indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__': build()

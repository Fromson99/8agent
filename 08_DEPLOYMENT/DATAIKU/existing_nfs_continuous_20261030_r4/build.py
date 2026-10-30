"""Remove only the per-invocation cap from the sealed R3 Dataiku load path."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.with_name('existing_nfs_fast_20261030_r3')
PACKAGE = 'DATAIKU_EXISTING_NFS_CLIENT_20261030_R4.zip'
NOTEBOOK = 'DATAIKU_EXISTING_NFS_RUN_R4.txt'
PREVIOUS_FULL_SHA = '36e52b270f8b9f73b1bfdd92d60a742afcc04fed969bce98af828dda6e54d267'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)

COMPATIBILITY = '''def _import_identity(state, expected, logs):
    """Keep checkpoint origin/journal binding; record the exact compatible executor."""
    original = state['identity']
    if original == expected:
        return expected
    previous_code = '36e52b270f8b9f73b1bfdd92d60a742afcc04fed969bce98af828dda6e54d267'
    if (not isinstance(original, dict) or original.get('code') != previous_code or
            {k:v for k,v in original.items() if k != 'code'} !=
            {k:v for k,v in expected.items() if k != 'code'}):
        raise io.DPError('IMPORT_BINDING: data/code/target changed')
    record = state.get('compatible_executor')
    if record is not None:
        if (not isinstance(record, dict) or record.get('origin_code_sha256') != previous_code or
                record.get('execution_code_sha256') != expected['code'] or
                record.get('policy') != 'existing-nfs-r4-remove-invocation-cap-v1'):
            raise io.DPError('IMPORT_BINDING: compatible executor record differs')
    else:
        receipt = logs / 'full-state.json'
        raw = receipt.read_bytes()
        receipt_sha = hashlib.sha256(raw).hexdigest()
        # Preserve pre-upgrade state exactly, including pending work and failure.
        backup = logs / ('pre-r4-state-' + receipt_sha + '.json')
        if backup.exists():
            if backup.read_bytes() != raw:
                raise io.DPError('IMPORT_BINDING: pre-upgrade receipt differs')
        else:
            with backup.open('xb') as saved:
                saved.write(raw); saved.flush(); io.os.fsync(saved.fileno())
        state['compatible_executor'] = {
            'origin_code_sha256': previous_code,
            'execution_code_sha256': expected['code'],
            'policy': 'existing-nfs-r4-remove-invocation-cap-v1',
            'prior_receipt_sha256': receipt_sha,
            'prior_receipt_file': backup.name,
            'at': time.time(),
        }
    # SQL journals continue using their original binding and cumulative counts.
    return original


'''

def build():
    assert not (HERE/'SEALED.json').exists(), 'Preserve sealed delivery'
    basezip=BASE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R3.zip'
    assert sha(basezip.read_bytes())=='9c9e6d5bcaf1bff809a763c9d13ee6d0f455322697cc09f2bf8c6b6480c62006'
    with zipfile.ZipFile(basezip) as z: old={n:z.read(n) for n in z.namelist()}
    assert all(sha(old[n])==h for n,h in json.loads(old['PACKAGE_FILES.json']).items())
    files=dict(old)
    full='client/02_BACKEND/lawrag/pipeline/oracle_full_package.py'
    assert sha(old[full])==PREVIOUS_FULL_SHA
    text=files[full].decode()
    text=replace_once(text,'import json\n','import json\nimport math\n')
    text=replace_once(text,'def import_generation(client, folder,',COMPATIBILITY+'def import_generation(client, folder,')
    text=replace_once(text,"    if not 1 <= seconds <= 21600: raise io.DPError('BUDGET: seconds 1..21600')",
        "    if seconds is not None and (type(seconds) not in (int, float) or\n"
        "                                not math.isfinite(seconds) or seconds < 1):\n"
        "        raise io.DPError('BUDGET: seconds must be None or finite and >= 1')")
    text=replace_once(text,"        if state['identity'] != identity: raise io.DPError('IMPORT_BINDING: data/code/target changed')",
        "        identity = _import_identity(state, identity, logs)")
    # Only importer; export has its own unrelated cap and remains byte-identical.
    before, marker, tail=text.partition('def import_generation(')
    tail=replace_once(tail,"        end = min(time.time()+seconds, state['deadline'])",
        "        end = state['deadline'] if seconds is None else min(time.time()+seconds, state['deadline'])")
    files[full]=(before+marker+tail).encode()
    text=files['existing_client.py'].decode()
    text=replace_once(text,"CLIENT_REVISION = 'existing-nfs-20261030-r3'","CLIENT_REVISION = 'existing-nfs-20261030-r4'")
    text=replace_once(text,"seconds=min(21600, max(1, int(store.value['deadline'] - time.time())))","seconds=None")
    text=replace_once(text,"                    print('CLOB_READ_BATCH_SIZE=' + str(clob_batch_size), flush=True)",
        "                    print('CLOB_READ_BATCH_SIZE=' + str(clob_batch_size), flush=True)\n"
        "                    print('LOAD_INVOCATION_CAP=NONE; ORIGINAL_JOB_DEADLINE=' + str(store.value['deadline']), flush=True)")
    files['existing_client.py']=text.encode()
    pins=json.loads(files['client/CODE_PINS.json'])
    for n in pins['files']:pins['files'][n]=sha(files['client/'+n])
    files['client/CODE_PINS.json']=(json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
    files['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    changed=[n for n in files if files[n]!=old[n]]
    assert set(changed)=={full,'existing_client.py','client/CODE_PINS.json','PACKAGE_FILES.json'}
    with zipfile.ZipFile(HERE/PACKAGE,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(files.items()):
            assert not name.lower().endswith(('.zip','.js','.jsx','.mjs','.cjs'))
            if name.endswith('.py'):ast.parse(raw,feature_version=(3,9))
            entry=zipfile.ZipInfo(name,(2026,10,30,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
            z.writestr(entry,raw)
    notebook=(BASE/'DATAIKU_EXISTING_NFS_RUN_R3.txt').read_text()
    notebook=notebook.replace(basezip.name,PACKAGE).replace(sha(basezip.read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    notebook=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),notebook)
    notebook=notebook.replace('이 R3 셀','이 R4 셀').replace('캐시된 R2','캐시된 이전').replace('R3를 읽습니다','R4를 읽습니다').replace('기존 R2 적재','기존 적재')
    notebook=notebook.replace("ACTION = 'check' # check → transfer → load, 상태만 확인: status", "ACTION = 'check' # 기존 이관 재개: check 확인 후 load. transfer 재실행 불필요")
    notebook='# R4: 적재 1회 6시간 제한 없음. 기존 최초 작업 기한/누적 호출 예산은 유지합니다.\n'+notebook
    ast.parse(notebook,feature_version=(3,9));(HERE/NOTEBOOK).write_text(notebook)
    report=dict(base_zip_sha256=sha(basezip.read_bytes()),changed_files=changed,preserved_files=len(files)-len(changed),
        checkpoint_directory='oracle-import-r2',compatible_checkpoint_origin_sha256=PREVIOUS_FULL_SHA,
        execution_full_sha256=sha(files[full]),invocation_cap_seconds=None,original_deadline_preserved=True,
        files={n:dict(sha256=sha((HERE/n).read_bytes()),bytes=(HERE/n).stat().st_size) for n in (PACKAGE,NOTEBOOK)})
    (HERE/'BUILD.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({n:sha(b) for n,b in files.items()},sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':build()

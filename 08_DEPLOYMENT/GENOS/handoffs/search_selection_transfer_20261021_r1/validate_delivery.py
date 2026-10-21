"""Run the sealed bash commands against tiny synthetic generations, sequentially."""
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_SEARCH_SELECTION_TRANSFER_20261021_R1'
ZIPNAME = 'GENOS_LATEST_SELECTION_DATA_20261021_R1.zip'
OUT = Path(tempfile.mkdtemp(prefix='validation-runtime-', dir=HERE))
sys.path[:0] = [str(ROOT/'02_BACKEND'), str(ROOT/'05_TESTS/CONTRACTS')]
from test_search_selection import metadata_generation
from lawrag.pipeline.search_selection import plan, activate
from semantic_runtime.contracts import sha
from semantic_runtime.search_selection import selection_path
from semantic_runtime.storage import Store

records=[]
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def fixture(tag, mode='missing'):
    base=OUT/tag;base.mkdir(exist_ok=False)
    dev=base/'DEV';dev.mkdir()
    required=list(json.loads((HERE/'CODE_MANIFEST.json').read_text())['required_existing_code'])
    required += ['02_BACKEND/lawrag/__init__.py','02_BACKEND/lawrag/pipeline/__init__.py',
                 '02_BACKEND/semantic_runtime/__init__.py','02_BACKEND/semantic_runtime/observability.py']
    for name in required:
        p=dev/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    g=metadata_generation(base,[('a','internal/규정(20240101).docx',{}),
                                ('b','internal/규정(20250101).docx',{}),
                                ('c','external/외규.docx',{'source_category':'external'})])
    write(dev/'00_SYSTEM/GENOS_SERVING_PATHS.json',{'schema_version':'genos-serving-paths-v1',
          'selection':'operator-fixed','generation':str(g),'runtime':str(base/'runtime'),
          'generation_manifest_sha256':sha(g/'manifest.json')})
    if mode!='missing':activate(plan(g,latest=mode=='v2',exceptions=dev/'00_SYSTEM/FILENAME_EXCEPTIONS.json' if mode=='v2' else None))
    package=base/'TRANSFER';package.mkdir()
    with zipfile.ZipFile(HERE/(NAME+'.zip')) as z:z.extractall(package)
    return {'base':base,'dev':dev,'g':g,'package':package,'target':selection_path(g),
            'store':sha(g/'store.sqlite'),'manifest':sha(g/'manifest.json')}

def run(f,script,args=(),fail=None):
    env={k:v for k,v in os.environ.items() if not k.startswith(('GENOS_','SEMANTIC_')) and k not in {'PYTHONPATH','DP'}}
    env.update(PATH=str(ROOT/'.venv/bin')+':'+env.get('PATH',''),PYTHONDONTWRITEBYTECODE='1',GENOS_AUTO_WARMUP='0')
    cmd=['bash',str(f['package']/script),*args,'--root',str(f['dev']),'--generation',str(f['g'])]
    p=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45)
    (OUT/('command-%03d.log'%len(records))).write_text(p.stdout)
    record={'scenario':f['base'].name,'script':script,'action':list(args),'exit':p.returncode,'expected_failure':fail}
    records.append(record)
    write(HERE/'DELIVERY_TRACE.json',records)
    if fail:
        assert p.returncode!=0 and fail in p.stdout,(record,p.stdout)
    else:assert p.returncode==0,(record,p.stdout)
    assert sha(f['g']/'store.sqlite')==f['store'] and sha(f['g']/'manifest.json')==f['manifest']
    assert 'TRANSFER_EXIT=' in p.stdout
    return p.stdout

for file in ('BUILD_DEV_ZIP.txt','RESTORE_NFS.txt'):
    subprocess.run(['bash','-n',str(HERE/file)],check=True)

f=fixture('missing')
run(f,'BUILD_DEV_ZIP.txt');assert not f['target'].exists()
ziphash=sha(f['dev']/ZIPNAME)
run(f,'BUILD_DEV_ZIP.txt');assert sha(f['dev']/ZIPNAME)==ziphash
run(f,'RESTORE_NFS.txt',['check']);assert not f['target'].exists()
run(f,'RESTORE_NFS.txt');assert f['target'].exists()
assert f['target'].stat().st_mode & 0o777 == f['g'].joinpath('manifest.json').stat().st_mode & 0o777
with closing(Store(f['g'],verify=False)) as s:
    s.selection.require_latest();assert [r[0] for r in s.db.execute('SELECT document_id FROM document ORDER BY document_id')]==['b','c']
run(f,'RESTORE_NFS.txt');run(f,'RESTORE_NFS.txt',['status'])
run(f,'BUILD_DEV_ZIP.txt');assert sha(f['dev']/ZIPNAME)==ziphash
state=f['dev']/ZIPNAME.replace('.zip','.apply-state.json')
value=json.loads(state.read_text());receipt=Path(value['receipt'])
value.update(state='PREPARED',receipt=None);write(state,value)
rr=json.loads(receipt.read_text());rr['state']='PREPARED';write(receipt,rr)
run(f,'RESTORE_NFS.txt');assert json.loads(state.read_text())['receipt']==str(receipt)
run(f,'RESTORE_NFS.txt',['rollback']);assert not f['target'].exists()
run(f,'RESTORE_NFS.txt',['rollback'])
run(f,'RESTORE_NFS.txt',fail='was rolled back')

f=fixture('legacy','legacy');f['target'].chmod(0o640);before=f['target'].read_bytes()
run(f,'BUILD_DEV_ZIP.txt');assert f['target'].read_bytes()==before
run(f,'RESTORE_NFS.txt');assert json.loads(f['target'].read_text())['schema_version'].endswith('-v2')
assert f['target'].stat().st_mode & 0o777 == 0o640
run(f,'RESTORE_NFS.txt',['rollback']);assert f['target'].read_bytes()==before
assert f['target'].stat().st_mode & 0o777 == 0o640

f=fixture('already_latest','v2');before=f['target'].read_bytes()
run(f,'BUILD_DEV_ZIP.txt');run(f,'RESTORE_NFS.txt');assert f['target'].read_bytes()==before
run(f,'RESTORE_NFS.txt',['rollback'],fail='no owned apply receipt')

f=fixture('code_drift');p=f['dev']/'02_BACKEND/semantic_runtime/search_selection.py';p.write_text(p.read_text()+'\n')
run(f,'BUILD_DEV_ZIP.txt',fail='differs from tested code');assert not f['target'].exists()

f=fixture('wrong_selection');p=f['dev']/'00_SYSTEM/GENOS_SERVING_PATHS.json';v=json.loads(p.read_text());v['generation']=str(f['base']);write(p,v)
run(f,'BUILD_DEV_ZIP.txt',fail='differs from current DEV serving selection');assert not f['target'].exists()

f=fixture('zip_traversal');run(f,'BUILD_DEV_ZIP.txt')
with zipfile.ZipFile(f['dev']/ZIPNAME,'a') as z:z.writestr('../escape','wrong')
run(f,'RESTORE_NFS.txt',fail='unexpected ZIP members');assert not f['target'].exists()

f=fixture('zip_hash');run(f,'BUILD_DEV_ZIP.txt')
with zipfile.ZipFile(f['dev']/ZIPNAME) as z:members={n:z.read(n) for n in z.namelist()}
members['generation.json']+=b' '
with zipfile.ZipFile(f['dev']/ZIPNAME,'w') as z:
    for n,raw in members.items():z.writestr(n,raw)
run(f,'RESTORE_NFS.txt',fail='ZIP hash/version mismatch');assert not f['target'].exists()

f=fixture('nfs_drift');run(f,'BUILD_DEV_ZIP.txt')
f['target'].parent.mkdir(exist_ok=True);f['target'].write_text('{}\n')
run(f,'RESTORE_NFS.txt',fail='NFS selection changed');assert f['target'].read_text()=='{}\n'

f=fixture('symlink');f['target'].parent.mkdir(exist_ok=True);other=f['base']/'other.json';other.write_text('{}')
f['target'].symlink_to(other)
run(f,'BUILD_DEV_ZIP.txt',fail='symlink path refused');assert other.read_text()=='{}'

f=fixture('package_drift');p=f['package']/'transfer.py';p.write_text(p.read_text()+'\n')
run(f,'BUILD_DEV_ZIP.txt',fail='Package file differs');assert not f['target'].exists()

f=fixture('concurrent')
lock=(f['dev']/ZIPNAME).with_suffix('.transfer.lock')
with lock.open('a') as stream:
    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
    run(f,'BUILD_DEV_ZIP.txt',fail='BlockingIOError')
run(f,'BUILD_DEV_ZIP.txt');assert not f['target'].exists()

f=fixture('different_dev_path');run(f,'BUILD_DEV_ZIP.txt')
other=f['base']/'DEV-DEPLOYED';shutil.copytree(f['dev'],other)
f['dev']=other
run(f,'RESTORE_NFS.txt')
assert json.loads(f['target'].read_text())['exceptions']['path']==str(other/'00_SYSTEM/FILENAME_EXCEPTIONS.json')
run(f,'RESTORE_NFS.txt',['rollback']);assert not f['target'].exists()

f=fixture('metadata_changed');run(f,'BUILD_DEV_ZIP.txt')
with sqlite3.connect(f['g']/'store.sqlite') as db:db.execute("UPDATE document SET name='changed' WHERE document_id='a'")
f['store']=sha(f['g']/'store.sqlite')
run(f,'RESTORE_NFS.txt',fail='does not match current metadata');assert not f['target'].exists()

f=fixture('stale_selection');f['target'].parent.mkdir(exist_ok=True)
bad=plan(f['g'],latest=True);bad['store_sha256']='0'*64;write(f['target'],bad)
run(f,'BUILD_DEV_ZIP.txt',fail='stale or invalid search selection binding')

print(json.dumps({'status':'PASS','commands':len(records),'expected_rejections':sum(bool(r['expected_failure']) for r in records),
                  'zip_sha256':sha(HERE/(NAME+'.zip'))},ensure_ascii=False))
write(HERE/'DELIVERY_VALIDATION.json',{'status':'PASS','commands':len(records),
    'expected_rejections':sum(bool(r['expected_failure']) for r in records),
    'zip_sha256':sha(HERE/(NAME+'.zip')),'field_execution':'NOT_RUN','trace':'DELIVERY_TRACE.json'})

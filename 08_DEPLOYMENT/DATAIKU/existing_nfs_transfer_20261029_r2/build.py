"""Client-only correction from the sealed R1; leave server and old receipts intact."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.with_name('existing_nfs_transfer_20261029_r1')
PACKAGE = 'DATAIKU_EXISTING_NFS_CLIENT_20261029_R2.zip'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    assert not (HERE/'SEALED.json').exists(), 'Preserve sealed delivery'
    oldzip = BASE/'DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip'
    assert sha(oldzip.read_bytes()) == '77d8b42038df3475d121f8f64ad465389cda15a5558de21f7d9417371efc099d'
    with zipfile.ZipFile(oldzip) as z:
        old = {n: z.read(n) for n in z.namelist()}
    oldpins = json.loads(old['PACKAGE_FILES.json'])
    assert all(sha(old[n]) == h for n,h in oldpins.items())
    files = dict(old)
    for name in ('oracle_query_publish.py', 'oracle_full_package.py'):
        rel = '02_BACKEND/lawrag/pipeline/'+name
        files['client/'+rel] = (ROOT/rel).read_bytes()
    files['existing_client.py'] = (HERE/'existing_client.py').read_bytes()
    pins = json.loads(files['client/CODE_PINS.json'])
    for n in pins['files']:
        pins['files'][n] = sha(files['client/'+n])
    files['client/CODE_PINS.json'] = (json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
    files['PACKAGE_FILES.json'] = (json.dumps({n:sha(b) for n,b in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    with zipfile.ZipFile(HERE/PACKAGE, 'w', zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            if n.endswith('.py'): ast.parse(b,feature_version=(3,9))
            info = zipfile.ZipInfo(n,(2026,10,29,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644 << 16; z.writestr(info,b)
    notebook = (BASE/'DATAIKU_EXISTING_NFS_RUN.txt').read_text()
    notebook = notebook.replace(oldzip.name, PACKAGE)
    notebook = notebook.replace(sha(oldzip.read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    notebook = re.sub(r'PACKAGE_BYTES = \d+', 'PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),notebook)
    oldtail = "sys.path[:0] = [str(root), str(root/'client'), str(root/'client/02_BACKEND')]\nimport existing_client"
    newtail = '''# Restart the kernel when changing from R1; never run cached old modules.
for module, relative in {
    'existing_client': 'existing_client.py',
    'lawrag.pipeline.oracle_full_package': 'client/02_BACKEND/lawrag/pipeline/oracle_full_package.py',
    'lawrag.pipeline.oracle_query_publish': 'client/02_BACKEND/lawrag/pipeline/oracle_query_publish.py',
}.items():
    loaded = sys.modules.get(module)
    if loaded is not None and (
        not getattr(loaded, '__file__', None) or
        hashlib.sha256(Path(loaded.__file__).read_bytes()).hexdigest() !=
        hashlib.sha256((root/relative).read_bytes()).hexdigest()
    ):
        raise RuntimeError('R1 코드가 커널에 남아 있습니다. Kernel > Restart 후 이 R2 셀만 실행하세요.')
sys.path[:0] = [str(root), str(root/'client'), str(root/'client/02_BACKEND')]
import existing_client'''
    assert notebook.count(oldtail)==1
    notebook=notebook.replace(oldtail,newtail)
    ast.parse(notebook,feature_version=(3,9))
    (HERE/'DATAIKU_EXISTING_NFS_RUN_R2.txt').write_text(notebook)
    changes = [n for n,b in files.items() if b != old.get(n)]
    assert set(changes)=={'client/02_BACKEND/lawrag/pipeline/oracle_query_publish.py',
        'client/02_BACKEND/lawrag/pipeline/oracle_full_package.py', 'existing_client.py',
        'client/CODE_PINS.json','PACKAGE_FILES.json'}
    report = {'baseline_zip_sha256':sha(oldzip.read_bytes()),
        'changed_files':changes,'preserved_files':len(files)-len(changes),
        'server_code_sha256':files['COMPUTE_CODE_SHA256.txt'].decode().strip(),
        'generation':'/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation',
        'field_generation_manifest_sha256':None,'field_commit':None,'field_revision':None,
        'main_changed':False,'server_changed':False,
        'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size}
                 for n in (PACKAGE,'DATAIKU_EXISTING_NFS_RUN_R2.txt')},
        'code_files':{n:sha(files[n]) for n in changes}}
    (HERE/'BUILD.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__': build()

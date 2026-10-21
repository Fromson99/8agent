"""Seal the reviewed six-file field delta; never read mutable workspace code."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
NAME='GENOS_SEARCH_LATEST_20261015_R2'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def archive(files):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,10,15,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,raw)
    return buffer.getvalue()

def main():
    inputs=json.loads((HERE/'PATCH_INPUTS.json').read_bytes())
    files={r['path']:(HERE/'payload'/r['path']).read_bytes() for r in inputs['files']}
    for row in inputs['files']:
        assert sha(files[row['path']])==row['after']
        compile(files[row['path']],row['path'],'exec')
    manifest={'format':'8agent-code/1','scope':NAME,
        'files':[{'path':r['path'],'sha256':r['after'],'bytes':len(files[r['path']])} for r in inputs['files']],
        'required_files':inputs['required_files']}
    code=archive({'CODE_MANIFEST.json':encode(manifest),**files})
    spec={'version':NAME,'files':inputs['files'],'manifest':manifest,'code_zip_sha256':sha(code)}
    static={'CODE.zip':code,'CODE_MANIFEST.json':encode(manifest),'PATCH_SPEC.json':encode(spec)}
    static.update({n:(HERE/n).read_bytes() for n in ('apply.py','run.py','smoke_check.py','GUIDE_UTF8.txt')})
    packed=archive(static);encoded=base64.b64encode(packed).decode()
    # The standalone TXT and ZIP entry use exactly the same sealed code. State
    # and receipts live in TRANSFER so either delivery route can resume safely.
    script='''#!/usr/bin/env bash
set -euo pipefail
SEARCH_LOG="./search-latest-r2-$(date +%Y%m%dT%H%M%S)-$$.log"
exec > >(tee -a "$SEARCH_LOG") 2>&1
trap 'rc=$?; echo "SEARCH_LATEST_R2 EXIT=$rc LOG=$SEARCH_LOG"; exit "$rc"' EXIT
printf 'TRANSFER=%s\\n' "$PWD"
python3 - "$@" <<'PYTHON_SEARCH_R2'
import base64,hashlib,io,os,pathlib,subprocess,sys,zipfile
raw=base64.b64decode("""ENCODED""")
if hashlib.sha256(raw).hexdigest()!='DIGEST':raise ValueError('embedded delivery changed')
root=pathlib.Path.cwd()/'search-latest-r2-state'
if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('runtime package path must not be a symlink')
root.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for name in z.namelist():
        if pathlib.PurePosixPath(name).name!=name:raise ValueError('unsafe delivery member')
        path=root/name;data=z.read(name)
        if path.is_symlink():raise ValueError('delivery member symlink refused')
        if path.exists():
            if path.read_bytes()!=data:raise ValueError('delivery member changed: '+name)
        else:
            with path.open('xb') as stream:stream.write(data)
print('PACKAGE='+str(root),flush=True)
result=subprocess.run([sys.executable,str(root/'run.py'),*sys.argv[1:]],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
raise SystemExit(result.returncode)
PYTHON_SEARCH_R2
'''.replace('ENCODED',encoded).replace('DIGEST',sha(packed))
    members={**static,NAME+'_RUN.txt':script.encode()}
    for name,raw in members.items():(HERE/name).write_bytes(raw)
    delivery=archive(members)
    (HERE/(NAME+'.zip')).write_bytes(delivery)
    (HERE/'BUILD_RESULT.json').write_bytes(encode({'zip_sha256':sha(delivery),'code_zip_sha256':sha(code),
        'runtime_package_sha256':sha(packed),'product_files':len(files),'standalone_script_complete':True}))
    print('SEALED '+NAME+' '+sha(delivery))

if __name__=='__main__':main()

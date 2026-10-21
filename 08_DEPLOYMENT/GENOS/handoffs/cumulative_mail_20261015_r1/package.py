"""Build reproducible ZIP + complete standalone TXT from the verified sources."""
import base64,gzip,hashlib,io,json,subprocess,zipfile
from copy import deepcopy
from pathlib import Path

HERE=Path(__file__).resolve().parent;NAME='GENOS_CUMULATIVE_MAIL_20261015_R1'
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def pack(files):
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,raw in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,10,15,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    return f.getvalue()
def main():
    spec=json.loads(gzip.decompress((HERE/'PATCH_SPEC.json.gz').read_bytes()));compact=deepcopy(spec)
    records=[];lookup={}
    for state in compact['signatures'].values():
        refs=[]
        for n,r in state.pop('patches').items():
            key=(n,r['before_sha256'],r['after_sha256'])
            if key not in lookup:lookup[key]=len(records);records.append(key)
            refs.append(lookup[key])
        state['patch_refs']=refs
    compact['patch_records']=records
    (HERE/'BUNDLE_SPEC.json.gz').write_bytes(gzip.compress(enc(compact),mtime=0))
    from spec_loader import load
    assert load()==spec
    names=['apply_patch.py','run.py','spec_loader.py','BUNDLE_SPEC.json.gz','search_smoke.py','WORKFLOW_PASTE_ALL.txt','GUIDE_UTF8.txt','MAIL_COVERAGE.json']
    files={n:(HERE/n).read_bytes() for n in names};raw=pack(files)
    shell='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_logs="./cumulative-mail-r1-logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "CUMULATIVE_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_log.exit"' EXIT
printf 'TRANSFER=%s\\n' "$PWD"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
python3 - "$@" <<'CUMULATIVE_MAIL_PY'
import base64,hashlib,io,os,pathlib,subprocess,sys,zipfile
raw=base64.b64decode('PAYLOAD')
if hashlib.sha256(raw).hexdigest()!='SHA':raise ValueError('embedded package changed')
root=pathlib.Path.cwd()/'cumulative-mail-r1-state'
if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('package path symlink refused')
root.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for name in z.namelist():
        if pathlib.PurePosixPath(name).name!=name:raise ValueError('unsafe package member')
        path=root/name;value=z.read(name)
        if path.is_symlink():raise ValueError('package file symlink refused')
        if path.exists():
            if path.read_bytes()!=value:raise ValueError('package file changed: '+name)
        else:
            with path.open('xb') as f:f.write(value)
print('PACKAGE='+str(root),flush=True)
result=subprocess.run([sys.executable,str(root/'run.py'),*sys.argv[1:]],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
raise SystemExit(result.returncode)
CUMULATIVE_MAIL_PY
'''.replace('PAYLOAD',base64.b64encode(raw).decode()).replace("'SHA'",repr(sha(raw)))
    txt=HERE/(NAME+'_RUN.txt');txt.write_text(shell)
    subprocess.run(['bash','-n',str(txt)],check=True)
    (HERE/(NAME+'.zip')).write_bytes(pack({**files,NAME+'_RUN.txt':shell.encode()}))
    (HERE/'PACKAGE_BINDING.json').write_bytes(enc({'version':NAME,'archive_sha256':sha((HERE/(NAME+'.zip')).read_bytes()),
        'run_sha256':sha(txt.read_bytes()),'runtime_sha256':sha(raw),'files':{n:sha(b) for n,b in files.items()},
        'expanded_spec_sha256':sha(enc(spec)),'lossless_spec_interning':True,'recursive_disallowed_extensions':[]}))
    print('ZIP', (HERE/(NAME+'.zip')).stat().st_size,'RUN',txt.stat().st_size,'spec',len(enc(compact)))
if __name__=='__main__':main()

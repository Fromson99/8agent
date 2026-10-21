"""Build reproducible ZIP + complete standalone TXT from the verified sources."""
import base64,gzip,hashlib,io,json,subprocess,zipfile
from copy import deepcopy
from pathlib import Path

HERE=Path(__file__).resolve().parent;NAME='GENOS_LATEST_SELECTION_20261015_R1'
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def pack(files):
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,raw in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,10,15,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    return f.getvalue()
def main():
    names=['installer.py','base_installer.py','compose.py','run.py','PAYLOAD.zip','PAYLOAD_MANIFEST.json','BASE_SPEC.json.gz','search_smoke.py','comparison.py','GUIDE_UTF8.txt']
    files={n:(HERE/n).read_bytes() for n in names};raw=pack(files)
    shell='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_logs="./latest-selection-r1-logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "LATEST_SELECTION_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_log.exit"' EXIT
printf 'TRANSFER=%s\\n' "$PWD"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
export LATEST_EXCEPTIONS_FILE="${LATEST_EXCEPTIONS_FILE:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/FILENAME_EXCEPTIONS.json}"
python3 - "$@" <<'LATEST_SELECTION_MAIL_PY'
import base64,hashlib,io,os,pathlib,subprocess,sys,zipfile
raw=base64.b64decode('PAYLOAD')
if hashlib.sha256(raw).hexdigest()!='SHA':raise ValueError('embedded package changed')
root=pathlib.Path.cwd()/'latest-selection-r1-state'
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
LATEST_SELECTION_MAIL_PY
'''.replace('PAYLOAD',base64.b64encode(raw).decode()).replace("'SHA'",repr(sha(raw)))
    txt=HERE/(NAME+'_RUN.txt');txt.write_text(shell)
    subprocess.run(['bash','-n',str(txt)],check=True)
    (HERE/(NAME+'.zip')).write_bytes(pack({**files,'FILENAME_EXCEPTIONS.json':(HERE/'FILENAME_EXCEPTIONS.json').read_bytes(),NAME+'_RUN.txt':shell.encode()}))
    (HERE/'PACKAGE_BINDING.json').write_bytes(enc({'version':NAME,'archive_sha256':sha((HERE/(NAME+'.zip')).read_bytes()),
        'run_sha256':sha(txt.read_bytes()),'runtime_sha256':sha(raw),'files':{n:sha(b) for n,b in files.items()},
        'policy_sha256':sha((HERE/'FILENAME_EXCEPTIONS.json').read_bytes()),'recursive_disallowed_extensions':[]}))
    print('ZIP', (HERE/(NAME+'.zip')).stat().st_size,'RUN',txt.stat().st_size)
if __name__=='__main__':main()

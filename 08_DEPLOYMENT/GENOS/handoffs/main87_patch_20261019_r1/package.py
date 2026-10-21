"""Seal the full ZIP and a standalone RUN TXT with the same payload."""
import ast,base64,json,subprocess,zlib
from pathlib import Path
from build import H,NAME,sha,enc,pack

def main():
    if (H/'SEALED.json').exists():raise RuntimeError('Preserve the sealed delivery; use a new revision')
    source=json.loads((H/'SOURCE_BINDING.json').read_bytes())
    spec={'version':NAME,'code_zip_sha256':source['code_zip_sha256'],
          'main_release':source['main_basis']['release_id'],'main_generation':source['main_basis']['pointer_generation'],
          'policy_sha256':sha((H/'FILENAME_EXCEPTIONS.json').read_bytes())}
    (H/'PACKAGE_SPEC.json').write_bytes(enc(spec))
    names=['run.py','replace.py','code_smoke.py','code.zip','PACKAGE_SPEC.json','FILENAME_EXCEPTIONS.json']
    files={n:(H/n).read_bytes() for n in names};raw=pack(files)
    shell='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_logs="./main87-patch-r1-logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "MAIN_FULL_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_log.exit"' EXIT
printf 'TRANSFER=%s\\n' "$PWD"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
python3 - "$@" <<'MAIN_FULL_MAIL_PY'
import base64,hashlib,io,os,pathlib,subprocess,sys,zipfile
raw=base64.b64decode('EMBEDDED_BYTES')
if hashlib.sha256(raw).hexdigest()!='EMBEDDED_SHA':raise ValueError('embedded package changed')
root=pathlib.Path.cwd()/'main87-patch-r1-state'
if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('state path symlink refused')
root.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for name in z.namelist():
        if pathlib.PurePosixPath(name).name!=name:raise ValueError('unsafe embedded package member')
        path=root/name;value=z.read(name)
        if path.is_symlink():raise ValueError('state file symlink refused')
        if path.exists():
            if path.read_bytes()!=value:raise ValueError('state package changed: '+name)
        else:
            with path.open('xb') as f:f.write(value)
print('PACKAGE='+str(root),flush=True)
result=subprocess.run([sys.executable,str(root/'run.py'),*sys.argv[1:]],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
raise SystemExit(result.returncode)
MAIN_FULL_MAIL_PY
'''.replace('EMBEDDED_BYTES',base64.b64encode(raw).decode()).replace('EMBEDDED_SHA',sha(raw))
    txt=H/(NAME+'_RUN.txt');txt.write_text(shell)
    subprocess.run(['bash','-n',str(txt)],check=True)
    # The separate GENOS workflow editor needs the same consumer plus its
    # existing stdlib logging support, even when no backend modules are importable.
    import zipfile
    with zipfile.ZipFile(H/'code.zip') as z:
        diag=z.read('genos_diagnostics.py');workflow=z.read('08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    bootstrap=("import base64,hashlib,sys,types,zlib\n"+
        f"_d=zlib.decompress(base64.b64decode({base64.b64encode(zlib.compress(diag,9)).decode()!r}))\n"+
        f"assert hashlib.sha256(_d).hexdigest()=={sha(diag)!r}\n"+
        "_m=types.ModuleType('genos_diagnostics');_m.__file__='genos_diagnostics.py';sys.modules['genos_diagnostics']=_m\nexec(compile(_d,_m.__file__,'exec'),_m.__dict__)\n")
    paste=bootstrap.encode()+workflow;ast.parse(paste,feature_version=(3,10))
    workflow_name=NAME+'_WORKFLOW_PASTE_ALL.txt';(H/workflow_name).write_bytes(paste)
    # The standalone RUN already contains every executable/code ZIP byte.
    # Avoid a second copy of those same bytes in the transfer archive.
    outer={NAME+'_RUN.txt':shell.encode(),workflow_name:paste,
           'FILENAME_EXCEPTIONS.json':(H/'FILENAME_EXCEPTIONS.json').read_bytes(),
           'GUIDE_UTF8.txt':(H/'GUIDE_UTF8.txt').read_bytes(),'SOURCE_BINDING.json':(H/'SOURCE_BINDING.json').read_bytes(),
           'GENOS_OVERLAYS.diff':(H/'GENOS_OVERLAYS.diff').read_bytes()}
    for n in ('VALIDATION.json','CHANGE_CONTRACT.txt','FIELD_EVIDENCE.json','PYTHON311_CHECK.json'):
        if (H/n).is_file():outer[n]=(H/n).read_bytes()
    (H/(NAME+'.zip')).write_bytes(pack(outer))
    records={n:{'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in [NAME+'.zip',NAME+'_RUN.txt',workflow_name,'GUIDE_UTF8.txt','FILENAME_EXCEPTIONS.json']}
    (H/'PACKAGE_BINDING.json').write_bytes(enc({'version':NAME,'runtime_sha256':sha(raw),'files':records,'main_basis':source['main_basis']}))
    (H/'SHA256SUMS.txt').write_text(''.join(v['sha256']+'  '+n+'\n' for n,v in records.items()))
    print(json.dumps({n:v['bytes'] for n,v in records.items()}))

if __name__=='__main__':main()

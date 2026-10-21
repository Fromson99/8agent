"""Seal the reviewed logging delta and a complete standalone TRANSFER runner."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

H = Path(__file__).resolve().parent
NAME = 'GENOS_ORACLE_LOGGING_20261019_R1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pack(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    return buffer.getvalue()


def main():
    if (H/'SEALED.json').exists():
        raise RuntimeError('This delivery is sealed; use a new revision')
    runtime = {str(p.relative_to(H)): p.read_bytes() for p in (H/'payload').rglob('*') if p.is_file()}
    runtime.update({n: (H/n).read_bytes() for n in ('PATCH_SPEC.json', 'install.py', 'code_smoke.py')})
    raw = pack(runtime)
    script = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_logs="./oracle-logging-r1-logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "ORACLE_LOGGING_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_log.exit"' EXIT
printf 'TRANSFER=%s\\n' "$PWD"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
python3 - "$@" <<'ORACLE_LOGGING_PY'
import base64,hashlib,io,os,pathlib,subprocess,sys,zipfile
raw=base64.b64decode('EMBEDDED')
if hashlib.sha256(raw).hexdigest()!='DIGEST':raise ValueError('embedded patch changed')
root=pathlib.Path.cwd()/'oracle-logging-r1-state'
if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('state symlink')
root.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for name in z.namelist():
        p=pathlib.PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\\\' in name:raise ValueError('unsafe package')
        target=root/name;value=z.read(name)
        if any(p.is_symlink() for p in (target,*target.parents)):raise ValueError('state symlink')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=value:raise ValueError('state bytes differ: '+name)
        else:target.write_bytes(value)
raise SystemExit(subprocess.run([sys.executable,str(root/'install.py'),*sys.argv[1:]],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}).returncode)
ORACLE_LOGGING_PY
'''.replace('EMBEDDED', base64.b64encode(raw).decode()).replace("'DIGEST'", repr(sha(raw)))
    runner = NAME + '_RUN.txt'
    (H/runner).write_text(script)
    subprocess.run(['bash', '-n', H/runner], check=True)
    outer = {**runtime, runner: script.encode(), 'GUIDE_UTF8.txt': (H/'GUIDE_UTF8.txt').read_bytes(),
             'CHANGE_CONTRACT.txt': (H/'CHANGE_CONTRACT.txt').read_bytes()}
    (H/(NAME+'.zip')).write_bytes(pack(outer))
    records = {n: {'sha256': sha((H/n).read_bytes()), 'bytes': (H/n).stat().st_size}
               for n in (NAME+'.zip', runner, 'GUIDE_UTF8.txt')}
    (H/'PACKAGE_BINDING.json').write_text(json.dumps(records, indent=2)+'\n')
    print(json.dumps(records))


if __name__ == '__main__':
    main()

"""Build the two-command delivery; never sends mail or edits product code."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_SEARCH_SELECTION_TRANSFER_20261021_R1'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

files = ['02_BACKEND/lawrag/pipeline/search_selection.py',
         '02_BACKEND/semantic_runtime/search_selection.py',
         '02_BACKEND/semantic_runtime/filename_versions.py',
         '02_BACKEND/semantic_runtime/contracts.py',
         '02_BACKEND/semantic_runtime/storage.py',
         '02_BACKEND/semantic_runtime/deployment_paths.py',
         '02_BACKEND/semantic_runtime/resident_data.py',
         '02_BACKEND/semantic_runtime/query_latency.py',
         '00_SYSTEM/FILENAME_EXCEPTIONS.json']
write(HERE/'CODE_MANIFEST.json', {'format': 'existing-code-read-only-v1',
    'code_modified': False, 'required_existing_code': {p: sha(ROOT/p) for p in files}})
payload = ['transfer.py', 'GUIDE_UTF8.txt', 'CODE_MANIFEST.json']
write(HERE/'PACKAGE.json', {'version': NAME, 'files': {p: sha(HERE/p) for p in payload}})
package_hash = sha(HERE/'PACKAGE.json')
launcher = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
TASK_PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
mkdir -p "$TASK_PACKAGE_DIR/logs"
TASK_LOG="$TASK_PACKAGE_DIR/logs/@@KIND@@-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_EXIT=$?; trap - EXIT; echo "TRANSFER_EXIT=$TASK_EXIT LOG=$TASK_LOG"; exit "$TASK_EXIT"' EXIT
echo "TRANSFER_START=$(date -u +%FT%TZ) LOG=$TASK_LOG"
export PYTHONDONTWRITEBYTECODE=1
python3 - "$TASK_PACKAGE_DIR" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]); h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
if h(p/'PACKAGE.json')!='@@HASH@@': raise SystemExit('PACKAGE hash mismatch; preserved')
for name,digest in json.loads((p/'PACKAGE.json').read_text())['files'].items():
    if h(p/name)!=digest: raise SystemExit('Package file differs: '+name)
print('PACKAGE_VERIFIED PYTHON='+sys.executable+' VERSION='+sys.version)
PY
@@ACTION@@
'''
for name, kind, action in [
    ('BUILD_DEV_ZIP.txt', 'build', 'python3 "$TASK_PACKAGE_DIR/transfer.py" build "$@"'),
    ('RESTORE_NFS.txt', 'restore', '''TASK_ACTION=apply
if [[ "${1:-}" == check || "${1:-}" == status || "${1:-}" == rollback || "${1:-}" == apply ]]; then
    TASK_ACTION="$1"
    shift
fi
python3 "$TASK_PACKAGE_DIR/transfer.py" "$TASK_ACTION" "$@"''')]:
    (HERE/name).write_text(launcher.replace('@@HASH@@', package_hash).replace('@@KIND@@',kind).replace('@@ACTION@@',action))
members = [*payload, 'PACKAGE.json', 'BUILD_DEV_ZIP.txt', 'RESTORE_NFS.txt', 'VALIDATION.txt']
with zipfile.ZipFile(HERE/(NAME+'.zip'), 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for name in members:
        info=zipfile.ZipInfo(name, date_time=(2026,10,21,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(HERE/name).read_bytes())
    assert z.testzip() is None
    assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
write(HERE/'SEALED.json', {'version':NAME,'files':{n:sha(HERE/n) for n in [*members,NAME+'.zip']},
    'field_execution':'NOT_RUN','serving_revision':'UNKNOWN'})
print(json.dumps({'zip':str(HERE/(NAME+'.zip')),'bytes':(HERE/(NAME+'.zip')).stat().st_size,
                  'sha256':sha(HERE/(NAME+'.zip'))}))

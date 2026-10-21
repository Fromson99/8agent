"""Seal the two-source patch and complete field commands; no mail side effects."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
NAME='GENOS_DEV_SEARCH_SELECTION_20261021_R1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
old=json.loads((HERE.parent/'search_selection_transfer_20261021_r1/CODE_MANIFEST.json').read_text())['required_existing_code']
names=['02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/lawrag/pipeline/search_selection.py']
for n in names:
    p=HERE/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
shutil.copyfile(HERE.parent/'rag_recovery_all_20261021_r2/genos_release_gate.py',HERE/'genos_release_gate.py')
write(HERE/'PATCH_SPEC.json',dict(version=NAME,required_existing_code=old,payload={n:sha(ROOT/n) for n in names}))
write(HERE/'CODE_MANIFEST.json',dict(format='8agent-code/1',scope='two-source-patch; field installer composes existing engine pins and data-specific JSON',
    files=[dict(path=n,sha256=sha(ROOT/n),bytes=(ROOT/n).stat().st_size) for n in names]))
members=['runner.py','selection_worker.py','genos_release_gate.py','PATCH_SPEC.json','CODE_MANIFEST.json','GUIDE_UTF8.txt',
    *['payload/'+n for n in names]]
write(HERE/'PACKAGE.json',dict(version=NAME,files={n:sha(HERE/n) for n in members}))
launcher='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
TASK_PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
mkdir -p "$TASK_PACKAGE_DIR/logs"
TASK_LOG="$TASK_PACKAGE_DIR/logs/run-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_EXIT=$?; trap - EXIT; echo "DEV_SELECTION_EXIT=$TASK_EXIT LOG=$TASK_LOG"; exit "$TASK_EXIT"' EXIT
echo "DEV_SELECTION_START=$(date -u +%FT%TZ) LOG=$TASK_LOG"
export PYTHONDONTWRITEBYTECODE=1
python3 - "$TASK_PACKAGE_DIR" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]); h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
if h(p/'PACKAGE.json')!='@@HASH@@':raise SystemExit('PACKAGE hash mismatch')
for name,digest in json.loads((p/'PACKAGE.json').read_text())['files'].items():
    if h(p/name)!=digest:raise SystemExit('Package file changed: '+name)
print('PACKAGE_VERIFIED PYTHON='+sys.executable+' VERSION='+sys.version)
PY
python3 "$TASK_PACKAGE_DIR/runner.py" "${@:-check}"
'''
(HERE/'RUN_DEV_SELECTION.txt').write_text(launcher.replace('@@HASH@@',sha(HERE/'PACKAGE.json')))
members+=['PACKAGE.json','RUN_DEV_SELECTION.txt']
with zipfile.ZipFile(HERE/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
    for n in members:
        info=zipfile.ZipInfo(n,(2026,10,21,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(HERE/n).read_bytes())
    assert z.testzip() is None
    assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
write(HERE/'SEALED.json',dict(version=NAME,files={n:sha(HERE/n) for n in [*members,NAME+'.zip']},
    selected_local_main_changed=False,genos_execution='NOT_RUN'))
print(json.dumps(dict(archive=str(HERE/(NAME+'.zip')),bytes=(HERE/(NAME+'.zip')).stat().st_size,sha256=sha(HERE/(NAME+'.zip')))))

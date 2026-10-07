"""Fix service bootstrap on the immutable field reference-build baseline."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1/GENOS_REFERENCE_BUILD_20261003_R1.zip'
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/compact_loader_20261006_r1'
STEM = 'GENOS_COMPACT_LOADER_20261006_R1'
GENERATION = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'


def patch(raw):
    text = raw.decode('utf-8')
    changes = {
        'manifest.get("schema_version") != "term-source-generation-v1"':
        'manifest.get("schema_version") not in {"term-source-generation-v1", "term-source-generation-v2"}',
        "manifest.get('schema_version') != 'semantic-fulltext-v2'":
        "manifest.get('schema_version') not in {'semantic-fulltext-v2', 'semantic-unit-fulltext-v1'}",
        'PeCab 1.0.8 fulltext v2 generation required;':
        'PeCab 1.0.8 fulltext v2 or unit fulltext generation required;',
    }
    for old, new in changes.items():
        if text.count(old) != 1:
            raise ValueError('Unexpected field baseline: ' + old)
        text = text.replace(old, new)
    ast.parse(text, feature_version=(3, 11))
    return text.encode('utf-8')


SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_mode="${1:-apply}"
task_logs="${GENOS_HANDOFF_LOG_DIR:-$task_dir/compact-loader-logs}"
mkdir -p "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$task_mode-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; trap - EXIT; printf "LOADER_EXIT=%s LOG=%s\n" "$task_exit" "$task_log"; exit "$task_exit"' EXIT
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
python3 - "$task_dir/__STEM__.zip" "${GENOS_DEV:-$HOME/DEV}" "$task_mode" "${2:-}" <<'LOADER_PY'
import fcntl,hashlib,importlib.util,json,os,subprocess,sys,types,zipfile
from pathlib import Path
print('PYTHON',sys.executable,sys.version.replace('\n',' '),flush=True)
if sys.version_info<(3,11):raise ValueError('Python 3.11+ required')
archive=Path(sys.argv[1]).resolve(strict=True);root=Path(sys.argv[2]).resolve(strict=True)
mode,arg=sys.argv[3:5]
def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
if sha(archive)!='__ZIP_SHA__':raise ValueError('Code ZIP hash mismatch')
with zipfile.ZipFile(archive) as z:
 manifest_raw=z.read('CODE_MANIFEST.json');manifest=json.loads(manifest_raw)
 raw=z.read('06_TOOLS/OFFLINE/genos_code_replace.py')
 row=next(r for r in manifest['files'] if r['path']=='06_TOOLS/OFFLINE/genos_code_replace.py')
 if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Installer hash mismatch')
 installer=types.ModuleType('checked_loader_installer');installer.__file__=str(archive.parent/'checked-installer.py')
 exec(compile(raw,installer.__file__,'exec'),installer.__dict__)
print('CODE_ROOT',root,'CODE_ZIP_SHA256',sha(archive),'CODE_MANIFEST_SHA256',hashlib.sha256(manifest_raw).hexdigest(),flush=True)
def pins(applied):
 for row in manifest['required_files']+manifest['files']:
  path=installer.plain(root/row['path']);path.resolve().relative_to(root)
  allowed={row['sha256']} if applied else {row['sha256'],*row.get('allowed_predecessors',[])}
  if not path.is_file() or sha(path) not in allowed:
   raise ValueError('CHECKOUT_DRIFT: '+row['path']+'; existing file preserved')
env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root),'GENOS_AUTO_WARMUP':'0'}
def selected():
 value=arg if mode in ('verify','gate') and arg else os.environ.get('GENOS_GENERATION','__GENERATION__')
 path=Path(value)
 if not path.is_absolute() or path.is_symlink() or not path.is_dir():raise ValueError('Existing absolute generation directory required')
 path=path.resolve(strict=True)
 print('GENERATION',path,'MANIFEST_SHA256',sha(path/'manifest.json'),flush=True)
 return path
def loader_check(generation):
 code="""import importlib.util,os,sys
from pathlib import Path
root=Path(sys.argv[1]);os.environ['GENOS_GENERATION']=sys.argv[2]
spec=importlib.util.spec_from_file_location('field_loader_check',root/'service/service.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
runtime=entry._runtime
code_root,generation,binding=runtime._resolve_binding()
if code_root!=root or generation!=Path(sys.argv[2]):raise ValueError('Unexpected service binding')
runtime._require_pecab_generation(generation,code_root)
print('SERVICE_LOADER_CONTRACT PASS',binding['mode'],str(generation),flush=True)
"""
 subprocess.run([sys.executable,'-c',code,str(root),str(generation)],cwd=root,env=env,check=True)
if mode in ('check','apply'):
 with installer.plain(root/'.genos-code-replacement.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);pins(False)
  installer.install(root,archive.parent,apply=mode=='apply',archive=archive)
  if mode=='apply':pins(True)
elif mode in ('verify','gate'):
 pins(True);generation=selected();loader_check(generation)
 if mode=='verify':
  subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_generation_e2e.py'),'--code-root',str(root),'--generation',str(generation)],cwd=root,env={**env,'GENOS_GENERATION':str(generation)},check=True)
 else:
  subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),'--code-zip',str(archive),'--deploy-root',str(root),'--generation',str(generation)],cwd=root,env={**env,'GENOS_GENERATION':str(generation)},check=True)
elif mode=='rollback':
 if not arg:raise ValueError('Supply exact backup path printed by apply')
 backup=installer.plain(Path(arg).resolve(strict=True))
 if Path(json.loads((backup/'receipt.json').read_text())['root']).resolve()!=root:raise ValueError('Rollback root mismatch')
 with installer.plain(root/'.genos-code-replacement.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);installer.rollback(backup)
else:raise ValueError('Modes: check apply verify gate rollback')
print('COMPLETE',mode,'ACTIVATED=False LIVE_WORKFLOW_E2E=NOT_RUN',flush=True)
LOADER_PY
'''


def main():
    def digest(raw): return hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(BASE) as z:
        parent = json.loads(z.read('CODE_MANIFEST.json'))
        old = {r['path']: r for r in parent['files'] + parent['required_files']}
        payload = {'service.py': patch(z.read('service.py')),
                   '06_TOOLS/OFFLINE/genos_code_replace.py': z.read('06_TOOLS/OFFLINE/genos_code_replace.py')}
    rows = []
    for name, raw in sorted(payload.items()):
        predecessors = {old[name]['sha256'], *old[name].get('allowed_predecessors', [])}
        rows.append({'path': name, 'role': 'code', 'sha256': digest(raw), 'bytes': len(raw),
                     'allowed_predecessors': sorted(predecessors)})
    required = [{'path': name, 'role': 'code', 'sha256': row['sha256']}
                for name, row in sorted(old.items()) if name not in payload]
    manifest = {'format': '8agent-code/1', 'id': STEM,
                'scope': 'Service bootstrap accepts source v1/v2 and PeCab article/unit fulltext; retained hash verification',
                'parent_code_zip_sha256': digest(BASE.read_bytes()), 'files': rows, 'required_files': required,
                'requires_rebuilt_generation': False, 'activated': False, 'generation_candidate': GENERATION}
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / (STEM + '.zip')
    if archive.exists(): raise ValueError('Immutable handoff exists; use a new version')
    raw_manifest = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in {**payload, 'CODE_MANIFEST.json': raw_manifest}.items():
            info = zipfile.ZipInfo(name, (2026, 10, 6, 0, 0, 0))
            info.external_attr = 0o100644 << 16; info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    script = OUT / (STEM + '_APPLY.txt')
    script.write_text(SCRIPT.replace('__STEM__', STEM).replace('__ZIP_SHA__', digest(archive.read_bytes()))
                      .replace('__GENERATION__', GENERATION))
    subprocess.run(['bash', '-n', str(script)], check=True)
    (OUT / 'CODE_MANIFEST.json').write_bytes(raw_manifest)
    record = {'code_zip_sha256': digest(archive.read_bytes()), 'code_manifest_sha256': digest(raw_manifest),
              'apply_txt_sha256': digest(script.read_bytes()), 'changed_runtime_files': ['service.py'],
              'required_files': len(required), 'field_generation_candidate': GENERATION,
              'field_commit': None, 'field_revision': None, 'genos_deployed': False,
              'generation_activated': False, 'live_workflow_e2e': 'NOT_RUN'}
    (OUT / 'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__': main()

"""Reproducible P1 patch on the verified cumulative v6 R4 code contract."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/sqlite_read_reuse_20261003_r1'
STEM = 'GENOS_SQLITE_READ_REUSE_20261003_R1'
BASE = ROOT / '08_DEPLOYMENT/GENOS/handoffs/unified_v6_cumulative_20261002_r4/CODE_MANIFEST.json'

SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_mode="${1:-check}"
task_logs="${GENOS_HANDOFF_LOG_DIR:-$task_dir/sqlite-read-reuse-logs}"
mkdir -p "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$task_mode-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; trap - EXIT; printf "HANDOFF_EXIT=%s LOG=%s\n" "$task_exit" "$task_log"; exit "$task_exit"' EXIT
python3 - "$task_dir/__STEM__.zip" "${GENOS_DEV:-$HOME/DEV}" "$task_mode" "${2:-}" "$task_log" <<'REUSE_PY'
import hashlib,json,os,subprocess,sys,types,zipfile,fcntl
from pathlib import Path
print('PYTHON',sys.executable,sys.version.replace('\n',' '),flush=True)
if sys.version_info < (3,11): raise ValueError('Python 3.11+ required')
archive=Path(sys.argv[1]).resolve(strict=True);root=Path(sys.argv[2]).resolve(strict=True)
mode,arg=sys.argv[3:5];logfile=Path(sys.argv[5]).resolve()
digest=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
if digest(archive)!='__ZIP_SHA__':raise ValueError('Code ZIP hash mismatch')
print('CODE_ROOT',root,'CODE_ZIP_SHA256',digest(archive),flush=True)
with zipfile.ZipFile(archive) as z:
 manifest_raw=z.read('CODE_MANIFEST.json');manifest=json.loads(manifest_raw)
 raw=z.read('06_TOOLS/OFFLINE/genos_code_replace.py')
 row=next(r for r in manifest['files'] if r['path']=='06_TOOLS/OFFLINE/genos_code_replace.py')
 if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Installer hash mismatch')
 installer=types.ModuleType('checked_reuse_installer');installer.__file__=str(archive.parent/'checked-installer.py')
 exec(compile(raw,installer.__file__,'exec'),installer.__dict__)
data=Path(os.environ.get('GENOS_DATA_ROOT',str(root/'01_DATA'))).resolve(strict=True)
prepared=os.environ.get('GENOS_PREPARED_RUN','financial-risk-success-20261001-r3')
run=os.environ.get('GENOS_REUSE_RUN','financial-risk-success-20261003-sqlite-r1')
def pins(applied):
 for r in manifest['required_files']+manifest['files']:
  target=installer.plain(root/r['path']);target.resolve().relative_to(root)
  allowed=[r['sha256']] if applied else [r['sha256']]+r.get('allowed_predecessors',[])
  if not target.is_file() or digest(target) not in allowed:
   raise ValueError('CHECKOUT_DRIFT: '+r['path']+'; preserve local edits and use a matching patch')
env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root)}
logdir=logfile.with_suffix('');logdir.mkdir(exist_ok=True)
selected_manifest=logdir/'CODE_MANIFEST.json';selected_manifest.write_bytes(manifest_raw)
print('CODE_MANIFEST_SHA256',digest(selected_manifest),'PREPARED_RUN',prepared,'OUTPUT_RUN',run,flush=True)
common=['--dev',str(root),'--data-root',str(data),'--prepared-run',prepared,'--run-id',run,
        '--code-manifest',str(selected_manifest),'--log-dir',str(logdir),
        '--serving','--fulltext-granularity','unit']
if os.environ.get('GENOS_COMPLETED_GLOSSARY'):
 common+=['--completed-glossary',os.environ['GENOS_COMPLETED_GLOSSARY']]
if mode in ('check','apply'):
 with installer.plain(root/'.genos-code-replacement.lock').open('a') as stream:
  fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
  pins(False)
  # Refuse known active builds. This never signals or kills another worker.
  idle="import sys; sys.path.insert(0,'06_TOOLS/OFFLINE'); import genos_reindex_runner as r; r.check_idle(sys.argv[1],sys.argv[2]); r.check_idle(sys.argv[1],sys.argv[3])"
  subprocess.run([sys.executable,'-c',idle,str(data),prepared,run],cwd=root,env=env,check=True)
  installer.install(root,archive.parent,apply=mode=='apply',archive=archive)
  if mode=='apply':pins(True)
elif mode in ('build','publish','verify'):
 pins(True)
 if mode=='verify':print('INSTALLED_BYTES_AND_DEPENDENCIES_VERIFIED',flush=True)
 else:
  command=[sys.executable,str(root/'06_TOOLS/OFFLINE/genos_reindex_runner.py'),mode,*common]
  if mode=='publish':
   shared=os.environ.get('GENOS_SHARED_ROOT')
   if not shared:raise ValueError('Set GENOS_SHARED_ROOT to an existing code-serving-visible NFS directory')
   command+=['--shared-root',shared]
  subprocess.run(command,cwd=root,env=env,check=True)
elif mode=='gate':
 pins(True)
 if arg:generation=Path(arg).resolve(strict=True)
 else:
  p=data/'TERM_RELEASES'/run/'shared-publication.json'
  if not p.is_file():raise ValueError('Publish first or supply the exact generation path as the second argument')
  generation=Path(json.loads(p.read_text())['generation_path']).resolve(strict=True)
 print('GENERATION',generation,'MANIFEST_SHA256',digest(generation/'manifest.json'),flush=True)
 subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),
  '--code-zip',str(archive),'--deploy-root',str(root),'--generation',str(generation)],cwd=root,env=env,check=True)
elif mode=='rollback':
 if not arg:raise ValueError('Supply the exact backup path printed by apply')
 backup=Path(arg).resolve(strict=True)
 if Path(json.loads((backup/'receipt.json').read_text())['root']).resolve()!=root:raise ValueError('Rollback root mismatch')
 with installer.plain(root/'.genos-code-replacement.lock').open('a') as stream:
  fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);installer.rollback(backup)
else:raise ValueError('Modes: check apply verify build publish gate rollback')
print('COMPLETE',mode,'ACTIVATED=False LIVE_WORKFLOW_E2E=NOT_RUN',flush=True)
REUSE_PY
'''


def main():
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    old = {r['path']: r for r in json.loads(BASE.read_text())['files']}
    pins = json.loads((ROOT / '09_ARTIFACTS/AUDITS/sqlite-read-implementation-20261003/ENGINE_PINS.json').read_text())
    names = set(pins['changed_code']) | {r['manifest'] for r in pins['engine_manifests']} | {
        '00_SYSTEM/PIPELINE.json', '06_TOOLS/OFFLINE/genos_code_replace.py',
        '06_TOOLS/OFFLINE/genos_reindex_only.py', '06_TOOLS/OFFLINE/genos_reindex_runner.py',
        '06_TOOLS/COMMANDS/genos_generation_e2e.py', '06_TOOLS/COMMANDS/genos_release_gate.py'}
    # Require the actual unchanged code/settings consumed by the build and runtime.
    required_names = {n for n in old if n.startswith(('00_SYSTEM/', '02_BACKEND/ENGINES/',
        '02_BACKEND/semantic_runtime/', '02_BACKEND/lawrag/core/', '02_BACKEND/lawrag/pipeline/',
        '02_BACKEND/lawrag/platform/', '02_BACKEND/PIPELINE/'))} | {
        '06_TOOLS/OFFLINE/genos_reindex_logging.py', '06_TOOLS/OFFLINE/genos_meaning_variants.py',
        'service.py', 'service/service.py', 'requirements.txt', 'requirements-serving.txt', 'requirements-pipeline.txt'}
    rows = [{'path': n, 'role': 'code', 'bytes': (ROOT/n).stat().st_size, 'sha256': sha(ROOT/n),
             'allowed_predecessors': [old[n]['sha256']]} for n in sorted(names)]
    required = []
    for n in sorted(required_names - names):
        assert sha(ROOT/n) == old[n]['sha256'], 'Unrelated baseline change: ' + n
        required.append({'path': n, 'role': 'code', 'sha256': sha(ROOT/n)})
    manifest = {'format': '8agent-code/1', 'id': STEM, 'scope': 'SQLite P1 reads + prepared reuse serving',
                'base_code_manifest_sha256': sha(BASE), 'files': rows, 'required_files': required,
                'experiment': 'ADR-0628-experiment-v1/single-card', 'activated': False}
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            info = zipfile.ZipInfo(r['path'], date_time=(2026,10,3,0,0,0)); info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED; z.writestr(info, (ROOT/r['path']).read_bytes())
        info = zipfile.ZipInfo('CODE_MANIFEST.json', date_time=(2026,10,3,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info, (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode())
    script = OUT / (STEM + '.txt')
    script.write_text(SCRIPT.replace('__STEM__', STEM).replace('__ZIP_SHA__', sha(archive)))
    subprocess.run(['bash', '-n', str(script)], check=True)
    record = {'files': {p.name: sha(p) for p in (archive, script)}, 'changed_or_packaged_files': len(rows),
              'required_unchanged_files': len(required), 'base_code_manifest_sha256': sha(BASE),
              'local_code_root': str(ROOT), 'field_code_root_default': '~/DEV',
              'field_commit': None, 'field_generation': None, 'field_revision': None,
              'git_pushed': False, 'generation_activated': False, 'genos_deployed': False}
    (OUT/'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__': main()

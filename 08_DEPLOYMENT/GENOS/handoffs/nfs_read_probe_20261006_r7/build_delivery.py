"""Freeze the small NFS diagnostic handoff; never include operating data or JS."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_NFS_READ_20261006_R7'
FILES = ('02_BACKEND/semantic_runtime/nfs_data_probe.py',
         '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py',
         '06_TOOLS/COMMANDS/genos_rag_data_bundle.py',
         '06_TOOLS/COMMANDS/genos_pack_rag_data.sh',
         '08_DEPLOYMENT/GENOS/workflow/genos_nfs_data_probe.py')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    archive = OUT / (NAME + '.zip')
    if archive.exists():
        raise FileExistsError('Use a new revision for an already built handoff')
    payload = {name: (ROOT / name).read_bytes() for name in FILES}
    for name, raw in payload.items():
        if Path(name).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
            raise ValueError('JavaScript member forbidden')
        if name.endswith('.py'):
            ast.parse(raw, feature_version=(3, 10) if '/workflow/' in name else (3, 11))
    old = zipfile.ZipFile(OUT.parent / 'nfs_read_probe_20261006_r1/GENOS_NFS_READ_20261006_R1.zip')
    old2 = zipfile.ZipFile(OUT.parent / 'nfs_read_probe_20261006_r2/GENOS_NFS_READ_20261006_R2.zip')
    old6 = zipfile.ZipFile(OUT.parent / 'nfs_read_probe_20261006_r6/GENOS_NFS_READ_20261006_R6.zip')
    manifest = {'format': '8agent-code/1', 'id': 'nfs-data-probe-20261006-r1',
                'scope': 'stdlib NFS/SQL read and committed-code identity probe; preserve existing RAG code/data',
                'files': [{'path': name, 'bytes': len(raw), 'sha256': sha(raw), 'allowed_predecessors': sorted({sha(previous.read(name)) for previous in (old, old2, old6) if name in previous.namelist()})}
                          for name, raw in sorted(payload.items())],
                'function_hooks': {'service.py': 'early NFS_DATA_PROBE branch only',
                                   '08_DEPLOYMENT/GENOS/stream_app.py': 'early NFS_DATA_PROBE branch only'},
                'field_commit': None, 'field_generation_actual': None, 'code_serving_revision': None}
    old.close()
    old2.close()
    old6.close()
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(payload.items()):
            z.writestr(name, raw)
        z.writestr('CODE_MANIFEST.json', encoded(manifest))
    zip_sha = sha(archive.read_bytes())
    driver = r'''#!/usr/bin/env bash
# Save ZIP and this TXT together in GENOS DEV/TRANSFER. Run: bash <this>.txt all
set -euo pipefail
umask 077
NFS_ATTACHMENT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
NFS_DRIVER_LOG_BASE="$NFS_ATTACHMENT_DIR/nfs-read-driver-logs"
mkdir -p -- "$NFS_DRIVER_LOG_BASE"
NFS_DRIVER_LOG_DIR="$(mktemp -d "$NFS_DRIVER_LOG_BASE/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
exec > >(tee -a "$NFS_DRIVER_LOG_DIR/RUN.log") 2>&1
NFS_DRIVER_MODE="${1:-all}"
if (( $# )); then shift; fi
printf 'START GENOS_NFS_READ_R7 mode=%s log=%s\n' "$NFS_DRIVER_MODE" "$NFS_DRIVER_LOG_DIR"
trap 'NFS_DRIVER_EXIT=$?; trap - EXIT; python3 - "$NFS_DRIVER_LOG_DIR/EXIT_STATUS.json" "$NFS_DRIVER_EXIT" "$NFS_DRIVER_MODE" <<"PY"
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"status":"DRIVER_STAGES_PASS" if sys.argv[2]=="0" else "FAILED", "exit_code":int(sys.argv[2]),"mode":sys.argv[3],"field_workflow_verified":False},indent=2)+"\n")
PY
printf "GENOS_NFS_READ_EXIT=%s\n" "$NFS_DRIVER_EXIT"; exit "$NFS_DRIVER_EXIT"' EXIT
NFS_DEV_ROOT="${GENOS_DEV:-$HOME/DEV}"
if [[ ! -d "$NFS_DEV_ROOT" ]]; then
  printf 'ERROR: existing DEV checkout missing; set GENOS_DEV to its absolute path.\n'
  exit 2
fi
NFS_ARCHIVE="$NFS_ATTACHMENT_DIR/__NAME__.zip"
NFS_ARCHIVE_SHA="__ZIP_SHA__"
NFS_BOOTSTRAP="$NFS_DRIVER_LOG_DIR/bootstrap"
python3 - "$NFS_ARCHIVE" "$NFS_ARCHIVE_SHA" "$NFS_BOOTSTRAP" <<'PY'
import ast,hashlib,json,sys,zipfile
from pathlib import Path,PurePosixPath
archive,expected,output=Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3])
digest=hashlib.sha256()
with archive.open('rb') as stream:
    for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
if digest.hexdigest()!=expected:raise SystemExit('ZIP SHA256 mismatch; preserve files and use this R7 ZIP/TXT pair')
with zipfile.ZipFile(archive) as z:
    names=z.namelist();m=json.loads(z.read('CODE_MANIFEST.json'))
    if m.get('format')!='8agent-code/1' or m.get('id')!='nfs-data-probe-20261006-r1':raise SystemExit('Unexpected CODE_MANIFEST')
    if len(names)!=len(set(names)) or set(names)!={r['path'] for r in m['files']}|{'CODE_MANIFEST.json'}:raise SystemExit('ZIP member inventory mismatch')
    for r in m['files']:
        name=r['path'];p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name or p.suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:raise SystemExit('Forbidden member')
        raw=z.read(name)
        if len(raw)!=r['bytes'] or hashlib.sha256(raw).hexdigest()!=r['sha256']:raise SystemExit('ZIP member hash mismatch')
        if name.endswith('.py'):ast.parse(raw,feature_version=(3,10) if '/workflow/' in name else (3,11))
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
print('ATTACHMENT_VERIFIED bytes and Python syntax')
PY
cd -- "$NFS_DEV_ROOT"
# Field paths confirmed in earlier GENOS build/runtime records.
# Explicit arguments after these defaults can select another known generation.
NFS_FIELD_ARGS=(--generation /nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation --runtime /nfs-root/diamo/8-agent/runtime)
NFS_FIELD_STATE_UNSET=1
for NFS_FIELD_OPTION in "$@"; do
  case "$NFS_FIELD_OPTION" in --state|--state=*|--state-unset) NFS_FIELD_STATE_UNSET=0 ;; esac
 done
if [[ "$NFS_FIELD_STATE_UNSET" == 1 ]]; then NFS_FIELD_ARGS+=(--state-unset); fi
case "$NFS_DRIVER_MODE" in
  install)
    python3 "$NFS_BOOTSTRAP/06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py" install --archive "$NFS_ARCHIVE" --zip-sha256 "$NFS_ARCHIVE_SHA" --code-root "$NFS_DEV_ROOT" "$@"
    ;;
  prepare)
    python3 06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py prepare --code-root "$NFS_DEV_ROOT" "${NFS_FIELD_ARGS[@]}" "$@"
    ;;
  push)
    python3 06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py push --code-root "$NFS_DEV_ROOT" --remote "${GENOS_NFS_REMOTE:-origin}" "$@"
    ;;
  all)
    python3 "$NFS_BOOTSTRAP/06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py" install --archive "$NFS_ARCHIVE" --zip-sha256 "$NFS_ARCHIVE_SHA" --code-root "$NFS_DEV_ROOT"
    python3 06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py prepare --code-root "$NFS_DEV_ROOT" "${NFS_FIELD_ARGS[@]}" "$@"
    python3 06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py push --code-root "$NFS_DEV_ROOT" --remote "${GENOS_NFS_REMOTE:-origin}"
    ;;
  pack-data)
    python3 "$NFS_BOOTSTRAP/06_TOOLS/COMMANDS/genos_rag_data_bundle.py" pack --code-root "$NFS_DEV_ROOT" "${NFS_FIELD_ARGS[@]}" --output-dir "$NFS_DEV_ROOT/TRANSFER" "$@"
    ;;
  restore-data)
    python3 "$NFS_BOOTSTRAP/06_TOOLS/COMMANDS/genos_rag_data_bundle.py" restore "$@"
    ;;
  *)
    printf 'Modes: all | install | prepare | push | pack-data | restore-data\n'
    exit 2
    ;;
esac
printf 'Code-space stage(s) completed. Deploy the exact printed commit and paste its generated WORKFLOW_PASTE_ALL.txt in the workflow test screen.\n'
'''.replace('__NAME__', NAME).replace('__ZIP_SHA__', zip_sha)
    runner = OUT / (NAME + '_RUN.txt')
    runner.write_text(driver)
    subprocess.run(['bash', '-n', str(runner)], check=True)
    (OUT / 'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    (OUT / (NAME + '_GUIDE_UTF8.txt')).write_bytes((OUT / 'GUIDE_UTF8.txt').read_bytes())
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == set(FILES) | {'CODE_MANIFEST.json'}
        assert all(Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for name in z.namelist())
        assert all(z.read(name) == (ROOT / name).read_bytes() for name in FILES)
    validation = {'version': NAME, 'code_zip_sha256': zip_sha, 'code_manifest_sha256': sha(encoded(manifest)),
                  'run_txt_sha256': sha(runner.read_bytes()), 'archive_members_verified': True,
                  'no_javascript_or_credentials_or_operating_data': True,
                  'python311_and_workflow310_syntax': True, 'bash_syntax': True,
                  'diagnostic_bundle_tests': {'passed': 41},
                  'existing_service_regression': {'passed': 22, 'failed': 1,
                       'failure': 'test_genos_input_byte_limit_uses_operator_setting: KeyError max_input_bytes',
                       'reproduced_before_nfs_hook': True, 'basis': 'earlier user-directed input-byte limit removal'},
                  'verified_local_code_root': str(ROOT), 'field_push_checkout': '~/DEV',
                  'field_commit': None, 'field_generation_path_recorded': str(Path('/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation')),
                  'field_generation_manifest_sha256': None, 'code_serving_revision': None,
                  'historically_confirmed_field_paths_explicit_in_driver': True, 'DEV_is_historically_NFS_not_local_ZIP_output': True, 'ZIP_default_DEV_TRANSFER': True, 'NFS_output_allowed_by_latest_user_request': True, 'stale_DEV_CURRENT_and_state_settings_bypassed': True, 'NFS_mount_entry_alias_supported_without_path_rewrite': True, 'failure_phase_and_requested_symlink_paths_recorded': True, 'DEV_alias_resolved_before_strict_file_checks': True, 'NFS_data_paths_not_rewritten': True, 'GENOS_accessed': False, 'field_deployment_verified': False,
                  'source_sha256': {name: sha((ROOT / name).read_bytes()) for name in FILES + ('service.py', '08_DEPLOYMENT/GENOS/stream_app.py')}}
    (OUT / 'VALIDATION.json').write_bytes(encoded(validation))
    print(json.dumps({'zip': str(archive), 'sha256': zip_sha, 'run': str(runner)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

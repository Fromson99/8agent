"""Build the DEV-root data ZIP launcher without replacing the sent R1 package."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_RAG_DATA_20261006_R2'
FILES = ('genos_rag_data_bundle.py', 'genos_pack_rag_data.sh')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    archive = OUT / (NAME + '.zip')
    if archive.exists():
        raise FileExistsError('Preserve existing delivery; use another revision')
    payload = {name: (ROOT / '06_TOOLS/COMMANDS' / name).read_bytes() for name in FILES}
    ast.parse(payload[FILES[0]], feature_version=(3, 11))
    manifest = {'schema_version': 'genos-offline-data-tool-handoff-v1', 'revision': NAME,
                'files': {name: digest(raw) for name, raw in payload.items()},
                'zip_output': '${GENOS_DEV:-$HOME/DEV}/genos-rag-data-<UTC>-<ID>.zip',
                'tests_passed': 13, 'GENOS_field_verified': False}
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in payload.items():
            z.writestr(name, raw)
        z.writestr('TOOL_MANIFEST.json', json.dumps(manifest, indent=2))
    zip_sha = digest(archive.read_bytes())
    driver = r'''#!/usr/bin/env bash
# GENOS DEV: save the R2 ZIP and this TXT together in ~/DEV/TRANSFER.
# Run: bash ~/DEV/TRANSFER/__NAME___RUN.txt --writers-stopped
set -euo pipefail
umask 077
RAG_ATTACHMENT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RAG_DRIVER_LOG_BASE="$RAG_ATTACHMENT_DIR/rag-data-r2-driver-logs"
mkdir -p -- "$RAG_DRIVER_LOG_BASE"
RAG_DRIVER_LOG_DIR="$(mktemp -d "$RAG_DRIVER_LOG_BASE/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
exec > >(tee -a "$RAG_DRIVER_LOG_DIR/RUN.log") 2>&1
printf 'START GENOS_RAG_DATA_R2 log=%s\n' "$RAG_DRIVER_LOG_DIR"
trap 'RAG_EXIT=$?; trap - EXIT; python3 - "$RAG_DRIVER_LOG_DIR/EXIT_STATUS.json" "$RAG_EXIT" <<"PY"
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"status":"PACK_COMMAND_PASS" if sys.argv[2]=="0" else "FAILED","exit_code":int(sys.argv[2]),"GENOS_deployment_verified":False},indent=2)+"\n")
PY
printf "GENOS_RAG_DATA_EXIT=%s\n" "$RAG_EXIT"; exit "$RAG_EXIT"' EXIT
RAG_DEV_ROOT="${GENOS_DEV:-$HOME/DEV}"
if [[ ! -d "$RAG_DEV_ROOT" ]]; then
  printf 'ERROR: existing DEV directory missing; set GENOS_DEV to its absolute path.\n'
  exit 2
fi
RAG_BOOTSTRAP="$RAG_DRIVER_LOG_DIR/bootstrap"
python3 - "$RAG_ATTACHMENT_DIR/__NAME__.zip" "__SHA__" "$RAG_BOOTSTRAP" <<'PY'
import ast,hashlib,json,sys,zipfile
from pathlib import Path
archive,expected,output=Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3])
if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:raise SystemExit('ZIP SHA256 mismatch; use the matching R2 ZIP/TXT pair')
with zipfile.ZipFile(archive) as z:
    names=z.namelist()
    if len(names)!=len(set(names)) or set(names)!={'genos_rag_data_bundle.py','genos_pack_rag_data.sh','TOOL_MANIFEST.json'}:raise SystemExit('Unexpected archive members')
    manifest=json.loads(z.read('TOOL_MANIFEST.json'))
    if manifest.get('revision')!='__NAME__' or set(manifest['files'])!={'genos_rag_data_bundle.py','genos_pack_rag_data.sh'}:raise SystemExit('Unexpected manifest')
    for name,expected_sha in manifest['files'].items():
        raw=z.read(name)
        if hashlib.sha256(raw).hexdigest()!=expected_sha:raise SystemExit('Member hash mismatch')
        if name.endswith('.py'):ast.parse(raw,feature_version=(3,11))
        output.mkdir(parents=True,exist_ok=True)
        (output/name).write_bytes(raw)
print('R2_ATTACHMENT_VERIFIED')
PY
GENOS_DEV="$RAG_DEV_ROOT" bash "$RAG_BOOTSTRAP/genos_pack_rag_data.sh" "$@"
printf 'Default data ZIP location: %s/genos-rag-data-<UTC>-<ID>.zip; use the exact ZIP path printed above.\n' "$RAG_DEV_ROOT"
'''.replace('__NAME__', NAME).replace('__SHA__', zip_sha)
    runner = OUT / (NAME + '_RUN.txt')
    runner.write_text(driver, encoding='utf-8')
    subprocess.run(['bash', '-n', str(runner)], check=True)
    for name, raw in payload.items():
        (OUT / name).write_bytes(raw)
    subprocess.run(['bash', '-n', str(OUT / FILES[1])], check=True)
    (OUT / 'TOOL_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    guide = (OUT / 'GUIDE_UTF8.txt').read_bytes()
    (OUT / (NAME + '_GUIDE_UTF8.txt')).write_bytes(guide)
    with zipfile.ZipFile(archive) as z:
        assert all(Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for name in z.namelist())
        assert all(z.read(name) == payload[name] for name in FILES)
    validation = {'revision': NAME, 'code_zip_sha256': zip_sha,
                  'run_txt_sha256': digest(runner.read_bytes()), 'tests_passed': 13,
                  'archive_member_hashes_and_no_js': True, 'bash_syntax': True,
                  'data_zip_directly_in_DEV': True, 'original_data_paths_preserved': True,
                  'previous_R1_archives_preserved': True, 'GENOS_field_verified': False}
    (OUT / 'VALIDATION.json').write_text(json.dumps(validation, indent=2) + '\n')
    print(json.dumps(validation, indent=2))


if __name__ == '__main__':
    main()

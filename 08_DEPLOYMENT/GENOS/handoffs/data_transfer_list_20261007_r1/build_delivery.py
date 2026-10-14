"""Build one standalone Bash TXT from the tested existing transport/probe code."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_TRANSFER_NFS_LIST_20261007_R1'
FILES = ('02_BACKEND/semantic_runtime/nfs_data_probe.py',
         '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py',
         '06_TOOLS/COMMANDS/genos_rag_data_bundle.py',
         '06_TOOLS/COMMANDS/genos_pack_rag_data.sh',
         '08_DEPLOYMENT/GENOS/workflow/genos_nfs_data_probe.py')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda v: (json.dumps(v, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    target = OUT / (NAME + '_RUN.txt')
    if target.exists():
        raise FileExistsError('Freeze completed deliveries; use a new revision')
    baseline = json.loads((OUT / 'BASELINE_SHA256.json').read_text())
    predecessors = {n: {baseline[n]} for n in FILES}
    for revision in ('r1', 'r2', 'r6', 'r7'):
        prior = ROOT / '08_DEPLOYMENT/GENOS/handoffs' / ('nfs_read_probe_20261006_' + revision) / ('GENOS_NFS_READ_20261006_' + revision.upper() + '.zip')
        with zipfile.ZipFile(prior) as archive:
            for name in FILES:
                if name in archive.namelist():
                    predecessors[name].add(sha(archive.read(name)))
    payload = {n: (ROOT / n).read_bytes() for n in FILES}
    manifest = {'format': '8agent-code/1', 'id': 'nfs-data-probe-20261006-r1',
                'scope': 'Existing NFS diagnostic hook plus actual file/team document metadata list; no RAG changes',
                'files': [{'path': n, 'bytes': len(raw), 'sha256': sha(raw), 'allowed_predecessors': sorted(predecessors[n])}
                          for n, raw in sorted(payload.items())],
                'field_commit': None, 'code_serving_revision': None}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for n, raw in sorted(payload.items()):
            archive.writestr(n, raw)
        archive.writestr('CODE_MANIFEST.json', encoded(manifest))
    code_zip = stream.getvalue()
    (OUT / 'CODE_PAYLOAD.zip').write_bytes(code_zip)
    (OUT / 'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    envelope = {**payload, 'CODE_PAYLOAD.zip': code_zip,
                'genos_transfer_data_list.py': (ROOT / '06_TOOLS/COMMANDS/genos_transfer_data_list.py').read_bytes(),
                'JOIN_TRANSFER_ZIP.txt': (ROOT / '08_DEPLOYMENT/GENOS/handoffs/zip_parts_bash_20261007_r4/JOIN_TRANSFER_ZIP.txt').read_bytes()}
    for n, raw in envelope.items():
        if Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
            raise ValueError('JavaScript is excluded from this handoff')
        if n.endswith('.py'):
            ast.parse(raw, filename=n, feature_version=(3, 10) if '/workflow/' in n else (3, 11))
    (OUT / 'SOURCE_SHA256.json').write_bytes(encoded({n: sha(raw) for n, raw in envelope.items()}))
    envelope['ENVELOPE_MANIFEST.json'] = encoded({'files': {n: {'sha256': sha(raw), 'bytes': len(raw)} for n, raw in envelope.items()}})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for n, raw in sorted(envelope.items()):
            archive.writestr(n, raw)
    raw = stream.getvalue()
    script = '''#!/usr/bin/env bash
# Complete standalone GENOS script. Keep .txt and run with bash.
set -Eeuo pipefail
umask 077
TRANSFER_TXT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
TRANSFER_LOG_BASE="$TRANSFER_TXT_DIR/transfer-nfs-list-logs"
mkdir -p -- "$TRANSFER_LOG_BASE"
TRANSFER_RUN_DIR="$(mktemp -d "$TRANSFER_LOG_BASE/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
exec > >(tee -a "$TRANSFER_RUN_DIR/RUN.log") 2>&1
trap 'TRANSFER_EXIT=$?; trap - EXIT; printf "{\\"exit_code\\":%d,\\"field_workflow_verified\\":false}\\n" "$TRANSFER_EXIT" > "$TRANSFER_RUN_DIR/EXIT_STATUS.json"; printf "EXIT=%s LOG=%s\\n" "$TRANSFER_EXIT" "$TRANSFER_RUN_DIR"; exit "$TRANSFER_EXIT"' EXIT
printf 'START GENOS_TRANSFER_NFS_LIST_R1 RUN_DIR=%s\\n' "$TRANSFER_RUN_DIR"
TRANSFER_BOOTSTRAP="$TRANSFER_RUN_DIR/bootstrap"
python3 - "$TRANSFER_BOOTSTRAP" <<'TRANSFER_BOOTSTRAP_PY'
import ast,base64,hashlib,io,json,sys,zipfile
from pathlib import Path,PurePosixPath
output=Path(sys.argv[1])
raw=base64.b64decode('__ENVELOPE_B64__',validate=True)
if hashlib.sha256(raw).hexdigest()!='__ENVELOPE_SHA__':raise SystemExit('Embedded code hash mismatch')
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    metadata=json.loads(archive.read('ENVELOPE_MANIFEST.json'))
    names=archive.namelist()
    if len(names)!=len(set(names)) or set(names)!=set(metadata['files'])|{'ENVELOPE_MANIFEST.json'}:raise SystemExit('Code inventory mismatch')
    verified={}
    for name,row in metadata['files'].items():
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\\\' in name or p.suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:raise SystemExit('Forbidden code member')
        content=archive.read(name)
        if len(content)!=row['bytes'] or hashlib.sha256(content).hexdigest()!=row['sha256']:raise SystemExit('Code member hash mismatch')
        if name.endswith('.py'):ast.parse(content,feature_version=(3,10) if '/workflow/' in name else (3,11))
        verified[name]=content
    for name,content in verified.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
print('EMBEDDED_CODE_VERIFIED',flush=True)
TRANSFER_BOOTSTRAP_PY
TRANSFER_DEV="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"
cd -- "$TRANSFER_DEV"
TRANSFER_MODE="${1:-all}"
if (( $# )); then shift; fi
python3 "$TRANSFER_BOOTSTRAP/genos_transfer_data_list.py" "$TRANSFER_MODE" "$@" --code-root "$TRANSFER_DEV" --tools-dir "$TRANSFER_BOOTSTRAP" --run-dir "$TRANSFER_RUN_DIR"
printf 'Read this RUN_DIR/STATUS.json. Deploy the printed commit with SERVING_ENV_PATHS.txt, then paste WORKFLOW_PASTE_ALL.txt in the workflow test screen.\\n'
'''.replace('__ENVELOPE_B64__', base64.b64encode(raw).decode()).replace('__ENVELOPE_SHA__', sha(raw))
    target.write_text(script, encoding='utf-8')
    subprocess.run(['bash', '-n', str(target)], check=True)
    record = {'version': NAME, 'runner_sha256': sha(target.read_bytes()), 'code_zip_sha256': sha(code_zip),
              'code_manifest_sha256': sha(encoded(manifest)), 'embedded_envelope_sha256': sha(raw),
              'code_members': list(FILES), 'target_nfs_root': '/nfs-root/diamo/8-agent',
              'default_generation': '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation',
              'default_runtime': '/nfs-root/diamo/8-agent/runtime', 'default_state': None,
              'source_path_evidence': ['GENOS.md NFS R7/R6 field-path records', 'nfs_read_probe_20261006_r7/GUIDE_UTF8.txt'],
              'data_zip_contains_existing_generation_and_runtime': True, 'operating_data_in_code_handoff': False,
              'email_attachments_plain_txt_only': True, 'javascript_excluded': True,
              'field_execution': False, 'field_commit': None, 'field_generation_manifest_sha256': None,
              'code_serving_revision': None, 'workflow_verified': False}
    (OUT / 'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

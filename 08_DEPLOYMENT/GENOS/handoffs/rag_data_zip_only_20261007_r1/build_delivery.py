"""Single-file, pack-only handoff using the exact verified R7 data tool."""
from pathlib import Path
import ast
import base64
import gzip
import hashlib
import json
import subprocess
import zipfile

R = Path(__file__).resolve().parents[4]
O = Path(__file__).resolve().parent
N = O.parent / 'nfs_read_probe_20261006_r7'
NAME = 'GENOS_DATA_ZIP_ONLY_20261007_R1.txt'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
record = json.loads((N / 'VALIDATION.json').read_text())
archive = N / (record['version'] + '.zip')
assert sha(archive.read_bytes()) == record['code_zip_sha256']
with zipfile.ZipFile(archive) as z:
    manifest = z.read('CODE_MANIFEST.json')
    assert sha(manifest) == record['code_manifest_sha256']
    name = '06_TOOLS/COMMANDS/genos_rag_data_bundle.py'
    raw = z.read(name)
    row = next(x for x in json.loads(manifest)['files'] if x['path'] == name)
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
ast.parse(raw, feature_version=(3, 11))
encoded = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode()
script = r'''#!/usr/bin/env bash
# RAG/AD writers must be normally stopped before running this pack-only TXT.
# Save anywhere in GENOS, then: bash GENOS_DATA_ZIP_ONLY_20261007_R1.txt
set -Eeuo pipefail
umask 077
zip_task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
zip_task_log_base="$zip_task_dir/data-zip-only-logs"
mkdir -p -- "$zip_task_log_base"
zip_task_log_dir="$(mktemp -d "$zip_task_log_base/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
exec > >(tee -a "$zip_task_log_dir/RUN.log") 2>&1
trap 'zip_task_exit=$?; trap - EXIT; python3 - "$zip_task_log_dir/EXIT_STATUS.json" "$zip_task_exit" <<"STATUS_PY"
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"status":"ZIP_CREATED" if sys.argv[2]=="0" else "FAILED", "exit_code":int(sys.argv[2]),"operation":"pack_only","field_deployment_verified":False},indent=2)+"\n")
STATUS_PY
printf "GENOS_DATA_ZIP_EXIT=%s LOG=%s\n" "$zip_task_exit" "$zip_task_log_dir/RUN.log"; exit "$zip_task_exit"' EXIT
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
printf 'START GENOS_DATA_ZIP_ONLY_R1\n'
python3 - "$zip_task_log_dir" "${GENOS_DEV:-$HOME/DEV}" "${GENOS_ZIP_GENERATION:-/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation}" "${GENOS_ZIP_RUNTIME:-/nfs-root/diamo/8-agent/runtime}" "$@" <<'PACK_PY'
import ast,base64,gzip,hashlib,os,subprocess,sys
from pathlib import Path
print('PYTHON',sys.executable,sys.version.replace('\n',' '),flush=True)
if sys.version_info<(3,11):raise SystemExit('Python 3.11+ required')
run,requested,generation,runtime=sys.argv[1:5]
root=Path(requested).resolve(strict=True)
if not root.is_dir():raise SystemExit('Existing GENOS DEV folder required')
raw=gzip.decompress(base64.b64decode('__EMBEDDED_TOOL__',validate=True))
if hashlib.sha256(raw).hexdigest()!='__TOOL_SHA256__':raise SystemExit('Embedded data tool hash mismatch; no data changed')
ast.parse(raw,feature_version=(3,11))
tool=Path(run)/'genos_rag_data_bundle.py';tool.write_bytes(raw)
extra=sys.argv[5:]
state=[] if any(x in ('--state','--state-unset') or x.startswith('--state=') for x in extra) else ['--state-unset']
args=[sys.executable,str(tool),'pack','--code-root',str(root),'--generation',generation,'--runtime',runtime,*state,'--output-dir',str(root/'TRANSFER'),'--writers-stopped',*extra]
print('ZIP_OUTPUT_DIR',str(root/'TRANSFER'),flush=True)
raise SystemExit(subprocess.run(args,cwd=root).returncode)
PACK_PY
'''.replace('__EMBEDDED_TOOL__', encoded).replace('__TOOL_SHA256__', sha(raw))
output = O / NAME
assert not output.exists(), 'Built handoffs are immutable; use another revision.'
output.write_text(script)
subprocess.run(['bash', '-n', str(output)], check=True)
loader = script.split("<<'PACK_PY'\n", 1)[1].rsplit('\nPACK_PY', 1)[0]
compile(loader, 'standalone-pack-loader', 'exec')
ast.parse(loader, feature_version=(3, 11))
metadata = {'name': NAME, 'txt_sha256': sha(output.read_bytes()), 'txt_bytes': output.stat().st_size,
            'embedded_tool_sha256': sha(raw), 'source_r7_zip_sha256': record['code_zip_sha256'],
            'operation': 'pack_only', 'self_contained_attachment': True,
            'default_output': '~/DEV/TRANSFER', 'genos_accessed': False,
            'javascript_in_attachment': False, 'operating_data_in_attachment': False}
(O / 'HANDOFF.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(metadata, ensure_ascii=False))

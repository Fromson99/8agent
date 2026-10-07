"""Single-file data ZIP handoff, with explicit change-tolerant copies."""
from pathlib import Path
import ast
import base64
import gzip
import hashlib
import json
import subprocess

R = Path(__file__).resolve().parents[4]
O = Path(__file__).resolve().parent
NAME = 'GENOS_DATA_ZIP_ONLY_20261007_R2.txt'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
source = R / '06_TOOLS/COMMANDS/genos_rag_data_bundle.py'
raw = source.read_bytes()
ast.parse(raw, feature_version=(3, 11))
encoded = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode()
script = r'''#!/usr/bin/env bash
# Save in GENOS TRANSFER, then: bash TRANSFER/GENOS_DATA_ZIP_ONLY_20261007_R2.txt
# Changes are reported without stopping the ZIP. No global point-in-time snapshot.
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
Path(sys.argv[1]).write_text(json.dumps({"status":"ZIP_CREATED_CHECK_REPORT" if sys.argv[2]=="0" else "FAILED", "exit_code":int(sys.argv[2]),"operation":"pack_only","field_deployment_verified":False},indent=2)+"\n")
STATUS_PY
printf "GENOS_DATA_ZIP_EXIT=%s LOG=%s\n" "$zip_task_exit" "$zip_task_log_dir/RUN.log"; exit "$zip_task_exit"' EXIT
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
printf 'START GENOS_DATA_ZIP_ONLY_R2\n'
python3 - "$zip_task_log_dir" "${GENOS_DEV:-$HOME/DEV}" "${GENOS_ZIP_GENERATION:-/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation}" "${GENOS_ZIP_RUNTIME:-/nfs-root/diamo/8-agent/runtime}" "$@" <<'PACK_PY'
import ast,base64,gzip,hashlib,subprocess,sys
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
args=[sys.executable,str(tool),'pack','--code-root',str(root),'--generation',generation,'--runtime',runtime,*state,'--output-dir',str(root/'TRANSFER'),'--allow-source-changes',*extra]
print('ZIP_OUTPUT_DIR',str(root/'TRANSFER'),flush=True)
print('SOURCE_CHANGES.txt: ZIP inside and output run folder; new files after inventory are listed but not copied.',flush=True)
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
            'embedded_tool_sha256': sha(raw), 'embedded_source': str(source.relative_to(R)),
            'operation': 'pack_only', 'self_contained_attachment': True,
            'default_output': '~/DEV/TRANSFER', 'genos_accessed': False,
            'source_change_policy': 'continue_and_report', 'cross_file_atomic': False,
            'sqlite_copy': 'per_database_online_backup_for_mutable_databases',
            'javascript_in_attachment': False, 'operating_data_in_attachment': False,
            'replaces': 'GENOS_DATA_ZIP_ONLY_20261007_R1.txt'}
(O / 'HANDOFF.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(metadata, ensure_ascii=False))

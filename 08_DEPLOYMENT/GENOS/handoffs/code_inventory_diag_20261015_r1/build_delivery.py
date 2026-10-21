"""Build read-only diagnostic with the exact sealed FACT_REASON R1 checks."""
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
PRIOR = OUT.with_name('fact_reason_20261015_r1')
NAME = 'GENOS_CODE_INVENTORY_DIAG_20261015_R1'
sha = lambda b: hashlib.sha256(b).hexdigest()


def main():
    assert not (OUT / (NAME + '.zip')).exists(), 'Preserve sealed delivery'
    spec_raw = (PRIOR / 'PATCH_SPEC.json.gz').read_bytes()
    spec = json.loads(gzip.decompress(spec_raw))
    reference = {'source_revision': spec['revision'], 'source_spec_sha256': sha(spec_raw),
                 'budget_policy': spec['budget_policy'],
                 'inputs': {k: v['label'] for k, v in spec['signatures'].items()},
                 'outputs': {v['output_signature']: v['label'] for v in spec['signatures'].values()}}
    reference_raw = json.dumps(reference, ensure_ascii=False, separators=(',', ':')).encode()
    code_raw = (PRIOR / 'apply_patch.py').read_bytes()
    code = code_raw.decode()
    wanted = {'sha', 'path_at', 'verify_bindings', 'normalized_inventory', 'signature'}
    nodes = [n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in nodes} == wanted
    helpers = '\n\n'.join(ast.get_source_segment(code, n) for n in nodes)
    header = ('import base64, gzip, hashlib, json\nfrom pathlib import Path, PurePosixPath\n'
              "CONFIG = '00_SYSTEM/GENOS_SERVING_PATHS.json'\n"
              f'DIAG_VERSION = {NAME!r}\nREFERENCE_SHA256 = {sha(reference_raw)!r}\n'
              f'_reference_raw = gzip.decompress(base64.b64decode({base64.b64encode(gzip.compress(reference_raw, mtime=0)).decode()!r}))\n'
              'assert hashlib.sha256(_reference_raw).hexdigest() == REFERENCE_SHA256\n'
              'REFERENCE = json.loads(_reference_raw)\n\n')
    diagnostic = header + helpers + '\n\n' + (OUT / 'diagnose_body.py').read_text()
    ast.parse(diagnostic, feature_version=(3, 10))
    (OUT / 'diagnose.py').write_text(diagnostic)
    shell = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_reports="$PWD/code-inventory-diag-r1-results"
mkdir -p -- "$task_reports"
task_output="$(mktemp -d "$task_reports/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
task_log="$task_output/DIAGNOSIS.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "DIAG_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_output/EXIT.txt"' EXIT
printf 'READ_ONLY_CODE_DIAGNOSIS OUTPUT=%s\\n' "$task_output"
python3 -B - "$task_output" <<'CODE_DIAG_PY'
'''
    run = OUT / (NAME + '_RUN.txt')
    run.write_text(shell + diagnostic + '\nCODE_DIAG_PY\n')
    subprocess.run(['bash', '-n', str(run)], check=True)
    binding = {'revision': NAME, 'operation': 'READ_ONLY_CODE_INVENTORY_DIAGNOSIS',
               'source_installer_sha256': sha(code_raw), 'source_spec_sha256': sha(spec_raw),
               'reference_sha256': sha(reference_raw), 'copied_functions': sorted(wanted),
               'known_predecessors': len(reference['inputs']), 'diagnose_sha256': sha(diagnostic.encode()),
               'run_sha256': sha(run.read_bytes()), 'code_writes': 0, 'model_calls': 0,
               'automatic_retry': 0, 'deadline_seconds': 180, 'field_status': 'NOT_VERIFIED'}
    (OUT / 'SOURCE_BINDING.json').write_text(json.dumps(binding, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run_bytes': run.stat().st_size, 'known_predecessors': len(reference['inputs'])}))


if __name__ == '__main__':
    main()

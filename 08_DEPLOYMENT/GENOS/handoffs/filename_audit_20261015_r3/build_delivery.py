"""Build a stdlib-only diagnostic handoff; no production code installation."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import textwrap
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_FILENAME_AUDIT_20261015_R3'


def sha(raw): return hashlib.sha256(raw).hexdigest()


def main():
    sources = {'genos_filename_audit.py': ROOT / '06_TOOLS/OFFLINE/genos_filename_audit.py',
        'deployment_paths.py': ROOT / '02_BACKEND/semantic_runtime/deployment_paths.py',
        'genos_generation_e2e.py': ROOT / '06_TOOLS/COMMANDS/genos_generation_e2e.py',
        'test_filename_audit.py': HERE / 'test_filename_audit.py'}
    files = {n: p.read_bytes() for n, p in sources.items()}
    manifest = {'schema_version': 'filename-audit-code-v1', 'purpose': 'read-only diagnostic; no installation',
        'required_files': [{'path': n, 'sha256': sha(raw), 'source': str(sources[n].relative_to(ROOT))} for n, raw in files.items()]}
    (HERE / 'CODE_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    files['CODE_MANIFEST.json'] = (HERE / 'CODE_MANIFEST.json').read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, raw in files.items(): z.writestr(n, raw)
    payload = buf.getvalue()
    encoded = '\n'.join(textwrap.wrap(base64.b64encode(payload).decode(), 100))
    runner = '''#!/usr/bin/env bash
set -Eeuo pipefail
AUDIT_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
AUDIT_LOG_BASE="$PWD/FILENAME_AUDIT_RUNS"
mkdir -p "$AUDIT_LOG_BASE"
AUDIT_LOG_DIR="$(mktemp -d "$AUDIT_LOG_BASE/run-$(date +%Y%m%d_%H%M%S)-XXXXXX")"
exec > >(tee -a "$AUDIT_LOG_DIR/console.log") 2>&1
trap 'AUDIT_EXIT=$?; printf "%s\\n" "$AUDIT_EXIT" > "$AUDIT_LOG_DIR/exit_status.txt"; printf "AUDIT_EXIT=%s LOG=%s\\n" "$AUDIT_EXIT" "$AUDIT_LOG_DIR"' EXIT
printf 'GENOS_FILENAME_AUDIT_REVISION=R3 Working directory: %s\\n' "$PWD"
python3 -B - "$AUDIT_SCRIPT_DIR" "$@" <<'PY_AUDIT'
import base64, hashlib, io, json, pathlib, sys, tempfile, zipfile
sys.dont_write_bytecode = True
raw = base64.b64decode("""PAYLOAD""")
if hashlib.sha256(raw).hexdigest() != 'PAYLOAD_HASH': raise ValueError('embedded code hash mismatch')
print('PYTHON=' + sys.executable + ' VERSION=' + sys.version, flush=True)
with tempfile.TemporaryDirectory(prefix='genos-filename-audit-code-') as d:
    root = pathlib.Path(d)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if pathlib.PurePosixPath(name).name != name: raise ValueError('invalid payload member')
        z.extractall(root)
    manifest = json.loads((root / 'CODE_MANIFEST.json').read_text())
    for item in manifest['required_files']:
        if hashlib.sha256((root / item['path']).read_bytes()).hexdigest() != item['sha256']: raise ValueError('code manifest mismatch')
    sys.path.insert(0, str(root))
    import genos_filename_audit
    raise SystemExit(genos_filename_audit.main(sys.argv[2:], default_exceptions_path=pathlib.Path(sys.argv[1]) / 'FILENAME_EXCEPTIONS.json'))
PY_AUDIT
'''.replace('PAYLOAD_HASH', sha(payload)).replace('PAYLOAD', encoded)
    (HERE / (NAME + '_RUN.txt')).write_text(runner, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('audit', sources['genos_filename_audit.py'])
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    sample = HERE / 'SAMPLE'
    if not sample.exists():
        sample.mkdir()
        # R3's sample is the user's named cases plus explicitly synthetic prior versions.
        names = json.loads((HERE / 'EXAMPLE_INPUTS.json').read_text())['rows']
        exceptions, config_hash = audit.load_exceptions(HERE / 'FILENAME_EXCEPTIONS.json')
        events = []
        selected = audit.select(names, exceptions, events)
        audit.report(sample, selected, {'mode': 'USER_NAMED_CASES_WITH_SYNTHETIC_PRIOR_VERSIONS', 'field_inventory': False,
            'exceptions': {'sha256': config_hash, 'revision': exceptions['revision'], 'enabled': True}}, events)
    package_files = {**files, NAME + '_RUN.txt': runner.encode()}
    for n in ('GUIDE_UTF8.txt', 'WORK_CONTRACT.txt', 'VALIDATION.json', 'FILENAME_EXCEPTIONS.json', 'EXAMPLE_INPUTS.json'):
        if (HERE / n).exists(): package_files[n] = (HERE / n).read_bytes()
    for f in sample.iterdir(): package_files['SAMPLE/' + f.name] = f.read_bytes()
    checksums = ''.join(sha(raw) + '  ' + n + '\n' for n, raw in sorted(package_files.items()))
    package_files['SHA256SUMS.txt'] = checksums.encode()
    with zipfile.ZipFile(HERE / (NAME + '.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for n, raw in sorted(package_files.items()):
            if Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}: raise ValueError('JS forbidden in email archive')
            z.writestr(n, raw)
    attachments = [NAME + '.zip', NAME + '_RUN.txt', 'FILENAME_EXCEPTIONS.json', 'GUIDE_UTF8.txt']
    (HERE / 'EMAIL_ATTACHMENTS_SHA256.txt').write_text(''.join(sha((HERE / n).read_bytes()) + '  ' + n + '\n' for n in attachments))
    print(json.dumps({n: (HERE / n).stat().st_size for n in attachments}, indent=2))


if __name__ == '__main__': main()

"""Package immutable selected MAIN133 with the established full-overwrite installer."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import tempfile
import zipfile
from materialize import materialize_code_zip

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_MAIN133_FULL_OVERWRITE_20261103_R1'
RUN = NAME + '_RUN.txt'
WORKFLOW = 'GENOS_MAIN133_WORKFLOW_PASTE_ALL.txt'
FORBIDDEN = {'.js', '.jsx', '.mjs', '.cjs'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


active_path = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
active_raw = active_path.read_bytes()
active = json.loads(active_raw)
assert active['generation'] == 133
release_path = ROOT / active['manifest_path']
release_raw = release_path.read_bytes()
assert sha(release_raw) == active['release_manifest_sha256']
release = json.loads(release_raw)
code_root = ROOT / release['code_root']
code = {}
for name, expected in release['files'].items():
    raw = (code_root / name).read_bytes()
    assert sha(raw) == expected, name
    code[name] = raw
assert len(code) == 513
helpers = ['requirements-serving.txt', 'requirements.txt', '06_TOOLS/COMMANDS/genos_generation_e2e.py']
for name in helpers:
    assert name not in code
    code[name] = (ROOT / name).read_bytes()
assert len(code) == 516
generation = ROOT / release['data_path']
assert sha((generation / 'manifest.json').read_bytes()) == release['data_manifest_sha256']
binding = {
    'main': 133, 'release_id': release['release_id'],
    'selected_serving_files': 513, 'included_serving_files': 513,
    'auxiliary_files': {name: sha(code[name]) for name in helpers},
    'selected_code_root': str(code_root),
    'release_manifest_sha256': sha(release_raw), 'active_pointer_sha256': sha(active_raw),
    'important_files': {name: sha(code[name]) for name in [
        'service.py', 'main.py', '00_SYSTEM/PIPELINE.json',
        '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',
        '02_BACKEND/semantic_runtime/term_index.py',
        '02_BACKEND/semantic_runtime/oracle_progress_body.py']},
    'local_generation_path': str(generation.resolve()),
    'local_generation_manifest_sha256': release['data_manifest_sha256'],
    'local_generation_included': False, 'deployment_checkout_requested': '~/DEV',
    'field_checkout_physical': None, 'field_commit': None,
    'field_generation_path': None, 'field_generation_manifest_sha256': None,
    'field_code_serving_revision': None, 'field_runtime': None,
    'quality_certified': False, 'field_deployment_verified': False,
    'overwrite_existing_authorized': True,
    'installer_basis': 'main123_full_overwrite_20261030_r3',
    'unselected_working_changes_included': False,
}
guide = (OUT / 'GUIDE.txt').read_bytes()
results = (ROOT / '09_ARTIFACTS/AUDITS/20261102-scenario-cumulative-main133/메인반영과_검증결과.txt').read_bytes()
with tempfile.TemporaryDirectory(prefix='main133-full-build-') as temporary:
    package = Path(temporary)
    payload_paths = {}
    for name, raw in sorted(code.items()):
        if name.endswith('.py'):
            ast.parse(raw, filename=name, feature_version=(3, 11))
            compile(raw, name, 'exec')
        assert not {'.git', '.env', '.venv', '01_DATA', 'GENOS_DATA', 'TRANSFER'}.intersection(Path(name).parts)
        archive_path = 'payload/' + name + ('.txt' if Path(name).suffix.lower() in FORBIDDEN else '')
        payload_paths[name] = archive_path
        target = package / archive_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    manifest = {'format': '8agent-code/1', 'release_id': release['release_id'],
                'files': [{'path': p, 'sha256': sha(raw), 'bytes': len(raw)} for p, raw in sorted(code.items())],
                'required_files': []}
    (package / 'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    (package / 'COMMIT_PATHS.txt').write_text('\n'.join(sorted(code)) + '\n')
    (package / 'runner.py').write_bytes((OUT / 'runner.py').read_bytes())
    (package / 'genos_release_gate.py').write_bytes((ROOT / '06_TOOLS/COMMANDS/genos_release_gate.py').read_bytes())
    (package / WORKFLOW).write_bytes(code['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
    (package / 'SELECTED_RELEASE_RECORD.json').write_bytes(encoded({'active': active, 'release': release}))
    (package / 'MAIN133_RESULTS.txt').write_bytes(results)
    (package / 'GUIDE.txt').write_bytes(guide)
    binding['transport_paths'] = {p: q for p, q in payload_paths.items() if q != 'payload/' + p}
    (package / 'SOURCE_BINDING.json').write_bytes(encoded(binding))
    spec = {'version': NAME, 'code': {p: sha(raw) for p, raw in sorted(code.items())},
            'patch': sorted(code), 'payload_paths': payload_paths, 'overwrite_existing': True,
            'selected_release_id': release['release_id'], 'selected_main': 133,
            'field_deployment_verified': False}
    (package / 'PACKAGE.json').write_bytes(encoded(spec))
    materialize_code_zip(package)
    spec['payload'] = {p.relative_to(package).as_posix(): sha(p.read_bytes()) for p in sorted(package.rglob('*'))
                       if p.is_file() and p.name != 'PACKAGE.json'}
    spec_raw = encoded(spec)
    (package / 'PACKAGE.json').write_bytes(spec_raw)
    with zipfile.ZipFile(OUT / (NAME + '.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in sorted(package.rglob('*')):
            if p.is_file() and p.name != 'code.zip':
                relative = p.relative_to(package).as_posix()
                assert p.suffix.lower() not in FORBIDDEN and not relative.endswith('.zip')
                archive.write(p, relative)
    (OUT / 'EXPECTED_PACKAGE.json').write_bytes(spec_raw)
    binding['code_manifest_sha256'] = sha((package / 'CODE_MANIFEST.json').read_bytes())

zip_sha = sha((OUT / (NAME + '.zip')).read_bytes())
bootstrap = (OUT / 'bootstrap.py').read_text().replace('__ZIP_SHA256__', zip_sha).replace('__SPEC_SHA256__', sha(spec_raw))
bootstrap = (OUT / 'materialize.py').read_text() + '\n' + bootstrap
compile(bootstrap, 'embedded_bootstrap.py', 'exec')
shell = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
TASK_LOG_DIR="$PWD/main133-full-overwrite-r1-logs"
if [[ -L "$TASK_LOG_DIR" ]]; then echo "Refuse symlink log folder" >&2; exit 2; fi
mkdir -p "$TASK_LOG_DIR"
TASK_LOG="$TASK_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_RC=$?; printf "%s\\n" "$TASK_RC" > "$TASK_LOG.exit"; echo "MAIN133_FULL_EXIT=$TASK_RC LOG=$TASK_LOG"' EXIT
python3 -u - "$@" <<'MAIN133_FULL_PY'
'''
(OUT / RUN).write_text(shell + bootstrap + '\nMAIN133_FULL_PY\n')
(OUT / WORKFLOW).write_bytes(code['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
subprocess.run(['bash', '-n', str(OUT / RUN)], check=True)
record = {**binding, 'code_files': len(code), 'package_sha256': sha(spec_raw),
          'zip_sha256': zip_sha, 'materialized_code_zip_sha256': spec['payload']['code.zip'],
          'product_changes_from_main133': 0, 'attachments': []}
for name in [NAME + '.zip', RUN, 'GUIDE.txt', WORKFLOW]:
    p = OUT / name
    record['attachments'].append({'filename': name, 'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())})
assert active_path.read_bytes() == active_raw
(OUT / 'HANDOFF.json').write_bytes(encoded(record))
print(json.dumps({'attachments': [{'filename': r['filename'], 'bytes': r['bytes']} for r in record['attachments']],
                  'code_files': len(code), 'selected_files': 513, 'no_prior_zip_required': True}))

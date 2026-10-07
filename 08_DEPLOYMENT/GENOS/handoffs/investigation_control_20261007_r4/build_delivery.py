"""Repair R2's known NFS-hook predecessor inventory, retaining selected MAIN bytes."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import zipfile
from datetime import datetime, timezone

R = Path(__file__).resolve().parents[4]
O = Path(__file__).resolve().parent
P = O.parent / 'investigation_control_20261007_r2'
N = O.parent / 'nfs_read_probe_20261006_r7'
NAME = 'GENOS_INVESTIGATION_CONTROL_20261007_R4'
read = lambda p: json.loads(p.read_text())
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
archive = O / (NAME + '.zip')
assert not archive.exists(), 'Built handoffs are immutable; use a new revision.'

parent_record = read(P / 'HANDOFF.json')
parent_zip = P / (parent_record['version'] + '.zip')
assert sha(parent_zip.read_bytes()) == parent_record['code_zip_sha256']
with zipfile.ZipFile(parent_zip) as z:
    manifest_raw = z.read('CODE_MANIFEST.json')
    assert sha(manifest_raw) == parent_record['code_manifest_sha256']
    parent = json.loads(manifest_raw)
    payload = {row['path']: z.read(row['path']) for row in parent['files']}
    for row in parent['files']:
        assert sha(payload[row['path']]) == row['sha256']
rows = {row['path']: dict(row) for row in parent['files']}

# The diagnostic ZIP omits the dynamically hooked service files. Recreate the
# exact deterministic hook on the frozen generation-42 code, rather than trusting
# photographed hashes or accepting arbitrary field code.
validation = read(N / 'VALIDATION.json')
nfs_zip = N / (validation['version'] + '.zip')
assert sha(nfs_zip.read_bytes()) == validation['code_zip_sha256']
with zipfile.ZipFile(nfs_zip) as z:
    raw = z.read('CODE_MANIFEST.json')
    assert sha(raw) == validation['code_manifest_sha256']
    nfs_manifest = json.loads(raw)
    nfs_payload = {row['path']: z.read(row['path']) for row in nfs_manifest['files']}
    for row in nfs_manifest['files']:
        assert sha(nfs_payload[row['path']]) == row['sha256']
helper_name = '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py'
spec = importlib.util.spec_from_loader('verified_nfs_hook', loader=None)
helper = importlib.util.module_from_spec(spec)
exec(compile(nfs_payload[helper_name], helper_name, 'exec'), helper.__dict__)
old = read(R / '08_DEPLOYMENT/RELEASES/local-genos-unit-v6-20261006-r1/release.json')
hook_evidence = []
for name, root_name in helper.HOOK_FILES.items():
    original = (R / old['code_root'] / name).read_bytes()
    assert sha(original) == old['files'][name]
    assert sha(original) in rows[name]['allowed_predecessors']
    derived = helper.hook(original, root_name)
    rows[name]['allowed_predecessors'] = sorted(set(rows[name]['allowed_predecessors']) | {sha(derived)})
    hook_evidence.append({'path': name, 'base_release': old['release_id'],
                          'base_sha256': sha(original), 'derived_sha256': sha(derived),
                          'hook_helper_sha256': sha(nfs_payload[helper_name])})
assert next(r['derived_sha256'] for r in hook_evidence if r['path'].endswith('stream_app.py')) == '7ea18ce5928757fe17aafdd0eaa78ad7cc46b88786784c4f72a33bdc39d899e8'
assert next(r['derived_sha256'] for r in hook_evidence if r['path'] == 'service.py') == '051b508b38a829dbd637742309b5d646a916ef8788a29c3d8ddf294d33598aa6'

added = []
for row in nfs_manifest['files']:
    name = row['path']
    if name in payload:
        assert payload[name] == nfs_payload[name], name
        continue
    payload[name] = nfs_payload[name]
    rows[name] = {**row, 'allow_missing_predecessor': True}
    added.append(name)

pointer = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer == parent['main_basis']['pointer']
release = read(R / pointer['manifest_path'])
assert sha((R / pointer['manifest_path']).read_bytes()) == pointer['release_manifest_sha256']
for name, digest in release['files'].items():
    assert sha(payload[name]) == sha((R / name).read_bytes()) == digest
for name, raw in payload.items():
    if name.endswith('.py'):
        compile(raw, name, 'exec')
        ast.parse(raw, feature_version=(3, 10) if '/workflow/' in name else (3, 11))
    assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs', '.sqlite', '.db', '.key', '.pem'}
manifest = {**parent, 'id': NAME, 'files': [rows[n] for n in sorted(rows)],
            'parent_code_zip_sha256': parent_record['code_zip_sha256'],
            'known_nfs_hook_predecessors': hook_evidence,
            'nfs_tools_basis': {'code_zip_sha256': validation['code_zip_sha256'], 'added_files': sorted(added)},
            'main_basis': {**parent['main_basis'],
                           'extra_installer_gate_documents': sorted(set(payload) - set(release['files']))}}
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name, raw in sorted({**payload, 'CODE_MANIFEST.json': encoded(manifest)}.items()):
        z.writestr(name, raw)
script = (O / 'APPLY_TEMPLATE.txt').read_text().replace('@NAME@', NAME).replace('@ZIP_SHA256@', sha(archive.read_bytes()))
(O / (NAME + '_APPLY.txt')).write_text(script)
(O / (NAME + '_WORKFLOW_PASTE_ALL.txt')).write_bytes(payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
(O / 'CODE_MANIFEST.json').write_bytes(encoded(manifest))
record = {**parent_record, 'version': NAME, 'created_at': datetime.now(timezone.utc).isoformat(),
          'code_zip_sha256': sha(archive.read_bytes()), 'code_zip_bytes': archive.stat().st_size,
          'code_manifest_sha256': sha(encoded(manifest)), 'apply_txt_sha256': sha(script.encode()),
          'code_files': len(rows), 'parent_code_zip_sha256': parent_record['code_zip_sha256'],
          'known_nfs_hook_predecessors': hook_evidence, 'added_nfs_tools': sorted(added),
          'all_265_main_serving_bytes_unchanged': True, 'field_workflow_test': 'NOT_RUN'}
(O / 'HANDOFF.json').write_bytes(encoded(record))
print(json.dumps(record, ensure_ascii=False, indent=2))

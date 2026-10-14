"""Package selected generation 44 over the verified cumulative field inventory."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone

R = Path(__file__).resolve().parents[4]
O = Path(__file__).resolve().parent
P = O.parent / 'native_chat_sse_20261007_r1'
T = O.parent / 'investigation_control_20261007_r4'
NAME = 'GENOS_INVESTIGATION_COMPLETION_20261007_R1'
read = lambda p: json.loads(p.read_text())
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
archive = O / (NAME + '.zip')
assert not archive.exists(), 'Built handoffs are immutable; use a new revision.'
parent_record = read(P / 'HANDOFF.json')
parent_zip = P / (parent_record['version'] + '.zip')
assert sha(parent_zip.read_bytes()) == parent_record['code_zip_sha256']
with zipfile.ZipFile(parent_zip) as z:
    raw = z.read('CODE_MANIFEST.json')
    assert sha(raw) == parent_record['code_manifest_sha256']
    parent = json.loads(raw)
    payload = {r['path']: z.read(r['path']) for r in parent['files']}
rows = {r['path']: dict(r) for r in parent['files']}
for name, raw in payload.items():
    assert sha(raw) == rows[name]['sha256'], name
pointer = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['release_id'] == 'investigation-completion-v6-20261007-r1'
release = read(R / pointer['manifest_path'])
assert sha((R / pointer['manifest_path']).read_bytes()) == pointer['release_manifest_sha256']
changed = []
for name, digest in release['files'].items():
    raw = (R / release['code_root'] / name).read_bytes()
    assert sha(raw) == digest == sha((R / name).read_bytes()), name
    old = rows.get(name)
    if payload.get(name) != raw:
        changed.append(name)
    payload[name] = raw
    rows[name] = ({**old, 'allowed_predecessors': sorted({old['sha256'], *old.get('allowed_predecessors', [])})}
                  if old else {'path': name, 'allow_missing_predecessor': True})
    rows[name].update(sha256=digest, bytes=len(raw))
for name, raw in payload.items():
    assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs', '.sqlite', '.db', '.key', '.pem'}
    if name.endswith('.py'):
        compile(raw, name, 'exec')
        ast.parse(raw, feature_version=(3, 10) if '/workflow/' in name else (3, 11))
    if name.startswith('02_BACKEND/ENGINES/') and name.endswith('.json'):
        for dependency, digest in json.loads(raw).get('files', {}).items():
            assert sha(payload[dependency]) == digest, (name, dependency)
manifest = {**parent, 'id': NAME, 'files': [rows[n] for n in sorted(rows)],
    'parent_code_zip_sha256': parent_record['code_zip_sha256'],
    'main_basis': {'pointer': pointer, 'serving_files': release['files'],
        'code_root': release['code_root'], 'data_path': release['data_path'],
        'data_manifest_sha256': release['data_manifest_sha256'],
        'extra_installer_gate_documents': sorted(set(payload) - set(release['files']))},
    'completion_review': {'implemented_release': release['release_id'],
        'followup_loop_redesign': 'DESIGN_ONLY_NOT_INCLUDED', 'quality_certified': False}}
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name, raw in sorted({**payload, 'CODE_MANIFEST.json': encoded(manifest)}.items()):
        z.writestr(name, raw)
template = (T / 'APPLY_TEMPLATE.txt').read_text()
template = template.replace('investigation-control-r4-logs', 'investigation-completion-r1-logs')
template = template.replace('Integrate validated investigation control v2 and NFS tools from local MAIN generation 43',
                            'Integrate validated investigation completion from local MAIN generation 44')
(O / 'APPLY_TEMPLATE.txt').write_text(template)
script = template.replace('@NAME@', NAME).replace('@ZIP_SHA256@', sha(archive.read_bytes()))
(O / (NAME + '_APPLY.txt')).write_text(script)
(O / (NAME + '_WORKFLOW_PASTE_ALL.txt')).write_bytes(payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
(O / 'CODE_MANIFEST.json').write_bytes(encoded(manifest))
record = {'version': NAME, 'created_at': datetime.now(timezone.utc).isoformat(),
    'code_zip_sha256': sha(archive.read_bytes()), 'code_zip_bytes': archive.stat().st_size,
    'code_manifest_sha256': sha(encoded(manifest)), 'apply_txt_sha256': sha(script.encode()),
    'workflow_txt_sha256': sha(payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']),
    'code_files': len(rows), 'main_serving_files': len(release['files']),
    'main_basis': manifest['main_basis'], 'parent_code_zip_sha256': parent_record['code_zip_sha256'],
    'changed_from_parent': changed, 'all_main_serving_bytes_identical': True,
    'source_git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip(),
    'push_checkout': '~/DEV', 'push_commit': None, 'actual_selected_generation': None,
    'actual_generation_manifest_sha256': None, 'code_serving_revision': None,
    'requires_rebuilt_generation': False, 'genos_deployed': False, 'field_workflow_test': 'NOT_RUN',
    'followup_loop_redesign': 'DESIGN_ONLY_NOT_INCLUDED'}
(O / 'HANDOFF.json').write_bytes(encoded(record))
print(json.dumps({'version': NAME, 'files': len(rows), 'serving': len(release['files']),
    'zip_bytes': archive.stat().st_size, 'sha256': record['code_zip_sha256']}, ensure_ascii=False))

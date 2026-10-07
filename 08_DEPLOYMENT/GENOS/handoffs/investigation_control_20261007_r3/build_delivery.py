"""Add proved NFS hook predecessors to immutable R2; retain every shipped code byte."""
from pathlib import Path
from datetime import datetime, timezone
import ast, hashlib, json, types, zipfile

R = Path(__file__).resolve().parents[4]
O = Path(__file__).resolve().parent
H = R / '08_DEPLOYMENT/GENOS/handoffs'
P = H / 'investigation_control_20261007_r2'
NAME = 'GENOS_INVESTIGATION_CONTROL_20261007_R3'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
read = lambda path: json.loads(path.read_text())
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def verified_archive(directory, record_name='HANDOFF.json'):
    record = read(directory / record_name)
    matches = [p for p in directory.glob('*.zip') if sha(p.read_bytes()) == record['code_zip_sha256']]
    assert len(matches) == 1, directory
    archive = matches[0]
    z = zipfile.ZipFile(archive)
    assert sha(z.read('CODE_MANIFEST.json')) == record['code_manifest_sha256']
    assert len(z.namelist()) == len(set(z.namelist()))
    return archive, record, z


def verified_member(z, path):
    manifest = json.loads(z.read('CODE_MANIFEST.json'))
    row = next(r for r in manifest['files'] + manifest.get('required_files', []) if r['path'] == path)
    raw = z.read(path)
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes'], path
    return raw


def reconstructed_hooks():
    hook_archive, hook_record, hook_zip = verified_archive(H / 'nfs_read_probe_20261006_r1', 'VALIDATION.json')
    try:
        source = verified_member(hook_zip, '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py')
    finally:
        hook_zip.close()
    module = types.ModuleType('_verified_historical_nfs_hook')
    exec(compile(source, str(hook_archive), 'exec'), module.__dict__)
    records, outputs = [], {}
    cases = [
        ('investigation_logging_20261006_r2', 'service.py', '_ROOT',
         'c6a601da9d6cf037375ae548b5d6b38ee37ecd294c32fb7479879c68276ac3a7',
         '051b508b38a829dbd637742309b5d646a916ef8788a29c3d8ddf294d33598aa6'),
        ('request_input_20261006_r2', '08_DEPLOYMENT/GENOS/stream_app.py', 'ROOT',
         '6c38ca65b079f2a9f433cbbc55d559f67e5dd723335c9b43d63fca1755370ea8',
         '7ea18ce5928757fe17aafdd0eaa78ad7cc46b88786784c4f72a33bdc39d899e8'),
    ]
    for directory, path, root_name, before, after in cases:
        archive, record, z = verified_archive(H / directory)
        try:
            raw = verified_member(z, path)
        finally:
            z.close()
        output = module.hook(raw, root_name)
        assert sha(raw) == before and sha(output) == after, path
        ast.parse(output, feature_version=(3, 11))
        assert module.hook(output, root_name) == output
        outputs[path] = output
        records.append({
            'path': path, 'baseline_zip': str(archive.relative_to(R)),
            'baseline_zip_sha256': record['code_zip_sha256'],
            'baseline_manifest_sha256': record['code_manifest_sha256'],
            'before_sha256': before, 'after_sha256': after, 'after_bytes': len(output),
            'hook_zip': str(hook_archive.relative_to(R)),
            'hook_zip_sha256': hook_record['code_zip_sha256'],
            'hook_source_sha256': sha(source),
            'method': 'Execute the hash-verified historical installer hook on hash-verified baseline bytes',
        })
    return records, outputs


def build():
    archive = O / (NAME + '.zip')
    assert not archive.exists(), 'Built deliveries are immutable; create another revision.'
    prior_archive, prior_record, z = verified_archive(P)
    try:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        payload = {row['path']: verified_member(z, row['path']) for row in manifest['files']}
        assert set(z.namelist()) == set(payload) | {'CODE_MANIFEST.json'}
    finally:
        z.close()
    proofs, _ = reconstructed_hooks()
    by_path = {row['path']: row for row in manifest['files']}
    for proof in proofs:
        row = by_path[proof['path']]
        assert proof['before_sha256'] in row['allowed_predecessors']
        row['allowed_predecessors'] = sorted({*row['allowed_predecessors'], proof['after_sha256']})
    manifest.update({
        'id': NAME, 'supersedes_code_zip_sha256': prior_record['code_zip_sha256'],
        'predecessor_compatibility_proofs': proofs,
        'field_photo_status': 'CACHE_PREFLIGHT_PASS then CHECKOUT_DRIFT before investigation R2 install',
    })
    pointer = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
    release = read(R / pointer['manifest_path'])
    assert pointer == manifest['main_basis']['pointer']
    assert sha((R / pointer['manifest_path']).read_bytes()) == pointer['release_manifest_sha256']
    assert release['files'] == manifest['main_basis']['serving_files']
    for path, digest in release['files'].items():
        assert sha(payload[path]) == sha((R / path).read_bytes()) == digest
    for path, raw in payload.items():
        assert Path(path).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs', '.sqlite', '.db', '.key', '.pem'}
        if path.endswith('.py'):
            ast.parse(raw, feature_version=(3, 11))
    manifest_raw = encoded(manifest)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path, raw in sorted({**payload, 'CODE_MANIFEST.json': manifest_raw}.items()):
            z.writestr(path, raw)
    template = (P / 'APPLY_TEMPLATE.txt').read_text().replace('investigation-control-r2-logs', 'investigation-control-r3-logs')
    old_pins = template.split('def pins(applied):\n', 1)[1].split('\nenv=', 1)[0]
    new_pins = ''' conflicts=[]
 for row in manifest['files']:
  path=installer.plain(root/row['path']);path.resolve().relative_to(root)
  allowed={row['sha256']} if applied else {row['sha256'],*row.get('allowed_predecessors',[])}
  if not path.exists() and not applied and row.get('allow_missing_predecessor'):continue
  actual=sha(path) if path.is_file() else None
  if actual not in allowed:conflicts.append({'path':row['path'],'actual_sha256':actual,'expected_sha256':row['sha256'],'allowed_sha256':sorted(allowed)})
 if conflicts:
  event('CHECKOUT_DRIFT',conflicts=conflicts,existing_files_preserved=True)
  raise ValueError('CHECKOUT_DRIFT: '+', '.join(r['path'] for r in conflicts)+'; existing files preserved')
 if applied and sha(root/'CODE_MANIFEST.json')!=hashlib.sha256(manifest_raw).hexdigest():raise ValueError('Installed inventory differs')'''
    template = template.replace(old_pins, new_pins)
    (O / 'APPLY_TEMPLATE.txt').write_text(template)
    script = template.replace('@NAME@', NAME).replace('@ZIP_SHA256@', sha(archive.read_bytes()))
    (O / (NAME + '_APPLY.txt')).write_text(script)
    (O / (NAME + '_WORKFLOW_PASTE_ALL.txt')).write_bytes(payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
    (O / 'CODE_MANIFEST.json').write_bytes(manifest_raw)
    (O / 'PREDECESSOR_PROOFS.json').write_bytes(encoded(proofs))
    record = {**prior_record, 'version': NAME, 'created_at': datetime.now(timezone.utc).isoformat(),
              'code_zip_sha256': sha(archive.read_bytes()), 'code_zip_bytes': archive.stat().st_size,
              'code_manifest_sha256': sha(manifest_raw), 'apply_txt_sha256': sha(script.encode()),
              'supersedes': prior_record['version'], 'supersedes_code_zip_sha256': prior_record['code_zip_sha256'],
              'shipped_code_identical_to_r2': True, 'predecessor_compatibility_proofs': proofs,
              'photo_verifies': ['GENOS Python 3.11.15', 'DEV resolves to /workspace', 'R2 ZIP verified',
                                'existing glossary compiler cache preflight passed', 'code drift stopped before investigation R2 install'],
              'field_install_status': 'R2_BLOCKED_BEFORE_INSTALL; R3_NOT_RUN',
              'genos_accessed': False}
    (O / 'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    build()

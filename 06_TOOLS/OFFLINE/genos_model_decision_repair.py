"""Minimal model-decision repair patch: verify, back up, apply and re-pin existing GENOS code."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import zipfile

PATCH_ID = 'model-decision-repair-20260929-r1'
FILES = ('02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py',
         '02_BACKEND/semantic_runtime/legal_agent/gateway.py',
         '02_BACKEND/semantic_runtime/progress.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, name):
    pure = PurePosixPath(name)
    if pure.is_absolute() or '..' in pure.parts or '\\' in name or str(pure) != name:
        raise ValueError('unsafe relative path: ' + name)
    path = root / name
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError('symlink not allowed: ' + name)
    return path


def atomic(path, data):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o640
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def output(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def load_archive(path):
    payloads, rows = {}, {}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(FILES) | {'CODE_MANIFEST.json'}:
            raise ValueError('unexpected or duplicate ZIP paths')
        code = json.loads(archive.read('CODE_MANIFEST.json'))
        if code.get('format') != '8agent-code/1' or code.get('patch') != PATCH_ID:
            raise ValueError('unsupported patch manifest')
        if len(code['files']) != len(FILES):
            raise ValueError('invalid patch inventory')
        for row in code['files']:
            name = row['path']
            if name not in FILES or name in rows:
                raise ValueError('unexpected or duplicate inventory path')
            payload = archive.read(name)
            if len(payload) != row['bytes'] or sha(payload) != row['sha256']:
                raise ValueError('ZIP payload differs from manifest: ' + name)
            info = archive.getinfo(name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('ZIP symlink rejected')
            payloads[name] = payload
            rows[name] = {'base_sha256': row['before_sha256'], 'new_sha256': row['sha256']}
    return {'files': rows}, payloads


def prepare(root, spec, payloads):
    changes = {}
    for name, row in spec['files'].items():
        target = safe_path(root, name)
        payload = payloads[name]
        if sha(payload) != row['new_sha256']:
            raise ValueError('payload hash mismatch: ' + name)
        compile(payload, name, 'exec')
        current = target.read_bytes()
        if sha(current) not in [row['base_sha256'], row['new_sha256'], *row.get('supported_base_sha256', [])]:
            raise ValueError('unsupported installed version; no changes: ' + name)
        changes[name] = payload
    pipeline_name = '00_SYSTEM/PIPELINE.json'
    pipeline_raw = safe_path(root, pipeline_name).read_bytes()
    config = json.loads(pipeline_raw)
    replacements = {}
    # Check unrelated code too. Never silently bless drift or rewrite data pins.
    checked = {}
    for entry in config['engines'].values():
        name = entry['manifest']
        raw = safe_path(root, name).read_bytes()
        if sha(raw) != entry['sha256']:
            raise ValueError('engine manifest pin mismatch: ' + name)
        manifest = json.loads(raw)
        updated = dict(manifest['files'])
        for file, expected in manifest['files'].items():
            if file not in checked:
                checked[file] = sha(safe_path(root, file).read_bytes())
            actual = checked[file]
            if file not in spec['files'] and actual != expected:
                raise ValueError('unrelated code drift: ' + file)
            if file in changes:
                if expected not in (spec['files'][file]['base_sha256'], spec['files'][file]['new_sha256'], *spec['files'][file].get('supported_base_sha256', [])):
                    raise ValueError('unsupported engine code baseline: ' + file)
                updated[file] = sha(changes[file])
        if updated != manifest['files']:
            manifest['files'] = dict(sorted(updated.items()))
            new = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            if raw.endswith(b'\n'):
                new += b'\n'
            changes[name] = new
            replacements[entry['sha256']] = sha(new)
    for contract in config['contracts'].values():
        if sha(safe_path(root, contract['schema_path']).read_bytes()) != contract['schema_sha256']:
            raise ValueError('unrelated schema drift: ' + contract['schema_path'])
    for old, new in replacements.items():
        pipeline_raw = pipeline_raw.replace(('"' + old + '"').encode(), ('"' + new + '"').encode())
    if replacements:
        changes[pipeline_name] = pipeline_raw
    return changes


def write_gate_zip(root, directory, spec):
    config = json.loads((root / '00_SYSTEM/PIPELINE.json').read_bytes())
    # Include all selected manifests so the emitted ZIP binds the resulting pins.
    names = set(spec['files']) | {'00_SYSTEM/PIPELINE.json'} | {x['manifest'] for x in config['engines'].values()}
    rows = []
    target = directory / 'applied-code.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            data = safe_path(root, name).read_bytes()
            rows.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
            archive.writestr(name, data)
        archive.writestr('CODE_MANIFEST.json', dump({'format': '8agent-code/1', 'patch': PATCH_ID, 'files': rows}))
    return target, sha(target.read_bytes())


def rollback(root, backup):
    receipt = json.loads((backup / 'receipt.json').read_bytes())
    if receipt['deploy_root'] != str(root) or receipt['patch'] != PATCH_ID:
        raise ValueError('backup belongs to another checkout/patch')
    restored = []
    for name, row in receipt['files'].items():
        data = safe_path(backup / 'before', name).read_bytes()
        if sha(data) != row['before']:
            raise ValueError('backup hash mismatch: ' + name)
        current = sha(safe_path(root, name).read_bytes())
        if current not in (row['before'], row['after']):
            raise ValueError('file changed after patch; rollback refused: ' + name)
        restored.append((safe_path(root, name), data))
    for path, data in restored:
        atomic(path, data)
    output({'status': 'ROLLED_BACK', 'backup': str(backup), 'deploy_root': str(root)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploy-root', type=Path, required=True)
    parser.add_argument('--rollback-from', type=Path)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    root = args.deploy_root.expanduser().resolve(strict=True)
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(actual).resolve() != root:
        raise ValueError('deploy-root must be the existing Git root')
    state = root / 'TRANSFER' / PATCH_ID
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'apply.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback_from:
            backup = args.rollback_from.expanduser().resolve(strict=True)
            backup.relative_to(state)
            rollback(root, backup)
            return
        spec, payloads = load_archive(args.archive)
        changes = prepare(root, spec, payloads)
        different = {n: data for n, data in changes.items() if safe_path(root, n).read_bytes() != data}
        backup = None
        if different:
            backup = Path(tempfile.mkdtemp(prefix='backup-', dir=state))
            receipt = {'patch': PATCH_ID, 'deploy_root': str(root), 'status': 'PREPARED',
                       'time': datetime.now(timezone.utc).isoformat(),
                       'base_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                       'files': {}}
            for name, data in different.items():
                old = safe_path(root, name).read_bytes()
                saved = backup / 'before' / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(old)
                receipt['files'][name] = {'before': sha(old), 'after': sha(data)}
            atomic(backup / 'receipt.json', dump(receipt))
            output({'status': 'BACKUP_READY', 'backup': str(backup)})
            try:
                for name, data in different.items():
                    if sha(safe_path(root, name).read_bytes()) != receipt['files'][name]['before']:
                        raise ValueError('concurrent checkout change: ' + name)
                    atomic(safe_path(root, name), data)
                for name, data in changes.items():
                    if sha(safe_path(root, name).read_bytes()) != sha(data):
                        raise ValueError('post-apply hash mismatch: ' + name)
                # Re-run all checks against the resulting checkout.
                prepare(root, spec, payloads)
            except BaseException:
                rollback(root, backup)
                raise
            receipt['status'] = 'APPLIED'
            atomic(backup / 'receipt.json', dump(receipt))
        archive, archive_sha = write_gate_zip(root, state, spec)
        result = {'status': 'APPLIED' if different else 'ALREADY_APPLIED', 'patch': PATCH_ID,
                  'deploy_root': str(root), 'backup': str(backup) if backup else None,
                  'changed_files': sorted(different), 'gate_zip': str(archive), 'gate_zip_sha256': archive_sha,
                  'generation': None, 'generation_manifest_sha256': None,
                  'deployment_commit': None, 'code_serving_revision': None,
                  'onsite_workflow_verified': False}
        atomic(state / ('apply-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'), dump(result))
        output(result)


if __name__ == '__main__':
    main()

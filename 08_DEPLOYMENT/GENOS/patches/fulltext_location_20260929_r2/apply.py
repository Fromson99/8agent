"""Pinned, reversible logging patch for an existing GENOS Git checkout."""
import argparse
import ast
import importlib.util
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile

PATCH = Path(__file__).resolve().parent
PATCH_ID = 'fulltext-location-20260929-r1'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'


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


def read_optional(path):
    return path.read_bytes() if path.exists() else None


def fingerprint(data):
    return sha(data) if data is not None else None


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
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


def prepare(root, spec):
    import transform
    for name, expected in spec['assets'].items():
        if sha(safe_path(PATCH, name).read_bytes()) != expected:
            raise ValueError('patch asset hash mismatch: ' + name)
    before = (PATCH/'baseline.py').read_bytes()
    after = (PATCH/'candidate.py').read_bytes()
    current = safe_path(root, transform.TARGET).read_bytes()
    changes = {transform.TARGET: transform.transform(current, before, after)}
    pipeline_name = '00_SYSTEM/PIPELINE.json'
    pipeline_raw = safe_path(root, pipeline_name).read_bytes()
    config = json.loads(pipeline_raw)
    replacements = {}
    checked = {}
    pinned = False
    for entry in config['engines'].values():
        name = entry['manifest']
        raw = safe_path(root, name).read_bytes()
        if sha(raw) != entry['sha256']:
            raise ValueError('engine manifest pin mismatch: ' + name)
        manifest = json.loads(raw)
        updated = dict(manifest['files'])
        for file, expected in manifest['files'].items():
            if file not in checked:
                checked[file] = fingerprint(read_optional(safe_path(root, file)))
            if checked[file] != expected:
                raise ValueError('installed code pin mismatch: ' + file)
            if file == transform.TARGET:
                pinned = True
                updated[file] = sha(changes[file])
        if updated != manifest['files']:
            manifest['files'] = dict(sorted(updated.items()))
            new = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            if raw.endswith(b'\n'):
                new += b'\n'
            changes[name] = new
            replacements[entry['sha256']] = sha(new)
    if not pinned:
        raise ValueError('search module has no selected engine pin')
    for contract in config['contracts'].values():
        if sha(safe_path(root, contract['schema_path']).read_bytes()) != contract['schema_sha256']:
            raise ValueError('schema pin mismatch: ' + contract['schema_path'])
    for old, new in replacements.items():
        pipeline_raw = pipeline_raw.replace(('"' + old + '"').encode(), ('"' + new + '"').encode())
    if replacements:
        changes[pipeline_name] = pipeline_raw
    return changes


def write_gate_zip(root, directory, spec):
    config = json.loads((root / '00_SYSTEM/PIPELINE.json').read_bytes())
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
        data = read_optional(safe_path(backup / 'before', name))
        if fingerprint(data) != row['before']:
            raise ValueError('backup hash mismatch: ' + name)
        target = safe_path(root, name)
        current = fingerprint(read_optional(target))
        if current not in (row['before'], row['after']):
            raise ValueError('file changed after patch; rollback refused: ' + name)
        restored.append((target, data))
    for path, data in restored:
        if data is None:
            path.unlink(missing_ok=True)
        else:
            atomic(path, data)
    output({'status': 'ROLLED_BACK', 'backup': str(backup), 'deploy_root': str(root)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploy-root', type=Path, required=True)
    parser.add_argument('--rollback-from', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    root = args.deploy_root.expanduser().resolve(strict=True)
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(actual).resolve() != root:
        raise ValueError('deploy-root must be the existing Git root')
    state = safe_path(root, 'TRANSFER/' + PATCH_ID)
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'apply.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback_from:
            rollback(root, args.rollback_from.expanduser().resolve(strict=True))
            return
        # An interruption can leave some files at before and others at after.
        # Restore an unfinished transaction before validating existing pins.
        for pending in sorted(state.glob('backup-*/receipt.json')):
            value = json.loads(pending.read_bytes())
            if value['status'] == 'PREPARED':
                if args.check_only:
                    raise ValueError('unfinished transaction; run MODE=apply to recover, backup='+str(pending.parent))
                rollback(root, pending.parent)
                value['status'] = 'RECOVERED'
                atomic(pending, dump(value))
        spec = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
        changes = prepare(root, spec)
        different = {n: data for n, data in changes.items() if read_optional(safe_path(root, n)) != data}
        if args.check_only:
            output({'status': 'CHECK_PASS', 'deploy_root': str(root), 'changed_files': sorted(different)})
            return
        backup = None
        if different:
            backup = Path(tempfile.mkdtemp(prefix='backup-', dir=state))
            receipt = {'patch': PATCH_ID, 'deploy_root': str(root), 'status': 'PREPARED',
                       'time': datetime.now(timezone.utc).isoformat(),
                       'base_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                       'files': {}}
            for name, data in different.items():
                old = read_optional(safe_path(root, name))
                if old is not None:
                    saved = safe_path(backup / 'before', name)
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    saved.write_bytes(old)
                receipt['files'][name] = {'before': fingerprint(old), 'after': sha(data)}
            atomic(backup / 'receipt.json', dump(receipt))
            output({'status': 'BACKUP_READY', 'backup': str(backup)})
            try:
                for name, data in different.items():
                    atomic(safe_path(root, name), data)
                for name, data in changes.items():
                    if sha(safe_path(root, name).read_bytes()) != sha(data):
                        raise ValueError('post-apply hash mismatch: ' + name)
                prepare(root, spec)
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

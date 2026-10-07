"""Pinned, reversible logging patch for an existing GENOS Git checkout."""
import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile

PATCH = Path(__file__).resolve().parent
PATCH_ID = 'team-request-logs-20260928-r3'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'
GATEWAY = '02_BACKEND/semantic_runtime/legal_agent/gateway.py'


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
    changes = {}
    for name, row in spec['files'].items():
        current = read_optional(safe_path(root, name))
        output({'status': 'INPUT_CHECK', 'path': name, 'sha256': fingerprint(current),
                'bytes': len(current) if current is not None else None})
        if row.get('strategy') == 'structural-report':
            if current is None:
                raise ValueError('installed report is missing: ' + name)
            for asset, expected in row['assets'].items():
                if sha(safe_path(PATCH, asset).read_bytes()) != expected:
                    raise ValueError('structural asset hash mismatch: ' + asset)
            module_spec = importlib.util.spec_from_file_location('team_report_transform', PATCH / 'structural_report.py')
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            try:
                changes[name] = module.transform(current, module.load_templates(PATCH))
            except (ValueError, SyntaxError) as exc:
                raise ValueError('report compatibility check failed; no source changes; '
                                 + 'installed_sha256=' + sha(current) + '; ' + str(exc)) from exc
            output({'status': 'STRUCTURAL_CHECK_PASS', 'path': name,
                    'before': sha(current), 'after': sha(changes[name]),
                    'changed': changes[name] != current})
            continue
        payload = safe_path(PATCH / 'payload', name).read_bytes()
        if sha(payload) != row['new_sha256']:
            raise ValueError('payload hash mismatch: ' + name)
        ast.parse(payload, feature_version=(3, 11))
        compile(payload, name, 'exec')
        accepted = [row['new_sha256'], *row['supported_base_sha256']]
        if fingerprint(current) not in accepted or (current is None and not row['allow_new']):
            raise ValueError('unsupported installed version; no changes: ' + name)
        changes[name] = payload
    pipeline_name = '00_SYSTEM/PIPELINE.json'
    pipeline_raw = safe_path(root, pipeline_name).read_bytes()
    config = json.loads(pipeline_raw)
    replacements = {}
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
                checked[file] = fingerprint(read_optional(safe_path(root, file)))
            # Every installed pin must describe the installed bytes, including
            # changed files. The patch cannot bless a pre-existing mismatch.
            if checked[file] != expected:
                raise ValueError('installed code pin mismatch: ' + file)
        if REPORT in updated or GATEWAY in updated:
            updated.update({file: sha(data) for file, data in changes.items()
                            if file in spec['files']})
        if updated != manifest['files']:
            manifest['files'] = dict(sorted(updated.items()))
            new = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            if raw.endswith(b'\n'):
                new += b'\n'
            changes[name] = new
            replacements[entry['sha256']] = sha(new)
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

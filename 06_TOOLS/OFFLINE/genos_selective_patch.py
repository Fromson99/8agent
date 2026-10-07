"""Apply one verified mail delta to an existing, consistently pinned GENOS checkout.

Stdlib plus Git only. All edits are planned before writes. Existing mail artifacts
remain immutable; the compatible bundle supplies their preserved before/after bytes.
"""
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
import sys
import tempfile
import zipfile

BUNDLE_ID = 'genos-selective-20260929-r1'
PACKAGE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def output(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def safe(root, name):
    pure = PurePosixPath(name)
    if pure.is_absolute() or '..' in pure.parts or '\\' in name or str(pure) != name:
        raise ValueError('unsafe relative path: ' + name)
    path = root / name
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError('symlink rejected: ' + name)
    return path


def read(path):
    return path.read_bytes() if path.exists() else None


def atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), path.stat().st_mode & 0o777 if path.exists() else 0o640)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_module(path, name):
    definition = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def merge(current, before, after, name):
    if current == after or before == after:
        return current
    if current == before:
        return after
    if current is None or before is None or after is None:
        raise ValueError('incompatible existing/new file; no writes: ' + name)
    with tempfile.TemporaryDirectory(prefix='genos-mail-merge-') as directory:
        paths = [Path(directory) / n for n in ('installed', 'before', 'feature')]
        for path, raw in zip(paths, (current, before, after)):
            path.write_bytes(raw)
        result = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
    if result.returncode != 0:
        # Conflict bodies can contain private site additions; never print them.
        raise ValueError('overlapping edits require an approved variant; no writes: ' + name)
    return result.stdout


def verify_pins(root):
    pipeline_raw = safe(root, '00_SYSTEM/PIPELINE.json').read_bytes()
    pipeline = json.loads(pipeline_raw)
    manifests, checked = {}, {}
    for entry in pipeline['engines'].values():
        name = entry['manifest']
        raw = safe(root, name).read_bytes()
        if sha(raw) != entry['sha256']:
            raise ValueError('engine manifest pin mismatch; no writes: ' + name)
        manifest = json.loads(raw)
        for file, expected in manifest['files'].items():
            if file not in checked:
                checked[file] = sha(read(safe(root, file)))
            if checked[file] != expected:
                raise ValueError('installed code pin mismatch; no writes: ' + file)
        manifests[name] = (raw, manifest)
    for contract in pipeline['contracts'].values():
        if sha(safe(root, contract['schema_path']).read_bytes()) != contract['schema_sha256']:
            raise ValueError('schema pin mismatch; no writes: ' + contract['schema_path'])
    return pipeline_raw, pipeline, manifests


def asset(bundle, name, expected):
    raw = safe(bundle, name).read_bytes()
    if sha(raw) != expected:
        raise ValueError('bundle asset hash mismatch: ' + name)
    return raw


def prepare(root, bundle, specification, selected):
    pipeline_raw, pipeline, manifests = verify_pins(root)
    feature = specification['features'][selected]
    for name, expected in feature.get('assets', {}).items():
        asset(bundle, name, expected)
    changes = {}
    if feature['strategy'] == 'decision':
        transformer = load_module(safe(bundle, feature['transformer']), '_selective_decision')
        for name, row in feature['files'].items():
            changes[name] = transformer.transform(read(safe(root, name)), row, bundle)
    elif feature['strategy'] == 'delegate':
        directory = safe(bundle, feature['directory'])
        # Preserve the existing narrow AST validators and their prerequisites.
        old_transform = sys.modules.pop('transform', None)
        sys.path.insert(0, str(directory))
        try:
            installer = load_module(directory / 'apply.py', '_selective_' + selected)
            original = json.loads((directory / 'PATCH_MANIFEST.json').read_bytes())
            preserved = {n: read(safe(root, n)) for n in original['files']
                         if sha(read(safe(root, n))) in feature.get('preserve_sha256', {}).get(n, [])}
            pending = {n: row for n, row in original['files'].items() if n not in preserved}
            if pending:
                planned = installer.prepare(root, {**original, 'files': pending})
                changes = {n: planned[n] for n in pending}
            changes.update(preserved)
        finally:
            sys.path.pop(0)
            sys.modules.pop('transform', None)
            if old_transform is not None:
                sys.modules['transform'] = old_transform
    else:
        for name, row in feature['files'].items():
            current = read(safe(root, name))
            if sha(current) in feature.get('preserve_sha256', {}).get(name, []):
                changes[name] = current
                continue
            results = []
            for option in row['options']:
                before = asset(bundle, option['before'], option['before_sha256']) if option['before'] else None
                after = asset(bundle, option['after'], option['after_sha256'])
                try:
                    results.append(merge(current, before, after, name))
                except ValueError:
                    pass
                if current in (before, after):
                    results = [after]
                    break
            # Multiple baselines must converge on exactly the same retained code.
            unique = set(results)
            if len(unique) != 1:
                raise ValueError('unsupported or ambiguous delta; no writes: ' + name)
            changes[name] = unique.pop()
    for name, raw in changes.items():
        if name.endswith('.py'):
            ast.parse(raw, feature_version=(3, 11))
            compile(raw, name, 'exec')
        elif name.endswith('.json'):
            json.loads(raw)
    # Verify the repair's read-only semantic hooks before modifying any file.
    for required in feature.get('requirements', []):
        raw = changes.get(required['path'], read(safe(root, required['path'])))
        if raw is None or required['token'].encode() not in raw:
            raise ValueError('missing prerequisite ' + required['path'] + ': ' + required['token'])
    updated_manifests = {}
    for name, (old_raw, manifest) in manifests.items():
        files = dict(manifest['files'])
        for file, raw in changes.items():
            if file in files:
                files[file] = sha(raw)
        for trigger, additions in feature.get('new_pins', {}).items():
            if trigger in files:
                for file in additions:
                    files[file] = sha(changes.get(file, read(safe(root, file))))
                    if files[file] is None:
                        raise ValueError('missing added engine dependency: ' + file)
        if files != manifest['files']:
            manifest = {**manifest, 'files': dict(sorted(files.items()))}
            raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            if old_raw.endswith(b'\n'):
                raw += b'\n'
            updated_manifests[name] = raw
    for entry in pipeline['engines'].values():
        if entry['manifest'] in updated_manifests:
            old, new = entry['sha256'], sha(updated_manifests[entry['manifest']])
            pipeline_raw = pipeline_raw.replace(('"' + old + '"').encode(), ('"' + new + '"').encode())
    def profile_bindings(node):
        nonlocal pipeline_raw
        if isinstance(node, dict):
            name = node.get('path')
            if name in changes and 'sha256' in node:
                expected = sha(read(safe(root, name)))
                if node['sha256'] != expected:
                    raise ValueError('explicit profile pin mismatch; no writes: ' + name)
                pipeline_raw = pipeline_raw.replace(('"' + expected + '"').encode(),
                    ('"' + sha(changes[name]) + '"').encode())
            for child in node.values():
                profile_bindings(child)
        elif isinstance(node, list):
            for child in node:
                profile_bindings(child)
    profile_bindings(pipeline)
    changes.update(updated_manifests)
    if pipeline_raw != safe(root, '00_SYSTEM/PIPELINE.json').read_bytes():
        changes['00_SYSTEM/PIPELINE.json'] = pipeline_raw
    return changes


def rollback(root, state, backup):
    backup = backup.resolve(strict=True)
    backup.relative_to(state)
    receipt_path = backup / 'receipt.json'
    receipt = json.loads(receipt_path.read_bytes())
    if receipt['deploy_root'] != str(root) or receipt['bundle'] != BUNDLE_ID:
        raise ValueError('backup belongs to another checkout/bundle')
    restored = []
    for name, row in receipt['files'].items():
        raw = read(safe(backup / 'before', name))
        if sha(raw) != row['before']:
            raise ValueError('backup hash mismatch: ' + name)
        if sha(read(safe(root, name))) not in (row['before'], row['after']):
            raise ValueError('later edit preserved; rollback refused: ' + name)
        restored.append((safe(root, name), raw))
    for path, raw in restored:
        if raw is None:
            path.unlink(missing_ok=True)
        else:
            atomic(path, raw)
    receipt['status'] = 'ROLLED_BACK'
    atomic(receipt_path, dump(receipt))
    verify_pins(root)
    output({'status': 'ROLLED_BACK', 'backup': str(backup)})


def gate_archive(root, state, names):
    config = json.loads(safe(root, '00_SYSTEM/PIPELINE.json').read_bytes())
    names = {n for n in names if read(safe(root, n)) is not None} | {'00_SYSTEM/PIPELINE.json'} | {e['manifest'] for e in config['engines'].values()}
    archive = state / 'applied-code.zip'
    rows = []
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for name in sorted(names):
            raw = safe(root, name).read_bytes()
            rows.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
            zipped.writestr(name, raw)
        zipped.writestr('CODE_MANIFEST.json', dump({'format': '8agent-code/1', 'patch': BUNDLE_ID, 'files': rows}))
    return archive


def run(root, bundle, selected, mode='apply', backup=None):
    root = root.expanduser().resolve(strict=True)
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(actual).resolve() != root:
        raise ValueError('deploy-root must be the existing Git root')
    specification = json.loads(safe(bundle, 'SELECTIVE_MANIFEST.json').read_bytes())
    if specification['bundle'] != BUNDLE_ID:
        raise ValueError('incorrect selective bundle')
    if selected not in specification['features']:
        raise ValueError('unknown feature: ' + selected)
    state = safe(root, 'TRANSFER/' + BUNDLE_ID)
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'apply.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if mode == 'rollback':
            rollback(root, state, backup)
            return
        for path in sorted(state.glob('backup-*/receipt.json')):
            receipt = json.loads(path.read_bytes())
            if receipt['status'] == 'PREPARED':
                if mode != 'apply':
                    raise ValueError('unfinished transaction; run MODE=apply to recover: ' + str(path.parent))
                rollback(root, state, path.parent)
        changes = prepare(root, bundle, specification, selected)
        different = {n: raw for n, raw in changes.items() if read(safe(root, n)) != raw}
        if mode == 'check':
            output({'status': 'CHECK_PASS', 'feature': selected, 'changed_files': sorted(different)})
            return
        # Preimages include all plans, so a concurrent edit of an unchanged
        # participating file is detected before the first checkout write too.
        inputs = {n: sha(read(safe(root, n))) for n in changes}
        receipt = None
        if different:
            backup = Path(tempfile.mkdtemp(prefix='backup-', dir=state))
            receipt = {'bundle': BUNDLE_ID, 'feature': selected, 'deploy_root': str(root),
                       'status': 'PREPARED', 'time': datetime.now(timezone.utc).isoformat(),
                       'base_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                       'files': {}}
            for name, raw in different.items():
                old = read(safe(root, name))
                if old is not None:
                    saved = safe(backup / 'before', name)
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    saved.write_bytes(old)
                receipt['files'][name] = {'before': sha(old), 'after': sha(raw)}
            atomic(backup / 'receipt.json', dump(receipt))
            output({'status': 'BACKUP_READY', 'backup': str(backup)})
            try:
                verify_pins(root)
                for name, expected in inputs.items():
                    if sha(read(safe(root, name))) != expected:
                        raise ValueError('concurrent checkout change: ' + name)
                for name, raw in different.items():
                    if sha(read(safe(root, name))) != inputs[name]:
                        raise ValueError('concurrent checkout change: ' + name)
                    atomic(safe(root, name), raw)
                for name, raw in changes.items():
                    if sha(read(safe(root, name))) != sha(raw):
                        raise ValueError('post-apply hash mismatch: ' + name)
                verify_pins(root)
                if any(read(safe(root, n)) != raw for n, raw in prepare(root, bundle, specification, selected).items()):
                    raise ValueError('feature recheck not idempotent')
            except BaseException:
                rollback(root, state, backup)
                raise
            receipt['status'] = 'APPLIED'
            atomic(backup / 'receipt.json', dump(receipt))
        history = set(changes)
        for path in state.glob('apply-*.json'):
            history.update(json.loads(path.read_bytes())['participating_files'])
        archive = gate_archive(root, state, history)
        result = {'status': 'APPLIED' if different else 'ALREADY_APPLIED', 'feature': selected,
                  'deploy_root': str(root), 'backup': str(backup) if receipt else None,
                  'changed_files': sorted(different), 'participating_files': sorted(history),
                  'bundle': BUNDLE_ID, 'bundle_manifest_sha256': sha(safe(bundle, 'SELECTIVE_MANIFEST.json').read_bytes()),
                  'gate_zip': str(archive), 'gate_zip_sha256': sha(archive.read_bytes()),
                  'generation': None, 'code_serving_revision': None, 'onsite_workflow_verified': False}
        atomic(state / ('apply-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'), dump(result))
        output(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploy-root', type=Path, required=True)
    parser.add_argument('--feature', default='decision-repair')
    parser.add_argument('--mode', choices=['apply', 'check', 'rollback'], default='apply')
    parser.add_argument('--rollback-from', type=Path)
    args = parser.parse_args()
    if args.mode == 'rollback' and args.rollback_from is None:
        parser.error('--rollback-from is required')
    run(args.deploy_root, PACKAGE, args.feature, args.mode, args.rollback_from)


if __name__ == '__main__':
    main()

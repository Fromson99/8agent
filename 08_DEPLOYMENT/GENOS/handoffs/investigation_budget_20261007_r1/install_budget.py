"""Apply exact service fragments to an inventoried DEV checkout, with rollback."""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import uuid
import zipfile

VERSION = 'GENOS_INVESTIGATION_BUDGET_20261007_R1'
MANAGED = ('service.py', 'CODE_MANIFEST.json')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def path_at(root, name):
    pure = PurePosixPath(name)
    if pure.is_absolute() or '..' in pure.parts or '\\' in name or str(pure) != name:
        raise ValueError('Unsafe relative path: ' + name)
    target = root / name
    for parent in (target, *target.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError('Internal symlink preserved: ' + name)
    target.resolve().relative_to(root)
    return target


def atomic(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.budget-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(root):
    with path_at(root, '.genos-code-replacement.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def payload_at(root):
    raw = path_at(root, 'CODE_MANIFEST.json').read_bytes()
    manifest = json.loads(raw)
    if manifest.get('format') != '8agent-code/1':
        raise ValueError('Existing 8agent-code/1 inventory required')
    payload = {}
    for row in manifest['files']:
        name = row['path']
        if name in payload or name == 'CODE_MANIFEST.json':
            raise ValueError('Duplicate/self-referencing code inventory')
        data = path_at(root, name).read_bytes()
        if sha(data) != row['sha256'] or len(data) != row['bytes']:
            raise ValueError('CHECKOUT_DRIFT; existing files preserved: ' + name)
        payload[name] = data
    if 'service.py' not in payload:
        raise ValueError('service.py is absent from installed code inventory')
    return raw, manifest, payload


def verify_bindings(payload):
    pipeline = json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for ident, binding in pipeline['engines'].items():
        name = binding['manifest']
        if sha(payload[name]) != binding['sha256']:
            raise ValueError('Engine registry mismatch: ' + ident)
        manifest = json.loads(payload[name])
        for name, expected in manifest['files'].items():
            if sha(payload[name]) != expected:
                raise ValueError('Engine code mismatch: ' + ident + ': ' + name)
        if manifest['entrypoint']['path'] not in manifest['files']:
            raise ValueError('Unbound engine entrypoint: ' + ident)
    for ident, config in pipeline['profiles'].items():
        for step in config['nodes']:
            manifest = json.loads(payload[pipeline['engines'][step['engine']]['manifest']])
            slot = pipeline['slots'][step['slot']]
            if any(slot[key] != manifest[key] for key in ('kind', 'inputs', 'outputs')):
                raise ValueError('Engine slot/port mismatch: ' + ident)
    for binding in pipeline['contracts'].values():
        if sha(payload[binding['schema_path']]) != binding['schema_sha256']:
            raise ValueError('Schema hash mismatch')
    print('ENGINE_BINDINGS PASS; engines=' + str(len(pipeline['engines'])), flush=True)


def transform(raw, spec):
    text = raw.decode('utf-8')
    applied = 'def _investigation_profile(' in text
    if applied:
        if any(text.count(op['after']) != 1 for op in spec['operations']):
            raise ValueError('Unknown or partial budget implementation; preserved')
        ast.parse(text, feature_version=(3, 11))
        return raw
    for op in spec['operations']:
        if text.count(op['before']) != 1:
            raise ValueError('Unsupported service fragment: ' + op['name'] + '; preserved')
        text = text.replace(op['before'], op['after'], 1)
    ast.parse(text, feature_version=(3, 11))
    return text.encode('utf-8')


def local_verification(raw, spec):
    if transform(raw, spec) != raw:
        raise ValueError('Budget implementation is missing')
    tree = ast.parse(raw)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('_investigation_profile', '_investigation_budget')]
    if len(functions) != 2:
        raise ValueError('Budget helpers missing')
    namespace = {'os': os}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'service-budget-contract', 'exec'), namespace)
    previous = {name: os.environ.get(name) for name in spec['settings']}
    try:
        for name in spec['settings']:
            os.environ.pop(name, None)
        value = {'max_model_attempts': 40, 'finalization_reserve': 3,
                 'max_tool_actions': 1024, 'tool_finalization_reserve': 4,
                 'wall_seconds': 1800, 'max_no_progress': 2,
                 'candidate_navigation': {'search_rounds': 8, 'assessment_reentry_limit': 2}}
        original = json.loads(json.dumps(value))
        configured = namespace['_investigation_profile'](value)
        assert namespace['_investigation_budget'](configured)['investigation_model_attempts'] == 37
        for name, number in zip(spec['settings'], ('60', '2048', '3600', '12', '0')):
            os.environ[name] = number
        configured = namespace['_investigation_profile'](value)
        budget = namespace['_investigation_budget'](configured)
        assert budget['investigation_model_attempts'] == 57 and budget['max_tool_actions'] == 2048
        assert budget['wall_seconds'] == 3600 and budget['search_rounds'] == 12
        assert budget['assessment_reentry_limit'] == 0 and value == original
        os.environ['GENOS_RAG_MAX_MODEL_ATTEMPTS'] = '3'
        try:
            namespace['_investigation_profile'](value)
        except ValueError:
            pass
        else:
            raise ValueError('Finalization reserve was not preserved')
    finally:
        for name, old in previous.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
    print('BUDGET_SETTINGS PASS; default=40, investigation=37; no model calls', flush=True)


def field_identity(root, generation=None):
    commit = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, check=True).stdout.strip()
    identity = {'code_root': str(root), 'git_commit': commit,
                'sys_executable': sys.executable, 'python': sys.version.split()[0],
                'service_sha256': sha(path_at(root, 'service.py').read_bytes()),
                'code_manifest_sha256': sha(path_at(root, 'CODE_MANIFEST.json').read_bytes()),
                'generation': None, 'generation_manifest_sha256': None,
                'code_serving_revision': os.environ.get('GENOS_CODESERVING_REVISION') or None,
                'workflow_test': 'NOT_RUN'}
    selected = generation or os.environ.get('GENOS_GENERATION')
    if not selected and (root / '00_SYSTEM/GENOS_SERVING_PATHS.json').is_file():
        selected = json.loads((root / '00_SYSTEM/GENOS_SERVING_PATHS.json').read_text()).get('generation')
    if selected:
        path = Path(selected)
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise ValueError('Selected generation is unavailable; preserved')
        identity.update(generation=str(path.resolve()),
                        generation_manifest_sha256=sha((path / 'manifest.json').read_bytes()))
    return identity


def prepare(root, spec):
    before, manifest, payload = payload_at(root)
    verify_bindings(payload)
    new_service = transform(payload['service.py'], spec)
    if new_service == payload['service.py']:
        local_verification(new_service, spec)
        return before, payload, {}, manifest
    local_verification(new_service, spec)
    after = json.loads(before)
    for row in after['files']:
        if row['path'] == 'service.py':
            row.update(sha256=sha(new_service), bytes=len(new_service))
    for row in after.get('required_files', []):
        if not isinstance(row, dict):
            raise ValueError('Legacy required_files inventory requires prior inventory migration')
        if row['path'] == 'service.py':
            row['sha256'] = sha(new_service)
    after['investigation_budget_settings'] = {
        'revision': VERSION, 'prior_inventory_sha256': sha(before),
        'modified_paths': ['service.py'], 'settings': spec['settings'],
        'default_model_attempts_changed': False, 'field_deployed': False}
    return before, payload, {'service.py': new_service, 'CODE_MANIFEST.json': encoded(after)}, after


def verify(root, spec):
    _, manifest, payload = payload_at(root)
    verify_bindings(payload)
    local_verification(payload['service.py'], spec)
    return manifest


def apply(root, spec, artifacts):
    before, payload, changes, _ = prepare(root, spec)
    if not changes:
        print('ALREADY_APPLIED; existing code preserved', flush=True)
        return
    identity = field_identity(root)
    backup = artifacts / ('backup-' + uuid.uuid4().hex)
    backup.mkdir()
    receipt = {'revision': VERSION, 'root': str(root), 'state': 'PREPARED',
               'identity': identity, 'created_at': datetime.now(timezone.utc).isoformat(), 'files': []}
    for name, new in changes.items():
        old = before if name == 'CODE_MANIFEST.json' else payload[name]
        mode = path_at(root, name).stat().st_mode & 0o777
        atomic(path_at(backup, name), old, mode)
        receipt['files'].append({'path': name, 'before_sha256': sha(old), 'after_sha256': sha(new), 'mode': mode})
    atomic(backup / 'receipt.json', encoded(receipt))
    print('BACKUP=' + str(backup), flush=True)
    for row in receipt['files']:
        if sha(path_at(root, row['path']).read_bytes()) != row['before_sha256']:
            raise ValueError('Code changed during preparation; existing code preserved')
    for row in receipt['files']:
        atomic(path_at(root, row['path']), changes[row['path']], row['mode'])
    verify(root, spec)
    archive = backup / 'APPLIED_CODE.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.writestr('CODE_MANIFEST.json', changes['CODE_MANIFEST.json'])
        for name, old in sorted(payload.items()):
            out.writestr(name, changes.get(name, old))
    receipt.update(state='VERIFIED', code_zip=str(archive), code_zip_sha256=sha(archive.read_bytes()),
                   applied_identity=field_identity(root))
    atomic(backup / 'receipt.json', encoded(receipt))
    print('APPLIED_CODE_ZIP=' + str(archive), flush=True)
    print('CODE_APPLIED; commit/gate/push/revision/environment/workflow pending', flush=True)


def undo(root, backup):
    if backup.is_symlink():
        raise ValueError('Backup must not be a symlink')
    receipt = json.loads((backup / 'receipt.json').read_bytes())
    if receipt['revision'] != VERSION or receipt['root'] != str(root):
        raise ValueError('Backup root/revision mismatch')
    if tuple(row['path'] for row in receipt['files']) != MANAGED:
        raise ValueError('Unexpected backup files')
    for row in receipt['files']:
        actual = sha(path_at(root, row['path']).read_bytes())
        if actual not in (row['before_sha256'], row['after_sha256']):
            raise ValueError('Later code change preserved: ' + row['path'])
        if sha(path_at(backup, row['path']).read_bytes()) != row['before_sha256']:
            raise ValueError('Backup hash mismatch: ' + row['path'])
    for row in receipt['files']:
        atomic(path_at(root, row['path']), path_at(backup, row['path']).read_bytes(), row['mode'])
    receipt['state'] = 'UNDONE'
    atomic(backup / 'receipt.json', encoded(receipt))
    print('CODE_RESTORED; redeploy original revision and original environment separately', flush=True)


def gate(root, spec, backup, generation):
    verify(root, spec)
    receipt = json.loads((backup / 'receipt.json').read_bytes())
    if receipt['revision'] != VERSION or receipt['root'] != str(root) or receipt['state'] != 'VERIFIED':
        raise ValueError('Verified backup for this checkout required')
    archive = backup / 'APPLIED_CODE.zip'
    if sha(archive.read_bytes()) != receipt['code_zip_sha256']:
        raise ValueError('Applied code ZIP hash mismatch')
    for name in MANAGED:
        committed = subprocess.run(['git', '-C', str(root), 'show', 'HEAD:' + name],
                                   capture_output=True, check=True).stdout
        if committed != path_at(root, name).read_bytes():
            raise ValueError('Commit the exact installed files first: ' + name)
    if not generation:
        configured = root / '00_SYSTEM/GENOS_SERVING_PATHS.json'
        if configured.is_file():
            generation = json.loads(configured.read_text()).get('generation')
        if not generation:
            loader = importlib.util.spec_from_file_location('installed_generation_selector',
                root / '06_TOOLS/COMMANDS/genos_generation_e2e.py')
            module = importlib.util.module_from_spec(loader)
            loader.loader.exec_module(module)
            generation = str(module.operator_generation(root))
    identity = field_identity(root, generation)
    subprocess.run([sys.executable, str(root / '06_TOOLS/COMMANDS/genos_release_gate.py'),
        '--code-zip', str(archive), '--deploy-root', str(root), '--generation', identity['generation']],
        cwd=root, check=True)
    atomic(backup / 'gate-receipt.json', encoded({'state': 'PASS', 'identity': identity,
        'code_zip_sha256': receipt['code_zip_sha256']}))
    print('RELEASE_GATE PASS; push/revision/environment/workflow pending', flush=True)


def main(spec, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['check', 'apply', 'verify', 'undo', 'gate'])
    parser.add_argument('backup', nargs='?')
    parser.add_argument('--root', default=os.environ.get('GENOS_DEV_ROOT') or os.environ.get('GENOS_DEV') or str(Path.home() / 'DEV'))
    parser.add_argument('--generation')
    args = parser.parse_args(argv)
    configured = Path(args.root).expanduser()
    root = configured.resolve(strict=True)
    git_root = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                              capture_output=True, text=True, check=True).stdout.strip()
    if Path(git_root).resolve() != root:
        raise ValueError('Existing DEV Git root required')
    print('CHECKOUT_RESOLVED=' + str(root), flush=True)
    artifacts = path_at(root, 'TRANSFER/investigation-budget-r1')
    artifacts.mkdir(parents=True, exist_ok=True)
    with locked(root):
        if args.mode == 'check':
            _, _, changes, _ = prepare(root, spec)
            print('CHECK PASS; changed files=' + str(len(changes)), flush=True)
        elif args.mode == 'apply':
            apply(root, spec, artifacts)
        elif args.mode == 'verify':
            verify(root, spec)
        else:
            if not args.backup:
                raise ValueError('Supply the exact BACKUP path printed by apply')
            backup = Path(args.backup).expanduser().resolve(strict=True)
            backup.relative_to(artifacts)
            if args.mode == 'undo':
                undo(root, backup)
            else:
                gate(root, spec, backup, args.generation)
    print(json.dumps(field_identity(root, args.generation), ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    try:
        spec = json.loads(Path(__file__).with_name('PATCH_SPEC.json').read_text())
        raise SystemExit(main(spec))
    except Exception as exc:
        print('BUDGET_INSTALL FAILED: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)

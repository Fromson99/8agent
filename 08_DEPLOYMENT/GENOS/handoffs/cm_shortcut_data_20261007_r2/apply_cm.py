"""Install final-core-source reuse on hash-bound known GENOS inventories.

Uses Python's standard library. The accompanying Bash TXT embeds this file and
its hash-bound patch specification so it can run without unpacking an archive.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
import uuid
import zipfile

VERSION = 'GENOS_CM_SHORTCUT_DATA_20261007_R2'
MODULE = '02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def path_at(root, name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name:
        raise ValueError('Unsafe relative path: ' + name)
    out = root / name
    for part in (out, *out.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError('Symlink preserved: ' + name)
    out.resolve().relative_to(root)
    return out


def atomic(path, raw, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.rollback-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode if mode is not None else 0o600)
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
    lock = path_at(root, '.genos-code-replacement.lock')
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def inventory(root, manifest):
    names = set()
    payload = {}
    for row in manifest['files']:
        name = row['path']
        if name in names:
            raise ValueError('Duplicate inventory path: ' + name)
        names.add(name)
        raw = path_at(root, name).read_bytes()
        if sha(raw) != row['sha256'] or len(raw) != row['bytes']:
            raise ValueError('CHECKOUT_DRIFT: ' + name + '; existing files preserved')
        payload[name] = raw
    return payload


def rebind(value, updates):
    if isinstance(value, dict):
        for name, (old, new) in updates.items():
            if value.get(name) == old:
                value[name] = new
            if value.get('path') == name and value.get('sha256') == old:
                value['sha256'] = new
        for child in value.values():
            rebind(child, updates)
    elif isinstance(value, list):
        for child in value:
            rebind(child, updates)


def verify_bindings(payload):
    """Check both registry->manifest and manifest->code before any write."""
    config = json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for engine, entry in config['engines'].items():
        name = entry['manifest']
        if name not in payload or sha(payload[name]) != entry['sha256']:
            raise ValueError('engine manifest hash mismatch: ' + engine + ': ' + name)
        manifest = json.loads(payload[name])
        for target, expected in manifest['files'].items():
            if target not in payload or sha(payload[target]) != expected:
                raise ValueError('engine code hash mismatch: ' + engine + ': ' + target)
        if manifest['entrypoint']['path'] not in manifest['files']:
            raise ValueError('engine entrypoint is not hash-bound: ' + engine)
    for profile, value in config['profiles'].items():
        for step in value['nodes']:
            manifest = json.loads(payload[config['engines'][step['engine']]['manifest']])
            slot = config['slots'][step['slot']]
            if any(slot[k] != manifest[k] for k in ('kind', 'inputs', 'outputs')):
                raise ValueError('engine slot/port mismatch: ' + profile)
    for contract in config['contracts'].values():
        name = contract['schema_path']
        if name not in payload or sha(payload[name]) != contract['schema_sha256']:
            raise ValueError('schema hash mismatch: ' + name)
    return len(config['engines'])


def prepared(root, spec):
    before_raw = path_at(root, 'CODE_MANIFEST.json').read_bytes()
    state = spec['states'].get(sha(before_raw))
    if state is None:
        raise ValueError('Known core shortcut R1 inventory required; existing files preserved')
    before = json.loads(before_raw)
    payload = inventory(root, before)
    after = json.loads(before_raw)
    changes = {}
    updates = {}
    for name, item in state['patches'].items():
        old = payload.get(name)
        if (sha(old) if old is not None else None) != item['before_sha256']:
            raise ValueError('Unknown code bytes; preserved: ' + name)
        if old is None and path_at(root, name).exists():
            raise ValueError('Unrecorded new module already exists; preserved: ' + name)
        new = base64.b64decode(spec['blobs'][item['after_sha256']], validate=True)
        if sha(new) != item['after_sha256']:
            raise ValueError('Patch result hash differs: ' + name)
        if name.endswith('.py'):
            compile(new, name, 'exec')
        elif name.endswith('.json'):
            json.loads(new)
        changes[name] = new
        if old is not None:
            updates[name] = (sha(old), sha(new))
    count = verify_bindings({**payload, **changes})
    print('ENGINE_BINDINGS PASS; engines=' + str(count), flush=True)
    rebind(after, updates)
    for row in after['files']:
        if row['path'] in changes:
            row.update(bytes=len(changes[row['path']]), sha256=sha(changes[row['path']]))
    for name, new in changes.items():
        if name not in payload:
            after['files'].append({'path': name, 'sha256': sha(new), 'bytes': len(new)})
    # The unmailed latency R1 used path strings here. Normalize its inventory
    # to the current gate contract without altering any serving code.
    file_hashes = {row['path']: row['sha256'] for row in after['files']}
    after['required_files'] = [
        {'path': row, 'sha256': file_hashes[row]} if isinstance(row, str) else row
        for row in after.get('required_files', [])]
    after['id'] = VERSION
    after['cm_curated_registration'] = {
        'revision': VERSION, 'prior_inventory_sha256': sha(before_raw),
        'modified_paths': sorted(changes), 'final_source_roots_only': True,
        'multiturn_current_head': True, 'requires_rebuilt_generation': False,
        'field_deployment_status': 'NOT_VERIFIED',
        'prior_state': state['label'], 'registry_pins_verified': True,
    }
    changes['CODE_MANIFEST.json'] = encoded(after)
    return before_raw, payload, changes, after


def local_verification(root):
    # Verify actual engine wiring in the deployed code root, without model calls.
    script = """
import sys
from types import SimpleNamespace
from semantic_runtime.contracts import Contracts
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.legal_agent import core_evidence_route
from lawrag.pipeline.shortcut_package import CONTRACT
assert CONTRACT == 'curated-core-evidence-route-v1'
c=Contracts(sys.argv[1])
assert c.pipeline['shortcut_v4']['features']['core_evidence_route'] is True
for profile in c.pipeline['profiles']:
    StageRunner(SimpleNamespace(contracts=c,profile_id=profile)).verify_profile()
print('CORE_SHORTCUT_ALL_PROFILES PASS; model calls=0')
"""
    env = {**os.environ, 'PYTHONPATH': str(root/'02_BACKEND'),
           'LAWRAG_WORKSPACE_ROOT': str(root), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(root)}
    subprocess.run([sys.executable, '-c', script, str(root)], cwd=root, env=env, check=True)


def field_identity(root, generation=None):
    result = {'code_root': str(root), 'sys_executable': sys.executable,
              'python': sys.version.split()[0], 'generation': None,
              'generation_manifest_sha256': None, 'git_commit': None,
              'code_serving_revision': None, 'workflow_test': 'NOT_RUN'}
    selected = generation or os.environ.get('GENOS_GENERATION')
    if selected:
        p = Path(selected)
        if not p.is_absolute() or p.is_symlink() or not p.is_dir():
            raise ValueError('Existing absolute generation path required')
        result.update(generation=str(p.resolve()),
                      generation_manifest_sha256=sha((p/'manifest.json').read_bytes()))
    if (root/'.git').exists():
        commit = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, check=True)
        result['git_commit'] = commit.stdout.strip()
    return result


def verify(root, spec):
    raw = path_at(root, 'CODE_MANIFEST.json').read_bytes()
    manifest = json.loads(raw)
    if manifest.get('cm_curated_registration', {}).get('revision') != VERSION:
        raise ValueError('Core shortcut has not been applied')
    if sha(raw) not in spec['output_inventories']:
        raise ValueError('Unknown shortcut inventory; existing files preserved')
    payload = inventory(root, manifest)
    count = verify_bindings(payload)
    print('ENGINE_BINDINGS PASS; engines=' + str(count), flush=True)
    local_verification(root)
    return manifest


def apply(root, spec, artifacts):
    current = json.loads(path_at(root, 'CODE_MANIFEST.json').read_bytes())
    if current.get('cm_curated_registration', {}).get('revision') == VERSION:
        verify(root, spec)
        print('ALREADY_APPLIED; no files changed', flush=True)
        return
    before_raw, payload, changes, after = prepared(root, spec)
    identity = field_identity(root)
    backup = artifacts / ('backup-' + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    receipt = {'revision': VERSION, 'root': str(root), 'state': 'PREPARED',
               'created_at': datetime.now(timezone.utc).isoformat(),
               'identity': identity, 'files': []}
    for name, new in changes.items():
        old = before_raw if name == 'CODE_MANIFEST.json' else payload.get(name)
        target = path_at(root, name)
        mode = target.stat().st_mode & 0o777 if old is not None else 0o644
        if old is not None:
            atomic(path_at(backup, name), old, mode)
        receipt['files'].append({'path': name, 'before_sha256': sha(old) if old is not None else None,
                                 'after_sha256': sha(new), 'mode': mode})
    atomic(backup/'receipt.json', encoded(receipt))
    print('BACKUP=' + str(backup), flush=True)
    # All validations precede the first code write; journal state exists before
    # mutation so interruption can be undone using the exact printed backup.
    for row in receipt['files']:
        name = row['path']
        target = path_at(root, name)
        actual = sha(target.read_bytes()) if target.exists() else None
        if actual != row['before_sha256']:
            raise ValueError('Code changed during preparation; preserved: ' + name)
    for row in receipt['files']:
        atomic(path_at(root, row['path']), changes[row['path']], row['mode'])
    receipt['state'] = 'APPLIED'
    atomic(backup/'receipt.json', encoded(receipt))
    verify(root, spec)
    # Build an exact gate ZIP from the installed checkout, preserving every
    # other code file in the selected prior inventory.
    archive = backup/'APPLIED_CODE.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.writestr('CODE_MANIFEST.json', changes['CODE_MANIFEST.json'])
        for name in sorted(set(payload) | (set(changes) - {'CODE_MANIFEST.json'})):
            if Path(name).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('Unexpected JavaScript in code inventory')
            out.writestr(name, changes[name] if name in changes else payload[name])
    receipt.update(state='VERIFIED', code_zip=str(archive), code_zip_sha256=sha(archive.read_bytes()),
                   code_manifest_sha256=sha(changes['CODE_MANIFEST.json']))
    atomic(backup/'receipt.json', encoded(receipt))
    print('APPLIED_CODE_ZIP=' + str(archive), flush=True)
    print('CODE_ZIP_SHA256=' + receipt['code_zip_sha256'], flush=True)
    print('CODE_APPLIED; Git push/revision deployment/workflow test pending', flush=True)


def undo(root, backup):
    receipt = json.loads((backup/'receipt.json').read_bytes())
    if receipt['revision'] != VERSION or receipt['root'] != str(root):
        raise ValueError('Backup root/revision mismatch')
    # Verify every current and backup byte before any restore. Interrupted
    # partial application may contain either the original or patched bytes.
    for row in receipt['files']:
        name = row['path']
        target = path_at(root, name)
        actual = sha(target.read_bytes()) if target.exists() else None
        if actual not in (row['before_sha256'], row['after_sha256']):
            raise ValueError('Later code change preserved; cannot restore: ' + name)
        if row['before_sha256'] is not None and sha(path_at(backup, name).read_bytes()) != row['before_sha256']:
            raise ValueError('Backup hash mismatch: ' + name)
    for row in receipt['files']:
        if row['before_sha256'] is None:
            path_at(root, row['path']).unlink(missing_ok=True)
        else:
            atomic(path_at(root, row['path']), path_at(backup, row['path']).read_bytes(), row['mode'])
    receipt['state'] = 'UNDONE'
    atomic(backup/'receipt.json', encoded(receipt))
    print('CODE_RESTORED; redeploy original revision separately', flush=True)


def main(spec, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['check', 'apply', 'verify', 'undo', 'gate'])
    parser.add_argument('backup', nargs='?')
    parser.add_argument('--root', default=str(Path.home()/'DEV'))
    parser.add_argument('--generation')
    args = parser.parse_args(argv)
    configured = Path(args.root).expanduser()
    print('CHECKOUT_PATH ' + json.dumps({
        'configured': str(configured), 'cwd': str(Path.cwd()),
        'exists': configured.exists(), 'is_directory': configured.is_dir(),
        'is_symlink': configured.is_symlink()}, ensure_ascii=False), flush=True)
    try:
        root = configured.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError('DEV path cannot be resolved: ' + str(configured)) from exc
    if not root.is_dir():
        raise ValueError('DEV path is not a directory: ' + str(root))
    # GENOS may mount the existing checkout through ~/DEV -> shared storage.
    # Resolve that root once; path_at still rejects symlinks inside its code.
    if not path_at(root, 'CODE_MANIFEST.json').is_file():
        raise ValueError('Installed CODE_MANIFEST.json missing from DEV: ' + str(root))
    print('CHECKOUT_RESOLVED=' + str(root), flush=True)
    artifacts = path_at(root, 'TRANSFER/cm-shortcut-data-r2')
    artifacts.mkdir(parents=True, exist_ok=True)
    with locked(root):
        if args.mode == 'check':
            value = json.loads(path_at(root, 'CODE_MANIFEST.json').read_bytes())
            if value.get('cm_curated_registration', {}).get('revision') == VERSION:
                verify(root, spec)
            else:
                _, _, changes, _ = prepared(root, spec)
                print('CHECK PASS; modified paths=' + str(len(changes)), flush=True)
        elif args.mode == 'apply':
            apply(root, spec, artifacts)
        elif args.mode == 'verify':
            verify(root, spec)
        elif args.mode == 'undo':
            if not args.backup:
                raise ValueError('Supply the exact BACKUP path printed by apply')
            undo(root, Path(args.backup).resolve(strict=True))
        elif args.mode == 'gate':
            verify(root, spec)
            if not args.backup or not args.generation:
                raise ValueError('gate requires exact BACKUP path and --generation')
            backup = Path(args.backup).resolve(strict=True)
            receipt = json.loads((backup/'receipt.json').read_bytes())
            if receipt['root'] != str(root) or receipt['revision'] != VERSION or receipt['state'] != 'VERIFIED':
                raise ValueError('Verified backup for this checkout required')
            archive = backup/'APPLIED_CODE.zip'
            if sha(archive.read_bytes()) != receipt['code_zip_sha256']:
                raise ValueError('Applied code archive hash mismatch')
            identity = field_identity(root, args.generation)
            subprocess.run([sys.executable, str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),
                '--code-zip', str(archive), '--deploy-root', str(root),
                '--generation', identity['generation']], cwd=root, check=True)
            atomic(backup/'gate-receipt.json', encoded({'state': 'PASS', 'identity': identity,
                'code_zip_sha256': receipt['code_zip_sha256']}))
            print('RELEASE_GATE PASS; push/deploy/workflow test pending', flush=True)
    print(json.dumps(field_identity(root, args.generation), ensure_ascii=False), flush=True)
    return 0


"""Data commands use the installed pipeline, selected SQL and explicit principal."""
def dispatch(spec, argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('mode')
    parsed, extra = parser.parse_known_args(argv)
    if not parsed.mode.startswith('data-'):
        return main(spec, argv)
    parser.add_argument('--generation', type=Path)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--principal', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(argv)
    modes = {'data-check':'package-check','data-import':'package-import',
             'data-verify':'package-verify','data-retire':'package-retire'}
    if args.mode not in modes:
        raise ValueError('Unknown data mode')
    root = args.root.resolve(strict=True)
    if not args.runtime.is_absolute() or not args.principal.is_absolute() or not args.receipt.is_absolute():
        raise ValueError('Absolute runtime/principal/receipt paths required')
    if args.mode != 'data-retire' and (args.generation is None or not args.generation.is_absolute()):
        raise ValueError('Actual selected absolute generation required')
    verify(root,spec)
    directory = root/'TRANSFER/cm-shortcut-data-r2'
    directory.mkdir(parents=True,exist_ok=True)
    package = directory/'CM51_SOURCE_PACKAGE.json'
    raw = base64.b64decode(spec['blobs'][spec['data_package_sha256']],validate=True)
    if sha(raw) != spec['data_package_sha256']:
        raise ValueError('Data package bytes differ')
    if package.exists() and package.read_bytes() != raw:
        raise ValueError('Existing package preserved; different bytes')
    if not package.exists():atomic(package,raw)
    command = [sys.executable,str(root/'06_TOOLS/pipeline.py'),'unified-memory',modes[args.mode],
        '--root',str(root),'--runtime',str(args.runtime),'--principal',str(args.principal),
        '--store-version','4']
    if args.generation is not None:command += ['--generation',str(args.generation)]
    source = args.receipt if args.mode in {'data-verify','data-retire'} else package
    output = args.receipt if args.mode=='data-import' else directory/(args.mode+'-'+sha(args.principal.read_bytes())[:16]+'.json')
    command += ['--source',str(source),'--output',str(output)]
    environment = {**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),
                   'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root)}
    completed = subprocess.run(command,cwd=root,env=environment,capture_output=True,text=True)
    atomic(directory/(args.mode+'-'+uuid.uuid4().hex+'.log'),(completed.stdout+completed.stderr).encode())
    if completed.returncode:
        print(completed.stderr,file=sys.stderr,flush=True)
        raise ValueError('Data command failed; SQL transaction and originals preserved; inspect TRANSFER logs')
    result = json.loads(output.read_bytes())
    identity = {**field_identity(root,args.generation),'runtime':str(args.runtime),
        'state_dir':os.environ.get('GENOS_STATE_DIR'),'principal_sha256':sha(args.principal.read_bytes()),
        'data_package_sha256':spec['data_package_sha256'],'command':args.mode,
        'receipt':str(output),'receipt_sha256':sha(output.read_bytes()),'model_calls':0,
        'cases':len(result.get('records',[])) or result.get('cases') or result.get('units') or result.get('retired')}
    atomic(directory/(args.mode+'-identity-'+uuid.uuid4().hex+'.json'),encoded(identity))
    print(json.dumps(identity,ensure_ascii=False),flush=True)
    return 0


if __name__ == '__main__':
    try:
        spec = json.loads(gzip.decompress(Path(__file__).with_name('PATCH_SPEC.json.gz').read_bytes()))
        raise SystemExit(dispatch(spec,sys.argv[1:]))
    except Exception as exc:
        print('CORE_SHORTCUT FAILED: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)

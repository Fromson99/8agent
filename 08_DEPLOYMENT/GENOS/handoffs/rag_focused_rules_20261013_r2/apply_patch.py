"""Install concise progress and the R10 SVG over hash-bound GENOS inventories.

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

VERSION = 'GENOS_RAG_FOCUSED_RULES_20261013_R2'
MODULE = '02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py'
CONFIG = '00_SYSTEM/GENOS_SERVING_PATHS.json'


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


def normalized_inventory(payload, manifest, spec):
    """Only normalize the sealed budget overlay and operator generation binding.

    These two existing field settings are verified and preserved byte for byte.
    All other files must match a complete approved code inventory.
    """
    pins = {name: sha(raw) for name, raw in payload.items() if name != 'CODE_MANIFEST.json'}
    budget = manifest.get('investigation_budget_settings')
    if budget is not None:
        policy = spec['budget_policy']
        expected = {'revision': policy['revision'], 'prior_inventory_sha256': budget.get('prior_inventory_sha256'),
                    'modified_paths': ['service.py'], 'settings': policy['settings'],
                    'default_model_attempts_changed': False, 'field_deployed': False}
        if budget != expected or len(str(budget.get('prior_inventory_sha256', ''))) != 64:
            raise ValueError('Unknown investigation budget preserved')
        text = payload['service.py'].decode()
        for operation in reversed(policy['operations']):
            if text.count(operation['after']) != 1:
                raise ValueError('Unknown budget service code preserved')
            text = text.replace(operation['after'], operation['before'], 1)
        pins['service.py'] = sha(text.encode())
    if CONFIG in payload:
        binding = json.loads(payload[CONFIG])
        if (binding.get('schema_version') != 'genos-serving-paths-v1'
                or binding.get('selection') != 'operator-fixed'
                or not Path(str(binding.get('generation', ''))).is_absolute()
                or not Path(str(binding.get('runtime', ''))).is_absolute()
                or len(str(binding.get('generation_manifest_sha256', ''))) != 64):
            raise ValueError('Existing generation binding differs; preserved')
        cm = manifest.get('cm_oneclick') or {}
        if cm and cm.get('generation_manifest_sha256') != binding['generation_manifest_sha256']:
            raise ValueError('CM and existing generation binding differ; preserved')
        pins.pop(CONFIG)
    return pins


def signature(payload, manifest, spec):
    pins = normalized_inventory(payload, manifest, spec)
    return sha(json.dumps(pins, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def repinned(payload, spec, *, reverse=False):
    """Only replace the known validator and pins that directly bind its bytes."""
    target = spec['target']
    previous = spec['after_sha256'] if reverse else spec['before_sha256']
    expected = spec['before_sha256'] if reverse else spec['after_sha256']
    replacement = base64.b64decode(spec['before' if reverse else 'after'], validate=True)
    if sha(payload[target]) != previous or sha(replacement) != expected:
        raise ValueError('Unexpected profile validator bytes; files preserved')
    changes = {target: replacement}
    pipeline = json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for entry in pipeline['engines'].values():
        name = entry['manifest']; engine = json.loads(payload[name])
        if target in engine['files']:
            if engine['files'][target] != previous:
                raise ValueError('Profile validator binding differs; files preserved')
            engine['files'][target] = expected
            raw = encoded(engine)
            changes[name] = raw
            entry['sha256'] = sha(raw)
    changes['00_SYSTEM/PIPELINE.json'] = encoded(pipeline)
    verify_bindings({**payload, **changes})
    return {n: raw for n, raw in changes.items() if raw != payload[n]}


def validate_prior(payload, manifest, spec, prior_meta):
    pin = signature(payload, manifest, spec)
    allowed = spec['predecessors'].get(pin, [])
    if (prior_meta.get('revision') != spec['prior_revision']
            or prior_meta.get('output_signature') != pin
            or prior_meta.get('input_signature') not in allowed):
        raise ValueError('Verified focused RAG R1 is required; existing files preserved')
    return pin


def prepared(root, spec):
    before_raw = path_at(root, 'CODE_MANIFEST.json').read_bytes()
    before = json.loads(before_raw);payload = inventory(root, before)
    verify_bindings(payload)
    prior_meta = before.get('rag_focused_rules', {})
    state_key = validate_prior(payload, before, spec, prior_meta)
    changes = repinned(payload, spec)
    after = json.loads(before_raw)
    rebind(after, {n: (sha(payload[n]), sha(raw)) for n, raw in changes.items()})
    for row in after['files']:
        if row['path'] in changes:
            raw = changes[row['path']];row.update(bytes=len(raw), sha256=sha(raw))
    output = signature({**payload, **changes}, after, spec)
    after['id'] = VERSION
    after['rag_focused_rules'] = {
        'revision': VERSION, 'input_signature': state_key, 'output_signature': output,
        'prior_inventory_sha256': sha(before_raw), 'prior_patch': prior_meta,
        'modified_paths': sorted(changes), 'source_release': spec['source_release'],
        'source_policy_sha256': spec['after_sha256'], 'requires_rebuilt_generation': False,
        'field_deployment_status': 'NOT_VERIFIED', 'cache_policy_changed': False}
    changes['CODE_MANIFEST.json'] = encoded(after)
    return before_raw, payload, changes, after


def local_verification(root):
    # Verify actual engine wiring in the deployed code root, without model calls.
    script = """
import sys,json
from pathlib import Path
from types import SimpleNamespace
from semantic_runtime.contracts import Contracts
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.legal_agent import completion_contracts as cc,completion_v8,request_entry,navigation_input,investigation_scope,law_navigation,memory_rag,bounded_source_session,unified_runtime
root=Path(sys.argv[1]);c=Contracts(root)
for profile in c.pipeline['profiles']:
    StageRunner(SimpleNamespace(contracts=c,profile_id=profile)).verify_profile()
p=json.loads((root/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_bytes())
from semantic_runtime.legal_agent.workflow_tiers_policy import profile
p=profile(p)
assert cc.version(p)==cc.V8
assert p['request_entry_policy']=='fused-title-v1'
from semantic_runtime.legal_agent.errors import ContractError
for bad in ({**p,'unrecognized_setting':True},{**p,'request_entry_policy':'invalid'}):
    try:profile(bad)
    except ContractError:pass
    else:raise AssertionError('invalid profile accepted')
assert request_entry.POLICY==p['request_entry_policy']=='fused-title-v1'
assert p['candidate_navigation']['compact_input'] is True
for mod in (cc,completion_v8,request_entry,navigation_input,investigation_scope,law_navigation,memory_rag,bounded_source_session,unified_runtime):
    assert Path(mod.__file__).resolve().is_relative_to(root)
print('R2_PROFILE_BOOTSTRAP_POLICY PASS')
print('FOCUSED_RAG_ALL_PROFILES PASS; completion=investigation-completion-v8; model calls=0')
print('FOCUSED_RAG_CODE_ROOT='+str(root))
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
    if not selected and (root/CONFIG).exists():
        selected = json.loads((root/CONFIG).read_bytes()).get('generation')
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
    manifest = json.loads(path_at(root, 'CODE_MANIFEST.json').read_bytes())
    meta = manifest.get('rag_focused_rules', {})
    if meta.get('revision') != VERSION:
        raise ValueError('R2 profile bootstrap correction has not been applied')
    payload = inventory(root, manifest);count = verify_bindings(payload)
    if signature(payload, manifest, spec) != meta.get('output_signature'):
        raise ValueError('R2 output inventory differs; files preserved')
    # Reversing only this sealed one-file delta must reproduce a known R1
    # inventory exactly; arbitrary edits cannot be self-approved by rehashing.
    prior_payload = {**payload, **repinned(payload, spec, reverse=True)}
    prior_pin = validate_prior(prior_payload, manifest, spec, meta.get('prior_patch', {}))
    if prior_pin != meta.get('input_signature') or meta.get('source_policy_sha256') != spec['after_sha256']:
        raise ValueError('R2 predecessor binding differs; files preserved')
    print('ENGINE_BINDINGS PASS; engines=' + str(count), flush=True)
    local_verification(root)
    return manifest


def apply(root, spec, artifacts):
    current = json.loads(path_at(root, 'CODE_MANIFEST.json').read_bytes())
    if current.get('rag_focused_rules', {}).get('revision') == VERSION:
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
    artifacts = path_at(root, 'TRANSFER/rag-focused-rules-r2')
    artifacts.mkdir(parents=True, exist_ok=True)
    with locked(root):
        if args.mode == 'check':
            value = json.loads(path_at(root, 'CODE_MANIFEST.json').read_bytes())
            if value.get('rag_focused_rules', {}).get('revision') == VERSION:
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


if __name__ == '__main__':
    try:
        spec = json.loads(gzip.decompress(Path(__file__).with_name('PATCH_SPEC.json.gz').read_bytes()))
        raise SystemExit(main(spec))
    except Exception as exc:
        print('RAG_DISPLAY FAILED: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)

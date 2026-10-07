"""Hash-gated R2 code application with explicit missing-file additions and rollback."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with Path(path).open('w', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n'); out.flush(); os.fsync(out.fileno())


def atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(source.read_bytes()); out.flush(); os.fsync(out.fileno())
    if target.exists():
        shutil.copymode(target, temporary)
    os.replace(temporary, target)


def checkout_path(dev, name):
    path = dev / name
    path.resolve().relative_to(dev.resolve())
    return path


def state(path):
    return sha(path) if path.is_file() else None


def engine_plan(dev, *, apply=False, add_new=False):
    """Update only package code pins; record existing unrelated inconsistencies unchanged."""
    dev = dev.resolve()
    rows = json.loads((HERE / 'CODE_MANIFEST.json').read_text())['files']
    targets = {r['path']: r['sha256'] for r in rows if r['role'] == 'code'}
    pipeline = dev / '00_SYSTEM/PIPELINE.json'
    original = pipeline.read_bytes(); config = json.loads(original)
    selected = json.loads(original)
    report = {'applied': False, 'changed_code': [], 'unlisted_runtime_files': [], 'schemas': [],
              'engine_manifests': [], 'data_pins_checked_not_rewritten': [],
              'scope': 'package-code-pins-only', 'serving_verified': False,
              'profiles_and_data_pins_preserved': True, 'preserved_existing_drift': []}
    writes = {}; metadata = {str(pipeline.relative_to(dev)): sha(pipeline)}
    protected = {}
    for engine_name, binding in config['engines'].items():
        name = binding['manifest']; path = checkout_path(dev, name)
        path.resolve().relative_to((dev / '02_BACKEND/ENGINES').resolve())
        if path.is_symlink(): raise ValueError('Engine manifest symlink rejected: ' + name)
        raw = path.read_bytes(); manifest = json.loads(raw); candidate = json.loads(raw)
        metadata[name] = hashlib.sha256(raw).hexdigest()
        if metadata[name] != binding['sha256']:
            report['preserved_existing_drift'].append({'kind': 'engine_manifest', 'engine': engine_name,
                'path': name, 'pinned_sha256': binding['sha256'], 'actual_sha256': metadata[name]})
        for source, expected in manifest['files'].items():
            actual = state(checkout_path(dev, source))
            if source in targets:
                if expected != targets[source]:
                    candidate['files'][source] = targets[source]; report['changed_code'].append(source)
            else:
                protected[source] = actual
                if actual != expected:
                    report['preserved_existing_drift'].append({'kind': 'code', 'engine': engine_name,
                        'path': source, 'pinned_sha256': expected, 'actual_sha256': actual})
        folder = checkout_path(dev, manifest['entrypoint']['path']).parent
        for source in folder.glob('*.py'):
            name_in_dev = str(source.relative_to(dev))
            if name_in_dev not in targets:
                protected[name_in_dev] = state(source)
                if name_in_dev not in manifest['files']:
                    report['preserved_existing_drift'].append({'kind': 'unlisted', 'engine': engine_name,
                        'path': name_in_dev, 'actual_sha256': protected[name_in_dev]})
        # New runtime dependencies are pinned only in engines that consume the changed compiler/index.
        additions = {'02_BACKEND/semantic_runtime/navigation_storage.py', '02_BACKEND/semantic_runtime/term_references_legacy.py'}
        if not ({'02_BACKEND/semantic_runtime/term_index.py', '02_BACKEND/lawrag/pipeline/term_generation.py'} & manifest['files'].keys()):
            additions = set()
        for source in additions & targets.keys() - manifest['files'].keys():
            candidate['files'][source] = targets[source]; report['unlisted_runtime_files'].append(source)
        if candidate == manifest: continue
        candidate['files'] = dict(sorted(candidate['files'].items()))
        content = (json.dumps(candidate, ensure_ascii=False, indent=2) + ('\n' if raw.endswith(b'\n') else '')).encode()
        new_sha = hashlib.sha256(content).hexdigest()
        writes[binding['manifest']] = content
        selected['engines'][engine_name]['sha256'] = new_sha
        report['engine_manifests'].append({'engine': engine_name, 'manifest': binding['manifest'], 'old': binding['sha256'], 'new': new_sha})
    for name, binding in config['contracts'].items():
        source = binding['schema_path']; actual = state(checkout_path(dev, source)); protected[source] = actual
        if actual != binding['schema_sha256']:
            report['preserved_existing_drift'].append({'kind': 'schema', 'contract': name,
                'path': source, 'pinned_sha256': binding['schema_sha256'], 'actual_sha256': actual})
    report['changed_code'] = sorted(set(report['changed_code']))
    report['unlisted_runtime_files'] = sorted(set(report['unlisted_runtime_files']))
    report['protected_existing_files'] = protected
    report['metadata_before'] = metadata
    report['metadata_expected_after'] = {name: hashlib.sha256(content).hexdigest() for name, content in writes.items()}
    if writes:
        report['metadata_expected_after'][str(pipeline.relative_to(dev))] = hashlib.sha256(
            (json.dumps(selected, ensure_ascii=False, indent=2) + '\n').encode()).hexdigest()
    for row in report['preserved_existing_drift']:
        print('EXISTING STATE PRESERVED ' + json.dumps(row, ensure_ascii=False), flush=True)
    if apply:
        for source, expected in targets.items():
            if state(checkout_path(dev, source)) != expected: raise ValueError('Applied code drift: ' + source)
        if any(state(checkout_path(dev, source)) != expected for source, expected in metadata.items()):
            raise ValueError('Concurrent engine metadata drift')
        for name, content in writes.items():
            with tempfile.NamedTemporaryFile(dir=HERE.parent, delete=False) as stream:
                temporary = Path(stream.name); stream.write(content)
            try: atomic_copy(temporary, checkout_path(dev, name))
            finally: temporary.unlink()
        if writes: write(pipeline, selected)
        report['applied'] = bool(writes)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    diagnostic = HERE.parent / ('package-engine-plan-' + stamp + '.json'); write(diagnostic, report)
    print('PACKAGE ENGINE PLAN ' + str(diagnostic) + '; historical data/serving not validated', flush=True)
    return report


def rollback(backup):
    receipt = json.loads((backup / 'before.json').read_text())
    dev = Path(receipt['dev'])
    planned = {}
    for report_name in ('baseline-engine-plan.json', 'engine-plan.json', 'engine-apply.json'):
        path = backup / report_name
        if path.is_file(): planned.update(json.loads(path.read_text()).get('metadata_expected_after', {}))
    conflicts = []
    for name, expected in receipt['before'].items():
        if expected is not None and sha(backup / 'files' / name) != expected:
            raise ValueError('Backup drift: ' + name)
    for name, expected in receipt['before'].items():
        target = dev / name
        if expected is None:
            if target.exists():
                if sha(target) != receipt['added'][name]:
                    raise ValueError('Added file drift; preserved: ' + name)
                target.unlink()
        else:
            if name == '00_SYSTEM/PIPELINE.json' or name.startswith('02_BACKEND/ENGINES/'):
                actual = state(target)
                if actual not in {expected, planned.get(name)}:
                    conflicts.append(name)
                    print('ROLLBACK PRESERVED CONCURRENT METADATA ' + name, flush=True)
                    continue
            atomic_copy(backup / 'files' / name, target)
    write(backup / 'rollback.json', {'dev': str(dev), 'restored': list(receipt['before']),
                                    'preserved_concurrent_metadata': conflicts, 'at': datetime.now(timezone.utc).isoformat()})
    print('ROLLBACK PACKAGE COMPLETE; external metadata preserved' if conflicts else 'ROLLBACK COMPLETE', backup, flush=True)


def apply(dev, *, check=False):
    dev = dev.resolve(strict=True)
    manifest = json.loads((HERE / 'CODE_MANIFEST.json').read_text())
    rows = manifest['files']
    code = [row for row in rows if row['role'] == 'code']
    before, additions = {}, {}
    for row in rows:
        source = HERE / row['path']
        source.resolve().relative_to(HERE.resolve())
        if sha(source) != row['sha256']:
            raise ValueError('Package drift: ' + row['path'])
        if source.suffix == '.py':
            ast.parse(source.read_text(), filename=str(source))
    for row in code:
        target = dev / row['path']
        target.resolve().relative_to(dev)
        if target.is_symlink():
            raise ValueError('Checkout symlink rejected: ' + row['path'])
        if not target.exists():
            if not row.get('allow_missing'):
                raise ValueError('Checkout file missing: ' + row['path'])
            before[row['path']] = None
            additions[row['path']] = row['sha256']
        else:
            actual = sha(target)
            if actual not in row.get('allowed_predecessors', []) + [row['sha256']]:
                raise ValueError('FILE_DRIFT: ' + row['path'] + '; no files applied')
            before[row['path']] = actual
        print('FILE CHECK', row['path'], 'ADD' if before[row['path']] is None else 'PASS', flush=True)
    if check:
        engine_plan(dev)
        print('PREFLIGHT PASS', dev, 'code_files=' + str(len(code)), flush=True)
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = dev / '.genos-pipeline-optimization-backups' / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for path in [dev / '00_SYSTEM/PIPELINE.json', *sorted((dev / '02_BACKEND/ENGINES').rglob('*.json'))]:
        if path.is_file():
            before[str(path.relative_to(dev))] = sha(path)
    for name, expected in before.items():
        if expected is not None:
            target = backup / 'files' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dev / name, target)
            if sha(target) != expected:
                raise ValueError('Backup mismatch: ' + name)
    write(backup / 'before.json', {'dev': str(dev), 'before': before, 'added': additions,
                                 'python': sys.executable, 'version': sys.version,
                                 'code_manifest_sha256': sha(HERE / 'CODE_MANIFEST.json')})
    baseline = engine_plan(dev)
    write(backup / 'baseline-engine-plan.json', baseline)
    try:
        for row in code:
            target = dev / row['path']
            current = sha(target) if target.exists() else None
            if current != before[row['path']]:
                raise ValueError('Concurrent checkout drift: ' + row['path'])
            atomic_copy(HERE / row['path'], target)
            print('FILE APPLIED', row['path'], row['sha256'], flush=True)
        for source, expected in baseline['protected_existing_files'].items():
            if state(checkout_path(dev, source)) != expected:
                raise ValueError('Concurrent change outside package: ' + source)
        for source, expected in baseline['metadata_before'].items():
            if state(checkout_path(dev, source)) != expected:
                raise ValueError('Concurrent engine metadata drift: ' + source)
        plan = engine_plan(dev)
        if plan['protected_existing_files'] != baseline['protected_existing_files']:
            raise ValueError('Concurrent file set change outside package')
        write(backup / 'engine-plan.json', plan)
        allowed = {row['path'] for row in code}
        if set(plan.get('changed_code', [])) - allowed or plan.get('schemas'):
            raise ValueError('Unrelated engine/schema drift; rolling back')
        unlisted = set(plan.get('unlisted_runtime_files', []))
        if unlisted - allowed:
            raise ValueError('Unrelated unlisted runtime files; rolling back')
        applied = engine_plan(dev, apply=True, add_new=bool(unlisted))
        write(backup / 'engine-apply.json', applied)
        for row in code:
            if sha(dev / row['path']) != row['sha256']:
                raise ValueError('Applied code drift: ' + row['path'])
        write(backup / 'applied.json', {'dev': str(dev), 'files': {row['path']: row['sha256'] for row in code},
                                      'generation_activated': False, 'git_pushed': False,
                                      'serving_deployed': False, 'data_pins_rewritten': False})
    except BaseException:
        rollback(backup)
        raise
    print('CODE APPLIED backup/receipt=' + str(backup), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dev', type=Path, default=Path.home() / 'DEV')
    p.add_argument('--check', action='store_true')
    p.add_argument('--rollback', type=Path)
    a = p.parse_args()
    if a.rollback:
        rollback(a.rollback.resolve())
    else:
        apply(a.dev, check=a.check)

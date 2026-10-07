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


def native_engine_plan(root, *, control_dev, apply=False, add_new=False):
    env = {**os.environ, 'PYTHONPATH': str(control_dev / '02_BACKEND'), 'LAWRAG_WORKSPACE_ROOT': str(control_dev)}
    program = '''import json, pathlib, sys
from semantic_runtime import control
root = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(control.__file__).resolve() == pathlib.Path(sys.argv[4]).resolve() / '02_BACKEND/semantic_runtime/control.py', 'wrong control code root'
print('ENGINE CONTROL ' + str(control.__file__), file=sys.stderr, flush=True)
report = control.rehash_engines(root, apply=sys.argv[2] == '1', add_new=sys.argv[3] == '1')
print(json.dumps(report, ensure_ascii=False), flush=True)
broken = any(not row['ok'] for row in report['data_pins_checked_not_rewritten'])
stale = bool(report['engine_manifests'] or report['schemas']) and not report['applied']
sys.exit(1 if broken or stale else 0)
'''
    command = [sys.executable, '-u', '-c', program, str(root), str(int(apply)), str(int(add_new)), str(control_dev)]
    print('ENGINE REHASH START apply=' + str(apply) + ' add_new=' + str(add_new), flush=True)
    result = subprocess.run(command, cwd=control_dev, env=env, capture_output=True, text=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    diagnostic = HERE.parent / ('engine-command-' + stamp + '.json')
    write(diagnostic, {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
                       'dev': str(control_dev), 'metadata_root': str(root), 'apply': apply, 'add_new': add_new, 'python': sys.executable})
    print('ENGINE REHASH OUTPUT ' + str(diagnostic) + ' returncode=' + str(result.returncode), flush=True)
    if result.returncode not in (0, 1):
        raise ValueError('Engine rehash failed; diagnostics=' + str(diagnostic) + ': ' + result.stderr[-1600:])
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError('Engine rehash did not return JSON; diagnostics=' + str(diagnostic) + ': ' + result.stderr[-1600:]) from error
    required = ('changed_code', 'unlisted_runtime_files', 'schemas', 'engine_manifests', 'data_pins_checked_not_rewritten')
    if not isinstance(report, dict) or not all(isinstance(report.get(key), list) for key in required) or not isinstance(report.get('applied'), bool):
        raise ValueError('Invalid engine report contract; diagnostics=' + str(diagnostic))
    if apply and result.returncode:
        raise ValueError('Engine rehash application did not pass')
    return report


def engine_plan(dev, *, apply=False, add_new=False):
    """Rehash isolated engine metadata; preserve every original data/profile binding."""
    dev = dev.resolve()
    pipeline = dev / '00_SYSTEM/PIPELINE.json'
    original = pipeline.read_bytes()
    config = json.loads(original)
    names = [entry['manifest'] for entry in config['engines'].values()]
    before = {}
    for name in names:
        target = dev / name
        target.resolve().relative_to((dev / '02_BACKEND/ENGINES').resolve())
        if target.is_symlink(): raise ValueError('Engine manifest symlink rejected: ' + name)
        before[name] = sha(target)
    allowed = {r['path'] for r in json.loads((HERE / 'CODE_MANIFEST.json').read_text())['files'] if r['role'] == 'code'}
    with tempfile.TemporaryDirectory(prefix='genos-code-engine-') as temporary:
        root = Path(temporary)
        for item in dev.iterdir():
            if item.name not in {'02_BACKEND', '00_SYSTEM'}:
                (root / item.name).symlink_to(item, target_is_directory=item.is_dir())
        for folder in ('02_BACKEND', '00_SYSTEM'):
            (root / folder).mkdir()
            for item in (dev / folder).iterdir():
                if (folder, item.name) in {('02_BACKEND', 'ENGINES'), ('00_SYSTEM', 'PIPELINE.json')}:
                    continue
                (root / folder / item.name).symlink_to(item, target_is_directory=item.is_dir())
        shutil.copytree(dev / '02_BACKEND/ENGINES', root / '02_BACKEND/ENGINES', ignore=shutil.ignore_patterns('__pycache__'))
        isolated = json.loads(original)
        isolated['profiles'] = {}  # Only the isolated copy; original selections are never rewritten.
        write(root / '00_SYSTEM/PIPELINE.json', isolated)
        report = native_engine_plan(root, control_dev=dev)
        report['scope'] = 'code-engine-pins-only'
        report['legacy_data_pins_validated'] = False
        report['legacy_profiles_preserved'] = True
        if set(report['changed_code']) - allowed or set(report['unlisted_runtime_files']) - allowed or report['schemas']:
            raise ValueError('Unrelated engine/schema drift; rolling back')
        if apply:
            report = {**native_engine_plan(root, control_dev=dev, apply=True, add_new=add_new),
                      'scope': 'code-engine-pins-only', 'legacy_data_pins_validated': False,
                      'legacy_profiles_preserved': True}
            if pipeline.read_bytes() != original or any(sha(dev / n) != expected for n, expected in before.items()):
                raise ValueError('Concurrent engine metadata drift')
            updated = json.loads((root / '00_SYSTEM/PIPELINE.json').read_text())
            selected = json.loads(original)
            for name, entry in selected['engines'].items():
                entry['sha256'] = updated['engines'][name]['sha256']
            for name in names:
                old = json.loads((dev / name).read_bytes())
                new = json.loads((root / name).read_bytes())
                if {k: v for k, v in old.items() if k != 'files'} != {k: v for k, v in new.items() if k != 'files'}:
                    raise ValueError('Unexpected engine contract change: ' + name)
            for name in names:
                if sha(root / name) != before[name]: atomic_copy(root / name, dev / name)
            write(pipeline, selected)
        print('ENGINE CODE PINS CHECKED; historical data/profile pins preserved, not validated; serving not activated', flush=True)
        return report


def rollback(backup):
    receipt = json.loads((backup / 'before.json').read_text())
    dev = Path(receipt['dev'])
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
            atomic_copy(backup / 'files' / name, target)
    write(backup / 'rollback.json', {'dev': str(dev), 'restored': list(receipt['before']),
                                    'at': datetime.now(timezone.utc).isoformat()})
    print('ROLLBACK COMPLETE', backup, flush=True)


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
    try:
        for row in code:
            target = dev / row['path']
            current = sha(target) if target.exists() else None
            if current != before[row['path']]:
                raise ValueError('Concurrent checkout drift: ' + row['path'])
            atomic_copy(HERE / row['path'], target)
            print('FILE APPLIED', row['path'], row['sha256'], flush=True)
        plan = engine_plan(dev)
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

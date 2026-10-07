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


def engine_plan(dev, *, apply=False, add_new=False):
    env = {**os.environ, 'PYTHONPATH': str(dev / '02_BACKEND'), 'LAWRAG_WORKSPACE_ROOT': str(dev)}
    command = [sys.executable, '-u', '-m', 'semantic_runtime.control', 'rehash-engines']
    if apply:
        command.append('--apply')
    if add_new:
        command.append('--add-new')
    result = subprocess.run(command, cwd=dev, env=env, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise ValueError('Engine rehash failed: ' + result.stderr[-1600:])
    report = json.loads(result.stdout)
    if apply and result.returncode:
        raise ValueError('Engine rehash application did not pass')
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

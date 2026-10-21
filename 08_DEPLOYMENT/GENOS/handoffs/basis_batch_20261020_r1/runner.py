"""Verified incremental patch and entry to the maintained basis-batch CLI."""
import argparse
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
STATE = HERE / 'INSTALL_STATE.json'
CONFIG = '00_SYSTEM/GENOS_SERVING_PATHS.json'


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink path refused: ' + str(path))
    return path


def sha(path):
    return hashlib.sha256(plain(path).read_bytes()).hexdigest()


def write(path, value):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = plain(path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp'))
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load():
    spec = json.loads((HERE/'PACKAGE.json').read_bytes())
    for name, expected in spec['payload'].items():
        if sha(HERE/name) != expected:
            raise ValueError('Package file changed: ' + name)
    return spec


def check(root, spec, *, installed=False):
    root = plain(root).resolve(strict=True)
    if not (root/'.git').exists():
        raise ValueError('Existing DEV Git checkout required: ' + str(root))
    for name, target in spec['code'].items():
        path = plain(root/name)
        actual = sha(path) if path.is_file() else None
        allowed = [target] if installed else spec['allowed_before'].get(name, [target])
        if actual not in allowed:
            raise ValueError('Unknown code; preserved without overwrite: ' + name)
    return root


def gate(root, spec):
    check(root, spec, installed=True)
    pipeline = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
    for entry in pipeline['engines'].values():
        manifest = root/entry['manifest']
        if sha(manifest) != entry['sha256']:
            raise ValueError('Engine manifest differs: ' + str(manifest))
        for name, expected in json.loads(manifest.read_text())['files'].items():
            if sha(root/name) != expected:
                raise ValueError('Engine dependency differs: ' + name)
    for entry in pipeline['workflows']['registered']:
        manifest = root/entry['manifest']
        if sha(manifest) != entry['sha256']:
            raise ValueError('Workflow manifest differs: ' + str(manifest))
        value = json.loads(manifest.read_text())
        if value['version'] != entry['version']:
            raise ValueError('Workflow version differs')
        for name, expected in value['files'].items():
            if sha(root/'02_BACKEND/workflow'/name) != expected:
                raise ValueError('Workflow dependency differs: ' + name)
    for name in spec['patch']:
        if name.endswith('.py'):
            ast.parse((root/name).read_bytes(), filename=name, feature_version=(3,11))
    print(json.dumps({'status':'CODE_GATE_PASS','root':str(root),'files':len(spec['code']),
                      'python':sys.executable,'version':sys.version,'generation_opened':False,
                      'model_calls':0}), flush=True)


def apply(root, spec):
    root = check(root, spec)
    saved = json.loads(STATE.read_text()) if STATE.exists() else None
    if saved:
        if saved['root'] != str(root) or saved['package_sha256'] != sha(HERE/'PACKAGE.json'):
            raise ValueError('Existing installer state has another code root/package')
        if saved['status'] == 'rolled_back':
            raise ValueError('This delivery was rolled back; preserve its state and use a new extraction for a new install')
    else:
        saved = {'root':str(root),'package_sha256':sha(HERE/'PACKAGE.json'),'status':'prepared','files':{}}
        for name in spec['patch']:
            path = root/name
            raw = path.read_bytes() if path.exists() else None
            saved['files'][name] = {'before':hashlib.sha256(raw).hexdigest() if raw is not None else None,
                                   'after':spec['code'][name], 'mode':path.stat().st_mode & 0o777 if raw is not None else 0o644}
            if raw is not None:
                backup = HERE/'backup'/name
                if backup.exists() and backup.read_bytes() != raw:
                    raise ValueError('Existing backup differs: ' + name)
                write(backup, raw)
        # Backups and immutable target bindings precede the first checkout write.
        write(STATE, saved)
    for name, record in saved['files'].items():
        target = root/name
        actual = sha(target) if target.exists() else None
        if actual == record['after']:
            continue
        if actual != record['before']:
            raise ValueError('Checkout changed during apply: ' + name)
        if record['before'] is not None and sha(HERE/'backup'/name) != record['before']:
            raise ValueError('Backup changed: ' + name)
        write(target, (HERE/'payload'/name).read_bytes())
        target.chmod(record['mode'])
    gate(root, spec)
    saved['status'] = 'applied'
    write(STATE, saved)
    print('APPLIED: existing DEV checkout; source SQLite/indexes and Git history unchanged', flush=True)


def rollback(root, spec):
    saved = json.loads(STATE.read_text())
    if saved['root'] != str(root) or saved['package_sha256'] != sha(HERE/'PACKAGE.json'):
        raise ValueError('Rollback binding differs')
    # Validate every file before restoring any.
    for name, record in saved['files'].items():
        path = plain(root/name)
        actual = sha(path) if path.exists() else None
        if actual not in (record['before'], record['after']):
            raise ValueError('Newer changes exist; rollback refused: ' + name)
        if record['before'] is not None and sha(HERE/'backup'/name) != record['before']:
            raise ValueError('Backup changed: ' + name)
    for name, record in saved['files'].items():
        path = root/name
        if record['before'] is None:
            if path.exists():path.unlink()
        else:
            write(path, (HERE/'backup'/name).read_bytes())
            path.chmod(record['mode'])
    saved['status'] = 'rolled_back'
    write(STATE, saved)
    print('ROLLED_BACK_CODE: relationship DB and workflow history preserved', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['check','apply','gate','rollback','install-status',
                                           'list','plan','run','resume','status','export'])
    parser.add_argument('--root', type=Path, default=Path.home()/'DEV')
    parser.add_argument('--job', type=Path)
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--team', default='risk_team')
    args = parser.parse_args()
    root = plain(args.root).resolve(strict=True)
    spec = load()
    with plain(HERE/'installer.lock').open('a') as stream:
        mode=fcntl.LOCK_EX if args.command in ('apply','rollback') else fcntl.LOCK_SH
        fcntl.flock(stream, mode | fcntl.LOCK_NB)
        if args.command == 'check':
            check(root, spec)
            print('CHECK_PASS: verified known baseline; no code/data modification', flush=True)
        elif args.command == 'apply':apply(root, spec)
        elif args.command == 'rollback':rollback(root, spec)
        elif args.command == 'gate':gate(root, spec)
        elif args.command == 'install-status':
            print(STATE.read_text() if STATE.exists() else 'NOT_INSTALLED', flush=True)
        else:
            gate(root, spec)
            config = json.loads(plain(root/CONFIG).read_text())
            job = args.job or Path(config['runtime'])/'basis-batch'/'pilot-20261020-r1'
            command = [sys.executable, str(root/'06_TOOLS/pipeline.py'),'basis-batch',args.command,
                       '--root',str(root),'--job',str(job),'--team',args.team,'--count',str(args.count)]
            if args.ids:command += ['--ids',*args.ids]
            env = {**os.environ,'DP':'sqlite','SEMANTIC_LLM_BACKEND':'genos','PYTHONDONTWRITEBYTECODE':'1',
                   'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
                   'SOURCE_PROVIDER_PROJECT_ROOT':str(root),'TEAM_ID':args.team,
                   'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
            print(json.dumps({'event':'BATCH_DISPATCH','code_root':str(root),'generation':config['generation'],
                              'runtime':config['runtime'],'job':str(job),'data_provider':'sqlite',
                              'serving_DP_unchanged':True}), flush=True)
            return subprocess.call(command, cwd=root, env=env)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

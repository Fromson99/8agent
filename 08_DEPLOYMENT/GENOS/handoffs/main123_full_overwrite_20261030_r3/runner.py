"""Backed-up full MAIN123 overwrite authorized by the user on 2026-10-30."""
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


def checkout_root(requested):
    """Allow the checkout entry alias, then enforce physical paths below it."""
    root = plain(Path(requested).expanduser().resolve(strict=True))
    if not root.is_dir() or not (root / '.git').exists():
        raise ValueError('Existing DEV Git checkout required: ' + str(root))
    git_env = {key: value for key, value in os.environ.items()
               if not key.startswith('GIT_')}
    result = subprocess.run(
        ['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
        env=git_env, capture_output=True, text=True, timeout=15,
    )
    if result.returncode or Path(result.stdout.strip()).resolve(strict=True) != root:
        raise ValueError('DEV must resolve to the existing Git checkout root: ' + str(root))
    print(json.dumps({'event': 'CHECKOUT_RESOLVED', 'requested': str(requested),
                      'physical': str(root)}, ensure_ascii=False), flush=True)
    return root


def bind_root(root):
    """Keep later commands on the same physical checkout as the first check."""
    identity = root.stat()
    expected = {'root': str(root), 'device': identity.st_dev, 'inode': identity.st_ino,
                'package_sha256': sha(HERE / 'PACKAGE.json')}
    with plain(HERE / 'root-binding.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binding = plain(HERE / 'ROOT_BINDING.json')
        if binding.exists():
            if json.loads(binding.read_text()) != expected:
                raise ValueError('DEV target changed since first check; no automatic retargeting')
        else:
            write(binding, expected)


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


def git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    return subprocess.run(['git', '-C', str(root), *args], env=env,
                          capture_output=True, check=True, timeout=30).stdout


def check(root, spec, *, installed=False):
    root = plain(root).resolve(strict=True)
    # The sealed full-delivery contract authorizes replacing old, dirty and
    # untracked manifest targets, after backing up their exact current bytes.
    if spec.get('overwrite_existing') is not True or set(spec['patch']) != set(spec['code']):
        raise ValueError('Full overwrite requires a complete sealed code manifest')
    saved = json.loads(plain(STATE).read_text()) if STATE.exists() else None
    if saved and (saved['root'] != str(root) or saved['package_sha256'] != sha(HERE/'PACKAGE.json')):
        raise ValueError('Installer state binding differs')
    for name, target in spec['code'].items():
        path = plain(root/name)
        if path.exists() and not path.is_file():
            raise ValueError('Not a regular file: ' + name)
        actual = sha(path) if path.is_file() else None
        if installed or name not in spec['patch']:
            if actual != target:
                raise ValueError('Required MAIN123 file differs: ' + name)
        elif saved:
            record = saved['files'][name]
            if actual not in (record['before'], record['after']):
                raise ValueError('Checkout changed after preparation: ' + name)
    for name in spec['patch']:
        if name.endswith('.py'):
            raw = (HERE/spec['payload_paths'][name]).read_bytes()
            ast.parse(raw, filename=name, feature_version=(3,11))
            compile(raw, name, 'exec')
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
    saved = json.loads(plain(STATE).read_text()) if STATE.exists() else None
    if saved:
        if saved['root'] != str(root) or saved['package_sha256'] != sha(HERE/'PACKAGE.json'):
            raise ValueError('Existing installer state has another code root/package')
        if saved['status'] == 'rolled_back':
            raise ValueError('This delivery was rolled back; preserve its state and use a new extraction for a new install')
    else:
        saved = {'root':str(root),'package_sha256':sha(HERE/'PACKAGE.json'),'status':'prepared','overwrite_existing':True,'git_status_before':git(root,'status','--porcelain=v1','--untracked-files=normal').decode(),'files':{}}
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
        write(target, (HERE/spec['payload_paths'][name]).read_bytes())
        target.chmod(record['mode'])
    gate(root, spec)
    saved['status'] = 'applied'
    write(STATE, saved)
    print('APPLIED MAIN123 FULL R3: all 492 code files verified; original files backed up', flush=True)


def rollback(root, spec):
    saved = json.loads(plain(STATE).read_text())
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
    print('ROLLED_BACK_CODE: previous code bytes restored; data untouched', flush=True)


def validate_package_location(root, spec):
    """Allow TRANSFER below DEV, but never overlap a write target or Git metadata."""
    plain(HERE)
    if root == HERE or HERE in root.parents:
        raise ValueError('Package must not contain the DEV checkout')
    metadata = [root / '.git', Path(git(root, 'rev-parse', '--absolute-git-dir').decode().strip())]
    targets = list(metadata)
    for name in spec['code']:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            raise ValueError('Invalid code target: ' + name)
        if any(part in ('.git','.env','.venv','01_DATA','GENOS_DATA','TRANSFER') for part in relative.parts):
            raise ValueError('Protected destination is not a code target: ' + name)
        targets.append(plain(root / relative))
    for target in targets:
        if target == HERE or HERE in target.parents or target in HERE.parents:
            raise ValueError('Package overlaps a code target or Git metadata: ' + str(target))
    print(json.dumps({'event': 'PACKAGE_LOCATION_VALID', 'package': str(HERE),
                      'checkout': str(root), 'inside_checkout': root in HERE.parents}), flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['check','apply','gate','gate-code','gate-sqlite','rollback','status'])
    p.add_argument('--root',type=Path,default=Path.home()/'DEV')
    args=p.parse_args();root=checkout_root(args.root);spec=load()
    validate_package_location(root, spec)
    with plain(HERE/'installer.lock').open('a') as lock:
        fcntl.flock(lock, (fcntl.LOCK_EX if args.command in ('apply','rollback') else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        bind_root(root)
        if args.command=='check':check(root,spec);print('CHECK_PASS MAIN123: package hashes, dependencies, writable targets and Python syntax')
        elif args.command=='apply':apply(root,spec)
        elif args.command=='rollback':rollback(root,spec)
        elif args.command=='status':print(plain(STATE).read_text() if STATE.exists() else 'NOT_INSTALLED')
        else:
            gate(root,spec)
            if args.command in ('gate-code','gate-sqlite'):
                command=[sys.executable,str(HERE/'genos_release_gate.py'),'--code-zip',str(HERE/'code.zip'),'--deploy-root',str(root)]
                if args.command=='gate-code':command+=['--code-only']
                return subprocess.call(command,cwd=root)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as exc:
        print('FAILED: '+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(2)

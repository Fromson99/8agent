"""Install maintained CLI additions into the existing checkout; preserve runtime."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
ANCHOR = 'root = Path(__file__).resolve().parents[1]\n'
ENTRY = "if __name__ == '__main__' and sys.argv[1:2] == ['basis-work']:\n    os.execv(sys.executable, [sys.executable, str(root / '06_TOOLS/COMMANDS/basis_work.py'), *sys.argv[2:]])\n"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), '내부 경로의 심볼릭 링크는 지원하지 않습니다: ' + str(path))
    return path


def atomic(path, data):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def save(path, value):
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def patch_entry(raw):
    text = raw.decode('utf-8')
    if ENTRY in text:
        require(text.count(ENTRY) == 1, '중복 basis-work 진입점')
        return raw
    require("['basis-work']" not in text and text.count(ANCHOR) == 1,
            '알 수 없는 pipeline.py 진입점입니다. 기존 파일을 보존했습니다.')
    return text.replace(ANCHOR, ANCHOR + ENTRY, 1).encode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check', 'apply', 'status', 'rollback'])
    p.add_argument('--root', type=Path, default=Path.home() / 'DEV')
    a = p.parse_args()
    root = a.root.resolve(strict=True)
    gitroot = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], check=True, capture_output=True, text=True).stdout.strip()
    require(Path(gitroot).resolve() == root, '기존 Git checkout 루트에서만 적용합니다.')
    package = json.loads((HERE / 'PACKAGE.json').read_text())
    for name, fingerprint in package['payload'].items():
        require(sha(plain(HERE / 'payload' / name).read_bytes()) == fingerprint, '패키지 해시 불일치: ' + name)
    statepath = HERE / 'STATE.json'
    state = json.loads(statepath.read_text()) if statepath.exists() else None
    require(state is None or (state['root'] == str(root) and state['package_sha256'] == sha((HERE / 'PACKAGE.json').read_bytes())),
            '다른 checkout 또는 패키지의 설치 기록입니다.')
    print(json.dumps({'action': a.action, 'root': str(root), 'python': sys.executable,
                      'python_version': sys.version, 'package_sha256': sha((HERE / 'PACKAGE.json').read_bytes())}), flush=True)
    if a.action == 'status':
        result = state or {'status': 'NOT_APPLIED'}
        if state and state['status'] == 'APPLIED':
            drift = [name for name, row in state['files'].items()
                     if not plain(root / name).is_file() or sha(plain(root / name).read_bytes()) != row['after_sha256']]
            if drift:
                result = {**state, 'status': 'DRIFTED', 'changed_files': drift}
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 1 if result['status'] == 'DRIFTED' else 0
    with plain(HERE / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if a.action == 'rollback':
            require(state and state['status'] in ('APPLIED', 'APPLYING', 'ROLLED_BACK'), '원복할 설치 기록이 없습니다.')
            for name, row in state['files'].items():
                path = plain(root / name)
                actual = sha(path.read_bytes()) if path.exists() else None
                require(actual in (row['before_sha256'], row['after_sha256']), '설치 후 수정된 파일: ' + name)
                if row['before_sha256'] is not None:
                    require(sha(plain(HERE / 'backup' / name).read_bytes()) == row['before_sha256'], '백업 해시 불일치: ' + name)
            for name, row in state['files'].items():
                path = plain(root / name)
                if row['before_sha256'] is None:
                    if path.exists():
                        path.unlink()
                else:
                    atomic(path, plain(HERE / 'backup' / name).read_bytes())
            state['status'] = 'ROLLED_BACK'
            save(statepath, state)
            print('ROLLED_BACK: 이번 명령 추가분만 원복했습니다. 원문·후보·관계·로그는 보존했습니다.', flush=True)
            return 0
        changes = {name: plain(HERE / 'payload' / name).read_bytes() for name in package['payload']}
        entry = '06_TOOLS/pipeline.py'
        changes[entry] = patch_entry(plain(root / entry).read_bytes())
        rows = {}
        for name, after in changes.items():
            path = plain(root / name)
            before = path.read_bytes() if path.exists() else None
            fingerprint = sha(before) if before is not None else None
            if state:
                row = state['files'][name]
                require(fingerprint in (row['before_sha256'], row['after_sha256']), '설치 후 변경된 파일: ' + name)
                require(sha(after) == row['after_sha256'], '패키지 적용 결과가 달라졌습니다: ' + name)
            else:
                allowed = package['allowed_before'].get(name, [None])
                require(name == entry or fingerprint in [*allowed, sha(after)], '알 수 없는 기존 파일입니다: ' + name)
            rows[name] = {'before_sha256': fingerprint, 'after_sha256': sha(after)}
        if a.action == 'check':
            print('CHECK_PASS: 원문·설정·모델·MAIN·ignore 변경 없음', flush=True)
            return 0
        if state is None:
            for name, row in rows.items():
                if row['before_sha256'] is not None:
                    backup = plain(HERE / 'backup' / name)
                    require(not backup.exists() or sha(backup.read_bytes()) == row['before_sha256'],
                            '다른 중단 작업의 백업이 있습니다: ' + name)
                    atomic(backup, plain(root / name).read_bytes())
            state = {'root': str(root), 'package_sha256': sha((HERE / 'PACKAGE.json').read_bytes()),
                     'status': 'APPLYING', 'files': rows}
            save(statepath, state)
        for name, after in changes.items():
            atomic(root / name, after)
        state['status'] = 'APPLIED'
        save(statepath, state)
        print('APPLIED: python3 ~/DEV/06_TOOLS/pipeline.py basis-work check', flush=True)
    return 0


if __name__ == '__main__':
    os.umask(0o077)
    raise SystemExit(main())

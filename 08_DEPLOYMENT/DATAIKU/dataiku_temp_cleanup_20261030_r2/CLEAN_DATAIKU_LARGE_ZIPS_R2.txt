"""Delete two photographed work ZIPs only after matching retained managed objects.

No new local data copy, DB operation, process termination, or recursive deletion.
Run with other structure/load/verify jobs stopped.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

GIB = 1024 ** 3
OBSERVED = {'PIPELINE_SUPPORT.zip': 2267000459, 'compute-audit.zip': 440366952}
NAMESPACE = '_pipeline/dataiku-owned-v1/'


def stamp(path):
    path = Path(path)
    if path.absolute() != path.resolve():
        raise ValueError('SYMLINK_PATH')
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
        raise ValueError('NOT_OWNED_SINGLE_FILE')
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def process_guard(identity):
    if not Path('/proc/self/fd').is_dir():
        raise ValueError('PROCESS_VISIBILITY_UNAVAILABLE')
    unknown = False
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != os.getuid():
                continue
            for fd in (p / 'fd').iterdir():
                try:
                    s = fd.stat()
                    if (s.st_dev, s.st_ino) == identity[:2]:
                        raise ValueError('FILE_IN_USE')
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
        except OSError:
            unknown = True
    if unknown:
        raise ValueError('PROCESS_VISIBILITY_INCOMPLETE')


def digest(stream, size, label):
    h, count, tick = hashlib.sha256(), 0, time.monotonic()
    while True:
        block = stream.read(1024 ** 2)
        if not block:
            break
        count += len(block)
        if count > size:
            raise ValueError('BACKUP_OR_LOCAL_SIZE_MISMATCH')
        h.update(block)
        if time.monotonic() - tick >= 30:
            print(label, round(count / GIB, 2), '/', round(size / GIB, 2), 'GiB', flush=True)
            tick = time.monotonic()
    if count != size:
        raise ValueError('BACKUP_OR_LOCAL_SIZE_MISMATCH')
    return h.hexdigest()


def paths(folder):
    result = {}
    for name in folder.list_paths_in_partition():
        normalized = name.lstrip('/')
        if normalized in result:
            raise ValueError('REMOTE_PATH_AMBIGUOUS')
        result[normalized] = name
    return result


def small_json(folder, path):
    with folder.get_download_stream(path) as f:
        raw = f.read(1024 ** 2 + 1)
    if len(raw) > 1024 ** 2:
        raise ValueError('CHECKPOINT_TOO_LARGE')
    suffix = re.search(r'checkpoint-\d{10}-([0-9a-f]{64})\.json$', path)
    if not suffix or hashlib.sha256(raw).hexdigest() != suffix[1]:
        raise ValueError('CHECKPOINT_HASH_MISMATCH')
    return json.loads(raw)


def audit_backup(folder, sha, size):
    known = paths(folder)
    relative = '_pipeline/blobs/' + sha + '.zip'
    remote = NAMESPACE + relative
    if remote not in known:
        raise ValueError('AUDIT_BACKUP_NOT_FOUND')
    expression = re.compile(re.escape(NAMESPACE) + r'_pipeline/jobs/([^/]+)/checkpoint-(\d{10})-([0-9a-f]{64})\.json')
    latest = {}
    for name in known:
        match = expression.fullmatch(name)
        if match:
            job, seq = match[1], int(match[2])
            if job in latest and latest[job][0] == seq:
                raise ValueError('CHECKPOINT_SEQUENCE_CONFLICT')
            if job not in latest or seq > latest[job][0]:
                latest[job] = (seq, name)
    if len(latest) > 100:
        raise ValueError('TOO_MANY_JOBS_FOR_BOUNDED_CHECK')
    for _, name in sorted(latest.values(), reverse=True):
        value = small_json(folder, known[name])
        if value.get('audit_blob') == {'path': relative, 'sha256': sha, 'bytes': size}:
            return known[remote]
    raise ValueError('AUDIT_CURRENT_CHECKPOINT_REFERENCE_NOT_FOUND')


def support_backup(folder):
    known = paths(folder)
    matches = [known[n] for n in ('PIPELINE_SUPPORT.zip', 'PIPELINE_SUPPORT (1).zip') if n in known]
    if len(matches) != 1:
        raise ValueError('SUPPORT_BACKUP_MISSING_OR_AMBIGUOUS')
    return matches[0]


def recipe_config(code):
    body = ast.parse(code).body
    if not body or not isinstance(body[-1], ast.Expr):
        raise ValueError('RECIPE_CONFIG_CHANGED')
    call = body[-1].value
    if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
            or call.func.id != 'run_recipe' or len(call.args) != 2 or call.keywords):
        raise ValueError('RECIPE_CONFIG_CHANGED')
    stage, cfg = [ast.literal_eval(a) for a in call.args]
    if (stage != 'structure' or not isinstance(cfg, dict)
            or set(cfg) != {'landing', 'raw', 'structured', 'load', 'connection'}
            or cfg['landing'] != 'ehA8dpVm'
            or any(not isinstance(v, str) or not v for v in cfg.values())):
        raise ValueError('RECIPE_CONFIG_CHANGED')
    return cfg


def locate(root, filename, expected_size):
    found = []
    for directory in root.glob('legal-recipes-*'):
        if directory.is_symlink() or not directory.is_dir():
            continue
        path = directory / filename
        if path.exists() and stamp(path)[2] == expected_size:
            found.append(path)
    if len(found) > 1:
        raise ValueError('MULTIPLE_MATCHING_LOCAL_FILES')
    return found[0] if found else None


def delete_verified(path, folder, lookup, expected_size):
    before = stamp(path)
    if before[2] != expected_size or time.time() - path.stat().st_mtime < 600:
        raise ValueError('SIZE_CHANGED_OR_RECENT_FILE')
    process_guard(before)
    print('대조 시작:', path.name, round(expected_size / GIB, 3), 'GiB', flush=True)
    with path.open('rb') as src:
        sha = digest(src, expected_size, '로컬 확인')
    if stamp(path) != before:
        raise ValueError('LOCAL_CHANGED')
    remote = lookup(folder, sha, expected_size)
    with folder.get_download_stream(remote) as src:
        other = digest(src, expected_size, '보관본 확인')
    if other != sha:
        raise ValueError('BACKUP_CONTENT_MISMATCH')
    process_guard(before)
    if stamp(path) != before:
        raise ValueError('LOCAL_CHANGED_BEFORE_DELETE')
    # Only this verified archive is unlinked. Its workspace and records remain.
    path.unlink()
    return {'file': str(path), 'result': 'DELETED_VERIFIED_BACKUP', 'bytes': before[2],
            'sha256': sha, 'retained_remote': remote}


def run(dataiku):
    if dataiku.default_project_key() != 'LEGAL_RAG':
        raise ValueError('LEGAL_RAG_REQUIRED')
    root = Path('/tmp').resolve()
    fs = os.statvfs(root)
    result = {'actions': [], 'free_GiB_before': fs.f_bavail * fs.f_frsize / GIB}
    landing = dataiku.Folder('ehA8dpVm')
    for name, size in OBSERVED.items():
        path = None
        try:
            path = locate(root, name, size)
            if path is None:
                action = {'file': name, 'result': 'NOT_FOUND_AT_OBSERVED_SIZE'}
            else:
                if name == 'PIPELINE_SUPPORT.zip':
                    folder = landing
                    lookup = lambda f, h, n: support_backup(f)
                else:
                    project = dataiku.api_client().get_project('LEGAL_RAG')
                    code = project.get_recipe('LEGAL_02_STRUCTURE_GENOS_R1').get_settings().get_code()
                    cfg = recipe_config(code)
                    folder = dataiku.Folder(cfg['structured'])
                    lookup = audit_backup
                action = delete_verified(path, folder, lookup, size)
        except Exception as exc:
            # Do not print connection details, full checkpoint contents or tokens.
            reason = str(exc) if type(exc) is ValueError and re.fullmatch(r'[A-Z_]+', str(exc)) else type(exc).__name__
            action = {'file': str(path) if path else name, 'result': 'PRESERVED', 'reason': reason}
        result['actions'].append(action)
        print(action['file'], ':', action['result'], action.get('reason', ''), flush=True)
    fs = os.statvfs(root)
    result['free_GiB_after'] = fs.f_bavail * fs.f_frsize / GIB
    result['deleted_bytes'] = sum(a.get('bytes', 0) for a in result['actions'] if a['result'] == 'DELETED_VERIFIED_BACKUP')
    print('R2 정리 종료 | 삭제한 ZIP 합계:', round(result['deleted_bytes'] / GIB, 3), 'GiB')
    print('여유 공간:', round(result['free_GiB_before'], 3), '→', round(result['free_GiB_after'], 3), 'GiB')
    print('원본/색인/재개기록 유지. 적재/검증은 재실행하지 않았습니다.')
    return result


if __name__ == '__main__':
    import dataiku
    LARGE_CLEANUP_RESULT = run(dataiku)

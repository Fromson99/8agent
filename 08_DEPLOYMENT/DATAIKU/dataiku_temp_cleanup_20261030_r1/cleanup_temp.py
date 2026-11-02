"""Dataiku notebook: inventory temp usage, unlink proven duplicate archives only.

Run after import/verification cells have stopped. No DB, network, moves or rmtree.
"""
import hashlib
import heapq
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
import zipfile

JOB = 'financial-risk-success-20261005-schema-r2'
NFS = 'legal-existing-nfs-20261029-r1'
PACKAGE_HASHES = {
    'c2a91252dccfad7595e685dc0942e2252baa88964e636945cc725cdc21613406',
    'cd8834876f3dcc81cbafd3a322cb909a26957378167da902d26f809b2e24fed3',
    'f1284bd750d8a61b6354609842de71e999470ecef875a6769f7016abdbdc5866',
}
GIB = 1024 ** 3


def signature(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
        raise ValueError('NOT_OWNED_SINGLE_REGULAR_FILE')
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def safe_path(base, name):
    p = PurePosixPath(name)
    if (not p.parts or p.is_absolute() or '..' in p.parts or str(p) != name
            or '\\' in name or ':' in name):
        raise ValueError('UNSAFE_MEMBER')
    current = base
    if current.is_symlink() or current.resolve() != current.absolute():
        raise ValueError('SYMLINK_PARENT')
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('SYMLINK_MEMBER')
    return current


def zip_proof(archive, extracted, *, receipts=False):
    """Every archived byte must remain in an existing, unchanged extracted file."""
    before = signature(archive)
    witnesses = {}
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if not members or len(members) > 10000:
            raise ValueError('MEMBER_COUNT')
        names = [m.filename for m in members]
        if len(set(names)) != len(names):
            raise ValueError('DUPLICATE_MEMBER')
        if receipts and 'full-state.json' not in names:
            raise ValueError('NO_FULL_STATE')
        for m in members:
            if m.is_dir() or stat.S_ISLNK(m.external_attr >> 16):
                raise ValueError('NON_FILE_MEMBER')
            if receipts and not m.filename.endswith(('.json', '.jsonl')):
                raise ValueError('NOT_RECEIPT')
            p = safe_path(extracted, m.filename)
            stamp = signature(p)
            if stamp[2] != m.file_size:
                raise ValueError('EXTRACTED_SIZE_MISMATCH')
            with z.open(m) as src, p.open('rb') as dst:
                while True:
                    a, b = src.read(1024 ** 2), dst.read(1024 ** 2)
                    if a != b:
                        raise ValueError('EXTRACTED_BYTES_MISMATCH')
                    if not a:
                        break
            if signature(p) != stamp:
                raise ValueError('EXTRACTED_CHANGED')
            witnesses[p] = stamp
    if signature(archive) != before:
        raise ValueError('ARCHIVE_CHANGED')
    return before, witnesses


def candidate(path, root):
    parts = path.relative_to(root).parts
    if (len(parts) == 2 and re.fullmatch(r'legal-recipes-[A-Za-z0-9_-]+', parts[0])
            and parts[1] == 'package.zip'):
        return 'code_archive'
    if len(parts) != 3 or parts[:2] != (NFS, JOB):
        return None
    if parts[2] == 'oracle-receipts.zip':
        return 'receipt_archive'
    if re.fullmatch(r'saved-oracle_(receipt|r1_failure)_blob-[0-9a-f]{64}\.zip', parts[2]):
        return 'receipt_archive'
    return None


def prove(path, kind):
    if kind == 'code_archive':
        stamp = signature(path)
        if stamp[2] > 2 * 1024 ** 2:
            raise ValueError('UNKNOWN_PACKAGE_SIZE')
        if hashlib.sha256(path.read_bytes()).hexdigest() not in PACKAGE_HASHES:
            raise ValueError('UNKNOWN_PACKAGE_HASH')
        return zip_proof(path, path.parent / 'code')
    if kind != 'receipt_archive':
        raise ValueError('NOT_ALLOWED')
    for directory in ('oracle-import-r2', 'oracle-import'):
        try:
            return zip_proof(path, path.parent / directory, receipts=True)
        except (OSError, ValueError, zipfile.BadZipFile):
            pass
    raise ValueError('NO_IDENTICAL_EXTRACTED_RECEIPTS')


def process_files():
    """Inspect visible same-user descriptors; incomplete visibility blocks deletion."""
    opened, deleted, errors = set(), {}, []
    if not Path('/proc/self/fd').is_dir():
        return opened, [], ['PROC_UNAVAILABLE']
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            for fd in (proc / 'fd').iterdir():
                try:
                    target = os.readlink(fd)
                    s = fd.stat()
                    opened.add((s.st_dev, s.st_ino))
                    if target.endswith(' (deleted)') and stat.S_ISREG(s.st_mode):
                        deleted[(s.st_dev, s.st_ino)] = {
                            'pid': int(proc.name), 'path': target, 'bytes': s.st_size,
                            'allocated_bytes': s.st_blocks * 512}
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
        except (OSError, PermissionError) as exc:
            errors.append({'pid': proc.name, 'error': type(exc).__name__})
    return opened, sorted(deleted.values(), key=lambda x: x['allocated_bytes'], reverse=True)[:20], errors


def inventory(root, max_files=200000, seconds=60):
    device = root.stat().st_dev
    rows, top, candidates, errors = {}, [], [], []
    seen, count, deadline = set(), 0, time.monotonic() + seconds
    complete = True
    def onerror(exc):
        errors.append({'path': exc.filename, 'error': type(exc).__name__})
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        base = Path(directory)
        kept = []
        for name in dirs:
            p = base / name
            try:
                s = p.lstat()
                if not p.is_symlink() and s.st_dev == device and s.st_uid == os.getuid():
                    kept.append(name)
                else:
                    errors.append({'path': str(p), 'error': 'SKIPPED_LINK_MOUNT_OR_OTHER_OWNER'})
            except OSError as exc:
                onerror(exc)
        dirs[:] = sorted(kept)
        for name in files:
            count += 1
            if count > max_files or time.monotonic() >= deadline:
                complete = False
                break
            p = base / name
            try:
                s = p.lstat()
                if not stat.S_ISREG(s.st_mode) or s.st_dev != device:
                    continue
                inode = (s.st_dev, s.st_ino)
                if inode in seen:
                    continue
                seen.add(inode)
                size = s.st_blocks * 512
                group = p.relative_to(root).parts[0]
                rows[group] = rows.get(group, 0) + size
                heapq.heappush(top, (size, str(p), s.st_size))
                if len(top) > 30:
                    heapq.heappop(top)
                kind = candidate(p, root)
                if kind:
                    candidates.append((p, kind))
            except OSError as exc:
                onerror(exc)
        if not complete:
            break
    return {
        'root': str(root), 'scan_complete': complete and not errors,
        'files_seen': count, 'visible_allocated_GiB': round(sum(rows.values()) / GIB, 4),
        'largest_directories': [{'name': k, 'allocated_GiB': round(v / GIB, 4)}
                                for k, v in sorted(rows.items(), key=lambda x: -x[1])[:30]],
        'largest_files': [{'path': p, 'allocated_GiB': round(b / GIB, 4), 'bytes': n}
                          for b, p, n in sorted(top, reverse=True)],
        'scan_errors': errors[:20], 'scan_error_count': len(errors),
    }, candidates


def clean_one(path, kind, *, apply, min_age=600):
    stamp = signature(path)
    if time.time() - path.stat().st_mtime < min_age:
        raise ValueError('RECENT_FILE_PROTECTED')
    print('DUPLICATE_CHECK', str(path), flush=True)
    stamp, witnesses = prove(path, kind)
    opened, _, errors = process_files()
    if stamp[:2] in opened:
        raise ValueError('ARCHIVE_OPEN_IN_PROCESS')
    if errors:
        raise ValueError('PROCESS_VISIBILITY_INCOMPLETE')
    if signature(path) != stamp or any(signature(p) != s for p, s in witnesses.items()):
        raise ValueError('CHANGED_BEFORE_DELETE')
    # The only mutation: this exact archive's directory entry, never a directory.
    if apply:
        path.unlink()
    return {'path': str(path), 'kind': kind, 'bytes': stamp[2],
            'result': 'DELETED_DUPLICATE' if apply else 'VERIFIED_DUPLICATE'}


def run_cleanup(roots, *, apply=True):
    roots = sorted({Path(p).expanduser().resolve() for p in roots if Path(p).is_dir()}, key=str)
    roots = [p for p in roots if not any(q != p and q in p.parents for q in roots)]
    report = {'mode': 'clean_verified_archives' if apply else 'inspect',
              'inventories': [], 'actions': [],
              'protected': 'generation, SQLite DB/index, checkpoint, JSON/JSONL, S3, Oracle, unknown files'}
    for root in roots:
        before = os.statvfs(root)
        print('SCANNING', str(root), '(파일 크기만 확인)', flush=True)
        inv, candidates = inventory(root)
        report['inventories'].append(inv)
        print(json.dumps(inv, ensure_ascii=False, indent=2), flush=True)
        # Largest duplicate archives first. No unknown file is a deletion target.
        for path, kind in sorted(candidates, key=lambda x: x[0].lstat().st_size, reverse=True):
            try:
                action = clean_one(path, kind, apply=apply)
            except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
                action = {'path': str(path), 'result': 'PRESERVED', 'reason': str(exc)}
            report['actions'].append(action)
            print(json.dumps(action, ensure_ascii=False), flush=True)
        after = os.statvfs(root)
        inv['free_GiB_before'] = round(before.f_bavail * before.f_frsize / GIB, 4)
        inv['free_GiB_after'] = round(after.f_bavail * after.f_frsize / GIB, 4)
        inv['observed_free_change_GiB'] = round(
            (after.f_bavail * after.f_frsize - before.f_bavail * before.f_frsize) / GIB, 4)
    _, report['open_deleted_files'], report['process_visibility_errors'] = process_files()
    report['deleted_archive_count'] = sum(a['result'] == 'DELETED_DUPLICATE' for a in report['actions'])
    report['notes'] = [
        '초기/실패 시점 사용량이 없어 이번 목록만으로 증가 원인을 확정하지 않습니다.',
        '여유 공간 변화는 동시 작업의 영향도 포함합니다. 삭제한 파일 크기와 다를 수 있습니다.',
        '열린 삭제 파일은 프로세스가 핸들을 닫아야 회수됩니다. 프로세스를 종료하지 않았습니다.',
        '대형 원본/색인이 주 점유자이면 이 정리만으로 해결됐다고 판정하지 않습니다.',
        '적재/검증을 재실행하지 않았고 임시 경로를 변경하지 않았습니다.',
    ]
    print('CLEANUP_RESULT', json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


def notebook_main():
    import dataiku
    if dataiku.default_project_key() != 'LEGAL_RAG':
        raise ValueError('LEGAL_RAG 프로젝트에서 실행하세요.')
    variables = dataiku.get_custom_variables()
    roots = ['/tmp', '/var/tmp', '/usr/tmp']
    scratch = variables.get('LEGAL_PIPELINE_SCRATCH')
    if scratch:
        roots.append(str(scratch))
    return run_cleanup(roots, apply=True)


if __name__ == '__main__':
    CLEANUP_RESULT = notebook_main()

#!/usr/bin/env python3
"""Recover a PREPARED GENOS raw migration on NFS; keep the source, no model calls."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import uuid


def plain(path):
    p = Path(path).absolute()
    if '..' in p.parts or any(x.is_symlink() for x in (p, *p.parents)):
        raise ValueError('심볼릭 링크/상위 경로 거부: ' + str(p))
    return p


def relpath(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('잘못된 파일 경로')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or p.as_posix() != value or value == '.':
        raise ValueError('안전하지 않은 상대 경로: ' + value)
    return value


def payload(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def info(path):
    p = plain(path)
    if not stat.S_ISREG(p.stat().st_mode):
        raise ValueError('일반 파일이 아닙니다: ' + str(p))
    digest = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'sha256': digest.hexdigest(), 'bytes': p.stat().st_size}


def scan(root, emit=lambda x: None, *, marker=False):
    result = {}
    for p in sorted(plain(root).rglob('*')):
        p = plain(p)
        if p.is_dir():
            continue
        rel = p.relative_to(root).as_posix()
        if marker and rel == '.migration-in-progress':
            continue
        result[rel] = info(p)
        if len(result) % 200 == 0:
            emit(f'해시 검사: {len(result)}개 파일 확인 중')
    return result


def atomic(path, value):
    path = plain(path)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('xb') as f:
        f.write(payload(value)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)  # Plain file replacement is supported on NFS; no renameat2 flags.


def rebase(value, source):
    if isinstance(value, list):
        return [rebase(x, source) for x in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, val in value.items():
        if key in {'file', 'body_file', 'body_html_file'} and isinstance(val, str) and Path(val).is_absolute():
            out[key] = plain(val).relative_to(source).as_posix()
        else:
            out[key] = rebase(val, source)
    return out


def copy_stream(stream, dest, *, resume):
    """Resume only an owned partial file after exact prefix comparison; never truncate."""
    dest = plain(dest)
    if dest.exists():
        if not resume or not stat.S_ISREG(dest.stat().st_mode):
            raise ValueError('기존 대상 파일 충돌: ' + str(dest))
        with dest.open('rb') as old:
            while True:
                chunk = old.read(1024 * 1024)
                if not chunk:
                    break
                if stream.read(len(chunk)) != chunk:
                    raise ValueError('중단 파일이 원본과 다름. 덮어쓰기 거부: ' + str(dest))
        mode = 'ab'
    else:
        mode = 'xb'
    with dest.open(mode) as f:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            f.write(chunk)
        f.flush(); os.fsync(f.fileno())


def recover(root, *, apply=False, emit=print):
    root = plain(root)
    layout = json.loads((root / '00_SYSTEM/WORKSPACE.json').read_text())
    matches = [x for x in layout['roots'] if x['id'] == 'data']
    if len(matches) != 1 or matches[0]['canonical_path'] != '01_DATA':
        raise ValueError('공통 01_DATA 레이아웃이 아닙니다')
    source, target = plain(root / 'data/corpus'), plain(root / '01_DATA/RAW')
    record = plain(root / '01_DATA/LOGS/raw-migration/receipt.json')
    progress_path = plain(record.parent / 'nfs-copy-progress.json')
    original = json.loads(record.read_text())
    if original.get('source') != str(source) or original.get('target') != str(target):
        raise ValueError('원문/대상 경로가 이동 기록과 다릅니다')
    copying = original.get('method') == 'NFS_COPY_KEEP_SOURCE'
    if (not copying and original['status'] != 'PREPARED') or (copying and original['status'] not in {'COPYING', 'COMPLETED'}):
        raise ValueError('PREPARED 복구 또는 이 복구 파일로 시작한 작업만 지원합니다')
    before, manifests = original['before'], original['manifests']
    if not before or not source.is_dir():
        raise ValueError('원문 폴더 또는 고정 목록이 없습니다')
    for rel in before:
        relpath(rel)
    if '.migration-in-progress' in before or not set(manifests) <= set(before):
        raise ValueError('잘못된 이동 목록/manifest')
    emit('1/3 원본 전체 해시 검사 (원본은 삭제하지 않습니다)')
    if scan(source, emit) != before:
        raise ValueError('PREPARED 이후 원문이 변경됐습니다. 자동 반입 중단.')
    for rel, value in manifests.items():
        if rebase(json.loads((source / rel).read_text()), source) != value:
            raise ValueError('manifest 경로 변환 기록이 원본과 다릅니다: ' + rel)
    expected = dict(before)
    for rel, value in manifests.items():
        data = payload(value)
        expected[rel] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    marker = plain(target / '.migration-in-progress')
    if not copying and target.exists():
        raise ValueError('RAW가 이미 있습니다. 병합/덮어쓰기하지 않습니다.')
    if copying and target.exists():
        if marker.exists():
            if marker.read_text() != original['copy_token']:
                raise ValueError('다른 작업의 RAW 표시 파일입니다')
        elif original['status'] != 'COMPLETED':
            raise ValueError('소유 표시 없는 미완료 RAW: 자동 덮어쓰기하지 않습니다')
    if original['status'] == 'COMPLETED':
        if not target.is_dir() or scan(target, emit, marker=True) != expected or original['after'] != expected:
            raise ValueError('완료된 RAW가 변경됐습니다. 원본은 보존합니다.')
        if apply and marker.exists():
            marker.unlink()  # Only our verified in-progress marker, never source/data.
        return {'status': 'ALREADY_COPIED', 'files': len(expected), 'target': str(target)}
    if not apply:
        return {'status': 'PREVIEW_ONLY', 'files': len(expected), 'target': str(target), 'source_kept': str(source)}
    if not copying:
        backup = plain(record.parent / 'receipt-before-nfs.json')
        if backup.exists():
            if json.loads(backup.read_text()) != original:
                raise ValueError('이전 기록 백업 충돌')
        else:
            with backup.open('xb') as f:
                f.write(payload(original)); f.flush(); os.fsync(f.fileno())
        original.update(method='NFS_COPY_KEEP_SOURCE', status='COPYING',
                        copy_token=uuid.uuid4().hex)
        atomic(record, original)
    if not progress_path.exists():
        if target.exists():
            raise ValueError('복사 진행 기록이 없습니다. 자동 덮어쓰기하지 않습니다')
        atomic(progress_path, {'token': original['copy_token'], 'completed': 0, 'inflight': None})
    progress = json.loads(progress_path.read_text())
    count = progress['completed']
    if progress['token'] != original['copy_token'] or type(count) is not int or not 0 <= count <= len(expected):
        raise ValueError('복사 진행 기록이 잘못됐습니다')
    next_rel = list(expected)[count] if count < len(expected) else None
    if progress['inflight'] not in (None, next_rel):
        raise ValueError('진행 중 파일 기록이 순서와 다릅니다')
    if not target.exists():
        target.mkdir()  # Exclusive directory claim, no renameat2 or merge.
        with marker.open('x') as f:
            f.write(original['copy_token']); f.flush(); os.fsync(f.fileno())
    actual = scan(target, marker=True)
    if not set(actual) <= set(expected):
        raise ValueError('RAW에 예상하지 않은 파일이 있습니다')
    done = set(list(expected)[:count])
    for rel in actual:
        if rel in done and actual[rel] != expected[rel]:
            raise ValueError('복사 완료 파일 변조: ' + rel)
        if rel not in done and rel != progress['inflight']:
            raise ValueError('기록 없는 대상 파일 충돌: ' + rel)
    emit('2/3 RAW 복사 시작 (중단 후 같은 명령으로 재개)')
    for index, (rel, expected_info) in enumerate(expected.items(), 1):
        dest = plain(target / rel)
        if rel in done:
            if actual.get(rel) != expected_info:
                raise ValueError('복사 완료 파일 누락/변경: ' + rel)
            continue
        resume = progress['inflight'] == rel
        if dest.exists() and not resume:
            raise ValueError('대상 파일이 이미 있습니다: ' + rel)
        progress['inflight'] = rel
        atomic(progress_path, progress)
        dest.parent.mkdir(parents=True, exist_ok=True)
        stream = io.BytesIO(payload(manifests[rel])) if rel in manifests else plain(source / rel).open('rb')
        with stream:
            copy_stream(stream, dest, resume=resume)
        if info(dest) != expected_info:
            raise ValueError('복사 결과 해시 불일치: ' + rel)
        progress.update(completed=index, inflight=None)
        atomic(progress_path, progress)
        if index % 100 == 0 or index == len(expected):
            emit(f'복사 {index}/{len(expected)} | {rel}')
    # Preserve empty upload directories too, particularly RAW/internal.
    for p in source.rglob('*'):
        if plain(p).is_dir():
            plain(target / p.relative_to(source)).mkdir(parents=True, exist_ok=True)
    emit('3/3 원본·RAW 최종 전체 해시 검사')
    if scan(source, emit) != before or scan(target, emit, marker=True) != expected:
        raise ValueError('최종 해시/목록 불일치. 적재 차단 유지; 원본 보존.')
    original.update(status='COMPLETED', after=expected, source_retained=True)
    atomic(record, original)
    if marker.read_text() != original['copy_token']:
        raise ValueError('완료 표시 충돌. 적재를 시작하지 마세요.')
    marker.unlink()
    return {'status': 'COPIED_VERIFIED', 'files': len(expected), 'target': str(target),
            'source_kept': str(source), 'note': '원본 보존, 전체 해시 검증 완료. LLM/임베딩 호출 없음.'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='/workspace')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    os.umask(0o077)
    try:
        root = plain(args.root)
        if args.apply:
            with plain(root / '01_DATA/.raw-migration.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = recover(root, apply=True)
        else:
            result = recover(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print('중단됨. 원본 보존. 같은 --apply 명령으로 재개하세요.')
        return 130
    except Exception as exc:
        print('복구 중단: ' + str(exc) + '\n원본/RAW/receipt.json은 삭제하지 마세요.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

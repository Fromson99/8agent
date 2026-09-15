"""Explicit same-filesystem raw-folder relocation, with recoverable manifest rebasing."""
from __future__ import annotations
import ctypes
import errno
import json
import os
from pathlib import Path
import shutil

from .genos_build import atomic
from .genos_stages import plain_path
from semantic_runtime.contracts import sha

PATH_FIELDS = {'file', 'body_file', 'body_html_file'}


def scan(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError('특수 파일/심볼릭 링크 이동 거부: ' + str(p))
        if p.is_file():
            result[p.relative_to(root).as_posix()] = {'sha256': sha(p), 'bytes': p.stat().st_size}
    return result


def rebase(value, source):
    """Only known manifest path fields; never edit document text or SHA fields."""
    if isinstance(value, list):
        return [rebase(x, source) for x in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in PATH_FIELDS and isinstance(item, str) and Path(item).is_absolute():
                path = Path(item)
                if '..' in path.parts:
                    raise ValueError('manifest parent traversal')
                try:
                    result[key] = path.relative_to(source).as_posix()
                except ValueError:
                    raise ValueError('원문 폴더 밖의 절대 경로: ' + item) from None
            else:
                result[key] = rebase(item, source)
        return result
    return value


def rename_no_replace(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        raise ValueError('안전한 원자 이동(renameat2)을 지원하지 않습니다. 원본을 보존합니다.')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def move(source, data, *, apply=False):
    source, data = plain_path(source), plain_path(data)
    target = plain_path(data / 'RAW')
    if source == target or source == data or source in data.parents or data in source.parents:
        raise ValueError('원문과 대상 폴더가 겹칩니다')
    record = plain_path(data / 'LOGS/raw-migration/receipt.json')
    if record.exists():
        receipt = json.loads(record.read_text())
        if receipt['source'] != str(source) or receipt['target'] != str(target):
            raise ValueError('다른 원문 이동 영수증이 있습니다')
        if receipt['status'] == 'COMPLETED':
            if source.exists() or not target.is_dir() or scan(target) != receipt['after']:
                raise ValueError('이전 이동 이후 원문이 변경됨. 덮어쓰지 않습니다.')
            return {'status': 'ALREADY_MOVED', 'target': str(target), 'files': len(receipt['after'])}
        if receipt['status'] not in {'PREPARED', 'MOVING'}:
            raise ValueError('알 수 없는 이동 상태')
        if source.exists() and target.exists():
            raise ValueError('원문과 대상이 동시에 존재합니다. 충돌, 덮어쓰지 않습니다.')
    else:
        if target.exists():
            raise FileExistsError('대상 RAW가 이미 있습니다. 병합/덮어쓰지 않습니다: ' + str(target))
        if not source.is_dir() or source.parent == source or (source / '.git').exists():
            raise ValueError('원문 전용 폴더를 지정하세요')
        before = scan(source)
        if not before:
            raise ValueError('원문 폴더가 비어 있습니다')
        manifests = {}
        for relative in before:
            if Path(relative).name == 'manifest.json':
                manifests[relative] = rebase(json.loads((source / relative).read_text()), source)
        receipt = {'status': 'PREPARED', 'source': str(source), 'target': str(target),
                   'before': before, 'manifests': manifests}
    if not apply:
        return {'status': 'PREVIEW_ONLY', 'source': str(source), 'target': str(target),
                'files': len(receipt['before']), 'bytes': sum(x['bytes'] for x in receipt['before'].values()),
                'manifests': len(receipt['manifests']), 'note': '--apply 전에는 이동하지 않습니다'}
    data.mkdir(parents=True, exist_ok=True)
    current = source if source.exists() else target
    if current.stat().st_dev != data.stat().st_dev:
        raise ValueError('다른 파일시스템입니다. 자동 복사/삭제하지 않습니다.')
    record.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        if scan(source) != receipt['before']:
            raise ValueError('이동 점검 이후 원문 변경됨')
        for relative in receipt['manifests']:
            backup = plain_path(record.parent / 'original-manifests' / relative)
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copyfile(source / relative, backup)
            if sha(backup) != receipt['before'][relative]['sha256']:
                raise ValueError('manifest 백업 해시 불일치')
        atomic(record, receipt)
        rename_no_replace(source, target)
    receipt['status'] = 'MOVING'
    atomic(record, receipt)
    # Interrupted rewrites are repeatable from original-manifest backups and frozen values.
    actual = scan(target)
    if set(actual) != set(receipt['before']):
        raise ValueError('이동 중 파일 목록 변경됨')
    for relative, info in receipt['before'].items():
        if relative not in receipt['manifests'] and actual[relative] != info:
            raise ValueError('이동 중 원문 해시 변경됨: ' + relative)
    for relative, value in receipt['manifests'].items():
        backup = record.parent / 'original-manifests' / relative
        if sha(backup) != receipt['before'][relative]['sha256']:
            raise ValueError('manifest 원본 백업 변경됨')
        atomic(target / relative, value)
    receipt.update(status='COMPLETED', after=scan(target))
    atomic(record, receipt)
    return {'status': 'MOVED', 'target': str(target), 'files': len(receipt['after']),
            'receipt': str(record), 'note': '원문 내용 보존. manifest 경로만 상대경로로 변경, 원본 manifest 백업 보존.'}

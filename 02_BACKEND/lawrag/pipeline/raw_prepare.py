"""Offline, copy-verified public package export into the shared authoring RAW tree.

Packages are immutable inputs, never move sources or hardlink them into writable RAW.
The caller owns the same exclusive migration lock used by the four-stage runner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

from lawrag.datasets.catalog import load_package
from semantic_runtime.contracts import sha
from .genos_build import atomic
from .genos_corpus import SOURCES
from .genos_raw_move import PATH_FIELDS, rename_no_replace, scan
from .genos_stages import plain_path

STAGES = ('STRUCTURE', 'LLM', 'VECTOR', 'LOGS')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('잘못된 상대 경로: ' + repr(value))
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or value != p.as_posix() or value == '.':
        raise ValueError('절대/상위/비정규 경로 거부: ' + value)
    return p


def normalized_manifest(value, source, files):
    """Rebase declared raw coordinates only; retain all titles, hashes and metadata."""
    if isinstance(value, list):
        return [normalized_manifest(x, source, files) for x in value]
    if not isinstance(value, dict):
        return value
    out = {}
    hash_fields = {'file': 'sha256', 'body_file': 'body_sha256',
                   'body_html_file': 'body_html_sha256'}
    for key, item in value.items():
        if key in PATH_FIELDS and item not in (None, ''):
            rel = relative(item).as_posix()
            for prefix in (f'data/corpus/{source}/', f'01_DATA/corpus/{source}/',
                           f'01_DATA/INBOX/AUTHORING/corpus/{source}/',
                           f'01_DATA/RAW/{source}/', f'corpus/{source}/', f'{source}/'):
                if rel.startswith(prefix):
                    rel = relative(rel[len(prefix):]).as_posix()
                    break
            if rel not in files:
                raise ValueError(f'{source}: manifest 원문이 패키지에 없음: {item}')
            if value.get(hash_fields[key]) != files[rel]['sha256']:
                raise ValueError(f'{source}: manifest 원문 해시 불일치: {item}')
            out[key] = rel
        else:
            out[key] = normalized_manifest(item, source, files)
    return out


def package_plan(root, selection_path):
    root, selection_path = plain_path(root), plain_path(selection_path)
    selection = json.loads(selection_path.read_text('utf-8'))
    if selection.get('schema_version') != 'raw-package-selection-v1':
        raise ValueError('지원하지 않는 패키지 선택 형식')
    pins = selection['packages']
    if len(pins) != len(SOURCES) or {x['source'] for x in pins} != set(SOURCES):
        raise ValueError('외규 7종을 각각 한 개의 고정 세대로 선택해야 합니다')
    planned, packages = {}, []
    for pin in pins:
        source = pin['source']
        manifest = plain_path(root / relative(pin['manifest']))
        manifest.relative_to(root / '01_DATA/PACKAGES')
        if sha(manifest) != pin['sha256']:
            raise ValueError('패키지 선택 해시 불일치: ' + str(manifest))
        package = load_package(manifest, verify_files=True)
        if (package.dataset_id != 'source-' + source or package.source_origin != 'public_external'
                or package.security_class != 'public' or package.representation != 'real'):
            raise ValueError('공개 실제 외규 원문 패키지만 허용: ' + source)
        files, original_manifest = {}, None
        for artifact in package.artifacts:
            if artifact.role != 'raw':
                raise ValueError('원문 외 산출물이 섞인 패키지 거부: ' + source)
            rel = relative(artifact.path).relative_to('ARTIFACTS').as_posix()
            path = plain_path(manifest.parent / artifact.path)
            row = {'source_path': str(path), 'sha256': artifact.sha256,
                   'bytes': path.stat().st_size, 'logical_id': artifact.logical_id,
                   'document_id': artifact.document_id}
            if artifact.logical_id == f'source:{source}:manifest':
                if original_manifest is not None:
                    raise ValueError('원문 manifest 중복')
                original_manifest = row
            else:
                if rel in files or rel == 'manifest.json':
                    raise ValueError('대상 원문 경로 충돌: ' + rel)
                files[rel] = row
        if not files or original_manifest is None:
            raise ValueError('원문 또는 SOURCE_MANIFEST 없음: ' + source)
        provenance = {k: getattr(package, k) for k in (
            'package_id', 'dataset_id', 'version_id', 'generation_id', 'build_id',
            'source_origin', 'security_class', 'representation', 'authority',
            'export_allowed', 'manifest_sha256')}
        provenance['source_manifest_sha256'] = original_manifest['sha256']
        value = normalized_manifest(json.loads(Path(original_manifest['source_path']).read_text('utf-8')),
                                    source, files)
        if not isinstance(value, dict) or not isinstance(value.get('items'), list):
            raise ValueError('원문 manifest items 목록 없음')
        value['raw_package_provenance'] = provenance
        payload = encoded(value)
        for rel, row in files.items():
            planned[source + '/' + rel] = row
        planned[source + '/manifest.json'] = {'content': value,
            'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
        packages.append({**pin, 'files': len(files), 'provenance': provenance,
                         'original_manifest': original_manifest})
    return {'schema_version': 'raw-package-import-v1', 'selection_sha256': sha(selection_path),
            'packages': packages, 'files': planned, 'excluded': selection.get('excluded', [])}


def protected(data):
    return {name: scan(plain_path(data / name)) for name in ('ACTIVE', 'SOURCE_SETS', 'CATALOG')
            if (data / name).exists()}


def verify_destination(target, plan, *, allow_additions=False):
    actual = scan(plain_path(target))
    expected = {k: {n: row[n] for n in ('sha256', 'bytes')} for k, row in plan['files'].items()}
    if not all(actual.get(k) == row for k, row in expected.items()):
        raise ValueError('RAW 원문/manifest 해시 불일치. 덮어쓰지 않습니다.')
    if not allow_additions and actual != expected:
        raise ValueError('복사 대기 폴더에 예상하지 않은 파일이 있습니다')
    return len(actual) - len(expected)


def import_packages(root, data, selection_path, *, apply=False):
    """Preview verifies every input. Apply is resumable and never overwrites RAW."""
    root, data = plain_path(root), plain_path(data)
    target = plain_path(data / 'RAW')
    record = plain_path(data / 'LOGS/raw-package-import/receipt.json')
    staging = plain_path(record.parent / 'staging')
    plan = package_plan(root, selection_path)
    receipt = json.loads(record.read_text('utf-8')) if record.exists() else None
    if receipt:
        if receipt['plan'] != plan or receipt['target'] != str(target):
            raise ValueError('이전 반입과 선택 세대/경로가 다릅니다. 기존 자료를 보존합니다.')
        if receipt['status'] not in ('COPYING', 'COMPLETED'):
            raise ValueError('알 수 없는 반입 영수증 상태')
    elif target.exists():
        raise FileExistsError('RAW가 이미 있습니다. 자동 병합/덮어쓰기 거부: ' + str(target))
    summary = {'status': 'PREVIEW_ONLY', 'target': str(target),
               'raw_files': sum(x['files'] for x in plan['packages']), 'manifests': len(plan['packages']),
               'bytes': sum(x['bytes'] for x in plan['files'].values()),
               'sources': {x['source']: x['files'] for x in plan['packages']},
               'excluded': plan['excluded'], 'receipt': str(record)}
    if target.exists():
        added = verify_destination(target, plan, allow_additions=receipt['status'] == 'COMPLETED')
        summary.update(status='ALREADY_IMPORTED', additional_files_preserved=added)
        if not apply or receipt['status'] == 'COMPLETED':
            return summary
    if not apply:
        return summary
    for name in (*STAGES, 'LOGS/raw-package-import'):
        plain_path(data / name).mkdir(parents=True, exist_ok=True)
    if receipt is None:
        if staging.exists():
            raise ValueError('영수증 없는 복사 대기 폴더가 있습니다. 보존 후 중단합니다.')
        receipt = {'status': 'COPYING', 'target': str(target), 'plan': plan,
                   'protected_before': protected(data)}
        atomic(record, receipt)
    if protected(data) != receipt['protected_before']:
        raise ValueError('활성 배포/SourceSet/catalog 변경 감지. 자동 진행 중단.')
    if not target.exists():
        staging.mkdir(exist_ok=True)
        (staging / 'internal').mkdir(exist_ok=True)  # User uploads; no synthetic internal examples.
        for rel, row in plan['files'].items():
            dest = plain_path(staging / relative(rel))
            if dest.exists():
                if not dest.is_file() or sha(dest) != row['sha256']:
                    raise ValueError('복사 대기 파일 충돌: ' + rel)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            # A single private scratch file is safely reusable after an interrupted copy.
            tmp = plain_path(record.parent / 'copy.tmp')
            if 'content' in row:
                tmp.write_bytes(encoded(row['content']))
            else:
                shutil.copyfile(plain_path(row['source_path']), tmp)
            if sha(tmp) != row['sha256'] or tmp.stat().st_size != row['bytes']:
                raise ValueError('복사 중 원문 변경/손상: ' + rel)
            rename_no_replace(tmp, dest)
        verify_destination(staging, plan)
        # Recheck selected package bytes before publishing, not only before copying.
        if package_plan(root, selection_path) != plan or protected(data) != receipt['protected_before']:
            raise ValueError('반입 중 입력/보호 자료 변경. RAW를 발행하지 않습니다.')
        rename_no_replace(staging, target)
    verify_destination(target, plan)
    receipt.update(status='COMPLETED', protected_after=protected(data))
    atomic(record, receipt)
    summary.update(status='IMPORTED', note='원문 복사·해시 검증 완료. 패키지/배포 보존. LLM 호출 없음.')
    return summary

"""Explicit re-admission of edited team RAW; caller holds the RAW write lock.

Only the working registration changes. Historic receipts, packages, structure
caches and serving generations are never rewritten. No parser/model calls.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import uuid

from semantic_runtime.contracts import sha
from .genos_stages import plain_path
from . import genos_build as build, team_raw


def refresh(data, *, apply=False):
    data = plain_path(data)
    pointer = plain_path(data / 'CATALOG/TEAM_LAYOUT.json')
    before = team_raw.config(data)
    if before is None:
        raise ValueError('TEAM_LAYOUT.json 없음: 먼저 팀별 RAW를 준비하세요')
    pointer_sha = sha(pointer)
    files = {str(p.relative_to(data)): (p, source, team)
             for p, source, team in team_raw.inputs(data)}
    hashes = {rel: sha(row[0]) for rel, row in files.items()}
    old = before['files']
    # Never follow catalog paths outside the explicitly scanned team tree.
    for rel in old:
        parts = Path(rel).parts
        if (Path(rel).is_absolute() or '..' in parts or len(parts) < 4
                or parts[0] != 'RAW' or parts[1] not in {'internal', 'external'}):
            raise ValueError('invalid registered team path: ' + rel)
        plain_path(data / rel)
    missing = {rel: row for rel, row in old.items() if rel not in files}
    updated, events, consumed = {}, [], set()
    for rel, (path, source, team) in files.items():
        identity = hashes[rel]
        previous = rel if rel in old else None
        if previous is None:
            candidates = [r for r, item in missing.items()
                          if item['sha256'] == identity and Path(r).parts[1] == source]
            if len(candidates) > 1:
                raise ValueError('이동 원본이 여러 개여서 자동 결속할 수 없음: ' + rel)
            previous = candidates[0] if candidates else None
        if previous is None:
            # Leave additions to the existing intake/derivative contracts. Do not
            # relabel extracted attachments or inherit export permission by name.
            continue
        item = copy.deepcopy(old[previous])
        changed = item['sha256'] != identity
        if changed:
            # A public-source approval is hash-bound; edited bytes do not inherit it.
            item['export_allowed'] = False
            item.setdefault('source_metadata', {})['export_allowed'] = False
        item['sha256'] = identity
        if previous != rel:
            consumed.add(previous)
            item['team'] = team
        updated[rel] = item
        if changed or previous != rel:
            events.append({'kind': 'CONTENT_CHANGED' if changed else 'MOVED',
                           'old_path': previous, 'path': rel,
                           'old_sha256': old[previous]['sha256'], 'sha256': identity})
    for rel, item in missing.items():
        if rel not in consumed:
            events.append({'kind': 'NO_LONGER_PRESENT', 'old_path': rel,
                           'old_sha256': item['sha256']})
    # Refresh must not silently certify stale generated PDFs/XML projections or
    # a different ZIP as the provenance of already extracted documents.
    derivatives = plain_path(data / 'CATALOG/RAW_DERIVATIVES.json')
    derivatives_sha = sha(derivatives) if derivatives.exists() else None
    if derivatives_sha:
        records = json.loads(derivatives.read_text())
        for rel, item in records.get('files', {}).items():
            if rel in files and (hashes[rel] != item['sha256']
                                 or hashes.get(item['origin']) != item['origin_sha256']):
                raise ValueError('파생본/원본 연결 변경: 해시 갱신으로 변환을 승인할 수 없음: ' + rel)
        for rel, item in records.get('extractions', {}).items():
            if rel in files and (hashes[rel] != item['sha256']
                                 or hashes.get(item['archive']) != item['archive_sha256']):
                raise ValueError('ZIP 추출 계보 변경: 새 반입이 필요함: ' + rel)
    summary = {'status': 'PLANNED' if events else 'UNCHANGED',
               'counts': dict(Counter(e['kind'] for e in events)),
               'registered_files': len(updated), 'scanned_files': len(files),
               'events': events, 'activated': False}
    if not apply or not events:
        return summary
    # Recheck bytes and selection immediately before committing the registration.
    current = {str(p.relative_to(data)): sha(p) for p, _, _ in team_raw.inputs(data)}
    if (current != hashes or sha(pointer) != pointer_sha
            or (sha(derivatives) if derivatives.exists() else None) != derivatives_sha):
        raise ValueError('갱신 도중 입력/등록 변경: 다시 실행하세요')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    history = plain_path(data / 'CATALOG/TEAM_LAYOUT_HISTORY' / stamp)
    history.mkdir(parents=True, exist_ok=False)
    after = copy.deepcopy(before)
    after['files'] = updated
    after['refresh'] = {'id': stamp, 'parent_sha256': pointer_sha,
                        'receipt': str((history / 'receipt.json').relative_to(data))}
    # Save both complete registrations before the single atomic pointer update.
    build.atomic(history / 'before.json', before)
    build.atomic(history / 'after.json', after)
    build.atomic(history / 'receipt.json', {
        'schema_version': 'team-raw-refresh-v1', 'id': stamp,
        'before_sha256': pointer_sha, 'after_sha256': sha(history / 'after.json'),
        'events': events, 'original_bytes_modified': False,
        'note': 'Previously overwritten source bytes cannot be recovered from hashes.'})
    build.atomic(pointer, after)
    return {**summary, 'status': 'REFRESHED', 'history': str(history)}

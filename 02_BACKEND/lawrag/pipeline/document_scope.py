"""Hash-pinned document selection for the maintained document build command.

Original RAW/package paths remain immutable; unlisted files are never discovered.
This selection controls new builds, not an already activated serving generation.
"""
from __future__ import annotations

import json
from pathlib import Path

from semantic_runtime.contracts import sha
from semantic_runtime.document_roles import role_of_row
from . import genos_build as builder
from .genos_stages import plain_path


def local_path(data, value):
    rel = Path(value)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('scope paths must be relative to the logical data root')
    return plain_path(Path(data) / rel)


def configured(data):
    pointer = plain_path(Path(data) / 'CATALOG/BUILD_SCOPE.json')
    if not pointer.exists():
        return None
    value = json.loads(pointer.read_text())
    path = local_path(data, value['path'])
    if sha(path) != value['sha256']:
        raise ValueError('build scope pointer/hash mismatch')
    return path


def collect(data, scope_path, bindings=None, *, exclude_internal=False, emit=print):
    data, scope_path = plain_path(data), plain_path(scope_path)
    scope = json.loads(scope_path.read_text())
    if scope.get('schema_version') != 'document-build-scope-v1' or not scope.get('documents'):
        raise ValueError('invalid or empty document build scope')
    for receipt in scope.get('provenance', []):
        if sha(local_path(data, receipt['path'])) != receipt['sha256']:
            raise ValueError('scope provenance changed: ' + receipt['path'])
    rows, assets, ignored = [], {}, []
    seen_paths = set()
    names = set()
    for document in scope['documents']:
        name = document['name']
        if name in names or not document.get('files'):
            raise ValueError('duplicate/empty scoped document: ' + name)
        names.add(name)
        for item in document['files']:
            path = local_path(data, item['path'])
            if item['path'] in seen_paths:
                raise ValueError('duplicate scoped file: ' + item['path'])
            seen_paths.add(item['path'])
            if exclude_internal and item['source'] == 'internal':
                ignored.append({'path': str(path), 'reason': 'internal_excluded'})
                continue
            if sha(path) != item['sha256']:
                raise ValueError('scoped original changed: ' + item['path'])
            if path.suffix.lower() not in builder.EXTENSIONS:
                ignored.append({'path': str(path), 'reason': 'unsupported_scoped_attachment'})
                continue
            one = builder.inventory(data, item['source'], bindings, selected=[path])
            row = one['files'][0]
            assets.update(one['format_assets'])
            row.update(name=name if item['role'] == 'body' else item.get('title', path.stem),
                       kind=item['kind'], external_source=item['external_source'],
                       raw_role=item['role'], source_metadata={**document.get('source_metadata', {}),
                           'security_class': item.get('security_class', 'restricted'),
                           'export_allowed': item.get('export_allowed', False)},
                       scope_document=name, input_collection=scope['scope_id'])
            if item['role'] == 'body':
                row['representation_group'] = 'scope:' + name
            elif item.get('title'):
                row['source_title'] = item['title']
            row['document_role'] = role_of_row(row)
            rows.append(row)
    rows, alternatives = builder.select_representations(rows)
    ignored.extend(alternatives)
    unique = {}
    for row in rows:
        old = unique.get(row['document_id'])
        if old is None:
            unique[row['document_id']] = row
        elif (old['sha256'], old['source'], old['external_source'], old['kind'], old['raw_role']) != (
                row['sha256'], row['source'], row['external_source'], row['kind'], row['raw_role']):
            raise ValueError('conflicting authority for duplicate scoped content')
        else:
            from .document_representations import merge_context
            merge_context(old, row)
    rows = list(unique.values())
    binding = {'path': str(scope_path.relative_to(data)), 'sha256': sha(scope_path),
               'scope_id': scope['scope_id'], 'requested_documents': len(names)}
    plan = {'input_root': str(data), 'files': rows, 'ignored': ignored,
            'format_assets': assets, 'bindings_sha256': sha(bindings) if bindings else None,
            'input_contract': 'document-build-scope-v1', 'document_scope': binding,
            'representation_policy': builder.REPRESENTATION_POLICY, 'all_corpus': False}
    report = {'corpus_root': str(data), 'files': rows, 'errors': [], 'warnings': [],
              'excluded': ignored, 'sources': {}, 'manifest_hashes': {},
              'aliases': [], 'unique_documents': len(rows), 'ok': bool(rows),
              'document_scope': binding}
    emit(f'[SCOPE] {scope["scope_id"]}: 지정 {len(names)}종, 본문·첨부 처리 입력 {len(rows)}개')
    return plan, report

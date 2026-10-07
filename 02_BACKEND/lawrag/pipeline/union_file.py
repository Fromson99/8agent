"""Hash-bound identical RAW files selected by more than one team."""
from __future__ import annotations

import json
from pathlib import Path

from semantic_runtime.contracts import sha
from .genos_stages import plain_path
from . import genos_build as builder

VERSION = 'union-file-v1'
RELATIVE = Path('RAW/union_file/manifest.json')


def _path(data: Path, relative: str) -> Path:
    parts = Path(relative).parts
    if len(parts) < 5 or parts[0] != 'RAW' or parts[1] not in {'external', 'internal'} or '..' in parts:
        raise ValueError('invalid union path: ' + relative)
    return plain_path(data / relative)


def make(data: Path, layout: dict, names: set[str], scope_sha256: str) -> dict:
    """Describe exact copies already registered in both team branches."""
    data = plain_path(data)
    files = layout['files']
    entries = []
    for risk, item in sorted(files.items()):
        if item.get('team') != 'risk_team' or item.get('scope_document') not in names:
            continue
        financial = risk.replace('/risk_team/', '/financial_team/', 1)
        twin = files.get(financial)
        if twin is None:
            raise ValueError('shared document has no financial file: ' + risk)
        for field in ('sha256', 'source', 'role', 'security_class', 'export_allowed', 'scope_document'):
            if item.get(field) != twin.get(field):
                raise ValueError('shared file authority differs: ' + risk)
        for rel in (risk, financial):
            if sha(_path(data, rel)) != item['sha256']:
                raise ValueError('shared file hash mismatch: ' + rel)
        entries.append({'risk_path': risk, 'financial_path': financial,
                        'sha256': item['sha256'], 'document': item['scope_document'],
                        'source': item['source'], 'role': item['role'],
                        'security_class': item['security_class'],
                        'export_allowed': item['export_allowed']})
    if not entries:
        raise ValueError('no shared RAW files')
    return {'schema_version': VERSION, 'scope_sha256': scope_sha256,
            'entries': entries, 'selection_policy': 'process exact bytes once per run; keep both team paths'}


def publish(data: Path, layout: dict, names: set[str], scope_sha256: str) -> dict:
    manifest = make(data, layout, names, scope_sha256)
    target = plain_path(Path(data) / RELATIVE)
    if target.exists():
        if json.loads(target.read_text()) != manifest:
            raise ValueError('existing union_file manifest differs')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        builder.atomic(target, manifest)
    return {'path': str(RELATIVE), 'sha256': sha(target), 'entries': len(manifest['entries'])}


def load(data: Path, layout: dict) -> dict:
    data = plain_path(data)
    path = plain_path(data / RELATIVE)
    if not path.exists():
        if layout.get('financial_photo61_share') or layout.get('financial_shared_document_names'):
            raise ValueError('shared team registration requires RAW/union_file/manifest.json')
        return {'schema_version': VERSION, 'entries': []}
    value = json.loads(path.read_text())
    if value.get('schema_version') != VERSION or not isinstance(value.get('entries'), list):
        raise ValueError('invalid union_file manifest')
    seen = set()
    for entry in value['entries']:
        risk, financial = entry['risk_path'], entry['financial_path']
        if financial != risk.replace('/risk_team/', '/financial_team/', 1):
            raise ValueError('union team paths differ')
        if (risk, financial) in seen:
            raise ValueError('duplicate union pair')
        seen.add((risk, financial))
        for rel, team in ((risk, 'risk_team'), (financial, 'financial_team')):
            item = layout['files'].get(rel)
            if not item or item['team'] != team or item['sha256'] != entry['sha256']:
                raise ValueError('union file not bound to team registration: ' + rel)
            if (any(item.get(field) != entry[field] for field in
                    ('source', 'role', 'security_class', 'export_allowed'))
                    or item.get('scope_document') != entry['document']):
                raise ValueError('union file authority changed: ' + rel)
            if sha(_path(data, rel)) != entry['sha256']:
                raise ValueError('union original changed: ' + rel)
    return value

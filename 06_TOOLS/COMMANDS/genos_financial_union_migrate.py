#!/usr/bin/env python3
"""Derive a dual-team GENOS generation from a verified, complete source generation.

Only document location metadata changes. Structure, navigation and fulltext SQLite
bytes are copied unchanged; neither the source nor a serving pointer is modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime.contracts import digest, sha, write
from lawrag.pipeline import union_file
from lawrag.pipeline.term_serving_bundle import verify_assets

SCOPE_REL = 'CATALOG/SCOPES/photo-required-80-hwpx-20260917.json'
LAYOUT_REL = 'CATALOG/TEAM_LAYOUT.json'
SCOPE_SHA = 'aba1df17dbd2648203cf3ceb9719b784f398822bdaf7a163f566765b7cd3025f'


def location(name: str, rel: str, item: dict) -> dict:
    path = Path(rel.removeprefix('RAW/'))
    folders = list(path.parent.parts)
    display = folders if folders and folders[-1] == name else [*folders, name]
    return {'document_title': name, 'file_name': path.name,
            'folder_names': folders, 'folder_path': ' > '.join(folders),
            'display_name': ' > '.join(display), 'relative_path': str(path),
            'source_category': item['source'], 'team': item['team'],
            'original_path': item.get('original_path', rel)}


def scope_rows(data: Path) -> tuple[list[dict], dict, dict]:
    scope_path, layout_path = data / SCOPE_REL, data / LAYOUT_REL
    if sha(scope_path) != SCOPE_SHA:
        raise ValueError('photo 61 scope hash differs')
    scope = json.loads(scope_path.read_text())['documents'][:61]
    if len(scope) != 61 or scope[0]['name'] != '상법' or scope[-1]['name'] != '상장회사 표준정관(2025)':
        raise ValueError('photo 61 boundary differs')
    layout = json.loads(layout_path.read_text())
    if layout.get('financial_photo61_share', {}).get('scope_sha256') != SCOPE_SHA:
        raise ValueError('financial photo 61 admission is not bound to the selected scope')
    union = union_file.load(data, layout)
    shared = {entry['document'] for entry in union['entries']}
    names = {row['name'] for row in scope}
    if len(names) != 61:
        raise ValueError('photo 61 document names differ')
    if set(layout.get('financial_photo61_share', {}).get('document_names', [])) != names:
        raise ValueError('financial team admission differs')
    if shared != {name for name in names if any(
            item.get('team') == 'risk_team' and item.get('scope_document') == name
            for item in layout['files'].values())}:
        raise ValueError('shared document registry differs')
    if not shared or not shared <= names:
        raise ValueError('no valid shared documents')
    by_name = {}
    for rel, item in layout['files'].items():
        if item.get('role') == 'body' and item.get('scope_document') in names:
            if sha(data / rel) != item['sha256']:
                raise ValueError('RAW body hash differs: ' + rel)
            by_name.setdefault(item['scope_document'], []).append((rel, item))
    for row in scope:
        registered = by_name.get(row['name'], [])
        expected = {f['sha256'] for f in row['files'] if f['role'] == 'body'}
        if not registered or not expected.intersection({item['sha256'] for _, item in registered}):
            raise ValueError('financial RAW body missing: ' + row['name'])
        teams = {item['team'] for _, item in registered}
        if 'financial_team' not in teams or (row['name'] in shared and 'risk_team' not in teams):
            raise ValueError('team RAW body missing: ' + row['name'])
    return scope, layout, union


def source_matches(source: Path, scope: list[dict]) -> list[tuple[str, str, dict]]:
    db = sqlite3.connect('file:' + str(source / 'store.sqlite') + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    matches, missing = [], []
    try:
        for row in scope:
            ids = {f['sha256'][:16] for f in row['files'] if f['role'] == 'body'}
            found = []
            for did in ids:
                source_row = db.execute(
                    'SELECT name,json FROM document WHERE document_id=?', (did,)).fetchone()
                if source_row is None:
                    continue
                stored_name, raw = source_row
                payload = json.loads(raw)
                title = (payload.get('document_metadata') or {}).get('document_title')
                if title != row['name'] and str(stored_name).rsplit(' > ', 1)[-1] != row['name']:
                    continue
                found.append((did, payload))
            if not found:
                missing.append(row['name'])
                continue
            for did, payload in found:
                if not db.execute('SELECT 1 FROM source_block WHERE document_id=? LIMIT 1', (did,)).fetchone():
                    missing.append(row['name'] + ' (source_block 없음)')
                else:
                    matches.append((row['name'], did, payload))
    finally:
        db.close()
    if missing:
        raise ValueError('source generation lacks these photo 61 versions: ' + ', '.join(missing))
    return matches


def patch_store(path: Path, matches: list[tuple[str, str, dict]], layout: dict) -> list[str]:
    changed = []
    db = sqlite3.connect(path)
    try:
        for name, did, payload in matches:
            current = payload.get('document_metadata') or {}
            locations = [(rel, item) for rel, item in layout['files'].items()
                         if item.get('scope_document') == name and item.get('role') == 'body'
                         and item['sha256'].startswith(did)]
            locations.sort(key=lambda x: (x[1]['team'] != 'risk_team', x[0]))
            if not locations:
                raise ValueError('no exact RAW body for ' + name)
            desired = [location(name, rel, item) for rel, item in locations]
            existing = [current, *current.get('aliases', [])]
            keys = {(v.get('team'), v.get('relative_path')) for v in existing if isinstance(v, dict)}
            for loc in desired:
                if (loc['team'], loc['relative_path']) not in keys:
                    if not current:
                        current = loc
                    else:
                        current.setdefault('aliases', []).append(loc)
            payload['document_metadata'] = current
            db.execute('UPDATE document SET json=? WHERE document_id=?',
                       (json.dumps(payload, ensure_ascii=False, separators=(',', ':')), did))
            changed.append(did)
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('updated store integrity failed')
    finally:
        db.close()
    return changed


def verify_team_membership(path: Path, matches: list[tuple[str, str, dict]], shared: set[str]) -> None:
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    try:
        for name, did, _ in matches:
            raw = db.execute('SELECT json FROM document WHERE document_id=?', (did,)).fetchone()
            if raw is None:
                raise ValueError('migrated document missing: ' + name)
            meta = json.loads(raw[0]).get('document_metadata') or {}
            teams = {loc.get('team') for loc in [meta, *meta.get('aliases', [])] if isinstance(loc, dict)}
            if 'financial_team' not in teams or (name in shared and 'risk_team' not in teams):
                raise ValueError('migrated team selection incomplete: ' + name)
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--source-generation', type=Path, required=True)
    p.add_argument('--output-root', type=Path, required=True)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--package-name')
    a = p.parse_args(argv)
    source = a.source_generation.resolve(strict=True)
    output = a.output_root.resolve(strict=True)
    data = a.data_root.resolve(strict=True)
    if a.source_generation.is_symlink() or source.name != 'generation' or not output.is_dir():
        p.error('source must be a real generation directory; output root must exist')
    scope, layout, union = scope_rows(data)
    if not union['entries']:
        raise ValueError('no exact shared RAW file pairs')
    verify_assets(source)
    if not (source / 'fulltext/manifest.json').is_file():
        raise ValueError('source generation lacks fulltext; cannot reuse complete indexes')
    source_manifest_path = source / 'manifest.json'
    source_hash = sha(source_manifest_path)
    source_manifest = json.loads(source_manifest_path.read_text())
    matches = source_matches(source, scope)
    name = a.package_name or ('financial-union-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + source_hash[:8])
    if name in {'', '.', '..'} or '/' in name or '\\' in name:
        p.error('invalid package name')
    target = output / name
    if target.exists():
        p.error('output already exists')
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('source generation has a symlink: ' + str(path))
    stage = Path(tempfile.mkdtemp(prefix='.' + name + '-', dir=output))
    try:
        generation = stage / 'generation'
        shutil.copytree(source, generation)
        if sha(source_manifest_path) != source_hash:
            raise ValueError('source manifest changed during copy')
        unchanged = {rel: sha(generation / rel) for rel in ('navigation/navigation.sqlite', 'fulltext/fulltext.sqlite')}
        changed = patch_store(generation / 'store.sqlite', matches, layout)
        verify_team_membership(generation / 'store.sqlite', matches,
                               {entry['document'] for entry in union['entries']})
        manifest = json.loads((generation / 'manifest.json').read_text())
        manifest['generation_id'] = name
        manifest['store_sha256'] = sha(generation / 'store.sqlite')
        manifest['team_union_derivation'] = {
            'source_generation_manifest_sha256': source_hash,
            'source_generation_id': source_manifest['generation_id'],
            'scope_sha256': SCOPE_SHA,
            'team_layout_sha256': sha(data / LAYOUT_REL),
            'union_file_sha256': sha(data / union_file.RELATIVE),
            'document_ids': sorted(changed),
            'policy': 'same structure and index rows; additional financial_team location metadata'}
        nav_path = generation / manifest['navigation']['path'] / 'manifest.json'
        nav = json.loads(nav_path.read_text())
        nav['generation_id'] = name
        nav['source_store_sha256'] = manifest['store_sha256']
        nav['source_manifest_sha256'] = digest({k: v for k, v in manifest.items()
                                                if k not in {'navigation', 'fulltext', 'fulltext_derivation'}})
        write(nav_path, nav)
        manifest['navigation']['manifest_sha256'] = sha(nav_path)
        ft_path = generation / manifest['fulltext']['path'] / 'manifest.json'
        ft = json.loads(ft_path.read_text())
        ft['generation_id'] = name
        ft['source_store_sha256'] = manifest['store_sha256']
        write(ft_path, ft)
        manifest['fulltext']['manifest_sha256'] = sha(ft_path)
        write(generation / 'manifest.json', manifest)
        verify_assets(generation)
        if {rel: sha(generation / rel) for rel in unchanged} != unchanged:
            raise ValueError('index SQLite changed')
        if sha(source_manifest_path) != source_hash:
            raise ValueError('source changed during migration')
        receipt = {'schema_version': 'genos-financial-union-migration-v1',
                   'source_generation': str(source), 'source_manifest_sha256': source_hash,
                   'generation_manifest_sha256': sha(generation / 'manifest.json'),
                   'store_sha256': manifest['store_sha256'],
                   'unchanged_index_sqlite': unchanged,
                   'scope_sha256': SCOPE_SHA,
                   'team_layout_sha256': sha(data / LAYOUT_REL),
                   'union_file_sha256': sha(data / union_file.RELATIVE),
                   'photo_documents': 61,
                   'shared_documents': len({entry['document'] for entry in union['entries']}),
                   'shared_file_pairs': len(union['entries']),
                   'changed_document_ids': sorted(changed)}
        write(stage / 'migration-receipt.json', receipt)
        if target.exists():
            raise ValueError('target appeared during migration')
        os.rename(stage, target)
    except BaseException:
        shutil.rmtree(stage)
        raise
    print('GENOS_GENERATION=' + str(target / 'generation'))
    print('MIGRATION_RECEIPT=' + str(target / 'migration-receipt.json'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Paged source-only document browsing; no glossary, model or inferred provenance."""
import json
from types import SimpleNamespace
from .folder_navigation import bind_catalogue, normalized


def page_args(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('invalid pagination')


def documents(store, *, category='all', folder='', title_query='', offset=0, limit=100, projection=None):
    page_args(offset, limit)
    if category not in ('all', 'internal', 'external', 'unknown'):
        raise ValueError('invalid document category')
    if len(title_query) > 500 or len(folder) > 1000:
        raise ValueError('document filter too long')
    catalogue = bind_catalogue(SimpleNamespace(), store, projection).document_catalogue
    rows = [row for row in catalogue.values()
            if (category == 'all' or row['category'] == category)
            and (not title_query or normalized(title_query) in normalized(row['name']))
            and (not folder or row.get('navigation_folder') == folder
                 or (row.get('navigation_folder') or '').startswith(folder.rstrip('/')+'/'))]
    rows.sort(key=lambda row: (row['name'], row['id']))
    return {'generation_id': store.manifest['generation_id'], 'documents': rows[offset:offset+limit],
            'total': len(rows), 'offset': offset,
            'next_offset': offset+limit if offset+limit < len(rows) else None,
            'content_read': False, 'search_field': 'document.name',
            'unknown_category_count': sum(r['category'] == 'unknown' for r in catalogue.values())}


def document(store, document_id):
    row = store.db.execute('SELECT document_id,name,source_artifact_sha256 FROM document WHERE document_id=?',
                           (document_id,)).fetchone()
    if row is None:
        raise KeyError(document_id)
    return dict(row)


def outline(store, document_id, *, offset=0, limit=100):
    page_args(offset, limit)
    doc = document(store, document_id)
    nodes = []
    for row in store.db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=? ORDER BY CAST(unit_id AS INTEGER),unit_id', (document_id,)):
        raw = json.loads(row['json'])
        nodes.append({'id': row['unit_id'], 'parent_id': row['parent_id'],
                      **{k: raw.get(k) for k in ('family','surface','title','span','coordinate_key','coordinate_scope')}})
    return {**doc, 'generation_id': store.manifest['generation_id'], 'nodes': nodes[offset:offset+limit],
            'total': len(nodes), 'offset': offset, 'next_offset': offset+limit if offset+limit < len(nodes) else None,
            'content_read': False, 'authority': 'stored source_unit hierarchy'}


def read(store, document_id, *, unit_id=None, offset=0, limit=50):
    page_args(offset, limit)
    doc = document(store, document_id)
    predicate = 'document_id=?'
    args = [document_id]
    if unit_id is not None:
        row = store.db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',
                               (document_id, str(unit_id))).fetchone()
        if row is None:
            raise KeyError(unit_id)
        span = json.loads(row[0]).get('span')
        if not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span) or span[0] >= span[1]:
            raise ValueError('invalid stored unit span')
        predicate += ' AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<?'
        args += span
    total = store.db.execute('SELECT count(*) FROM source_block WHERE '+predicate, args).fetchone()[0]
    rows = [dict(row) for row in store.db.execute('SELECT * FROM source_block WHERE '+predicate+
            ' ORDER BY CAST(block_id AS INTEGER),block_id LIMIT ? OFFSET ?', [*args, limit, offset])]
    return {**doc, 'generation_id': store.manifest['generation_id'], 'source_store_sha256': store.manifest['store_sha256'],
            'unit_id': unit_id, 'blocks': rows, 'text': '\n'.join(row['text'] for row in rows),
            'total': total, 'offset': offset, 'next_offset': offset+limit if offset+limit < total else None,
            'complete': offset == 0 and len(rows) == total, 'content_read': True,
            'read_extent': 'stored unit blocks' if unit_id is not None else 'document blocks, paginated'}

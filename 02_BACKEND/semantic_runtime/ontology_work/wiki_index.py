"""Bounded metadata shards and stable cursors, not full-text corpus scans."""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent.errors import ContractError
from .wiki_contracts import scope_key

SHARDS = 16
SHARD_LIMIT = 1024


def catalog_id(scope):
    return 'ws-cat-' + scope_key(scope)


def empty(scope):
    return {'kind': 'WIKI_CATALOG', 'scope': deepcopy(scope), 'shards': {}, 'publications': {}}


def shard_for(bid):
    return digest(bid)[0]


def row(document, revision, work_hash):
    content = document['content']
    return {'bundle_id': document['bundle_id'], 'kind': document['kind'], 'revision': revision,
            'work_hash': work_hash, 'scope': document['scope'], 'state': document['state'],
            'title': content.get('title', content.get('text', ''))[:240],
            'anchors': sorted({digest(b['anchor']) for b in content.get('source_basis', [])}),
            'origin_refs': content.get('origin_refs', []),
            'semantic_hash': document.get('semantic_hash')}


def page(workspace, *, kind='ENTRY', query='', anchor=None, cursor=None, limit=32):
    if kind not in ('ENTRY', 'STATEMENT', 'VIEW') or not isinstance(query, str) or len(query) > 240 or type(limit) is not int or not 1 <= limit <= 128:
        raise ContractError('workspace index filter')
    catalog, pin = workspace.catalog()
    binding = digest([workspace.scope(workspace.document_ids), kind, query, anchor, workspace.actor])
    after = ''
    if cursor:
        if not isinstance(cursor, dict) or cursor.get('catalog_hash') != pin['work_hash'] or cursor.get('binding') != binding:
            raise ContractError('workspace index cursor is stale or outside scope')
        after = cursor['after']
        if not isinstance(after, str):
            raise ContractError('workspace index cursor')
    candidates = []
    for shard in sorted(catalog['shards']):
        values = workspace.store.get(catalog['shards'][shard])
        for bid, item in values['items'].items():
            if bid <= after or item['kind'] != kind:
                continue
            # Do not return titles, counts, source metadata or text before ACL.
            try:
                workspace.check_scope(item)
            except ContractError:
                continue
            if query.casefold() not in item['title'].casefold() or anchor and digest(anchor) not in item['anchors']:
                continue
            candidates.append(item)
    candidates.sort(key=lambda r: r['bundle_id'])
    selected = candidates[:limit]
    return {'items': deepcopy(selected), 'catalog_hash': pin['work_hash'],
            'cursor': {'catalog_hash': pin['work_hash'], 'binding': binding, 'after': selected[-1]['bundle_id']} if len(candidates) > limit else None,
            'search_scope': 'WORKSPACE_METADATA_SHARDS', 'exhaustive_legal_search': False}

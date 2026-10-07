"""Law/article directories over the explicitly bound own-block fulltext index."""
from collections import defaultdict
from ..contracts import digest
from ..fulltext import question_terms
from .errors import ContractError

CONTRACT = 'law-candidate-navigation-v3'
DEFAULT_POLICY = {'mode': 'legacy', 'law_page_size': 12, 'article_page_size': 4,
                  'hit_page_size': 8, 'search_rounds': 8, 'allow_unresolved_completion': True, 'investigation_control': False,
                  'assessment_reentry_limit': 2}


def policy(session):
    return {**DEFAULT_POLICY, **session.profile.get('candidate_navigation', {})}


def validate_policy(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULT_POLICY):
        raise ContractError('unknown candidate navigation setting')
    result = {**DEFAULT_POLICY, **value}
    if result['mode'] not in ('legacy', 'law-first-v1'):
        raise ContractError('unknown candidate navigation mode')
    for key in ('law_page_size', 'article_page_size', 'hit_page_size', 'search_rounds'):
        if type(result[key]) is not int or result[key] < 1:
            raise ContractError('invalid candidate navigation page/budget: '+key)
    if type(result['investigation_control']) is not bool or type(result['assessment_reentry_limit']) is not int or result['assessment_reentry_limit'] < 0:
        raise ContractError('invalid investigation control setting')
    if type(result['allow_unresolved_completion']) is not bool:
        raise ContractError('allow_unresolved_completion must be bool')
    return result


def enabled(session):
    return policy(session)['mode'] == 'law-first-v1' and getattr(session.matcher, 'unit_fulltext', None) is not None


def allowed(session):
    return {sid for sid, row in session.tools.sources.items() if row['document_id'] in session.scope}


def index(session):
    return session.matcher.unit_fulltext, session.matcher.unit_fulltext_db


def token(session, kind, identity):
    return kind+digest({'contract': CONTRACT, 'question': session.context.request['question'],
        'scope': sorted(session.scope), 'index': session.matcher.unit_fulltext.manifest['index_sha256'],
        'identity': identity})[:28]


def hit_shape(hit, terms):
    return {k: v for k, v in hit.items() if k not in ('text', 'score', 'query_terms')} | {
        'match_paths': [{'terms': list(terms)}]}


def discover(recall):
    from .source_recall import focused_queries
    from .structure_query import resolve
    s = recall.s; idx, db = index(s)
    plan = getattr(s, 'recall_query_plan', {'queries': [], 'law_names': []})
    queries = getattr(s, 'law_search_queries', None) or focused_queries(s.context.request['question'], plan)
    terms = sorted({term for query in queries for term in question_terms(query)})
    page = idx.law_groups_page(db, terms, allowed(s), limit=policy(s)['law_page_size'])
    structural = resolve(s.context.request['question'], s.matcher, s.scope)
    direct = structural['source_ids'] if structural['status'] == 'MATCH' else []
    if set(direct)-allowed(s):
        raise ContractError('structural originals outside request scope')
    # Exact positions are entry hints; the full corpus directory remains present.
    hits = []; selected = list(direct)
    for law in page['items']:
        articles = idx.article_groups_page(db, terms, law['document_id'], allowed(s), limit=1)
        for article in articles['items']:
            sid = article['source_id']; selected.append(sid)
            for h in idx.hit_page(db, terms, sid, allowed(s), limit=1)['items']:
                hits.append(hit_shape(h, terms))
    for sid in direct:
        source = s.tools.sources[sid]
        pairs = [p for p in structural.get('pairs', []) if p.get('document_id') == source['document_id']
                 and sid in s.matcher._unit_sources(source['document_id'], p['unit_id'])]
        from .unit_reading import blocks
        for requested in dict.fromkeys(str(p['unit_id']) for p in pairs) if pairs else [str(source['unit_id'])]:
            uid=requested
            if not blocks(s,source['document_id'],uid,'exact'):
                # An explicit empty container is still an entry: preview its first
                # actual child body and retain the requested subtree READ scope.
                subtree=set(blocks(s,source['document_id'],uid,'subtree'))
                candidates=[s.store.source(source['document_id'],b['block_id']) for b in source['blocks'] if str(b['block_id']) in subtree]
                uid=next((str(b['unit_id']) for b in candidates if b['text']),None)
                if uid is None:continue
            key=sid+'#unit:'+uid
            existing=next((h for h in hits if h['key']==key),None)
            if existing:
                existing.update(entry_reason='exact_structure',requested_unit_id=requested)
            else:
                hits.append({'key':key, 'source_id':sid,'document_id':source['document_id'],
                    'unit_id':uid,'requested_unit_id':requested,'article_unit_id':source['unit_id'],
                    'document_name':source['document_name'],'heading':source.get('heading',''),
                    'match_paths':[],'entry_reason':'exact_structure'})
    selected = list(dict.fromkeys(selected))
    catalogue = {'contract': CONTRACT, 'terms': terms, 'queries': queries, 'law_page': page,
        'query_fingerprint': digest({'terms': terms, 'scope': sorted(s.scope), 'index': idx.manifest['index_sha256']}),
        'index_sha256': idx.manifest['index_sha256'], 'search_policy': 'best-own-block-match-v1'}
    s.repo.event('LAW_FULLTEXT_DIRECTORY', {'queries': queries, 'laws': [{**law,'name':s.matcher.documents[law['document_id']]} for law in page['items']],
        'total_laws': page['total'], 'has_more_laws': page['next_cursor'] is not None,
        'query_fingerprint': catalogue['query_fingerprint']})
    return selected, {'discovery_mode': 'fulltext', 'law_navigation': catalogue,
        'unit_hits': hits, 'unit_index_sha256': idx.manifest['index_sha256'],
        'selected_for_read': selected, 'discovered': selected, 'routes': {}, 'queries': [],
        'structure_query': structural, 'parent_selections_preserved': True}


def prepare(recall):
    from .unit_reading import acquire_batch, read_state
    s = recall.s; selected, discovery = recall.discover()
    state = read_state(s)
    hits = discovery['unit_hits']
    reads = acquire_batch(s, hits, state)
    eligible = list(dict.fromkeys(r['source_id'] for r in reads if r['complete']))
    return {**discovery, 'unit_read_contract': 'unit-read-v1', 'unit_reads': reads,
        'pending_unit_hits': [], 'read_state': state, 'actions': [a for r in reads for a in r['actions']],
        'selected_for_read': selected, 'selection_complete': eligible, 'prepared_complete': eligible,
        'read_complete': [], 'read_partial': eligible, 'source_chars': state['chars'],
        'selection_evidence_ids': list(dict.fromkeys(e for r in reads for e in r['evidence_ids'])),
        'packets': [], 'limits': [], 'actual_model_presented': []}


def parent_offer(session, hit):
    from .unit_reading import offers
    choices = offers(session, hit)
    uid = hit['unit_id']; root = hit['article_unit_id']
    unit = session.matcher.units.get((hit['document_id'], str(uid)))
    parent = unit.get('parent') if unit and str(uid) != str(root) else root
    if hit.get('requested_unit_id'):parent=hit['requested_unit_id']
    chosen = next((o for o in choices if o['unit_id'] == parent and o['extent'] == 'subtree'), None)
    if chosen is None:
        chosen = next((o for o in choices if str(o['unit_id']) == str(parent) and o['extent'] == 'subtree'), None)
    return chosen or next(o for o in choices if o['extent'] == 'exact')


def siblings(session, hit, offer):
    result = []
    for (did, uid), unit in session.matcher.units.items():
        if did == hit['document_id'] and str(unit.get('parent')) == str(offer['unit_id']):
            result.append({'unit_id': uid, 'label': unit.get('surface') or unit.get('title') or uid,
                           'order': unit.get('span', [0])[0]})
    return sorted(result, key=lambda r: (r['order'], str(r['unit_id'])))

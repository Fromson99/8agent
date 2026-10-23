"""Law/article directories over the explicitly bound own-block fulltext index."""
from collections import defaultdict
from ..contracts import digest
from ..fulltext import question_terms
from .errors import ContractError
from .. import query_latency as latency
from ..runtime_cache import CACHE

from . import query_scope as qs
CONTRACT = 'law-candidate-navigation-v3'
DEFAULT_POLICY = {'mode': 'legacy', 'law_page_size': 12, 'article_page_size': 4,
                  'hit_page_size': 8, 'search_rounds': 8, 'allow_unresolved_completion': True, 'investigation_control': False,
                  'assessment_reentry_limit': 2, 'completion_contract': False, 'structure_first': False, 'batch_selected_pages': False, 'selectable_search': False, 'compact_input': False, 'completion_policy_version': 'investigation-completion-v4', 'length_recovery_max_tokens': 0, 'definition_entry': False, 'answer_first': False, 'selected_connection_scope': False, 'answer_progress_control': False, 'delegation_frontier': False, 'bounded_judgment_notes': False, 'definition_context': False, 'small_connection_context': False, 'read_judgment': False}


def policy(session):
    return {**DEFAULT_POLICY, **session.profile.get('candidate_navigation', {})}


def validate_policy(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULT_POLICY):
        raise ContractError('unknown candidate navigation setting')
    result = {**DEFAULT_POLICY, **value}
    length_limit = result['length_recovery_max_tokens']
    if type(length_limit) is not int or not 0 <= length_limit <= 80000:
        raise ContractError('invalid navigation length recovery ceiling')
    if result['mode'] not in ('legacy', 'law-first-v1'):
        raise ContractError('unknown candidate navigation mode')
    for key in ('law_page_size', 'article_page_size', 'hit_page_size', 'search_rounds'):
        if type(result[key]) is not int or result[key] < 1:
            raise ContractError('invalid candidate navigation page/budget: '+key)
    if type(result['investigation_control']) is not bool or type(result['assessment_reentry_limit']) is not int or result['assessment_reentry_limit'] < 0:
        raise ContractError('invalid investigation control setting')
    if type(result['completion_contract']) is not bool or (result['completion_contract'] and not result['investigation_control']):
        raise ContractError('completion contract requires investigation control')
    if type(result['allow_unresolved_completion']) is not bool:
        raise ContractError('allow_unresolved_completion must be bool')
    if any(type(result[k]) is not bool for k in ('structure_first','batch_selected_pages','selectable_search','compact_input','definition_entry','answer_first','selected_connection_scope','answer_progress_control','delegation_frontier','bounded_judgment_notes','definition_context','small_connection_context','read_judgment')):
        raise ContractError('invalid structure/read policy')
    if result['read_judgment'] and (not result['compact_input'] or not result['investigation_control']
            or result['mode'] != 'law-first-v1' or result['answer_first'] or result['answer_progress_control']
            or result['completion_policy_version'] == 'investigation-completion-v4'):
        raise ContractError('read judgment requires modern compact navigation without automatic answer-progress handoff')
    if result['structure_first'] and result['mode'] != 'law-first-v1':
        raise ContractError('structure-first requires law navigation')
    if result['selectable_search'] and not result['structure_first']:raise ContractError('selectable search requires scoped navigation support')
    if result['selected_connection_scope'] and (not result['compact_input'] or result['answer_first']):
        raise ContractError('selected connection scope requires navigation judgment before assessment')
    if result['small_connection_context'] and not result['selected_connection_scope']:raise ContractError('small connection context requires selected connection scope')
    if result['answer_progress_control'] and (not result['compact_input'] or not result['investigation_control']):raise ContractError('answer progress requires compact investigation control')
    if result['definition_context'] and (not result['investigation_control'] or not result['delegation_frontier']):raise ContractError('definition context requires controlled verified delegation frontier')
    if result['answer_first'] and not result['compact_input']:raise ContractError('answer-first requires compact completion input')
    if result['compact_input'] and not result['completion_contract']:raise ContractError('compact input requires completion contract')
    if result['completion_policy_version'] not in ('investigation-completion-v4','investigation-completion-v5','investigation-completion-v6','investigation-completion-v7','investigation-completion-v8'):
        raise ContractError('unknown completion policy version')
    if result['completion_policy_version'] in ('investigation-completion-v5','investigation-completion-v6','investigation-completion-v7','investigation-completion-v8') and not result['completion_contract']:
        raise ContractError('v5 requires completion contract')
    return result


def enabled(session):
    return policy(session)['mode'] == 'law-first-v1' and getattr(session.matcher, 'unit_fulltext', None) is not None


def allowed(session):
    sources = session.tools.sources
    from ..term_index import SourceMap
    verify = getattr(sources, 'cache_binding', None) if isinstance(sources, SourceMap) else None
    if verify: verify()
    key = (id(sources), frozenset(session.scope))
    cache = getattr(session, '_law_allowed_sources', None)
    with latency.span('law.allowed_scope', cache_hit=cache is not None and cache[0] == key) as metrics:
        if cache is None or cache[0] != key:
            with_scope = getattr(sources, 'ids_for_documents', None)
            def build():
                ids = (with_scope(session.scope) if with_scope else
                       frozenset(sid for sid, row in sources.items() if row['document_id'] in session.scope))
                if verify: verify()
                return ids
            if verify:
                binding = ('scope', verify(), frozenset(session.scope))
                remaining = getattr(getattr(session, 'context', None), 'remaining', None)
                ids, stats = CACHE.get_or_build(binding, build, kind='scope', remaining=remaining)
                verify(); metrics.update(stats)
            else:
                ids = build()
            cache = session._law_allowed_sources = (key, ids)
        metrics['allowed_count'] = len(cache[1])
        return cache[1]


def index(session):
    db = session.matcher.unit_fulltext_db
    db._cache_remaining = getattr(getattr(session, 'context', None), 'remaining', None)
    return session.matcher.unit_fulltext, db


def token(session, kind, identity):
    return kind+digest({'contract': CONTRACT, 'question': session.context.request['question'],
        'scope': sorted(session.scope), **({'direct_scope':qs.active(session)} if qs.active(session) else {}), 'index': session.matcher.unit_fulltext.manifest['index_sha256'],
        'identity': identity})[:28]


def hit_shape(hit, terms):
    return {k: v for k, v in hit.items() if k not in ('text', 'score', 'query_terms')} | {
        'match_paths': [{'terms': list(terms)}]}


def structure_hit(session, source_id, unit_id):
    """Preview a real owned block, retaining the exact requested subtree."""
    from .unit_relations import hit_for
    from .unit_reading import blocks
    source = session.tools.sources[source_id]
    requested = str(unit_id)
    uid = requested
    if not blocks(session, source['document_id'], uid, 'exact'):
        subtree = set(blocks(session, source['document_id'], uid, 'subtree'))
        candidates = [session.store.source(source['document_id'], b['block_id'])
                      for b in source['blocks'] if str(b['block_id']) in subtree]
        uid = next((str(b['unit_id']) for b in candidates
                    if str(b['unit_id']) != requested and b['text']), None)
        if uid is None:
            raise ContractError('structural location has no bound original body')
    return {**hit_for(session, source_id, uid), 'entry_reason': 'exact_structure',
            'requested_unit_id': requested}


def search_queries(session, plan):
    """Preserve accepted query intent; raw text is only a legacy fallback."""
    explicit = getattr(session, 'law_search_queries', None)
    planned = plan.get('queries') if getattr(session, 'entry_search', None) else None
    selected = explicit or planned
    if selected:
        queries = list(dict.fromkeys(q.strip() for q in selected if isinstance(q, str) and q.strip()))
        if queries:
            return queries, ('selected_search_queries' if explicit else 'accepted_request_queries')
    from .source_recall import focused_queries
    return focused_queries(session.context.request['question'], plan), 'request_query_fallback'


@latency.timed('law.recall.discover', pressure=True)
def discover(recall):
    from .comparison_research import recall as task_recall
    requested=task_recall(recall)
    if requested is not None:return requested
    path=getattr(recall.s,'core_evidence_route',None) if not qs.active(recall.s) else None
    if path and not (getattr(recall.s,'law_search_queries',None) or getattr(recall.s,'force_fulltext_recall',False)):
        from .core_evidence_route import direct_discovery
        from .corrected_memory import MemoryError
        try:return direct_discovery(recall,path)
        except (MemoryError,KeyError,ValueError):
            recall.s.repo.event('CORE_EVIDENCE_ROUTE_FALLBACK',{'reason':'current source coordinates or spans changed'})
            recall.s.core_evidence_route=None
    from .source_recall import focused_queries
    from .structure_query import resolve
    s = recall.s; idx, db = index(s)
    plan = getattr(s, 'recall_query_plan', {'queries': [], 'law_names': []})
    with latency.span('law.recall.tokenize') as metrics:
        queries, query_origin = search_queries(s, plan)
        route_queries = list(queries)
        terms = sorted({term for query in queries for term in question_terms(query)})
        metrics.update(query_count=len(queries), term_count=len(terms))
    entry=getattr(s,'entry_search',None) or {}
    body_selected=policy(s)['selectable_search'] and (entry.get('mode')=='FULLTEXT' or getattr(s,'law_search_queries',None))
    if policy(s)['structure_first'] and not body_selected:
        return structured_discovery(s, queries, terms, route_queries=route_queries, query_origin=query_origin)
    page = idx.law_groups_page(db, terms, qs.search_sources(s), limit=policy(s)['law_page_size'], **qs.fulltext(s))
    with latency.span('law.recall.structure'):
        query_routes = [qs.filter_route(s,resolve(query, s.matcher, qs.documents(s))) for query in route_queries]
        structural = dict(query_routes[0])
        matches = [r for r in [structural, *query_routes] if r['status'] == 'MATCH']
        if matches:
            structural = {**structural, 'status': 'MATCH',
                'pairs': list({(p['document_id'], str(p['unit_id']), p.get('source_id'), digest(p.get('source_partition'))): p for r in matches for p in r['pairs']}.values()),
                'source_ids': list(dict.fromkeys(sid for r in matches for sid in r['source_ids']))}
        structural['query_routes'] = query_routes
    direct = structural['source_ids'] if structural['status'] == 'MATCH' else []
    if set(direct)-allowed(s):
        raise ContractError('structural originals outside request scope')
    # Exact positions are entry hints; the full corpus directory remains present.
    hits = []; selected = list(direct)
    for law in page['items']:
        articles = idx.article_groups_page(db, terms, law['document_id'], qs.search_sources(s), limit=1, **qs.fulltext(s))
        for article in articles['items']:
            sid = article['source_id']; selected.append(sid)
            for h in idx.hit_page(db, terms, sid, qs.search_sources(s), limit=1, **qs.fulltext(s))['items']:
                hits.append(hit_shape(h, terms))
    for sid in direct:
        source = s.tools.sources[sid]
        partitions=[p for p in structural['pairs'] if p.get('source_partition') is not None and p.get('source_id')==sid]
        if partitions:
            from . import tool_availability, structure_query
            hits=[h for h in hits if h['source_id']!=sid]
            for pair in partitions:
                read_plan,unavailable=tool_availability.article_plan(s,structure_query.read_identity(pair))
                if unavailable:raise ContractError('exact structural partition unavailable: '+unavailable)
                hits.append(read_plan[0])
            continue
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
    catalogue = {'contract': CONTRACT, 'terms': terms, 'queries': queries, 'route_queries': route_queries, 'query_origin': query_origin, 'law_page': page,
        'query_fingerprint': digest({'terms': terms, 'route_queries': route_queries, 'query_origin': query_origin, 'scope': sorted(s.scope), 'index': idx.manifest['index_sha256']}),
        'index_sha256': idx.manifest['index_sha256'], 'search_policy': 'best-own-block-match-v1'}
    s.repo.event('LAW_FULLTEXT_DIRECTORY', {'queries': queries, 'laws': [{**law,'name':s.matcher.documents[law['document_id']]} for law in page['items']],
        'total_laws': page['total'], 'has_more_laws': page['next_cursor'] is not None,
        'query_fingerprint': catalogue['query_fingerprint']})
    return selected, {'discovery_mode': 'fulltext', 'law_navigation': catalogue,
        'unit_hits': hits, 'unit_index_sha256': idx.manifest['index_sha256'],
        'selected_for_read': selected, 'discovered': selected, 'routes': {}, 'queries': [],
        'structure_query': structural, 'parent_selections_preserved': True}


@latency.timed('law.recall.prepare', pressure=True)
def prepare(recall):
    from .unit_reading import acquire_batch, read_state
    s = recall.s; selected, discovery = recall.discover()
    state = read_state(s)
    hits = discovery['unit_hits']
    with latency.span('law.recall.acquire_originals', unit_count=len(hits)):
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
    units=session.matcher.units
    rows=units.for_document(hit['document_id']) if hasattr(units,'for_document') else units.items()
    for (did, uid), unit in rows:
        if did == hit['document_id'] and str(unit.get('parent')) == str(offer['unit_id']):
            result.append({'unit_id': uid, 'label': unit.get('surface') or unit.get('title') or uid,
                           'order': unit.get('span', [0])[0]})
    return sorted(result, key=lambda r: (r['order'], str(r['unit_id'])))


def structured_discovery(s, queries, terms, *, route_queries=None, query_origin='legacy_request_expansion'):
    """Titles/coordinates locate sources; never search original bodies here."""
    from . import structure_query as sq
    route_queries = route_queries if route_queries is not None else list(dict.fromkeys([s.context.request['question'], *queries]))
    selected_sets = (qs.active(s) or {}).get('selections', [])
    if selected_sets:
        from . import structure_selection as ss
        routes = [ss.route(selected_sets, s.matcher, qs.documents(s))]
        first = selected_sets[0]
        directory = qs.catalogue(s, document_id=first['document_id'],
            structure_filter={'selection': first['selection']}, limit=policy(s)['law_page_size'])
    else:
        routes = [qs.filter_route(s,sq.resolve(q, s.matcher, qs.documents(s))) for q in route_queries]
        directory = qs.catalogue(s, queries=route_queries,
            limit=policy(s)['law_page_size'])
    pairs = {(p['document_id'], str(p['unit_id']), p.get('source_id'), digest(p.get('source_partition'))): p
             for r in routes if r['status']=='MATCH' for p in r['pairs']}
    hits=[]
    for pair in pairs.values():
        did,uid=pair['document_id'],str(pair['unit_id'])
        ids=([pair['source_id']] if pair.get('source_id') else s.matcher._unit_sources(did,uid))
        for sid in ids:
            if sid not in allowed(s):raise ContractError('structured source outside request scope')
            if pair.get('source_partition') is not None:
                from . import tool_availability
                read_plan,unavailable=tool_availability.article_plan(s,sq.read_identity(pair))
                if unavailable:raise ContractError('exact structural partition unavailable: '+unavailable)
                hits.append(read_plan[0])
            else:hits.append(structure_hit(s,sid,uid))
    hits=list({(h['key'],h.get('requested_unit_id'),digest(h.get('source_partition'))):h for h in hits}.values())
    docs=list(dict.fromkeys([r['document_id'] for r in directory['items']]+[p['document_id'] for p in pairs.values()]))
    if qs.active(s):docs=list(dict.fromkeys([*docs,*qs.documents(s)]))
    page={'items':[{'document_id':did,'article_count':None,'unit_count':None} for did in docs],
        'total':len(docs),'next_cursor':None}
    idx,_=index(s)
    catalogue={'contract':CONTRACT,'terms':terms,'queries':queries,'route_queries':route_queries,'query_origin':query_origin,'law_page':page,
        'query_fingerprint':digest({'terms':terms,'queries':queries,'route_queries':route_queries,'query_origin':query_origin,'scope':sorted(s.scope),
            'index':idx.manifest['index_sha256'],'search_policy':'structure-first-scoped-v1'}),
        'index_sha256':idx.manifest['index_sha256'],'search_policy':'structure-first-scoped-v1'}
    selected=list(dict.fromkeys(h['source_id'] for h in hits))
    s.repo.event('LAW_STRUCTURE_DIRECTORY',directory)
    return selected,{'discovery_mode':'structure','law_navigation':catalogue,'structure_catalogue':directory,
        'unit_hits':hits,'unit_index_sha256':idx.manifest['index_sha256'],'selected_for_read':selected,
        'discovered':selected,'routes':{},'queries':[], 'structure_query':{'status':'MATCH' if pairs else 'MISS',
        'pairs':list(pairs.values()),'source_ids':selected,'query_routes':routes},'parent_selections_preserved':True}


def fulltext_scope_keys(session, document_id, unit_id=None):
    """Resolve selected metadata scope to indexed units before lexical ranking."""
    import json
    from .structure_query import document_tree
    if document_id not in session.scope:raise ContractError('fulltext document outside request scope')
    tree=document_tree(session.matcher,document_id)
    if unit_id is None:units=set(tree['nodes'])
    else:
        unit_id=str(unit_id)
        if unit_id not in tree['nodes']:raise ContractError('fulltext subtree is not stored')
        units=set();todo=[unit_id]
        while todo:
            uid=todo.pop()
            if uid in units:continue
            units.add(uid);todo.extend(tree['children'].get(uid,[]))
    if qs.active(session):units={uid for uid in units if qs.direct(session,document_id,uid)}
    idx,db=index(session);idx.check_unchanged()
    rows=db.execute("SELECT key,source_id FROM unit WHERE document_id=? AND json_extract(json,'$.unit_id') IN (SELECT value FROM json_each(?))",
                    (document_id,json.dumps(sorted(units)))).fetchall()
    permitted=allowed(session)
    return frozenset(key for key,sid in rows if sid in permitted)


def scoped_read_unit(session, source_id, selected_unit):
    """Clip a broad structural selection to each article's original boundary."""
    if selected_unit is None:return None
    source=session.tools.sources[source_id];uid=str(source['unit_id']);selected=str(selected_unit);seen=set()
    while uid not in seen:
        if uid==selected:return str(source['unit_id'])
        seen.add(uid);node=session.matcher.units.get((source['document_id'],uid))
        if not node or node.get('parent') is None:break
        uid=str(node['parent'])
    return selected


def answer_first(profile):
    """Ordinary user RAG; workflow research retains its parent's return contract."""
    from .workflow_execution import task_context
    return bool(profile.get('candidate_navigation', {}).get('answer_first')) and not task_context()

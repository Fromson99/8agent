"""Derive direct source entries from the current adopted route, never its answer.

Units use the existing immutable shortcut/wiki relations. Their mutable head is
validated against the live goal and route on every read; an interrupted correction
cannot expose an older successful turn. Source text stays in the existing source
authority, while this record stores only coordinates and span fingerprints.
"""
import json
from .corrected_memory import MemoryError, digest, encoded

CONTRACT = 'core-evidence-route-v1'
PREFIX = 'unit:core:'


def enabled(cases):
    return bool(hasattr(cases, 'shortcut') and cases.flags.get('core_evidence_route'))


def conditions(state):
    return {'task': ' '.join(state['task'].split()),
            'facts': sorted(state.get('facts', []), key=encoded),
            'source_category': state.get('source_category', 'all')}


def source_binding(binding):
    return {key: binding.get(key) for key in ('generation', 'store_sha256', 'unit_index_sha256')}


def current(repo, value, principal):
    path = value.get('core_evidence_route')
    if not path:
        return
    if path.get('contract') == 'curated-core-evidence-route-v1':
        from lawrag.pipeline.shortcut_package import current as curated_current
        return curated_current(repo, value, principal)
    if path.get('contract') != CONTRACT:
        raise MemoryError('unsupported core evidence route')
    goal = repo.db.execute('SELECT * FROM goal WHERE id=?', (path['goal_id'],)).fetchone()
    if not goal or goal['status'] != 'READY' or goal['revision'] != path['goal_revision']:
        raise MemoryError('core evidence route superseded or pending')
    owner = repo.db.execute('SELECT owner,team FROM session WHERE id=?', (goal['session'],)).fetchone()
    if not owner or tuple(owner) != (principal['user_id'], principal['team_id']):
        raise MemoryError('core evidence route owner changed')
    state = json.loads(goal['state'])
    if digest(state) != path['state_hash']:
        raise MemoryError('core evidence route conditions changed')
    route = repo.db.execute("SELECT * FROM route WHERE goal=? AND revision=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",
                            (goal['id'], goal['revision'])).fetchone()
    if not route or route['id'] != path['route_id'] or route['hash'] != path['route_hash']:
        raise MemoryError('core evidence route is no longer the accepted head')
    accepted = json.loads(route['payload'])
    if digest(accepted) != route['hash']:
        raise MemoryError('core evidence route authority corrupt')
    selection = repo.db.execute('SELECT payload,hash FROM node WHERE id=?', (accepted['nodes']['SELECT'],)).fetchone()
    if not selection or selection['hash'] != path['selection_hash'] or digest(json.loads(selection['payload'])) != selection['hash']:
        raise MemoryError('core evidence route selection changed')


def finalize(cases, result, principal):
    """Call only after native publication/export succeeded, including retry recovery."""
    if not enabled(cases) or not principal.get('authenticated') or not result.get('goal_id'):
        return None
    repo = cases.shortcut
    gid = result['goal_id']
    goal = cases.db.execute('SELECT * FROM goal WHERE id=?', (gid,)).fetchone()
    route = cases.route(gid)
    if not goal or goal['status'] != 'READY' or not route or goal['revision'] != result['revision']:
        raise MemoryError('cannot finalize a pending or stale core evidence route')
    parts = cases.parts(gid)
    selection = parts['SELECT']['payload']
    adopted = set(selection['final_ids'])
    originals = selection.get('selected_originals', parts['READ']['payload']['originals'])
    originals = [s for s in originals if s['source_id'] in adopted]
    if not originals:
        return None
    state = json.loads(goal['state'])
    binding = source_binding(cases.executor.binding)
    unit = PREFIX + gid
    old = repo.db.execute('SELECT k.payload,u.head FROM sw_unit u JOIN sw_knowledge k ON k.unit=u.id AND k.revision=u.head WHERE u.id=?', (unit,)).fetchone()
    if old and json.loads(old['payload']).get('core_evidence_route', {}).get('route_id') == route['id']:
        value = json.loads(old['payload'])
        current(repo, value, principal)
        return {'unit_id': unit, 'revision': old['head'], 'route_id': route['id']}
    case = repo.investigation(cases.active_case, principal, cases.original_session)
    targets = []
    sources = []
    for original in originals:
        did = original['document_id']
        if did not in principal['document_ids'] or did not in state['document_ids']:
            raise MemoryError('core evidence route escaped current document scope')
        spans = original.get('adopted_spans')
        if spans is None:
            wanted = set(original.get('evidence_ids', []))
            evidence = selection.get('selected_evidence', parts['READ']['payload']['evidence'])
            spans = [p for e in evidence if e['source_id'] == original['source_id'] and (not wanted or e['evidence_id'] in wanted) for p in e['spans']]
        if not spans:
            raise MemoryError('core source has no adopted original spans')
        witnesses = []
        unit_ids = []
        for span in spans:
            raw = cases.executor.pipeline.store.source(did, str(span['block_id']))
            lo, hi = span['start_cp'], span['end_cp']
            if not 0 <= lo < hi <= len(raw['text']) or raw['text'][lo:hi] != span['text']:
                raise MemoryError('core source span no longer matches original')
            uid = str(raw['unit_id'])
            if uid not in unit_ids:
                unit_ids.append(uid)
            witnesses.append({'block_id': str(span['block_id']), 'start_cp': lo, 'end_cp': hi,
                              'text_hash': digest(span['text']), 'unit_id': uid})
        ref = repo.source(principal, {'document_id': did, 'document_name': original.get('document_name', did),
            'generation': binding['generation'], 'coordinate': str(original['unit_id']),
            'text': original['text'], 'version': binding['store_sha256']})
        source = dict(repo.db.execute('SELECT * FROM sw_source WHERE id=?', (ref,)).fetchone())
        sources.append(source)
        targets.append({'document_id': did, 'article_unit_id': str(original['unit_id']),
            'read_unit_ids': unit_ids, 'spans': witnesses, 'source_ref': ref,
            'source_id': original['source_id'], 'reason': 'current SELECT-adopted source'})
    path = {'contract': CONTRACT, 'goal_id': gid, 'goal_revision': goal['revision'],
        'route_id': route['id'], 'route_hash': route['hash'], 'selection_hash': digest(selection),
        'state_hash': digest(state), 'conditions': conditions(state), 'source_binding': binding,
        'targets': targets, 'public_only': bool(case['public_only']),
        'origin': {'investigation_id': case['id'], 'investigation_revision': case['revision'],
                   'selection_ref': route['payload']['judgment_refs']['SELECT']},
        'execution': 'DIRECT_SOURCE_ENTRIES_THEN_CURRENT_SELECTION_AND_ASSESSMENT',
        'legal_claim_reuse': False, 'discarded_exploration_replayed': False}
    value = {'id': unit, 'topic': state['task'], 'question': state['task'], 'completeness': 'OPEN',
        'unresolved': ['현재 질문의 적용과 충분성은 원문을 다시 확보한 뒤 확인'],
        'jurisdiction': 'UNKNOWN', 'applicable_time': 'UNKNOWN', 'members': [
            {'unit': unit, 'ref': s['id'], 'role': 'SOURCE', 'start': 0,
             'stop': len(json.loads(s['payload'])['text']), 'reason': 'current adopted source'} for s in sources],
        'claims': [], 'procedures': [], 'observations': [], 'documents': sorted({s['document_id'] for s in originals}),
        'visibility': 'PRIVATE', 'concept_status': 'DISCOVERY', 'input_cases': [case['id']],
        'checklist': {'required_facts': False, 'sources': True, 'exceptions': False, 'corrections': True},
        'core_evidence_route': path}
    revision = old['head'] + 1 if old else 1
    scope = repo.scope(principal)
    build = 'core-build:' + digest([unit, route['id']])
    with repo.transaction():
        current(repo, value, principal)
        repo.db.execute('INSERT INTO sw_unit VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET head=excluded.head', (unit, scope, revision))
        repo.db.execute('INSERT INTO sw_knowledge VALUES(?,?,?,?,?,?)', (unit, revision, build, encoded(value), digest(value), 'OPEN'))
        repo.db.execute('INSERT INTO sw_lifecycle VALUES(?,?,?)', (unit, revision, 'PUBLISHED'))
        for member, source in zip(value['members'], sources):
            repo.db.execute('INSERT INTO sw_member VALUES(?,?,?,?)', (unit, revision, member['ref'], encoded(member)))
            repo.db.execute('INSERT INTO sw_dependency VALUES(?,?,?,?,?,?)', (unit, revision, source['id'], source['revision'], source['hash'], 'EVIDENCE'))
        repo.db.execute('INSERT INTO sw_dependency VALUES(?,?,?,?,?,?)', (unit, revision, case['id'], str(case['revision']), digest(case), 'ACL'))
        repo.enqueue(scope, 'projection', unit, revision)
        repo.trace(case['id'], principal, kind='CORE_EVIDENCE_ROUTE', payload={
            'status': 'CURRENT_ACCEPTED', 'unit_id': unit, 'revision': revision,
            'route_id': route['id'], 'goal_revision': goal['revision'], 'path_hash': digest(path)},
            documents=value['documents'], session=cases.original_session)
    return {'unit_id': unit, 'revision': revision, 'route_id': route['id']}


def lookup(host, state, principal, *, question=None):
    """Conditions bind the key; candidate menus and failed discovery do not."""
    if not principal.get('authenticated'):
        return None
    repo = host.shortcut
    from ..ad_store import features
    if not all(features(repo.db, principal['team_id'])[key] for key in ('shortcut', 'wiki')):
        return None
    key = conditions(state)
    request_key = ' '.join(question.split()) if isinstance(question, str) else key['task']
    scopes = repo.knowledge_scopes(principal)
    slots = ','.join('?' for _ in scopes)
    query = f"""SELECT u.id,u.head FROM sw_unit u JOIN sw_knowledge k ON k.unit=u.id AND k.revision=u.head
        WHERE u.scope IN ({slots}) AND u.id LIKE ? AND
        (json_extract(k.payload,'$.core_evidence_route.conditions.task')=? OR
        (json_extract(k.payload,'$.core_evidence_route.contract')=? AND
        EXISTS (SELECT 1 FROM json_each(k.payload,'$.core_evidence_route.question_keys') WHERE value=?)))
        ORDER BY u.rowid DESC"""
    for row in repo.db.execute(query, (*scopes, PREFIX+'%', key['task'], 'curated-core-evidence-route-v1', request_key)):
        try:
            value = repo.current(row['id'], row['head'], principal)
        except (MemoryError, OSError):
            continue
        path = value['core_evidence_route']
        curated = path['contract'] == 'curated-core-evidence-route-v1'
        if curated and question is not None:
            # The literal current request identifies an explicitly curated seed.
            # Model-paraphrased task and current facts still govern SELECT/ASSESS.
            if request_key not in path.get('question_keys', [path['conditions']['task']]):
                continue
        elif path['conditions'] != key:
            continue
        if path['source_binding'] != source_binding(host.binding):
            continue
        if not set(value['documents']) <= set(state['document_ids']):
            continue
        if host.model.pipeline.term_agent.transport.binding['trust_zone'] == 'external' and not path['public_only']:
            continue
        return {**path, 'conditions': key if curated else path['conditions'],
                'unit_id': row['id'], 'revision': row['head']}
    return None


def direct_discovery(recall, path):
    """Current navigation receives fresh handles for the stored source coordinates."""
    from . import law_candidates as lc
    s = recall.s
    idx, _ = lc.index(s)
    hits = []
    selected = []
    for target in path['targets']:
        did = target['document_id']
        if did not in s.scope:
            raise MemoryError('core evidence source is outside current scope')
        for span in target['spans']:
            raw = s.store.source(did, span['block_id'])
            if digest(raw['text'][span['start_cp']:span['end_cp']]) != span['text_hash']:
                raise MemoryError('core evidence original changed')
        for uid in target['read_unit_ids']:
            ids = s.matcher._unit_sources(did, uid)
            if not ids:
                raise MemoryError('core evidence coordinate no longer resolves')
            for sid in ids:
                if sid not in lc.allowed(s):
                    raise MemoryError('core evidence source is not authorized')
                source = s.tools.sources[sid]
                key = sid+'#unit:'+uid
                if any(h['key'] == key for h in hits):
                    continue
                selected.append(sid)
                hits.append({'key': key, 'source_id': sid, 'document_id': did, 'unit_id': uid,
                    'requested_unit_id': uid, 'article_unit_id': str(source['unit_id']),
                    'document_name': source['document_name'], 'heading': source.get('heading', ''),
                    'match_paths': [], 'entry_reason': 'exact_structure'})
    selected = list(dict.fromkeys(selected))
    docs = list(dict.fromkeys(h['document_id'] for h in hits))
    terms = []
    page = {'items': [{'document_id': d, 'article_count': len({h['source_id'] for h in hits if h['document_id']==d}),
                      'unit_count': sum(h['document_id']==d for h in hits)} for d in docs], 'total': len(docs), 'next_cursor': None}
    catalogue = {'contract': lc.CONTRACT, 'terms': terms, 'queries': [], 'law_page': page,
        'query_fingerprint': digest([CONTRACT, path['unit_id'], path['revision'], sorted(s.scope), idx.manifest['index_sha256']]),
        'index_sha256': idx.manifest['index_sha256'], 'search_policy': 'current-core-source-coordinate-v1'}
    s.repo.event('CORE_EVIDENCE_ROUTE_USED', {'unit_id': path['unit_id'], 'revision': path['revision'],
        'origin_goal_revision': path['goal_revision'], 'targets': [{'document_id': t['document_id'], 'read_unit_ids': t['read_unit_ids']} for t in path['targets']],
        'fulltext_discovery': False, 'legal_claim_reuse': False})
    return selected, {'discovery_mode': 'core-route', 'law_navigation': catalogue,
        'unit_hits': hits, 'unit_index_sha256': idx.manifest['index_sha256'], 'selected_for_read': selected,
        'discovered': selected, 'routes': {}, 'queries': [], 'parent_selections_preserved': True,
        'core_evidence_route': {'unit_id': path['unit_id'], 'revision': path['revision']}}

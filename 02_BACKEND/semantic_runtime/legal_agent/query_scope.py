"""User search boundaries are independent of authorization and witnessed reads.

Selectors contain user words, never the authorized document inventory. Metadata
resolves selectors; an empty or ambiguous result never becomes global search.
"""
from copy import deepcopy
from ..contracts import digest
from ..navigation_match import norm
from .errors import ContractError
from . import structure_selection as selection_sets

CONTRACT = 'direct-search-scope-v1'
CHANGE = {'type': 'object', 'additionalProperties': False,
    'required': ['operation', 'targets', 'user_quote'], 'properties': {
        'operation': {'enum': ['KEEP', 'REPLACE', 'ADD', 'CLEAR']},
        'user_quote': {'type': 'string'},
        'targets': {'type': 'array', 'maxItems': 4, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['document', 'structure'], 'properties': {
                'document': {'type': ['string', 'null'], 'minLength': 1},
                'structure': {'type': ['string', 'null'], 'minLength': 1},
                'selection': {'anyOf': [selection_sets.SCHEMA, {'type': 'null'}]}}}}}}
PROMPT = '''
search_scope_change는 매 명령에서 반드시 출력하는 검색 범위 판단이다. 새 범위 지정이 없으면 {operation:"KEEP",targets:[],user_quote:""}를 출력한다. 범위·열거·제외를 queries에만 적고 이 판단을 생략하지 않는다. targets마다 selection을 명시하고, 번호 집합은 selection/structure=null, 문서 전체는 selection=null/structure=null, 번호 없는 목차 제목은 selection=null/structure=제목으로 표현한다.
search_scope_change는 사용자가 직접 지정한 검색 대상 법령/내규와 장·절·조·항·목차 범위를 갱신한다.
operation=KEEP이면 기존 범위를 유지하고 targets=[], user_quote=""다. 단순 검색어 수정·못 찾은 내용 재질문은 범위를 해제하지 않는다.
명시한 법령/범위로 바꾸면 REPLACE, 기존 범위에 명시적으로 추가하면 ADD, 범위를 없애고 전체에서 찾으라고 명시할 때만 CLEAR다.
문서 전체와 모든 문서는 다르다. 특정 법령 전체/규정 전부로 넓히거나 장·절 제한만 없애면 REPLACE로 document=그 법령명, structure=null을 지정한다. 법령 제한은 유지되므로 CLEAR를 쓰지 않는다.
CLEAR는 모든 법령/허용 문서 전체로 문서 제한까지 없애는 요청에만 쓴다. 특정 문서명이 현재 발언에 함께 있으면 전체 해제를 추측하지 말고 NEED_TARGET으로 확인한다. 문서 전체를 요청하면 앞의 REPLACE 규칙을 따른다.
targets의 document는 사용자가 쓴 법령명/문서명/약칭, structure는 사용자가 쓴 장·절·조항 번호나 목차 제목이며 없는 값은 null이다. 실제 ID는 출력하지 않는다.
각 target 값은 user_quote에 실제로 있는 표현만 쓰고 user_quote는 현재 발언에서 그대로 복사한다. 이전 답변에서 추측한 법령명은 범위를 지정하지 않는다.
document=null이면 기존에 지정된 단일 문서 안에서 structure를 찾는다. 구조화된 법령명·목차를 검색 대상으로 제시한 최초 질문도 REPLACE로 지정한다.
현재 질문을 수정하면 같은 goal을 보완한다. 앞선 검색 실패는 새 사건이나 전체 검색의 이유가 아니다. 목적/검색어 수정과 범위 변경은 함께 할 수 있다.
직접 검색은 확정된 범위 안에서만 수행한다. 범위 밖 원문은 이미 읽은 원문에서 검증된 참조·정의 연결을 따라 읽을 수 있으며 이것은 직접 검색 범위를 넓히지 않는다.
'''
PROMPT += selection_sets.PROMPT + '''
search_scope_change.targets의 selection에는 위 구조화 선택을 사용하고 structure=null로 둔다.
단일 항목도 SINGLE로 선택할 수 있다. structure 문자열은 기존 단일 목차 제목 호환용이다.
user_quote는 현재 발언 원문을 그대로 보존한다. 정규화한 parent_path나 n을 user_quote에 억지로 맞춰 다시 쓰지 않는다.
document=null이면 이전에 지정한 단일 문서 문맥을 이어간다. 범위·제외의 기준 부모는 현재 발언과 대화 문맥으로 판단한다.
현재 발언이 직전 확인 질문에 대한 짧은 답이면 recent_dialogue의 마지막 연속 clarification=true 턴에서 사용자가 직접 지정한 대상도 이어받을 수 있다. 그때 user_quote는 해당 사용자 발언의 연속 원문이다. assistant 답변이나 더 오래된 다른 조사에서 범위를 가져오지 않는다. 현재 답변이 그 대상을 선택하는지는 명령 검토에서 함께 확인한다. 거절된 명령 자체는 승인된 범위가 아니다.
'''


def model_change_schema():
    """Current models must declare a scope decision; stored legacy commands remain valid."""
    value = deepcopy(CHANGE)
    target = value['properties']['targets']['items']
    target['required'].append('selection')
    target['properties']['structure']['description'] = '번호 집합은 selection에 쓰고 null. 번호 없는 단일 목차 제목 조회에만 문자열.'
    target['properties']['selection']['description'] = '번호의 단일·복수·범위·제외 선택. 문서 전체 또는 번호 없는 목차 제목이면 null.'
    return value


class UnresolvedScope(ValueError):
    """Expected metadata ambiguity/miss, not an absence of legal evidence."""


def units(matcher, did):
    rows = matcher.units
    return rows.for_document(did) if hasattr(rows, 'for_document') else (
        (key, value) for key, value in rows.items() if key[0] == did)


def within(matcher, did, uid, root):
    if root is None:
        return True
    uid = str(uid); seen = set()
    while uid not in seen:
        if uid == str(root):
            return True
        seen.add(uid)
        node = matcher.units.get((did, uid))
        if not node or node.get('parent') is None:
            return False
        uid = str(node['parent'])
    raise ContractError('search scope structure cycle')


def target(matcher, did, uid):
    metadata = matcher.document_context.get(did, {})
    node = matcher.units.get((did, str(uid))) if uid is not None else None
    return {'document_id': did, 'unit_id': uid,
            'document_name': metadata.get('document_title') or matcher.documents[did],
            'title': node.get('title', '') if node else '',
            'coordinate': node.get('coordinate_key') if node else None,
            'metadata_hash': digest([metadata, node])}


def pending_clarifications(dialogue):
    """Only the uninterrupted clarification exchange at the end of this session."""
    start=len(dialogue)
    while start and dialogue[start-1].get('clarification') is True:start-=1
    return deepcopy(dialogue[start:])


SUBORDINATE = ('시행령', '시행규칙', '시행세칙')


def abbreviates(name, title):
    """A user's shorthand of a document title: same first character, all characters in order.

    "금융회사 지배구조법" for "금융회사의 지배구조에 관한 법률" (ADR-1454 S7). Only the user's own words
    are matched (the follow-up lexical contract is unchanged); a shorthand matching several titles stays
    unresolved. A shorthand without 시행령·시행규칙·시행세칙 does not name those subordinate documents.
    """
    short, full = norm(name), norm(title)
    if len(short) < 3 or not full or short[0] != full[0]:
        return False
    if any(word in full and word not in short for word in SUBORDINATE):
        return False
    rest = iter(full)
    return all(char in rest for char in short)


def name_choices(matcher, authorized, name):
    """Authorized documents a written name denotes: exact title/alias, title part, then shorthand."""
    exact = []; partial = []
    for did in sorted(authorized):
        metadata = matcher.document_context.get(did, {})
        title = metadata.get('document_title') or matcher.documents[did]
        labels = [title, *getattr(matcher, 'document_aliases', {}).get(did, ())]
        if any(norm(name) == norm(label) for label in labels):
            exact.append(did)
        elif norm(name) in norm(title):
            partial.append(did)
    choices = exact or partial
    if not choices:
        choices = [did for did in sorted(authorized) if any(abbreviates(name, label) for label in
                   [matcher.document_context.get(did, {}).get('document_title') or matcher.documents[did],
                    *getattr(matcher, 'document_aliases', {}).get(did, ())])]
    return choices


def declared_title_choices(matcher, authorized, name):
    """A law-title abbreviation the corpus declares, e.g. 「주식회사 등의 외부감사에 관한 법률」(이하 "외감법").

    The declared 「title」 is resolved with name_choices. Declarations naming
    different documents leave the name ambiguous (several choices).
    """
    from . import declared_names
    try:
        _, choices = declared_names.title_documents(matcher, name, authorized,
                                                    lambda title: name_choices(matcher, authorized, title))
    except (ValueError, RuntimeError):
        # Lookup is a hint; the unresolved name is reported as before.
        return []
    return choices


def resolve(change, previous, matcher, authorized, utterance, *, model_resolved=False, reference_utterances=()):
    """Resolve a quoted scope decision against unique authorized metadata.

    Fresh fused entry may resolve ellipsis and aliases to canonical names.
    Existing follow-up commands retain their current lexical contract.
    """
    from jsonschema import validate
    validate(change, CHANGE)
    operation = change['operation']
    if operation == 'KEEP':
        if change['targets'] or change['user_quote']:
            raise UnresolvedScope('유지 명령에는 새 검색 범위를 넣을 수 없습니다.')
        return deepcopy(previous)
    quote = change['user_quote']
    if not quote or not any(quote in text for text in (utterance,*reference_utterances)):
        raise UnresolvedScope('검색 범위 변경의 사용자 원문을 확인해야 합니다.')
    if operation == 'CLEAR':
        if change['targets']:
            raise UnresolvedScope('범위 해제와 새 범위 지정은 함께 할 수 없습니다.')
        # A named document in the current utterance is not proof of an unrestricted
        # request. Preserve the prior scope and clarify; never infer a global one.
        for did in authorized:
            metadata=matcher.document_context.get(did,{})
            title=metadata.get('document_title') or matcher.documents.get(did,'')
            labels=[title,*getattr(matcher,'document_aliases',{}).get(did,())]
            if any(label and norm(label) in norm(utterance+' '+quote) for label in labels):
                raise UnresolvedScope('특정 문서가 포함된 범위 해제 요청입니다. 해당 문서 전체인지, 모든 문서인지 확인해야 합니다.')
        return None
    if not change['targets']:
        raise UnresolvedScope('지정한 법령명 또는 목차를 확인해야 합니다.')
    authorized = set(authorized)
    roots = list(previous['targets']) if previous and operation == 'ADD' else []
    selections = list(previous.get('selections', [])) if previous and operation == 'ADD' else []
    for selector in change['targets']:
        name, structure = selector['document'], selector['structure']
        selection = selector.get('selection')
        if selection is not None and structure is not None:
            raise UnresolvedScope('구조화 선택과 단일 목차 문자열을 함께 지정할 수 없습니다.')
        if not name and not structure and selection is None:
            raise UnresolvedScope('법령명 또는 목차 중 하나가 필요합니다.')
        if not model_resolved and any(value and norm(value) not in norm(quote) for value in (name, structure)):
            raise UnresolvedScope('검색 범위는 현재 발언에 있는 이름으로 지정해야 합니다.')
        if name:
            choices = name_choices(matcher, authorized, name)
            if not choices:
                choices = declared_title_choices(matcher, authorized, name)
        else:
            choices = list(dict.fromkeys(t['document_id'] for t in (previous or {}).get('targets', [])))
        if len(choices) != 1:
            titles = [matcher.document_context.get(d, {}).get('document_title') or matcher.documents[d]
                      for d in choices[:5]]
            raise UnresolvedScope('검색 범위의 문서를 하나로 확인하지 못했습니다: ' +
                                  (', '.join(titles) if titles else str(name or '기존 문서 범위')))
        did = choices[0]; uid = None
        if selection is not None:
            try:
                record = selection_sets.resolve(selection, matcher, did, authorized)
            except selection_sets.SelectionError as exc:
                raise UnresolvedScope(str(exc)) from exc
            if record not in selections: selections.append(record)
            for selected_uid in record['unit_ids']:
                row = target(matcher, did, selected_uid)
                if row not in roots: roots.append(row)
            continue
        if structure:
            candidates = []
            for (doc, node_id), node in units(matcher, did):
                labels = [node.get(k) for k in ('coordinate_key', 'surface', 'title')]
                coordinate=getattr(matcher,'stored_coordinates',{}).get((did,node_id))
                if coordinate:labels.append(coordinate.canonical_surface())
                labels += [' '.join(str(v) for v in (node.get('surface'), node.get('title')) if v)]
                path=[];cursor=str(node_id);seen=set()
                while cursor not in seen:
                    seen.add(cursor);ancestor=matcher.units.get((did,cursor))
                    if not ancestor:break
                    path.append(ancestor.get('surface',''))
                    if ancestor.get('parent') is None:break
                    cursor=str(ancestor['parent'])
                labels.append(' '.join(reversed(path)))

                if any(label and ''.join(structure.split()) == ''.join(str(label).split()) for label in labels):
                    if node.get('coordinate_binding', {}).get('mode') != 'unresolved':
                        candidates.append(str(node_id))
            # A bare persisted coordinate denotes the body branch. Addenda have
            # their own scope and cannot compete merely because surface matches.
            # Use the same stored coordinate grammar as typed selections, never
            # infer a legal scope from the question or article title.
            from lawrag.core.legal_coordinate import parse_label
            requested = parse_label(structure)
            if requested is not None and ''.join(structure.split()) == requested.canonical_surface():
                coordinates = getattr(matcher, 'stored_coordinates', {})
                candidates = [candidate for candidate in candidates
                    if matcher.units[(did,candidate)].get('coordinate_scope') == 'body'
                    and coordinates.get((did,candidate)) is not None
                    and coordinates[(did,candidate)].as_dict() == requested.as_dict()]
            if len(candidates) != 1:
                raise UnresolvedScope('지정 문서에서 목차·조항을 하나로 확인하지 못했습니다: ' + structure)
            uid = candidates[0]
        row = target(matcher, did, uid)
        if row not in roots:
            roots.append(row)
    check_selection_exclusions(matcher, roots, selections)
    if len(roots) > (selection_sets.MAX_NODES if selections else 16):
        raise UnresolvedScope('검색 범위가 너무 많습니다. 조사할 문서·목차를 좁혀 주세요.')
    record = {'contract': CONTRACT, 'targets': roots}
    if selections: record['selections'] = selections
    return {**record, 'hash': digest(record)}


def check_selection_exclusions(matcher, roots, selections):
    for selected_set in selections:
        for excluded in selected_set['excluded_unit_ids']:
            if any(t['document_id'] == selected_set['document_id'] and
                   (t['unit_id'] is None or within(matcher,t['document_id'],excluded,t['unit_id']) or
                    within(matcher,t['document_id'],t['unit_id'],excluded)) for t in roots):
                raise UnresolvedScope('기존 또는 다른 선택 범위가 제외 항목을 다시 포함합니다. 포함·제외를 함께 REPLACE로 지정해 주세요.')


def attach(session, scope):
    if scope:
        if scope.get('contract') != CONTRACT or scope.get('hash') != digest({k:v for k,v in scope.items() if k != 'hash'}):
            raise ContractError('search scope hash mismatch')
        for row in scope['targets']:
            did = row['document_id']
            if did not in session.scope:
                raise ContractError('search scope outside authorization')
            if target(session.matcher, did, row['unit_id']) != row:
                raise ContractError('search scope metadata changed; resolve the requested scope again')
        for record in scope.get('selections', []):
            selection_sets.verify(record, session.matcher, session.scope)
        try:
            check_selection_exclusions(session.matcher, scope['targets'], scope.get('selections', []))
        except UnresolvedScope as exc:
            raise ContractError('persisted search scope reincludes excluded units') from exc
    session.direct_search_scope = deepcopy(scope)
    # Grants are rebuilt from verified acquired evidence, never inherited as ACL.
    session.scope_read_grants = {}


def active(session):
    return getattr(session, 'direct_search_scope', None)


def documents(session):
    scope = active(session)
    return sorted({t['document_id'] for t in scope['targets']} & set(session.scope)) if scope else session.scope


def direct(session, did, uid=None):
    scope = active(session)
    if did not in session.scope:
        return False
    return not scope or any(t['document_id'] == did and
        (t['unit_id'] is None or uid is not None and within(session.matcher, did, uid, t['unit_id']))
        for t in scope['targets'])


def search_sources(session):
    from .law_candidates import allowed
    if not active(session):
        return allowed(session)
    docs = frozenset(documents(session))
    sources = session.tools.sources
    scoped = getattr(sources, 'ids_for_documents', None)
    if scoped is not None:
        verify = getattr(sources, 'cache_binding', None)
        if verify is None:
            return scoped(docs)
        binding = verify()
        key = (id(sources), binding, frozenset(session.scope), docs)
        cached = getattr(session, '_direct_search_sources', None)
        if cached is None or cached[0] != key:
            ids = scoped(docs)
            if verify and verify() != binding:
                raise ContractError('search source binding changed')
            session._direct_search_sources = (key, ids)
        # Retain Oracle SourceScope: fulltext pushes its document predicate to SQL.
        return session._direct_search_sources[1]
    return frozenset(sid for sid in allowed(session) if sources[sid]['document_id'] in docs)


def fulltext(session):
    """Apply unit filters before ranking and pagination, including global RESEARCH."""
    scope = active(session)
    if not scope or all(t['unit_id'] is None for t in scope['targets']):
        return {}
    cached = getattr(session, '_direct_search_keys', None)
    if cached and cached[0] == scope['hash']:
        return {'unit_keys': cached[1]} if cached[1] is not None else {}
    from .law_candidates import fulltext_scope_keys
    keys = set()
    for row in scope['targets']:
        found = fulltext_scope_keys(session, row['document_id'], row['unit_id'])
        if found is None:
            # A whole large document is a direct target: rank within the targeted
            # documents (search_sources) instead of listing every unit key.
            session._direct_search_keys = (scope['hash'], None)
            return {}
        keys.update(found)
    session._direct_search_keys = (scope['hash'], frozenset(keys))
    return {'unit_keys': frozenset(keys)}


def filter_route(session, route):
    if not active(session) or route.get('status') != 'MATCH' or 'pairs' not in route:
        return route
    pairs = [p for p in route['pairs'] if direct(session, p['document_id'], p.get('unit_id'))]
    ids = {sid for p in pairs for sid in ([p['source_id']] if p.get('source_id') else
        session.matcher._unit_sources(p['document_id'], p['unit_id']))}
    return {**route, 'pairs': pairs, 'source_ids': [s for s in route['source_ids'] if s in ids],
            'status': 'MATCH' if pairs else 'MISS'}


def catalogue(session, *, recover_names=True, **kwargs):
    from . import structure_query as sq
    if active(session):
        kwargs['row_filter'] = lambda row: direct(session, row['document_id'], row.get('unit_id'))
    page=sq.catalogue(session.matcher, documents(session), **kwargs)
    if active(session):page['resolutions']=[filter_route(session,r) for r in page['resolutions']]
    if recover_names:
        from .law_name_recovery import attach
        page=attach(page,session.matcher,documents(session))
    return page


def permitted_blocks(session, sid):
    source = session.tools.sources[sid]; did = source['document_id']
    if did not in session.scope:
        return set()
    known = {str(b['block_id']) for b in source['blocks']}
    if not active(session) or direct(session, did):
        return known
    from .unit_reading import blocks
    permitted = set()
    for row in active(session)['targets']:
        if row['document_id'] == did:
            permitted.update(map(str, blocks(session, did, str(row['unit_id']), 'subtree')))
    permitted.update(getattr(session, 'scope_read_grants', {}).get(sid, {}))
    return known & permitted


def grant(session, sid, block_ids, *, witness):
    """Called only after unit_relations verified an acquired anchor and edge."""
    if not active(session):
        return
    source = session.tools.sources[sid]
    ids = set(map(str, block_ids))
    if source['document_id'] not in session.scope or not ids <= {str(b['block_id']) for b in source['blocks']}:
        raise ContractError('reference read grant outside authorization or source')
    records = session.scope_read_grants.setdefault(sid, {})
    fresh = ids - set(records)
    records.update({bid: deepcopy(witness) for bid in ids})
    if fresh:
        session.repo.event('SCOPE_REFERENCE_READ_GRANT', {'scope_hash': active(session)['hash'],
            'source_id': sid, 'block_ids': sorted(fresh), 'witness': witness})


def filter_offers(session, hit, offers, blocked):
    if not active(session):
        return offers, blocked
    permitted = permitted_blocks(session, hit['source_id'])
    kept = []; rejected = list(blocked)
    for offer in offers:
        if set(map(str, offer['block_ids'])) <= permitted:
            kept.append(offer)
        else:
            rejected.append({'unit_id': offer['unit_id'], 'extent': offer['extent'],
                             'reason': 'outside_direct_scope_without_verified_connection'})
    return kept, rejected


def action_allowed(session, action, identity):
    if not active(session):
        return True
    did = identity.get('document_id')
    if action in ('OPEN_LAW', 'SEARCH_BODY', 'SEARCH_STRUCTURE', 'RETRY_LAW_STRUCTURE', 'NEXT_STRUCTURE', 'BROWSE_STRUCTURE', 'OPEN_STRUCTURE'):
        if did is None:
            return True  # All queries still execute through scoped catalogue/fulltext.
        if did not in documents(session):
            return False
        uid = identity.get('unit_id')
        return uid is None or direct(session, did, uid)
    if action == 'READ_ARTICLES':
        sid = identity.get('source_id')
        if sid:
            return bool(permitted_blocks(session, sid))
    return True


def read_identity(session, action, identity):
    """Offer the requested subtree rather than an enclosing whole article."""
    if not active(session) or action != 'READ_ARTICLES' or not identity.get('source_id'):
        return identity
    source = session.tools.sources[identity['source_id']]
    did = source['document_id']; uid = identity.get('unit_id', source['unit_id'])
    if direct(session, did, uid):
        return identity
    # A witnessed endpoint already carries its exact unit. Keep it for the
    # read-offer validator, which checks the actual blocks again before I/O.
    if getattr(session, 'scope_read_grants', {}).get(identity['source_id']):
        return identity
    roots = [t['unit_id'] for t in active(session)['targets'] if t['document_id'] == did
             and t['unit_id'] is not None and within(session.matcher,did,t['unit_id'],uid)]
    if len(roots) == 1:
        return {**identity, 'unit_id': roots[0]}
    return None


def document_structure(session, document_id, *, unit_id=None, offset=0, limit=8):
    from . import structure_query as sq
    if not active(session):
        return sq.document_structure(session.matcher,documents(session),document_id,
            unit_id=unit_id,offset=offset,limit=limit)
    if document_id not in documents(session):
        # Connected sources keep their already acquired text, not a new search tree.
        return {'contract':'stored-document-structure-v1','document_id':document_id,
            'document_name':session.matcher.documents[document_id], 'shape':{},'focus':None,
            'path':[],'parent_unit_id':None,'children':[],'offset':0,'total':0,'next_offset':None,
            'navigation_hint_only':True,'citation_eligible':False,'scope_limited':True}
    if unit_id is not None and not direct(session,document_id,unit_id):
        unit_id = None
    roots = [t['unit_id'] for t in active(session)['targets'] if t['document_id'] == document_id]
    if unit_id is None and None not in roots:
        tree = sq.document_tree(session.matcher,document_id)
        rows = [sq.tree_row(session.matcher,document_id,str(uid),tree) for uid in roots]
        page = sq.document_structure(session.matcher,documents(session),document_id,limit=0)
        return {**page,'children':rows[offset:offset+limit], 'offset':offset,'total':len(rows),
            'next_offset':offset+limit if offset+limit < len(rows) else None,'scope_limited':True}
    return sq.document_structure(session.matcher,documents(session),document_id,
        unit_id=unit_id,offset=offset,limit=limit)


def drop_grants(session, saved, reason, *, unrestored=None):
    """Persisted reference grants that no current acquired original witnesses are given up, not failed on.

    ADR-1454 S4 (MAIN176 HTTP 500): turn 2 narrowed the anchor article to the chosen 항 records, so on
    turn 3 the references witnessed by the dropped blocks could not be re-verified and the whole request
    died in restore_grants. A grant only widens what a connected source may be read; without it the
    direct scope stays exactly as resolved and the investigation acquires the connection again if needed.
    Nothing is granted here (the session keeps only the grants verified in this request).
    """
    rows = unrestored if unrestored is not None else {sid: sorted(rows) for sid, rows in saved.items()}
    rows = {sid: ids for sid, ids in rows.items() if ids}
    if not rows:
        return
    session.repo.event('SCOPE_REFERENCE_GRANT_DROPPED', {'scope_hash': active(session)['hash'], 'reason': reason,
        'sources': {sid: {'block_ids': ids, 'kinds': sorted({str((saved.get(sid) or {}).get(b, {}).get('kind') or 'REFERENCE') for b in ids})}
                    for sid, ids in rows.items()},
        'effect': 'reads of these blocks need a new verified connection in this request; direct scope unchanged'})


def restore_grants(session, checkpoint):
    """Revalidate persisted witnessed edges from acquired originals on resume.

    Grants that cannot be re-witnessed now are dropped (narrower reading scope), never a request failure.
    """
    if not active(session) or not checkpoint.get('scope_read_grants'):
        return
    if checkpoint.get('direct_scope_hash') != active(session)['hash']:
        drop_grants(session, checkpoint['scope_read_grants'], 'DIRECT_SCOPE_CHANGED')
        return
    from . import unit_relations as rel
    records={**checkpoint.get('selected',{}),**checkpoint.get('contexts',{})}
    for record in records.values():
        for evidence in record['evidence']:session.source.verify(evidence)
    saved=checkpoint['scope_read_grants']
    pending={w['reference_id'] for rows in saved.values() for w in rows.values() if w.get('reference_id')}
    anchors=list(dict.fromkeys(r['source_id'] for r in records.values()))
    # Exact IDs avoid rerunning unrelated reference pages. New grants may allow
    # a later anchor in a multi-hop chain. No read/model budget is reset here.
    for _ in range(len(pending)+1):
        before=sum(len(v) for v in session.scope_read_grants.values())
        for offset in range(0,len(anchors),rel.LIMITS['anchors_per_round']):
            ids=sorted(pending)
            for start in range(0,len(ids),rel.LIMITS['edges_per_anchor']):
                rel.catalog(session,anchors[offset:offset+rel.LIMITS['anchors_per_round']],records,set(),
                    only_references=ids[start:start+rel.LIMITS['edges_per_anchor']])
        for sid,rows in saved.items():
            for bid,w in rows.items():
                if w.get('kind')!='STRUCTURAL_ANCESTOR':continue
                child=next((r for r in records.values() if r['source_id']==sid and
                    str(r['offer']['unit_id'])==str(w['acquired_unit_id']) and
                    set(map(str,r['offer']['block_ids'])) <= permitted_blocks(session,sid)),None)
                if child and within(session.matcher,child['document_id'],w['acquired_unit_id'],w['parent_unit_id']):
                    from .unit_reading import blocks
                    if bid in set(blocks(session,child['document_id'],str(w['parent_unit_id']),'exact')):
                        grant(session,sid,[bid],witness=w)
        if sum(len(v) for v in session.scope_read_grants.values())==before:break
    if any(w.get('kind')=='REQUIRED_CONNECTED_TARGET' for rows in saved.values() for w in rows.values()):
        from .source_goal_control import grant_required_targets
        grant_required_targets(session,checkpoint,restore=True)
    unrestored={sid:sorted(set(rows)-permitted_blocks(session,sid)) for sid,rows in saved.items()}
    drop_grants(session,saved,'NO_CURRENT_VERIFIED_WITNESS',unrestored=unrestored)

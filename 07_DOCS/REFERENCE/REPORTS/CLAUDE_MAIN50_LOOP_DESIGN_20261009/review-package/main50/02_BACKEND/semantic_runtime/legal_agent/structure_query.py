"""Resolve explicit document/article pairs using the bound original structure only."""
import re
import threading
from collections import defaultdict

from lawrag.core.legal_coordinate import find_coordinates
from ..document_aliases import _key as name_key
from ..document_roles import role_of_metadata

_LOCK = threading.Lock()
_COORDINATES = None
_INDEX = None


def document_hits(text, matcher):
    """A body request names the body document, not every annex bearing its title."""
    out = []
    for hit in matcher.document_names.match(text):
        if hit['key'] not in matcher.title_keys:
            continue
        values = [did for did in hit['values'] if role_of_metadata(
            getattr(matcher, 'document_context', {}).get(did, {})) == 'body']
        if values:
            out.append({**hit, 'values': list(dict.fromkeys(values))})
    return out


def coordinate_index(matcher):
    """Reuse the immutable generation's coordinate map across request matchers."""
    global _COORDINATES, _INDEX
    coordinates = matcher.stored_coordinates
    with _LOCK:
        if coordinates is not _COORDINATES:
            index = defaultdict(list)
            for key, coordinate in coordinates.items():
                unit = matcher.units[key]
                if (coordinate and coordinate.unit == '조'
                        and unit.get('coordinate_scope') == 'body'
                        and unit.get('coordinate_binding', {}).get('mode') != 'unresolved'):
                    index[(key[0], coordinate.canonical_surface())].append(key[1])
            _COORDINATES, _INDEX = coordinates, dict(index)
        return _INDEX


def heading_route(question, matcher, scope, hits, result):
    """A literal stored article heading may locate a node without a numbered query."""
    names = {did for hit in hits for did in hit['values']}
    if len(names) != 1 or not names <= set(scope):
        return {**result, 'reason': 'AMBIGUOUS_DOCUMENT_PAIR'}
    did = next(iter(names))
    matches = defaultdict(set)
    for hit in matcher.structures.match(question):
        if len(hit['key']) < 4 or any(h['start'] <= hit['start'] and hit['end'] <= h['end'] for h in hits):
            continue
        for value in hit['values']:
            key = value['document_id'], value['unit_id']
            coordinate = matcher.stored_coordinates.get(key)
            unit = matcher.units.get(key, {})
            if (value['kind'] == 'TITLE' and key[0] == did and coordinate and coordinate.unit == '조'
                    and not coordinate.chain and unit.get('coordinate_scope') == 'body'
                    and unit.get('coordinate_binding', {}).get('mode') != 'unresolved'):
                matches[hit['key']].add(key)
    if not matches or any(len(keys) != 1 for keys in matches.values()):
        return {**result, 'reason': 'MISSING_OR_AMBIGUOUS_HEADING'}
    pairs, sources = [], []
    for _, uid in sorted({key for keys in matches.values() for key in keys}):
        coordinate = matcher.stored_coordinates[(did, uid)].canonical_surface()
        if coordinate_index(matcher).get((did, coordinate)) != [uid]:
            return {**result, 'reason': 'MISSING_OR_AMBIGUOUS_COORDINATE'}
        ids = matcher._unit_sources(did, uid)
        if not ids or any(matcher.sources[sid]['document_id'] != did for sid in ids):
            return {**result, 'reason': 'NO_BOUND_ORIGINAL'}
        sources.extend(ids)
        pairs.append({'document_id': did, 'document_name': matcher.documents[did],
                      'unit_id': uid, 'coordinate': coordinate, 'heading': matcher.units[(did, uid)].get('title', '')})
    sources = list(dict.fromkeys(sources))
    if len(sources) > 16:
        return {**result, 'reason': 'STRUCTURE_SELECTION_LIMIT'}
    return {'status': 'MATCH', 'pairs': pairs, 'source_ids': sources, 'reason': 'EXACT_DOCUMENT_HEADING'}


def definition_route(question, matcher, scope, hits, result):
    """Route one explicitly quoted term to its bound definition in one named document."""
    if not re.search(r'정의|의미|뜻|이란|란\s*무엇', question):
        return result
    quoted = set(re.findall(r"['\"‘“]([^'\"’”]{2,40})['\"’”]", question))
    if len(quoted) != 1:
        return result
    named = {did for hit in hits for did in hit['values']}
    if len(named) != 1 or not named <= set(scope):
        return result
    definitions = getattr(getattr(matcher, 'tools', None), 'definitions', {})
    did = next(iter(named))
    term = next(iter(quoted))
    rows = [d for d in definitions.values() if d['document_id'] == did and d['key'] == term]
    if not rows or len(rows) > 16:
        return result
    sources = list(dict.fromkeys(d['source_id'] for d in rows))
    if any(sid not in matcher.sources or matcher.sources[sid]['document_id'] != did
           for sid in sources):
        return result
    return {'status': 'MATCH', 'pairs': [{'document_id': did,
             'document_name': matcher.documents[did], 'unit_id': d['unit_id'],
             'term': term, 'definition_id': d['id']} for d in rows],
            'source_ids': sources, 'reason': 'EXACT_DOCUMENT_DEFINITION'}


def navigation_context(question, matcher, scope, *, matches=None):
    """Compact, non-citable structure/term locations for the existing first planner."""
    matches = matcher.starts(question, scope) if matches is None else matches
    scope = set(scope)
    named = {d['id'] for d in matches['documents']}
    structures = []
    for row in matches['structures']:
        did, uid = row['document_id'], row['unit_id']
        if did not in scope or (named and did not in named):
            continue
        unit = matcher.units.get((did, uid), {})
        structures.append({'document_id': did, 'unit_id': uid,
                           'coordinate': unit.get('coordinate_key'),
                           'title': unit.get('title', '')[:100], 'match_kind': row['kind']})
        if len(structures) == 8:
            break
    terms = []
    for row in matches['terms']:
        term = matcher.tools.terms.get(row['id'], {})
        label = term.get('label', '')
        if label and label not in {t['label'] for t in terms}:
            terms.append({'term_id': row['id'], 'label': label,
                          'question_text': row['question_spans'][0]['text']})
        if len(terms) == 6:
            break
    # A definition in another document is a possible lead, never an applicable rule.
    labels = {t['label'] for t in terms}
    labels.update(re.findall(r"['\"‘“]([^'\"’”]{2,40})['\"’”]", question))
    definition_candidates = []
    for d in getattr(matcher.tools, 'definitions', {}).values():
        if (d['document_id'] not in scope or d['key'] not in labels or
                (named and d['document_id'] not in named)):
            continue
        definition_candidates.append({'definition_id': d['id'], 'term': d['key'],
                                      'document_id': d['document_id'], 'unit_id': d['unit_id'],
                                      'source_id': d['source_id'],
                                      'scope_status': d.get('scope_status')})
        if len(definition_candidates) > 8:
            break
    # An arbitrary first page from many documents would bias the first planner.
    ambiguous = not named and (len(definition_candidates) > 8 or
        len({d['document_id'] for d in definition_candidates}) > 3)
    definitions = [] if ambiguous else definition_candidates[:8]
    return {'documents': [{'document_id': d['id'], 'name': d['name']}
                          for d in matches['documents'][:3] if d['id'] in scope],
            'structures': structures, 'terms': terms, 'definitions': definitions,
            'definition_candidates_ambiguous': ambiguous,
            'navigation_hint_only': True, 'citation_eligible': False}


def _resolve(question, matcher, scope, *, document_id=None):
    """All requested pairs must be unique and readable; partial hits never narrow scope."""
    result = {'status': 'MISS', 'pairs': [], 'source_ids': [], 'reason': 'NO_EXPLICIT_PAIR'}
    coordinates = find_coordinates(question)
    if not getattr(matcher, 'stored_coordinates', None):
        return result
    if (re.search(r'부칙|별표|별지|부터|내지|[~～]', question)
            or any(coordinates[i].start < coordinates[i-1].end for i in range(1, len(coordinates)))):
        return {**result, 'reason': 'RANGE_OR_NON_BODY'}
    hits = document_hits(question, matcher)
    if document_id is not None:
        if document_id not in scope:
            return {**result, 'reason': 'DOCUMENT_OUTSIDE_REQUEST_SCOPE'}
        if hits and any(set(h['values']) != {document_id} for h in hits):
            return {**result, 'reason': 'CONFLICTING_DOCUMENT_TARGET'}
        if not hits:
            # A server-issued document target supplies the missing name. It does
            # not change coordinates or manufacture a law-name alias.
            hits = [{'key': '', 'start': 0, 'end': 0, 'values': [document_id]}]
    if not hits:
        return result
    if not coordinates:
        heading = heading_route(question, matcher, scope, hits, result)
        return heading if heading['status'] == 'MATCH' else definition_route(question, matcher, scope, hits, result)
    scope = set(scope)
    index = coordinate_index(matcher)
    previous_end = 0
    pairs, sources = [], []
    for mention in coordinates:
        preceding = [h for h in hits if previous_end <= h['start'] and h['end'] <= mention.start]
        if not preceding:
            preceding = [h for h in hits if h['end'] <= mention.start][-1:]
        if not preceding and len(hits) == 1:
            preceding = hits
        if len(preceding) != 1 or len(set(preceding[0]['values'])) != 1:
            return {**result, 'reason': 'AMBIGUOUS_DOCUMENT_PAIR'}
        gap_start = max(previous_end, preceding[0]['end'])
        if re.search(r'(?:시행령|시행규칙|[가-힣A-Za-z]+(?:법|규정|규칙))', question[gap_start:mention.start]):
            # "법A 제6조와 시행령 제7조" must not silently bind both to 법A.
            return {**result, 'reason': 'UNRESOLVED_INTERVENING_DOCUMENT'}
        did = preceding[0]['values'][0]
        if did not in scope:
            return {**result, 'reason': 'DOCUMENT_OUTSIDE_REQUEST_SCOPE'}
        locator = mention.coordinate.canonical_surface()
        units = index.get((did, locator), [])
        if len(units) != 1:
            return {**result, 'reason': 'MISSING_OR_AMBIGUOUS_COORDINATE'}
        ids = matcher._unit_sources(did, units[0])
        if not ids or any(matcher.sources[sid]['document_id'] != did for sid in ids):
            return {**result, 'reason': 'NO_BOUND_ORIGINAL'}
        pairs.append({'document_id': did, 'document_name': matcher.documents[did],
                      'unit_id': units[0], 'coordinate': locator,
                      'question_span': {'start': mention.start, 'end': mention.end, 'text': mention.surface}})
        sources.extend(ids)
        previous_end = mention.end
    sources = list(dict.fromkeys(sources))
    if len(sources) > 16:
        return {**result, 'reason': 'STRUCTURE_SELECTION_LIMIT'}
    return {'status': 'MATCH', 'pairs': pairs, 'source_ids': sources, 'reason': 'EXACT_DOCUMENT_COORDINATE'}


FAILURES = {
    'MISSING_DOCUMENT': ('조회할 문서를 특정하지 못했습니다.', 'SEARCH_STRUCTURE'),
    'AMBIGUOUS_DOCUMENT': ('문서 이름에 해당하는 판본 또는 문서가 여러 개입니다.', 'CHOOSE_VERSION'),
    'MISSING_COORDINATE': ('현재 문서의 해당 분기에 요청한 좌표가 없습니다.', 'OPEN_STRUCTURE'),
    'AMBIGUOUS_COORDINATE': ('같은 분기에 요청한 좌표가 중복되어 원문을 확정할 수 없습니다.', 'BROWSE_STRUCTURE'),
    'UNRESOLVED_COORDINATE_BINDING': ('좌표는 저장되어 있지만 구조 바인딩이 미해결입니다.', 'BROWSE_STRUCTURE'),
    'MISSING_TITLE': ('현재 분기에 일치하는 저장 제목이 없습니다.', 'OPEN_STRUCTURE'),
    'TITLE_FILTER_MISMATCH': ('좌표는 있지만 지정한 제목 조건과 일치하지 않습니다.', 'BROWSE_STRUCTURE'),
    'MISSING_STRUCTURE_BRANCH': ('요청한 본문·부칙 등의 분기가 저장 구조에 없습니다.', 'OPEN_STRUCTURE'),
    'MISSING_ORIGINAL': ('구조 위치에 연결된 원문이 없습니다.', 'BROWSE_STRUCTURE'),
    'NON_UNIQUE_ORIGINAL': ('구조 위치의 원문 연결이 유일하지 않습니다.', 'BROWSE_STRUCTURE'),
    'INVALID_COORDINATE': ('좌표 필드에 하나의 완전한 좌표를 지정해야 합니다.', 'SEARCH_STRUCTURE'),
    'CONFLICTING_DOCUMENT': ('선택한 문서와 조회 표현에서 지정한 문서가 다릅니다.', 'SEARCH_STRUCTURE'),
    'OUTSIDE_SCOPE': ('요청 문서는 현재 허용 범위에 없습니다.', 'SEARCH_STRUCTURE'),
    'UNSUPPORTED_STRUCTURE_RANGE': ('본문 단일 좌표 조회로 범위·부칙·별표 요청을 대체할 수 없습니다.', 'OPEN_STRUCTURE'),
    'SELECTION_LIMIT': ('한 번에 읽을 수 있는 구조 선택 한도를 넘었습니다.', 'OPEN_STRUCTURE'),
    'UNRESOLVED_HEADING': ('저장된 제목 위치를 유일하게 확정하지 못했습니다.', 'SEARCH_STRUCTURE'),
}


def failure(code, *, count=None):
    message, action = FAILURES[code]
    return {'code': code, 'message': message, 'suggested_action': action,
            **({'candidate_count': count} if count is not None else {}),
            'automatic_fulltext_fallback': False}


def resolve(question, matcher, scope, *, document_id=None):
    """Preserve the legacy route while exposing a precise, scoped failure code."""
    result = _resolve(question, matcher, scope, document_id=document_id)
    if result['status'] == 'MATCH':
        return result
    reason = result['reason']
    code = {'NO_EXPLICIT_PAIR': 'MISSING_DOCUMENT', 'AMBIGUOUS_DOCUMENT_PAIR': 'AMBIGUOUS_DOCUMENT',
        'MISSING_OR_AMBIGUOUS_HEADING': 'UNRESOLVED_HEADING', 'NO_BOUND_ORIGINAL': 'MISSING_ORIGINAL',
        'RANGE_OR_NON_BODY': 'UNSUPPORTED_STRUCTURE_RANGE', 'DOCUMENT_OUTSIDE_REQUEST_SCOPE': 'OUTSIDE_SCOPE',
        'CONFLICTING_DOCUMENT_TARGET': 'CONFLICTING_DOCUMENT', 'UNRESOLVED_INTERVENING_DOCUMENT': 'MISSING_DOCUMENT',
        'STRUCTURE_SELECTION_LIMIT': 'SELECTION_LIMIT'}.get(reason, 'MISSING_COORDINATE')
    count = None
    if reason == 'MISSING_OR_AMBIGUOUS_COORDINATE':
        hits = document_hits(question, matcher)
        docs = {d for h in hits for d in h['values'] if d in scope}
        if document_id is not None:
            docs = {document_id} & set(scope)
        if len(docs) == 1:
            did = next(iter(docs)); index = coordinate_index(matcher)
            for mention in find_coordinates(question):
                locator = mention.coordinate.canonical_surface()
                ids = index.get((did, locator), [])
                if len(ids) == 1:
                    continue
                count = len(ids)
                code = 'AMBIGUOUS_COORDINATE' if ids else 'MISSING_COORDINATE'
                if not ids and any(d == did and c and c.canonical_surface() == locator
                        and matcher.units[(d, u)].get('coordinate_scope') == 'body'
                        and matcher.units[(d, u)].get('coordinate_binding', {}).get('mode') == 'unresolved'
                        for (d, u), c in matcher.stored_coordinates.items()):
                    code = 'UNRESOLVED_COORDINATE_BINDING'
                break
    return {**result, 'failure': failure(code, count=count)}


def lookup_report(page):
    """Summarize outcomes without hiding candidates or inventing original text."""
    rows = page['items']
    structures = [r for r in rows if r['kind'] == 'structure']
    diagnostic = page.get('failure')
    if not diagnostic and structures:
        if any(r.get('ambiguous') for r in structures):
            diagnostic = failure('AMBIGUOUS_COORDINATE', count=page['total'])
        elif any(not r.get('source_binding_unique') for r in structures
                 if r.get('coordinate_scope') == 'body' and r.get('level', '조') in ('조','항','호','목')):
            diagnostic = failure('NON_UNIQUE_ORIGINAL' if any(r.get('original_count', 0) > 1 for r in structures)
                                 else 'MISSING_ORIGINAL')
    if not diagnostic and not rows and page['total'] == 0:
        diagnostic = next((r['failure'] for r in page['resolutions'] if r.get('failure')), failure('MISSING_COORDINATE'))
    return {**page, 'lookup_status': 'MISS' if not rows else 'NEEDS_SELECTION' if diagnostic
            or page['total'] > 1 else 'MATCH', 'failure': diagnostic}


def catalogue(matcher, scope, *, queries=None, document_id=None, offset=0, limit=8,
              structure_filter=None):
    """Paged stored titles/coordinates; no body scan, fulltext rank or evidence.

    A bare coordinate across documents is a candidate list, never an exact pair.
    Duplicate body coordinates remain visible without an executable READ.
    """
    scope = set(scope)
    if document_id is not None and document_id not in scope:
        raise ValueError('structure target outside request scope')
    if structure_filter is not None:
        return filtered_catalogue(matcher, scope, document_id, structure_filter, offset, limit)
    docs = {did for did in ({document_id} if document_id is not None else scope)
            if role_of_metadata(getattr(matcher, 'document_context', {}).get(did, {})) == 'body'}
    queries = list(queries or [])
    # Planner queries form one request: a bare coordinate must inherit the
    # explicitly named document set, including inaccessible/ambiguous names.
    # With no named document, keep the broad metadata-only candidate list.
    named_batch = {did for query in queries for hit in document_hits(query, matcher)
                   for did in hit['values']}
    if document_id is None and named_batch:
        docs &= named_batch
    rows = {}; resolutions = []
    index = coordinate_index(matcher)
    for query in queries or ['']:
        route = resolve(query, matcher, scope, document_id=document_id) if query else None
        if route:
            resolutions.append({'query': query, **route})
        if route and route['status'] == 'MATCH':
            keys = {(p['document_id'], str(p['unit_id'])) for p in route['pairs']
                    if p['document_id'] in docs
                    and matcher.stored_coordinates.get((p['document_id'], str(p['unit_id'])))
                    and (p['document_id'], matcher.stored_coordinates[
                        (p['document_id'], str(p['unit_id']))].canonical_surface()) in index}
        else:
            hits = document_hits(query, matcher) if query else []
            named = {did for h in hits for did in h['values']}
            active = docs & named if named else docs
            # An inaccessible named law must not become an all-document lookup.
            if document_id and named and named != {document_id}:
                active = set()
            coordinates = [c.coordinate.canonical_surface() for c in find_coordinates(query)]
            if coordinates:
                keys = {(did, uid) for (did, coordinate), ids in index.items()
                        if did in active and coordinate in coordinates for uid in ids}
                if route and route['reason'] == 'RANGE_OR_NON_BODY':
                    keys = set()
            else:
                title_hits = {(r['document_id'], str(r['unit_id']))
                    for h in matcher.structures.match(query) for r in h['values'] if r['kind'] == 'TITLE'} if query else set()
                keys = {(did, uid) for (did, coordinate), ids in index.items()
                        for uid in ids if did in active and not matcher.stored_coordinates[(did, uid)].chain
                        and (not query or (did, uid) in title_hits)}
                if query and not keys:
                    q = name_key(query)
                    for did in sorted(active):
                        labels = [matcher.documents[did],
                            getattr(matcher, 'document_context', {}).get(did, {}).get('document_title', ''),
                            *getattr(matcher, 'document_aliases', {}).get(did, ())]
                        if did in named or any(q and q in name_key(label) for label in labels):
                            rows[('document', did)] = {'kind': 'document', 'document_id': did,
                                'document_name': matcher.documents[did], 'content_read': False}
        for did, uid in keys:
            unit = matcher.units[(did, uid)]
            coordinate = matcher.stored_coordinates[(did, uid)].canonical_surface()
            ids = matcher._unit_sources(did, uid)
            readable = len(ids) == 1 and matcher.sources.get(ids[0], {}).get('document_id') == did
            rows[('structure', did, uid)] = {'kind': 'structure', 'document_id': did,
                'document_name': matcher.documents[did], 'unit_id': uid, 'coordinate': coordinate,
                'title': unit.get('title', ''), 'coordinate_scope': 'body', 'content_read': False,
                'ambiguous': len(index[(did, coordinate)]) != 1,
                'source_id': ids[0] if readable else None, 'source_binding_unique': readable,
                'original_count': len(ids)}
    ordered = sorted(rows.values(), key=lambda r: (r['document_name'], r['document_id'],
        0 if r['kind'] == 'document' else 1,
        matcher.units[(r['document_id'], r['unit_id'])].get('span', [0])[0] if r['kind'] == 'structure' else 0,
        r.get('unit_id', '')))
    for row in ordered[offset:offset+limit]:
        if row['kind'] == 'structure':
            row['path'] = node_path(matcher, row['document_id'], row['unit_id'])
    return lookup_report({'contract': 'stored-structure-catalogue-v1', 'queries': queries,
        'document_id': document_id, 'offset': offset, 'total': len(ordered),
        'items': ordered[offset:offset+limit],
        'next_offset': offset+limit if offset+limit < len(ordered) else None,
        'resolutions': resolutions, 'navigation_hint_only': True, 'citation_eligible': False})


def node_level(matcher, did, uid):
    unit = matcher.units[(did, uid)]
    coordinate = matcher.stored_coordinates.get((did, uid))
    if coordinate:
        return (coordinate.chain[-1][0] or '미확인') if coordinate.chain else coordinate.unit
    family = unit.get('family', '')
    return {'kr_article': '조', 'circled': '항', 'hangul_dot': '목',
            'dot_number:1': '호'}.get(family, family.removeprefix('kr_') or '미확인')


def node_label(matcher, did, uid):
    unit = matcher.units[(did, uid)]
    coordinate = matcher.stored_coordinates.get((did, uid))
    return {'unit_id': uid, 'level': node_level(matcher, did, uid),
        'surface': unit.get('surface', ''), 'title': unit.get('title', '')[:160],
        'coordinate': coordinate.canonical_surface() if coordinate else None,
        'coordinate_scope': unit.get('coordinate_scope') or 'unknown'}


def node_path(matcher, did, uid):
    """The actual stored parent chain, including containers above an article."""
    from .errors import ContractError
    path, seen = [], set()
    while uid is not None:
        uid = str(uid)
        if uid in seen or (did, uid) not in matcher.units:
            raise ContractError('missing/cyclic stored structure parent')
        seen.add(uid)
        path.append(node_label(matcher, did, uid))
        uid = matcher.units[(did, uid)].get('parent')
    return list(reversed(path))


def document_tree(matcher, did):
    """Index the bound tree once per immutable document; mutable fixtures rescan."""
    prepared = getattr(matcher, 'prepared_structure', None)
    reusable = prepared is not None and matcher.units is prepared['units']
    guard = prepared['lock'] if reusable else threading.Lock()
    with guard:
        cache = prepared.setdefault('document_structure', {}) if reusable else {}
        if did in cache:
            return cache[did]
        keys = prepared['unit_index'].get(did, ()) if reusable else (
            key for key in matcher.units if key[0] == did)
        children, coordinates, levels, edges, branches = defaultdict(list), defaultdict(list), {}, set(), defaultdict(int)
        nodes = []
        for _, uid in keys:
            unit = matcher.units[(did, uid)]
            parent = unit.get('parent')
            children[str(parent) if parent is not None else None].append(uid)
            nodes.append(uid)
        for siblings in children.values():
            siblings.sort(key=lambda uid: (matcher.units[(did, uid)].get('span', [0])[0], uid))
        for uid in sorted(nodes, key=lambda uid: (matcher.units[(did, uid)].get('span', [0])[0], uid)):
            unit = matcher.units[(did, uid)]
            row = node_label(matcher, did, uid)
            branch, level = row['coordinate_scope'], row['level']
            branches[branch] += 1
            entry = levels.setdefault(level, {'level': level, 'count': 0, 'examples': []})
            entry['count'] += 1
            if len(entry['examples']) < 2:
                entry['examples'].append({k: row[k] for k in ('surface', 'coordinate', 'title', 'coordinate_scope')})
            parent = unit.get('parent')
            if parent is not None and (did, str(parent)) in matcher.units:
                edges.add((node_level(matcher, did, str(parent)), level))
            if row['coordinate'] and unit.get('coordinate_binding', {}).get('mode') != 'unresolved':
                coordinates[(branch, row['coordinate'])].append(uid)
        tree = {'children': dict(children), 'coordinates': dict(coordinates), 'nodes': nodes,
            'shape': {'levels': list(levels.values()),
                'parent_child_levels': [{'parent': a, 'child': b} for a, b in sorted(edges)],
                'branches': [{'coordinate_scope': b, 'node_count': n} for b, n in sorted(branches.items())],
                'node_count': len(nodes), 'root_count': len(children.get(None, []))}}
        if reusable:
            cache[did] = tree
        return tree


def tree_row(matcher, did, uid, tree):
    row = {'kind': 'structure', 'document_id': did, 'document_name': matcher.documents[did],
           **node_label(matcher, did, uid), 'path': node_path(matcher, did, uid),
           'child_total': len(tree['children'].get(uid, [])), 'content_read': False}
    ids = matcher._unit_sources(did, uid)
    row['original_count'] = len(ids)
    row['source_binding_unique'] = len(ids) == 1 and matcher.sources.get(ids[0], {}).get('document_id') == did
    row['source_id'] = ids[0] if row['source_binding_unique'] else None
    row['ambiguous'] = bool(row['coordinate'] and len(tree['coordinates'].get(
        (row['coordinate_scope'], row['coordinate']), [])) != 1)
    # Containers navigate to children. Article/provision originals keep the
    # existing exact scope and source checks; an outline is never evidence.
    coordinate = matcher.stored_coordinates.get((did, uid))
    row['readable'] = bool(coordinate and coordinate.unit == '조'
        and coordinate_index(matcher).get((did, coordinate.canonical_surface())) == [uid]
        and row['source_binding_unique'] and not row['ambiguous'])
    return row


def document_structure(matcher, scope, document_id, *, unit_id=None, offset=0, limit=8):
    """Shape, current path and paged direct children, without reading any body."""
    if document_id not in scope:
        raise ValueError('structure target outside request scope')
    if unit_id is not None:
        unit_id = str(unit_id)
        if (document_id, unit_id) not in matcher.units:
            raise ValueError('unknown stored structure node')
    tree = document_tree(matcher, document_id)
    children = tree['children'].get(unit_id, [])
    path = node_path(matcher, document_id, unit_id) if unit_id is not None else []
    return {'contract': 'stored-document-structure-v1', 'document_id': document_id,
        'document_name': matcher.documents[document_id], 'shape': tree['shape'],
        'focus': node_label(matcher, document_id, unit_id) if unit_id is not None else None,
        'path': path, 'parent_unit_id': path[-2]['unit_id'] if len(path) > 1 else None,
        'children': [tree_row(matcher, document_id, uid, tree) for uid in children[offset:offset+limit]],
        'offset': offset, 'total': len(children),
        'next_offset': offset+limit if offset+limit < len(children) else None,
        'search_fields': ['coordinate', 'title', 'coordinate_scope'],
        'search_rule': 'Fields match stored structure in this document; coordinate_scope defaults to body. '
                       'Titles and paths are navigation only. No automatic fulltext fallback on a miss.',
        'navigation_hint_only': True, 'citation_eligible': False}


def filtered_catalogue(matcher, scope, did, filters, offset, limit):
    """Typed coordinate/title filters against stored nodes of one bound document."""
    if did is None or did not in scope:
        raise ValueError('typed structure lookup requires a scoped document')
    tree = document_tree(matcher, did)
    branch = filters.get('coordinate_scope') or 'body'
    coordinate, title = filters.get('coordinate', '').strip(), filters.get('title', '').strip()
    if not coordinate and not title:
        raise ValueError('typed structure lookup requires a coordinate or title')
    mentions = find_coordinates(coordinate) if coordinate else []
    valid = not coordinate or (len(mentions) == 1 and not coordinate[:mentions[0].start].strip()
                              and not coordinate[mentions[0].end:].strip())
    locator = mentions[0].coordinate.canonical_surface() if valid and mentions else None
    candidates = tree['coordinates'].get((branch, locator), []) if coordinate else tree['nodes']
    rows = [tree_row(matcher, did, uid, tree) for uid in candidates
            if valid and (matcher.units[(did, uid)].get('coordinate_scope') or 'unknown') == branch
            and (not title or name_key(title) in name_key(matcher.units[(did, uid)].get('title', '')))]
    rows.sort(key=lambda row: (matcher.units[(did, row['unit_id'])].get('span', [0])[0], row['unit_id']))
    diagnostic = None
    if not valid:
        diagnostic = failure('INVALID_COORDINATE')
    elif branch not in {b['coordinate_scope'] for b in tree['shape']['branches']}:
        diagnostic = failure('MISSING_STRUCTURE_BRANCH')
    elif not rows:
        unresolved = coordinate and any(c and c.canonical_surface() == locator
            and (matcher.units[(d, u)].get('coordinate_scope') or 'unknown') == branch
            and matcher.units[(d, u)].get('coordinate_binding', {}).get('mode') == 'unresolved'
            for (d, u), c in matcher.stored_coordinates.items() if d == did)
        diagnostic = failure('UNRESOLVED_COORDINATE_BINDING' if unresolved else
            'TITLE_FILTER_MISMATCH' if coordinate and candidates and title else
            'MISSING_COORDINATE' if coordinate else 'MISSING_TITLE')
    return lookup_report({'contract': 'stored-structure-catalogue-v1', 'queries': [], 'structure_filter': filters,
        'document_id': did, 'offset': offset, 'total': len(rows), 'items': rows[offset:offset+limit],
        'next_offset': offset+limit if offset+limit < len(rows) else None,
        'resolutions': [{'status': 'MATCH' if rows and not any(r['ambiguous'] for r in rows) else 'MISS',
                         'reason': 'STORED_STRUCTURE_FILTER' if valid else 'INVALID_COORDINATE_FILTER',
                         **({'failure': diagnostic} if diagnostic else {})}], 'failure': diagnostic,
        'navigation_hint_only': True, 'citation_eligible': False})

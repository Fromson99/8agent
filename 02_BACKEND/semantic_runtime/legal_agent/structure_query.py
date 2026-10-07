"""Resolve explicit document/article pairs using the bound original structure only."""
import re
import threading
from collections import defaultdict

from lawrag.core.legal_coordinate import find_coordinates

_LOCK = threading.Lock()
_COORDINATES = None
_INDEX = None


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


def resolve(question, matcher, scope):
    """All requested pairs must be unique and readable; partial hits never narrow scope."""
    result = {'status': 'MISS', 'pairs': [], 'source_ids': [], 'reason': 'NO_EXPLICIT_PAIR'}
    coordinates = find_coordinates(question)
    if not getattr(matcher, 'stored_coordinates', None):
        return result
    if (re.search(r'부칙|별표|별지|부터|내지|[~～]', question)
            or any(coordinates[i].start < coordinates[i-1].end for i in range(1, len(coordinates)))):
        return {**result, 'reason': 'RANGE_OR_NON_BODY'}
    hits = [h for h in matcher.document_names.match(question) if h['key'] in matcher.title_keys]
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

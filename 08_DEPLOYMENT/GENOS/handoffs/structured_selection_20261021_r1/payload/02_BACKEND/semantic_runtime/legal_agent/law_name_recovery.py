"""Title-only recovery of a failed document/article pair; never source evidence."""
from copy import deepcopy
import re

from lawrag.core.legal_coordinate import find_coordinates
from ..contracts import digest
from ..document_roles import role_of_metadata
from ..fulltext import question_terms
from ..navigation_match import norm
from .errors import ContractError, ProposalError

CONTRACT = 'law-name-recovery-v1'
RECOVERABLE = {'MISSING_DOCUMENT', 'AMBIGUOUS_DOCUMENT', 'MISSING_COORDINATE', 'MISSING_PARENT', 'MISSING_SELECTION_LEVEL'}
GENERIC = {'법', '법률', '시행령', '시행규칙', '규정', '규칙', '관한', '대한', '및', '등'}
PROMPT = '''law_name_recovery는 법령명+조문 조회 실패 뒤 조문 조건을 빼고 법령 이름만 검색한 후보다.
name_query와 실제 title/일치 단서를 보고 의도한 법령을 고른다. retry_action(RETRY_LAW_STRUCTURE)은 선택한 법령에서 보존된 원래 조문을 다시 조회한다.
조문 번호를 다시 만들거나 유사 법령을 자동 정답으로 취급하지 않는다. 재조회 결과의 read_action으로 원문을 읽은 뒤 채택한다.
적합한 후보가 없거나 다시 못 찾으면 미확인으로 남기고 다른 허용 조사 또는 부분 종료를 선택한다. 이름 후보는 원문도 적용 근거도 아니다.'''


def metadata(matcher, did):
    context = matcher.document_context.get(did, {})
    title = context.get('document_title') or matcher.documents[did]
    aliases = list(getattr(matcher, 'document_aliases', {}).get(did, ()))
    return title, aliases, digest([did, title, aliases, context])


def candidates(matcher, scope, name, limit=8):
    """Match content morphemes only against permitted titles/registered aliases."""
    terms = set(question_terms(name)) - GENERIC
    query = norm(name)
    if not query or not terms:
        return [], 0
    rows = []
    for did in sorted(set(scope) & set(matcher.documents)):
        context = matcher.document_context.get(did, {})
        if role_of_metadata(context) != 'body':
            continue
        title, aliases, fingerprint = metadata(matcher, did)
        if not context.get('document_title') and any(x in title for x in ('>', '/', '\\')):
            continue
        best = None
        for label in [title, *aliases]:
            if not norm(label):
                continue
            label_terms = set(question_terms(label)) - GENERIC
            matched = terms & label_terms
            exact = query == norm(label)
            partial = query in norm(label) or norm(label) in query
            if not exact and not partial and not matched:
                continue
            score = (int(exact), int(partial), len(matched) / max(1, len(terms)),
                     len(matched) / max(1, len(label_terms)))
            if best is None or score > best[0]:
                best = (score, {'document_id': did, 'title': title,
                    'matched_label': label, 'matched_terms': sorted(matched),
                    'match_kind': 'EXACT_NAME' if exact else 'PARTIAL_NAME' if partial else 'TITLE_TERMS',
                    'metadata_hash': fingerprint, 'citation_eligible': False})
        if best:
            rows.append(best)
    rows.sort(key=lambda r: (tuple(-n for n in r[0]), r[1]['title'], r[1]['document_id']))
    return [row for _, row in rows[:limit]], len(rows)


def attach(page, matcher, scope):
    """A single body locator can be retried; ambiguous ranges stay unmodified."""
    if page.get('offset') or page.get('name_retry'):
        return page
    failed = [r for r in page.get('resolutions', []) if r.get('status') == 'MISS']
    if any(r.get('status') == 'MATCH' for r in page.get('resolutions', [])):
        return page
    codes = {r.get('failure', {}).get('code') for r in failed if r.get('failure')}
    if page.get('failure'):
        codes.add(page['failure']['code'])
    if not codes or not codes <= RECOVERABLE:
        return page
    did = page.get('document_id')
    filters = deepcopy(page.get('structure_filter'))
    queries = page.get('queries', [])
    if filters:
        if did not in scope or filters.get('coordinate_scope', filters.get('selection', {}).get('coordinate_scope')) not in ('', 'body'):
            return page
        name = metadata(matcher, did)[0]
        locator = filters.get('coordinate')
    else:
        if len(queries) != 1:
            return page
        query = queries[0]
        if re.search(r'부터|내지|[~～]|부칙|별표|별지|서식', query):
            return page
        mentions = find_coordinates(query)
        if len(mentions) != 1:
            return page
        mention = mentions[0]
        name = query[:mention.start].strip(' \t\n「」『』“”\"\'')
        if not name and did in scope:
            name = metadata(matcher, did)[0]
        if not name:
            return page
        locator = mention.surface
        filters = {'coordinate': locator, 'title': '', 'coordinate_scope': 'body'}
    if 'selection' not in filters:
        mentions = find_coordinates(locator)
        if len(mentions) != 1 or mentions[0].coordinate.unit != '조':
            return page
        if locator[:mentions[0].start].strip() or locator[mentions[0].end:].strip():
            return page
    items, total = candidates(matcher, scope, name)
    value = {'contract': CONTRACT, 'name_query': name, 'original_queries': list(queries),
        'original_document_id': did, 'original_failure': deepcopy(page.get('failure') or
            next((r['failure'] for r in failed if r.get('failure')), None)),
        'structure_filter': filters, 'candidates': items, 'total_candidates': total,
        'omitted_candidates': max(0, total - len(items)), 'citation_eligible': False,
        'no_match_means': '이 이름 검색에서 후보를 찾지 못했으며 관련 법령 부재의 증명이 아닙니다.'}
    value['recovery_id'] = digest(value)
    return {**page, 'law_name_recovery': value}


def retry_key(recovery, did):
    filters = recovery['structure_filter']
    if 'selection' in filters:
        return digest([norm(recovery['name_query']), filters['selection'], did])
    coordinate = find_coordinates(filters['coordinate'])[0].coordinate.canonical_surface()
    return digest([norm(recovery['name_query']), coordinate, norm(filters['title']),
                   filters['coordinate_scope'] or 'body', did])


def validate_retry(inv, identity):
    recovery = inv.p['structure_page'].get('law_name_recovery')
    if not recovery or recovery['recovery_id'] != identity['recovery_id']:
        raise ProposalError('stale law name recovery selection')
    if recovery['recovery_id'] != digest({k: v for k, v in recovery.items() if k != 'recovery_id'}):
        raise ContractError('law name recovery hash mismatch')
    did = identity['document_id']
    from . import query_scope as qs
    if did not in qs.documents(inv.s):
        raise ContractError('law name recovery outside search scope')
    row = next((r for r in recovery['candidates'] if r['document_id'] == did), None)
    if not row:
        raise ProposalError('law name candidate was not offered')
    if metadata(inv.s.matcher, did)[2] != row['metadata_hash']:
        raise ContractError('law name candidate metadata changed')
    if retry_key(recovery, did) in inv.p.get('law_name_retry_history', []):
        raise ProposalError('unchanged law name and coordinate retry')
    if len(inv.p['structure_search_history']) >= inv.policy['search_rounds']:
        raise ProposalError('structure lookup rounds exhausted')
    return recovery

"""Bounded document term hints and acquired-source anchors, never legal adoption."""
from copy import deepcopy
import json
import sqlite3
from ..contracts import digest
from ..fulltext import _search_forms
from .errors import ContractError, BudgetExhausted, ToolExecutionError

VERSION = 'connected-exploration-v2'
DOCUMENTS = 4
ARTICLES = 6
TERMS = 4
CONTEXT_CHARS = 10000


def diverse_reference_cards(cards, limit=16):
    first, rest, seen = [], [], set()
    for card in sorted(cards, key=lambda c: c['already_read']):
        key = (card['target']['source_id'], card['direction'])
        (rest if key in seen else first).append(card)
        seen.add(key)
    return (first+rest)[:limit]


def offer_reference_reads(inv, references, offer):
    for card in references.get('dependency_cards', []):
        if card['already_read']:
            continue
        target = card['target']
        # The verified reference catalog owns endpoint validation. Reading the
        # article remains subject to the existing exact scope/budget checks.
        identity = {k: target[k] for k in ('source_id', 'document_id', 'unit_id')}
        card['read_action'] = offer('READ_ARTICLES', identity,
            target['document_name']+' '+target['heading']+' 연결 원문 읽기')
        card['document_id'] = target['document_id']
        card['document_name'] = target['document_name']
        card['heading'] = target['heading']
        card['preview_is_reference_witness'] = True


def anchors(inv):
    """Focus is a display position; acquired, unexcluded originals remain roots."""
    records = inv.read_records()
    known = {r['source_id'] for r in records.values()}
    order = [inv.p['groups'][g]['source_id'] for g in inv.p.get('window_groups', []) if g in inv.p['groups']]
    order += [inv.p['groups'][g]['source_id'] for g in inv.p.get('system_definition_seed', {}).get('acquired_groups', []) if g in inv.p['groups']]
    order += [r['source_id'] for r in records.values()]
    return list(dict.fromkeys(sid for sid in order if sid in known))


def term_keys(inv):
    labels = []
    for item in inv.p.get('definition_matches', []):
        d = inv.s.tools.definitions[item['definition_id']]
        if d['document_id'] not in inv.s.scope:
            raise ContractError('term exploration definition outside request scope')
        label = d.get('label') or d['key']
        # definition_matches already verifies the request term span.
        labels.append(label)
    if not labels:
        for tid in inv.s.tools.match(inv.question):
            label = inv.s.tools.terms[tid]['label']
            if ''.join(label.split()) in ''.join(inv.question.split()) and len(label) >= 2:
                labels.append(label)
    return sorted(set(labels), key=lambda x: (-len(x), x))[:TERMS]



def query_forms(labels):
    # Each label stays a phrase. Splitting into OR tokens would turn a specific
    # compound into broad matches such as every occurrence of "비율".
    return list(dict.fromkeys(form for label in labels if (form := _search_forms(label).strip())))


def state(inv):
    binding = digest([VERSION, inv.p['binding'], sorted(inv.s.scope), inv.s.context.query['generation_id']])
    value = inv.p.setdefault('document_term_exploration', {'version': VERSION, 'binding': binding, 'documents': {}})
    if value.get('version') != VERSION or value.get('binding') != binding:
        raise ContractError('document term exploration binding changed')
    return value


def page_reason(inv, ident):
    value = state(inv)
    d = value['documents'].get(ident.get('document_id'))
    if (not d or d['status'] != 'READY' or not d.get('next_cursor')
            or ident.get('binding') != d['binding'] or ident.get('cursor') != d['next_cursor']):
        return 'STALE_TERM_CURSOR'
    return None


def load_page(inv, did, entry, cursor=None):
    from . import query_scope as qs
    if did not in qs.documents(inv.s):
        entry.update(status='PARTIAL',reason='OUTSIDE_DIRECT_SEARCH_SCOPE',absence_proven=False)
        return
    if did not in inv.s.scope:
        raise ContractError('term exploration document outside request scope')
    if entry['status'] in ('FAILED', 'PARTIAL'):
        return  # No blind retry of an unchanged failed catalogue.
    if inv.left() <= max(1, inv.s.profile.get('selection_time_reserve_seconds', 1)):
        entry.update(status='PARTIAL', reason='FINALIZATION_TIME_RESERVE')
        inv.save()
        return
    if not entry['query_terms']:
        entry.update(status='PARTIAL', reason='NO_INDEXABLE_TERM', absence_proven=False)
        inv.save()
        return
    entry['status'] = 'STARTED'
    inv.save()
    try:
        # IDs of one authorized document only. Oracle's source adapter performs
        # this lookup remotely; no full corpus catalogue or body restoration.
        allowed = inv.s.tools.sources.ids_for_documents([did])
        if not hasattr(allowed, 'document_ids'):
            allowed = set(allowed)
        page = inv.idx.article_groups_page(inv.db, entry['query_terms'], did, allowed, cursor=cursor, limit=ARTICLES, **qs.fulltext(inv.s))
        rows = []
        for item in page['items']:
            sid = item['source_id']
            source = inv.s.tools.sources[sid]
            if sid not in allowed or source['document_id'] != did:
                raise ContractError('term result outside selected document')
            hitpage = inv.idx.hit_page(inv.db, entry['query_terms'], sid, allowed, limit=1, **qs.fulltext(inv.s))
            preview = hitpage['items'][0] if hitpage['items'] else None
            if preview and (preview['source_id'] != sid or preview['document_id'] != did):
                raise ContractError('term preview identity differs from source')
            rows.append({'source_id': sid, 'document_id': did, 'document_name': source['document_name'],
                'heading': source.get('heading', ''), 'unit_id': source['unit_id'],
                'matched_units': item['unit_count'], 'preview': preview['text'][:240] if preview else '',
                'preview_unit_id': preview.get('unit_id') if preview else None,
                'source_artifact_sha256': source['source_artifact_sha256'], 'citation_eligible': False})
        entry.update(status='READY', items=rows, total=page['total'], cursor=deepcopy(cursor),
            next_cursor=page['next_cursor'], pages_read=entry.get('pages_read', 0)+1)
        inv.s.repo.event('DOCUMENT_TERM_CANDIDATES', {'document_id': did, 'terms': entry['terms'], 'query_terms':entry['query_terms'],
            'source_ids': [r['source_id'] for r in rows], 'total': page['total'], 'cursor': cursor,
            'next_cursor': page['next_cursor'], 'binding': entry['binding'], 'original_acquired': False})
    except (BudgetExhausted, ToolExecutionError, TimeoutError, sqlite3.OperationalError) as error:
        if isinstance(error, sqlite3.OperationalError) and not any(x in str(error).lower() for x in ('interrupt', 'locked', 'busy')):
            raise
        entry.update(status='PARTIAL' if isinstance(error, BudgetExhausted) else 'FAILED',
            reason=type(error).__name__, absence_proven=False)
        inv.s.repo.event('DOCUMENT_TERM_CANDIDATES_INCOMPLETE', {'document_id': did, 'status': entry['status'], 'error_type': type(error).__name__, 'absence_proven': False})
    finally:
        inv.save()


def advance(inv, ident):
    reason = page_reason(inv, ident)
    if reason:
        raise ContractError(reason)
    entry = state(inv)['documents'][ident['document_id']]
    load_page(inv, ident['document_id'], entry, ident['cursor'])


def menu(inv, offer):
    if not inv.modern:
        return None
    labels = term_keys(inv)
    if not labels:
        return None
    # A definition READ or an explicitly located/opened document establishes a
    # scope. The initial global law results alone do not trigger body expansion.
    docs = [r['document_id'] for r in inv.read_records().values()]
    location = inv.p.get('structure_location') or {}
    if location.get('document_id'):
        docs.insert(0, location['document_id'])
    opened = inv.p.get('opened_law')
    if opened in inv.p['laws']:
        docs.insert(0, inv.p['laws'][opened]['document_id'])
    docs = list(dict.fromkeys(docs))
    if not docs:
        return None
    saved = state(inv)
    forms = query_forms(labels)
    result = {'contract': VERSION, 'documents': [], 'omitted_documents': max(0, len(docs)-DOCUMENTS),
        'meaning': '선택한 문서 안의 용어 사용 위치다. 미리보기는 원문 확보나 적용 판단이 아니다. 필요한 항을 읽고 기존 원문과 함께 판단한다.'}
    for did in docs[:DOCUMENTS]:
        if did not in inv.s.scope:
            raise ContractError('term exploration scope changed')
        binding = digest([saved['binding'], did, labels, forms, inv.idx.manifest['index_sha256']])
        entry = saved['documents'].setdefault(did, {'binding': binding, 'terms': labels, 'query_terms':forms, 'status': 'NEW', 'items': [], 'next_cursor': None})
        if entry['binding'] != binding:
            raise ContractError('term exploration query changed')
        if entry['status'] == 'NEW':
            load_page(inv, did, entry)
        elif entry['status'] == 'STARTED':
            # Interrupted query outcome is unknown; originals stay available.
            entry.update(status='PARTIAL', reason='INTERRUPTED_CATALOGUE', absence_proven=False)
            inv.save()
        row = {'document_id': did, 'terms': labels, 'query_terms':forms, 'status': entry['status'], 'total': entry.get('total'), 'items': [], 'reason': entry.get('reason')}
        for item in entry['items']:
            source = inv.s.tools.sources[item['source_id']]
            if source['document_id'] != did or source['source_artifact_sha256'] != item['source_artifact_sha256']:
                raise ContractError('term candidate source binding changed')
            shown = deepcopy(item)
            row['items'].append(shown)
        if len(json.dumps({**result, 'documents': result['documents']+[row]}, ensure_ascii=False)) + 512*(len(row['items'])+1) > CONTEXT_CHARS:
            result['omitted_documents'] += 1
            continue
        for shown in row['items']:
            identity = {k: shown[k] for k in ('document_id', 'source_id', 'unit_id')}
            shown['read_action'] = offer('READ_ARTICLES', identity, shown['document_name']+' '+shown['heading']+' 용어 사용 원문 읽기')
        if entry['status'] == 'READY' and entry.get('next_cursor'):
            row['next_action'] = offer('NEXT_TERM_MATCHES', {'document_id': did, 'binding': binding, 'cursor': entry['next_cursor']}, '이 문서의 용어 사용 조항 더 보기')
        result['documents'].append(row)
    return result


def current_actions(data):
    result=[]
    for card in data.get('references',{}).get('dependency_cards',[]):
        if card.get('read_action'):result.append(card['read_action'])
    for doc in data.get('document_term_candidates',{}).get('documents',[]):
        result.extend(r['read_action'] for r in doc['items'] if r.get('read_action'))
        if doc.get('next_action'):result.append(doc['next_action'])
    return result

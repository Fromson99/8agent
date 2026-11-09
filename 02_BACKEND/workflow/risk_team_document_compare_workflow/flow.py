"""문서 대사: one internal document, every stored row, saved after each unit.

There is no request time limit and no model-call limit (manifest execution
policy). Each physical model call still has its own transport timeout, an
unknown provider outcome is never re-sent, and a bounded correction failure
holds only that group or unit. A stopped run is continued with "계속".
"""
from collections import Counter
from copy import deepcopy
import json
import re
from ..contracts import WorkflowError, digest
from . import selection, group_review, compare_unit
from .report import build

POLICY = 'document-compare-v2'
QUESTION_CHARS = 4000      # internal original text sent to one external search
SOURCE_CHARS = 80000       # JSON size of the originals in one comparison call (context bound)
ARTICLE_CHARS = 4000       # a found external article up to this size is compared whole
HINT_CHARS = 500           # one search hint (native task contract)
SHARED_CHARS = 16000      # JSON size of the neighbour units' articles added to one comparison
# Structural numbering of the internal document ("제2-3조", "제3장", "①", "(1)", "1.", "가.").
# As a search word it finds external articles that only share the number.
NUMBERING = re.compile(r'제\s*\d+(?:\s*-\s*\d+)*\s*(?:편|장|절|관|조|항|호|목)(?:\s*의\s*\d+)?'
                       r'|[\u2460-\u2473]|\(\s*\d+\s*\)|(?<!\w)(?:\d+|[가나다라마바사아자차카타파하])\s*[.)](?=\s|$)')


def _log():
    from semantic_runtime import observability as obs
    return obs, obs.get_logger('workflow.document_compare')


def evidence(port, ids):
    """Originals recorded (and verified) when read; the whole run is re-verified at REPORT."""
    out = []
    for ident in ids:
        e = port.session.repo.evidence(ident)
        out.append({'evidence_id': e['evidence_id'], 'side': port.categories[e['document_id']],
                    'document_id': e['document_id'],
                    'metadata': {'document_name': e['metadata'].get('document_name'), 'heading': e['metadata'].get('heading', '')},
                    'spans': [{'text': s['text']} for s in e['spans']]})
    return out


def _store_text(port, did):
    store = port.session.store

    def text(segments):
        rows = store.sources(did, [s['block_id'] for s in segments])
        return ''.join(row['text'][s['start_cp']:s['end_cp']] for s, row in zip(segments, rows))
    return text


def _coverage(port, ids, segments):
    """Evidence IDs whose read spans cover these segments exactly, or None."""
    spans = {}
    for ident in ids:
        for span in port.session.repo.evidence(ident)['spans']:
            spans.setdefault(str(span['block_id']), []).append((span['start_cp'], span['end_cp'], ident))
    used = set()
    for segment in segments:
        position, end = segment['start_cp'], segment['end_cp']
        for start, stop, ident in sorted(spans.get(str(segment['block_id']), [])):
            if start <= position < stop:
                used.add(ident)
                position = min(stop, end)
            if position >= end:
                break
        if position < end:
            return None
    return used


def _save(ctx, state):
    ctx.repo.save(state)


def execute(ctx):
    state = ctx.repo.state()['checkpoint']
    while True:
        stage = state['stage']
        if stage == 'INTAKE':
            intake(ctx, state)
        elif stage == 'INVENTORY':
            inventory(ctx, state)
        elif stage == 'GROUPS':
            for group in state['inventory']['groups']:
                if state['groups'][group['group_id']]['status'] not in ('done', 'held'):
                    process_group(ctx, state, group)
            state['stage'] = 'REPORT'
        elif stage == 'REPORT':
            ctx.rag.port.verify_all()
            result = build(ctx, state)
            state['stage'] = 'END'
            return ctx.repo.save(state, status=result['status'], result=result)
        elif stage == 'END':
            return ctx.repo.state()['result']
        else:
            raise ValueError('unknown document comparison stage')
        _save(ctx, state)


def intake(ctx, state):
    decision = selection.decide(ctx, ctx.request['question'])
    if decision[0] == 'ask':
        candidates = [{'number': n + 1, 'document_id': r['document_id'], 'name': r['name']} for n, r in enumerate(decision[1])]
        shown = [{'document_id': c['document_id'], 'name': c['name']} for c in candidates]
        selection.save(ctx, candidates=shown, candidates_hash=digest(shown))
        state['selection'] = {'status': 'NEEDS_DOCUMENT', 'reason': decision[2], 'candidates': candidates}
        state['stage'] = 'REPORT'
    elif decision[0] == 'document':
        state['selection'] = {'status': 'SELECTED'}
        state['document'] = {'document_id': decision[1]['document_id'], 'name': decision[1]['name']}
        state['stage'] = 'INVENTORY'
    else:
        resume(ctx, state, decision[1])


def _groups(ctx, did):
    from semantic_runtime.basis_links.reading_groups import build as reading_groups
    ctx.context.remaining()
    ctx.rag.port.session.repo.reserve_tool()
    # Every stored text block exactly once, in rows; the builder checks coverage.
    return reading_groups(ctx.rag.port.session.store, did)['groups']


def inventory(ctx, state):
    did = state['document']['document_id']
    groups = _groups(ctx, did)
    rows = sum(len(g['rows']) for g in groups)
    state['inventory'] = {'policy': POLICY, 'hash': digest(groups), 'groups': groups, 'rows': rows}
    state['groups'] = {g['group_id']: {'status': 'pending'} for g in groups}
    state.setdefault('named_external', [])
    state.setdefault('carry_evidence', [])
    selection.save(ctx, last_run={'run_id': ctx.context.run_id, 'document_id': did, 'status': 'running'})
    obs, log = _log()
    obs.event(log, 'document_compare.inventory', document_id=did, groups=len(groups), rows=rows)
    state['stage'] = 'GROUPS'


def resume(ctx, state, last):
    """Carry finished groups of a stopped run of the same document and session."""
    old = ctx.continuation(last['run_id'])
    if old.get('document', {}).get('document_id') != last['document_id'] or 'inventory' not in old:
        raise WorkflowError('DOCUMENT_CONTINUATION_BINDING', '이어 갈 문서 대사의 기록이 맞지 않습니다.', 409)
    state['selection'] = {'status': 'CONTINUED', 'continuation_of': last['run_id']}
    state['document'] = deepcopy(old['document'])
    if old['request'].get('workflow_id') != ctx.request['workflow_id']:
        raise WorkflowError('DOCUMENT_CONTINUATION_BINDING', '다른 업무의 실행은 이어 갈 수 없습니다.', 409)
    if all(v['status'] == 'done' for v in old['groups'].values()):
        state['selection']['status'] = 'ALREADY_COMPLETE'
        state['stage'] = 'REPORT'
        return
    if digest(_groups(ctx, state['document']['document_id'])) != old['inventory']['hash']:
        raise WorkflowError('DOCUMENT_CHANGED', '문서 판본이 바뀌어 이어 갈 수 없습니다. 문서 이름으로 새로 시작해 주세요.', 409)
    port = ctx.rag.port
    # Only verified originals are imported; the earlier usage stays with that run.
    port.session.repo.record_observation({'tool': 'document_compare_continuation', 'args': {'parent_run': last['run_id']}},
        {'status': 'OK', 'reused': True, 'parent_usage': old['usage']}, old['evidence'], verify=port.session.verify)
    state['inventory'] = deepcopy(old['inventory'])
    state['groups'] = {gid: deepcopy(v) if v['status'] == 'done' else {'status': 'pending'} for gid, v in old['groups'].items()}
    state['named_external'] = list(old.get('named_external', []))
    state['carry_evidence'] = list(old.get('carry_evidence', []))
    state['continuation_of'] = last['run_id']
    selection.save(ctx, last_run={'run_id': ctx.context.run_id, 'document_id': state['document']['document_id'], 'status': 'running'})
    state['stage'] = 'GROUPS'


def process_group(ctx, state, group):
    gid, port = group['group_id'], ctx.rag.port
    g = state['groups'][gid]
    did = state['document']['document_id']
    refs = group_review.refs(group)
    if g['status'] == 'pending':
        handle = port.session.handle('U', group['node'])
        ids, cursor = set(g.get('internal', [])), g.get('cursor')
        while True:
            result = ctx.rag.source_call({'operation': 'read_node', 'side': 'internal', 'args': {'node': handle, 'cursor': cursor},
                                          'reason': '문서 대사 원문 읽기'}, call_id='document-read:' + digest([gid, cursor]))
            ids |= set(result.get('evidence_ids', []))
            if result['status'] not in ('OK', 'TRUNCATED'):
                g.update(status='held', reason='내규 원문 읽기를 완료하지 못했습니다(' + str(result.get('error_code') or result['status']) + ').')
                return _save(ctx, state)
            cursor = result.get('next_cursor')
            g.update(internal=sorted(ids), cursor=cursor)
            _save(ctx, state)
            if not cursor:
                break
        rows = {}
        for ref, row in zip(refs, group['rows']):
            used = _coverage(port, g['internal'], row['segments'])
            if used is None:
                g.update(status='held', reason='읽은 원문이 묶음의 모든 행을 덮지 못했습니다.')
                return _save(ctx, state)
            rows[ref] = sorted(used)
        text = _store_text(port, did)
        # Recorded for the report only; a unit's search is narrowed by names in its own text.
        found = selection_external(port, '\n'.join(text(r['segments']) for r in group['rows']))
        state['named_external'] = list(dict.fromkeys(state['named_external'] + found))
        g.update(status='read', row_evidence=rows)
        _save(ctx, state)
    if g['status'] == 'read':
        text = _store_text(port, did)

        def accounted(value):
            report = group_review.accounting(value, group)
            if not group_review.complete(report):
                raise ValueError('every R number must be placed exactly once; missing: %s; placed more than once: %s'
                                 % (', '.join(report['missing']) or '-', ', '.join(report['duplicated']) or '-'))
        try:
            value = ctx.model.decide('GROUP_READ', group_review.payload(state['document']['name'], group, text),
                                     group_review.schema(group), group_review.SYSTEM, accounted)
        except WorkflowError as exc:
            if exc.code != 'WORKFLOW_REPAIR_EXHAUSTED':
                raise
            g.update(status='held', reason='행 정리 응답이 모든 행을 한 번씩 배치하지 못했습니다(보완 1회 후).')
            return _save(ctx, state)
        labels = dict(zip(refs, group['rows']))
        g['placement'] = {'not_target': value['not_target'], 'hold': value['hold']}
        g['units'] = [{'unit_id': gid[:16] + '-U%d' % (n + 1), 'label': u['label'], 'summary': u['summary'], 'refs': u['rows'],
                       'row_labels': [labels[r]['label'] for r in u['rows']],
                       'internal': sorted({e for r in u['rows'] for e in g['row_evidence'][r]}), 'status': 'pending'}
                      for n, u in enumerate(value['units'])]
        g['status'] = 'placed'
        _save(ctx, state)
    # Every unit of the group searches first, so each comparison can also use the
    # external articles its neighbours found (same chapter, often the same rule).
    for unit in g['units']:
        if unit['status'] != 'done' and 'external' not in unit:
            search_unit(ctx, state, group, unit)
    for unit in g['units']:
        if unit['status'] != 'done':
            process_unit(ctx, state, group, unit)
            state['carry_evidence'] = sorted(set(state['carry_evidence']) | set(unit['internal'])
                                             | set(unit.get('external', [])) | set(unit.get('articles') or []) | set(unit.get('cited') or []))
            _save(ctx, state)
    g['status'] = 'done'
    _save(ctx, state)
    obs, log = _log()
    done = sum(v['status'] in ('done', 'held') for v in state['groups'].values())
    units = [u for v in state['groups'].values() for u in v.get('units', []) if u['status'] == 'done']
    different = sum(u['verdict'] in ('CONFLICT', 'POSSIBLE_GAP', 'ADDITIONAL_INTERNAL') for u in units)
    # Display-only journal receipt for the chat progress line; no state is read back from it.
    ctx.repo.work.event('DOCUMENT_COMPARE_PROGRESS', {'done': done, 'total': len(state['groups']),
                                                      'units': len(units), 'different': different})
    obs.event(log, 'document_compare.group.completed', document_id=did, group=done, total=len(state['groups']),
              units=len(g['units']))


def plain(text):
    """Words of a name or heading without the internal document's numbering."""
    return re.sub(r'\s+', ' ', NUMBERING.sub(' ', text or '')).strip(' ·-:()[]「」')


def search_hints(unit):
    """First search words of one unit's external search; no model call.

    The unit's name without the internal numbering: a number such as "제2-3조" makes the
    child read external articles that only share it. More words (summary, headings, the
    document name) were measured on the ADR-1447 units and ranked long annexes higher
    (the first search is BM25 over the union of the words), so only the name is used.
    """
    hint = (plain(unit['label']) or plain(unit['summary']))[:HINT_CHARS].strip()
    return [hint] if len(hint) >= 2 else [unit['label'][:HINT_CHARS]]


def external_task(document, unit, body, request, named):
    """The question, task and reason for one unit's external search; no model call.

    The child runs the ordinary source RAG: the unit's internal original and the user
    request are its question. A rule named in the unit's own text narrows the search to
    that rule (searched, never loaded whole); with no name every external rule is searched.
    The internal original is the parent's text, not the user's words: the child does not
    acquire definitions for the terms in it (question_definitions).
    """
    need = ('내규 「%s」의 "%s" 내용에 대응하는 외규 원문을 찾는다. 요약: %s '
            '(내규의 조문 번호는 내규 자체의 번호이며 외규의 같은 번호 조문과 관계없다)'
            % (document, plain(unit['label']) or unit['label'], unit['summary']))
    question = need + '\n내규 원문:\n' + body[:QUESTION_CHARS] + '\n사용자 요청: ' + request
    task = {'source_category': 'external', 'search_hints': search_hints(unit),
            'issues': [{'id': unit['unit_id'], 'question': need, 'numeric': False}], 'facts': [],
            'research_policy': 'question-scoped-research-v2',
            'research_requirements': [{'issue_id': unit['unit_id'], 'task': need, 'requirements': []}],
            'return_mode': 'sources', 'preferred_document_ids': [], 'question_definitions': False,
            'session_key': digest([unit['unit_id']])[:32]}
    if named:
        task['search_document_ids'] = sorted(named)
    return question, task


def selection_external(port, text):
    from semantic_runtime.comparison_research_bridge import preferred_documents
    return preferred_documents(port, text, 'external')


def read_article(ctx, sid):
    """Evidence IDs of one whole external article, or None to keep the passages read.

    The child returns the exact passages it read, often one sentence of an article.
    The comparison needs the rest of that article, so the parent reads all of it
    (verified like every read). A longer article keeps only the child's passages.
    """
    port = ctx.rag.port
    s = port.session
    source = s.tools.sources.get(sid)
    if not source or port.categories.get(source['document_id']) != 'external':
        return None
    did, blocks = source['document_id'], [str(b['block_id']) for b in source['blocks']]
    if not blocks or sum(len(row['text']) for row in s.store.sources(did, blocks)) > ARTICLE_CHARS:
        return None
    handle, ids, cursor = s.node(did, source.get('unit_id'), sid), [], None
    while True:
        result = ctx.rag.source_call({'operation': 'read_node', 'side': 'external', 'args': {'node': handle, 'cursor': cursor},
                                      'reason': '문서 대사 외규 조문 전체 읽기'}, call_id='document-article:' + digest([sid, cursor]))
        if result['status'] not in ('OK', 'TRUNCATED'):
            return None
        ids.extend(result.get('evidence_ids', []))
        cursor = result.get('next_cursor')
        if not cursor:
            return list(dict.fromkeys(ids)) or None


def whole_articles(ctx, state, ids):
    """The found external originals as whole articles, each article once."""
    port = ctx.rag.port
    known = state.setdefault('articles', {})
    by_source = {}
    for ident in ids:
        by_source.setdefault(port.session.repo.evidence(ident)['source_id'], []).append(ident)
    out = []
    for sid, found in by_source.items():
        if sid not in known:
            known[sid] = read_article(ctx, sid)
            _save(ctx, state)
        out.extend(known[sid] or found)
    return list(dict.fromkeys(out))


def _read_node(ctx, handle, key):
    ids, cursor = [], None
    while True:
        result = ctx.rag.source_call({'operation': 'read_node', 'side': 'external', 'args': {'node': handle, 'cursor': cursor},
                                      'reason': '문서 대사 내규가 적은 외규 조문 읽기'}, call_id='document-cited-read:' + digest([key, cursor]))
        if result['status'] not in ('OK', 'TRUNCATED'):
            return []
        ids.extend(result.get('evidence_ids', []))
        cursor = result.get('next_cursor')
        if not cursor:
            return list(dict.fromkeys(ids))


def cited_articles(ctx, state, group, unit):
    """External articles that this unit's own internal text cites, read without a search.

    The index already resolves a citation such as "금융투자업규정 제4-26조제1항" to that
    provision; the reference tool adds citations written with a name the internal
    document declared in another article ("규정 제32조" after "…상장규정(이하 "규정")").
    Only citations written in this unit's rows count. A cited article up to
    ARTICLE_CHARS is read whole; a longer one only at the cited provision.
    """
    port = ctx.rag.port
    s = port.session
    rows = dict(zip(group_review.refs(group), group['rows']))
    blocks = {str(seg['block_id']) for r in unit['refs'] for seg in rows[r]['segments']}
    known = state.setdefault('articles', {})
    out = []
    for ident in unit['internal']:
        cursor = None
        while True:
            result = ctx.rag.source_call({'operation': 'follow_reference', 'side': 'both',
                                          'args': {'evidence_id': ident, 'direction': 'outgoing', 'cursor': cursor},
                                          'reason': '문서 대사 내규가 적은 외규 조문 찾기'},
                                         call_id='document-cited:' + digest([unit['unit_id'], ident, cursor]))
            for ref in result.get('items', []):
                if str((ref.get('witness') or {}).get('block_id')) not in blocks:
                    continue
                if ref.get('declared_name'):
                    # `규정 제32조` resolved from the name this internal document declared elsewhere.
                    unit.setdefault('cited_names', []).append({**ref['declared_name'], 'locator': ref['locator']})
                for target in ref.get('targets', []):
                    node = s.resolve(target['node'], 'U')
                    if port.categories.get(node['document_id']) != 'external':
                        continue
                    sources = node.get('source_id') and [node['source_id']] or \
                        s.matcher._unit_sources(node['document_id'], str(node['unit_id']))
                    whole = None
                    if len(sources) == 1:
                        if sources[0] not in known:
                            known[sources[0]] = read_article(ctx, sources[0])
                            _save(ctx, state)
                        whole = known[sources[0]]
                    out.extend(whole or _read_node(ctx, target['node'], [unit['unit_id'], target['node']]))
            cursor = result.get('next_cursor')
            if not cursor:
                break
    return list(dict.fromkeys(out))


def search_unit(ctx, state, group, unit):
    port = ctx.rag.port
    did, name = state['document']['document_id'], state['document']['name']
    text = _store_text(port, did)
    rows = dict(zip(group_review.refs(group), group['rows']))
    body = '\n'.join(text(rows[r]['segments']) for r in unit['refs'])
    # Only a rule named in this unit's own text narrows the search (document-wide names do not).
    named = selection_external(port, body)
    question, task = external_task(name, unit, body, ctx.request['question'], named)
    # Same source-return form as the question 대사 external search: the child is anchored
    # on the exact internal originals of this unit and returns originals only.
    anchors = [{'evidence_id': e['evidence_id'], 'document_id': e['document_id'],
                'document_name': e['metadata']['document_name'], 'heading': e['metadata']['heading'],
                'quote': e['spans'][0]['text']} for e in evidence(port, unit['internal'])]
    task['internal_anchors'] = [{'issue_id': unit['unit_id'], 'definition': unit['summary'], 'scope_reason': '문서 대사 단위',
                                 'queries': list(task['search_hints']), 'sources': anchors}]
    result = ctx.rag.call({'operation': 'ask_rag', 'side': 'external', 'args': {'question': question, 'previous': None, 'task': task}},
                          call_id='document-external:' + digest([unit['unit_id'], question, task]))
    unit.update(external=sorted(result.get('evidence_ids', [])), external_status=result.get('status'),
                external_error=result.get('error_code'), external_search=task.get('search_document_ids'),
                external_notes=list(result.get('unresolved', [])))
    _save(ctx, state)
    if result.get('unknown_outcome'):
        # A model call of this search has no known outcome. Nothing more is sent: the run
        # stops with the finished groups saved; continuing ("계속") is the user's decision.
        raise WorkflowError('DOCUMENT_STOPPED_UNKNOWN_OUTCOME',
                            '외규 조사 중 결과를 알 수 없는 모델 호출이 있어 멈췄습니다.', 503)
    unit['cited'] = cited_articles(ctx, state, group, unit)
    unit['articles'] = whole_articles(ctx, state, unit['external'])
    _save(ctx, state)


def _size(item):
    return len(json.dumps(item, ensure_ascii=False))


def process_unit(ctx, state, group, unit):
    port = ctx.rag.port
    name = state['document']['name']
    if unit.get('articles') is None:
        unit['articles'] = whole_articles(ctx, state, unit.get('external', []))
        _save(ctx, state)
    cited = list(unit.get('cited') or [])
    own = [i for i in unit['articles'] if i not in cited]
    # Articles found for the other units of this reading group, the most often found first.
    found = Counter(i for u in state['groups'][group['group_id']]['units'] if u is not unit
                    for i in dict.fromkeys((u.get('cited') or []) + (u.get('articles') or [])) if i not in own and i not in cited)
    shared = [i for i, _ in sorted(found.items(), key=lambda item: -item[1])]
    if not cited and not own and not shared:
        unit.update(status='done', verdict='EXTERNAL_NOT_FOUND', comparison=None)
        return
    internal = evidence(port, unit['internal'])
    external, omitted, used_shared, size = [], [], [], sum(_size(e) for e in internal)
    shared_size = 0
    for found_for, ids in (('cited_in_unit', cited), ('this_unit', own), ('nearby_unit', shared)):
        for e in evidence(port, ids):
            item = {**e, 'found_for': found_for}
            if found_for == 'nearby_unit':
                if size + _size(item) > SOURCE_CHARS or shared_size + _size(item) > SHARED_CHARS:
                    continue
                shared_size += _size(item)
                used_shared.append(e['evidence_id'])
            elif size + _size(item) > SOURCE_CHARS:
                omitted.append(e['evidence_id'])
                continue
            external.append(item)
            size += _size(item)
    if not external:
        unit.update(status='done', verdict='DEFERRED', comparison=None, omitted_external=omitted,
                    note='찾은 외규 원문이 한 번의 비교 입력보다 커서 비교하지 못했습니다.')
        return
    sources = internal + external
    data = {'document': name, 'question': ctx.request['question'], 'unit': {'label': unit['label'], 'summary': unit['summary']},
            'sources': deepcopy(sources)}
    try:
        value = ctx.model.decide('UNIT_COMPARE', data, compare_unit.schema(), compare_unit.SYSTEM, compare_unit.validator(sources))
    except WorkflowError as exc:
        if exc.code != 'WORKFLOW_REPAIR_EXHAUSTED':
            raise
        unit.update(status='done', verdict='DEFERRED', comparison=None, omitted_external=omitted, shared_external=used_shared,
                    note='비교 응답이 원문 인용 규칙을 맞추지 못했습니다(보완 1회 후).')
        return
    unit.update(status='done', verdict=value['verdict'], comparison=value, omitted_external=omitted, shared_external=used_shared)

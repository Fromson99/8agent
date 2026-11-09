"""Render saved observations only; no model call and no regenerated judgment."""
from html import escape

VERDICTS = {'CONFLICT': '상충', 'POSSIBLE_GAP': '미비 후보', 'ADDITIONAL_INTERNAL': '내부 추가기준',
            'DEFERRED': '판정 보류', 'EXTERNAL_NOT_FOUND': '외규 못 찾음', 'CONFORMS': '부합'}
DIFFERENT = ('CONFLICT', 'POSSIBLE_GAP', 'ADDITIONAL_INTERNAL')
OPEN = ('DEFERRED', 'EXTERNAL_NOT_FOUND')
STOPS = {'DOCUMENT_STOPPED_UNKNOWN_OUTCOME': '외규 조사 중 결과를 알 수 없는 모델 호출이 생겼습니다. 같은 요청을 자동으로 다시 보내지 않습니다',
         'MODEL_TRANSPORT_ERROR': '모델 호출 전송 오류', 'WORKFLOW_MODEL_OUTCOME_UNKNOWN': '결과를 알 수 없는 모델 호출'}
BOX = 'border:1px solid #dbe3ed;border-radius:16px;padding:14px 16px;margin:14px 0;'
QUOTE = 'white-space:normal;overflow-wrap:anywhere'


def h(value):
    return escape(str(value or ''), quote=True)


def _metadata(port, ident):
    e = port.session.repo.evidence(ident)
    return e['metadata'].get('document_name') or e['document_id'], e['metadata'].get('heading', '')


def _quotes(port, citations):
    parts = []
    for c in citations:
        document, heading = _metadata(port, c['evidence'])
        parts.append('<p><strong>' + h(document + ' · ' + heading) + '</strong></p><blockquote style="' + QUOTE + '">'
                     + h(c['quote']).replace('\n', '<br>') + '</blockquote>')
    return ''.join(parts)


def _unit_table(port, state, unit, groups):
    value = unit.get('comparison') or {}
    location = ' · '.join(unit['row_labels'])
    internal = _quotes(port, value.get('internal_citations', []))
    if not internal:
        group = groups[unit['group_id']]
        from .flow import _store_text
        from .group_review import refs
        rows = dict(zip(refs(group), group['rows']))
        text = _store_text(port, state['document']['document_id'])
        internal = ''.join('<blockquote style="' + QUOTE + '">' + h(text(rows[r]['segments'])).replace('\n', '<br>') + '</blockquote>'
                           for r in unit['refs'])
    external = _quotes(port, value.get('external_citations', []))
    if not external:
        external = '<p>이 단위와 비교할 외규 원문을 찾지 못했습니다. 외규에 규정이 없다는 뜻은 아닙니다.</p>' if unit['verdict'] == 'EXTERNAL_NOT_FOUND' \
            else '<p>비교에 사용한 외규 인용이 없습니다.</p>'
    opinion = ['<strong>' + h(VERDICTS[unit['verdict']]) + '</strong>']
    for key in ('difference', 'reason'):
        if value.get(key):
            opinion.append(h(value[key]))
    if value.get('internal_text'):
        opinion.append('내규: ' + h(value['internal_text']))
    if value.get('external_text'):
        opinion.append('외규: ' + h(value['external_text']))
    notes = list(value.get('unresolved', [])) + ([unit['note']] if unit.get('note') else []) + list(unit.get('external_notes', []))
    if unit.get('external_error'):
        notes.append('외규 조사 중단 사유: ' + unit['external_error'])
    if unit.get('omitted_external'):
        notes.append('찾은 외규 원문 중 %d개는 입력 크기 때문에 이번 비교에 넣지 못했습니다.' % len(unit['omitted_external']))
    if notes:
        opinion.append('미확인: ' + '; '.join(h(n) for n in dict.fromkeys(notes)))
    return ('<h4>' + h(unit['label']) + '</h4><p>내규 위치: ' + h(location) + '</p>'
            '<table style="width:100%;table-layout:fixed"><thead><tr><th>내규 원문</th><th>외규 출처·원문</th><th>검토 의견</th></tr></thead>'
            '<tbody><tr><td>' + internal + '</td><td>' + external + '</td><td><p>' + '<br>'.join(opinion) + '</p></td></tr></tbody></table>')


def _selection(state):
    value = state.get('selection') or {}
    if value.get('status') == 'NEEDS_DOCUMENT':
        lines = ['<h2>문서 대사 — 문서 선택</h2>', '<p>' + h(value['reason']) + '</p>']
        if value['candidates']:
            lines.append('<ol>' + ''.join('<li>' + h(c['name']) + '</li>' for c in value['candidates']) + '</ol>')
            lines.append('<p>번호만 입력하면(예: 1) 그 문서 전체로 대사를 시작합니다.</p>')
        return '\n'.join(lines)
    if value.get('status') == 'ALREADY_COMPLETE':
        return ('<h2>문서 대사</h2><p>「' + h(state['document']['name']) + '」의 문서 전체 대사는 이전 실행에서 이미 끝났습니다. '
                '다시 하려면 문서 이름으로 새로 요청해 주세요.</p>')
    return None


def build(ctx, state, status=None, code=None):
    port = ctx.rag.port
    picked = _selection(state)
    units, held_rows, not_target, held_groups = [], [], [], []
    groups = {g['group_id']: g for g in (state.get('inventory') or {}).get('groups', [])}
    for gid, group in groups.items():
        g = state['groups'][gid]
        from .group_review import refs
        labels = dict(zip(refs(group), group['rows']))
        if g['status'] == 'held':
            held_groups.append((group['title'], g.get('reason', '')))
            continue
        for item in (g.get('placement') or {}).get('not_target', []):
            not_target.extend((labels[r]['label'], item['reason']) for r in item['rows'])
        for item in (g.get('placement') or {}).get('hold', []):
            held_rows.append((' · '.join(labels[r]['label'] for r in item['rows']), item['reason']))
        for unit in g.get('units', []):
            if unit['status'] == 'done':
                units.append({**unit, 'group_id': gid})
    finished = sum(state['groups'][gid]['status'] in ('done', 'held') for gid in groups)
    complete = bool(groups) and finished == len(groups)
    if status is None:
        status = 'completed' if picked is not None or (complete and not held_groups) else 'partial'
    counts = {k: sum(u['verdict'] == k for u in units) for k in VERDICTS}
    if picked is not None:
        text = picked
    else:
        document = state.get('document') or {}
        lines = ['<h2>문서 대사 결과</h2>', '<p>문서: 「' + h(document.get('name', '미선택')) + '」</p>',
                 '<p>요청: ' + h(ctx.request['question']) + '</p>',
                 '<p>진행: 읽기 묶음 %d/%d · 원문 행 %d · 대사 단위 %d</p>' % (finished, len(groups), (state.get('inventory') or {}).get('rows', 0), len(units)),
                 '<p>집계: ' + ' · '.join('%s %d' % (VERDICTS[k], counts[k]) for k in VERDICTS)
                 + ' · 대상 아님 %d행 · 보류 %d건</p>' % (len(not_target), len(held_rows) + len(held_groups)),
                 '<p>판정은 확보한 원문에 대한 검토 의견입니다. 외규를 찾지 못한 것은 외규에 규정이 없다는 뜻이 아닙니다.</p>']
        if state.get('continuation_of'):
            lines.append('<p>이전 실행에서 끝낸 묶음을 이어받아 진행했습니다.</p>')
        if status == 'partial' or code:
            reason = STOPS.get(code, code)
            lines.append('<p><strong>문서 전체 대사가 끝나지 않았습니다' + (' (중단 사유: ' + h(reason) + ')' if code else '')
                         + '. 같은 대화에서 "계속"을 보내면 끝낸 묶음은 다시 하지 않고 이어서 진행합니다.</strong></p>')
        ordered = sorted(units, key=lambda u: list(VERDICTS).index(u['verdict']))
        different = [u for u in ordered if u['verdict'] in DIFFERENT]
        unresolved = [u for u in ordered if u['verdict'] in OPEN]
        same = [u for u in ordered if u['verdict'] == 'CONFORMS']
        if different:
            lines.append('<h3>차이가 있는 단위 · %d건</h3>' % len(different))
            lines.extend(_unit_table(port, state, u, groups) for u in different)
        if unresolved:
            lines.append('<h3>판정 보류·외규 못 찾음 · %d건</h3>' % len(unresolved))
            lines.extend(_unit_table(port, state, u, groups) for u in unresolved)
        if same:
            lines.append('<details style="' + BOX + '"><summary style="cursor:pointer;"><strong>부합 · %d건</strong></summary>' % len(same))
            lines.extend(_unit_table(port, state, u, groups) for u in same)
            lines.append('</details>')
        if not_target:
            lines.append('<details style="' + BOX + '"><summary style="cursor:pointer;"><strong>대상 아님 · %d행</strong></summary><ul>' % len(not_target)
                         + ''.join('<li>' + h(label) + ' — ' + h(reason) + '</li>' for label, reason in not_target) + '</ul></details>')
        if held_rows or held_groups:
            lines.append('<h3>보류 — 확인이 필요한 행</h3><ol>'
                         + ''.join('<li>' + h(label) + ' — ' + h(reason) + '</li>' for label, reason in held_rows)
                         + ''.join('<li>읽기 묶음 「' + h(title) + '」 전체 — ' + h(reason) + '</li>' for title, reason in held_groups)
                         + '</ol>')
        text = '\n'.join(lines)
    if state.get('inventory'):
        from . import selection
        selection.save(ctx, last_run={'run_id': ctx.context.run_id, 'document_id': state['document']['document_id'],
                                      'status': status})
    summary = {'document': state.get('document'), 'selection': state.get('selection'), 'groups_total': len(groups),
               'groups_finished': finished, 'groups_held': len(held_groups), 'units': len(units), 'verdicts': counts,
               'not_target_rows': len(not_target), 'held_rows': len(held_rows), 'continuation_of': state.get('continuation_of')}
    return {'response_schema': 'workflow-result-v1', 'workflow_id': ctx.request['workflow_id'],
            'workflow_version': ctx.request['workflow_version'], 'run_id': ctx.context.run_id,
            'request_id': ctx.request['request_id'], 'status': status, 'stop_code': code,
            'answer': {'text': '<!-- GENOS_COMPARISON_START -->\n\n' + text + '\n\n<!-- GENOS_COMPARISON_END -->'},
            'document_compare': summary, 'evidence_refs': list(state.get('carry_evidence', [])),
            'unresolved': [reason for _, reason in held_groups] + [reason for _, reason in held_rows],
            'resume_available': picked is None and bool(state.get('document')) and status == 'partial',
            'usage': ctx.repo.work.budget(), 'quality_certified': False}

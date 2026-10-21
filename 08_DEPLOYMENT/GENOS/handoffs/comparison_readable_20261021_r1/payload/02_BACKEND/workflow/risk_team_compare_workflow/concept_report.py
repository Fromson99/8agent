"""One source-bound concept table shared by API, saved results and GENOS."""
from copy import deepcopy
import html
import re
from ..contracts import digest
from .contracts import check_citations
from .report import literal, RELATIONS, VERDICTS

VERSION = 'internal-concept-table-v1'
DISPLAY_VERSION = 'comparison-readable-v1'


def document_name(value):
    """Drop storage folders, retaining a named appendix's parent document."""
    text = str(value or '').strip()
    prefix = re.match(r'^(internal|external)\s*([>/])\s*', text, re.I)
    if not prefix:
        return text or '문서명 미확인'
    parts = [p.strip() for p in text.split(prefix.group(2)) if p.strip()]
    for index, part in enumerate(parts):
        if index >= 2 and part in {'별표서식', '별표·서식', '별표', '별지', '서식'}:
            return ' · '.join(parts[index-1:])
    return parts[-1]


def source_row(e, quote):
    return {'selection_id': e['evidence_id'], 'selection_ids': [e['evidence_id']],
        'document_id': e['document_id'], 'document_name': e['metadata']['document_name'],
        'coordinate_label': e['metadata'].get('heading', ''), 'quote': quote,
        'side': e['side'], 'generation_id': e['generation_id'],
        'source_artifact_hash': e['source_artifact_hash']}


def source_key(row):
    return tuple(row[k] for k in ('side', 'document_id', 'generation_id', 'source_artifact_hash'))


def label_sources(table):
    """One public number per document/version; every route/quote stays in audit."""
    labels, counts = {}, {}
    rows = table.get('final_answer', []) + table['rows']
    sources = [s for r in rows for side in ('internal', 'external') for s in r[side]]
    sources += table.get('unreviewed_originals', [])
    for source in sources:
        key = source_key(source)
        if key not in labels:
            side = source['side']
            counts[side] = counts.get(side, 0) + 1
            labels[key] = ('내규' if side == 'internal' else '외규')+' '+str(counts[side])
        source['label'] = labels[key]


def original_quote_key(evidence, quote):
    """Display identity only; keep every validated route ID in the audit."""
    required = ('side', 'document_id', 'unit_id', 'generation_id', 'source_artifact_hash')
    if any(evidence.get(k) is None for k in required):
        return ('route', evidence['evidence_id'], quote)
    locations = set()
    for span in evidence['spans']:
        if (span.get('block_id') is None or not span.get('block_hash')
                or type(span.get('start_cp')) is not int):
            continue
        start = 0
        while True:
            offset = span['text'].find(quote, start)
            if offset < 0:
                break
            absolute = span['start_cp'] + offset
            locations.add((span['block_id'], span['block_hash'], absolute, absolute + len(quote)))
            start = offset + 1
    # The citation format has no selected offset: repeated text in different
    # positions is ambiguous, so do not silently merge it across route IDs.
    if len(locations) != 1:
        return ('route', evidence['evidence_id'], quote)
    return ('original', *(evidence[k] for k in required), next(iter(locations)), quote)


def render(table):
    """Escape literal sources once; keep readable HTML intact in every consumer."""
    def escaped(value):
        return html.escape(str(value), quote=True).replace('\r\n', '\n').replace('\n', '<br>')

    all_rows = table.get('final_answer', []) + table['rows']
    originals = [s for row in all_rows for side in ('internal', 'external') for s in row[side]]
    originals += table.get('unreviewed_originals', [])
    aliases = dict(table.get('display_aliases', {}))
    for s in originals:
        for ident in s.get('selection_ids', [s['selection_id']]):
            aliases[ident] = '〔'+s['label']+'〕'
    for row in table['rows']:
        if row.get('concept_id'):
            aliases[row['concept_id']] = row['label']

    def prose(value):
        text = str(value or '')
        for ident in sorted(aliases, key=len, reverse=True):
            text = re.sub(r'(?<![A-Za-z0-9_-])'+re.escape(ident)+r'(?![A-Za-z0-9_-])',
                          lambda _: aliases[ident], text)
        text = re.sub(r'\bE[0-9a-fA-F]{16,64}\b', '인용 출처', text)
        text = text.replace('미완료', '추가 확인 필요')
        return escaped(text)

    def sources(rows):
        groups = {}
        for source in rows:
            groups.setdefault(source_key(source), []).append(source)
        blocks = []
        for group in groups.values():
            first = group[0]
            locations = list(dict.fromkeys(s['coordinate_label'] for s in group if s['coordinate_label']))
            heading = ' · '.join(locations[:3])
            if len(locations) > 3:
                heading += ' 외 '+str(len(locations)-3)+'곳'
            title = '〔'+first['label']+'〕 '+document_name(first['document_name'])
            block = '<details><summary>'+escaped(title)
            if heading:
                block += ' · '+escaped(heading)
            block += ' — 원문 보기</summary>'
            for source in group:
                block += '<p>'+escaped(source['coordinate_label'] or '조항 위치 미기록')+'</p>'
                # Raw quotations never pass through prose/ID/status rewriting.
                block += '<blockquote style="white-space:normal;overflow-wrap:anywhere">'+escaped(source['quote'])+'</blockquote>'
            blocks.append(block+'</details>')
        return ''.join(blocks)

    def paired(internal, external, opinion, *, final=False):
        if final:
            missing_external = '이 설명은 내규 원문을 근거로 작성했습니다.'
            missing_internal = '이 설명은 외규 원문을 근거로 작성했습니다.'
        else:
            missing_external = ('외규 원문은 확보했으며, 이 항목과의 적용 관계는 추가 확인이 필요합니다.'
                if any(s['side'] == 'external' for s in originals) else
                '연결 외규 원문 미확보 — 해당 규정이 없다는 뜻은 아닙니다.')
            missing_internal = '내규 원문 미확보'
        return ('<table style="width:100%;table-layout:fixed"><thead><tr>'
            '<th>내규 출처·원문</th><th>외규 출처·원문</th><th>검토 의견</th>'
            '</tr></thead><tbody><tr><td>'+ (sources(internal) or missing_internal)+
            '</td><td>'+ (sources(external) or missing_external)+
            '</td><td>'+opinion+'</td></tr></tbody></table>')

    output = ['<!-- GENOS_COMPARISON_START --><div class="comparison-report">',
        '<h2>내규·외규 검토 결과</h2>',
        '<p>질문: '+prose(table['question'])+'</p>',
        '<p>기준일: '+escaped(table['as_of'] or '미지정 — 현재 유효성 미확인')+'</p>']
    final = table.get('final_answer')
    if final:
        output.append('<p>확인한 원문으로 작성한 답변입니다. 출처를 펼치면 해당 설명에 인용한 원문을 볼 수 있습니다.</p>')
        for number, row in enumerate(final, 1):
            refs = list(dict.fromkeys(s['label'] for side in ('internal', 'external') for s in row[side]))
            output.append('<p>'+prose(row['text'])+' '+escaped(' '.join('〔'+r+'〕' for r in refs))+'</p>')
        output.append('<details><summary>답변에 사용한 내규·외규 근거 펼치기</summary>')
        output.append('<p>아래는 각 설명에 실제 인용한 근거입니다. 같은 설명에 인용되었다는 사실만으로 내규·외규의 직접 연결이나 부합이 확정되는 것은 아닙니다.</p>')
        for number, row in enumerate(final, 1):
            output.append('<h3>설명 '+str(number)+'</h3>')
            output.append(paired(row['internal'], row['external'], prose(row['text']), final=True))
        output.append('</details>')
    else:
        output.append('<p>개념·연결·해석은 확보한 원문에 대한 검토 의견입니다.</p>')
        for row in table['rows']:
            output.append('<h3>'+prose(row['label'])+'</h3><p>'+prose(row['definition'])+'</p>')
            if row['scope_reason']:
                output.append('<details><summary>검토 범위</summary><p>'+prose(row['scope_reason'])+'</p></details>')
            opinions = []
            for opinion in row['opinions']:
                opinions.append('<p><strong>'+prose(opinion['verdict_label'])+'</strong><br>'+
                    prose(opinion['difference'])+'<br>'+prose(opinion['reason'])+
                    '<br>연결 판단: '+prose(opinion['relation_label'])+'</p>')
            for observation in row['observations']:
                # Empty task-board placeholders are audit state, not an opinion.
                if observation.get('reviewed', True):
                    opinions.append('<p><strong>'+prose(observation['field_label'])+'</strong><br>내규: '+
                        prose(observation['internal_text'])+'<br>외규: '+prose(observation['external_text'])+
                        '<br>'+prose(observation['difference'])+'</p>')
            if not opinions:
                opinions.append('확보한 원문을 제시합니다. 항목별 적용 관계는 추가 확인이 필요합니다.')
            output.append(paired(row['internal'], row['external'], ''.join(opinions)))
        if not table['rows']:
            output.append('<p>연결할 내규 원문 미확보 — 질문에 적용할 내규 확인이 필요합니다.</p>')

    # Keep unused originals available, once per exact route/quote. Never discard
    # old findings or mistake their absence in the final text for source absence.
    displayed = final if final else table['rows']
    shown = {(source_key(s), ident, s['quote']) for r in displayed
             for side in ('internal', 'external') for s in r[side]
             for ident in s.get('selection_ids', [s['selection_id']])}
    remaining, seen = [], set()
    for source in originals:
        key = (source_key(source), source['selection_id'], source['quote'])
        if key not in shown and key not in seen:
            remaining.append(source);seen.add(key)
    if remaining:
        output.append('<details><summary>함께 확인한 원문 · '+str(len({source_key(s) for s in remaining}))+'개 문서</summary>')
        output.append('<p>확보한 원문입니다. 답변에 인용되지 않은 자료의 적용 관계는 추가 확인이 필요합니다.</p>')
        output.append(sources(remaining)+'</details>')

    unresolved = table.get('answer_unresolved', []) + table['unresolved']
    unresolved += [u for row in table['rows'] for u in row['unresolved']]
    notes = []
    if not final:
        notes = list(dict.fromkeys(prose(row['label']+' · '+observation['field_label']+
            ': 양측 원문의 적용 관계를 추가 확인해야 합니다.')
            for row in table['rows'] for observation in row['observations']
            if not observation.get('reviewed', True)))
    for value in unresolved:
        # Omit repeated generated workflow-state lines, retaining specific model
        # limitations and every raw status/cause in the saved structured result.
        if (re.fullmatch(r'조사 미완료: [A-Za-z0-9_]+', value) or
                value.endswith(' — 항목 확인 미완료') or
                value in {'조사 또는 항목 검토 미완료', '항목별 검토 미완료', '개념 범위·외규 조사 미완료'}):
            continue
        text = prose(value)
        if text and text not in notes:
            notes.append(text)
    if notes:
        output.append('<details><summary>추가 확인 사항 · '+str(len(notes))+'건</summary><ul>')
        output.extend('<li>'+note+'</li>' for note in notes)
        output.append('</ul></details>')
    output.append('</div><!-- GENOS_COMPARISON_END -->')
    return ''.join(output)


def apply(ctx, state, result, by):
    from .task_board import CONFIG
    concepts = state.get('concept_plan', {}).get('concepts', [])
    items = result['comparison_items']['items']
    pairs = {p['pair_id']: p for p in state.get('basis', {}).get('pairs', [])}
    labels = {}
    counts = {}
    selected_ids = set()
    cards = result['assembly']['term_agent']['source_bundle']['sources']
    known = {c['selection_id'] for c in cards}

    def selected(citations, side):
        check_citations(citations, by)
        values = []
        seen = {}
        for citation in citations:
            e = by[citation['evidence']]
            if e['side'] != side:
                raise ValueError('comparison table citation belongs to opposite side')
            ident = e['evidence_id']
            selected_ids.add(ident)
            key = original_quote_key(e, citation['quote'])
            if key not in labels:
                counts[side] = counts.get(side, 0) + 1
                labels[key] = ('내규' if side == 'internal' else '외규')+' '+str(counts[side])
            if key in seen:
                if ident not in seen[key]['selection_ids']:
                    seen[key]['selection_ids'].append(ident)
            else:
                row = {'selection_id': ident, 'selection_ids': [ident],
                    'document_id': e['document_id'],
                    'document_name': e['metadata']['document_name'],
                    'coordinate_label': e['metadata'].get('heading', ''),
                    'quote': citation['quote'], 'side': side, 'label': labels[key],
                    'generation_id': e['generation_id'], 'source_artifact_hash': e['source_artifact_hash']}
                values.append(row)
                seen[key] = row
            if ident not in known:
                cards.append({'selection_id':ident,'document_id':e['document_id'],
                    'document_name':e['metadata']['document_name'],'coordinate_label':e['metadata'].get('heading',''),
                    'generation_id':e['generation_id'],'source_artifact_hash':e['source_artifact_hash'],
                    'spans':deepcopy(e['spans']),'excerpt':e['text'],'side':side,'content_read':True,
                    'interpretation_status':'UNVERIFIED','coverage':'READ_SPANS_ONLY'})
                known.add(ident)
        return values

    rows = []
    for concept in concepts:
        related = [i for i in items if i['issue_id'] == concept['id']]
        finals = [r for r in state.get('comparison', {}).get('rows', [])
                  if pairs[r['pair_id']]['issue_id'] == concept['id']]
        citations = {s: [] for s in ('internal', 'external')}
        citations['internal'].extend(concept['internal_citations'])
        for item in related:
            for side in citations:
                citations[side].extend(item[side]['citations']+item[side]['dependencies'])
        for row in finals:
            for citation in row['citations']+[c for d in row['dimensions'] for c in d['citations']]:
                if citation['evidence'] not in by:
                    raise ValueError('comparison table has unknown source')
                citations[by[citation['evidence']]['side']].append(citation)
        observations = [{'field':i['field'],'field_label':CONFIG['fields'][i['field']],
            'reviewed':bool(i['internal']['text'] or i['external']['text'] or i['difference']),
            'internal_text':i['internal']['text'] or '내규 항목 검토 미완료',
            'external_text':i['external']['text'] or '외규 항목 검토 미완료',
            'difference':i['difference'] or '항목별 해석 미완료'} for i in related]
        opinions = [{'verdict_label':VERDICTS[r['verdict']], 'difference':r['difference'],
            'reason':r['reason'],'relation_label':RELATIONS[pairs[r['pair_id']]['basis_relation']]} for r in finals]
        missing = [i[s]['missing'] for i in related for s in citations if i[s]['missing']]
        missing.extend(x for r in finals for x in r['unresolved'])
        rows.append({'concept_id':concept['id'], 'request_issue_id':concept['request_issue_id'],
            'label':concept['label'], 'definition':concept['definition'], 'scope_reason':concept['scope_reason'],
            **{s:selected(citations[s],s) for s in citations},
            'observations':observations,'opinions':opinions,'unresolved':list(dict.fromkeys(missing))})
    # If concept planning stopped, keep the actual returned originals readable.
    # No semantic grouping or external association is fabricated by this path.
    if not concepts:
        for e in by.values():
            if e['side'] != 'internal':
                continue
            rows.append({'concept_id':None,'request_issue_id':None,'label':'개념 검토 미완료',
                'definition':'확보한 내규 원문입니다. 개념 범위와 외규 연결은 아직 정하지 못했습니다.',
                'scope_reason':'','internal':selected([{'evidence':e['evidence_id'],'quote':s['text']} for s in e['spans']],'internal'),
                'external':[],'observations':[],'opinions':[],'unresolved':['개념 범위·외규 조사 미완료']})
    unreviewed=[]
    for record in result.get('unreviewed_sources',[]):
        ident=record['evidence_id']
        if ident not in by or by[ident]['side']!=record['side']:
            raise ValueError('unreviewed original binding changed')
        if ident in selected_ids:continue
        e=by[ident]
        unreviewed.extend(selected([{'evidence':ident,'quote':s['text']} for s in e['spans']],e['side']))
    table = {'schema_version':VERSION, 'question':ctx.request['question'],'as_of':ctx.request['as_of'],
             'rows':rows,'unresolved':list(result.get('unresolved', [])),
             'display_version':DISPLAY_VERSION,
             'display_aliases':{i['id']:i['label'] for i in state.get('scope',{}).get('issues',[])}}
    if unreviewed:table['unreviewed_originals']=unreviewed
    label_sources(table)
    table['content_hash'] = digest(table)
    result['comparison_table'] = table
    result['concept_plan'] = deepcopy(state.get('concept_plan'))
    result['report']['question_scope'] = deepcopy(state.get('question_scope'))
    result['answer']['text'] = render(table)
    result['evidence_refs'] = sorted(set(result['evidence_refs']) | selected_ids)
    result['evidence_summary']['reported'] = len(cards)
    bundle = result['assembly']['term_agent']['source_bundle']
    bundle.pop('bundle_hash', None)
    bundle['bundle_hash'] = digest(bundle)
    return result

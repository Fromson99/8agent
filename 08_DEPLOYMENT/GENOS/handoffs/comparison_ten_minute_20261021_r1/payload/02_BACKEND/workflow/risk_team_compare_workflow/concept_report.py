"""One source-bound concept table shared by API, saved results and GENOS."""
from copy import deepcopy
from ..contracts import digest
from .contracts import check_citations
from .report import literal, RELATIONS, VERDICTS

VERSION = 'internal-concept-table-v1'


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
    # Escape before introducing our own HTML. Original quotations are never
    # summarized, trimmed, or passed through prose sentence rewriting.
    def cell(text):
        return literal(text).replace('\r\n', '\n').replace('\n', '<br>')

    def sources(rows, quotes):
        blocks = []
        for row in rows:
            block = cell(row['document_name']+' · '+(row['coordinate_label'] or '조항 위치 미기록'))
            block += ' '+cell('〔'+row['label']+'〕')
            if quotes:
                block += '<br>「'+cell(row['quote'])+'」'
            blocks.append(block)
        return '<br><br>'.join(blocks)

    lines = ['## 내규·외규 대사 보고서', '', '질문: '+literal(table['question']), '',
             '사용자 질문 → 확인한 내규 → 내규 개념·조항 범위 → 연결 외규 → 대사 해석', '',
             '기준일: '+literal(table['as_of'] or '미지정 — 현재 유효성 미확인'), '',
             '개념 정의·연결 판단·해석은 LLM의 검토 의견입니다. 원문은 아래 출처와 함께 확인할 수 있습니다.', '',
             '| 내규 출처·조항 | 개념·확인 내용 | 내규 원문 | 연결 외규 출처·원문 | 대사 해석·미확인 |',
             '|---|---|---|---|---|']
    for row in table['rows']:
        concept = '**'+cell(row['label'])+'**<br>'+cell(row['definition'])
        if row['scope_reason']:
            concept += '<br><br>범위 선정 이유: '+cell(row['scope_reason'])
        if row['observations']:
            concept += '<br><br>'+'<br>'.join(cell(x['field_label'])+': '+cell(x['internal_text'])
                                            for x in row['observations'])
        interpretation = []
        for opinion in row['opinions']:
            interpretation.append('**'+cell(opinion['verdict_label'])+'**<br>'+
                cell(opinion['difference'])+'<br>'+cell(opinion['reason'])+
                '<br>연결 판단: '+cell(opinion['relation_label']))
        for observation in row['observations']:
            interpretation.append(cell(observation['field_label'])+'<br>외규 확인: '+
                cell(observation['external_text'])+'<br>대사: '+cell(observation['difference']))
        if not interpretation:
            interpretation.append('대사 해석 미완료')
        if row['unresolved']:
            interpretation.append('**미확인**<br>'+'<br>'.join(cell(x) for x in row['unresolved']))
        lines.append('| '+' | '.join([
            sources(row['internal'], False) or '내규 출처 미확보',
            concept,
            sources(row['internal'], True) or '내규 원문 미확보',
            sources(row['external'], True) or (
                '이 행에 연결할 외규 원문 미선택 — 확보 후 미검토 원문은 아래에 별도 표시합니다.'
                if any(s['side']=='external' for s in table.get('unreviewed_originals',[])) else
                '연결 외규 원문 미확보 — 해당 규정이 없다는 뜻은 아닙니다.'),
            '<br><br>'.join(interpretation)])+' |')
    if not table['rows']:
        lines.append('| 미확보 | 내규 개념 범위 미확정 | 미확보 | 조사 미수행 | 내규 확보·개념 검토 필요 |')
    if table.get('unreviewed_originals'):
        lines.extend(['', '확보한 원문 — 항목별 검토 미완료', '',
            '아래 원문은 확보했으나 비교 항목과의 대응·적용 판단은 아직 완료하지 못했습니다.'])
        for original in table['unreviewed_originals']:
            lines.extend(['', sources([original], True)])
    if table['unresolved']:
        lines.extend(['', '추가 확인 사항', ''])
        lines.extend('- '+literal(x) for x in table['unresolved'])
    return '\n'.join(lines)


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
             'rows':rows,'unresolved':list(result.get('unresolved', []))}
    if unreviewed:table['unreviewed_originals']=unreviewed
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

"""Deterministic, current-route display. No model call or inferred rationale."""
from ..contracts import digest
from .errors import ContractError

REVISION = 'judgment-view-20261006-r1'
STAGES = ('INTENT', 'PLAN', 'RECALL', 'READ', 'SELECT', 'ASSESS', 'COMPOSE')
LABELS = ('질문 이해', '검색 계획', '자료 검색', '원문 확인', '근거 선택', '적용 판단', '답변 작성')


def reason_text(value):
    text = str(value or '').strip()
    if text in {'없음', '이유 없음', '이유가 없음', '별도 이유 없음',
                '모델이 별도 이유를 제공하지 않음', 'N/A', 'null', 'None'}:
        return ''
    return text


def build(parts, case, *, state, run_id, allowed_documents, executed=()):
    """Only project verified current heads and sources in the effective scope."""
    refs = case.get('judgment_refs') or {}
    if not refs:
        return None
    allowed = set(allowed_documents)
    sources = {}
    read = parts.get('READ', {}).get('payload', {})
    selection = parts.get('SELECT', {}).get('payload', {})
    def source_label(source):
        locations = list(dict.fromkeys(str(o['label']) for o in source.get('read_scopes', []) if o.get('label')))
        return {'source_id': source['source_id'], 'document_name': source.get('document_name') or source['document_id'],
                'coordinate': ' / '.join(locations) or source.get('coordinate_label') or source.get('heading') or source.get('unit_id') or ''}
    for source in [*read.get('originals', []), *selection.get('selected_originals', [])]:
        if source.get('document_id') in allowed:
            sources[source['source_id']] = source_label(source)
    selected = set(selection.get('final_ids', []))
    chosen_reasons = {}
    navigation=selection.get('law_navigation') or {}
    laws={law['id']:law for law in navigation.get('laws',[]) if law.get('document_id') in allowed}
    law_reasons={row['law_id']:row for row in navigation.get('law_decisions',[]) if row['law_id'] in laws}
    for branch in navigation.get('branches',[]):
        if branch['law_id'] in laws and branch['source_id'] in sources:
            chosen_reasons[branch['source_id']]=reason_text(branch.get('reason')) or reason_text(law_reasons.get(branch['law_id'],{}).get('reason'))
    for decision in selection.get('decisions', []):
        for choice in decision.get('decision', {}).get('choices', []):
            sid = selection.get('label_to_source', {}).get(choice.get('id'))
            if sid in sources:
                chosen_reasons[sid] = reason_text(choice.get('reason'))

    stages = []
    for index, (stage, label) in enumerate(zip(STAGES, LABELS), 1):
        part = parts.get(stage)
        ref = refs.get(stage)
        if not part or not ref or digest(part['payload']) != ref['payload_hash']:
            raise ContractError('judgment display current-head hash mismatch: ' + stage)
        payload = part['payload']
        status = '이번 요청 수행' if stage in executed else '현재 판단 유지'
        if case.get('status') == 'REUSED' and stage not in executed:
            status = '확정 경험 연결'
        row = {'id': str(index), 'stage': stage, 'label': label, 'status': status,
               'judgment_ref': ref, 'decisions': [], 'data': [], 'actions': []}
        if stage == 'INTENT':
            row['decisions'] = [payload['purpose']]
            row['actions'] = ['질문의 조사 목적과 검색 개념 정리']
            row['concepts'] = payload.get('concepts', [])
            row['facts'] = state.get('facts', [])
        elif stage == 'PLAN':
            row['decisions'] = ['검색어: ' + str(q) for q in payload.get('queries', [])]
            row['actions'] = ['현재 질문과 지정 문서 범위로 검색 계획 구성']
            row['documents'] = payload.get('law_names', [])
            row['processing'] = '고정 처리'
        elif stage == 'RECALL':
            row['actions'] = ['검색 기록에서 읽을 후보 수집']
            row['data'] = [{**sources[sid], 'action': '읽을 후보로 선택'}
                           for sid in payload.get('selected_for_read', []) if sid in sources]
        elif stage == 'READ':
            row['actions'] = ['원문을 열람하고 출처·버전·원문 범위 확인']
            row['data'] = [{**source_label(s), 'action': '원문 열람', 'quote': s.get('text', '')}
                           for s in payload.get('originals', []) if s.get('document_id') in allowed]
            for receipt in payload.get('record', {}).get('actions', []):
                sid=receipt.get('source_id')
                action=receipt.get('action') or {}
                status=(receipt.get('result') or {}).get('status')
                if sid in sources and status in ('OK','REUSED'):
                    extent=(action.get('args') or {}).get('extent')
                    label={'exact':'해당 단위 본문', 'subtree':'하위 항·호·목 포함'}.get(extent,'원문 범위')
                    row['actions'].append(sources[sid]['document_name']+' · '+label+' 열람'+(' · 기존 열람 재사용' if status=='REUSED' else ''))
            row['actions']=list(dict.fromkeys(row['actions']))
        elif stage == 'SELECT':
            row['actions'] = ['읽은 원문에서 답변에 사용할 근거 선택']
            row['data'] = [{**source, 'action': '답변 근거 채택' if sid in selected else '최종 근거에 미포함',
                            'reason': chosen_reasons.get(sid, '')} for sid, source in sources.items()]
            row['decisions'] = [str(issue) for d in payload.get('decisions', [])
                                for issue in d.get('decision', {}).get('issues', [])]
            if navigation:
                row['laws']=[{**law,'selection':law_reasons.get(key),
                    'branches':[b for b in navigation.get('branches',[]) if b['law_id']==key]} for key,law in laws.items()]
                row['decisions'] += [laws[key]['name']+' · '+str(choice['reason']) for key,choice in law_reasons.items()]
                row['limitations']=payload.get('completion_limitations',[])
                row['completion_policy']=payload.get('completion_policy')
                if payload.get('control_contract'):
                    row['investigation_chain']=payload['investigation_chain']
                    row['return_points']=payload['return_points']
                    row['inventory']=payload['saved_inventory']
                    row['source_inventory']=payload['evidence_inventory']
                row['actions'] += [str(d['decision']['next_action'])+' · '+str(d['decision']['reason'])
                                   for d in payload.get('decisions',[]) if 'next_action' in d.get('decision',{})]
        elif stage in ('ASSESS', 'COMPOSE'):
            row['actions'] = ['선택한 원문을 현재 조건에 적용' if stage == 'ASSESS'
                              else '현재 판단과 출처를 유지해 최종 답변 작성']
            for claim in payload.get('claims', []):
                sid = claim['source_id']
                if sid not in sources:
                    continue
                row['data'].append({**sources[sid], 'action': '판단 근거 인용',
                                    'judgment': claim['text'], 'quote': claim['quote']})
            row['limitations'] = payload.get('limitations', [])
            if stage=='ASSESS' and 'issue_assessments' in payload:
                row.update(issue_assessments=payload['issue_assessments'],gaps=payload['gaps'],answer_coverage=payload['answer_coverage'])
        rationale = reason_text(payload.get('reason'))
        if rationale:
            row['reason'] = rationale
        stages.append(row)
    view = {'schema_version': 'judgment-view-v1', 'revision': REVISION,
            'question_id': case['question_id'], 'question_revision': case['revision'],
            'route_id': case['route_id'], 'run_id': run_id, 'stages': stages}
    view['content_sha256'] = digest(view)
    return view

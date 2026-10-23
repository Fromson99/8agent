from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate'];D=C/'02_BACKEND/semantic_runtime/legal_agent'
def change(name,old,new):
 p=D/name;s=p.read_text();assert s.count(old)==1,(name,s.count(old));p.write_text(s.replace(old,new))
change('connection_scope.py',"    data['connection_scope_choices'] = choices",'''    data['connection_scope_choices'] = choices
    attempted = next((c for c in choices if c['selected'] and
        c['connection_preview']['status'] != 'NOT_SELECTED'), None)
    selectable = any(a['action'] == 'FOLLOW_CONNECTION' and
        a.get('identity', {}).get('connection_scope') for a in actions.values())
    data['connection_review'] = {
        'required_before_finish': bool(data.get('sources') and selectable and not attempted),
        'status': attempted['connection_preview']['status'] if attempted else
            ('SELECT_SCOPE' if selectable else 'UNAVAILABLE'),
        'scope_id': attempted['id'] if attempted else None,
        'all_targets_required': False,
        'rule': '종료 판단 전에 사용할 원문 범위를 FOLLOW_CONNECTION으로 선택해 저장 연결을 확인한다. '
                '조회 결과를 받은 뒤 필요한 연결만 읽는다. 빈 목록·일부 확인·실패도 상태를 보존해 종료할 수 있다. '
                '조회 불가나 예산 소진은 확보 원문을 전달하며 원문 부재로 단정하지 않는다.'}
''')
change('law_navigation.py',"    terminal_actions = {'PENDING'} | ({'FINISH'} if originals else set())", "    review_required = view.get('connection_review', {}).get('required_before_finish', False)\n    terminal_actions = {'PENDING'} | ({'FINISH'} if originals and not review_required else set())")
change('decision_projection.py',"    if basis:\n        bindings['FINISH']", "    if basis and not data.get('connection_review', {}).get('required_before_finish', False):\n        bindings['FINISH']")
change('decision_projection.py',"    else:\n        alternatives.append(obj({'choice':{'const':'PENDING'},'reason':reason}))", "    elif not basis:\n        alternatives.append(obj({'choice':{'const':'PENDING'},'reason':reason}))")
change('decision_projection.py',"        'connection_scope_rule':data.get('connection_scope_rule'),", "        'connection_scope_rule':data.get('connection_scope_rule'),\n        'connection_review':deepcopy(data.get('connection_review',{})),")
change('decision_projection.py',"            '연결이 필요할 때 최종 사용할 구조 범위를 FOLLOW_CONNECTION으로 선택한다. '", "            'connection_review.required_before_finish=true이면 종료 전에 사용할 구조 범위를 FOLLOW_CONNECTION으로 선택한다. '\n            '목록 조회가 끝나면 필요한 대상만 읽거나 현재 원문으로 종료를 판단한다. '")
change('request_repair.py',"def bind_gaps(value, session, rounds):", '''def assessment_locator_options(sources, navigation):
    """Location labels from verified delivered originals and stored links only.

    Existence in the catalogue does not prove a model-supplied location. Unknown
    locations remain an empty selector; the gap reason retains what is missing.
    """
    rows = {}; documents = set()
    def add(source, origin):
        name = source.get('document_name', '').strip()
        heading = source.get('heading', '').strip()
        if not name:
            return
        documents.add(name)
        if heading:
            label = name + ' ' + heading
            rows.setdefault(label, {'target': label, 'origin': origin,
                'source_id': source.get('source_id'), 'document_id': source.get('document_id')})
    for source in sources:
        add(source, 'DELIVERED_ORIGINAL')
    for group in navigation.get('groups', []):
        if group.get('connections'):
            add(group.get('target') or {}, 'STORED_REFERENCE_TARGET')
    for name in documents:
        rows.setdefault(name, {'target': name, 'origin': 'KNOWN_DOCUMENT'})
    return [rows[k] for k in sorted(rows)]


def bind_gaps(value, session, rounds, *, allowed_targets=None):''')
change('request_repair.py',"    for n, raw in enumerate(out['gaps']):\n        previous", "    for n, raw in enumerate(out['gaps']):\n        if allowed_targets is not None and raw.get('missing_target', '') not in allowed_targets:\n            raise ProposalError('missing_target must select a verified source/reference location; use empty string for unknown location and retain the missing content in reason')\n        previous")
change('request_repair.py',"            if gap['target_binding']['status'] == 'UNLOCATED' and not raw.get('missing_target'):", "            if (gap['target_binding']['status'] == 'UNLOCATED' and not raw.get('missing_target')\n                    and (allowed_targets is None or prior.get('missing_target', '') in allowed_targets)):")
change('completion_execution.py',"def assessment_projection(schema):", "def assessment_projection(schema, *, allowed_targets=None):")
change('completion_execution.py',"                branches=[]\n                for kind in props['kind']['enum']:", "                if allowed_targets is not None:\n                    props['missing_target']['enum'] = list(allowed_targets)\n                branches=[]\n                for kind in props['kind']['enum']:")
change('completion_execution.py',"        basis = {'output_contract_version':output.VERSION", "        locator_options = rr.assessment_locator_options(sources, selection.get('reference_navigation', {})) if modern and profile.get('candidate_navigation',{}).get('selected_connection_scope') else None\n        allowed_targets = ['', *(r['target'] for r in locator_options)] if locator_options is not None else None\n        basis = {'locator_options_hash':digest(locator_options), 'output_contract_version':output.VERSION")
change('completion_execution.py',"        generation_schema,expand_assessment=assessment_projection(schema) if modern else (schema,lambda v:v)", "        generation_schema,expand_assessment=assessment_projection(schema,allowed_targets=allowed_targets) if modern else (schema,lambda v:v)\n        if allowed_targets is not None:\n            answer_policy += '\\nmissing_target은 locator_options.target의 제공된 표기를 그대로 선택한다. 필요한 위치가 목록에 없으면 빈 문자열로 두고 reason에 필요한 내용을 설명한다. 조항 번호를 추측하지 않는다.'")
change('completion_execution.py',"                    'reference_leads': reference_leads(selection.get('reference_navigation', {})),", "                    'reference_leads': reference_leads(selection.get('reference_navigation', {})),\n                    'locator_options':locator_options,")
change('completion_execution.py',"                    accepted=rr.bind_gaps(accepted,self.s.sources,rounds)", "                    accepted=rr.bind_gaps(accepted,self.s.sources,rounds,allowed_targets=allowed_targets)")
p=Path(__file__).with_name('repin.py');s=p.read_text().replace("('connection_scope.py', 'decision_projection.py')", "('connection_scope.py', 'decision_projection.py', 'law_navigation.py', 'request_repair.py', 'completion_execution.py')");p.write_text(s)
print('Changed five candidate modules; working source untouched')

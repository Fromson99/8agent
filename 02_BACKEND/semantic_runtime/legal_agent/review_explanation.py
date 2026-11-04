"""Current review projection; acquisition is not a semantic resolution.

Only committed assessment inputs enter this module. Historical declarations are
retained by the ledger, never rendered as current instructions verbatim.
"""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError

VERSION = 'review-explanation-v1'


def seal(value):
    return {**value, 'content_sha256': digest(value)}


def verify(value):
    if value.get('schema_version') != VERSION or value.get('content_sha256') != digest(
            {k: v for k, v in value.items() if k != 'content_sha256'}):
        raise ContractError('review explanation binding changed')
    return value


def need_items(assessment):
    receipt = assessment.get('read_judgment_review') or {}
    targets = {t['id']: t for t in receipt.get('need_continuity', {}).get('targets', [])}
    reviewed = {r['id']: r for r in (receipt.get('review') or {}).get('needs', [])}
    rows = []
    for need in receipt.get('prior_needs', []):
        final = reviewed.get(need['id'], {})
        status = final.get('status', 'INCOMPLETE')
        links = sorted(set(need.get('target_refs') or []) | set(final.get('target_refs') or []))
        linked = [targets[t] for t in links if t in targets]
        acquired = bool(linked) and len(linked) == len(links) and all(t.get('available_complete') for t in linked)
        acquisition = 'ACQUIRED' if acquired else 'PARTIAL' if any(t.get('acquired') for t in linked) else 'NOT_RECORDED' if not linked else 'MISSING'
        if status in ('RESOLVED', 'NOT_NEEDED'):
            reason, action = '최종 검토 완료', None
        elif acquired:
            reason, action = '원문 확보 완료. 필요 항목과 주장·근거의 최종 연결 검토가 남아 있습니다.', 'REVIEW_AGAIN'
        elif linked:
            reason, action = '지정한 원문 범위의 확보 또는 전달이 완료되지 않았습니다.', 'READ_SCOPE'
        else:
            reason, action = '필요 항목의 최종 검토와 대응 원문 범위 연결이 확인되지 않았습니다.', 'REVIEW_AGAIN'
        declaration = str(need.get('text') or '').strip()
        import re
        if not linked and declaration and not re.match(r'^(?:없음(?:[.。\s]|$)|N/A$|None$|null$)', declaration):
            if not assessment.get('scenario_calculation'):
                reason += ' 조사 당시 확인 목적(이력): ' + declaration
        rows.append({'id': need['id'], 'kind': 'REVIEW' if acquired or not linked else 'SOURCE',
            'target_refs': links, 'issue_refs': deepcopy(need.get('issue_refs', [])),
            'targets': [{k: deepcopy(t[k]) for k in ('id', 'document_id', 'coordinate', 'coordinate_scope') if k in t} for t in linked],
            'acquisition': acquisition, 'delivery': 'PRESENTED' if acquired else 'NOT_RECORDED',
            'review': status, 'reason': reason, 'impact': '해당 필요 항목에 대한 결론을 확정할 수 없습니다.' if action else '기록된 검토 범위에 한정합니다.',
            'next_action': action, 'actor': 'SYSTEM', 'claim_refs': deepcopy(final.get('claim_refs', [])),
            **({'historical_declaration': declaration} if assessment.get('scenario_calculation') and declaration else {})})
    return rows


def build(assessment, sources):
    items = need_items(assessment)
    for index, gap in enumerate(assessment.get('gaps', [])):
        if not gap.get('material', True):
            continue
        fact = gap['kind'] == 'MISSING_FACT'
        acquired = gap_acquired(gap, sources)
        items.append({'id': 'gap:' + str(index + 1), 'kind': 'FACT' if fact else 'REVIEW' if acquired else 'SOURCE',
            'target_refs': [], 'issue_refs': [gap['issue_id']], 'targets': [],
            'acquisition': 'NOT_APPLICABLE' if fact else 'ACQUIRED' if acquired else 'NOT_RECORDED', 'delivery': 'PRESENTED' if acquired else 'NOT_RECORDED',
            'review': 'OPEN', 'reason': ('원문 확보 완료. 해당 범위에 대한 의미·연결 검토는 미완료입니다.' if acquired else gap.get('missing_target') or gap['reason']),
            'impact': '해당 요건에 의존하는 결론은 미확정입니다.',
            'next_action': 'REQUEST_FACT' if fact else 'REVIEW_AGAIN' if acquired else 'RESEARCH', 'actor': 'USER' if fact else 'SYSTEM', 'claim_refs': []})
    incomplete = (assessment.get('read_judgment_review', {}).get('status') == 'INCOMPLETE'
                  or assessment.get('model_proposal', {}).get('review_status') == 'INCOMPLETE')
    failure = assessment.get('model_proposal', {}).get('failure', {})
    explanations = {
        'SCOPE_USE_UNSUPPORTED_RANGE':'사용한 것으로 표시한 원문 구간 중 실제 답변의 근거로 연결되지 않은 구간이 있습니다.',
        'SCOPE_CLAIM_EVIDENCE':'원문 구간에 연결한 주장과 그 주장이 실제 인용한 근거가 맞지 않습니다.',
        'SCOPE_TARGET_COVERAGE':'확인 대상 원문 범위 중 최종 검토에서 빠지거나 중복된 대상이 있습니다.',
        'SCOPE_RANGE_COVERAGE':'확보한 원문 구간의 사용·제외·미확인 검토가 빠졌거나 중복됐습니다.',
        'SCOPE_FOREIGN_EVIDENCE':'검토 대상 범위 밖의 원문이 근거로 연결됐습니다.',
        'SCOPE_REVIEW_REASON_ISSUE':'원문 구간의 검토 이유 또는 질문 쟁점 연결이 빠졌습니다.',
        'SCOPE_QUOTE_INVALID':'원문 범위를 제외하는 근거로 제시한 문구가 현재 질문과 일치하지 않습니다.',
        'SCOPE_USE_LINK':'사용할 원문과 실제 답변 주장의 연결을 완료하지 못했습니다.',
        'SCOPE_EXCLUSION_LINK':'제외한 원문에 사용 주장이나 미확인 항목이 함께 연결돼 있습니다.',
        'SCOPE_EXCLUDED_ADOPTED':'제외한 것으로 표시한 원문을 답변에서 동시에 사용했습니다.',
        'SCOPE_OPEN_GAP':'미확인으로 남긴 원문 구간이 해당 질문의 미해결 항목과 연결되지 않았습니다.',
        'SCOPE_ACQUISITION_INCOMPLETE':'답변에 필요한 원문 범위의 확보가 끝나지 않았습니다.',
        'SCOPE_REVIEW_INCOMPLETE':'확보한 원문 범위 중 최종 검토가 끝나지 않은 부분이 있습니다.',
        'FINAL_REVIEW_PURPOSE_CHANGE':'이전에 사용한 근거의 판단을 바꾸면서 변경 이유와 실제 근거를 연결하지 못했습니다.',
        'REQUIREMENT_GAP_COVERAGE':'미확인 사항은 기록됐으나 요구사항 검토표와의 연결을 완료하지 못했습니다.',
        'REQUIREMENT_COVERAGE_MISSING':'질문의 일부 요구사항 또는 쟁점에 대한 검토가 빠졌습니다.',
        'REQUIREMENT_MATERIAL_GAP':'요구사항과 해당 미확인 사항의 연결이 맞지 않습니다.',
        'REQUIREMENT_CLAIM_EVIDENCE':'요구사항을 충족한다고 제시한 주장과 실제 근거의 연결이 맞지 않습니다.',
        'REQUIREMENT_EXCLUSION_BASIS':'요구사항을 제외할 근거나 사용자가 한정한 범위를 확인하지 못했습니다.',
        'REQUIREMENT_SCOPE_QUOTE':'요구사항 제외에 사용한 문구가 현재 사용자 요청과 일치하지 않습니다.',
        'REQUIREMENT_REASON_EMPTY':'요구사항의 검토 내용이나 이유가 비어 있습니다.',
        'SCENARIO_APPLICATION_LINK':'가정 적용 주장과 조건의 연결이 빠졌거나 맞지 않습니다.',
        'REVIEW_LINK_INVALID':'검토표가 참조하는 주장·근거 연결이 없거나 중복·미사용 상태입니다.',
        'SCENARIO_CURRENT_VALUE_BINDING':'현재 적용값이 해당 가정의 변경 필드와 연결되지 않았습니다.',
        'SCENARIO_COMPARISON_BINDING':'과거 비교값이 현재 적용값 또는 다른 필드와 섞였습니다.',
        'SCENARIO_NUMERIC_LITERAL':'현재 적용 또는 별도 비교 설명의 금액·단위가 해당 역할의 연결값과 다릅니다.',
        'SCENARIO_APPLICATION_COVERAGE':'변경된 규칙 조건을 적용한 주장을 확인하지 못했습니다.',
        'SCENARIO_CHANGED_VALUE_MISSING':'적용 설명에 변경된 규칙값이 반영되지 않았습니다.',
        'SCENARIO_SUPERSEDED_RULE':'가정 적용 설명에서 변경 전 규칙값을 다시 사용했습니다.',
        'COMPUTED_GAP_IN_REASON':'미확인 입력이 설명문에만 적혀 있어 구조화된 입력 연결을 완료하지 못했습니다.',
        'SCENARIO_REVIEW_SHAPE':'가정 검토 결과의 필수 형식을 확인하지 못했습니다.',
        'SCENARIO_CONTEXT_MISMATCH':'최종 검토가 현재 가정 분기에 연결되지 않았습니다.',
        'SCENARIO_CONDITION_CONFLICT':'최종 검토와 타입 조건 평가 결과가 다릅니다.',
        'SCENARIO_UNRESOLVED_CONCLUSION':'미확인 요건이 남았는데 충족으로 판단했습니다.',
        'SCENARIO_SUPERSEDED_FACT':'변경 전 값을 현재 가정의 사실로 다시 사용했습니다.',
        'NEED_TARGET_INCOMPLETE': '필요 항목과 원문 범위의 최종 검토 연결이 빠졌습니다.',
        'NEED_TARGET_CLAIM_LINK': '검토한 원문 범위와 최종 주장 사이의 연결이 맞지 않습니다.',
        'NEED_RESOLUTION_CLAIM': '해결로 표시한 필요 항목에 대응하는 최종 주장을 확인하지 못했습니다.',
        'NEED_RESOLUTION_JUDGMENT': '필요 항목을 해결한 판단 연결을 확인하지 못했습니다.',
        'NEED_TARGET_ISSUE': '원문 범위와 쟁점의 연결이 맞지 않습니다.',
        'NEED_CLAIM_LINK': '필요 항목과 주장 근거의 연결을 확인하지 못했습니다.'}
    failures = [{'code': r['code'], 'reason': explanations[r['code']], 'stage':'ASSESS',
        'impact':'해당 연결을 사용하는 결론은 확정하지 않습니다.', 'actor':'SYSTEM'}
        for r in failure.get('issues', []) if r.get('code') in explanations]
    failures.extend({'code':r['code'],'reason':'가정 검토 결과의 필수 형식을 확인하지 못했습니다.',
        'stage':'ASSESS','impact':'가정하의 결론을 확정하지 않습니다.','actor':'SYSTEM'}
        for r in failure.get('issues',[]) if r.get('code','').startswith('SCHEMA_') and r.get('path','').startswith('/scenario_review'))
    # The generation projection now owns this constant. Keep the public
    # semantic failure code while retaining the original wire error in journal.
    failures.extend({'code':'SCENARIO_CONDITION_CONFLICT','reason':explanations['SCENARIO_CONDITION_CONFLICT'],
        'stage':'ASSESS','impact':'가정하의 결론을 확정하지 않습니다.','actor':'SYSTEM'}
        for r in failure.get('issues',[]) if r.get('code')=='MINIMAL_OUTPUT_CONSTANT'
        and r.get('path')=='/scenario_review/condition_results')
    if incomplete:
        items.append({'id': 'final-review', 'kind': 'REVIEW', 'target_refs': [],
            'issue_refs': [r['issue_id'] for r in assessment.get('issue_assessments', [])], 'targets': [],
            'acquisition': 'ACQUIRED' if sources else 'NOT_RECORDED', 'delivery': 'PRESENTED' if sources else 'NOT_RECORDED',
            'review': 'INCOMPLETE', 'reason': '시스템이 최종 주장·필요·원문의 연결 검증을 완료하지 못했습니다.',
            'impact': '확보한 원문은 제공하지만 최종 결론은 확정하지 않습니다.',
            'next_action': 'REVIEW_AGAIN', 'actor': 'SYSTEM', 'claim_refs': []})
    return seal({'schema_version': VERSION, 'basis_hash': digest({k: v for k, v in assessment.items() if k not in ('review_explanation','ontology_explanation')}),
        'outcome': 'SOURCE_ONLY' if assessment.get('source_excerpt_reply') else assessment.get('answer_coverage', 'NOT_RECORDED'),
        'completed': [{'source_id': s['source_id'], 'document_id': s['document_id'],
            'document_name': s.get('document_name') or s['document_id'], 'coordinate': s.get('heading', ''),
            'acquisition': 'ACQUIRED'} for s in sources],
        **({'historical_issues': list(dict.fromkeys(r['historical_issue'] for r in assessment.get('limitation_items', []) if r.get('historical_issue')))} if assessment.get('scenario_calculation') else {}),
        'items': items, 'failed_checks': failures, 'ontology': deepcopy(assessment.get('ontology_explanation',
            {'status': 'NOT_RECORDED', 'bundles': [], 'adoption': 'NOT_RECORDED'})),
        'scenario_review':deepcopy(assessment.get('model_proposal',{}).get('scenario_review')),
        **({'scenario_calculation':deepcopy(assessment['scenario_calculation'])} if assessment.get('scenario_calculation') else {}),
        **({'scenario_application_display':deepcopy(assessment['scenario_application_display'])} if assessment.get('scenario_application_display') else {}),
        'semantic_quality_certified': False})


def bind_case(explanation, case, state=None):
    verify(explanation)
    value = deepcopy(explanation); value.pop('content_sha256')
    value['case'] = {k: case[k] for k in ('question_id', 'revision', 'route_id')}
    value['actions'] = []
    for item in value['items']:
        kind = item['next_action']
        if not kind:
            continue
        action = {'schema_version': 'review-action-v1', 'kind': kind, 'item_id': item['id'],
            'target_refs': item['target_refs'], 'case': value['case'], 'basis_hash': explanation['content_sha256'],
            'actor': item['actor'], 'fact_name':item['reason'] if kind == 'REQUEST_FACT' else None, 'label': {'REVIEW_AGAIN':'검토 다시 하기', 'REQUEST_FACT':'사실 입력', 'READ_SCOPE':'원문 범위 확인', 'RESEARCH':'대응 원문 찾기'}[kind], 'input': 'fact_text' if kind == 'REQUEST_FACT' else None,
            'enabled': True,
            'unavailable_reason': None}
        action['id'] = digest(action)
        value['actions'].append(action)
    from .scenario_facts import options as fact_options
    fields={}
    for bundle in explanation['ontology'].get('bundles', []):
        fields.update((bundle.get('assembly') or {}).get('evaluation_plan', {}).get('spec', {}).get('fields', {}))
    for kind, label in (('VIEW_REVIEW','검토 상태 보기'), ('WHAT_IF','가정 비교'), ('SCENARIO_REVIEW','가정의 의미 재검토')):
        action = {'schema_version':'review-action-v1', 'kind':kind, 'label':label,
            'case':value['case'], 'basis_hash':explanation['content_sha256'],
            'enabled':kind == 'VIEW_REVIEW' or bool(fields), 'actor':'USER',
            'unavailable_reason':'승인된 타입 식과 편집할 입력이 등록되지 않았습니다.' if kind != 'VIEW_REVIEW' and not fields else None,
            'fields':deepcopy(fields) if kind != 'VIEW_REVIEW' else {},
            'fact_options': fact_options(state or {}) if kind != 'VIEW_REVIEW' else [],
            'input':'kind/changes/bindings' if kind != 'VIEW_REVIEW' else None}
        action['id']=digest(action)
        value['actions'].append(action)
    return seal(value)


def gap_acquired(gap, sources):
    if gap['kind'] == 'MISSING_FACT':
        return False
    target = gap.get('target_binding') or {}
    expected = target.get('expected', [])
    if target.get('status') != 'EXACT' or not expected or any('document_id' not in p for p in expected):
        return False
    from .completion_contracts import evidence_options
    from .evidence_inventory import covers
    options = evidence_options(sources)
    return all(covers([p for p in expected if p['document_id']==did],
                      [p for p in options if p['document_id']==did])
               for did in {p['document_id'] for p in expected})


def current_gap_limitations(assessment, sources):
    """Keep declarations verbatim in history; display the exact current range."""
    rows={r['id']:r for r in assessment['limitation_items']}
    for gap in assessment.get('gaps', []):
        if not gap_acquired(gap,sources):continue
        target=(gap.get('missing_target') or '').strip()
        ident='L'+digest([gap['issue_id'],gap['kind'],gap.get('material_id'),target])[:20]
        if ident in rows:
            rows[ident]['text']=(target+': ' if target else '')+'원문 확보 완료. 해당 범위의 최종 의미·연결 검토는 미완료입니다.'
            rows[ident]['navigation_status']='ACQUIRED_REVIEW_PENDING'
    assessment['limitations']=list(dict.fromkeys(r['text'] for r in assessment['limitation_items']))

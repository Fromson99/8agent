"""Complete retained-opinion accounting in the existing ASSESS call.

Final opinions never erase navigation opinions. Resolution receipts retain both
sides, and unavailable originals cannot become supported answer claims.
"""
from copy import deepcopy
from jsonschema import validate
from ..contracts import digest
from .completion_contracts import obj
from .errors import ContractError, ProposalError
from . import read_judgment as rj

FIELD = 'read_judgment_review'
PROMPT = '''read_judgments에는 조사 중 남긴 잠정 판단·부족·충돌과 이전 최종 검토가 있다. 이전 의견은 정답이 아니다. 현재 원문과 다시 대조한다. 선택한 긍정 근거뿐 아니라 제외·보류 의견, 예외·반대 근거, 미해결 부족·충돌도 빠짐없이 검토한다.
read_judgment_review.judgments에는 제시된 모든 판단 ID를 한 번씩 넣는다. disposition=USE/CONDITIONAL은 실제 claims의 claim_refs와 같은 현재 evidence_options의 basis_refs로 연결한다. UNRESOLVED는 미확인, NOT_USED는 이번 답변에 불필요하다는 판단이며 각각 이유가 필요하다. 원문이 재제시되지 않은 이전 의견은 사실로 인용하지 않는다.
needs/conflicts에는 제시된 모든 ID의 현재 OPEN/RESOLVED/NOT_NEEDED와 이유, material(이번 질문의 결론에 영향을 주는가)을 쓴다. 해결되었다면 실제 원문 basis_refs가 필요하며 충돌은 양쪽 원문을 함께 확인해야 한다. 필요 없다는 판단도 삭제하지 않고 이유를 남긴다. 중요한 미확인은 제한 사항으로 남길 수 있다. 추가 조사가 필요하면 기존 gaps에 필요한 내용을 쓴다. 근거 없는 조항 번호나 도구를 만들지 않는다.'''
PROMPT += '''
CONDITIONAL은 이번 claims에 실제 조건부 주장을 작성했다는 뜻이다. 추가 확인이 필요해 아직 답변에 쓰지 못하는 판단은 UNRESOLVED다. claims=[]이면 USE/CONDITIONAL과 claim_refs를 쓰지 않는다. 존재하지 않는 C1 같은 번호를 추가해도 실제 주장이 되지 않는다. claims의 실제 claim_id를 작성한 뒤 그 번호만 연결한다. 원문 확보가 더 필요하면 채택 판단과 별개로 gaps에 필요한 대상을 지정한다. 이미 읽은 조항을 미확보 대상으로 고르지 않는다. 필요한 위치가 locator_options에 없으면 missing_target=""로 두고 reason에 설명한다.
'''


def independent_core(raw, schema, references, schema_name):
    """Decode only a valid core of a rejected review; never accept the response."""
    from .minimal_output import Projection
    from jsonschema import ValidationError
    if not isinstance(raw, dict) or FIELD not in schema.get('properties', {}):
        return None
    value, core_schema = core({FIELD: None, **raw}, schema)
    try:
        value = Projection(core_schema).expand(value)
        if references is not None:
            value = references.decode(value, core_schema, schema_name)
    except (ProposalError, ValidationError):
        return None
    return {**value, FIELD: None}


def independent_research(execution, error, value, schema, *, content_impl, options,
                         facts, sources, investigation, rounds, allowed_targets, decision_key):
    """Reject the opinion, but validate an independent exact missing-source request.

    This runs only after the existing correction is exhausted. It never commits
    claims or repairs a legal disposition, and uses the ordinary SELECT reentry.
    """
    from . import output_contract as output, request_repair as rr
    from .evidence_inventory import covers
    from .corrected_memory import Reenter
    from jsonschema import ValidationError
    if (not isinstance(error, output.OutputContractError)
            or error.category not in ('FINAL_READ_REVIEW_INVALID','OUTPUT_SHAPE_INVALID')
            or not isinstance(value, dict)):
        return False
    core_value, core_schema = core({FIELD:None, **value}, schema)
    try:
        if 'disposition' not in core_value:
            from .completion_execution import assessment_projection
            _, expand = assessment_projection(core_schema, allowed_targets=allowed_targets)
            core_value = expand(core_value)
        accepted, proposal = content_impl.prepare(core_value, core_schema, execution.issues, options, facts)
        accepted = rr.bind_gaps(accepted, execution.s.sources, rounds, allowed_targets=allowed_targets)
        result = content_impl.materialize(accepted, options, execution.issues, proposal)
        if result['claims']:
            execution.verify_claims(result['claims'], sources)
    except (ProposalError, ValidationError):
        return False
    actual = {}
    for option in options:
        actual.setdefault(option['document_id'], []).append(option)
    eligible = []
    for gap in result['gaps']:
        target = gap.get('target_binding', {})
        if not gap['material'] or gap['kind'] == 'MISSING_FACT' or target.get('status') != 'EXACT':
            continue
        expected = target.get('expected', [])
        if not expected or not rr.may_reopen(gap, investigation):
            continue
        if all(covers([p for p in expected if p['document_id'] == did], actual.get(did, []))
               for did in {p['document_id'] for p in expected}):
            continue
        eligible.append(gap)
    policy = execution.s.sources.profile
    budget = execution.s.work.budget()
    if (not eligible
            or getattr(execution,'reentry_counters',{}).get('ASSESS_GAP_REENTRY',0) >= policy['candidate_navigation']['assessment_reentry_limit']
            or budget['model_limit']-budget['finalization_reserve']-budget['model_reserved'] < 2
            or execution.s.context.remaining() <= policy['selection_time_reserve_seconds']):
        return False
    signature = digest({'binding':investigation.get('binding'),
        'targets':sorted(g['target_binding_hash']+digest(g['target_binding']) for g in eligible),
        'originals':sorted((p['document_id'],str(p['block_id']),p['start_cp'],p['end_cp'],p['text_hash']) for p in options)})
    prior = investigation.get('final_review_recovery', [])
    if any(row['signature'] == signature for row in prior):
        return False
    checkpoint = deepcopy(investigation)
    receipt = {'signature':signature,'decision_key':decision_key,'rejected_proposal_hash':getattr(error,'raw_proposal_hash',digest(value)),
        'gaps':[g['identity_key'] for g in eligible], 'claims_adopted':False,'review_adopted':False}
    receipt['previous_no_progress'] = checkpoint.get('no_progress', 0)
    checkpoint.setdefault('final_review_recovery', []).append(receipt)
    # A first exact lookup of an unread target is concrete progress. A repeated
    # target with the same originals was rejected above; request budgets survive.
    checkpoint['no_progress'] = 0
    checkpoint.setdefault('request_progress', []).append('verified-gap-lookup:' + signature)
    # The existing reentry consumer retains only claims; empty claims cannot
    # turn rejected output into an accepted opinion or reusable knowledge.
    research = {'claims':[], 'gaps':eligible, 'issue_assessments':[],
        FIELD:{'status':'INCOMPLETE','review':None}, 'recovery_receipt':receipt}
    execution.s.work.event('FINAL_REVIEW_INDEPENDENT_RESEARCH', receipt)
    raise Reenter('SELECT','independent missing originals after rejected final review',
        {'reentry_kind':'ASSESS_GAP_REENTRY','gaps':eligible,'assessment':research,'investigation_state':checkpoint})


def context(investigation, question, issues, options, allowed):
    key = rj.key_for(investigation.get('binding'), question, issues)
    state = rj.checked(investigation.get('read_judgments', {}).get(key, {}))
    heads = deepcopy(state.get('heads', {}))
    for option in options:
        jid = 'J' + digest([key, option['document_id'], option['source_id']])[:24]
        heads.setdefault(jid, {'id': jid, 'source_id': option['source_id'], 'document_id': option['document_id'],
            'use': 'DEFER', 'finding': '', 'reason': '조사 중 판단 미완료; 최종 검토에서 현재 원문 확인',
            'basis': [], 'version': 0, 'issue_refs': [i['id'] for i in issues]})
    for head in heads.values():
        if head['document_id'] not in allowed:
            raise ContractError('retained read judgment outside authorized assessment scope')
        head['available_evidence_refs'] = [o['id'] for o in options
            if o['source_id'] == head['source_id'] and o['document_id'] == head['document_id']]
        head['original_available'] = bool(head['available_evidence_refs'])
    return {'version': rj.VERSION, 'request_key': key, 'state_hash': state.get('state_hash'),
        'judgments': list(heads.values()), 'needs': list(deepcopy(state.get('needs', {})).values()),
        'conflicts': list(deepcopy(state.get('conflicts', {})).values()),
        'previous_final_review': deepcopy(state.get('final_reviews', [])[-1:]),
        'rule': 'Every retained judgment, need and conflict requires an explicit final disposition; omission never closes it.'}


def review_schema(ctx, options, *, enforce_claim_shape=False):
    refs = rj.strings([o['id'] for o in options])
    def entries(items, props):
        return {'type': 'array', 'minItems': len(items), 'maxItems': len(items), 'items': obj({
            'id': {'enum': [r['id'] for r in items]} if items else {'type': 'string'},
            'reason': rj.TEXT, 'basis_refs': deepcopy(refs), **props})}
    status = {'status': {'enum': ['OPEN', 'RESOLVED', 'NOT_NEEDED']}, 'material': {'type': 'boolean'}}
    schema = obj({'judgments': entries(ctx['judgments'], {
        'disposition': {'enum': ['USE', 'CONDITIONAL', 'UNRESOLVED', 'NOT_USED']},
        'claim_refs': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}}}),
        'needs': entries(ctx['needs'], status), 'conflicts': entries(ctx['conflicts'], status)})
    if enforce_claim_shape:
        base = schema['properties']['judgments']['items']
        adopted = deepcopy(base); pending = deepcopy(base)
        adopted['properties']['disposition']['enum'] = ['USE', 'CONDITIONAL']
        adopted['properties']['claim_refs']['minItems'] = 1
        pending['properties']['disposition']['enum'] = ['UNRESOLVED', 'NOT_USED']
        pending['properties']['claim_refs']['maxItems'] = 0
        base['anyOf'] = [adopted, pending]
        base['properties']['disposition']['description'] = ('USE/CONDITIONAL은 실제 claims에 채택한 판단이다. claims에 없는 판단이나 추가 조사 대기는 UNRESOLVED, 이번 답변에 불필요하면 NOT_USED로 판단한다.')
    return schema


def attach(schema, ctx, options):
    value = deepcopy(schema)
    value['properties'][FIELD] = review_schema(ctx, options, enforce_claim_shape=True)
    value['required'].append(FIELD)
    return value


def core(value, schema):
    value, schema = deepcopy(value), deepcopy(schema)
    value.pop(FIELD)
    schema['properties'].pop(FIELD)
    schema['required'].remove(FIELD)
    return value, schema


def covered(basis, options):
    """All original intervals of each side remain available, including hashes."""
    from .evidence_inventory import covers
    for original in basis:
        offered = [o for o in options if o['source_id'] == original['source_id']
                   and o['document_id'] == original['document_id']]
        if not covers(original['spans'], offered):
            return False
        # Whole equal intervals can additionally prove content identity; split
        # intervals still pass the existing source/claim verification on ASSESS.
        for span in original['spans']:
            matching = [o for o in offered if all(o[k] == span[k] for k in ('block_id','start_cp','end_cp'))]
            if matching and any(o['text_hash'] != span['text_hash'] for o in matching):
                raise ContractError('retained judgment original hash changed')
    return bool(basis)


def validate_review(value, ctx, options):
    from .output_contract import OutputContractError, issue
    review = value[FIELD]
    validate(review, review_schema(ctx, options))
    by_ref = {o['id']: o for o in options}
    problems = []; diagnostics = []
    def fail(code, path, message, expected):
        problems.append(message); diagnostics.append(issue(code, path, expected=expected))
    for field in ('judgments', 'needs', 'conflicts'):
        ids = [r['id'] for r in review[field]]; expected={r['id'] for r in ctx[field]}
        if len(ids) != len(set(ids)) or set(ids) != expected:
            fail('FINAL_REVIEW_ID_COVERAGE','/'+FIELD+'/'+field,
                'final review must account for every retained '+field,
                {'missing_ids':sorted(expected-set(ids)), 'duplicate_ids':sorted({x for x in ids if ids.count(x)>1}), 'expected_ids':sorted(expected)})
        for i,row in enumerate(review[field]):
            if not row['reason'].strip():
                fail('FINAL_REVIEW_REASON','/'+FIELD+'/'+field+'/'+str(i)+'/reason',
                    'final disposition requires reason',{'id':row['id'],'nonempty':True})
    heads = {r['id']: r for r in ctx['judgments']}
    claims = {c['claim_id']: c for c in value['claims']}
    for i,row in enumerate(review['judgments']):
        head = heads[row['id']];path='/'+FIELD+'/judgments/'+str(i)
        if row['disposition'] in ('USE', 'CONDITIONAL'):
            own = set(row['basis_refs']) & set(head['available_evidence_refs'])
            if not own or not row['claim_refs'] or set(row['claim_refs']) - claims.keys():
                # Report each independent correction together, without choosing
                # a legal opinion, claim, or original on the model's behalf.
                if not own:
                    fail('FINAL_REVIEW_OWN_ORIGINAL',path+'/basis_refs',
                        'used judgment requires its current original',
                        {'judgment_id':row['id'],'available_evidence_refs':head['available_evidence_refs']})
                if not row['claim_refs'] or set(row['claim_refs']) - claims.keys():
                    fail('FINAL_REVIEW_ACTUAL_CLAIM',path+'/claim_refs',
                        'used judgment requires an actual claim; claims가 비어 있으면 USE/CONDITIONAL로 채택할 수 없음. 원문으로 실제 주장을 작성하거나 UNRESOLVED/NOT_USED를 판단하고 claim_refs=[]로 작성',
                        {'judgment_id':row['id'],'actual_claim_ids':list(claims),'claim_count':len(claims),
                         'nonadopting_dispositions':['UNRESOLVED','NOT_USED'],'nonadopting_claim_refs':[]})
            elif any(not (set(claims[c]['evidence_refs']) & own) for c in row['claim_refs']):
                fail('FINAL_REVIEW_SHARED_ORIGINAL',path+'/basis_refs',
                    'judgment and claim must share current original evidence',
                    {'judgment_id':row['id'],'own_evidence_refs':sorted(own),
                     'claim_evidence_refs':{c:claims[c]['evidence_refs'] for c in row['claim_refs']}})
        elif row['claim_refs']:
            fail('FINAL_REVIEW_UNADOPTED_CLAIM',path+'/claim_refs',
                'unresolved/unused judgment cannot claim final adoption',
                {'judgment_id':row['id'],'disposition':row['disposition'],'claim_refs':[]})
    for field in ('needs', 'conflicts'):
        known = {r['id']: r for r in ctx[field]}
        for i,row in enumerate(review[field]):
            if row['status'] != 'RESOLVED':continue
            path='/'+FIELD+'/'+field+'/'+str(i)+'/basis_refs'
            if not row['basis_refs']:
                fail('FINAL_REVIEW_RESOLUTION_ORIGINAL',path,'final resolution requires current original evidence',{'id':row['id'],'nonempty':True})
            if field == 'conflicts':
                selected = [by_ref[r] for r in row['basis_refs']]
                if not all(covered(opinion['basis'], selected) for opinion in known[row['id']]['opinions']):
                    fail('FINAL_REVIEW_CONFLICT_ORIGINALS',path,
                        'final conflict resolution requires the exact originals of both opinions',{'id':row['id'],'requires_both_originals':True})
    if problems:raise OutputContractError('; '.join(dict.fromkeys(problems)),diagnostics,category='FINAL_READ_REVIEW_INVALID')


def retain(result, value, ctx, investigation, options):
    """Keep final accounting distinct from provisional findings; replay-safe."""
    receipt = {'status': 'REVIEWED', 'input_hash': digest(ctx), 'state_hash': ctx['state_hash'],
        'review': deepcopy(value[FIELD]), 'prior_judgments': deepcopy(ctx['judgments']),
        'prior_needs': deepcopy(ctx['needs']), 'prior_conflicts': deepcopy(ctx['conflicts'])}
    receipt['receipt_hash'] = digest(receipt)
    result[FIELD] = receipt
    state = rj.checked(investigation.get('read_judgments', {}).get(ctx['request_key'], {}))
    if state:
        state = deepcopy(state)
        history = state.setdefault('final_reviews', [])
        if any(r['receipt_hash'] == receipt['receipt_hash'] for r in history):return
        if state['state_hash'] != ctx['state_hash']:
            raise ContractError('stale final read judgment revision')
        by_ref = {o['id']:o for o in options}
        for field in ('needs','conflicts'):
            for row in value[FIELD][field]:
                basis = [{'reference_id':ref, 'source_id':by_ref[ref]['source_id'],
                    'document_id':by_ref[ref]['document_id'],
                    'spans':[{k:by_ref[ref][k] for k in ('block_id','start_cp','end_cp','text_hash')}],
                    'text_hash':by_ref[ref]['text_hash']} for ref in row['basis_refs']]
                state[field][row['id']].update(status=row['status'],reason=row['reason'],basis=basis,
                    material=row['material'],resolution_origin='ASSESS')
        history.append(deepcopy(receipt))
        state['state_hash'] = rj.seal(state)
        investigation['read_judgments'][ctx['request_key']] = state


def incomplete(result, ctx):
    result[FIELD] = {'status': 'INCOMPLETE', 'input_hash': digest(ctx),
        'prior_judgments': deepcopy(ctx['judgments']), 'prior_needs': deepcopy(ctx['needs']),
        'prior_conflicts': deepcopy(ctx['conflicts']), 'review': None}


def limitations(result):
    receipt = result.get(FIELD)
    if not receipt:return False
    review = receipt.get('review')
    material_open = False
    if review:
        for field in ('needs', 'conflicts'):
            for row in review[field]:
                if row['status'] != 'OPEN':continue
                material_open |= row['material']
                text = ('미확인 사항: ' if field == 'needs' else '해결하지 못한 판단 충돌: ') + row['reason']
                result['limitation_items'].append({'id': 'L-'+row['id'], 'kind': 'READ_JUDGMENT_UNRESOLVED',
                    'issue_id': None, 'text': text})
        for row in review['judgments']:
            if row['disposition'] == 'UNRESOLVED':
                result['limitation_items'].append({'id': 'L-'+row['id'], 'kind': 'READ_JUDGMENT_UNRESOLVED',
                    'issue_id': None, 'text': '판단 보류: ' + row['reason']})
    result['limitations'] = list(dict.fromkeys(r['text'] for r in result['limitation_items']))
    if material_open:result['disposition'] = 'LIMITED_ANSWER'
    return material_open

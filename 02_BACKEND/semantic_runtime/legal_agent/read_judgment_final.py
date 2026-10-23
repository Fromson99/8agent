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


def review_schema(ctx, options):
    refs = rj.strings([o['id'] for o in options])
    def entries(items, props):
        return {'type': 'array', 'minItems': len(items), 'maxItems': len(items), 'items': obj({
            'id': {'enum': [r['id'] for r in items]} if items else {'type': 'string'},
            'reason': rj.TEXT, 'basis_refs': deepcopy(refs), **props})}
    status = {'status': {'enum': ['OPEN', 'RESOLVED', 'NOT_NEEDED']}, 'material': {'type': 'boolean'}}
    return obj({'judgments': entries(ctx['judgments'], {
        'disposition': {'enum': ['USE', 'CONDITIONAL', 'UNRESOLVED', 'NOT_USED']},
        'claim_refs': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}}}),
        'needs': entries(ctx['needs'], status), 'conflicts': entries(ctx['conflicts'], status)})


def attach(schema, ctx, options):
    value = deepcopy(schema)
    value['properties'][FIELD] = review_schema(ctx, options)
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
    review = value[FIELD]
    validate(review, review_schema(ctx, options))
    by_ref = {o['id']: o for o in options}
    problems = []
    for field in ('judgments', 'needs', 'conflicts'):
        ids = [r['id'] for r in review[field]]
        if len(ids) != len(set(ids)) or set(ids) != {r['id'] for r in ctx[field]}:
            problems.append('final review must account for every retained ' + field)
        if any(not r['reason'].strip() for r in review[field]):
            problems.append('final disposition requires reason')
    heads = {r['id']: r for r in ctx['judgments']}
    claims = {c['claim_id']: c for c in value['claims']}
    for row in review['judgments']:
        head = heads[row['id']]
        if row['disposition'] in ('USE', 'CONDITIONAL'):
            own = set(row['basis_refs']) & set(head['available_evidence_refs'])
            if not own or not row['claim_refs'] or set(row['claim_refs']) - claims.keys():
                problems.append('used judgment requires an actual claim and its current original')
            elif any(not (set(claims[c]['evidence_refs']) & own) for c in row['claim_refs']):
                problems.append('judgment and claim must share current original evidence')
        elif row['claim_refs']:
            problems.append('unresolved/unused judgment cannot claim final adoption')
    for field in ('needs', 'conflicts'):
        known = {r['id']: r for r in ctx[field]}
        for row in review[field]:
            if row['status'] != 'RESOLVED':continue
            if not row['basis_refs']:
                problems.append('final resolution requires current original evidence')
            if field == 'conflicts':
                selected = [by_ref[r] for r in row['basis_refs']]
                if not all(covered(opinion['basis'], selected) for opinion in known[row['id']]['opinions']):
                    problems.append('final conflict resolution requires the exact originals of both opinions')
    if problems:raise ProposalError('; '.join(dict.fromkeys(problems)))


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

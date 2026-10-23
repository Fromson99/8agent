"""Source-bound provisional judgments inside the existing navigation call.

Omission retains an old opinion. Only explicit, evidenced revisions change a
head; needs and conflicts have independent lifetimes. No legal inference,
automatic target selection, or additional model/retry loop lives here.
"""
from copy import deepcopy
from jsonschema import validate
from ..contracts import digest
from .completion_contracts import obj
from .errors import ContractError, ProposalError

VERSION = 'read-judgment-v1'
WIRE_VERSION = 'read-judgment-delta-v2'
USES = ['CORE', 'SUPPORT', 'CONDITIONAL', 'DEFER', 'EXCLUDE']
PROMPT = '''현재 원문을 읽은 판단과 다음 행동을 이 응답 하나에 함께 쓴다.
read_judgments.required에는 새로 전달된 원문 묶음이 있다. 각 judgment_id를 read_review.judgments에서 빠짐없이 검토한다. CORE=질문의 직접 근거, SUPPORT=보조 근거, CONDITIONAL=특정 조건에서 사용, DEFER=판단 보류, EXCLUDE=이번 답에 사용하지 않음이다. finding에는 확인한 내용, reason에는 질문과 실제 원문을 대조한 이유, basis_refs에는 그 판단의 현재 원문을 쓴다. 원문을 읽었다는 사실만으로 적용·충분성이 확정되지 않는다.
처음은 SET, 기존 판단을 수정할 때도 SET과 변경 이유·근거를 쓴다. KEEP은 기존 의미 판단을 유지하며 새 원문도 대조했다는 뜻이다. KEEP/WITHDRAW에는 judgment_id, operation, reason, basis_refs만 쓴다. 기존 finding/use/issue_refs는 서버가 보존하므로 다시 작성하지 않는다. WITHDRAW는 기존 판단 철회이며 이유와 근거가 필요하다. 새 내용·부족을 발견했으면 SET으로 명시한다. 충돌이 풀리지 않으면 CONFLICT와 conflicts_with에 양쪽 판단을 연결하고 보류한다. 원문에 없는 의미 충돌을 코드가 해결해주지 않는다.
이전 판단을 응답에서 생략하면 그대로 유지된다. 기존 부족·충돌도 생략하거나 새 missing=[]를 썼다고 사라지지 않는다. missing에는 새로 발견한 구체적 미확인만 쓴다. 기존 부족은 need_updates로 OPEN/RESOLVED/NOT_NEEDED와 이유를 남긴다. RESOLVED는 실제 원문 근거가 필요하다. 연결 목록·도구 성공만으로 부족이 해결되지는 않는다. 충돌 해결은 conflict_updates에 양쪽 원문 근거와 이유를 남긴다.
다음 도구의 judgment_refs는 그 행동의 이유가 된 판단이다. missing_need에는 남은 어떤 내용을 어느 연결·도구로 확인할지 쓴다. 명시 참조·역참조 모두 역할을 판단하며 자동으로 따라가지 않는다. FINISH도 남은 부족을 지우지 않고 최종 검토로 넘길 수 있다. 최종 법률 답변을 여기서 작성하지 않는다.'''


def enabled(inv):
    return bool(getattr(inv,'policy',{}).get('read_judgment'))


def seal(value):
    return digest({k: v for k, v in value.items() if k != 'state_hash'})


def key_for(binding, question, issues):
    return digest([VERSION, binding, question, issues])


def request_key(inv, data):
    return key_for(inv.p['binding'], data.get('current_request', inv.question), data['issues'])


def checked(state):
    if state and (state.get('version') != VERSION or state.get('state_hash') != seal(state)):
        raise ContractError('read judgment state hash/version mismatch')
    return state


def state_for(inv, data):
    return checked(inv.p.get('read_judgments', {}).get(request_key(inv, data), {}))


def strings(values, *, minimum=0):
    values = list(values)
    return {'type': 'array', 'minItems': minimum, 'maxItems': len(values), 'uniqueItems': True,
            'items': {'enum': values} if values else {'type': 'string'}}


TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 600}


def originals(inv, data):
    rows = {}
    for source in data.get('sources', []):
        if not source.get('text'):
            continue
        did = source.get('document_id')
        if did not in inv.s.scope:
            raise ContractError('read judgment original outside authorized scope')
        sid = source['source_id']
        jid = 'J' + digest([request_key(inv, data), did, sid])[:24]
        row = rows.setdefault(jid, {'id': jid, 'source_id': sid, 'document_id': did,
            'document_name': source.get('document_name'), 'heading': source.get('heading'),
            'source_refs': [], 'material': [], 'originals': []})
        spans = [{k: p[k] for k in ('block_id', 'start_cp', 'end_cp')}
                 | {'text_hash': digest(p['text'])} for p in source.get('spans', [])]
        if not spans:
            raise ContractError('read judgment requires original span coordinates')
        row['source_refs'].append(source['id'])
        row['material'].extend(digest([did, sid, p]) for p in spans)
        row['originals'].append({'reference_id': source['id'], 'source_id': sid,
            'document_id': did, 'spans': spans, 'text_hash': digest(source['text'])})
    for row in rows.values():
        row['material'] = sorted(set(row['material']))
    return rows


def context(inv, data, key):
    state = state_for(inv, data)
    # Replaying an accepted model result must use its exact old semantic view.
    previous = state.get('receipts', {}).get(key)
    if previous:
        return deepcopy(previous['context'])
    visible = originals(inv, data)
    heads = state.get('heads', {})
    required = [jid for jid, row in visible.items()
                if set(row['material']) - set(heads.get(jid, {}).get('seen_material', []))]
    return {'version': VERSION, 'request_key': request_key(inv, data),
        'state_hash': state.get('state_hash'), 'required': required,
        'current_originals': list(visible.values()), 'judgments': list(deepcopy(heads).values()),
        'needs': list(deepcopy(state.get('needs', {})).values()),
        'conflicts': list(deepcopy(state.get('conflicts', {})).values()),
        'previous_final_review': deepcopy(state.get('final_reviews', [])[-1:]),
        'retention_rule': 'Omitted previous judgments, needs and conflicts stay unchanged; opinions are not legal truth.'}


def review_schema(ctx, current, issues):
    ids = list(dict.fromkeys([r['id'] for r in ctx['current_originals']] + [r['id'] for r in ctx['judgments']]))
    refs = strings(current)
    row = obj({'judgment_id': {'enum': ids} if ids else {'type': 'string'},
        'operation': {'enum': ['SET', 'KEEP', 'WITHDRAW', 'CONFLICT']},
        'use': {'enum': USES}, 'finding': {'type': 'string', 'maxLength': 700},
        'reason': TEXT, 'issue_refs': strings(issues, minimum=1), 'basis_refs': refs,
        'missing': {'type': 'array', 'maxItems': 4, 'uniqueItems': True, 'items': TEXT},
        'conflicts_with': strings(ids)})
    def updates(items):
        return {'type': 'array', 'maxItems': len(items), 'items': obj({
            'id': {'enum': [r['id'] for r in items]} if items else {'type': 'string'},
            'status': {'enum': ['OPEN', 'RESOLVED', 'NOT_NEEDED']}, 'reason': TEXT,
            'basis_refs': deepcopy(refs)})}
    return obj({'judgments': {'type': 'array', 'maxItems': len(ids), 'items': row},
        'need_updates': updates(ctx['needs']), 'conflict_updates': updates(ctx['conflicts'])})


def attach(schema, ctx, current, issues):
    value = deepcopy(schema)
    ids = list(dict.fromkeys([r['id'] for r in ctx['current_originals']] + [r['id'] for r in ctx['judgments']]))
    for branch in value['anyOf']:
        branch['properties']['read_review'] = wire_review_schema(ctx, current, issues)
        branch['required'].append('read_review')
        if branch['properties']['choice']['const'] not in ('FINISH', 'PENDING'):
            target = branch['properties']['selections']['items'] if branch['properties']['choice']['const'] == 'READ' else branch
            target['properties']['judgment_refs'] = strings(ids, minimum=1 if ids else 0)
            target['required'].append('judgment_refs')
    return value


def wire_review_schema(ctx, current, issues):
    """Do not ask the model to regenerate host-owned retained opinions."""
    schema = review_schema(ctx, current, issues)
    row = schema['properties']['judgments']['items']
    alternatives = []
    for op in ('SET', 'CONFLICT', 'KEEP', 'WITHDRAW'):
        if op in ('KEEP', 'WITHDRAW') and not ctx['judgments']:
            continue
        branch = deepcopy(row)
        branch['properties']['operation'] = {'const': op}
        if op in ('KEEP', 'WITHDRAW'):
            branch['properties']['judgment_id'] = {'enum': [h['id'] for h in ctx['judgments']]}
            # Optional legacy fields stay verifiable at ingestion, but are
            # hidden by the existing wire projection. They never change a head.
            for name in ('finding','use','issue_refs','missing','conflicts_with'):
                branch['required'].remove(name)
                branch['properties'][name]['readOnly'] = True
        alternatives.append(branch)
    schema['properties']['judgments']['items'] = {'type':'object', 'anyOf':alternatives}
    return schema


def normalize_review(value, ctx):
    """Pure reconstruction from an exact prior head, never semantic repair."""
    from .output_contract import OutputContractError, issue
    result = deepcopy(value); changes = []
    old = {r['id']:r for r in ctx['judgments']}
    for index, row in enumerate(result['read_review']['judgments']):
        op = row['operation']
        if op not in ('KEEP','WITHDRAW'):
            continue
        prior = old.get(row['judgment_id'])
        path = '/read_review/judgments/' + str(index)
        errors = []
        if prior is None:
            errors.append(issue('READ_JUDGMENT_UNKNOWN_PRIOR',path+'/judgment_id'))
        else:
            expected = {'finding':'', 'use':prior['use'] if op=='KEEP' else 'EXCLUDE',
                'issue_refs':prior['issue_refs'], 'missing':[], 'conflicts_with':[]}
            for name, fixed in expected.items():
                if name not in row:continue
                valid = row[name] == fixed
                if name=='finding':valid = row[name] in ('',prior['finding'])
                if not valid:
                    errors.append(issue('READ_JUDGMENT_RETAINED_FIELD_CHANGED',path+'/'+name,
                        expected='KEEP/WITHDRAW preserves prior content; changed content or new needs requires explicit SET/CONFLICT'))
        if errors:
            raise OutputContractError('retained judgment contains an unapproved change',errors,category='DECISION_CONFLICT')
        for name, fixed in expected.items():
            if name not in row or row[name] != fixed:
                changes.append({'judgment_id':row['judgment_id'],'field':name,
                    'rule':'EXACT_PRIOR_FINDING_REPEATED' if name=='finding' and name in row else 'RETAINED_HOST_FIELD',
                    'before_present':name in row,'before':deepcopy(row.get(name)),'after':deepcopy(fixed)})
            row[name] = deepcopy(fixed)
    return result, changes


def correction_scope(ctx):
    """Stable across menu/presentation aliases and final-review prose changes."""
    return {'contract':WIRE_VERSION,'request_key':ctx['request_key'],
        'originals':sorted([{'id':r['id'],'material':sorted(r['material'])}
            for r in ctx['current_originals']],key=lambda r:r['id']),
        'judgments':sorted([{'id':h['id'],'version':h['version']}
            for h in ctx['judgments']],key=lambda h:h['id'])}


def validate_review(value, ctx, current, issues):
    review = value['read_review']
    validate(review, review_schema(ctx, current, issues))
    old = {r['id']: r for r in ctx['judgments']}
    visible = {r['id']: r for r in ctx['current_originals']}
    ids = [r['judgment_id'] for r in review['judgments']]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append('one judgment update per original bundle')
    if set(ctx['required']) - set(ids):
        problems.append('newly delivered originals omitted from read review')
    for row in review['judgments']:
        jid = row['judgment_id']; prior = old.get(jid); op = row['operation']
        if jid not in visible and jid not in old:
            problems.append('unknown judgment identity')
        if not row['basis_refs'] or not row['reason'].strip():
            problems.append('judgment requires current original evidence and reason')
        if op in ('KEEP', 'WITHDRAW'):
            if not prior or row['finding'] or row['missing'] or row['conflicts_with']:
                problems.append('KEEP/WITHDRAW retains prior finding; no silent replacement or new needs')
            if prior and row['use'] != (prior['use'] if op == 'KEEP' else 'EXCLUDE'):
                problems.append('KEEP retains use; WITHDRAW explicitly excludes')
        elif not row['finding'].strip():
            problems.append('new/revised/conflicting judgment requires finding')
        if jid in visible and not (set(row['basis_refs']) & set(visible[jid]['source_refs'])):
            problems.append('review must cite its currently delivered original bundle')
        if op == 'CONFLICT' and (not row['conflicts_with'] or row['use'] != 'DEFER'):
            problems.append('unresolved conflict retains both opinions and defers use')
        if op != 'CONFLICT' and row['conflicts_with']:
            problems.append('conflicts_with requires explicit CONFLICT operation')
        for other in row['conflicts_with']:
            if other == jid and not prior or other not in old and other not in ids:
                problems.append('conflict must bind an existing or same-response judgment')
    reobserved = {'N' + digest([r['judgment_id'], ' '.join(t.split())])[:24]
                  for r in review['judgments'] for t in r['missing']}
    if any(u['id'] in reobserved and u['status'] != 'OPEN' for u in review['need_updates']):
        problems.append('same response cannot reopen and close the same need')
    for field, known in [('need_updates', ctx['needs']), ('conflict_updates', ctx['conflicts'])]:
        known = {r['id']: r for r in known}; seen = set()
        for update in review[field]:
            if update['id'] in seen:
                problems.append('duplicate need/conflict update')
            seen.add(update['id'])
            if update['status'] == 'RESOLVED' and not update['basis_refs']:
                problems.append('resolution requires current original evidence')
            if not update['reason'].strip():
                problems.append('need/conflict update requires reason')
            if field == 'conflict_updates' and update['status'] == 'RESOLVED':
                conflict = known[update['id']]
                from .read_judgment_final import covered
                offered = [{'source_id':current[ref]['source_id'],'document_id':current[ref]['document_id'],
                            **span,'text_hash':digest(span['text'])}
                           for ref in update['basis_refs'] for span in current[ref]['spans']]
                if not all(covered(opinion['basis'],offered) for opinion in conflict['opinions']):
                    problems.append('conflict resolution must retain exact original evidence from both sides')
    if value['choice'] not in ('FINISH', 'PENDING'):
        for action in value['selections'] if value['choice'] == 'READ' else [value]:
            refs = action['judgment_refs']
            if (old or visible) and not refs or set(refs) - (set(old) | set(ids)):
                problems.append('next action must refer to retained/reviewed judgment')
            linked = [next((r for r in review['judgments'] if r['judgment_id'] == j), old.get(j)) for j in refs]
            if any(action['issue_id'] not in r['issue_refs'] for r in linked if r):
                problems.append('next action and judgment must bind the same question issue')
    if problems:
        raise ProposalError('; '.join(dict.fromkeys(problems)))


def record(inv, data, value, key, ctx, actions, *, wire_value=None, normalizations=()):
    state = state_for(inv, data)
    proposal_hash = digest(value)
    previous = state.get('receipts', {}).get(key)
    if previous:
        if previous['proposal_hash'] != proposal_hash or previous['context'] != ctx:
            raise ContractError('accepted read judgment proposal/context changed')
        return
    if ctx['request_key'] != request_key(inv, data) or ctx['state_hash'] != state.get('state_hash'):
        raise ContractError('stale read judgment revision')
    current = {s['id']: s for s in data.get('sources', []) if s.get('text')}
    validate_review(value, ctx, current, [i['id'] for i in data['issues']])
    from . import evidence_inventory as inventory
    for row in value['read_review']['judgments']:
        for ref in row['basis_refs']:
            inventory.check_presented_page(inv.s, inv.p, current[ref])
    for field in ('need_updates', 'conflict_updates'):
        for update in value['read_review'][field]:
            for ref in update['basis_refs']:
                inventory.check_presented_page(inv.s, inv.p, current[ref])
    ns = deepcopy(state) if state else {'version': VERSION, 'request_key': ctx['request_key'],
        'heads': {}, 'needs': {}, 'conflicts': {}, 'history': [], 'receipts': {}}
    visible = originals(inv, data)
    if list(visible.values()) != ctx['current_originals']:
        raise ContractError('read judgment original presentation changed')
    originals_by_ref = {r['reference_id']: r for bundle in visible.values() for r in bundle['originals']}
    def basis(refs):
        return [deepcopy(originals_by_ref[r]) for r in refs]
    changes = []
    for row in value['read_review']['judgments']:
        jid = row['judgment_id']; prior = deepcopy(ns['heads'].get(jid)); original = visible.get(jid, prior)
        head = {k: deepcopy(original[k]) for k in ('source_id', 'document_id')}
        head.update(document_name=original.get('document_name'),heading=original.get('heading'),
            id=jid, version=(prior['version'] + 1 if prior else 1), operation=row['operation'],
            use=row['use'], finding=prior['finding'] if row['operation'] in ('KEEP', 'WITHDRAW') else row['finding'],
            reason=row['reason'], issue_refs=row['issue_refs'], basis=basis(row['basis_refs']),
            seen_material=sorted(set((prior or {}).get('seen_material', [])) | set(visible.get(jid, {}).get('material', []))),
            previous_version=prior['version'] if prior else None)
        ns['heads'][jid] = head
        changes.append({'previous': prior, 'current': deepcopy(head)})
        for text in row['missing']:
            nid = 'N' + digest([jid, ' '.join(text.split())])[:24]
            # Re-observing a closed need reopens it explicitly; no duplicate row.
            need = ns['needs'].get(nid)
            ns['needs'][nid] = {'id': nid, 'judgment_id': jid, 'text': text, 'issue_refs': row['issue_refs'],
                'status': 'OPEN', 'reason': row['reason'], 'basis': basis(row['basis_refs']),
                'previous_status': need['status'] if need else None}
    for row in value['read_review']['judgments']:
        if row['operation'] != 'CONFLICT':
            continue
        jid = row['judgment_id']
        for other in row['conflicts_with']:
            left = state['heads'][other] if other == jid else ns['heads'][other]
            right = ns['heads'][jid]
            cid = 'X' + digest(sorted([(left['id'], left['version']), (right['id'], right['version'])]))[:24]
            ns['conflicts'][cid] = {'id': cid, 'status': 'OPEN', 'reason': row['reason'],
                'opinions': [deepcopy(left), deepcopy(right)], 'basis': basis(row['basis_refs'])}
    for field, target in [('need_updates', 'needs'), ('conflict_updates', 'conflicts')]:
        for update in value['read_review'][field]:
            item = ns[target][update['id']]
            item.update(status=update['status'], reason=update['reason'], basis=basis(update['basis_refs']))
    selected = value.get('selections', []) if value['choice'] == 'READ' else ([] if value['choice'] in ('FINISH', 'PENDING') else [value])
    receipt = {'key': key, 'proposal_hash': proposal_hash, 'context': deepcopy(ctx),
        'review': deepcopy(value['read_review']), 'changes': changes, 'choice': value['choice'],
        'next_actions': [{k: deepcopy(a[k]) for k in ('target', 'issue_id', 'missing_need', 'judgment_refs') if k in a}
            | {'action': deepcopy(actions.get(a.get('target')))} for a in selected],
        'automatic_adoption': False, 'additional_model_call': False}
    if wire_value is not None:
        receipt.update(wire_version=WIRE_VERSION,wire_proposal_hash=digest(wire_value),
            normalizations=deepcopy(list(normalizations)))
    ns['receipts'][key] = receipt
    ns['history'].append(key)
    ns['state_hash'] = seal(ns)
    inv.p.setdefault('read_judgments', {})[ctx['request_key']] = ns
    inv.s.repo.event('READ_JUDGMENT_RECORDED', {k: deepcopy(v) for k, v in receipt.items() if k != 'context'})
    inv.save()

"""Carry approved ontology meaning into the existing answer decision.

No source acquisition, model call, judgment or automatic adoption happens here.
The current ASSESS originals/options are the only permissible model references;
navigation E/page IDs must never leak into this different input namespace.
"""
from copy import deepcopy

from ..contracts import digest
from .errors import ContractError
from . import ontology_context as context, ontology_compiler as compiler
from . import ontology_input, evidence_inventory as inventory, unit_reading

VERSION = 'ontology-assessment-v1'
PROMPT = '''ontology_bundles는 승인된 개념·원문 연결 묶음이며 이번 질문의 정답이나 충분성 판정이 아니다. 각 provision의 source_refs는 이번 evidence_options의 실제 원문이다. semantic_plan이 있으면 측정 대상·산정 입력/방식·범위·조건·효과·예외 대상의 의존 순서를 원문과 함께 검토한다. EXPERIMENT_PROPOSAL_NOT_APPROVED는 과거 에이전트 판단에서 제안된 연구 지식이며 원문보다 우선하지 않는다. UNKNOWN은 미확보이며 거짓이나 0이 아니다. 서로 다른 효과와 그 조건·예외를 합치지 않고 현재 사안의 적용은 직접 판단한다. 원문과 개념·관계를 함께 보고 이번 응답에서 답변 내용(claims), 충족 범위(issue_assessments), 실제 부족(gaps)을 판단한다. COMPLETE는 등록 묶음의 원문이 제시되었다는 뜻이며 질문 해결을 보장하지 않는다. read_judgments에 아직 검토하지 않은 원문이 있으면 현재 원문과 evidence_options로 최종 사용 여부를 판단한다. assembly_catalog가 있으면 승인된 목적별 nodes/edges/typed slots와 정확 문장 body를 함께 검토한다. 조건·효과·분모·기준일·예외를 구분하고 unresolved의 미확인을 없애지 않는다. 각 경로의 source_refs는 현재 입력 원문이며 package_sha256·판본은 재사용 추적용이다. 경로 선택·충분성과 실제 답변 claims는 이번 질문에 대해 판단한다. 등록 연결이나 남은 탐색 항목이 있다는 이유만으로 추가 조사하지 않는다. 답변에 필요한 핵심 원문이 부족하면 기존 gaps에 필요한 내용과 다음 행동을 함께 적고, 확인하지 못한 부분은 그대로 남긴다.'''


def enabled(profile):
    policy = profile.get('candidate_navigation', {})
    return (context.enabled(policy) and policy.get('ontology_direct_assessment') is True
            and policy.get('completion_contract') is True
            and policy.get('ontology_context', {}).get('mode', 'A0') != 'A0')


def ready(inv):
    if not enabled(inv.s.profile):
        return False
    settings = context.config(inv)
    state = inv.p.get('ontology_context')
    if not state:
        return False
    _check_state(state, settings)
    return any(plan.get('fragments') for plan in state['plans'].values())


def _check_state(state, settings):
    if (state.get('version') != context.VERSION
            or state.get('snapshot_sha256') != settings['snapshot_sha256']):
        raise ContractError('ontology assessment checkpoint binding changed')


def _refs(spans, options):
    """Every non-whitespace original character must exist in current options."""
    refs = []
    for option in options:
        matches = [p for p in spans if str(p['block_id']) == str(option['block_id'])
                   and p['start_cp'] <= option['start_cp'] < option['end_cp'] <= p['end_cp']]
        if not matches or any(p['text'][option['start_cp']-p['start_cp']:
                                       option['end_cp']-p['start_cp']] != option['text'] for p in matches):
            raise ContractError('ontology assessment option content or range changed')
        refs.append(option['id'])
    intervals = inventory.intervals(options)
    for span in spans:
        cursor = span['start_cp']
        for lo, hi in intervals.get(str(span['block_id']), []):
            lo, hi = max(lo, span['start_cp']), min(hi, span['end_cp'])
            if hi <= cursor:
                continue
            if span['text'][cursor-span['start_cp']:lo-span['start_cp']].strip():
                return []
            cursor = hi
        if span['text'][cursor-span['start_cp']:].strip():
            return []
    return list(dict.fromkeys(refs))


def project(session, investigation, sources, options):
    """Recompile against current exact originals, including partial partitions.

    Acquisition receipts remain server-side. A provision omitted from ASSESS
    cannot expose its values or notes, even when an earlier menu delivered it.
    This does not reuse a navigation display or claim a successful delivery.
    """
    if not enabled(session.profile) or not investigation.get('ontology_context'):
        return {}
    if session.profile['candidate_navigation']['ontology_context'] == {'mode': 'DB'}:
        from ..ontology_work.runtime import config as database_config, recheck
        recheck(session, investigation)
        settings = database_config(session.profile['candidate_navigation'], investigation, investigation['binding'])
    else:
        settings = context.configuration(session.profile['candidate_navigation']['ontology_context'])
    state = investigation['ontology_context']; _check_state(state, settings)
    bundles = {b['bundle_id']: b for b in settings['snapshot']['bundles']}
    originals = {s['source_id']: s for s in sources}
    if len(originals) != len(sources):
        raise ContractError('ontology assessment source identity repeated')
    cards = []; proofs = []
    for plan in sorted(state['plans'].values(), key=lambda p: p['bundle_id']):
        bundle = bundles.get(plan['bundle_id'])
        if not bundle or plan['id'] != digest([investigation['binding'], settings['snapshot_sha256'], plan['bundle_id']]):
            raise ContractError('ontology assessment plan binding changed')
        if plan['status'] == 'NEEDS_REVIEW':
            cards.append({'plan_id': plan['id'], 'bundle_id': plan['bundle_id'],
                          'status': 'NEEDS_REVIEW', 'text': '판본·내용 변경으로 승인 묶음을 사용하지 않습니다.'})
            continue
        expected_anchors = {compiler.anchor_key(p['anchor']): p['anchor'] for p in bundle['provisions']}
        fragments = []; pending = deepcopy(plan['unresolved']); seen = set()
        for row in plan['fragments']:
            anchor = row['anchor']; key = compiler.anchor_key(anchor)
            if key in seen or anchor != expected_anchors.get(key):
                raise ContractError('ontology assessment anchor changed or repeated')
            seen.add(key)
            hit_offer, reason = context.resolve(session, anchor)
            if reason:
                raise ContractError('ontology assessment fragment binding changed: ' + reason)
            hit, offer = hit_offer
            wanted = set(map(str, offer['block_ids']))
            if row['source_id'] != hit['source_id'] or set(map(str, row['block_ids'])) != wanted:
                raise ContractError('ontology assessment own-block scope changed')
            original = originals.get(row['source_id'])
            if original and original['document_id'] != anchor['document_id']:
                raise ContractError('ontology assessment source document changed')
            # Current verified originals may use an equivalent, newer read receipt.
            # Binding, own-block coverage and full anchor content hash stay mandatory.
            spans = [p for p in (original or {}).get('adopted_spans', [])
                     if str(p['block_id']) in wanted]
            expected = inventory.expected(session, anchor['document_id'], offer['block_ids'])
            if not inventory.covers(expected, spans):
                pending.append({'anchor': deepcopy(anchor), 'reason': 'ASSESSMENT_ORIGINAL_NOT_PRESENTED'})
                continue
            text = unit_reading.reassemble([{'spans': spans}])
            if compiler.content_hash(text) != anchor['content_sha256']:
                raise ContractError('ontology assessment original content changed')
            offered = [o for o in options if o['source_id'] == row['source_id']
                    and o['document_id'] == anchor['document_id'] and str(o['block_id']) in wanted
                    and o['evidence_id'] in {p['evidence_id'] for p in spans}]
            refs = _refs(spans, offered)
            if not refs:
                pending.append({'anchor': deepcopy(anchor), 'reason': 'ASSESSMENT_EVIDENCE_NOT_PRESENTED'})
                continue
            fragments.append({'anchor': deepcopy(anchor), 'text': text, 'evidence_refs': refs})
        compiled = compiler.compile_bundle(bundle, fragments, unresolved=pending,
            remaining_connections=plan['remaining_connections'], mode=settings['mode'])
        payload = deepcopy(compiled['payload'])
        if settings.get('semantic_binding'):
            from .ontology_semantics import compile_plan
            semantic=compile_plan(settings['semantic_binding'],fragments)
            payload['semantic_plan']=semantic
        # The compiler sees only this input's fragments. Do not confuse its
        # missing-fragment marker with the durable acquisition ledger.
        payload['unresolved'] = [r for r in payload['unresolved']
            if not (r.get('reason') == 'SOURCE_NOT_ACQUIRED'
                    and compiler.anchor_key(r['anchor']) in seen)]
        for provision in payload['provisions']:
            provision.pop('text', None)
            provision['source_refs'] = provision.pop('evidence_refs', [])
            provision['delivery_status'] = 'PREPARED' if provision['source_refs'] else 'NOT_SENT'
            if compiler.anchor_key(provision['anchor']) in seen:
                provision['acquisition_status'] = 'ACQUIRED'
        if payload['status'] != 'COMPLETE':
            payload['review_notes_status'] = 'WITHHELD_UNTIL_ALL_ORIGINALS_PRESENTED'
        payload = ontology_input.payload(payload)
        package=settings.get('scenario_packages',{}).get(bundle['bundle_id']) or settings.get('scenario_package')
        if package and package['bundle_id']==bundle['bundle_id']:
            from .ontology_scenarios import bind_current
            payload['scenario_catalog']=bind_current(package,fragments)
        assembly=settings.get('assembly_packages',{}).get(bundle['bundle_id']) or settings.get('assembly_package')
        if assembly and assembly['bundle_id']==bundle['bundle_id']:
            from ..ontology_work.assembly_compiler import bind_current
            payload['assembly_catalog']=bind_current(assembly,fragments)
        cards.append({'contract': VERSION, 'plan_id': plan['id'], 'mode': settings['mode'],
            'status': compiled['status'], 'payload': payload,
            'presentation': {'kind': settings['mode'], 'sections': compiled['presentation']['sections'],
                             'originals': 'source_refs는 이번 evidence_options의 원문이다.'},
            'connection_scan': deepcopy(plan['scan'])})
        proofs.append({'plan_id': plan['id'], 'compiled_sha256': compiled['payload_sha256'],
                       'current_evidence_refs': [ref for f in fragments for ref in f['evidence_refs']]})
    from ..ontology_work.runtime import assessment_references
    return {'ontology_bundles': cards, 'ontology_assessment': {
        'version': VERSION, 'snapshot_sha256': settings['snapshot_sha256'],
        'workspace_publications': assessment_references(investigation, cards),
        'proofs': proofs, 'delivery_status': 'PREPARED_NOT_SENT',
        'automatic_adoption': False, 'evidence_sufficient': False}}


def usage_schema(schema, payload):
    """Optional for old clients; absence never means adoption."""
    if not payload:
        return schema
    schema = deepcopy(schema)
    from .completion_contracts import obj
    schema['properties']['ontology_usage'] = {'type': 'array', 'items': obj({
        'package_sha256': {'type': 'string'}, 'path_id': {'type': 'string'},
        'node_ids': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'uniqueItems': True},
        'claim_id': {'type': 'string'}})}
    return schema


def usage_core(value, schema, payload):
    """Only explicit model use with current path, node AND claim evidence."""
    from .errors import ProposalError
    value, schema = deepcopy(value), deepcopy(schema)
    usage = value.pop('ontology_usage', None)
    schema['properties'].pop('ontology_usage', None)
    if usage is None:
        return value, schema, None
    if not isinstance(usage, list):
        raise ProposalError('ontology usage must be an array')
    paths = {(c['payload']['assembly_catalog']['package_sha256'], p['id']): p
        for c in payload.get('ontology_bundles', []) if c.get('payload', {}).get('assembly_catalog')
        for p in c['payload']['assembly_catalog']['paths']}
    claims = {c['claim_id']: c for c in value.get('claims', [])}
    seen = set()
    for index, row in enumerate(usage):
        if not isinstance(row, dict) or set(row) != {'package_sha256', 'path_id', 'node_ids', 'claim_id'}:
            raise ProposalError('ontology usage fields changed')
        path = paths.get((row['package_sha256'], row['path_id']))
        claim = claims.get(row['claim_id'])
        if not path or not claim or not isinstance(row['node_ids'], list) or not row['node_ids']:
            raise ProposalError('ontology usage references an unoffered path or claim')
        nodes = {n['id']: n for n in path['nodes']}
        if len(set(row['node_ids'])) != len(row['node_ids']) or set(row['node_ids']) - nodes.keys():
            raise ProposalError('ontology usage references an unoffered node')
        # bind_current supplied exact complete originals of this path. A mere
        # matching document/package ID is insufficient for an adoption receipt.
        if not set(path['source_refs']) <= set(claim.get('evidence_refs', [])):
            from .output_contract import OutputContractError, issue
            raise OutputContractError('ontology usage lacks the path original evidence in this claim',
                [issue('ONTOLOGY_PATH_EVIDENCE', '/ontology_usage/'+str(index),
                    related=['/claims'],
                    expected={'claim_id': row['claim_id'], 'path_id': row['path_id'],
                        'required_evidence_refs': path['source_refs'],
                        'claim_evidence_refs': claim.get('evidence_refs', []),
                        'allowed_repair': 'Reconsider the selected path/nodes and claim evidence from current originals. Do not add unchosen sources or change legal meaning automatically.'})],
                category='DECISION_CONFLICT')
        key = digest(row)
        if key in seen:
            raise ProposalError('duplicate ontology usage')
        seen.add(key)
    return value, schema, usage


def explanation(payload, *, decision_key, usage=None, received=False, enabled=False):
    bundles = []
    for card in payload.get('ontology_bundles', []):
        catalog = card.get('payload', {}).get('assembly_catalog')
        bundles.append({'bundle_id': card.get('bundle_id') or card.get('payload', {}).get('bundle_id'),
            'status': card['status'], 'assembly': deepcopy(catalog),
            'adoption': 'NOT_RECORDED' if usage is None else 'ADOPTED' if catalog and any(r['package_sha256']==catalog['package_sha256'] for r in usage) else 'NOT_USED',
            'claim_uses': [r for r in usage or [] if catalog and r['package_sha256'] == catalog['package_sha256']]})
    return {'status': 'RESPONSE_RECEIVED' if received and payload else 'PREPARED_NOT_SENT' if payload else 'NO_RESULTS' if enabled else 'OFF',
        'input_hash': digest(payload), 'decision_key': decision_key,
        'workspace_publications': deepcopy(payload.get('ontology_assessment', {}).get('workspace_publications', [])),
        'adoption': 'NOT_RECORDED' if usage is None else 'RECORDED', 'bundles': bundles}


def accepted_uses(assessment):
    """Project explicit, validated claim use; delivered packages are not use."""
    review=assessment.get('review_explanation')
    if not review:return []  # Legacy judgments never gain inferred adoption.
    from .review_explanation import verify
    verify(review)
    if assessment.get('source_excerpt_reply'):return []
    ontology=review.get('ontology',{})
    if ontology.get('status')!='RESPONSE_RECEIVED' or ontology.get('adoption')!='RECORDED':return []
    claims={c.get('claim_id') for c in assessment.get('claims',[])}
    uses=[]
    for bundle in ontology.get('bundles',[]):
        if bundle.get('adoption')!='ADOPTED':continue
        for use in bundle.get('claim_uses',[]):
            if use['claim_id'] not in claims:
                raise ContractError('accepted ontology use lost its claim')
            uses.append({'bundle_id':bundle['bundle_id'],**deepcopy(use)})
    return uses

PROMPT += '\nontology_usage는 이번 claims에 실제 사용한 assembly_catalog의 package_sha256/path_id/node_ids/claim_id 연결이다. 사용하지 않았다면 []로 둔다. 선택 경로의 source_refs를 해당 claim.evidence_refs에 모두 포함한다. 단순 조회나 원문 인용만으로 온톨로지 사용을 주장하지 않는다.'

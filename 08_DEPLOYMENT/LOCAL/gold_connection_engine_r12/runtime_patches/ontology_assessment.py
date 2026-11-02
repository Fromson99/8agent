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
        from ..ontology_work.runtime import config as database_config
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
    return {'ontology_bundles': cards, 'ontology_assessment': {
        'version': VERSION, 'snapshot_sha256': settings['snapshot_sha256'],
        'proofs': proofs, 'delivery_status': 'PREPARED_NOT_SENT',
        'automatic_adoption': False, 'evidence_sufficient': False}}

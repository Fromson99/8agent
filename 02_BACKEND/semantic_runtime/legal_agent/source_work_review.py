"""Project acquired-source bookkeeping from explicit model-owned scope reviews.

No legal status, missing acquisition or source partition is inferred. The full
canonical review still passes every existing judgment/need/scope validator.
"""
from copy import deepcopy
from . import need_continuity
from .errors import ProposalError
from .output_contract import OutputContractError, issue, validate_shape

VERSION = 'source-work-review-v1'
PROMPT = ('read_judgments.needs 중 SOURCE_GOAL/STRUCTURE_SELECTION의 확보 완료 항목은 '
    '서버가 scope_reviews의 명시적 USE/EXCLUDE/OPEN과 실제 연결로 조립한다. '
    'needs 응답에는 스키마가 제시하는 ID만 작성한다. scope_reviews의 모든 대상·원문 범위와 '
    'judgments, 독립적인 의미상 need·conflict·요구 검토는 계속 직접 판단한다. '
    '원문 확보 또는 조사 작업 완료가 법률 쟁점의 해결을 뜻하지 않는다.')


def eligible(ctx, options):
    if not ctx or ctx.get('need_continuity', {}).get('version') != need_continuity.VERSION:
        return []
    targets = {t['id']: t for t in ctx['need_continuity']['targets']}
    return [n for n in ctx['needs'] if n.get('origin') in ('SOURCE_GOAL', 'STRUCTURE_SELECTION')
        and n.get('target_refs') and all(tid in targets and targets[tid]['available_evidence_refs']
            and need_continuity.available(targets[tid], options) for tid in n['target_refs'])]


def derived(value, ctx, options):
    targets = {t['id']: t for t in ctx['need_continuity']['targets']}
    reviews = value['read_judgment_review'].get('scope_reviews', [])
    def fail(path, **expected):
        raise OutputContractError('조사 장부는 명시적으로 검토한 전체 원문 범위에서만 조립합니다.',
            [issue('SOURCE_WORK_SCOPE_REQUIRED', path, expected=expected)], category='FINAL_READ_REVIEW_INVALID')
    rows = []
    for need in eligible(ctx, options):
        groups = []
        for tid in need['target_refs']:
            found = [(i, r) for i, r in enumerate(reviews) if r['target_id'] == tid]
            if len(found) != 1:
                fail('/read_judgment_review/scope_reviews', target_id=tid, required='exactly one scope review')
            index, review = found[0]
            refs = [ref for g in review['groups'] for ref in g['basis_refs']]
            permitted = set(targets[tid]['available_evidence_refs'])
            if len(refs) != len(set(refs)) or set(refs) != permitted:
                fail('/read_judgment_review/scope_reviews/'+str(index)+'/groups', target_id=tid,
                    required='each available range exactly once', allowed_evidence_refs=sorted(permitted))
            groups.extend(review['groups'])
        opened = [g for g in groups if g['disposition'] == 'OPEN']
        rows.append({'id': need['id'], 'status': 'OPEN' if opened else 'RESOLVED',
            'material': bool(opened),
            'reason': '범위 검토에서 보류한 확인 사항이 남아 있습니다.' if opened else '확보한 원문의 범위별 검토 결과를 연결했습니다.',
            'basis_refs': sorted({r for g in groups for r in g['basis_refs']}),
            'claim_refs': [] if opened else sorted({c for g in groups if g['disposition'] == 'USE' for c in g['claim_refs']}),
            'gap_indices': sorted({i for g in opened for i in g['gap_indices']}),
            'target_refs': list(need['target_refs']), 'scope_quote': ''})
    return rows


EXCLUSION_PROMPT = (
    'NOT_NEEDED는 이 검토 항목이 이번 답에 불필요하다는 직접 판단이다. '
    'exclusion_basis=ORIGINALS는 실제 basis_refs를 하나 이상 선택한다. '
    'CURRENT_REQUEST는 현재 사용자 질문 전체를 그대로 근거로 선택한다. '
    'REQUEST_SPAN은 질문의 연속 구간을 0부터 세는 유니코드 start_cp와 끝을 포함하지 않는 end_cp로 선택한다. '
    'scope_quote를 새 문장으로 쓰지 않는다. 선택한 구간만 서버가 복원한다. '
    '이 선택은 원문 사용, 주장 채택, 미확인 근거 검사를 대신하지 않는다.')


def _exclusion_options(branch, need, targets, question):
    """Every wire option names the evidence for this model-owned exclusion."""
    properties = branch['properties']
    properties.pop('scope_quote')
    properties['claim_refs']['maxItems'] = 0
    properties['gap_indices']['maxItems'] = 0
    branch['required'].remove('scope_quote')
    branch['required'].append('exclusion_basis')
    empty_source_target = need.get('origin') in ('SOURCE_GOAL', 'STRUCTURE_SELECTION') and any(
        not targets[tid]['available_evidence_refs'] for tid in need.get('target_refs', []))
    if not empty_source_target:
        original = deepcopy(branch)
        original['properties']['exclusion_basis'] = {'const': 'ORIGINALS'}
        original['properties']['basis_refs']['minItems'] = 1
        yield original
    if question.strip():
        whole = deepcopy(branch)
        whole['properties']['exclusion_basis'] = {'const': 'CURRENT_REQUEST'}
        yield whole
        span = deepcopy(branch)
        span['properties']['exclusion_basis'] = {'const': 'REQUEST_SPAN'}
        span['properties']['quote_span'] = {
            'type': 'object', 'additionalProperties': False,
            'properties': {
                'start_cp': {'type': 'integer', 'minimum': 0, 'maximum': len(question)-1},
                'end_cp': {'type': 'integer', 'minimum': 1, 'maximum': len(question)}},
            'required': ['start_cp', 'end_cp']}
        span['required'].append('quote_span')
        yield span


def _restore_exclusions(rows, question):
    for index, row in enumerate(rows):
        if row['status'] != 'NOT_NEEDED':
            continue
        basis = row.pop('exclusion_basis')
        if basis == 'ORIGINALS':
            row['scope_quote'] = ''
        elif basis == 'CURRENT_REQUEST':
            row['scope_quote'] = question
        else:
            span = row.pop('quote_span')
            start, end = span['start_cp'], span['end_cp']
            quote = question[start:end]
            if not quote.strip():
                raise OutputContractError(
                    '제외 근거는 현재 질문의 비어 있지 않은 연속 구간이어야 합니다.',
                    [issue('NEED_EXCLUSION_QUESTION_SPAN', f'/read_judgment_review/needs/{index}/quote_span',
                           expected={'start_before_end': True, 'question_length': len(question)})],
                    category='FINAL_READ_REVIEW_INVALID')
            row['scope_quote'] = quote


def projection(schema, ctx, options):
    if not ctx or ctx.get('need_continuity', {}).get('version') != need_continuity.VERSION:
        return deepcopy(schema), deepcopy
    host_ids = {n['id'] for n in eligible(ctx, options)}
    wire = deepcopy(schema)
    needs = wire['properties']['read_judgment_review']['properties']['needs']
    explicit = [n['id'] for n in ctx['needs'] if n['id'] not in host_ids]
    needs.update(minItems=len(explicit), maxItems=len(explicit))
    needs['items']['properties']['id'] = {'enum': explicit} if explicit else {'type': 'string'}
    targets = {t['id']: t for t in ctx['need_continuity']['targets']}
    blocked = {n['id'] for n in ctx['needs'] if any(
        tid not in targets or not need_continuity.available(targets[tid], options)
        for tid in n.get('target_refs', []))}
    # Expose status/field relations already enforced by the canonical validator.
    # The model still owns the status, reason, originals, claim and gap choices.
    by_id = {n['id']: n for n in ctx['needs']}
    question = ctx['need_continuity']['question']
    branches = []
    for ident in explicit:
        for status in needs['items']['properties']['status']['enum']:
            if status == 'RESOLVED' and ident in blocked:continue
            branch = deepcopy(needs['items']);props = branch['properties']
            props['id'] = {'const': ident};props['status'] = {'const': status}
            if status == 'OPEN':
                props['material'] = {'const': True}
                props['claim_refs']['maxItems'] = 0
                props['gap_indices']['minItems'] = 1
                props['scope_quote'] = {'const': ''}
            elif status == 'NOT_NEEDED':
                branches.extend(_exclusion_options(branch, by_id[ident], targets, question))
                continue
            else:
                props['claim_refs']['minItems'] = 1
                props['basis_refs']['minItems'] = 1
                props['gap_indices']['maxItems'] = 0
                props['scope_quote'] = {'const': ''}
            branches.append(branch)
    if branches:needs['items'] = {'anyOf': branches}
    def expand(raw):
        try:
            validate_shape(raw, wire)
            value = deepcopy(raw)
            _restore_exclusions(value['read_judgment_review']['needs'], question)
            value['read_judgment_review']['needs'].extend(derived(value, ctx, options))
            validate_shape(value, schema)
            return value
        except ProposalError as exc:
            exc.proposal = deepcopy(raw)
            raise
    return wire, expand


def repair_proposal(value, ctx, options):
    """Remove only an exactly reconstructed host suffix, never a raw bad row."""
    if not eligible(ctx, options) or not isinstance(value, dict):
        return deepcopy(value)
    # Only expanded shared-review proposals can have a host-owned suffix.
    from . import assessment_links
    from ..contracts import digest
    receipt = value.get(assessment_links.FIELD)
    if not isinstance(receipt, dict) or receipt.get('receipt_hash') != digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):
        return deepcopy(value)
    try:
        rows = derived(value, ctx, options)
        original = value['read_judgment_review']['needs']
        if original[-len(rows):] != rows:
            return deepcopy(value)
    except (ProposalError, KeyError, TypeError):
        return deepcopy(value)
    result = deepcopy(value)
    result['read_judgment_review']['needs'] = result['read_judgment_review']['needs'][:-len(rows)]
    return result

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


def projection(schema, ctx, options):
    host_ids = {n['id'] for n in eligible(ctx, options)}
    if not host_ids:
        return deepcopy(schema), deepcopy
    wire = deepcopy(schema)
    needs = wire['properties']['read_judgment_review']['properties']['needs']
    explicit = [n['id'] for n in ctx['needs'] if n['id'] not in host_ids]
    needs.update(minItems=len(explicit), maxItems=len(explicit))
    needs['items']['properties']['id'] = {'enum': explicit} if explicit else {'type': 'string'}
    def expand(raw):
        try:
            validate_shape(raw, wire)
            value = deepcopy(raw)
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

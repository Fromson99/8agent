from common import *
S=ROOT/read(DES/'candidate-path.json')['snapshot'];D=S/'02_BACKEND/semantic_runtime/legal_agent'
p=D/'assessment_input.py';s=p.read_text().replace("VERSION = 'lossless-assessment-input-v1'", "VERSION = 'lossless-assessment-input-v2'\nSUPPORTED_VERSIONS = ('lossless-assessment-input-v1', VERSION)")
s=s.replace("INSTRUCTIONS = ('ASSESS 입력의 current_case.facts와 current_case.scenario가 현재 사실과 가정이다. '","INSTRUCTIONS = ('일반 ASSESS의 current_facts는 현재 사실이다. 가정 검토에서는 current_case.facts와 current_case.scenario가 현재 사실과 가정이다. '")
s=s.replace("return ((stage or view.get('source_stage')) in ('memory-assess', 'memory-assess-repair')\n            and 'hypothetical_scenario' in view)","return (stage or view.get('source_stage')) in ('memory-assess', 'memory-assess-repair')")
s=s.replace("meta.get('version') != VERSION", "meta.get('version') not in SUPPORTED_VERSIONS")
p.write_text(s)
p=D/'completion_execution.py';s=p.read_text().replace('from . import assessment_links, scenario_application, scenario_computation','from . import assessment_links, scenario_application, scenario_computation, source_work_review')
s=s.replace('shared_reviews=bool(scenario_context and (judgment_context is not None or requirement_context is not None))','shared_reviews=bool(modern and (judgment_context is not None or requirement_context is not None))\n        host_source_work=source_work_review.eligible(judgment_context,options) if modern else []')
s=s.replace("if shared_reviews:basis['review_links_version']=assessment_links.VERSION", "if shared_reviews:basis['review_links_version']=assessment_links.VERSION\n        if host_source_work:basis['source_work_review_version']=source_work_review.VERSION")
s=s.replace("assessment_links.repair_proposal(prior.get('proposal'))", "assessment_links.repair_proposal(source_work_review.repair_proposal(prior.get('proposal'),judgment_context,options))")
s=s.replace('assessment_links.repair_proposal(value)', 'assessment_links.repair_proposal(source_work_review.repair_proposal(value,judgment_context,options))')
s=s.replace("if shared_reviews:answer_policy += '\\n'+assessment_links.PROMPT", "if shared_reviews:answer_policy += '\\n'+assessment_links.PROMPT\n        if host_source_work:answer_policy += '\\n'+source_work_review.PROMPT")
s=s.replace('        if shared_reviews:\n            generation_schema,expand_links', '        if host_source_work:\n            generation_schema,expand_work=source_work_review.projection(generation_schema,judgment_context,options)\n            expand_core=expand_assessment\n            expand_assessment=lambda raw:expand_core(expand_work(raw))\n        if shared_reviews:\n            generation_schema,expand_links')
p.write_text(s)
p=D/'source_work_review.py';p.write_text('''"""Project acquired-source bookkeeping from explicit model-owned scope reviews.

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
''')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ROOT/read(DES/'candidate-path.json')['candidate']
ac.register(C,'02_BACKEND/semantic_runtime/legal_agent/source_work_review.py',kind='candidate_only')
print('Edited 3 product modules in candidate only')

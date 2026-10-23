"""Bind norm quotes to delivered span IDs; never ask the model to recopy originals."""
from copy import deepcopy
from jsonschema import validate
from ..contracts import digest
from . import completion_v6 as v6, completion_v7 as v7
from .errors import ProposalError, ContractError

VERSION = 'investigation-completion-v8'
CONTENT = 'source-modality-v4'
PROMPT = '규정 내용은 rule에 한 번 작성하고 explanation=""로 둔다. 순수 설명은 rule=null과 근거에 연결한 explanation을 쓴다. rule의 subject·scope·action은 필수이며 action은 짧은 행위명이다. 발생 전제는 condition_tree, 효과·수치·기한·행동 의무는 norms, 예외는 exceptions로 구분한다. 별도 전제는 condition_tree=null이며 의무 자체를 전제로 중복하지 않는다.\nnorm.kind는 원문 맥락에 따른 OBLIGATION/PERMISSION/PROHIBITION/UNSPECIFIED다. norm.source_ref는 주된 원문 ID 하나이고 norm.evidence_refs에도 포함해야 한다. 인용문·위치·해시는 서버가 조립하므로 source_quote/conclusion/details를 작성하지 않는다. 같은 효과·적용 맥락은 한 norm으로 모은다. 원문의 조건·예외·주체와 특정 항·호의 준용 범위를 유지한다.\n필요한 자료·사실의 부족은 gaps, 확인된 내용은 claims에 함께 유지한다. 제외하거나 요청에 불필요한 내용을 gap으로 만들지 않으며 필요한 자료가 모두 있으면 gaps=[]다. 스키마의 필수 값과 제시된 ID만 사용한다.'


def assessment_schema(issues, materials, options, facts, previous_keys=()):
    schema = v7.assessment_schema(issues, materials, options, facts, previous_keys)
    def visit(node):
        if isinstance(node, dict):
            props = node.get('properties', {})
            if 'source_quote' in props:
                props.pop('source_quote')
                props['source_ref'] = {'type': 'string', 'enum': [o['id'] for o in options]}
                node['required'] = ['source_ref' if k == 'source_quote' else k for k in node['required']]
            if 'content_contract' in props: props['content_contract'] = {'const': CONTENT}
            if 'action' in props and 'norms' in props:
                props['action']['description'] = '필수 행위명. 빈 문자열 금지. 상세 효과는 norms에 쓰고 여기에는 짧은 행위명을 쓴다.'
            for value in node.values(): visit(value)
        elif isinstance(node, list):
            for value in node: visit(value)
    visit(schema)
    return schema


def as_v7(content):
    out = deepcopy(content); out['content_contract'] = v7.CONTENT
    for norm in (out.get('rule') or {}).get('norms', []): norm.pop('source_ref')
    return out


def compile_claim(content):
    out = v7.compile_claim(as_v7(content))
    out['answer_content'] = deepcopy(content)
    return out


def prepare(value, schema, issues, options, facts):
    validate(value, schema)
    canonical = deepcopy(value); offered = {o['id']: o for o in options}
    corrections = []; seen = set()
    # Narrative context can report a real missing source. Presentation preferences
    # must not prevent valid material gaps from reaching bounded investigation.
    # Each claim still passes source, condition, and final-content validation.
    for claim in canonical['claims']:
        for norm in (claim.get('rule') or {}).get('norms', []):
            ref = norm['source_ref']
            if ref not in norm['evidence_refs']:
                raise ProposalError('norm source_ref must belong to its selected evidence_refs')
            source = offered[ref]; norm['source_quote'] = source['text']
            context = {k: v for k, v in claim['rule'].items() if k != 'norms'}
            key = (source['source_id'], source['text'], norm['kind'],
                   ' '.join(norm['text'].split()), digest(context))
            # Reusing a verified norm across issues is not a source/meaning error.
            seen.add(key)
    normalized = deepcopy(canonical)
    normalized['claims'] = [v7.normalized(as_v7(c)) for c in canonical['claims']]
    materials = [g['material_id'] for g in value['gaps'] if g['material_id'] is not None]
    previous = [g['previous_gap_key'] for g in value['gaps'] if g.get('previous_gap_key')]
    accepted, model = v6.prepare(normalized,
        v6.assessment_schema(issues, materials, options, facts, previous), issues, options, facts)
    accepted['claims'] = [compile_claim(c) for c in canonical['claims']]
    model['norm_label_corrections'] = corrections
    return accepted, model


def materialize(value, options, issues, model):
    out = v6.materialize(value, options, issues, model)
    out['completion_contract'] = VERSION
    for claim in out['claims']: verify_content(claim)
    return out


def verify_content(claim):
    if 'answer_content' not in claim: return
    content = claim['answer_content']; expected = compile_claim(content)
    if any(claim.get(k) != v for k, v in expected.items()):
        raise ContractError('accepted source-bound content changed during rendering')
    receipts = {o['id']: o for o in claim.get('span_receipts', [])}
    for norm in (content.get('rule') or {}).get('norms', []):
        source = receipts.get(norm['source_ref'])
        if (not source or norm['source_ref'] not in norm['evidence_refs']
                or norm['source_quote'] != source['text']):
            raise ContractError('norm quote differs from its delivered source_ref receipt')

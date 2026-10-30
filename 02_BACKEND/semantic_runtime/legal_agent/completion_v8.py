"""Bind norm quotes to delivered span IDs; never ask the model to recopy originals."""
from copy import deepcopy
from jsonschema import validate
from ..contracts import digest
from . import completion_v6 as v6, completion_v7 as v7
from .errors import ProposalError, ContractError

VERSION = 'investigation-completion-v8'
CONTENT = 'source-modality-v4'
PROMPT = '''규칙·조건·의무·허용·금지·예외를 설명하는 claim은 rule에 작성하고 explanation=""로 둔다. 단순 요약이라는 이유로 규정을 rule=null의 설명으로 바꾸지 않는다. 순수 설명은 rule=null과 근거에 연결한 explanation을 쓴다.
rule의 subject·scope·action은 필수다. subject는 적용 주체·대상, scope는 해당 규칙의 적용 범위, action은 짧은 행위명이다. 발생 전제는 condition_tree, 효과·수치·기한·행동 의무는 norms, 예외는 exceptions에 연결한다. 별도 전제가 없으면 condition_tree=null이며 의무 자체를 전제로 중복하지 않는다.
norm.text는 답변에 표시할 완결된 효과를 쓴다. 수치만 쓰지 말고 그 수치가 적용되는 대상·산정 기준·단위·상한 조건·기간의 기산점을 포함한다. 적용 주체나 지역·시점의 한정은 subject/scope 또는 해당 norm.text에 명시한다. claim 전체에 적용되지 않는 조건을 공통 scope로 확대하지 않는다. exceptions는 어떤 효과의 예외인지 target과 text로 밝힌다. 같은 내용을 여러 필드에서 반복하지 않는다.
norm.kind는 원문 맥락에 따른 OBLIGATION/PERMISSION/PROHIBITION/UNSPECIFIED다. norm.source_ref는 주된 원문 ID 하나이며 norm.evidence_refs에도 포함한다. 추가 범위·조건을 뒷받침하는 현재 원문도 해당 evidence_refs에 연결한다. 인용문·위치·해시는 서버가 조립하므로 source_quote/conclusion/details를 작성하지 않는다. 자동 인용은 norm.text에서 빠뜨린 내용을 채워 주지 않는다. 같은 효과·적용 맥락은 한 norm으로 모으되 서로 다른 적용 범위를 합치지 않는다.
필요한 자료·사실의 부족은 gaps, 확인된 내용은 claims에 유지한다. 요청에 불필요한 내용은 gap으로 만들지 않으며 필요한 자료가 모두 있으면 gaps=[]다. 스키마의 필수 값과 제시된 ID만 사용한다.'''


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

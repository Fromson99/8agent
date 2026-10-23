"""Bind norm quotes to delivered span IDs; never ask the model to recopy originals."""
from copy import deepcopy
from jsonschema import validate
from ..contracts import digest
from . import completion_v6 as v6, completion_v7 as v7
from .errors import ProposalError, ContractError

VERSION = 'investigation-completion-v8'
CONTENT = 'source-modality-v4'
PROMPT = '''v8은 규정 내용을 한 번만 작성한다. conclusion/details/source_quote 필드는 쓰지 않는다.
규칙·조건·의무·허용·금지·예외는 rule에 작성하고 explanation은 빈 문자열로 둔다.
norm.source_ref는 그 효과의 주된 원문인 evidence_options의 ID 하나이며 반드시 해당 norm.evidence_refs에도 포함한다.
원문 인용을 다시 쓰거나 여러 원문을 연결하지 않는다. 서버가 선택한 ID의 정확한 원문을 붙인다.
norm.text에는 요청에 필요한 사실·금액·기한을 한 번만 쓴다. 적용 전제는 condition_tree, 효과는 norms에 구분한다.
norm.kind는 OBLIGATION/ PERMISSION/ PROHIBITION/ UNSPECIFIED다. 명시 원문의 양태와 일치시키며 불명확한 문구는 전체 맥락에서 판단하고, 판단할 수 없으면 UNSPECIFIED를 쓴다.
의무·허용·금지는 원문의 주체·행위·조건·예외와 전체 맥락으로 판단한다. 서버는 어미로 의미나 표지를 교체하지 않으며 선택 원문의 실제 일치·권한·버전을 검증한다.
같은 효과와 적용 맥락의 사실은 한 norm으로 모으고 여러 요구에 필요하면 issue_refs를 모은다.
규칙과 같은 내용을 되풀이하는 별도 요약 narrative는 작성하지 않는다. 필요한 별도 설명은 원문에 연결하며, 부족한 자료는 gaps에 반드시 기록한다. 순수 설명 요청은 모든 rule을 null로 두고 explanation을 한 번 쓴다.
gaps는 사용자가 요구한 답변을 완성하는 데 필요한 자료·사실의 부족만 기록한다.
사용자가 명시적으로 제외한 세부 항목이나 답변에 필요 없는 참조의 미조사는 MISSING_SOURCE/MISSING_FACT가 아니다. 이를 미확인이라고 설명하려고 gap을 만들지 말고 gaps에서 생략한다. 필요한 자료가 모두 있으면 gaps는 빈 배열이다. 제외한 내용을 읽었다고 주장하거나 근거로 사용하지 않는다.
요청한 범위의 실제 부족은 material=true로 보존하고 적절한 원문 탐색 행동을 고른다. 법령·서식 원문 미확인은 REQUEST_FACT가 아니다. REQUEST_FACT는 사용자가 특정 사건에 적용을 요청했고 그 결론에 필요한 실제 사실이 제공되지 않았을 때만 쓴다.
필요 없는 참조·시행령·서식의 세부 사항을 확장하지 않는다. 조건의 ALL/ANY/UNKNOWN 관계와 예외를 정확히 보존한다.
'''


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
            if key in seen:
                raise ProposalError('Repeated source clause, effect and context: merge identical facts and issue_refs')
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

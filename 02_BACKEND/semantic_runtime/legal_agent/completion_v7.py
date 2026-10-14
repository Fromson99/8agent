"""One authoritative source-backed body per claim, with historical v6 support."""
from copy import deepcopy
from jsonschema import validate
from . import completion_v6 as v6, completion_contracts as cc
from .errors import ProposalError, ContractError

VERSION='investigation-completion-v7'
CONTENT='source-modality-v3'
PROMPT='''v7에서는 같은 법률 내용을 conclusion/details/rule에 반복 작성하지 않는다. conclusion과 details 필드는 없다.
규칙·조건·의무·허용·금지·예외 질문은 rule을 작성하고 explanation은 빈 문자열로 둔다.
적용 대상은 subject, 행위는 action, 범위는 scope, 효과의 전제만 condition_tree에 쓴다.
norms의 text에는 필요한 효과와 구체 항목·수치·기한을 빠짐없이 한 번만 쓴다. 조건을 이행 의무로 중복 작성하지 않는다.
정의·비교 설명 등 양태가 없는 원문 사실도 필요한 경우 UNSPECIFIED norm으로 원문에 연결한다.
같은 source_quote로 설명을 여러 번 쓰지 않는다. 여러 요구에 필요한 동일 사실은 하나의 claim에 issue_refs를 모은다.
모든 claim이 구조화 규칙이면 별도 요약·비교 반복용 narrative claim을 추가하지 않는다. 의무/허용 표시는 코드가 추가하므로 영어 enum이나 같은 구분을 다시 설명하지 않는다.
구조화 규칙을 쓰지 않는 순수 설명 요청에만 모든 claim의 rule을 null로 두고 explanation에 완결된 설명을 한 번 쓴다.
norm.kind는 OBLIGATION(의무)/PERMISSION(허용)/PROHIBITION(금지)/UNSPECIFIED(미확정)다.
'''+'\n'.join(v6.PROMPT.split('\n')[1:3])


def assessment_schema(issues,materials,options,facts,previous_keys=()):
    schema=v6.assessment_schema(issues,materials,options,facts,previous_keys)
    claim=schema['properties']['claims']['items']
    for key in ('conclusion','details'):
        del claim['properties'][key];claim['required'].remove(key)
    claim['properties']['content_contract']={'const':CONTENT}
    claim['properties']['explanation']={'type':'string','maxLength':3000}
    claim['required'].append('explanation')
    structured,narrative=deepcopy(claim),deepcopy(claim)
    structured['properties']['rule']=deepcopy(claim['properties']['rule']['anyOf'][1])
    structured['properties']['rule']['properties']['norms']['minItems']=1
    structured['properties']['explanation']={'const':''}
    narrative['properties']['rule']={'type':'null'}
    narrative['properties']['explanation']['minLength']=1
    claim['anyOf']=[structured,narrative]
    return schema


def display_condition(node):
    """Presentation-only Boolean identities; original evidence tree is retained."""
    if node is None or node['mode']=='LEAF':return deepcopy(node)
    out=deepcopy(node);mode=out['mode']
    children=[display_condition(c) for c in out['children']]
    if mode in ('ALL','ANY'):
        flat=[]
        for child in children:
            flat.extend(child['children'] if child['mode']==mode else [child])
        children=[]
        for child in flat:
            if child not in children:children.append(child)
        if len(children)==1:return children[0]
    out['children']=children
    return out


def render_content(content):
    if content['rule'] is None:return content['explanation']
    shown=deepcopy(content)
    if content.get('content_contract')==CONTENT:
        shown['rule']['condition_tree']=display_condition(shown['rule']['condition_tree'])
    return v6.render_content({**shown,'conclusion':'','details':[]}).strip()


def normalized(content):
    return {k:deepcopy(v) for k,v in content.items() if k not in ('explanation','content_contract')} | {
        'content_contract':'source-modality-v1','conclusion':render_content(content),'details':[]}


def compile_claim(content):
    out=v6.compile_claim(normalized(content))
    out.update(text=render_content(content),answer_content=deepcopy(content))
    return out


def verify_single_content(value,options):
    rules=[c['rule'] for c in value['claims']]
    if any(r is not None for r in rules) and any(r is None for r in rules):
        raise ProposalError('Do not append narrative repetitions to structured rules; write each sourced fact once in rule.norms')
    offered={o['id']:o for o in options};seen=set()
    for rule in rules:
        if rule is None:continue
        for norm in rule['norms']:
            quote=norm['source_quote']
            sources=tuple(sorted({offered[i]['source_id'] for i in norm['evidence_refs'] if quote in offered[i]['text']}))
            key=(sources,' '.join(quote.split()))
            if key in seen:raise ProposalError('Repeated source clause: combine its facts and issue_refs instead of paraphrasing it in another norm')
            seen.add(key)


def prepare(value,schema,issues,options,facts):
    validate(value,schema)
    verify_single_content(value,options)
    normalized_value=deepcopy(value)
    normalized_value['claims']=[normalized(c) for c in value['claims']]
    material_ids=[g['material_id'] for g in value['gaps'] if g['material_id'] is not None]
    previous_keys=[g['previous_gap_key'] for g in value['gaps'] if g.get('previous_gap_key')]
    accepted,model=v6.prepare(normalized_value,v6.assessment_schema(issues,material_ids,options,facts,previous_keys),issues,options,facts)
    accepted['claims']=[compile_claim(c) for c in value['claims']]
    return accepted,model


def materialize(value,options,issues,model):
    out=v6.materialize(value,options,issues,model)
    out['completion_contract']=VERSION
    return out


def verify_content(claim):
    if 'answer_content' not in claim:return
    expected=compile_claim(claim['answer_content'])
    if any(claim.get(k)!=v for k,v in expected.items()):
        raise ContractError('accepted single rule content changed or disappeared during rendering')

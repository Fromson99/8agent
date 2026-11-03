"""Single-content completion wire contract. Structure is not legal certification."""
from copy import deepcopy
from jsonschema import validate
from ..contracts import digest
from . import completion_contracts as cc
from .errors import ProposalError, ContractError

VERSION = 'investigation-completion-v6'
PROMPT = '''v6 계약: rule.obligations 대신 rule.norms를 쓴다. norms의 kind는 OBLIGATION(의무)/PERMISSION(허용)/PROHIBITION(금지)/UNSPECIFIED(명시 양태 미확정)다.
각 norm의 source_quote는 그 효과를 근거로 제시하는 evidence_refs 원문의 연속 문장·절이다. 명시적인 끝말이 없어도 원문 전체 맥락을 보고 분류하되, 단순 끝말 검출 결과를 법률적 정답 증명으로 취급하지 않는다. 서로 다른 양태가 섞인 인용은 더 정확한 절로 나누거나 UNSPECIFIED로 보존한다. 단순 가능성·능력을 서술한 문구를 법적 허용으로 단정하지 말고, 양태를 확정할 수 없으면 UNSPECIFIED를 쓴다.
‘할 수 있다’는 허용이며 ‘하여야 한다’라는 의무로 바꾸지 않는다. ‘하여서는 아니 된다’는 금지다. 결론·세부 설명에도 같은 양태를 유지한다.
적용 조건은 효과 발생의 전제이고, 이행 의무는 그 효과에 따라 요구되는 행동이다. 결론은 질문에 직접 답하는 짧은 요약, 구체 내용은 details/조건/norms/예외 중 알맞은 한 곳에만 쓴다.
아래 공통 원문 계약도 따른다. claims에는 결론 conclusion, 근거 있는 세부 설명 details, 필요한 rule을 쓴다.
같은 설명을 conclusion/details/조건에 중복하지 않는다. rule은 결론을 다시 생성하지 않는다.
조건은 condition_tree 안의 LEAF 또는 ALL/ANY/UNKNOWN children으로 중첩한다. ID/root/groups는 작성하지 않는다.
norms는 조건과 구분된 원문의 의무·허용·금지이며 분류가 불확실하면 UNSPECIFIED로 보존한다. exceptions의 target은 예외가 바꾸는 대상의 원문에 근거한 설명이다.
예외가 확인되지 않았다는 상투 문장은 쓰지 않는다. 중요한 예외 원문이 없으면 material gap으로 남긴다.
모든 details/조건/의무/예외는 제공된 evidence_refs에 연결한다. 사실관계는 fact_refs의 실제 사용자 원문만 쓴다.
이전과 같은 부족이면 previous_gap_key를 선택하고 문서·조문 missing_target을 보존한다.
issue_assessments/disposition은 판단 제안이다. 코드는 명시한 핵심 gap과 채택 claim에 맞춰 보수적으로 충족 표시를 결정한다.'''
SCOPE_PROMPT = '''각 issue의 request_quote는 사용자가 직접 요구한 부분의 연속된 원문이다.
background_quotes에는 요구가 아닌 업무 배경 원문만 쓴다. 배경만 인용한 별도 issue를 만들지 않는다.
다른 조문을 읽어야 하는 조사 의존성은 새 사용자 요구가 아니다. 요청한 비교·조건·주체·예외는 그대로 보존한다.'''


def intent_schema(base):
    out = deepcopy(base)
    row = out['properties']['issues']['items']
    # Literal membership in the admitted request is the provenance boundary.
    row['properties']['request_quote'] = {'type':'string','minLength':1}
    row['required'].append('request_quote')
    out['properties']['background_quotes'] = {'type':'array','maxItems':8,
        'items':{'type':'string','minLength':1}}
    out['required'].append('background_quotes')
    return out


def verify_intent(value, request):
    backgrounds = value['background_quotes']
    if any(q not in request for q in backgrounds):raise ProposalError('background quote outside current request')
    # Positions handle repeated phrases without assuming every parenthesis is background.
    def occurrences(q):
        return [(i,i+len(q)) for i in range(len(request)) if request.startswith(q,i)]
    spans = [s for q in backgrounds for s in occurrences(q)]
    for issue in value['issues']:
        found = occurrences(issue['request_quote'])
        if not found:raise ProposalError('request quote outside current request')
        if all(any(lo<=a and b<=hi for lo,hi in spans) for a,b in found):
            raise ProposalError('background-only quote cannot create an explicit request issue')


def assessment_schema(issues, materials, options, facts, previous_keys=()):
    schema = cc.assessment_schema(issues,materials,options)
    ids = [o['id'] for o in options]
    text = {'type':'string','minLength':1}
    fragment = cc.obj({'text':text,'evidence_refs':cc.refs(ids,1)})
    def node(depth):
        leaf = cc.obj({'mode':{'const':'LEAF'},'text':text,'evidence_refs':cc.refs(ids,1)})
        if not depth:return leaf
        return {'anyOf':[leaf, cc.obj({'mode':{'enum':['ALL','ANY','UNKNOWN']},
            'children':{'type':'array','minItems':1,'maxItems':8,'items':node(depth-1)}})]}
    fact_ids=[f['id'] for f in facts]
    rule = cc.obj({'kind':{'enum':['GENERAL_RULE','CASE_APPLICATION']},
        'subject':text,'action':text,'scope':text,
        'condition_tree':{'anyOf':[{'type':'null'},node(3)]},
        'norms':{'type':'array','maxItems':12,'items':cc.obj({'kind':{'enum':['OBLIGATION','PERMISSION','PROHIBITION','UNSPECIFIED']},'text':text,'source_quote':{'type':'string','minLength':2},'evidence_refs':cc.refs(ids,1)})},
        'exceptions':{'type':'array','maxItems':12,'items':cc.obj({
            'target':text,'text':text,'evidence_refs':cc.refs(ids,1)})},
        'fact_refs':{'type':'array','maxItems':16,'items':cc.obj({
            'id':{'type':'string',**({'enum':fact_ids} if fact_ids else {})},'quote':text}),
            **({} if fact_ids else {'maxItems':0})}})
    claim = schema['properties']['claims']['items']
    del claim['properties']['text'];claim['required'].remove('text')
    claim['properties'].update(conclusion=text, details={'type':'array','maxItems':12,'items':fragment},
                               rule={'anyOf':[{'type':'null'},rule]})
    claim['properties']['content_contract']={'const':'source-modality-v1'}
    claim['required'] += ['conclusion','details','rule','content_contract']
    gap = schema['properties']['gaps']['items']
    gap['properties']['previous_gap_key'] = {'anyOf':[{'type':'null'},
        {'type':'string','enum':list(previous_keys)}]} if previous_keys else {'type':'null'}
    return schema


def compile_claim(raw):
    content = deepcopy(raw)
    atoms=[];groups=[];nested=[]
    def fragment_refs(rows):
        for row in rows:nested.extend(row['evidence_refs'])
    fragment_refs(content['details'])
    def visit(node):
        if node['mode']=='LEAF':
            key='T'+str(len(atoms)+1)
            atoms.append({'id':key,'text':node['text'],'evidence_refs':node['evidence_refs']})
            nested.extend(node['evidence_refs']);return key
        members=[visit(child) for child in node['children']]
        key='G'+str(len(groups)+1);groups.append({'id':key,'mode':node['mode'],'members':members});return key
    rule=content['rule'];derived=None
    if rule is not None:
        root=visit(rule['condition_tree']) if rule['condition_tree'] is not None else None
        fragment_refs(rule['norms']);fragment_refs(rule['exceptions'])
        derived={k:deepcopy(rule[k]) for k in ('kind','subject','action','scope','fact_refs')}
        derived.update(conclusion=content['conclusion'],conditions=atoms,groups=groups,root=root,
            exceptions=[{k:x[k] for k in ('text','evidence_refs')} for x in rule['exceptions']],
            exception_status='SOURCE_EXCEPTIONS' if rule['exceptions'] else 'NOT_ESTABLISHED')
    return {k:deepcopy(content[k]) for k in ('claim_id','issue_refs')} | {
        'text':render_content(content),'evidence_refs':list(dict.fromkeys(content['evidence_refs']+nested)),
        'rule':derived,'answer_content':content}


def render_content(content):
    rule=content['rule'];typed=set()
    def key(text):return ' '.join(text.split()).rstrip(' .。')
    def leaves(node):
        if node is None:return []
        if node['mode']=='LEAF':return [node['text']]
        return [text for c in node['children'] for text in leaves(c)]
    if rule:
        typed={key(x['text']) for x in rule['norms']+rule['exceptions']}|{key(x) for x in leaves(rule['condition_tree'])}
    pieces=[];seen=set()
    for text in [content['conclusion']]+[x['text'] for x in content['details']]:
        ident=key(text)
        if ident not in typed and ident not in seen:pieces.append(text);seen.add(ident)
    labels={'OBLIGATION':'의무','PERMISSION':'허용','PROHIBITION':'금지','UNSPECIFIED':'규정'}
    leaf_keys={key(x) for x in leaves(rule['condition_tree'])} if rule else set()
    def render_node(node):
        if node['mode']=='LEAF':
            roles=list(dict.fromkeys(labels[r['kind']] for r in rule['norms'] if key(r['text'])==key(node['text'])))
            return ('/'.join(roles)+': ' if roles else '')+node['text']
        prefix={'ALL':'모두 충족','ANY':'하나 이상 충족','UNKNOWN':'요건 관계 미확인'}[node['mode']]
        return '('+prefix+': '+'; '.join(render_node(c) for c in node['children'])+')'
    if rule is not None:
        pieces.append('적용 범위: '+' · '.join(dict.fromkeys(rule[k] for k in ('subject','action','scope'))))
        if rule['condition_tree'] is not None:pieces.append('적용 조건: '+render_node(rule['condition_tree']))
        rows=[]
        for row in rule['norms']:
            ident=(row['kind'],key(row['text']))
            if ident not in rows and key(row['text']) not in leaf_keys:
                pieces.append(labels[row['kind']]+': '+row['text']);rows.append(ident)
        pieces+=['예외 ('+r['target']+'): '+r['text'] for r in rule['exceptions']]
        if rule['fact_refs']:pieces.append('사용자가 제공한 전제: '+'; '.join(r['quote'] for r in rule['fact_refs']))
    return '\n'.join(pieces)


def source_modality(text):
    """Deprecated lexical classifier: legal modality is a model judgment."""
    return 'UNSPECIFIED'


def verify_modalities(value,options):
    """Verify source identity; the model owns contextual legal modality."""
    offered={o['id']:o for o in options}
    for claim in value['claims']:
        for norm in (claim.get('rule') or {}).get('norms',[]):
            quote=norm['source_quote']
            if not quote or not any(quote in offered.get(i,{}).get('text','') for i in norm['evidence_refs']):
                raise ProposalError('norm source_quote must be an exact clause of its selected evidence')


def prepare(value, schema, issues, options, facts):
    """Validate source-selected content, then derive conservative coverage once."""
    validate(value,schema)
    verify_modalities(value,options)
    out, gap_actions = cc.source_gap_actions(value)
    model={'disposition':value['disposition'],'issue_assessments':deepcopy(value['issue_assessments']),
        'gaps':deepcopy(value['gaps'])}
    if gap_actions:model['gap_action_corrections'] = gap_actions
    out['claims']=[compile_claim(c) for c in value['claims']]
    allowed={o['id'] for o in options}
    for c in out['claims']:
        if not set(c['evidence_refs']) <= allowed:raise ProposalError('unknown nested evidence reference')
        if c['rule'] is not None:
            errors=cc.rule_errors(c,facts)
            if errors:raise ProposalError('; '.join(errors))
    # Preserve submitted materiality; missing-source type is not importance.
    blocked={g['issue_id'] for g in out['gaps'] if g['material']}
    for row in out['issue_assessments']:
        supported=any(row['issue_id'] in c['issue_refs'] for c in out['claims'])
        if not supported:row['status']='INSUFFICIENT'
        elif row['status']=='COVERED' and row['issue_id'] in blocked:row['status']='PARTIAL'
    out['disposition']=('NEEDS_INVESTIGATION' if any(g['material'] and g['kind']!='MISSING_FACT' for g in out['gaps']) else
        'ANSWER' if all(r['status']=='COVERED' for r in out['issue_assessments']) else 'LIMITED_ANSWER')
    # Reuse the existing semantic boundary after removing the new wire-only fields.
    legacy=deepcopy(out)
    for claim in legacy['claims']:claim.pop('answer_content')
    for gap in legacy['gaps']:gap.pop('previous_gap_key',None)
    # material IDs require the actual allowed pool, not the empty default above.
    # The supplied wire schema already verified that pool; validate semantics with it retained.
    legacy_schema=cc.assessment_schema(issues,
        [g['material_id'] for g in legacy['gaps'] if g['material_id'] is not None],options,contract=cc.CONTRACT,facts=facts)
    errors=cc.assessment_errors(legacy,legacy_schema,issues,model_materiality=True)
    if errors:raise ProposalError('; '.join(errors))
    return out, model


def materialize(value, options, issues, model):
    by_id={o['id']:o for o in options}
    out=deepcopy(value)
    for claim in out['claims']:
        selected=[by_id[i] for i in claim['evidence_refs']]
        if not selected:raise ContractError('claim requires delivered source spans')
        quotes=[{'source_id':s['source_id'],'quote':s['text']} for s in selected]
        claim.update(**quotes[0],evidence=quotes[1:],span_receipts=deepcopy(selected))
    out.update(completion_contract=VERSION,model_proposal=model)
    return cc.refresh_limitations(out,issues)


def verify_content(claim):
    if 'answer_content' not in claim:return
    expected=compile_claim(claim['answer_content'])
    if any(claim.get(k)!=v for k,v in expected.items()):
        raise ContractError('accepted answer content changed or disappeared during rendering')


def project_assessment(context, sources, options):
    """One exact source-text copy, referenced by source ID. No body truncation."""
    data=deepcopy(context)
    # Context may include earlier stage outputs; leave their contracts intact.
    metadata=[]
    for source in sources:
        row={k:deepcopy(v) for k,v in source.items() if k not in ('text','adopted_spans')}
        row['evidence_refs']=[o['id'] for o in options if o['source_id']==source['source_id']]
        metadata.append(row)
    return data,metadata

"""One model-owned claim/evidence relation, reusable by independent reviews.

Only identical relationships are shared. Dispositions, reasons, issue/gap/target
links and source-scope partitions remain explicit and pass the original validators.
"""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError, ProposalError
from .output_contract import OutputContractError, issue, validate_shape

VERSION = 'assessment-review-links-v2'
DIRECT_VERSION = 'assessment-review-links-v3-direct'
SUPPORTED_VERSIONS = ('assessment-review-links-v1', VERSION, DIRECT_VERSION)
FIELD = 'review_links'
REVIEWS = ('read_judgment_review', 'requirement_review')
PROMPT = '''검토표의 link_ref는 최상위 review_links에서 선택한다. review_links에는 id와 claim_refs/basis_refs를 한 번 작성하고, 같은 주장·근거 조합을 사용하는 판단·need·범위·요구 행에서는 같은 id를 재사용한다. 서로 다른 조합은 다른 연결이다. link_ref는 해당 행의 claim_refs와 basis_refs를 대신하며 채택·해결을 뜻하지 않는다. USE/EXCLUDE/OPEN, status/disposition, reason, issue_refs, gap_indices, target_refs와 scope_quote는 각 행의 의미에 맞게 직접 판단한다. 근거 없는 해결이나 다른 범위의 연결을 만들지 않는다. 원문의 확보와 사건의 확정은 별개다. 스키마가 link_ref 대신 basis_refs를 제시하는 비채택 행에서는 서버가 claim_refs=[]를 고정한다. 이 행에는 link_ref나 claim_refs를 작성하지 않고 해당 basis_refs와 gap/이유를 작성한다. 채택 행의 link_ref 설명에 있는 최소·최대 개수를 지킨다. 사용하지 않는 연결을 넣지 않는다. 문자열 길이 상한을 채우거나 같은 설명을 반복하지 않는다.'''
DIRECT_PROMPT = '''검토 행의 claim_refs에는 이번 claims의 실제 claim_id를, basis_refs에는 현재 evidence_options의 실제 ID를 직접 쓴다. 별도의 review_links나 link_ref를 만들지 않는다. 원문 확보·읽기 완료와 답변 채택을 구분한다. USE/CONDITIONAL은 실제 답변 주장과 근거를 연결하고, 채택하지 않는 판단은 이유와 미확인을 보존한다. 상태·이유·요구·범위·gap은 직접 판단한다. 서버는 작성된 연결의 동일성만 기록하며 법률 판단을 대신하지 않는다.'''


def obj(properties):
    return {'type':'object','additionalProperties':False,'properties':properties,'required':list(properties)}


def link_schema(evidence):
    return {'type':'array','items':obj({'id':{'type':'string','pattern':'^review-link:[1-9][0-9]*$'},
        'claim_refs':{'type':'array','uniqueItems':True,'items':{'type':'string'}},
        'basis_refs':{'type':'array','uniqueItems':True,'items':{'type':'string','enum':evidence}}})}


def attach(schema, options, *, direct=False):
    out=deepcopy(schema)
    out['properties'][FIELD]=obj({'version':{'const':DIRECT_VERSION if direct else VERSION},'links':link_schema([r['id'] for r in options]),
        'bindings':{'type':'array','items':obj({'path':{'type':'string'},'link_id':{'type':'string'}})},
        'empty_claim_paths':{'type':'array','uniqueItems':True,'items':{'type':'string'}},
        'proposal_hash':{'type':'string'},'receipt_hash':{'type':'string'}})
    out['required'].append(FIELD)
    return out


def direct_projection(schema):
    """Keep branch constraints in generation; intern exact explicit links only.

    Receipt IDs are storage metadata, not another model-authored relationship.
    No status, claim, evidence, gap, or reason is inferred or changed here.
    """
    wire=deepcopy(schema)
    wire['properties'].pop(FIELD)
    wire['required']=[k for k in wire['required'] if k!=FIELD]
    def expand(raw):
        try:
            validate_shape(raw,wire)
            value=deepcopy(raw);links=[];bindings=[];by_value={}
            def collect(node,path):
                if isinstance(node,list):
                    for index,child in enumerate(node):collect(child,path+'/'+str(index))
                elif isinstance(node,dict):
                    if {'claim_refs','basis_refs'}<=node.keys():
                        # Tuple equality, not hash equality or set containment:
                        # preserve ordering and distinguish different relations.
                        key=(tuple(node['claim_refs']),tuple(node['basis_refs']))
                        if key not in by_value:
                            ident='review-link:'+str(len(links)+1)
                            by_value[key]=ident
                            links.append({'id':ident,**{k:deepcopy(node[k]) for k in ('claim_refs','basis_refs')}})
                        bindings.append({'path':path,'link_id':by_value[key]})
                    for name,child in node.items():collect(child,path+'/'+name)
            for name in REVIEWS:
                if name in value:collect(value[name],'/'+name)
            receipt={'version':DIRECT_VERSION,'links':links,'bindings':bindings,
                     'empty_claim_paths':[],'proposal_hash':digest(raw)}
            receipt['receipt_hash']=digest(receipt);value[FIELD]=receipt
            validate_shape(value,schema)
            return value
        except ProposalError as exc:
            exc.proposal=deepcopy(raw)
            raise
    return wire,expand


def projection(schema):
    """Return generation schema and exact expansion; no best-match inference."""
    if schema['properties'][FIELD]['properties']['version'].get('const')==DIRECT_VERSION:
        return direct_projection(schema)
    wire=deepcopy(schema)
    wire['properties'][FIELD]=deepcopy(schema['properties'][FIELD]['properties']['links'])
    empty_rules=[]
    def transform(node,path=()):
        if not isinstance(node,dict):return
        props=node.get('properties',{});branches=node.get('anyOf',[])
        if ({'claim_refs','basis_refs'}<=props.keys() and branches and
                all(isinstance(branch,dict) and set(props)<=set(branch.get('properties',{}))
                    and set(node.get('required',[]))<=set(branch.get('required',[]))
                    and branch.get('additionalProperties') is False for branch in branches)):
            node.pop('properties');node.pop('required',None);node.pop('additionalProperties',None)
        for name,child in list(node.get('properties',{}).items()):transform(child,path+(name,))
        if isinstance(node.get('items'),dict):transform(node['items'],path+('*',))
        for key in ('anyOf','oneOf','allOf'):
            for child in node.get(key,[]):transform(child,path)
        props=node.get('properties',{})
        if {'claim_refs','basis_refs'}<=props.keys():
            if props['claim_refs'].get('maxItems')==0:
                props.pop('claim_refs')
                node['required']=[k for k in node.get('required',[]) if k!='claim_refs']
                empty_rules.append((path,deepcopy(node)))
                return
            constraints={name:{k:v for k,v in props[name].items() if k in ('minItems','maxItems','uniqueItems')} for name in ('claim_refs','basis_refs')}
            props.pop('claim_refs');props.pop('basis_refs')
            import json
            props['link_ref']={'type':'string','pattern':'^review-link:[1-9][0-9]*$',
                'description':'Selected review_links row must satisfy '+json.dumps(constraints,separators=(',',':'))}
            node['required']=[k for k in node.get('required',[]) if k not in ('claim_refs','basis_refs')]+['link_ref']
    for name in REVIEWS:
        if name in wire['properties']:transform(wire['properties'][name],(name,))

    def decode(raw):
        validate_shape(raw,wire)
        value=deepcopy(raw);rows=value.pop(FIELD);links={};bindings=[];empty_paths=[]
        def fail(path,expected):
            raise OutputContractError('검토 연결은 한 번 정의한 실제 주장·근거 조합이어야 합니다.',
                [issue('REVIEW_LINK_INVALID',path,expected=expected)],category='REQUIREMENT_REVIEW_INVALID')
        for i,row in enumerate(rows):
            if row['id'] in links:fail('/'+FIELD+'/'+str(i),{'duplicate_id':row['id']})
            links[row['id']]=row
        def restore(node,path):
            if isinstance(node,list):return [restore(child,path+'/'+str(i)) for i,child in enumerate(node)]
            if not isinstance(node,dict):return node
            out={k:restore(v,path+'/'+k) for k,v in node.items() if k!='link_ref'}
            if 'link_ref' in node:
                ident=node['link_ref']
                if ident not in links:fail(path+'/link_ref',{'allowed_ids':list(links)})
                out.update({k:deepcopy(links[ident][k]) for k in ('claim_refs','basis_refs')})
                bindings.append({'path':path,'link_id':ident})
            else:
                from jsonschema import Draft202012Validator
                parts=path.split('/')[1:]
                matched=any(len(parts)==len(pattern) and all(a==b or a=='*' for a,b in zip(pattern,parts))
                    and Draft202012Validator(shape).is_valid(node) for pattern,shape in empty_rules)
                if matched:
                    out['claim_refs']=[];empty_paths.append(path)
            return out
        for name in REVIEWS:
            if name in value:value[name]=restore(value[name],'/'+name)
        used={r['link_id'] for r in bindings}
        if used!=set(links):fail('/'+FIELD,{'unused_ids':sorted(set(links)-used)})
        receipt={'version':VERSION,'links':rows,'bindings':bindings,'empty_claim_paths':empty_paths,'proposal_hash':digest(raw)}
        receipt['receipt_hash']=digest(receipt);value[FIELD]=receipt
        try:validate_shape(value,schema)
        except OutputContractError as exc:
            remapped=[]
            for entry in exc.issues:
                item=deepcopy(entry)
                for binding in bindings:
                    for field in ('claim_refs','basis_refs'):
                        original=binding['path']+'/'+field
                        if item['path']==original or item['path'].startswith(original+'/'):
                            index=next(i for i,row in enumerate(rows) if row['id']==binding['link_id'])
                            item['path']=binding['path']+'/link_ref'
                            item['related_paths']=['/'+FIELD+'/'+str(index)+'/'+field]
                            item['expected_constraint']={'link_id':binding['link_id'],'field':field,'constraint':entry.get('expected_constraint')}
                remapped.append(item)
            raise OutputContractError('선택한 공유 연결이 해당 검토 행의 주장·근거 개수 제약과 일치하지 않습니다.',remapped,category='REQUIREMENT_REVIEW_INVALID') from exc
        return value
    def expand(raw):
        try:return decode(raw)
        except ProposalError as exc:
            exc.proposal=deepcopy(raw)
            raise
    return wire,expand


def core(value,schema):
    value,schema=deepcopy(value),deepcopy(schema)
    value.pop(FIELD,None);schema['properties'].pop(FIELD,None)
    schema['required']=[k for k in schema['required'] if k!=FIELD]
    return value,schema


def verify_saved(assessment):
    receipt=assessment.get(FIELD)
    expected=assessment.get('assessment_basis',{}).get('review_links_version')
    required=expected in SUPPORTED_VERSIONS
    if receipt is None:
        if required and not assessment.get('source_excerpt_reply') and assessment.get('model_proposal',{}).get('review_status')!='INCOMPLETE':
            raise ContractError('saved review links missing')
        return
    if receipt.get('version') not in SUPPORTED_VERSIONS or (required and receipt.get('version')!=expected) or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):
        raise ContractError('saved review links changed')
    if receipt.get('version') in (VERSION,DIRECT_VERSION) and not isinstance(receipt.get('empty_claim_paths'),list):
        raise ContractError('saved empty claim bindings missing')
    links={r['id']:r for r in receipt['links']}
    if len(links)!=len(receipt['links']):raise ContractError('saved review link duplicate')
    view={'requirement_review':assessment.get('requirement_review',{}).get('rows'),
          'read_judgment_review':assessment.get('read_judgment_review',{}).get('review')}
    seen=set();used=set()
    for binding in receipt['bindings']:
        path=binding['path'];ident=binding['link_id']
        if path in seen or ident not in links:raise ContractError('saved review link binding changed')
        seen.add(path);used.add(ident);node=view
        try:
            for component in path.split('/')[1:]:node=node[int(component)] if isinstance(node,list) else node[component]
        except (KeyError,IndexError,TypeError,ValueError) as exc:raise ContractError('saved review link path changed') from exc
        if any(node.get(k)!=links[ident][k] for k in ('claim_refs','basis_refs')):
            raise ContractError('saved review does not match its shared link')
    if used!=set(links):raise ContractError('saved review link unused')
    for path in receipt.get('empty_claim_paths',[]):
        if path in seen:raise ContractError('saved empty review path duplicate')
        seen.add(path);node=view
        try:
            for part in path.split('/')[1:]:node=node[int(part)] if isinstance(node,list) else node[part]
        except (KeyError,IndexError,TypeError,ValueError) as exc:raise ContractError('saved empty review path changed') from exc
        if node.get('claim_refs')!=[]:raise ContractError('saved nonadopting review claims changed')


def repair_proposal(value):
    """Return the same relationships in the generation vocabulary for repair.

    The original canonical proposal stays in the decision journal. Never invent
    a missing link or erase an invalid field from a rejected raw response.
    """
    result=deepcopy(value)
    if not isinstance(result,dict) or not isinstance(result.get(FIELD),dict):return result
    receipt=result[FIELD]
    if receipt.get('version') not in SUPPORTED_VERSIONS or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):return result
    direct=receipt['version']==DIRECT_VERSION
    definitions={r['id']:r for r in receipt['links']}
    for binding in receipt['bindings']:
        node=result
        try:
            for part in binding['path'].split('/')[1:]:node=node[int(part)] if isinstance(node,list) else node[part]
            definition=definitions[binding['link_id']]
        except (KeyError,IndexError,TypeError,ValueError):return deepcopy(value)
        if any(node.get(k)!=definition[k] for k in ('claim_refs','basis_refs')):return deepcopy(value)
        if not direct:
            for key in ('claim_refs','basis_refs'):node.pop(key)
            node['link_ref']=binding['link_id']
    for path in receipt.get('empty_claim_paths',[]):
        node=result
        try:
            for part in path.split('/')[1:]:node=node[int(part)] if isinstance(node,list) else node[part]
        except (KeyError,IndexError,TypeError,ValueError):return deepcopy(value)
        if node.get('claim_refs')!=[]:return deepcopy(value)
        node.pop('claim_refs')
    if direct:result.pop(FIELD)
    else:result[FIELD]=deepcopy(receipt['links'])
    return result

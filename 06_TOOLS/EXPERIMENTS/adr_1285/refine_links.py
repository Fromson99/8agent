from common import *
L=ROOT/read(DES/'candidate-path.json')['snapshot']/'02_BACKEND/semantic_runtime/legal_agent'
p=L/'assessment_links.py';s=p.read_text()
s=s.replace("'bindings':{'type':'array','items':obj({'path':{'type':'string'},'link_id':{'type':'string'}})},", "'bindings':{'type':'array','items':obj({'path':{'type':'string'},'link_id':{'type':'string'}})},\n        'empty_claim_paths':{'type':'array','uniqueItems':True,'items':{'type':'string'}},")
a=s.index('    def transform(node):');b=s.index('\n    def decode(raw):',a)
s=s[:a]+'''    empty_rules=[]
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
''' +s[b:]
s=s.replace("value=deepcopy(raw);rows=value.pop(FIELD);links={};bindings=[]", "value=deepcopy(raw);rows=value.pop(FIELD);links={};bindings=[];empty_paths=[]")
s=s.replace("                bindings.append({'path':path,'link_id':ident})\n            return out", """                bindings.append({'path':path,'link_id':ident})
            else:
                from jsonschema import Draft202012Validator
                parts=path.split('/')[1:]
                matched=any(len(parts)==len(pattern) and all(a==b or a=='*' for a,b in zip(pattern,parts))
                    and Draft202012Validator(shape).is_valid(node) for pattern,shape in empty_rules)
                if matched:
                    out['claim_refs']=[];empty_paths.append(path)
            return out""")
s=s.replace("receipt={'version':VERSION,'links':rows,'bindings':bindings,'proposal_hash':digest(raw)}", "receipt={'version':VERSION,'links':rows,'bindings':bindings,'empty_claim_paths':empty_paths,'proposal_hash':digest(raw)}")
s=s.replace("    if used!=set(links):raise ContractError('saved review link unused')", """    if used!=set(links):raise ContractError('saved review link unused')
    for path in receipt.get('empty_claim_paths',[]):
        if path in seen:raise ContractError('saved empty review path duplicate')
        seen.add(path);node=view
        try:
            for part in path.split('/')[1:]:node=node[int(part)] if isinstance(node,list) else node[part]
        except (KeyError,IndexError,TypeError,ValueError) as exc:raise ContractError('saved empty review path changed') from exc
        if node.get('claim_refs')!=[]:raise ContractError('saved nonadopting review claims changed')""")
s=s.replace("    result[FIELD]=deepcopy(receipt['links'])", """    for path in receipt.get('empty_claim_paths',[]):
        node=result
        try:
            for part in path.split('/')[1:]:node=node[int(part)] if isinstance(node,list) else node[part]
        except (KeyError,IndexError,TypeError,ValueError):return deepcopy(value)
        if node.get('claim_refs')!=[]:return deepcopy(value)
        node.pop('claim_refs')
    result[FIELD]=deepcopy(receipt['links'])""")
p.write_text(s)

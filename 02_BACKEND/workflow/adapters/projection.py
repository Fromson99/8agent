"""Wire-only mechanical fields; canonical validators still own acceptance.

IDs resolve only within this immutable presented packet. The raw provider
proposal remains in model_attempt and the expanded result in workflow_call.
"""
from copy import deepcopy
from ..contracts import digest

VERSION = 'workflow-mechanical-projection-v12'


def project_sources(data):
    """Return the exact source wire view and its packet-local citation map.

    Labels deliberately restart in each packet. The catalogue hash binds their
    original span coordinates as well as their text; the model call identity
    includes this projected view. Nothing is resolved from a global ID cache.
    """
    data=deepcopy(data); citations={}; catalogue=[]
    for source in data.get('sources',[]):
        options=[]
        for span in source.pop('spans',[]):
            text=span['text']
            # The selected native span is the citation unit. Its existing
            # request context budget owns delivery; character boundaries do not
            # create new source meaning or arbitrarily split conditions.
            ident='C'+str(len(citations)+1)
            citations[ident]={'evidence':source['evidence_id'],'quote':text}
            catalogue.append({'citation_id':ident,'evidence':source['evidence_id'],'span':span})
            options.append({'citation_id':ident,'text':text})
        # No text inference for old/custom consumers without exact span records.
        if options:
            source.pop('text',None)
            source['citation_options']=options
    if citations:
        data['citation_catalogue_hash']=digest(catalogue)
    return data,citations


def prepare(stage, data, schema):
    data,citations=project_sources(data)
    general=stage=='ITEMS' and data.get('review_mode') in ('INITIAL','UPDATE')
    if stage=='ITEMS' and data.get('review_mode') in ('INITIAL','UPDATE'):
        # State is an immutable observation, not a submission-shaped example.
        # Keep every prior finding/quote; never relabel old packet-local C IDs.
        history=[]
        for item in data.pop('previous',[]):
            if item is None:continue
            entry={'field':item['field'],'comparison_observation':item.get('difference',''),'readings':{}}
            for side in ('internal','external'):
                row=item[side]
                entry['readings'][side]={'text':row['text'],'missing':row['missing'],
                    'status':row['status'],
                    'source_history':[{'original_id':c['evidence'],'quoted_original':c['quote']} for c in row['citations']+row['dependencies']],
                    'earlier_findings':[{'text':a['text'],'source_history':[{'original_id':c['evidence'],'quoted_original':c['quote']} for c in a['citations']+a['dependencies']]} for a in row.get('alternatives',[])]}
            history.append(entry)
        data['read_only_history']=history
    projected=bool(citations)
    source_ids=[s['evidence_id'] for s in data.get('sources',[])]
    side_ids={side:[s['evidence_id'] for s in data.get('sources',[]) if s.get('side')==side] for side in ('internal','external')}
    pairs=(data.get('basis') or {}).get('pairs',[])
    issues={i['id']:i for i in data.get('scope',{}).get('issues',[])}
    single=pairs[0] if stage=='COMPARE' and len(pairs)==1 else None
    numeric=issues[single['issue_id']]['numeric'] if single else None
    dimension_names=[]
    def rewrite(node):
        if isinstance(node,list):return [rewrite(x) for x in node]
        if not isinstance(node,dict):return node
        if projected and set(node.get('properties',{}))=={'evidence','quote'}:
            selected={'type':'object','properties':{'citation_id':{'type':'string','enum':list(citations)}},
                    'required':['citation_id'],'additionalProperties':False}
            return {'anyOf':[selected,{'type':'string','enum':list(citations)}]} if general else selected
        result={k:rewrite(v) for k,v in node.items()}
        props=result.get('properties',{})
        if stage=='ITEMS' and {'evidence_id','disposition','fields','reason'}<=set(props):
            # Field membership is already expressed by the actual citations.
            # Keep the model's source judgment, not a second copy of that map.
            for name in ('fields','declared_disposition','binding_note'):
                props.pop(name,None)
                if name in result['required']:result['required'].remove(name)
        if single and 'verdict' in props and 'pair_id' in props:
            for k in ('pair_id','numeric'):
                props.pop(k);result['required'].remove(k)
            dimension=props['dimensions']['items']
            # Numerical dimensions are optional observations, not a mandatory
            # ten-way checklist. Non-numeric rows keep an empty host-owned list.
            result['required'].remove('dimensions')
            if not numeric:props['dimensions']['maxItems']=0
        if stage=='ITEMS' and {'status','text','citations','dependencies','scope_sufficient','missing'}<=set(props):
            for name in ('dependencies','scope_sufficient'):
                props.pop(name);result['required'].remove(name)
            if general:
                props['missing']={'anyOf':[{'type':'string'},
                    {'type':'array','items':{'type':'string'},'maxItems':100}]}
        if stage=='ITEMS' and 'anchor_ids' in props and 'locator_id' in props:
            for name in ('anchor_ids','operation'):
                props.pop(name);result['required'].remove(name)
            props['locator_id']['enum']=[*data.get('locators',{}),None]
        if stage=='ITEMS' and 'field' in props and data.get('fields'):
            props['field']['enum']=list(data['fields'])
            if general and data.get('review_mode')=='UPDATE':
                props.pop('task_plan_unchanged',None)
                for name in ('content_status','difference','next_tasks'):
                    if name in result['required']:result['required'].remove(name)
        if stage=='COMPARE' and 'verdict' in props and 'dimensions' in props:
            # Emit the supplied observations before the overall conclusion.
            # Required order is part of the stable schema digest (object-key
            # order alone is not), so an older decision cannot be reused under
            # this generation contract. No semantic field is added or decided.
            observations=('citations','dimensions','difference','reason','unresolved','verdict')
            order=[name for name in props if name not in observations]
            order.extend(name for name in observations if name in props)
            result['properties']={name:props[name] for name in order}
            result['required']=[name for name in order if name in result['required']]
        if stage=='BASIS' and 'basis_relation' in props and 'pair_id' in props:
            props.pop('pair_id');result['required'].remove('pair_id')
            for side in ('internal','external'):
                if side_ids[side]:props[side]['items']={'type':'string','enum':side_ids[side]}
        if stage=='BASIS' and set(props)=={'status','reason','citations','as_of'}:
            props.pop('as_of');result['required'].remove('as_of')
        if stage=='BASIS':
            if 'issue_id' in props and issues:props['issue_id']={'type':'string','enum':list(issues)}
            for name in ('from_evidence','to_evidence'):
                if name in props and source_ids:props[name]={'type':'string','enum':source_ids}
            if 'context_evidence' in props and source_ids:props['context_evidence']['items']={'type':'string','enum':source_ids}
        return result
    wire=rewrite(schema)
    if general:
        item=wire['properties']['items']['items']
        canonical_side=deepcopy(item['properties']['external'])
        alias_side=deepcopy(canonical_side)
        for old,new in (('status','assessment'),('text','finding')):
            alias_side['properties'][new]=alias_side['properties'].pop(old)
            alias_side['required']=[new if k==old else k for k in alias_side['required']]
        for side in ('internal','external'):
            item['properties'][side]={'anyOf':[deepcopy(canonical_side),deepcopy(alias_side)]}
        if data.get('review_mode')=='UPDATE':
            # One side per flat patch is the preferred submission. The previous
            # nested form remains valid; neither form can invent a side/status.
            flat={'type':'object','additionalProperties':False,
                'properties':{'field':deepcopy(item['properties']['field']),
                    'side':{'enum':['internal','external']},**deepcopy(canonical_side['properties'])},
                'required':['field','side',*canonical_side['required']]}
            for name in ('content_status','difference','next_tasks'):
                flat['properties'][name]=deepcopy(item['properties'][name])
            alias_flat=deepcopy(flat)
            for old,new in (('status','assessment'),('text','finding')):
                alias_flat['properties'][new]=alias_flat['properties'].pop(old)
                alias_flat['required']=[new if k==old else k for k in alias_flat['required']]
            wire['properties']['items']['items']={'anyOf':[flat,item,alias_flat]}
            wire['properties']['items']['maxItems']=28
        elif data.get('fields'):
            # An initial review answers one issue: at most one item for each of its requested fields.
            wire['properties']['items']['maxItems']=len(data['fields'])
    if single:
        wire['properties']['rows'].update(minItems=1,maxItems=1)
    if stage=='BASIS' and not all(side_ids.values()):wire['properties']['pairs']['maxItems']=0
    def expand(value):
        from jsonschema import validate
        # Reject omissions/extra keys before any mechanical fields are restored.
        # In particular, never hide a supplied dimension or extra comparison row.
        if (general and data.get('review_mode')!='UPDATE' and data.get('fields') and isinstance(value,dict)
                and isinstance(value.get('items'),list) and len(value['items'])>len(data['fields'])):
            raise ValueError('too many items: this call reviews only the given issue. Submit at most one item for each requested field ('
                +', '.join(data['fields'])+'); '+str(len(value['items']))+' were submitted. Put several findings of one field in that item, '
                'and leave the other issues of the question to their own review')
        validate(value,wire)
        normalizations=[]
        prepared=deepcopy(value)
        if general:
            grouped={}
            for index,original in enumerate(prepared['items']):
                row=deepcopy(original);path='/items/'+str(index)
                if 'side' in row:
                    side=row.pop('side')
                    body={k:row.pop(k) for k in list(row) if k in ('status','text','assessment','finding','citations','missing','need_resolution')}
                    row[side]=body
                    normalizations.append({'rule':'flat-side-patch-v1','path':path,
                        'field':row['field'],'side':side,'original_hash':digest(original)})
                for side in ('internal','external'):
                    if side not in row:continue
                    body=row[side]
                    if 'assessment' in body:
                        body['status']=body.pop('assessment');body['text']=body.pop('finding')
                        normalizations.append({'rule':'judgment-key-alias-v1','path':path+'/'+side,
                            'renames':{'assessment':'status','finding':'text'}})
                field=row['field']
                if field not in grouped:grouped[field]=row;continue
                prior=grouped[field]
                if any(side in prior and side in row for side in ('internal','external')):
                    raise ValueError('duplicate field-side patch: field '+str(field)+' has more than one judgment for the same side; '
                        'submit each requested field once per side and put several findings of one field in that item')
                for name,entry in row.items():
                    if name=='field':continue
                    if name in prior and prior[name]!=entry:
                        raise ValueError('conflicting paired patch metadata: '+name)
                    prior[name]=entry
            prepared['items']=list(grouped.values())
        def walk(node,path=()):
            if isinstance(node,list):return [walk(x,path+(str(i),)) for i,x in enumerate(node)]
            if not isinstance(node,dict):return node
            if projected and set(node)=={'citation_id'}:
                if node['citation_id'] not in citations:raise ValueError('citation ID outside presented packet')
                return deepcopy(citations[node['citation_id']])
            result={}
            for k,v in node.items():
                here=path+(k,)
                if general and k=='missing' and isinstance(v,list):
                    result[k]='\n'.join(v)
                    normalizations.append({'rule':'explanation-lines-v1','path':'/'+('/'.join(here)),
                        'original':deepcopy(v),'canonical':result[k]})
                elif general and projected and k=='citations':
                    result[k]=[]
                    for i,c in enumerate(v):
                        if isinstance(c,str):
                            result[k].append(deepcopy(citations[c]))
                            normalizations.append({'rule':'packet-citation-choice-v1','path':'/'+('/'.join(here+(str(i),))),
                                'original':c,'canonical_choice':{'citation_id':c}})
                        else:result[k].append(walk(c,here+(str(i),)))
                else:result[k]=walk(v,here)
            return result
        result=walk(prepared)
        receipt['normalizations']=normalizations
        if single:
            for row in result['rows']:
                row['pair_id']=single['pair_id'];row['numeric']=numeric
                row.setdefault('dimensions',[])
        if stage=='ITEMS':
            for index,item in enumerate(result['items']):
                if general and data.get('review_mode')=='UPDATE':
                    omitted=[k for k in ('content_status','difference','next_tasks') if k not in item]
                    # No comparison was submitted: leave it explicitly unknown.
                    # No plan was submitted: the existing queue is not deleted.
                    item.setdefault('content_status','UNKNOWN');item.setdefault('difference','')
                    if 'next_tasks' not in item:item.update(next_tasks=[],task_plan_unchanged=True)
                    if omitted:normalizations.append({'rule':'partial-review-patch-v1','path':'/items/'+str(index),
                        'omitted':omitted,'comparison_if_omitted':'UNKNOWN','task_plan_if_omitted':'PRESERVE'})
                for side in ('internal','external'):
                    if data.get('review_mode')=='UPDATE' and side not in item:continue
                    item[side]['dependencies']=[]
                    item[side]['scope_sufficient']=item[side]['status']=='CONFIRMED'
                for task in item['next_tasks']:
                    locator=data.get('locators',{}).get(task['locator_id']) if task['locator_id'] else None
                    origin=locator.get('origin_evidence_id') if locator else None
                    task['anchor_ids']=[origin] if origin in source_ids else []
                    task['operation']=('follow_reference' if locator.get('reference_id') else 'read_node') if locator else 'search_text'
            for update in result.get('evidence_updates',[]):
                update['fields']=list(dict.fromkeys(item['field'] for item in result['items']
                    if any(c['evidence']==update['evidence_id'] for side in ('internal','external')
                           for c in item.get(side,{}).get('citations',[]))))
                if update['disposition']=='USED' and not update['fields']:
                    # A declaration alone cannot create a supported claim.
                    # Preserve it explicitly; never fabricate the missing link.
                    update['declared_disposition']='USED'
                    update['disposition']='UNRESOLVED'
                    update['binding_note']='사용 선언에 대응하는 항목 인용이 없어 반영 미완료로 보존했습니다.'
        if stage=='BASIS':
            for index,pair in enumerate(result['pairs'],1):
                pair['pair_id']='P'+str(index)
                pair['applicability']['as_of']=data.get('as_of')
        return result
    catalogue_hash=data.get('citation_catalogue_hash',digest(citations))
    receipt={'version':VERSION,'catalogue_hash':catalogue_hash,'citation_count':len(citations),
             'schema_hash':digest(wire),'binding_hash':digest([VERSION,single,data.get('as_of'),catalogue_hash])}
    return data,wire,expand,receipt

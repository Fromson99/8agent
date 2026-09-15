"""Versioned term pipeline ports, sharing the selected source store."""
from importlib import import_module

def retrieve(inputs,parameters,context):
    p=context['runtime'];request=inputs['request']
    query=p.plan(request['question'],request.get('document_ids'))
    return {'retrieved':{'request':request,'query':query,'retrieval':p.retrieve(query,use_llm=request.get('use_llm',True))}}

def select(inputs,parameters,context):
    v=inputs['retrieved'];state=v['retrieval']['term_agent'];ids=set(state['selected_ids']);rows=v['retrieval']['candidates']
    return {'selected':{**v,'selection':{'selected':[x for x in rows if x['id'] in ids],
            'discarded_ids':[x['id'] for x in rows if x['id'] not in ids],'method':'term-agent','term_agent':state}}}

def module(p):return import_module(p.__class__.__module__.rsplit('.',1)[0]+'.term_agent')

def assemble(inputs,parameters,context):
    p=context['runtime'];v=inputs['selected']
    return {'assembled':{**v,'assembly':module(p).assemble(p,v['query'],v['selection'])}}

def answer(inputs,parameters,context):
    p=context['runtime'];v=inputs['assembled']
    return {'result':{**v,'answer':module(p).answer(p,v['query'],v['assembly'])}}

def load(inputs,parameters,context):
    from semantic_runtime.storage import publish
    r=inputs['request']
    return {'generation':publish(context['repository_root'],r['source_store'],r['output'],
            data_status=r.get('data_status','DRAFT'),export_allowed=r.get('export_allowed',False),scope=r.get('scope'))}

def feedback(inputs,parameters,context):
    from semantic_runtime.feedback import proposal_for
    return {'proposal':proposal_for(inputs['event'])}

"""Observational payload sizing. Never mutates a provider request."""
import copy,json

def compact(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))

def sizes(body):
    messages=body.get('messages',[])
    return {'message_chars':sum(len(m.get('content','')) for m in messages),
            'system_chars':sum(len(m.get('content','')) for m in messages if m.get('role')=='system'),
            'schema_chars':len(compact(body.get('response_format',{}))),
            'provider_bytes':len(compact(body).encode())}

def old_metadata(value):
    if isinstance(value,list):return [old_metadata(v) for v in value]
    if not isinstance(value,dict):return value
    out={k:old_metadata(v) for k,v in value.items() if k not in ('research_continuity','research_progress')}
    if 'progress' in out and isinstance(out['progress'],dict) and 'criterion' in out['progress']:
        out['progress']={k:v for k,v in out['progress'].items() if k in ('unchanged_turns','limit')}
    if 'research_task_history' in out:
        out['research_task_history']=[{k:({f:r['target'].get(f) for f in ('document_name','coordinate')} if r.get('target') else None) if k=='target' else r.get(k) for k in ('fields','side','question','status','target')} for r in out['research_task_history']]
    return out

def metrics(body):
    result=sizes(body);counterfactual=copy.deepcopy(body);parts=[]
    for message in counterfactual.get('messages',[]):
        try:value=json.loads(message.get('content',''))
        except (ValueError,TypeError):continue
        stripped=old_metadata(value)
        before=len(compact(value));after=len(compact(stripped))
        parts.append({'role':message.get('role'),'added_metadata_chars':before-after})
    result['added_continuity_metadata_chars']=sum(r['added_metadata_chars'] for r in parts)
    result['metadata_fraction_of_messages']=result['added_continuity_metadata_chars']/max(1,result['message_chars'])
    result['size_definition']='Unicode chars and UTF-8 compact provider bytes; actual billed tokens come only from provider usage. Metadata counterfactual keeps current sources/decisions; removes additive fields and restores old history shape; excludes static instruction text changes.'
    return result

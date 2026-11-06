"""Read-only accounting of real reviewer responses, native execution and unfinished SSE."""
from common import *
import base64,collections
from jsonschema import Draft202012Validator
pin=read(DES/'candidate-reviewed.json')
C=ROOT/pin['code_root']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage

def route(value,chain=False):
    return dict(action=value.get('action' if chain else 'next_action'),
        targets=[t['id'] for t in value.get('targets',[])] if chain else value.get('targets',[]),
        queries=value.get('queries',[]),structure_filter=value.get('structure_filter'))
def incomplete(path):
    value=read(path);body=base64.b64decode(value['body_base64'])
    messages=[];done=0;finish=[];seen=0
    for line in body.splitlines():
        if not line.startswith(b'data:'):continue
        raw=line[5:].strip()
        if raw==b'[DONE]':done+=1;continue
        try:event=json.loads(raw)
        except ValueError:continue
        for choice in event.get('choices',[]):
            seen+=1;messages.append(choice.get('delta',{}).get('content') or '')
            if choice.get('finish_reason'):finish.append(choice['finish_reason'])
    text=''.join(messages);decoder=json.JSONDecoder();remaining=text.strip();objects=[]
    while remaining:
        try:obj,end=decoder.raw_decode(remaining)
        except ValueError:break
        objects.append(obj);remaining=remaining[end:].strip()
        for prefix in ('```','```json'):
            if remaining.startswith(prefix):remaining=remaining[len(prefix):].lstrip()
    req=read(path.with_name('request.json.gz'));schema=req['response_format']['json_schema']['schema']
    return {'received_bytes':len(body),'deltas':seen,'content_chars':len(text),'done_frames':done,
        'finish_reasons':finish,'complete_objects_in_prefix':len(objects),'distinct_complete_objects':len({json.dumps(x,sort_keys=True) for x in objects}),
        'first_object_would_match_wire_schema':Draft202012Validator(schema).is_valid(objects[0]) if objects else None,
        'first_directive':objects[0].get('directive') if objects and isinstance(objects[0],dict) else None,'unfinished_tail_chars':len(remaining),
        'used_as_provider_result':False,'source':str(path.relative_to(ADR))}
rows=[]
for folder in sorted((ART/'public-live').iterdir()):
    result=read(folder/'result.json')['turns'][0]
    runid=result.get('run_id')
    traces=[]
    for jp in sorted((folder/'runtime').rglob('journal.sqlite')):
        if runid and jp.parent.name!=runid:continue
        with journal_storage.connect(jp.as_uri()+'?mode=ro',uri=True) as db:
            events=[(seq,k,json.loads(v)) for seq,k,v in db.execute("select seq,kind,payload_json from event where kind like 'SUPERVISOR_%' or kind in ('INVESTIGATION_CHAIN_STEP','READ_CANDIDATE_PAGE_SELECTED','ASSESSMENT_REVIEW_STOPPED') order by seq")]
        for i,(seq,k,v) in enumerate(events):
            item={'journal':jp.parent.name,'seq':seq,'kind':k}
            if k=='INVESTIGATION_CHAIN_STEP':
                item.update(route(v,True),labels=[t.get('label') for t in v.get('targets',[])],
                    reason=v.get('reason'),status=v.get('status'))
            elif k=='SUPERVISOR_DECISION':
                next_step=next(((n,e) for n,kind,e in events[i+1:] if kind=='INVESTIGATION_CHAIN_STEP'),None)
                item.update(directive=v['directive'],reason=v['reason'],remaining_scope=v['remaining_scope'],
                    cancelled=route(v['cancelled']) if v.get('cancelled') else None,accepted=route(v['accepted']),
                    next_chain_seq=next_step[0] if next_step else None,route_matches=bool(next_step and route(v['accepted'])==route(next_step[1],True)))
            elif k=='SUPERVISOR_HANDOFF':
                item.update(reason=v['reason'],later_chain_steps=[n for n,kind,e in events[i+1:] if kind=='INVESTIGATION_CHAIN_STEP'])
            else:item.update({key:v[key] for key in ('reason','number','directive','choice','actor','code') if key in v})
            traces.append(item)
    inputs=[]
    for p in sorted((folder/'canonical').glob('[0-9][0-9][0-9].json.gz')):
        v=read(p)['view']
        if 'proposed_action' not in v or 'remaining_supervisor_calls' not in v:continue
        choice=v['proposed_action'];out=p.with_name(p.name.replace('.json','-output.json'))
        inputs.append({'number':int(p.name[:3]),'trigger':v.get('trigger'),'proposal':choice,'current_goals':v.get('answer_progress_context',{}).get('current_goals',[]),
            'execution_plan':v.get('execution_plan'),'has_prior_selection':bool(v.get('previous_selector_proposal')),
            'actual_output':read(out) if out.exists() else None})
    rows.append({'cell':folder.name,'case_id':result['case_id'],'trace':traces,'review_inputs':inputs,
        'partial_streams':[incomplete(p) for p in sorted((folder/'raw').glob('call-*/partial.json.gz'))]})
put(ART/'supervisor-trace.json',{'cells':rows,'model_calls_by_audit':0})
for c in rows:
    print(c['cell'],[(x['kind'],x.get('directive'),x.get('action'),x.get('reason','')[:100],x.get('route_matches')) for x in c['trace']],c['partial_streams'])

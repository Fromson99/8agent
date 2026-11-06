"""Review each delivered answer and the case context recorded at command resolution."""
from common import ROOT,DES,ART,read,put
import collections
import json
import sqlite3

cell=ART/'public-live/conversation-repaired'
calls=read(cell/'calls.json')
recorded=[]
stages=[]
responses={}
def dicts(v):
    if isinstance(v,dict):
        yield v
        for child in v.values():yield from dicts(child)
    elif isinstance(v,list):
        for child in v:yield from dicts(child)

for plan in read(DES/'live-cases.json')[0]['steps']:
    target=cell/f"turn-{plan['number']}"
    if not (target/'request.json').exists():
        recorded.append({'turn':plan['number'],'state':'not_started','question':plan['question']})
        continue
    body=read(target/'request.json')
    model=[c for c in calls if c['turn']==body['request_id']]
    traces=[]
    for call in model:
        n=call['canonical_number'];path=cell/'canonical'/f'{n:03}.json.gz'
        inp=read(path)['view']
        if call['stage'] in ('source-request-route','memory-resolve','memory-resolve-repair','memory-command-check'):
            packet=read(cell/'raw'/f"call-{call['number']:03}"/'request.json.gz')
            wire=[]
            for msg in packet.get('messages',[]):
                try:wire.append(json.loads(msg['content']))
                except (ValueError,TypeError):wire.append(msg.get('content'))
            context=next((o for o in dicts(inp) if 'utterance' in o and 'goals' in o),{})
            goals=[{'id':g.get('id'),'task':(g.get('state') or {}).get('task'),
                'previous_text':(g.get('previous_response') or {}).get('text'),
                'last_review':(g.get('previous_response') or {}).get('review_status')} for g in context.get('goals') or []]
            outpath=cell/'canonical'/f'{n:03}-output.json.gz'
            traces.append({'call':call['number'],'stage':call['stage'],'known_outcome':call['status'],'goal_menu':goals,
                'literal_repeat_target':context.get('literal_repeat_target'),'methods':list(context.get('offered_methods') or {}),
                'prior_answer_turns_in_wire':[num for num,text in responses.items() if text and text in str(wire)],
                'model_output':read(outpath) if outpath.exists() else None})
    stages.append({'turn':plan['number'],'command_traces':traces})
    if not (target/'response.json.gz').exists():
        recorded.append({'turn':plan['number'],'state':'started_no_http_response','question':plan['question'],'call_stages':[row['stage'] for row in model]})
        continue
    resp=read(target/'response.json.gz'); val=resp['body']
    ans=val.get('answer') or {}
    ctx=(val.get('assembly') or {}).get('context') or []
    agent=(val.get('assembly') or {}).get('term_agent') or {}
    responses[plan['number']]=ans.get('text','') if isinstance(ans,dict) else None
    cd=read(target/'result.json')
    sources={x['id']:x for x in ctx if isinstance(x,dict) and 'id' in x}
    claims=[{'text':x.get('text'), 'selected_ids':x.get('source_ids',[]),
             'cited_originals':[{'source_id':sid,'text':sources[sid]['text']} for sid in x.get('source_ids',[]) if sid in sources]} for x in ans.get('claims',[])] if isinstance(ans,dict) else []
    recorded.append({'turn':plan['number'],'state':'http_received','question':plan['question'],'sent_question':body['question'],
        'status':resp['http_status'],'run_id':val.get('run_id'),'goal':val.get('question_id'),'case':val.get('investigation_id'),
        'revision':val.get('revision'),'method':val.get('method_id'),'executed':val.get('executed'),'coverage':agent.get('answer_coverage'),
        'answer_or_failure':(target/'public-answer.txt').read_text() if (target/'public-answer.txt').is_file() else val.get('message'),
        'claim_count':len(claims),'claim_evidence':claims,'source_ids':list(sources),'stop_reason':agent.get('stop_reason'),
        'model_stages':[row['stage'] for row in model],'model_calls':len(model),'unknown':cd['unknown'],'elapsed':cd['request_seconds'],
        'reported_cost':sum((c.get('usage') or {}).get('cost',0) for c in model),'duplicate':cd.get('duplicate')})
put(ART/'turn-audit.json',{'turns':recorded,'routing':stages,'note':'Command notes reflect canonical state and outbound wire. Earlier answers remain context only; cited originals are recorded separately.'})
for r in recorded:
    print(r['turn'],r['state'],r.get('status'),r.get('method'),r.get('goal'),r.get('executed'),r.get('coverage'),r.get('model_calls'),str(r.get('answer_or_failure'))[:170])

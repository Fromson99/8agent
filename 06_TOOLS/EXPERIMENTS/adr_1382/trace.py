"""Audit the source and previous-response deliveries after a closed live run."""
from common import ART, DES, ROOT, read, put
import sqlite3

base=ART/'public-live/photo-selected'
data=ROOT/read(DES/'baseline.json')['release']['data_path']
with sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True) as source:
    block=source.execute("SELECT text FROM source_block WHERE document_id=? AND block_id=?",('7bbe815ff43b6635','1390')).fetchone()[0]
assert '연 2회 이상의 결산기를 정한 회사는 매기에 총회를 소집하여야 한다.' in block
turns=[]
for turn in sorted(base.glob('turn-*')):
    saved=turn/'response.json.gz'
    if not saved.exists(): continue
    response=read(saved)
    body=response.get('body') or {}
    agent=(body.get('assembly') or {}).get('term_agent') or {}
    contexts=(body.get('assembly') or {}).get('context') or []
    answer=body.get('answer') or {}
    claims=answer.get('claims',[]) if isinstance(answer,dict) else []
    evidence=[c for c in contexts if block in c['text']]
    ids={c['id'] for c in evidence}
    turns.append({'turn':turn.name,'http':response['http_status'],'method':body.get('method_id'),'question_id':body.get('question_id'),
        'revision':body.get('revision'),'execution':body.get('executed'),'outcome':agent.get('accepted_outcome'),
        'source_ids_with_exact_365_2':sorted(ids),'claims_citing_365_2':[c for c in claims if ids.intersection(c.get('source_ids',[]))],
        'public_answer':(turn/'public-answer.txt').read_text() if (turn/'public-answer.txt').exists() else None,
        'error':body.get('error') or body.get('detail') if response['http_status']!=200 else None})
def walk(value,key):
    if isinstance(value,dict):
        for k,v in value.items():
            if k==key:yield v
            yield from walk(v,key)
    if isinstance(value,list):
        for v in value:yield from walk(v,key)
stages=[]
for call in read(base/'calls.json'):
    n=call['number']; packet=read(base/'raw'/f'call-{n:03}'/'request.json.gz')
    decoded=[]
    for message in packet['messages']:
        text=message.get('content','')
        try:
            import json
            decoded.append(json.loads(text))
        except (TypeError,ValueError):decoded.append(text)
    canonical=read(base/'canonical'/f'{n:03}.json.gz')['view']
    prior=[{'contains_turn1_answer':v.get('text')==turns[0]['public_answer'],'review_recovery':v.get('review_recovery'),
            'review_status':v.get('review_status'),'investigation_status':v.get('investigation_status')} for v in walk(canonical,'previous_response') if isinstance(v,dict)]
    stages.append({'n':n,'stage':call['stage'],'provider_status':call['status'],'http_status':call.get('http_status'),
        'exact_stored_365_2_in_wire':block in str(decoded),'previous_response':prior})
put(ART/'photo-trace.json',{'source':{'document_id':'7bbe815ff43b6635','article':'상법 제365조 제2항','block_id':'1390','stored_text':block},'turns':turns,'stages':stages})
print(turns)

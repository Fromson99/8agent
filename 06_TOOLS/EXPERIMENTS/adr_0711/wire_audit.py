"""Verify actual transmitted originals against durable views, without models."""
from pathlib import Path
import hashlib,json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0711-compact-selection-source-input';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
size=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')))
records=[];errors=[]
for case in read(A/'artifacts/design/dataset.json')['cases']:
 for arm in ('baseline','compact'):
  folder=O/arm/case['case_id'];paths=list((folder/'runtime').rglob('journal.sqlite'))
  assert len(paths)==1
  db=sqlite3.connect(paths[0].resolve().as_uri()+'?mode=ro',uri=True)
  for call in sorted((folder/'provider').glob('call-*')):
   req=read(call/'request.json');view=json.loads(req['messages'][1]['content'])['view']
   row=db.execute('SELECT body_json FROM model_view WHERE view_id=?',(view['view_id'],)).fetchone();assert row
   stored=json.loads(row[0]);texts={s['text_id']:s['text'] for s in view.get('sources',[]) if s.get('text_id')}
   count=0
   for index,source in enumerate(view.get('sources',[])):
    assert source['text']==stored['sources'][index]['text']
    assert source['source_id']==stored['sources'][index]['source_id']
   def walk(current,original,path='$'):
    global count
    if isinstance(current,list):
     for i,v in enumerate(current):walk(v,original[i],path+f'[{i}]')
    elif isinstance(current,dict):
     if 'text_ref' in current:
      ref=current['text_ref'];assert ref['id'] in texts
      assert 0<=ref['start']<ref['end']<=len(texts[ref['id']])
      assert texts[ref['id']][ref['start']:ref['end']]==original['text'],path
      count+=1
     for k,v in current.items():
      if k in original and k not in ('text_ref','text_id'):walk(v,original[k],path+'.'+k)
   walk(view,stored)
   response=read(call/'response.json') if (call/'response.json').exists() else {}
   records.append({'arm':arm,'case_id':case['case_id'],'call':call.name,'phase':view.get('source_stage'),
    'prompt_tokens':response.get('usage',{}).get('prompt_tokens'),'view_chars':size(view),
    'schema_chars':size(req['response_format']['json_schema']['schema']),
    'action_count':len(view.get('actions',[])),'source_count':len(view.get('sources',[])),
    'original_text_references_verified':count,'source_bytes_unchanged':True,
    'chain_steps':len(view.get('investigation_chain',{}).get('steps',[])),
    'input_projection':view.get('input_projection'),
    'request_sha256':hashlib.sha256((call/'request.json').read_bytes()).hexdigest()})
  db.close()
assert any(x['original_text_references_verified'] for x in records if x['arm']=='compact')
result={'status':'passed','source_text_unchanged':True,'all_text_refs_equal_durable_originals':True,
        'references_checked':sum(x['original_text_references_verified'] for x in records),'calls':records}
(O/'wire-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('Verified exact source text and',result['references_checked'],'wire references across',len(records),'saved provider calls')

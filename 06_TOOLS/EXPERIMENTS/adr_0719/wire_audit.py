"""Verify actual transmitted originals against durable views, without models."""
from pathlib import Path
import hashlib,json,sqlite3
R=Path(__file__).resolve().parents[3];number=int(Path(__file__).parent.name[-4:]);A=next((R/'04_EXPERIMENTS/ADR').glob(f'ADR-{number:04}-*'));O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
size=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')))
records=[];errors=[];gold_by_id={x['case_id']:x for x in read(A/'artifacts/design/gold.json')['cases']};coverage=[]
for case in read(A/'artifacts/design/dataset.json')['cases']:
 for arm in (('repaired',) if case['case_id'].startswith('S') else ('baseline','repaired')):
  folder=O/arm/case['case_id'];paths=list((folder/'runtime').rglob('journal.sqlite'))
  assert len(paths)==1
  gold_texts=[]
  db=sqlite3.connect(paths[0].resolve().as_uri()+'?mode=ro',uri=True)
  for call in sorted((folder/'provider').glob('call-*')):
   req=read(call/'request.json');view=json.loads(req['messages'][1]['content'])['view']
   row=db.execute('SELECT body_json FROM model_view WHERE view_id=?',(view['view_id'],)).fetchone();assert row
   stored=json.loads(row[0]);texts={s['text_id']:s['text'] for s in view.get('sources',[]) if s.get('text_id')}
   count=0
   for index,source in enumerate(view.get('sources',[])):
    assert source.get('text')==stored['sources'][index].get('text')
    assert source['source_id']==stored['sources'][index]['source_id']
    if source['source_id']==gold_by_id[case['case_id']]['source_id'] and source.get('text'):gold_texts.append(source['text'])
   for option in view.get('evidence_options',[]):
    assert option in stored.get('evidence_options',[])
    if option.get('source_id')==gold_by_id[case['case_id']]['source_id']:gold_texts.append(option['text'])
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
  combined=''.join(''.join(t.split()) for t in gold_texts)
  lines=[line for line in gold_by_id[case['case_id']]['text'].splitlines() if line.strip()]
  missing=[i for i,line in enumerate(lines) if ''.join(line.split()) not in combined]
  coverage.append({'arm':arm,'case_id':case['case_id'],'all_gold_lines_present':not missing,'gold_lines':len(lines),'missing_line_indices':missing})
# Direct small reads may need no duplicate span references. Every present reference is verified.
assert any(x['arm']=='repaired' for x in records)
result={'status':'passed','source_text_unchanged':True,'all_text_refs_equal_durable_originals':True,
        'gold_source_coverage':coverage,
        'candidate_all_gold_lines_present':all(x['all_gold_lines_present'] for x in coverage if x['arm']=='repaired'),
        'references_checked':sum(x['original_text_references_verified'] for x in records),'calls':records}
(O/'wire-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('Verified exact source text and',result['references_checked'],'wire references across',len(records),'saved provider calls')

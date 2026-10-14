"""Post-selection source extent and first-search audit; no product input changes."""
from pathlib import Path
from collections import defaultdict
import json,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0707-grounded-law-title-entry';O=A/'artifacts/run-001';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def ro(p):
 db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
f=read(D/'freeze.json');db=ro(R/f['source_generation']/'store.sqlite');did='0798989e52ca0254'
unit=json.loads(db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',(did,'1038')).fetchone()[0])
# This fixed diagnostic coordinate is used only after all product requests; it was never injected as a target.
expected_ids=set(map(str,range(*unit['span'])));rows=[]
for arm,case in read(D/'dataset.json')['order']:
 out=O/arm/case;result=read(out/'result.json');jd=ro(next((out/'runtime').rglob('journal.sqlite')))
 events=[{'kind':r['kind'],'payload':json.loads(r['payload_json'])} for r in jd.execute('SELECT kind,payload_json FROM event ORDER BY seq')];jd.close()
 relevant=[e for e in events if e['kind'] in ('LAW_TITLE_HINTS','REQUEST_ENTRY_ACCEPTED','LAW_STRUCTURE_DIRECTORY','LAW_FULLTEXT_DIRECTORY','LAW_SCOPED_FULLTEXT','LAW_DECISION_REJECTED')]
 modes=[e['kind'] for e in relevant if e['kind'] in ('LAW_STRUCTURE_DIRECTORY','LAW_FULLTEXT_DIRECTORY')]
 hint=next((e['payload'] for e in relevant if e['kind']=='LAW_TITLE_HINTS'),None)
 entry=next((e['payload'] for e in relevant if e['kind']=='REQUEST_ENTRY_ACCEPTED'),{})
 spans=defaultdict(list);requests=[];actions=[]
 def walk(v, inherited=None):
  if isinstance(v,dict):
   current=v.get('document_id',inherited)
   if current==did:
    for s in v.get('spans',[]):
     if isinstance(s,dict) and str(s.get('block_id')) in expected_ids and isinstance(s.get('text'),str) and isinstance(s.get('start_cp'),int) and isinstance(s.get('end_cp'),int):
      spans[str(s['block_id'])].append((s['start_cp'],s['end_cp'],s['text']))
   for x in v.values():walk(x,current)
  elif isinstance(v,list):
   for x in v:walk(x,inherited)
 for p in sorted((out/'provider').glob('call-*')):
  req=read(p/'request.json');v=json.loads(req['messages'][1]['content'])['view'];phase=v.get('source_stage',v.get('phase'));walk(v)
  requests.append({'phase':phase,'law_title_hints':v.get('law_title_hints')})
  resp=p/'response.json'
  if resp.exists():
   try:value=json.loads(read(resp)['choices'][0]['message']['content'])
   except (ValueError,KeyError,TypeError):continue
   if isinstance(value,dict) and 'next_action' in value:actions.append({'phase':phase,'action':value['next_action'],'reason':value.get('reason')})
 coverage=[]
 if case=='cm-018':
  for bid in sorted(expected_ids,key=int):
   text=db.execute('SELECT text FROM block_payload WHERE document_id=? AND block_id=?',(did,bid)).fetchone()[0]
   ranges=[]
   for lo,hi,body in spans[bid]:
    if text[lo:hi]!=body:raise AssertionError('Presented span does not match original')
    ranges.append((lo,hi))
   end=0
   for lo,hi in sorted(ranges):
    if lo>end:break
    end=max(end,hi)
   coverage.append({'block_id':bid,'original_chars':len(text),'covered_through':end,'complete':end>=len(text)})
 rows.append({'arm':arm,'case_id':case,'title_hints':hint,'search_selection':entry.get('search'),
   'context_quotes':entry.get('context_quotes'),'intent':entry.get('intent'),'command':entry.get('command'),
   'first_discovery':modes[0] if modes else None,'discovery_events':modes,'actions':actions,
   'cm_paragraph_1':{'document_id':did,'unit_id':'1038','expected_blocks':len(expected_ids),
      'physically_presented_complete':all(x['complete'] for x in coverage),'blocks':coverage} if coverage else None})
(O/'trace-review.json').write_text(json.dumps({'scope':'Physical model input spans, validated against selected source; no legal grading; title hints do not narrow authorization','cases':rows},ensure_ascii=False,indent=2)+'\n')
for row in rows:print(row['arm'],row['case_id'],row['first_discovery'],row['search_selection'],row['cm_paragraph_1'] and row['cm_paragraph_1']['physically_presented_complete'])

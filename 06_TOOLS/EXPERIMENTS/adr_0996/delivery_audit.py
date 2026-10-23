"""Post-run only: bind prepared receipts to actual wire evidence, not guidance labels."""
from common import *
import gzip,sqlite3

def unpack(v):
 if isinstance(v,dict):
  if set(v)=={'table_columns','table_rows'}:
   return [unpack(dict(zip(v['table_columns'],row))) for row in v['table_rows']]
  return {k:unpack(x) for k,x in v.items()}
 if isinstance(v,list):return [unpack(x) for x in v]
 return v

def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for x in v.values():yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)

sources={s['document_id']:s for s in read(DES/'curated-source-values.json')['sources']};rows=[]
for r in read(RUN/'result.json')['results']:
 p=RUN/'agent_layer'/r['arm']/r['case_id'];calls=[];events=[]
 for name in r['journal_paths']:
  db=sqlite3.connect((ROOT/name).resolve().as_uri()+'?mode=ro',uri=True)
  for kind,payload in db.execute("SELECT kind,payload_json FROM event WHERE kind IN ('KNOWLEDGE_ORIGINALS_PREPARED','KNOWLEDGE_INPUT_RETURNED','KNOWLEDGE_INPUT_FAILED')"):
   events.append({'kind':kind,'payload':json.loads(payload)})
  db.close()
 for path in sorted((p/'wire').glob('*.json.gz')):
  with gzip.open(path,'rt') as f:wire=json.load(f)
  data=unpack(json.loads(wire['messages'][1]['content']))['view']
  phase=data.get('source_stage',data.get('phase'))
  if not str(phase).startswith('memory-assess'):continue
  # Exclude all guidance, title/label/check descriptions: only evidence fields.
  content=list(strings({'sources':data.get('sources'),'evidence_options':data.get('evidence_options')}))
  present=[]
  for did,source in sources.items():
   for b in source['blocks']:
    if any(b['text'] in text for text in content):present.append({'document_id':did,'block_id':b['id'],'sha256':b['sha256']})
  refs_by_id={item['ref']['id']:item['source_refs'] for e in events if e['kind']=='KNOWLEDGE_ORIGINALS_PREPARED' for item in e['payload']['items']}
  expected={(ref['document_id'],str(ref['locator']),ref['content_hash']) for item in data.get('knowledge_original_review',{}).get('items',[]) if item['status']=='PREPARED' for ref in refs_by_id[item['ref']['id']]}
  actual={(x['document_id'],str(x['block_id']),x['sha256']) for x in present}
  calls.append({'expected_ref_count':len(expected),'missing_refs':sorted(expected-actual),'wire':str(path.relative_to(ROOT)),'sha256':sha(path),'phase':phase,'original_blocks':present,
    'review_task_present':bool(data.get('knowledge_original_review'))})
 row={'case_id':r['case_id'],'arm':r['arm'],'events':events,'assessment_inputs':calls,
      'every_assessment_prepared_refs_present':all(not c['missing_refs'] for c in calls) if calls else None,
      'all_prepared_ref_witnesses_in_wire':None}
 prepared=[e['payload'] for e in events if e['kind']=='KNOWLEDGE_ORIGINALS_PREPARED']
 if prepared and calls:
  expected={(ref['document_id'],str(ref['locator']),ref['content_hash']) for e in prepared for item in e['items'] if item['status']=='PREPARED' for ref in item['source_refs']}
  actual={(x['document_id'],str(x['block_id']),x['sha256']) for c in calls for x in c['original_blocks']}
  row['all_prepared_ref_witnesses_in_wire']=expected<=actual
  row['expected_count']=len(expected);row['delivered_count']=len(expected&actual)
 put(p/'delivery-audit.json',row);rows.append(row)
put(RUN/'delivery-audit.json',rows)
print(json.dumps([{k:v for k,v in r.items() if k not in ('events','assessment_inputs')} for r in rows],ensure_ascii=False))

"""Explain saved failures without executing or changing product decisions."""
from common import *
import json
C=ROOT/read(DES/'candidate-selected.json')['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage
rows=[]
for d in sorted((ART/'public-live').iterdir()):
 response=d/'turn-1/response.json.gz'
 if not response.exists():continue
 value=read(response);body=value['body'];reply=((body.get('assembly') or {}).get('term_agent') or {}).get('guided_reply') or {}
 if not reply.get('needs_guidance') and value['http_status']==200:continue
 errors=[]
 for path in (d/'runtime').rglob('*.sqlite'):
  db=journal_storage.connect(path.as_uri()+'?mode=ro',uri=True)
  if db.execute("SELECT count(*) FROM sqlite_master WHERE name='event'").fetchone()[0]:
   columns={r[1] for r in db.execute('PRAGMA table_info(event)')}
   if {'kind','payload_json'}<=columns:
    for row in db.execute("SELECT * FROM event WHERE kind='OUTPUT_DECISION_STATE'"):
     payload=json.loads(row['payload_json'])
     if payload.get('error'):errors.append({'journal':str(path.relative_to(ROOT)),'seq':row['seq'],'error':payload['error'],'status':payload.get('status'),'owner':payload.get('owner')})
  db.close()
 calls=read(d/'calls.json') if (d/'calls.json').exists() else []
 last_answer=[]
 for call in calls:
  raw=d/'raw'/f"call-{call['number']:03d}"/'response.json.gz'
  if call.get('stage')=='memory-guided-answer' and raw.exists():
   replyraw=read(raw);last_answer.append({'call':call['number'],'content':replyraw.get('choices',[{}])[0].get('message',{}).get('content'),'path':str(raw.relative_to(ROOT)),'sha256':sha(raw)})
 rows.append({'case_id':d.name.removesuffix('-selected'),'http_status':value['http_status'],'interruption':reply.get('interruption'),'saved_errors':errors,'model_final_outputs':last_answer,'unknown_calls':[c for c in calls if c['status'] in ('unknown','started')],'product_changed':False})
put(ART/'failure-diagnosis.json',{'cases':rows,'read_only':True,'new_model_calls':0})
print(json.dumps([{'case_id':r['case_id'],'http_status':r['http_status'],'errors':[e['error'] for e in r['saved_errors']],'unknown':len(r['unknown_calls'])} for r in rows],ensure_ascii=False))

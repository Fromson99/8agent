"""Read-only source, wire, memory and usage accounting after the declared stop."""
from common import *
import sqlite3,collections
C=ROOT/read(DES/'candidate-bounded.json')['code_root']
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent import journal_storage
from semantic_runtime.legal_agent.local_gemma import provider_request
data=ROOT/read(DES/'baseline.json')['release']['data_path']
source=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
unit_cache={};block_cache={};versions={};inventory=set()
public=read(DES/'source-scope.json')['public']
for did in public:
 versions[did]=source.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]
 units={str(uid):(None if parent is None else str(parent),json.loads(v)) for uid,parent,v in source.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,))}
 unit_cache[did]=units
 inventory.update((did,str(uid)) for uid,(_,v) in units.items() if v.get('family')=='kr_article')
def original(did,bid):
 key=(did,str(bid))
 if key not in block_cache:block_cache[key]=source.execute('SELECT unit_id,text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?',key).fetchone()
 return block_cache[key]
def article(did,bid):
 b=original(did,bid)
 if b is None:return None
 uid=str(b[0]);seen=set();units=unit_cache[did]
 while uid in units and uid not in seen:
  seen.add(uid);parent,v=units[uid]
  if v.get('family')=='kr_article':return did,uid
  uid=parent
 return None
def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for x in v.values():yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
rows=[]
for d in sorted((ART/'public-live').iterdir()):
 if not (d/'result.json').exists():continue
 r=read(d/'result.json');calls=read(d/'calls.json');raws=[read(p) for p in sorted((d/'raw').glob('call-*/request.json.gz'))]
 allowed=set(read(d/'binding.json')['scope']);acquired=set();presented=set()
 a={'case_id':r['case_id'],'source_checks':0,'delivered_checks':0,'source_mismatches':[],'acl_violations':[],'wire_mismatches':[],'attempts':0,'budget_reserved_by_request':{},'original_responses_rewritten':False}
 def verify(did,s,where):
  if did not in allowed:a['acl_violations'].append({'where':where,'document_id':did});return
  b=original(did,s['block_id'])
  if b is None or b[1][s['start_cp']:s['end_cp']]!=s['text'] or b[2]!=versions[did]:a['source_mismatches'].append({'where':where,'document_id':did,'block_id':s['block_id']});return
  root=article(did,s['block_id'])
  if root is not None:(acquired if where=='acquired' else presented).add(root)
 for jp in sorted((d/'runtime').rglob('*.sqlite')):
  db=journal_storage.connect(jp.as_uri()+'?mode=ro',uri=True);tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if {'evidence_unit','evidence_span'}<=tables:
   for x in db.execute('SELECT u.evidence_id,u.document_id,u.source_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
    verify(x['document_id'],dict(x),'acquired');a['source_checks']+=1
  if 'model_attempt' in tables:
   for x in db.execute('SELECT * FROM model_attempt ORDER BY created_seq'):
    a['attempts']+=1;out=provider_request(json.loads(x['request_json']));out['usage']={'include':True}
    if out not in raws:a['wire_mismatches'].append(x['attempt_id'])
  if {'event','budget'}<=tables and {'kind','payload_json'}<={x[1] for x in db.execute('PRAGMA table_info(event)')}:
   amounts=[dict(x) for x in db.execute('SELECT * FROM budget')]
   for x in db.execute("SELECT payload_json FROM event WHERE kind='REQUEST_BUDGET_BOUND'"):
    key=json.loads(x[0])['request_key'];a['budget_reserved_by_request'][key]=max(a['budget_reserved_by_request'].get(key,0),*[b.get('model_reserved',0) for b in amounts])
  db.close()
 wire_texts=[]
 for payload in raws:
  for msg in payload.get('messages',[]):
   text=msg.get('content','')
   try:v=json.loads(text)
   except (ValueError,TypeError):v=text
   wire_texts.extend(strings(v))
 def walk(v):
  if isinstance(v,dict):
   if v.get('document_id') and isinstance(v.get('spans'),list):
    for s in v['spans']:
     if isinstance(s,dict) and all(k in s for k in ('block_id','start_cp','end_cp','text')) and s['text'] and any(s['text'] in t for t in wire_texts):
      verify(v['document_id'],s,'wire');a['delivered_checks']+=1
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 for p in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):walk(read(p)['view'])
 a.update(acquired_articles=sorted(acquired),presented_articles=sorted(presented),physical_calls=len(calls),unknown=sum(c['status']=='unknown' for c in calls),reported_cost_usd=sum((c.get('usage') or {}).get('cost',0) for c in calls),reported_tokens=sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),model_seconds=sum(c.get('seconds',0) for c in calls),budget_reserved=sum(a['budget_reserved_by_request'].values()),resources=read(d/'resource-final.json'))
 a['budget_matches']=a['budget_reserved']==a['attempts']==len(calls)
 a['output_caps']=[k for p in raws for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in p]
 a['source_inventory_count']=len(inventory)
 put(d/'audit.json',a);rows.append(a)
source.close()
put(ART/'source-inventory.json',{'article_roots':sorted(inventory),'document_versions':versions})
put(ART/'source-wire-audit.json',{'cells':rows,'model_calls':0,'counting':'Article roots in same stored source version. Original spans are compared byte-for-byte in Python codepoint coordinates. Model delivery requires literal text in actual outbound input. No legal accuracy rate.'})
print(json.dumps([{k:x[k] for k in ('case_id','source_checks','delivered_checks','source_mismatches','acl_violations','wire_mismatches','physical_calls','budget_matches','acquired_articles','presented_articles')} for x in rows],ensure_ascii=False))

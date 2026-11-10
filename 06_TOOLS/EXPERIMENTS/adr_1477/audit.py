"""Read-only source, ACL, wire and usage accounting after the declared stop.

Originals were served from local Oracle Gold whose dataset_version equals the selected local
generation (design/oracle-gold.json); spans are therefore compared byte-for-byte against that
generation's store. Journals live in Oracle agent records, so acquired articles are taken from
the response's evidence inventory and the canonical model inputs, not from local SQLite journals."""
from common import *
import sqlite3
C=ROOT/read(DES/'candidate-selected-A.json')['code_root']
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent.local_gemma import provider_request
data=ROOT/read(DES/'baseline.json')['release']['data_path'];gold=read(DES/'oracle-gold.json')
assert read(data/'manifest.json')['store_sha256'] and gold['dataset_version']==read(DES/'baseline.json')['release']['data_manifest_sha256']
source=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
unit_cache={};block_cache={};versions={}
def units_of(did):
 if did not in unit_cache:unit_cache[did]={str(uid):(None if parent is None else str(parent),json.loads(v)) for uid,parent,v in source.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,))}
 return unit_cache[did]
def original(did,bid):
 key=(did,str(bid))
 if key not in block_cache:block_cache[key]=source.execute('SELECT unit_id,text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?',key).fetchone()
 return block_cache[key]
def article(did,bid):
 b=original(did,bid)
 if b is None:return None
 uid=str(b[0]);seen=set();units=units_of(did)
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
 if not (d/'result.json').exists() or not (d/'calls.json').exists():continue
 r=read(d/'result.json');calls=read(d/'calls.json');raws=[read(p) for p in sorted((d/'raw').glob('call-*/request.json.gz'))]
 allowed=set(read(d/'binding.json')['scope']);presented=set();acquired=set()
 for did in allowed:
  if did not in versions:versions[did]=source.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]
 a={'case_id':r['case_id'],'source_checks':0,'delivered_checks':0,'source_mismatches':[],'acl_violations':[],'wire_mismatches':[],'original_responses_rewritten':False}
 def verify(did,s,where):
  if did not in allowed:a['acl_violations'].append({'where':where,'document_id':did});return
  b=original(did,s['block_id'])
  if b is None or b[1][s['start_cp']:s['end_cp']]!=s['text'] or b[2]!=versions[did]:a['source_mismatches'].append({'where':where,'document_id':did,'block_id':s['block_id']});return
  root=article(did,s['block_id'])
  if root is not None:(presented if where=='wire' else acquired).add(root)
 wire_texts=[]
 for payload in raws:
  for msg in payload.get('messages',[]):
   text=msg.get('content','')
   try:v=json.loads(text)
   except (ValueError,TypeError):v=text
   wire_texts.extend(strings(v))
 def walk(v,where):
  if isinstance(v,dict):
   if v.get('document_id') and isinstance(v.get('spans'),list):
    for s in v['spans']:
     if isinstance(s,dict) and all(k in s for k in ('block_id','start_cp','end_cp','text')) and s['text']:
      if where=='wire' and not any(s['text'] in t for t in wire_texts):continue
      verify(v['document_id'],s,where);a['delivered_checks' if where=='wire' else 'source_checks']+=1
   for x in v.values():walk(x,where)
  elif isinstance(v,list):
   for x in v:walk(x,where)
 for p in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):walk(read(p)['view'],'wire')
 resp=d/'turn-1/response.json.gz'
 if resp.exists():walk(read(resp)['body'],'response')
 a.update(acquired_articles=sorted(acquired),presented_articles=sorted(presented),physical_calls=len(calls),unknown=sum(c['status']=='unknown' for c in calls),reported_cost_usd=sum((c.get('usage') or {}).get('cost',0) for c in calls),reported_tokens=sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),model_seconds=sum(c.get('seconds',0) for c in calls),resources=read(d/'resource-final.json'),sql=r.get('sql'),embedding_calls=len(read(d/'embedding-calls.json')) if (d/'embedding-calls.json').exists() else 0)
 a['output_caps']=[k for p in raws for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in p]
 a['providers']=sorted({str(c.get('actual_provider')) for c in calls})
 put(d/'audit.json',a);rows.append(a)
source.close()
put(ART/'source-wire-audit.json',{'cells':rows,'model_calls':0,'counting':'Spans in canonical model inputs (wire) and the response body are compared byte-for-byte with the selected generation store, which has the same dataset_version as the local Oracle Gold publication. Article roots per same stored source version. No legal accuracy rate.'})
print(json.dumps([{k:x[k] for k in ('case_id','source_checks','delivered_checks','source_mismatches','acl_violations','physical_calls','unknown','reported_cost_usd','embedding_calls','presented_articles')} for x in rows],ensure_ascii=False))

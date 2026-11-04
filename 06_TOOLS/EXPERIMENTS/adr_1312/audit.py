"""Offline source/wire/usage audit against same-artifact local originals."""
from common import *
import gzip,sqlite3,collections,statistics
def raw(p):
 with gzip.open(p,'rt') as f:return json.load(f)
C=ROOT/read(DES/'candidate-after.json')['code_root'];sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent import journal_storage
from semantic_runtime.legal_agent.local_gemma import provider_request
data=ROOT/read(DES/'baseline.json')['release']['data_path'];source=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
did='7bbe815ff43b6635';version=source.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]
assert all(o['anchor']['version']==version for e in read(DES/'scoring-only-originals.json') for o in e['originals'])
units={str(uid):(str(parent) if parent is not None else None,json.loads(text)) for uid,parent,text in source.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,))}
blocks={str(bid):(str(uid),text,h) for bid,uid,text,h in source.execute('SELECT block_id,unit_id,text,source_artifact_sha256 FROM source_block WHERE document_id=?',(did,))}
def article(block):
 uid=blocks[str(block)][0];seen=set()
 while uid in units and uid not in seen:
  seen.add(uid);parent,v=units[uid]
  if v.get('family')=='kr_article':return int(uid)
  uid=parent
 return None
inventory=sorted(int(uid) for uid,(_,v) in units.items() if v.get('family')=='kr_article')
allrows=[]
for d in sorted((ART/'live').iterdir()):
 if not (d/'result.json').exists():continue
 r=read(d/'result.json');calls=read(d/'calls.json');raws=[raw(p) for p in sorted((d/'raw').glob('call-*/request.json.gz'))]
 a={'cell':d.name,'case_id':r['case_id'],'arm':r['arm'],'http_status':r['http_status'],'source_checks':0,'delivered_checks':0,'source_mismatches':[],'acl_violations':[],'wire_mismatches':[],'acquired_articles':[],'presented_articles':[],'ontology_events':[],'failure':'','attempts':0,'budget_reserved_by_request':{},'raw_outputs_changed':False}
 acquired=set();presented=set();evidences={};supervisor_events=[]
 def verify(doc,s,where):
  if doc!=did:a['acl_violations'].append(where);return
  b=blocks.get(str(s['block_id']))
  if not b or b[1][s['start_cp']:s['end_cp']]!=s['text'] or b[2]!=version:a['source_mismatches'].append({'where':where,'block':s['block_id']});return
  root=article(s['block_id'])
  if root is not None:(acquired if where=='acquired' else presented).add(root)
 for jp in sorted((d/'runtime').rglob('*.sqlite')):
  db=journal_storage.connect(jp.as_uri()+'?mode=ro',uri=True);tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if {'evidence_unit','evidence_span'}<=tables:
   for x in db.execute('SELECT u.evidence_id,u.document_id,u.source_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
    verify(x['document_id'],dict(x),'acquired');a['source_checks']+=1;evidences.setdefault(x['evidence_id'],[]).append(dict(x))
  if 'model_attempt' in tables:
   for x in db.execute('SELECT * FROM model_attempt ORDER BY created_seq'):
    a['attempts']+=1;out=provider_request(json.loads(x['request_json']));out['usage']={'include':True}
    if out not in raws:a['wire_mismatches'].append(x['attempt_id'])
  if 'event' in tables and {'kind','payload_json'}<={x[1] for x in db.execute('PRAGMA table_info(event)')}:
   for x in db.execute('SELECT kind,payload_json FROM event'):
    if x['kind'].startswith('SUPERVISOR'):supervisor_events.append({'kind':x['kind'],'payload':json.loads(x['payload_json'])})
    if 'ONTOLOGY' in x['kind']:a['ontology_events'].append({'kind':x['kind'],'payload':json.loads(x['payload_json'])})
   if 'budget' in tables:
    amounts=[dict(x) for x in db.execute('SELECT * FROM budget')]
    for x in db.execute("SELECT payload_json FROM event WHERE kind='REQUEST_BUDGET_BOUND'"):
     key=json.loads(x[0])['request_key'];a['budget_reserved_by_request'][key]=max(a['budget_reserved_by_request'].get(key,0),*[b.get('model_reserved',0) for b in amounts])
  db.close()
 # Canonical sources count as delivered only when their literal text occurs in an actual wire input.
 def strings(v):
  if isinstance(v,str):yield v
  elif isinstance(v,dict):
   for x in v.values():yield from strings(x)
  elif isinstance(v,list):
   for x in v:yield from strings(x)
 wire_texts=[];wire_ontology=[]
 def collect_ontology(v,call):
  if isinstance(v,dict):
   for k,x in v.items():
    if k=='ontology_bundles' and isinstance(x,list):
     for bundle in x:wire_ontology.append({'call':call,'bundle':bundle})
    else:collect_ontology(x,call)
  elif isinstance(v,list):
   for x in v:collect_ontology(x,call)
 for call_number,payload in enumerate(raws,1):
  for msg in payload.get('messages',[]):
   content=msg.get('content','')
   try:value=json.loads(content)
   except (ValueError,TypeError):value=content
   wire_texts.extend(strings(value));collect_ontology(value,call_number)
 a['wire_ontology_inputs']=wire_ontology
 def walk(v):
  if isinstance(v,dict):
   if v.get('document_id') and isinstance(v.get('spans'),list):
    for s in v['spans']:
     if isinstance(s,dict) and all(k in s for k in ('block_id','start_cp','end_cp','text')) and s['text'] and any(s['text'] in t for t in wire_texts):
      verify(v['document_id'],s,'wire_delivered');a['delivered_checks']+=1
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 for p in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):walk(raw(p)['view'])
 a.update(acquired_articles=sorted(acquired),presented_articles=sorted(presented),physical_calls=len(calls),unknown=sum(x['status']=='unknown' for x in calls),reported_cost_usd=sum((x.get('usage') or {}).get('cost',0) for x in calls),reported_tokens=sum((x.get('usage') or {}).get('total_tokens',0) for x in calls),model_seconds=sum(x.get('seconds',0) for x in calls),actual_providers=dict(collections.Counter(x.get('actual_provider') or str(x.get('http_status')) for x in calls)))
 a['budget_reserved']=sum(a['budget_reserved_by_request'].values());a['budget_matches']=a['budget_reserved']==len(calls) and a['attempts']==len(calls)
 a['output_caps']=[k for p in raws for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in p]
 a['authorized_derivations']=len(read(d/'authorized-derivations.json')) if (d/'authorized-derivations.json').exists() else 0
 a['resources']=read(d/'resource-final.json') if (d/'resource-final.json').exists() else {};a['resource_stop']=(d/'resource-stop.json').exists()
 a['peak_rusage_below5GiB']=a['resources'].get('peak_rss_KiB',float('inf'))<5*1024**2
 log=ART/(d.name+'.log');failures=[]
 for line in log.read_text().splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  e=x.get('failure_diagnostics') or x.get('error_diagnostics',{}).get('diagnostics')
  if e and e.get('error_message'):failures.append({'type':e.get('error_type'),'message':e['error_message'],'location':e.get('location')})
 a['supervisor_events']=supervisor_events
 a['failures']=failures;a['failure']=failures[-1]['message'] if failures else ''
 response=raw(d/'response.json.gz')['body'];a['answer_coverage']=response.get('assembly',{}).get('term_agent',{}).get('accepted_outcome')
 a['review_ontology']=response.get('assembly',{}).get('term_agent',{}).get('review_explanation',{}).get('ontology')
 a['ontology_display_vs_wire_mismatch']=bool(wire_ontology) and (a['review_ontology'] or {}).get('status')=='PREPARED_NOT_SENT'
 put(d/'audit.json',a);allrows.append(a)
source.close()
put(ART/'source-wire-audit.json',{'fresh_process':True,'external_calls':0,'oracle_calls':0,'source_artifact_version':version,'source_article_inventory':inventory,'cells':allrows,'counting':'Article roots in the same-artifact source store. Delivered=canonical exact spans found in actual model wire inputs, including repeated delivery. Acquired=journal evidence spans. Metadata/candidate titles do not count as original text.'})
print(json.dumps([{k:a[k] for k in ('cell','physical_calls','source_checks','delivered_checks','failure','budget_matches','acquired_articles','presented_articles')} for a in allrows],ensure_ascii=False))

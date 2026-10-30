"""Read-only original/wire/journal audit. Never sends a model request."""
from common import *
import sys,sqlite3,gzip,collections
f=read(DES/'freeze-preflight-002.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent.local_gemma import provider_request
cid=sys.argv[1];P=ART/'live'/cid;r=read(P/'result.json');body=(read(P/'response.json').get('body') or {}) if (P/'response.json').exists() else {};answer=body.get('answer') or {};answer=answer if isinstance(answer,dict) else {}
scope=set(read(P/'request.json')['json']['document_ids']);data=ROOT/read(DES/'baseline.json')['release']['data_path'];db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
a={'case_id':cid,'http_status':r.get('http_status'),'status':r.get('status'),'model_calls':r['model_calls'],'seconds':r['seconds'],'claim_count':len(answer.get('claims',[])),'answer_chars':len(answer.get('text','')),'accepted_outcome':(body.get('assembly') or {}).get('term_agent',{}).get('accepted_outcome'),'span_checks':0,'delivered_span_checks':0,'source_mismatches':[],'acl_violations':[],'runs':[],'events':[],'assessments':[],'read_source_ids':[],'published_source_ids':sorted({s for c in answer.get('claims',[]) for s in c.get('source_ids',[])})}
def verify(did,span,where):
 raw=db.execute('select text from source_block where document_id=? and block_id=?',(did,str(span['block_id']))).fetchone()
 if not raw or raw[0][span['start_cp']:span['end_cp']]!=span['text']:a['source_mismatches'].append({'where':where,'document_id':did,'block_id':span['block_id']})
 if did not in scope:a['acl_violations'].append({'where':where,'document_id':did})
for jp in r['journals']:
 with sqlite3.connect((ROOT/jp).as_uri()+'?mode=ro',uri=True) as j:
  j.row_factory=sqlite3.Row;run=dict(j.execute('select * from run').fetchone());budget=dict(j.execute('select * from budget').fetchone());attempts=[dict(x) for x in j.execute('select attempt_id,request_hash,request_json,status,receipt_json from model_attempt order by created_seq')]
  a['runs'].append({'run_id':run['run_id'],'status':run['status'],'budget':budget,'attempts':[{k:v for k,v in x.items() if k!='request_json'} for x in attempts]})
  for x in attempts:
   recorded=[read(p) for p in sorted((P/'raw').glob('call-*/request.json.gz'))]
   outbound=provider_request(json.loads(x['request_json']));outbound['usage']={'include':True}
   assert outbound in recorded,'native-adapted reserved/physical body mismatch'
  for e in j.execute('select * from evidence_unit'):
   a['read_source_ids'].append(e['source_id'])
   for span in j.execute('select * from evidence_span where evidence_id=?',(e['evidence_id'],)):
    verify(e['document_id'],dict(span),'acquired');a['span_checks']+=1
  for x in j.execute('select seq,kind,payload_json from event order by seq'):
   if any(tag in x['kind'] for tag in ('SOURCE_GOAL','PROVIDER','REJECT','REPAIR','INDEPENDENT','SUPERVISOR','SCOPE_SOURCE','REQUIREMENT','RUN_FAILED')):a['events'].append({'seq':x['seq'],'kind':x['kind'],'payload':json.loads(x['payload_json'])})
  for x in j.execute("select version,payload_json from entity_version where kind='case_stage' and entity_id='case:ASSESS' order by version"):
   a['assessments'].append({'version':x['version'],'payload':json.loads(x['payload_json'])})
def walk(v):
 if isinstance(v,dict):
  if v.get('document_id') and isinstance(v.get('spans'),list):
   for x in v['spans']:
    if all(k in x for k in ('text','block_id','start_cp','end_cp')):verify(v['document_id'],x,'model_input');a['delivered_span_checks']+=1
  for x in v.values():walk(x)
 elif isinstance(v,list):
  for x in v:walk(x)
for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):walk(json.load(gzip.open(p,'rt'))['view'])
db.close();a['read_source_ids']=sorted(set(a['read_source_ids']));a['output_cap_fields']=[]
for p in sorted((P/'raw').glob('call-*/request.json.gz')):
 req=read(p)
 for k in ('max_tokens','max_completion_tokens','max_output_tokens'):
  if k in req:a['output_cap_fields'].append([p.parent.name,k])
a['physical_budget_matches']=sum(x['budget']['model_reserved'] for x in a['runs'])==r['model_calls']
a['new_model_calls_during_audit']=0;a['quality_certified']=False;put(P/'audit.json',a)
print(json.dumps({k:v for k,v in a.items() if k not in ('events','runs','assessments','read_source_ids','published_source_ids')},ensure_ascii=False))

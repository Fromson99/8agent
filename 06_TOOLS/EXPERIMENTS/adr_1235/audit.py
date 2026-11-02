"""Post-run read-only checks, separate from product context and model calls."""
from pathlib import Path
import json,gzip,hashlib,sys,sqlite3,collections
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1235-gold-ontology-transport-live';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):
 with (gzip.open(p,'rt') if str(p).endswith('.gz') else p.open()) as f:return json.load(f)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary,write_raw_json
binding=read(R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json');C=R/binding['engine_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.journal_storage import connect as journal_connect
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.contracts import digest
parent=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';base=read(parent/'artifacts/design/baseline.json');data=R/base['release']['data_path']
cid=sys.argv[1];P=O/'live'/cid;result=read(P/'result.json');calls=read(P/'calls.json') if (P/'calls.json').exists() else []
body=read(P/'response.json')['body'] if (P/'response.json').exists() else {};answer=body.get('answer') or {};answer=answer if isinstance(answer,dict) else {}
scope=set(read(P/'request.json')['json']['document_ids']);a={'case_id':cid,'final_answer_present':bool(answer.get('text','').strip()),'claim_count':len(answer.get('claims',[])),'answer_chars':len(answer.get('text','')),'http_status':result.get('http_status'),'status':result.get('status'),'source_checks':0,'nested_view_checks':0,'flat_view_checks':0,'source_mismatches':[],'acl_violations':[],'runs':[],'wire_request_matches':0,'wire_request_mismatches':[],'output_caps':[],'events':[],'assessments':[],'sqlite_corpus_fallback':False,'new_model_calls':0,'quality_certified':False}
# Original SQLite is opened only here, in the offline audit after inference.
db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-4096')
def verify(did,span,where):
 row=db.execute('select text from source_block where document_id=? and block_id=?',(did,str(span['block_id']))).fetchone()
 if not row or row[0][span['start_cp']:span['end_cp']]!=span['text']:a['source_mismatches'].append({'where':where,'document_id':did,'block_id':span['block_id']})
 if did not in scope:a['acl_violations'].append({'where':where,'document_id':did})
raw_requests=[read(p) for p in sorted((P/'raw').glob('*/request.json.gz'))]
for req in raw_requests:
 a['output_caps'] += [k for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in req]
acquired=[];journals=[]
for jp in sorted((P/'runtime').rglob('*.sqlite')):
 with journal_connect(jp.as_uri()+'?mode=ro',uri=True) as j:
  tables={x[0] for x in j.execute("select name from sqlite_master where type='table'")}
  if not {'evidence_unit','evidence_span','model_attempt','budget'}<=tables:continue
  journals.append(str(jp.relative_to(R)))
  runs=[dict(x) for x in j.execute('select * from run')];budgets=[dict(x) for x in j.execute('select * from budget')]
  a['runs'].append({'journal':str(jp.relative_to(R)),'runs':runs,'budgets':budgets})
  for x in j.execute('select attempt_id,request_json,status from model_attempt order by created_seq'):
   outbound=provider_request(json.loads(x['request_json']));outbound['usage']={'include':True}
   if outbound in raw_requests:a['wire_request_matches']+=1
   else:a['wire_request_mismatches'].append({'attempt_id':x['attempt_id'],'status':x['status']})
  for row in j.execute('select u.document_id,u.source_id,s.block_id,s.start_cp,s.end_cp,s.text from evidence_unit u join evidence_span s on s.evidence_id=u.evidence_id'):
   v=dict(row);verify(v['document_id'],v,'acquired');a['source_checks']+=1;acquired.append(v)
  for row in j.execute('select seq,kind,payload_json from event order by seq'):
   if any(t in row['kind'] for t in ['REJECT','FAILED','SUPERVISOR','SOURCE_GOAL','PROVIDER','REQUIREMENT']):a['events'].append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
  for row in j.execute("select version,payload_json from entity_version where kind='case_stage' and entity_id='case:ASSESS' order by version"):
   a['assessments'].append({'version':row['version'],'payload':json.loads(row['payload_json'])})
def walk(v):
 if isinstance(v,dict):
  if v.get('document_id') and isinstance(v.get('spans'),list):
   for s in v['spans']:
    if isinstance(s,dict) and all(k in s for k in ['text','block_id','start_cp','end_cp']):verify(v['document_id'],s,'nested_view');a['nested_view_checks']+=1
  for x in v.values():walk(x)
 elif isinstance(v,list):
  for x in v:walk(x)
finals=[]
for cp in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(cp)['view'];walk(v)
 for e in v.get('evidence_options',[]):
  if all(k in e for k in ['document_id','text','block_id','start_cp','end_cp']):verify(e['document_id'],e,'flat_view');a['flat_view_checks']+=1
 if str(v.get('source_stage','')).startswith('memory-assess'):
  finals.append({'path':str(cp.relative_to(R)),'view':v,'output':read(cp.with_name(cp.name.replace('.json.gz','-output.json.gz'))) if cp.with_name(cp.name.replace('.json.gz','-output.json.gz')).exists() else None})
a['final_assessment_inputs']=len(finals);a['physical_budget_matches']=sum(b['model_reserved'] for x in a['runs'] for b in x['budgets'])==len(calls)
a['tool_actions']=sum(b['tool_used'] for x in a['runs'] for b in x['budgets'])
a['model_seconds']=sum(x.get('seconds',0) for x in calls);a['other_seconds']=result['seconds']-a['model_seconds'];a['reported_cost_usd']=sum((x.get('usage') or {}).get('cost',0) or 0 for x in calls)
a['provider_counts']=dict(collections.Counter(tuple(x.get('provider',{}).get('only',[])) for x in calls)) if False else dict(collections.Counter('/'.join(x.get('provider',{}).get('only',[])) for x in calls))
a['http_counts']=dict(collections.Counter(str(x.get('http_status')) for x in calls));a['finish_reason_counts']=dict(collections.Counter(ch.get('finish_reason') for p in (P/'raw').glob('*/response.json.gz') for ch in read(p).get('choices',[])))
a['usage_reported_calls']=sum(bool(x.get('usage')) for x in calls);a['unknown']=result['unknown']
a['input_tokens']=sum((x.get('usage') or {}).get('prompt_tokens',0) for x in calls);a['output_tokens']=sum((x.get('usage') or {}).get('completion_tokens',0) for x in calls)
samples=read(P/'resources.json') if (P/'resources.json').exists() else []
a['resource']={'stop':(P/'resource-stop.json').exists(),'minimum_available_GiB':min((x['MemAvailable']/1024**3 for x in samples),default=None),'max_host_swap_growth_MiB':max((x['host_swap_growth']/1024**2 for x in samples),default=None),'max_rss_GiB':max((x['VmRSS']/1024**3 for x in samples),default=None)}
for name in read(P/'sqlite-opens.json'):
 if name!=':memory:' and str(P) not in name:a['sqlite_corpus_fallback']=True
storage={'checked':False,'reason':'No completed API answer assembly'}
if body.get('assembly',{}).get('term_agent',{}).get('case'):
 case=body['assembly']['term_agent']['case'];view=body['assembly']['term_agent']['judgment_view'];stages=[]
 with journal_connect((R/journals[0]).as_uri()+'?mode=ro',uri=True) as j:
  for stage,ref in case['judgment_refs'].items():
   row=j.execute('select payload_json,payload_hash from entity_version where kind=? and entity_id=? and version=?',(ref['kind'],ref['entity_id'],ref['version'])).fetchone()
   assert row and digest(json.loads(row[0]))==row[1]==ref['payload_hash'];stages.append(stage)
 with journal_connect(next((P/'runtime').rglob('cases-v4.sqlite')).as_uri()+'?mode=ro',uri=True) as j:
  rows=[(s,json.loads(r)) for s,r in j.execute('select status,response from request where response is not null')];matches=[(s,r) for s,r in rows if r.get('goal_id')==body['question_id']];assert len(matches)==1
  s,r=matches[0];storage={'checked':True,'stages':stages,'stored_request_status':s,'answer_equal':r['answer']['text']==answer['text'],'assessment_hash_equal':r['answer']['assessment_hash']==case['judgment_refs']['ASSESS']['payload_hash'],'view_hash_verified':digest({k:v for k,v in view.items() if k!='content_sha256'})==view['content_sha256']}
a['storage']=storage
raw=write_raw_json(P/'audit-detail.json.gz',{'events':a.pop('events'),'assessments':a.pop('assessments'),'acquired':acquired,'finals':finals});a['detail']=raw
write_summary(P/'audit.json',a);db.close()
print(json.dumps({k:v for k,v in a.items() if k not in ['runs','detail']},ensure_ascii=False,indent=2))

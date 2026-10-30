"""Read completed run evidence without retries, model calls or product changes."""
from common import *
import sqlite3,base64
cid=sys.argv[1];P=ART/'live'/cid
a=read(P/'audit.json');r=read(P/'result.json');calls=read(P/'calls.json')
data=ROOT/read(DES/'baseline.json')['release']['data_path']
nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
acquired=set()
for sid in a['read_source_ids']:
 row=nav.execute('select json from source where id=?',(sid,)).fetchone()
 if row:
  x=json.loads(row[0]);c=x.get('article_coordinate') or {}
  acquired.add((c.get('doc_id',x.get('document_id')),str(c.get('node',x.get('unit_id')))))
nav.close()
required=next(x for x in read(ART/'evaluation-only/cases.json') if x['id']==cid)['targets']
required_results=[{**x,'acquired':(x['doc_id'],str(x['node'])) in acquired} for x in required]
samples=[]
with gzip.open(P/'resource-samples.jsonl.gz','rt') as stream:
 for line in stream:samples.append(json.loads(line))
b=read(P/'resource-baseline.json');sample_set=samples or [b]
stats={'samples':len(samples),'minimum_available_gib':min(x['available'] for x in sample_set)/1024**3,
 'maximum_worker_rss_gib':max(x['rss'] for x in sample_set)/1024**3,
 'maximum_host_swap_growth_mib':max(x['swap_used']-b['swap_used'] for x in sample_set)/1024**2,
 'resource_stop':(P/'resource-stop.json').exists()}
runs=[]
for path in r['journals']:
 with sqlite3.connect((ROOT/path).as_uri()+'?mode=ro',uri=True) as j:
  state=j.execute('select status from run').fetchone()[0]
  attempts=[x[0] for x in j.execute('select status from model_attempt order by created_seq')]
  budget=j.execute('select model_reserved,tool_used from budget').fetchone()
  reviews=j.execute("select count(*) from event where kind='REQUIREMENT_COVERAGE_REVIEWED'").fetchone()[0]
  runs.append({'status':state,'attempts':attempts,'model_reserved':budget[0],'tool_used':budget[1],'requirement_review_events':reviews})
with sqlite3.connect(next((P/'runtime').rglob('cases-v4.sqlite')).as_uri()+'?mode=ro',uri=True) as store:
 request_status=[x[0] for x in store.execute('select status from request')]
partials=[]
for path in sorted((P/'raw').glob('call-*/partial-response.json.gz')):
 part=read(path);body=base64.b64decode(part['body_base64'])
 partials.append({'call':path.parent.name,'bytes':len(body),'whitespace_only':not body.strip(),
 'sha256':hashlib.sha256(body).hexdigest(),'diagnostics':part['diagnostics']})
pids=sorted({x.get('transport_diagnostics',{}).get('worker_pid') for x in calls}-{None})
diag={'case_id':cid,'source_version':'Frozen selected MAIN115 data; no external current-law validation',
 'required_originals':required_results,'request_status':request_status,'runs':runs,
 'model_calls':r['model_calls'],'elapsed_seconds':r['seconds'],'return_http_status':r.get('http_status'),
 'model_transport_seconds':sum(x.get('seconds',0) for x in calls),
 'completed_response_providers':sorted({x['actual_provider'] for x in calls if x.get('actual_provider')}),
 'requested_providers':[x['provider']['only'] for x in calls],
 'provider_switches':sum(x['kind']=='MODEL_PROVIDER_STATE' for x in a['events']),
 'source_goal_reads':sum(x['kind']=='SOURCE_GOAL_RESULT' and x['payload'].get('operation')=='READ' and x['payload'].get('status')=='ACQUIRED' for x in a['events']),
 'source_checks':a['span_checks'],'model_view_span_checks':a['delivered_span_checks'],
 'source_mismatches':a['source_mismatches'],'acl_violations':a['acl_violations'],
 'physical_budget_matches':a['physical_budget_matches'],'partial_responses':partials,'resource':stats,
 'worker_pids':pids,'remaining_worker_pids':[p for p in pids if Path('/proc',str(p)).exists()],
 'whole_case_retries':0,'new_model_calls_during_audit':0,'remote_cancel_confirmed':False,
 'upstream_internal_reason_known':False,'final_answer_present':bool((P/'answer.txt').read_text())}
put(P/'diagnosis.json',diag)
if not diag['final_answer_present']:
 unknown=[x for x in calls if x['status']=='unknown']
 why='Model response incomplete; '+unknown[-1].get('error_type','unknown') if unknown else 'No completed final answer; inspect saved run and model receipts'
 put(P/'content-review.json',{'case_id':cid,'passed':False,'failure_type':'other: incomplete_final_answer',
  'reason':why,'content_evaluated':False,'reference_answer_used_in_product':False,'new_model_calls':0})
print(json.dumps(diag,ensure_ascii=False))

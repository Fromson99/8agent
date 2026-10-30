"""Post-run evidence only; no product mutation, retry or provider request."""
from common import *
import sqlite3,base64
P=ART/'live/cm-007';a=read(P/'audit.json');r=read(P/'result.json');calls=read(P/'calls.json');f=read(DES/'freeze.json');data=ROOT/read(DES/'baseline.json')['release']['data_path']
assert r['http_status']==504 and len(calls)==2
assert calls[1]['status']=='unknown' and calls[1]['error_type']=='AbsoluteDeadlineExceeded'
partial=read(P/'raw/call-002/partial-response.json.gz');body=base64.b64decode(partial['body_base64']);assert len(body)==660 and not body.strip()
nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
acquired=[]
for sid in a['read_source_ids']:
 row=nav.execute('select json from source where id=?',(sid,)).fetchone()
 if row:
  x=json.loads(row[0]);c=x.get('article_coordinate') or {};acquired.append({'doc_id':c.get('doc_id',x.get('document_id')),'node':str(c.get('node',x.get('unit_id')))})
nav.close();required=next(x for x in read(ART/'evaluation-only/cases.json') if x['id']=='cm-007')['targets']
required_results=[{'law':x['law'],'article':x['article'],'doc_id':x['doc_id'],'node':x['node'],'acquired':{'doc_id':x['doc_id'],'node':str(x['node'])} in acquired} for x in required]
assert all(x['acquired'] for x in required_results)
samples=[]
with gzip.open(P/'resource-samples.jsonl.gz','rt') as stream:
 for line in stream:samples.append(json.loads(line))
b=read(P/'resource-baseline.json');stats={'samples':len(samples),'minimum_available_gib':min(x['available'] for x in samples)/1024**3,'maximum_worker_rss_gib':max(x['rss'] for x in samples)/1024**3,'maximum_host_swap_growth_mib':max(x['swap_used']-b['swap_used'] for x in samples)/1024**2,'resource_stop':(P/'resource-stop.json').exists()}
j=sqlite3.connect((ROOT/r['journals'][0]).as_uri()+'?mode=ro',uri=True);run=j.execute('select status from run').fetchone()[0];attempts=[x[0] for x in j.execute('select status from model_attempt order by created_seq')];budget=j.execute('select model_reserved,tool_used from budget').fetchone();reviews=j.execute("select count(*) from event where kind='REQUIREMENT_COVERAGE_REVIEWED'").fetchone()[0];assess=j.execute("select count(*) from entity_version where kind='case_stage' and entity_id='case:ASSESS'").fetchone()[0];j.close()
store=sqlite3.connect(next((P/'runtime').rglob('cases-v4.sqlite')).as_uri()+'?mode=ro',uri=True);request_status=[x[0] for x in store.execute('select status from request')];store.close()
pids=[182340]+[x['transport_diagnostics']['worker_pid'] for x in calls];remaining=[pid for pid in pids if Path('/proc',str(pid)).exists()]
assert run=='FAILED' and request_status==['FAILED'] and attempts==['SUCCEEDED','UNKNOWN'] and budget[0]==2 and not remaining
payload=read(P/'raw/call-002/request.json.gz')
wire_user=next(x['content'] for x in payload['messages'] if x['role']=='user')
review={'case_id':'cm-007','passed':False,'failure_type':'other: model_transport_absolute_deadline','reason':'No final answer: second request received HTTP200 headers and660 whitespace bytes, then absolute deadline. Both required originals were acquired. New requirement-review ASSESS was not reached.','content_evaluated':False,'reference_answer_used_in_product':False,'new_model_calls':0}
put(P/'content-review.json',review)
put(P/'diagnosis.json',{'case_id':'cm-007','source_version':'Frozen current MAIN114 data; no external current-law validation','required_originals':required_results,'request_status':request_status,'run_status':run,'model_attempt_statuses':attempts,'model_reserved':budget[0],'tool_used':budget[1],'requirement_review_events':reviews,'saved_assessments':assess,'source_goal_reads':sum(x['kind']=='SOURCE_GOAL_RESULT' and x['payload'].get('operation')=='READ' and x['payload'].get('status')=='ACQUIRED' for x in a['events']),'deadline':calls[1]['transport_diagnostics'],'partial_body_verified':{'bytes':len(body),'whitespace_only':True,'sha256':hashlib.sha256(body).hexdigest()},'resource':stats,'worker_pids':pids,'remaining_worker_pids':remaining,'return_http_status':r['http_status'],'elapsed_seconds':r['seconds'],'source_checks':a['span_checks'],'model_view_span_checks':a['delivered_span_checks'],'source_mismatches':a['source_mismatches'],'acl_violations':a['acl_violations'],'physical_budget_matches':a['physical_budget_matches'],'provider_switches':0,'whole_case_retries':0,'upstream_reason_known':False,'remote_cancel_confirmed':False,'unknown_call_usage_known':False,'payload_observation':{'user_chars':len(wire_user),'schema_utf8_bytes':len(json.dumps(payload['response_format'],ensure_ascii=False,separators=(',',':')).encode()),'causal_inference':'Large schema observed; not proven cause of upstream noncompletion.'},'store_audit_note':'storage-audit.json INCOMPLETE denotes no completed answer for gate; actual persisted request/run statuses are FAILED.','new_model_calls_during_audit':0})
print(json.dumps({'calls':2,'request_status':request_status,'run_status':run,'source_goals_acquired':3,'requirement_review_events':reviews,'required_originals':required_results,'resource':stats,'workers_gone':not remaining},ensure_ascii=False))

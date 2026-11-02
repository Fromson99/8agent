"""Fresh-process offline audit; no external client or Oracle connection."""
from common import *
import sqlite3,collections,os
F=read(DES/'freeze.json');C=ROOT/F['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage
from semantic_runtime.legal_agent.local_gemma import provider_request
P=ART/'live'/sys.argv[1];r=read(P/'result.json');response=read(P/'response.json') if (P/'response.json').exists() else {};body=response.get('body') or {};answer=body.get('answer') or {};answer=answer if isinstance(answer,dict) else {}
allowed=set(read(DES/'cases.json')[0]['request']['json']['document_ids']);data=ROOT/read(DES/'baseline.json')['release']['data_path']
source=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
a={'fresh_process':True,'http_status':response.get('status'),'answer_chars':len(answer.get('text','')),'source_checks':0,'delivered_checks':0,'source_mismatches':[],'acl_violations':[],'journals':[],'attempts':[],'wire_mismatches':[],'events':[],'assessments':[],'stored_responses':[],'publications':[],'request_budgets':{},'new_model_calls':0}
def verify(did,s,where):
 row=source.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(did,str(s['block_id']))).fetchone()
 if not row or row[0][s['start_cp']:s['end_cp']]!=s['text']:a['source_mismatches'].append({'where':where,'document_id':did,'block_id':s['block_id']})
 if did not in allowed:a['acl_violations'].append({'where':where,'document_id':did})
def walk(v):
 if isinstance(v,dict):
  if v.get('document_id') and isinstance(v.get('spans'),list):
   for s in v['spans']:
    if isinstance(s,dict) and all(k in s for k in ('text','block_id','start_cp','end_cp')):verify(v['document_id'],s,'model_input');a['delivered_checks']+=1
  for v2 in v.values():walk(v2)
 elif isinstance(v,list):
  for v2 in v:walk(v2)
raws=[read(p) for p in sorted((P/'raw').glob('call-*/request.json.gz'))]
for jp in sorted((P/'runtime').rglob('*.sqlite')):
 db=journal_storage.connect(jp.as_uri()+'?mode=ro',uri=True);tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")};info={'path':str(jp.relative_to(ROOT)),'tables':sorted(tables),'bytes':jp.stat().st_size}
 if 'run' in tables:info['runs']=[dict(x) for x in db.execute('SELECT * FROM run')]
 if 'budget' in tables:info['budget']=[dict(x) for x in db.execute('SELECT * FROM budget')]
 if {'evidence_unit','evidence_span'}<=tables:
  for x in db.execute('SELECT u.document_id,u.source_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
   verify(x['document_id'],dict(x),'acquired');a['source_checks']+=1
 if 'model_attempt' in tables:
  for x in db.execute('SELECT * FROM model_attempt ORDER BY created_seq'):
   saved=json.loads(x['request_json']);outbound=provider_request(saved);outbound['usage']={'include':True}
   if outbound not in raws:a['wire_mismatches'].append({'attempt_id':x['attempt_id'],'keys':sorted(outbound)})
   a['attempts'].append({'attempt_id':x['attempt_id'],'status':x['status'],'receipt':json.loads(x['receipt_json']) if x['receipt_json'] else None})
 if 'event' in tables and {'seq','kind','payload_json'}<={x[1] for x in db.execute('PRAGMA table_info(event)')}:
  for x in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'):
   if any(t in x['kind'] for t in ('REJECT','FAILED','UNKNOWN','SUPERVISOR','REQUIREMENT','SOURCE_GOAL','RUN_COMPLETED')):a['events'].append({'seq':x['seq'],'kind':x['kind'],'payload':json.loads(x['payload_json'])})
 if 'entity_version' in tables:
  for x in db.execute("SELECT version,payload_json FROM entity_version WHERE kind='case_stage' AND entity_id='case:ASSESS' ORDER BY version"):a['assessments'].append({'version':x['version'],'payload':json.loads(x['payload_json'])})
 if 'publication' in tables:a['publications'] += [dict(x) for x in db.execute('SELECT * FROM publication')]
 if 'request' in tables and {'status','response'}<={x[1] for x in db.execute('PRAGMA table_info(request)')}:
  for x in db.execute('SELECT status,response FROM request WHERE response IS NOT NULL'):
   v=json.loads(x['response']);saved_answer=v.get('answer') or {};a['stored_responses'].append({'path':str(jp.relative_to(ROOT)),'status':x['status'],'answer_chars':len(saved_answer.get('text','')) if isinstance(saved_answer,dict) else 0,'same_answer':bool(answer) and saved_answer==answer,'same_text':bool(answer) and isinstance(saved_answer,dict) and saved_answer.get('text')==answer.get('text')})
 if 'event' in tables and info.get('budget'):
  for e in db.execute("SELECT payload_json FROM event WHERE kind='REQUEST_BUDGET_BOUND'"):
   key=json.loads(e[0])['request_key'];a['request_budgets'][key]=max(a['request_budgets'].get(key,0),*(b.get('model_reserved',0) for b in info['budget']))
 a['journals'].append(info);db.close()
for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):walk(read(p)['view'])
source.close();calls=read(P/'calls.json');a['physical_calls']=len(calls);a['unknown']=sum(x['status'] in ('unknown','started') for x in calls);a['post_unknown_calls']=sum(len(calls)-i-1 for i,x in enumerate(calls) if x['status'] in ('unknown','started'));a['model_seconds']=sum(x.get('seconds',0) for x in calls);a['reported_cost_usd']=sum((x.get('usage') or {}).get('cost',0) or 0 for x in calls);a['missing_usage_calls']=sum(not x.get('usage') for x in calls);a['reported_input_tokens']=sum((x.get('usage') or {}).get('prompt_tokens',0) or 0 for x in calls);a['reported_output_tokens']=sum((x.get('usage') or {}).get('completion_tokens',0) or 0 for x in calls)
a['reserved']=sum(a['request_budgets'].values());a['physical_budget_matches']=a['reserved']==len(calls) and len(a['attempts'])==len(calls);a['output_cap_fields']=[k for v in raws for k in ('max_tokens','max_completion_tokens','max_output_tokens') if k in v]
a['provider_counts']=dict(collections.Counter('/'.join(x.get('provider',{}).get('only',[])) for x in calls));a['finish_reasons']=dict(collections.Counter(c.get('finish_reason') for p in (P/'raw').glob('call-*/response.json.gz') for c in read(p).get('choices',[])))
samples=[]
with gzip.open(P/'resource-samples.jsonl.gz','rt') as h:
 for line in h:samples.append(json.loads(line))
baseline=read(P/'resource-baseline.json');a['resources']={'samples':len(samples),'min_available_GiB':min((s['available']/1024**3 for s in samples),default=None),'peak_RSS_GiB':max((s['rss']/1024**3 for s in samples),default=None),'max_swap_growth_MiB':max(((s['swap_used']-baseline['swap_used'])/1024**2 for s in samples),default=None),'resource_stop':read(P/'resource-stop.json') if (P/'resource-stop.json').exists() else None}
a['runtime_bytes']=sum(p.stat().st_size for p in (P/'runtime').rglob('*') if p.is_file());a['runtime_db_bytes']=sum(j['bytes'] for j in a['journals']);a['changed_release_files']=[n for n,h in F['files'].items() if sha(C/n)!=h];a['changed_inputs']=[n for n,h in F['inputs'].items() if sha(ROOT/n)!=h];a['active_pointer_unchanged']=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==F['pointer_sha256'];a['cleanup_completed']=(P/'cleanup.json').exists();a['duplicate']=read(P/'duplicate.json') if (P/'duplicate.json').exists() else None
follow=read(P/'follow-response.json') if (P/'follow-response.json').exists() else {}
fb=follow.get('body') or {}
a['followup']={'http_status':follow.get('status'),'same_goal':bool(fb) and fb.get('goal_id')==body.get('goal_id'),'same_investigation':bool(fb) and fb.get('investigation_id')==body.get('investigation_id'),'claims':len((fb.get('answer') or {}).get('claims',[])),'read_assessment':fb.get('assembly',{}).get('term_agent',{}).get('accepted_outcome'),'executed_stages':fb.get('executed_stages'),'duplicate':read(P/'follow-duplicate.json') if (P/'follow-duplicate.json').exists() else None}
a['turn_calls']=dict(collections.Counter(x['turn'] for x in calls))
a['first_turn_review']=body.get('assembly',{}).get('term_agent',{}).get('accepted_outcome');a['first_turn_claims']=len(answer.get('claims',[]))
a['turns']=read(P/'turns.json');a['responses']={}
from semantic_runtime.legal_agent.review_explanation import verify as verify_explanation
for turn in a['turns']:
 rp=P/(turn['label']+'-response.json.gz')
 response=read(rp);b=response.get('body') or {};meta=b.get('assembly',{}).get('term_agent',{});view=meta.get('review_explanation')
 entry={'http_status':response['status'],'goal_id':b.get('goal_id'),'revision':b.get('revision'),'claims':len((b.get('answer') or {}).get('claims',[])),'executed_stages':b.get('executed_stages')}
 if view:
  verify_explanation(view)
  entry.update(explanation_hash_verified=True,items=view['items'],ontology_status=view['ontology']['status'],ontology_adoption=view['ontology']['adoption'],ontology_bundles=view['ontology'].get('bundles',[]))
 if meta.get('scenario_comparison'):entry['comparison']=meta['scenario_comparison']
 if meta.get('scenario_context'):entry['hypothetical']=meta['scenario_context']
 a['responses'][turn['label']]=entry
# Current baseline and hypothetical response validated from fresh native journals.
os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=str(DES/'ontology-config.json')
from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
from semantic_runtime.legal_agent.unified_publication import validate_saved
a['current_publication_checks']=[]
for label in ('baseline-after','semantic-low','semantic-high','semantic-rule'):
 if label not in a['responses'] or a['responses'][label]['http_status']!=200:continue
 b=read(P/(label+'-response.json.gz'))['body']
 jp=next((P/'runtime').glob('legal-agent/runs/*/'+b['run_id']+'/journal.sqlite'))
 repo=UnifiedRepository(jp)
 try:validate_saved(repo,b);a['current_publication_checks'].append({'label':label,'valid':True})
 finally:repo.close()
put(P/'audit.json',a)
print(json.dumps({k:a[k] for k in ('http_status','answer_chars','source_checks','delivered_checks','source_mismatches','acl_violations','wire_mismatches','physical_calls','unknown','post_unknown_calls','reported_cost_usd','duplicate','active_pointer_unchanged')},ensure_ascii=False))

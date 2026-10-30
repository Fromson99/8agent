"""Post-run scope, actual wire, purpose rejection and integrity audit; no requests."""
from common import *
import sqlite3,collections,os
P=ART/'live/cm-009';f=read(DES/'freeze-live.json');b=read(DES/'baseline.json');r=read(P/'result.json');a=read(P/'audit.json')
sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.judgment_changes import PROMPT
data=ROOT/b['release']['data_path'];db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
j=sqlite3.connect((ROOT/r['journals'][0]).as_uri()+'?mode=ro',uri=True);j.row_factory=sqlite3.Row
# The frozen service uses plain TEXT journals; do not accidentally decode BLOBs with sqlite.
assert not j.execute("select 1 from event where typeof(payload_json)!='text' limit 1").fetchone()
events=[{'seq':x['seq'],'kind':x['kind'],'payload':json.loads(x['payload_json'])} for x in j.execute('select seq,kind,payload_json from event order by seq')]
acquired=[dict(x) for x in j.execute('select u.document_id,u.source_id,s.block_id,s.start_cp,s.end_cp,s.text from evidence_unit u join evidence_span s on s.evidence_id=u.evidence_id')]
def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for x in v.values():yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
def coverage(expected,spans):
 missing=[]
 for e in expected:
  hits=sorted((x['start_cp'],x['end_cp']) for x in spans if x.get('document_id')==e['document_id'] and str(x.get('block_id'))==e['block_id'])
  cursor=e['start_cp']
  for lo,hi in hits:
   if lo<=cursor:cursor=max(cursor,hi)
  if cursor<e['end_cp']:missing.append(e['block_id'])
 return {'complete':not missing,'expected_blocks':[e['block_id'] for e in expected],'missing_blocks':missing}
did='3521c3aaa5a735fd';expected={}
for suffix in ('마','바'):
 coord='제31조제1항제3호'+suffix+'목'
 units=[json.loads(x[0]) for x in db.execute('select json from source_unit where document_id=?',(did,))]
 unit=next(u for u in units if u.get('legal_coordinate',{}).get('surface')==coord)
 lo,hi=unit['span'];parts=[]
 for bid,txt in db.execute('select block_id,text from source_block where document_id=? and cast(block_id as integer)>=? and cast(block_id as integer)<? order by cast(block_id as integer)',(did,lo,hi)):
  parts.append({'document_id':did,'block_id':str(bid),'start_cp':0,'end_cp':len(txt),'text':txt,'text_hash':digest(txt)})
 assert parts
 expected[coord]={'unit_id':unit['id'],'parts':parts,'acquired':coverage(parts,acquired)}
origin=db.execute('select text from source_block where document_id=? and block_id=?',(did,'200')).fetchone()[0]
canon=[];flat_checks=0;mismatches=[];acl=[];scope=set(read(DES/'corpus.json')['document_ids'])
for cp in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(cp)['view']
 for e in v.get('evidence_options',[]):
  if not all(k in e for k in ('document_id','block_id','start_cp','end_cp','text')):continue
  flat_checks+=1
  row=db.execute('select text from source_block where document_id=? and block_id=?',(e['document_id'],str(e['block_id']))).fetchone()
  if not row or row[0][e['start_cp']:e['end_cp']]!=e['text']:mismatches.append({'canonical':cp.name,'id':e.get('id')})
  if e['document_id'] not in scope:acl.append(e['id'])
 stage=read(cp.with_name(cp.name.replace('.json.gz','-summary.json')))['stage']
 if not stage.startswith('memory-assess'):continue
 num=int(cp.name[:3]);physical=next(c for c in read(P/'calls.json') if c['stage']==stage)
 req=read(P/f"raw/call-{physical['number']:03d}/request.json.gz")
 payload=json.loads(req['messages'][-1]['content']);texts=list(strings(payload));o=read(cp.with_name(cp.name.replace('.json.gz','-output.json.gz')))
 out={'canonical':num,'physical':physical['number'],'stage':stage,'system_chars':len(req['messages'][0]['content']),
  'change_prompt_delivered':PROMPT in req['messages'][0]['content'],
  'change_schema_delivered':'change_review' in json.dumps(req['response_format']),
  'source13_original_reference_delivered':any(origin in t for t in texts),'scope':{},'not_used':[],
  'material_gaps':o['gaps'],'requirement_review':o['requirement_review'],
  'feedback':{k:x for k,x in (v.get('repair_feedback') or {}).items() if k!='rejected_assessment'}}
 heads={x['id']:x for x in v['read_judgments']['judgments']}
 for coord,e in expected.items():
  entry=coverage(e['parts'],v['evidence_options']);entry['actual_wire_blocks']=[s['block_id'] for s in e['parts'] if any(s['text'] in t for t in texts)]
  entry['actual_wire_complete']=len(entry['actual_wire_blocks'])==len(e['parts']);out['scope'][coord]=entry
 for row in o['read_judgment_review']['judgments']:
  if row['disposition']!='NOT_USED':continue
  h=heads[row['id']]
  out['not_used'].append({'output':row,'source_id':h['source_id'],'document_name':h['document_name'],'heading':h['heading'],'prior':h.get('change_from'),'purposes':h['review_purposes'],'change_record_present':bool(row.get('change_review'))})
 canon.append(out)
state=read(P/'investigation-state.json');goals=[g for s in state.get('investigation_supervisor',{}).values() for g in s.get('source_goals',[])]
bundle_events=[e for e in events if e['kind']=='SOURCE_REFERENCE_BUNDLE_BOUND']
scope_result={'expected':expected,'origin_source13':{'document_id':did,'block_id':'200','text':origin},'final_inputs':canon,
 'goals':goals,'bundle_events':bundle_events,'flat_final_evidence_checks':flat_checks,'flat_mismatches':mismatches,'flat_acl_violations':acl,
 'required_source_complete':all(x['acquired']['complete'] for x in expected.values()),
 'required_final_delivery_complete':bool(canon) and all(all(x['complete'] and x['actual_wire_complete'] for x in c['scope'].values()) for c in canon),
 'new_model_calls':0,'scope_note':'Article root presence and original13 citation text do not prove target31 body acquisition.'}
put(P/'exact-scope-audit.json',scope_result)
casedb=sqlite3.connect(next((P/'runtime').rglob('cases-v4.sqlite')).as_uri()+'?mode=ro',uri=True)
request_statuses=[list(x) for x in casedb.execute('select status,count(*) from request group by status')]
calls=read(P/'calls.json');samples=[json.loads(line) for line in gzip.open(P/'resource-samples.jsonl.gz','rt')];baseline=read(P/'resource-baseline.json')
diagnosis={'case_id':'cm-009','http_status':r['http_status'],'run_status':a['runs'][0]['status'],'request_statuses':request_statuses,
 'failure_codes':sorted({i['code'] for c in canon for i in c.get('feedback',{}).get('validation',{}).get('issues',[])}),
 'assessment_rejections':[e for e in events if e['kind']=='COMPLETION_ASSESSMENT_REJECTED'],
 'supervisor_rejections':[e for e in events if 'SUPERVISOR' in e['kind'] and 'REJECT' in e['kind']],
 'requirement_gap_reconciliations':[e for e in events if e['kind']=='REQUIREMENT_GAPS_RECONCILED'],
 'final_answer_count':int(a['claim_count']>0),'reviewer_calls':sum('final-original-review' in x['stage'] for x in calls),
 'calls':len(calls),'tools':a['runs'][0]['budget']['tool_used'],'seconds':r['seconds'],'model_seconds':sum(x['seconds'] for x in calls),
 'other_seconds':r['seconds']-sum(x['seconds'] for x in calls),'http_counts':dict(collections.Counter(str(x['http_status']) for x in calls)),
 'usage':{'input_tokens':sum((x.get('usage') or {}).get('prompt_tokens',0) for x in calls),'output_tokens':sum((x.get('usage') or {}).get('completion_tokens',0) for x in calls),'known_response_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls),'usage_complete':all(isinstance(x.get('usage'),dict) for x in calls),'unreported_usage_http':[x['http_status'] for x in calls if not isinstance(x.get('usage'),dict)]},
 'unknown_attempts':sum(x['status']!='responded' for x in calls),'all_workers_reaped':all(x['transport_diagnostics']['worker_reaped'] for x in calls),
 'resource_stop':(P/'resource-stop.json').exists(),'min_available_gib':min(x['available'] for x in samples)/1024**3,
 'max_swap_growth_mib':max(x['swap_used']-baseline['swap_used'] for x in samples)/1024**2,
 'new_model_calls_during_audit':0}
put(P/'diagnosis.json',diagnosis)
check={'candidate_files_unchanged':all(sha(ROOT/f['code_root']/p)==h for p,h in f['files'].items()),
 'frozen_inputs_unchanged':all(sha(ROOT/p)==h for p,h in f['inputs'].items()),
 'frozen_scripts_unchanged':all(sha(ROOT/p)==h for p,h in f['scripts'].items()),
 'working_files_unchanged':all(sha(ROOT/p)==h for p,h in b['working_files'].items()),
 'active_main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']}
assert all(check.values()),check
put(ART/'post-run-integrity.json',{'checks':check,'candidate_files':len(f['files']),'working_files':len(b['working_files']),'new_model_calls':0})
put(ART/'audit-helper-errors.json',{'failures':[{'script':'composition_audit.py','error':'IndexError: list index out of range','cause':'Caller omitted cm-009 argument','corrected_command':'.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1203/composition_audit.py cm-009','outcome':'Correctly recorded no final assessment/compose; no new request'},
 {'script':'ad-hoc read-only inspection','error':"AttributeError: 'str' object has no attribute 'get'",'cause':'completion_contract is a version string; actual goals are under investigation_supervisor','correction':'Read investigation_supervisor/source_goals; no product change'}],
 'reader_failure':'artifacts/audit-preparation-correction.json','new_model_calls':0})
print(json.dumps({'scopes':{k:v['acquired'] for k,v in expected.items()},'final_scope_pass':scope_result['required_final_delivery_complete'],'diagnosis':{k:v for k,v in diagnosis.items() if k not in ('assessment_rejections','supervisor_rejections')},'integrity':check},ensure_ascii=False))

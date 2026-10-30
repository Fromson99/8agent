"""Read-only one-run audit: source spans, declared needs, wire and resource state."""
from common import *
import collections,sqlite3
P=ART/'live/cm-009';f=read(DES/'freeze-live.json');b=read(DES/'baseline.json');r=read(P/'result.json');a=read(P/'audit.json')
sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.need_continuity import PROMPT as NEED_PROMPT
from semantic_runtime.legal_agent.judgment_changes import PROMPT as CHANGE_PROMPT
db=sqlite3.connect((ROOT/b['release']['data_path']/'store.sqlite').as_uri()+'?mode=ro',uri=True)
j=connect((ROOT/r['journals'][0]).as_uri()+'?mode=ro',uri=True)
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
units=[json.loads(x[0]) for x in db.execute('select json from source_unit where document_id=?',(did,))]
for suffix in ('마','바'):
 coord='제31조제1항제3호'+suffix+'목';unit=next(u for u in units if u.get('legal_coordinate',{}).get('surface')==coord)
 lo,hi=unit['span'];parts=[]
 for bid,txt in db.execute('select block_id,text from source_block where document_id=? and cast(block_id as integer)>=? and cast(block_id as integer)<? order by cast(block_id as integer)',(did,lo,hi)):
  parts.append({'document_id':did,'block_id':str(bid),'start_cp':0,'end_cp':len(txt),'text':txt,'text_hash':digest(txt)})
 assert parts;expected[coord]={'unit_id':unit['id'],'parts':parts,'acquired':coverage(parts,acquired)}
origin=db.execute('select text from source_block where document_id=? and block_id=?',(did,'200')).fetchone()[0]
state=read(P/'investigation-state.json') if (P/'investigation-state.json').exists() else {}
all_needs={};snapshots=[]
for sp in sorted((P/'states').glob('[0-9][0-9][0-9].json.gz')):
 st=read(sp);current={k:v for s in st.get('investigation_supervisor',{}).values() for k,v in s.get('material_needs',{}).items()}
 snapshots.append({'file':sp.name,'ids':sorted(current),'previous_ids_missing':sorted(set(all_needs)-set(current))});all_needs.update(current)
goals=[g for s in state.get('investigation_supervisor',{}).values() for g in s.get('source_goals',[])]
model_declarations=[]
for op in sorted((P/'canonical').glob('*-output.json.gz')):
 proposal=read(op)
 for goal in proposal.get('answer_progress',{}).get('goals',[]):
  if not goal.get('material_need','').strip():continue
  model_declarations.append({'file':op.name,'choice':proposal.get('choice'),'issue_id':goal['issue_id'],
   'material_need':goal['material_need'],'status':goal['status'],
   'present_in_committed_need_ledger':any(' '.join(n['text'].split())==' '.join(goal['material_need'].split()) for n in all_needs.values())})
finals=[];flat_checks=0;mismatches=[];acl=[];scope=set(read(DES/'corpus.json')['document_ids']);calls=read(P/'calls.json')
for cp in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 payload=read(cp);v=payload['view'];stage=read(cp.with_name(cp.name.replace('.json.gz','-summary.json')))['stage']
 for e in v.get('evidence_options',[]):
  if not all(k in e for k in ('document_id','block_id','start_cp','end_cp','text')):continue
  flat_checks+=1;row=db.execute('select text from source_block where document_id=? and block_id=?',(e['document_id'],str(e['block_id']))).fetchone()
  if not row or row[0][e['start_cp']:e['end_cp']]!=e['text']:mismatches.append({'canonical':cp.name,'id':e.get('id')})
  if e['document_id'] not in scope:acl.append(e['id'])
 if not stage.startswith('memory-assess'):continue
 matching=[c for c in calls if c['stage']==stage]
 if not matching:continue
 physical=matching[-1];req=read(P/f"raw/call-{physical['number']:03d}/request.json.gz")
 wire=json.loads(req['messages'][-1]['content']);texts=list(strings(wire));op=cp.with_name(cp.name.replace('.json.gz','-output.json.gz'));out=read(op) if op.exists() else None
 ctx=v.get('read_judgments',{});needs=ctx.get('needs',[]);known={n['id'] for n in needs};review=(out or {}).get('read_judgment_review',{});rows=review.get('needs',[])
 item={'canonical':cp.name,'physical':physical['number'],'stage':stage,'need_continuity_present':bool(ctx.get('need_continuity')),
  'need_ids':sorted(known),'need_count':len(needs),'material_need_count':sum(n.get('origin')=='ANSWER_PROGRESS' for n in needs),
  'prior_declared_ids_missing':sorted(set(all_needs)-known),'needs_text_delivered':{n['id']:any(n.get('text','') in t for t in texts) for n in needs},
  'need_prompt_delivered':NEED_PROMPT in req['messages'][0]['content'],'change_prompt_delivered':CHANGE_PROMPT in req['messages'][0]['content'],
  'wire_schema_has_change_review':'change_review' in json.dumps(req['response_format']),
  'stop_reason':v.get('investigation_stop_reason'),'latest_goals':ctx.get('need_continuity',{}).get('latest_goals',[]),
  'source13_reference_delivered':any(origin in t for t in texts),'scope':{},'output_exists':out is not None,
  'output_need_rows':rows,'output_missing_ids':sorted(known-{n['id'] for n in rows}),'output_duplicate_ids':[n for n,count in collections.Counter(n['id'] for n in rows).items() if count>1],
  'output_judgments':review.get('judgments',[]),'material_gaps':(out or {}).get('gaps'),
  'issue_assessments':(out or {}).get('issue_assessments'),'requirement_review':(out or {}).get('requirement_review'),
  'feedback':{k:x for k,x in (v.get('repair_feedback') or {}).items() if k!='rejected_assessment'}}
 for coord,e in expected.items():
  entry=coverage(e['parts'],v.get('evidence_options',[]));entry['actual_wire_blocks']=[s['block_id'] for s in e['parts'] if any(s['text'] in t for t in texts)]
  entry['actual_wire_complete']=len(entry['actual_wire_blocks'])==len(e['parts']);item['scope'][coord]=entry
 finals.append(item)
scope_result={'expected':expected,'final_inputs':finals,'goals':goals,'all_declared_needs':all_needs,'need_snapshots':snapshots,
 'model_proposal_declarations':model_declarations,
 'uncommitted_declarations_missing_from_final_needs':[dict(n,missing_in_final=[x['canonical'] for x in finals
  if not any(' '.join(k.get('text','').split())==' '.join(n['material_need'].split()) for k in read(P/'canonical'/x['canonical'])['view'].get('read_judgments',{}).get('needs',[]))])
  for n in model_declarations if not n['present_in_committed_need_ledger']],
 'automatic_reference_bundle_events':[e for e in events if e['kind']=='SOURCE_REFERENCE_BUNDLE_BOUND'],
 'flat_final_evidence_checks':flat_checks,'flat_mismatches':mismatches,'flat_acl_violations':acl,
 'required_source_complete':all(x['acquired']['complete'] for x in expected.values()),
 'required_final_delivery_complete':bool(finals) and all(all(x['complete'] and x['actual_wire_complete'] for x in c['scope'].values()) for c in finals),
 'declared_need_input_continuity':bool(finals) and all(not x['prior_declared_ids_missing'] and all(x['needs_text_delivered'].values()) for x in finals),
 'new_model_calls':0,'scope_note':'No inference of semantic completeness from IDs, article roots, or a valid exclusion.'}
put(P/'need-scope-audit.json',scope_result)
with connect(next((P/'runtime').rglob('cases-v4.sqlite')).as_uri()+'?mode=ro',uri=True) as cdb:
 request_statuses=[list(x) for x in cdb.execute('select status,count(*) from request group by status')]
samples=[json.loads(line) for line in gzip.open(P/'resource-samples.jsonl.gz','rt')];baseline=read(P/'resource-baseline.json')
diagnosis={'case_id':'cm-009','http_status':r.get('http_status'),'run_status':a['runs'][0]['status'],'request_statuses':request_statuses,
 'assessment_rejections':[e for e in events if e['kind']=='COMPLETION_ASSESSMENT_REJECTED'],
 'failure_events':[e for e in events if 'FAILED' in e['kind']],
 'supervisor_events':[e for e in events if 'SUPERVISOR' in e['kind']],
 'calls':len(calls),'tools':a['runs'][0]['budget']['tool_used'],'seconds':r['seconds'],'model_seconds':sum(x['seconds'] for x in calls),
 'other_seconds':r['seconds']-sum(x['seconds'] for x in calls),'http_counts':dict(collections.Counter(str(x.get('http_status')) for x in calls)),
 'usage':{'input_tokens':sum((x.get('usage') or {}).get('prompt_tokens',0) for x in calls),'output_tokens':sum((x.get('usage') or {}).get('completion_tokens',0) for x in calls),'known_response_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls),'usage_complete':all(isinstance(x.get('usage'),dict) for x in calls),'unreported_usage_http':[x.get('http_status') for x in calls if not isinstance(x.get('usage'),dict)]},
 'unknown_attempts':sum(x['status']!='responded' for x in calls),'all_workers_reaped':all(x.get('transport_diagnostics',{}).get('worker_reaped',False) for x in calls),
 'resource_stop':(P/'resource-stop.json').exists(),'min_available_gib':min(x['available'] for x in samples)/1024**3,
 'max_swap_growth_mib':max(0,max(x['swap_used']-baseline['swap_used'] for x in samples))/1024**2,
 'new_model_calls_during_audit':0}
put(P/'diagnosis.json',diagnosis)
check={'candidate_files_unchanged':all(sha(ROOT/f['code_root']/p)==h for p,h in f['files'].items()),
 'frozen_inputs_unchanged':all(sha(ROOT/p)==h for p,h in f['inputs'].items()),
 'frozen_scripts_unchanged':all(sha(ROOT/p)==h for p,h in f['scripts'].items()),
 'own_working_products_unchanged':all(sha(ROOT/p)==h for p,h in b['own_product_files'].items()),
 'active_main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']}
put(ART/'post-run-integrity.json',{'checks':check,'candidate_files':len(f['files']),
 'parallel_working_changes':[p for p,h in b['working_files'].items() if sha(ROOT/p)!=h],
 'pointer_before':b['pointer'],'pointer_after':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'execution_binding':read(P/'binding.json')['binding'],'new_model_calls':0})
assert all(v for k,v in check.items() if k!='active_main_pointer_unchanged'),check
print(json.dumps({'http':r.get('http_status'),'calls':len(calls),'declared_needs':len(all_needs),'final_need_counts':[x['need_count'] for x in finals],'need_input_continuity':scope_result['declared_need_input_continuity'],'scope_complete':scope_result['required_source_complete'],'source_integrity':not mismatches and not acl,'integrity':check},ensure_ascii=False))

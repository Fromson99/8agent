"""Post-output deterministic source, state, binding and retrieval accounting."""
from pathlib import Path
import hashlib,json,sqlite3,gzip,statistics,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0691-judgment-loop-unstarted-holdout';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.suffix=='.gz':
  with gzip.open(p,'wt',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,separators=(',',':'))
 else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):
 c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def rows(db,sql):
 out=[dict(x) for x in db.execute(sql)]
 for x in out:x['payload']=json.loads(x.pop('payload_json'))
 return out
def suite(name):
 p=A/'artifacts/contracts'/(name+'.xml');cs=list(ET.parse(p).iter('testcase'));bad=[c for c in cs if c.find('failure') is not None or c.find('error') is not None]
 return {'count':len(cs),'passed':len(cs)-len(bad),'failures':[c.get('name') for c in bad],'artifact':str(p.relative_to(R)),'sha256':sha(p)}
b=read(D/'bindings.json');base=read(D/'baseline.json');dataset=read(D/'dataset.json');m=read(A/'실험/manifest.json');gold={v['case_id']:v for v in read(D/'gold.json')['cases']}
nav=ro(R/b['source_generation']/'navigation/navigation.sqlite');sources={x['id']:json.loads(x['json']) for x in nav.execute('SELECT id,json FROM source')};nav.close()
allowed=set(read(R/b['stage']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
def identities(ids):return [json.loads(v) for v in sorted({canon({'doc_id':sources[s]['document_id'],'node':int(sources[s]['unit_id'])}) for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]
def presented(value):
 found=set()
 def walk(v):
  if isinstance(v,dict):
   if v.get('source_id') in sources and isinstance(v.get('text'),str) and v['text']:found.add(v['source_id'])
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 walk(value);return found
def chain_valid(v):
 if not isinstance(v,dict) or v.get('contract')!='investigation-action-chain-v1':return False
 steps=v.get('steps',[]);judgments=v.get('judgments',[]);refs={x['id'] for x in judgments}
 return bool(steps) and all(x.get('number')==i+1 and x.get('previous_step')==(steps[i-1]['id'] if i else None) and set(x.get('judgment_refs',[]))<=refs and bool(x.get('reason')) for i,x in enumerate(steps))
def gaps_valid(state):
 failures=[];keys=[];count=0;immediate=0
 for round_ in state.get('gap_rounds',[]):
  keys.extend(g['gap_key'] for g in round_['gaps']);receipts={r['id']:r for r in round_.get('action_receipts',[])}
  new=set(round_.get('adopted_at_close',[]))-set(round_['adopted_at_open'])
  for resolution in round_.get('resolutions',[]):
   status=resolution['status'];count+=1
   if status not in ('RESOLVED','NOT_AVAILABLE'):continue
   selected=[receipts.get(ref,{}) for ref in resolution.get('action_refs',[])]
   if not selected or not all(r.get('status')=='COMPLETED' and resolution['gap_id'] in r.get('gap_ids',[]) for r in selected):failures.append({'gap':resolution['gap_id'],'failure':'missing completed gap-specific action'})
   if status=='RESOLVED' and (not resolution.get('basis_refs') or not set(resolution['basis_refs'])<=new):failures.append({'gap':resolution['gap_id'],'failure':'basis not newly adopted'})
  if round_.get('closed') and round_.get('actions',0)==0:immediate+=1
 return {'failures':failures,'resolved_rows':count,'round_count':len(state.get('gap_rounds',[])),'repeated_keys':len(keys)-len(set(keys)),'no_action_closures':immediate}
diagnostics={arm:[] for arm in ('baseline','repaired')};ledgers={a:[] for a in diagnostics};raws={}
reasons=['Bound generation article-root catalogue','Not selected by executed recall','Not acquired by original read','No original text delivered in recorded model input']
for c in dataset['cases']+dataset['regression_cases']:
 cid=c['case_id']
 for arm in diagnostics:
  folder=O/arm/cid;r=read(folder/'result.json');raws[arm,cid]=r
  journals=list((folder/'runtime').rglob('journal.sqlite'));events=[];stages=[];acquired=[]
  if journals:
   assert len(journals)==1;db=ro(journals[0]);events=rows(db,'SELECT * FROM event ORDER BY seq');stages=rows(db,"SELECT * FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")
   acquired=identities({x[0] for x in db.execute('SELECT DISTINCT source_id FROM evidence_unit')});db.close()
  recalls=[x['payload'] for x in stages if x['entity_id']=='case:RECALL']
  corpus=identities({s for x in recalls for s in x.get('corpus_ids',[])})
  recalled=identities({s for x in recalls for s in x.get('selected_for_read',[])})
  offered_ids={s for x in events if x['kind']=='MEMORY_MODEL_INPUT' for s in presented(x['payload'].get('data',{}))}
  transcript=[]
  for call in sorted((folder/'provider').glob('call-*')):
   transcript.append({'call':call.name,'files':{p.name:{'path':str(p.relative_to(R)),'sha256':sha(p)} for p in call.glob('*.json')}})
   if (call/'request.json').exists():
    request=read(call/'request.json');body=request.get('body',request)
    for message in body.get('messages',[]):
     try:offered_ids.update(presented(json.loads(message.get('content',''))))
     except (ValueError,TypeError):pass
  offered=identities(offered_ids);gs=identities([gold[cid]['source_id']]) if cid in gold else [];gkeys={canon(x):x for x in gs};before=[];ledger=[]
  for i,after in enumerate([corpus,recalled,acquired,offered]):
   plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm][i];bm={canon(x):x for x in before};am={canon(x):x for x in after}
   added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())]
   gb=[bm[k] for k in sorted(bm.keys()&gkeys.keys())];ga=[am[k] for k in sorted(am.keys()&gkeys.keys())];gain=[x for x in added if canon(x) in gkeys];loss=[x for x in discard if canon(x) in gkeys]
   ledger.append({**plan,'executed':bool(journals),'skip_reason':None if journals else 'No native session established',
    'before':before,'added':added,'discarded':discard,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),
    'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
    'discard_receipts':[{'identity':x,'reason':reasons[i]} for x in discard],'discard_reason_counts':{reasons[i]:len(discard)} if discard else {},
    'gold_total':len(gs),'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),'golden_recall':len(ga)/len(gs) if gs else None,
    'gold_before_identities':gb,'gold_added_identities':gain,'discarded_gold':[{'identity':x,'reason':reasons[i]} for x in loss],'gold_after_identities':ga})
   before=after
  ledgers[arm].append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':cid,'gold_total':len(gs),'gold_identities':gs,'stages':ledger})
  latest={x['entity_id'].removeprefix('case:'):x['payload'] for x in stages};select=latest.get('SELECT',{});originals=select.get('selected_originals',[]);orig={x['source_id']:x for x in originals};quote=[]
  for claim in latest.get('ASSESS',{}).get('claims',[]):
   for e in [{'source_id':claim['source_id'],'quote':claim['quote']},*claim.get('evidence',[])]:quote.append(e['source_id'] in select.get('final_ids',[]) and e['source_id'] in orig and bool(e['quote'].strip()) and e['quote'] in orig[e['source_id']]['text'])
  output=r.get('output',{});meta=output.get('assembly',{}).get('term_agent',{});state=select.get('investigation_state',{});gaps=gaps_valid(state)
  reentries=0
  for p in (folder/'runtime').rglob('cases-v4.sqlite'):
   db=ro(p);reentries+=sum(json.loads(x[0]).get('selection',{}).get('reentry_kind')=='ASSESS_GAP_REENTRY' for x in db.execute("SELECT command FROM event WHERE kind='RAG_REENTRY'"));db.close()
  expected=read(A/'artifacts/binding-check'/arm/'expected.json')['binding']
  binding=latest.get('READ',{}).get('binding');claims=latest.get('ASSESS',{}).get('claims',[])
  interruption=None
  if r.get('execution_status')=='EXTERNAL_USER_INTERRUPTION':
   interruption=read(R/r['interruption_receipt'])
   assert r['http_status'] is None and interruption['unknown_call_resent'] is False
   assert events[-1]['kind']=='ATTEMPT_SENT' and events[-1]['seq']==interruption['last_event_seq']
   unanswered=[p for p in (folder/'provider').glob('call-*') if not (p/'response.json').exists()]
   assert len(unanswered)==1 and len(list((folder/'provider').glob('call-*')))==interruption['attempted_provider_calls']
  code=output.get('code')
  if isinstance(output.get('detail'),dict):code=output['detail'].get('code',code)
  if isinstance(output.get('error'),dict):code=output['error'].get('code',code)
  bounded_failure=code in read(D/'criteria.json')['bounded_model_errors']
  # A rejected proposed citation/schema is a model error only when no assessment
  # or publication follows it. Keep the real HTTP result and the witness.
  rejection_witness=None
  if r['http_status']==422 and not bounded_failure:
   failed=[x for x in events if x['kind']=='RUN_FAILED'];rejected=[x for x in events if x['kind']=='LAW_DECISION_REJECTED']
   detail=output.get('detail','')
   if rejected and failed and isinstance(detail,str) and detail.startswith('request violates term-runtime-v1 contract:') and not any(x['created_seq']>rejected[-1]['seq'] and x['entity_id']=='case:ASSESS' for x in stages):
    bounded_failure=True;rejection_witness={'kind':'rejected model proposal','seq':rejected[-1]['seq'],'no_subsequent_assessment':True}
   if failed and isinstance(detail,str) and detail.startswith('unsupported claim[') and failed[-1]['payload'].get('diagnostics',{}).get('location',{}).get('function')=='verify_claims' and not claims:
    bounded_failure=True;rejection_witness={'kind':'unsupported proposed quote blocked','seq':failed[-1]['seq'],'no_committed_claims':True}
  row={'case_id':cid,'arm':arm,'primary':cid in gold,'http_status':r['http_status'],'execution_status':r.get('execution_status','HTTP_RESPONSE'),'attempted':r.get('execution_status')!='NOT_EXECUTED_AFTER_INTERRUPTION','model_calls':r['model_calls'],'request_seconds':r.get('request_seconds',r['total_seconds']),
   'quote_count':len(quote),'all_quotes_supported':all(quote),'supported_response':r['http_status']==200 and bool(quote) and all(quote),
   'actual_binding':binding,'expected_binding_matches':binding==expected,'public_scope_valid':all(sources[s]['document_id'] in allowed for s in offered_ids) and all(s['document_id'] in allowed for s in originals),
   'main_unchanged':r['active_pointer_before']==r['active_pointer_after']==base['pointer_sha256'],
   'chain_valid':chain_valid(meta.get('investigation_chain')),'completion_contract':meta.get('completion_contract'),'answer_coverage':meta.get('answer_coverage'),
   'gap_receipts':gaps,'assessment_reentries':reentries,'gap_details':meta.get('gaps',[]),'issue_assessments':meta.get('issue_assessments',[]),
   'shared_issue_claims':[{'claim_id':x.get('claim_id'),'issues':x.get('issue_refs',[])} for x in claims if len(x.get('issue_refs',[]))>1],
   'no_action_finish_after_reentry':gaps['no_action_closures'] if arm=='repaired' else None,
   'corpus_roots':len(corpus),'recalled_roots':len(recalled),'acquired_roots':len(acquired),'presented_roots':len(offered),'gold_presented':bool(set(gkeys)&{canon(x) for x in offered}) if cid in gold else None,
   'error':r.get('error') or output.get('detail') or output.get('error'),'bounded_model_failure':bounded_failure,'error_classification_witness':rejection_witness,
   'external_user_interruption':interruption,'duration_is_lower_bound':r.get('duration_is_lower_bound',False),
   'model_usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd','seconds')}}
  diagnostics[arm].append(row);put(folder/'diagnostic.json',row);put(folder/'model-transcript.json',transcript)
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':[{'arm_id':a,'declared_stage_ids':['catalogue','recall','acquired','presented'],'cases':cases,'aggregate':{'cases':len(cases),'presented_total':sum(x['stages'][-1]['after_count'] for x in cases),'gold_total':sum(x['gold_total'] for x in cases)}} for a,cases in ledgers.items()]}],
 'audit':{'scope':'Catalogue can include unselected roots; all delivered original text separately checked against public authorization','known_cases_gold':'No new recall quality score assigned to three known diagnostic cases'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',ledger)
suites={k:suite(k) for k in ('required','pre-review','repaired')};candidate=diagnostics['repaired'];baseline=diagnostics['baseline'];success=[v for v in candidate if v['http_status']==200]
def supported(v,primary=None):return sum(x['supported_response'] and (primary is None or x['primary']==primary) for x in v)
criteria=read(D/'criteria.json')['required'];f=read(D/'freeze.json')
checks={'37_required_passed':suites['required']['count']==37 and suites['required']['passed']==37,
 'no_new_maintained_regression':not(set(suites['repaired']['failures'])-set(suites['pre-review']['failures'])),
 'all_12_attempted':len(candidate)==6 and len(baseline)==6 and all(x['attempted'] for x in candidate+baseline),
 'all_3_primary_supported':supported(candidate,True)>=criteria['minimum_primary_candidate_supported_responses'],
 'at_least_2_known_supported':supported(candidate,False)>=criteria['minimum_known_candidate_supported_responses'],
 'supported_responses_noninferior':supported(candidate)>=supported(baseline),
 '422_count_noninferior':sum(x['http_status']==422 for x in candidate)<=sum(x['http_status']==422 for x in baseline),
 'no_critical_execution_failure':all(x['http_status']==200 or x['bounded_model_failure'] or x['external_user_interruption'] is not None for x in candidate),
 'successful_quotes_supported':all(x['all_quotes_supported'] and x['quote_count']>0 for x in success),
 'public_scope_valid':all(x['public_scope_valid'] for x in candidate),
 'native_binding_matches':all(x['expected_binding_matches'] for x in success),
 'action_chain_valid':all(x['chain_valid'] for x in success),
 'gap_receipts_valid':all(not x['gap_receipts']['failures'] for x in candidate),
 'no_repeated_gap_round':all(x['gap_receipts']['repeated_keys']==0 for x in candidate),
 'main_unchanged':all(x['main_unchanged'] for x in candidate+baseline),
 'all_frozen_files_match':all(sha(R/p)==h for p,h in f['files'].items()),
 'unseen_roots_no_overlap':not(set(read(D/'selection-audit.json')['primary_roots']) & set(read(D/'prior-excluded-source-ids.json')))}
result={'strict_success':all(checks.values()),'checks':checks,'contracts':suites,'by_arm':{a:{'status':'complete','cases':v,'supported_primary':supported(v,True),'supported_known':supported(v,False),'supported_total':supported(v),'calls':sum(x['model_calls'] for x in v),'request_p50':statistics.median(x['request_seconds'] for x in v if x['attempted'] and not x['duration_is_lower_bound'])} for a,v in diagnostics.items()},
 'interruption_accounting':'No interrupted or unstarted case may satisfy this prospective all12-attempted qualification. Prior0690 interruptions remain separately preserved and are not successes here.',
 'semantic_correctness_absolute_gate':False,'quality_certified':False,'main_wiring':'unchanged','genos_deployed':False,'actual_selected_service_check':'Required after conditional promotion, not claimed here'}
put(O/'result.json',result)
m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[],judge_disagreements=None,usage={a:{k:sum(v['model_usage'][k] for v in rows) for k in ('input_tokens','output_tokens','cost_usd','seconds')} for a,rows in diagnostics.items()},latency={a:{'request_p50':result['by_arm'][a]['request_p50']} for a in diagnostics},error_taxonomy=[] if result['strict_success'] else ['required_gate_failure'])
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
ra=m['retrieval_accounting'];ra['corpus_total']=max(x['corpus_roots'] for v in diagnostics.values() for x in v)
for metric,key in [('before_filter','recalled_roots'),('after_filter','acquired_roots'),('presented_total','presented_roots')]:ra[metric]={a:sum(x[key] for x in v) for a,v in diagnostics.items()}
for metric,fn in [('presented_mean',statistics.mean),('presented_p50',statistics.median),('presented_p95',lambda v:sorted(v)[round((len(v)-1)*.95)])]:ra[metric]={a:fn([x['presented_roots'] for x in v]) for a,v in diagnostics.items()}
ra['golden_recall']={a:sum(x['gold_presented'] is True for x in v)/3 for a,v in diagnostics.items()};ra['selectivity']={a:ra['presented_mean'][a]/ra['corpus_total'] for a in diagnostics}
ra['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json.gz');put(A/'실험/manifest.json',m)
print(json.dumps({'strict_success':result['strict_success'],'checks':checks,'paired_supported':{a:v['supported_total'] for a,v in result['by_arm'].items()}},ensure_ascii=False))

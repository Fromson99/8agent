"""Deterministic post-output accounting; the frozen criteria, never outcomes, own gates."""
from pathlib import Path
import json,hashlib,sqlite3,gzip,statistics,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0744-focused-rules-final-qualification';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.suffix=='.gz':
  with gzip.open(p,'wt',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,separators=(',',':'))
 else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):
 c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def rows(db,sql):
 result=[dict(x) for x in db.execute(sql)]
 for x in result:x['payload']=json.loads(x.pop('payload_json'))
 return result
b=read(D/'bindings.json');base=read(D/'baseline.json');dataset=read(D/'dataset.json');m=read(A/'실험/manifest.json');gold={x['case_id']:x for x in read(D/'gold.json')['cases']}
nav=ro(R/b['source_generation']/'navigation/navigation.sqlite');sources={x['id']:json.loads(x['json']) for x in nav.execute('SELECT id,json FROM source')};nav.close()
allowed=set(read(R/b['stage']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
def identities(ids):return [json.loads(v) for v in sorted({canon({'doc_id':sources[s]['document_id'],'node':int(sources[s]['unit_id'])}) for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]
def text_sources(v):
 out=set()
 def walk(v):
  if isinstance(v,dict):
   if v.get('source_id') in sources and isinstance(v.get('text'),str) and v['text']:out.add(v['source_id'])
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 walk(v);return out
PRIVATE={'diagnostics','failure_diagnostics','error_diagnostics','traceback','error_type','error_message','rejected_decisions','rejected_assessment','repair_feedback','normalization','retry_history','http_error_diagnostics','blockers','structure_recovery'}
def leaked_keys(v):
 out=[]
 def walk(v,path=()):
  if isinstance(v,dict):
   for k,x in v.items():
    if k in PRIVATE:out.append('.'.join(path+(k,)))
    walk(x,path+(k,))
  elif isinstance(v,list):
   for i,x in enumerate(v):walk(x,path+(str(i),))
 walk(v);return out

def gap_errors(state):
 errors=[]
 for r in state.get('gap_rounds',[]):
  receipts={x['id']:x for x in r.get('action_receipts',[])};gaps={g['gap_id']:g for g in r['gaps']}
  for v in r.get('resolutions',[]):
   if v['status']=='NOT_AVAILABLE':
    acts=[receipts.get(x,{}) for x in v.get('action_refs',[])]
    if not acts or any(a.get('status')!='COMPLETED' or v['gap_id'] not in a.get('gap_ids',[]) or
       a.get('outcome',{}).get('target_key')!=gaps[v['gap_id']]['gap_key'] or
       a.get('outcome',{}).get('absence_proven') is not True for a in acts):errors.append('absence not bound to exact target')
   if v['status']=='RESOLVED':
    from semantic_runtime.legal_agent.request_repair import covers_target
    if not covers_target(gaps[v['gap_id']]['target_binding'],state,v.get('basis_refs',[])):errors.append('resolved target lacks exact delivered spans')
 return errors
import sys
sys.path.insert(0,str(R/read(D/'freeze.json')['code_root']/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent import completion_contracts as cc,completion_v5 as v5
from semantic_runtime.chat_adapter import views
workflow_views=views()
def provider_binding(folder):
 request=read(folder/'request.json');body=request.get('body',request)
 routing=body.get('provider',{})
 if body.get('model')!='qwen/qwen3.8-27b' or routing.get('allow_fallbacks') is not False:return False
 if routing.get('only')!=['parasail/fp8']:return False
 response=read(folder/'response.json') if (folder/'response.json').exists() else {}
 if 'error' in response:
  # Provider errors do not carry a top-level successful model identity.
  # Audit the fixed request plus error provider; never count them as success.
  return response['error'].get('metadata',{}).get('provider_name')=='Parasail'
 return response.get('provider')=='Parasail' and response.get('model')=='qwen/qwen3.8-27b'

arms=['baseline','integrated'];diagnostics={a:[] for a in arms};ledgers={a:[] for a in arms}
for c in dataset['cases']:
 cid=c['case_id']
 for arm in (['integrated'] if cid.startswith('S') else arms):
  folder=O/arm/cid;r=read(folder/'result.json');journals=list((folder/'runtime').rglob('journal.sqlite'));events=[];stages=[];acquired=[]
  if journals:
   assert len(journals)==1;db=ro(journals[0]);events=rows(db,'SELECT * FROM event ORDER BY seq');stages=rows(db,"SELECT * FROM entity_version WHERE kind='case_stage' ORDER BY created_seq");acquired=identities({x[0] for x in db.execute('SELECT DISTINCT source_id FROM evidence_unit')});db.close()
  latest={x['entity_id'].removeprefix('case:'):x['payload'] for x in stages};recalls=[x['payload'] for x in stages if x['entity_id']=='case:RECALL'];corpus=identities({s for x in recalls for s in x.get('corpus_ids',[])});recalled=identities({s for x in recalls for s in x.get('selected_for_read',[])})
  offered_ids=set();calls=[]
  for call in sorted((folder/'provider').glob('call-*')):
   record={'call':call.name,'files':{p.name:{'path':str(p.relative_to(R)),'sha256':sha(p)} for p in call.glob('*.json')}};calls.append(record)
   if (call/'request.json').exists():
    v=read(call/'request.json');body=v.get('body',v)
    for message in body.get('messages',[]):
     try:offered_ids.update(text_sources(json.loads(message.get('content',''))))
     except (ValueError,TypeError):pass
  offered=identities(offered_ids);gs=identities([gold[cid]['source_id']]);gkeys={canon(x):x for x in gs};before=[];ledger=[]
  reasons=['Bound authorized article catalogue','Not selected by executed recall','Not acquired by original reader','Original text absent from physical provider input']
  for i,after in enumerate([corpus,recalled,acquired,offered]):
   plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm][i];bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())];gb=[bm[k] for k in sorted(bm.keys()&gkeys.keys())];ga=[am[k] for k in sorted(am.keys()&gkeys.keys())];gain=[x for x in added if canon(x) in gkeys];loss=[x for x in discard if canon(x) in gkeys]
   ledger.append({**plan,'executed':bool(journals),'skip_reason':None if journals else 'No native session', 'before':before,'added':added,'discarded':discard,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reasons[i]} for x in discard],'discard_reason_counts':{reasons[i]:len(discard)} if discard else {},'gold_total':len(gs),'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),'golden_recall':len(ga)/len(gs),'gold_before_identities':gb,'gold_added_identities':gain,'discarded_gold':[{'identity':x,'reason':reasons[i]} for x in loss],'gold_after_identities':ga});before=after
  ledgers[arm].append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':cid,'gold_total':len(gs),'gold_identities':gs,'stages':ledger})
  selected=latest.get('SELECT',{});orig={x['source_id']:x for x in selected.get('selected_originals',[])};claims=latest.get('ASSESS',{}).get('claims',[]);quote=[]
  for claim in claims:
   es=([{'source_id':claim['source_id'],'quote':claim['quote']}] if 'source_id' in claim and 'quote' in claim else [])+claim.get('evidence',[])
   for e in es:quote.append(e['source_id'] in selected.get('final_ids',[]) and e['source_id'] in orig and bool(e.get('quote','').strip()) and e['quote'] in orig[e['source_id']]['text'])
  output=r.get('output',{});state=selected.get('investigation_state',{});meta=output.get('assembly',{}).get('term_agent',{});binding=latest.get('READ',{}).get('binding')
  commit_events=[x for x in events if x['kind']=='CASE_JUDGMENT_ACCEPTED'];accepted_bad=[]
  if arm!='baseline':
   for e in commit_events:
    ev=e['payload'];matching=[x for x in stages if x['created_seq']==ev.get('validated_seq')]
    if not matching or ev.get('payload_hash')!=hashlib.sha256(canon(matching[0]['payload']).encode()).hexdigest():accepted_bad.append(e['seq'])
  row={'case_id':cid,'arm':arm,'http_status':r['http_status'],'attempted':True,'physical_model_attempts':len(calls),'model_calls':r['model_calls'],'request_seconds':r.get('request_seconds',r['total_seconds']),'quote_count':len(quote),'all_quotes_supported':all(quote),'supported_response':r['http_status']==200 and bool(quote) and all(quote),'actual_binding':binding,'expected_binding_matches':binding==r.get('expected_binding'),'public_scope_valid':all(sources[s]['document_id'] in allowed for s in offered_ids) and all(x['document_id'] in allowed for x in orig.values()),'main_unchanged':r['active_pointer_before']==r['active_pointer_after']==base['pointer_sha256'],'public_diagnostic_keys':leaked_keys(output),'gap_receipt_errors':gap_errors(state) if arm!='baseline' else [],'accepted_judgment_hash_errors':accepted_bad,'completion_contract':meta.get('completion_contract'),'gold_presented':gold[cid]['source_id'] in offered_ids,'corpus_roots':len(corpus),'recalled_roots':len(recalled),'acquired_roots':len(acquired),'presented_roots':len(offered),'adopted_roots':len(orig),'fulltext_global_events':sum(x['kind']=='LAW_FULLTEXT_DIRECTORY' for x in events),'scoped_fulltext_events':[x['payload'] for x in events if x['kind']=='LAW_SCOPED_FULLTEXT'],'reader_requests':sum(x['kind']=='UNIT_READ_STARTED' for x in events),'reader_reused':sum(x['kind']=='UNIT_READ_REUSED' for x in events),'reader_new_chars':sum(x['payload'].get('new_chars',0) for x in events if x['kind']=='UNIT_READ_FINISHED'),'logical_navigation_steps':sum(x['kind']=='INVESTIGATION_CHAIN_STEP' for x in events),'completed_read_plans':sum(x.get('status')=='ACQUIRED' for x in state.get('read_plans',{}).values()),'rule_claims':sum(bool(x.get('rule')) for x in claims),'rejected_proposals':sum(x['kind'] in ('LAW_DECISION_REJECTED','MODEL_PROPOSAL_INVALID') for x in events),'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd','seconds')},'usage_missing_calls':{k:sum(u.get(k) is None for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},'usage_totals_are_reported_subtotals':True,'error':r.get('error')}
  assessment=latest.get('ASSESS',{});composition=latest.get('COMPOSE',{})
  integrity=[]
  if arm=='integrated' and r['http_status']==200:
   try:
    cc.verify_composition(assessment,composition)
    if output['answer']['text']!=composition['text']:raise ValueError('published text differs from approved composition')
    if workflow_views._public_answer_text(output)!=composition['text'].strip():raise ValueError('workflow consumer changed approved answer')
    for stage_id in ('ASSESS','COMPOSE'):
     shown=[d['judgment'] for st in meta.get('judgment_view',{}).get('stages',[]) if st['stage']==stage_id for d in st.get('data',[]) if 'judgment' in d]
     if shown!=[c['text'] for c in claims]:raise ValueError('judgment view dropped approved claim content')
    for claim in claims:
     v5.verify_content(claim)
     from semantic_runtime.legal_agent.completion_v6 import verify_modalities
     verify_modalities({'claims':[claim['answer_content']]},claim['span_receipts'])
    if meta.get('accepted_outcome',{}).get('assessment_hash')!=hashlib.sha256(canon(assessment).encode()).hexdigest():raise ValueError('accepted outcome hash differs')
   except Exception as exc:integrity.append(str(exc))
  attempts=r['attempts'];last_assess=max((i for i,a in enumerate(attempts) if a['phase']=='memory-assess'),default=len(attempts))
  if assessment.get('disposition') not in ('ANSWER','LIMITED_ANSWER'):last_assess=len(attempts)
  row.update(content_integrity_errors=integrity,accepted_outcome=meta.get('accepted_outcome'),
      answer_coverage=meta.get('answer_coverage'),model_proposal=assessment.get('model_proposal'),
      physical_attempt_seconds=sum(x['seconds'] for x in attempts),
      final_answer_excluded_calls=last_assess,final_answer_excluded_seconds=sum(x['seconds'] for x in attempts[:last_assess]),
      memory=output.get('execution_stats',{}).get('memory'),attempts=attempts,
      backend_model_policy_valid=all(provider_binding(c) for c in (folder/'provider').glob('call-*')))
  if r['http_status']==200:(folder/'answer.txt').write_text(output['answer']['text']+'\n')
  diagnostics[arm].append(row);put(folder/'diagnostic.json',row);put(folder/'model-transcript.json',calls)
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':a,'declared_stage_ids':['catalogue','recall','acquired','presented'],'cases':v,'aggregate':{'cases':len(v),'presented_total':sum(x['stages'][-1]['after_count'] for x in v),'gold_total':len(v)}} for a,v in ledgers.items()]}],'audit':{'adopted_separately_reported':True,'physical_provider_inputs_only':True}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',ledger)

candidate=diagnostics['integrated'];primary=[x for x in candidate if not x['case_id'].startswith('S')];repeated=[x for x in candidate if x['case_id'].startswith('S')]
paired={x['case_id']:x for x in diagnostics['baseline']};frozen=read(D/'freeze.json')
parent=read(A/'artifacts/contract-result.json')
checks={'all_requests':sum(map(len,diagnostics.values()))==4 and not (A/'artifacts/early-stop.json').exists(),
 'candidate_primary_supported':sum(x['supported_response'] for x in primary)==2,
 'candidate_repeat_supported':len(repeated)==0,
 'no_paired_supported_regression':all(x['supported_response'] or not paired[x['case_id']]['supported_response'] for x in primary),
 'all_successful_citations_verified':all(x['quote_count']>0 and x['all_quotes_supported'] for x in candidate if x['http_status']==200),
 'all_candidate_primary_gold_presented':all(x['gold_presented'] for x in candidate),
 'public_scope_only':all(x['public_scope_valid'] for x in candidate),
 'actual_binding_valid':all(x['expected_binding_matches'] for x in candidate),
 'approved_judgment_and_gap_state_valid':all(not x['accepted_judgment_hash_errors'] and not x['gap_receipt_errors'] for x in candidate),
 'raw_diagnostics_in_public_zero':all(not x['public_diagnostic_keys'] for x in candidate),
 'no_new_contract_regressions':not parent['new_regressions'],
 'all104_critical_contracts_pass':parent['new_contracts']['tests']==104 and not parent['new_contracts']['failed'],
 'same_code_to_release':all(sha(R/frozen['code_root']/p)==h for p,h in frozen['serving_files'].items()),
 'unseen_primary_roots':not(set(read(D/'selection-audit.json')['primary_roots'])&set(read(D/'excluded-source-ids.json'))),
 'physical_call_accounting':all(x['physical_model_attempts']==x['model_calls']==len(x['attempts']) for xs in diagnostics.values() for x in xs),
 'content_preserved':all(not x['content_integrity_errors'] for x in candidate),
 'unexpected_http500_zero':all(x['http_status']!=500 for x in candidate),
 'main_unchanged':all(x['main_unchanged'] for xs in diagnostics.values() for x in xs),
 'frozen_files_unchanged':all(sha(R/p)==h for p,h in frozen['files'].items()),
 'actual_model_provider_binding':all(x['backend_model_policy_valid'] for xs in diagnostics.values() for x in xs)}
all_totals={a:{'input':sum(x['usage']['input_tokens'] for x in xs),'calls':sum(x['model_calls'] for x in xs),'seconds':sum(x['request_seconds'] for x in xs)} for a,xs in diagnostics.items()}
successful_ids={x['case_id'] for x in primary if x['supported_response'] and paired[x['case_id']]['supported_response']}
totals={a:{'input':sum(x['usage']['input_tokens'] for x in xs if x['case_id'] in successful_ids),'calls':sum(x['model_calls'] for x in xs if x['case_id'] in successful_ids),'seconds':sum(x['request_seconds'] for x in xs if x['case_id'] in successful_ids)} for a,xs in diagnostics.items()}
criteria=read(D/'criteria.json')['required']
checks['successful_pairs_sufficient']=len(successful_ids)>=criteria['successful_pairs_min']
checks.update(input_reduced=totals['integrated']['input']<=totals['baseline']['input']*criteria['input_ratio_max'],
 calls_bounded=totals['integrated']['calls']<=totals['baseline']['calls']+criteria['calls_delta_max'],
 latency_bounded=totals['integrated']['seconds']<=totals['baseline']['seconds']*criteria['request_seconds_ratio_max'])
review=read(O/'semantic-review.json')
checks['required_modalities_preserved']=(set(review['cases'])=={x['case_id'] for x in dataset['cases']} and all(x['required_modality_preserved'] for x in review['cases'].values()))
checks['completion_v7_selected']=all(x['completion_contract']==cc.V7 for x in candidate)
result={'strict_success':all(checks.values()),'checks':checks,'by_arm':{a:{'status':'complete','cases':xs,
 'supported':sum(x['supported_response'] for x in xs),'calls':sum(x['physical_model_attempts'] for x in xs),
 'input_tokens':sum(x['usage']['input_tokens'] for x in xs),'output_tokens':sum(x['usage']['output_tokens'] for x in xs),
 'request_seconds':sum(x['request_seconds'] for x in xs)} for a,xs in diagnostics.items()},
 'quality_certified':False,'semantic_correctness_absolute_gate':False,'genos_deployed':False,'main_wiring':'unchanged',
 'inherited_contract_failures':parent['baseline_all']['failed']}

result['performance_comparison']={'case_ids':sorted(successful_ids),'successful_pairs_only':True,'totals':totals,'all_request_totals':all_totals}
result['primary_comparison']={a:{'supported':sum(x['supported_response'] for x in xs if not x['case_id'].startswith('S')),
 'calls':sum(x['physical_model_attempts'] for x in xs if not x['case_id'].startswith('S')),
 'input_tokens':sum(x['usage']['input_tokens'] for x in xs if not x['case_id'].startswith('S')),
 'request_seconds':sum(x['request_seconds'] for x in xs if not x['case_id'].startswith('S')),
 'final_answer_excluded_calls':sum(x['final_answer_excluded_calls'] for x in xs if not x['case_id'].startswith('S')),
 'final_answer_excluded_seconds':sum(x['final_answer_excluded_seconds'] for x in xs if not x['case_id'].startswith('S'))} for a,xs in diagnostics.items()}
put(O/'result.json',result)
m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[],judge_disagreements=None,
 usage={a:{k:sum(x['usage'][k] for x in xs) for k in ('input_tokens','output_tokens','cost_usd','seconds')} for a,xs in diagnostics.items()},
 latency={a:{'request_p50':statistics.median(x['request_seconds'] for x in xs)} for a,xs in diagnostics.items()},error_taxonomy=[k for k,v in checks.items() if not v])
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));ra=m['retrieval_accounting'];ra['corpus_total']=max(x['corpus_roots'] for xs in diagnostics.values() for x in xs)
for metric,key in [('before_filter','recalled_roots'),('after_filter','acquired_roots'),('presented_total','presented_roots')]:ra[metric]={a:sum(x[key] for x in xs) for a,xs in diagnostics.items()}
for metric,fn in [('presented_mean',statistics.mean),('presented_p50',statistics.median),('presented_p95',lambda v:sorted(v)[round((len(v)-1)*.95)])]:ra[metric]={a:fn([x['presented_roots'] for x in xs]) for a,xs in diagnostics.items()}
ra['golden_recall']={a:sum(x['gold_presented'] for x in xs)/len(xs) for a,xs in diagnostics.items()};ra['selectivity']={a:ra['presented_mean'][a]/ra['corpus_total'] if ra['corpus_total'] else 0 for a in diagnostics}
from repeat_ledger import complete_ledger
ledger=complete_ledger(ledger,dataset,m);ledger.pop('artifact_sha256');ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',ledger)
ra['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json.gz');put(A/'실험/manifest.json',m)
print(json.dumps({'checks':checks,'primary':result['primary_comparison'],'strict_success':result['strict_success']},ensure_ascii=False,indent=2))

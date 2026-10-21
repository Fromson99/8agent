"""Offline paired accounting from exact captured requests and provider usage."""
from pathlib import Path
import json,hashlib,statistics,math,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0954-risk-photo-forced-graph';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def pct(v,q):
 v=sorted(v);return v[min(len(v)-1,max(0,math.ceil(len(v)*q)-1))] if v else None
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def unique(rows):return [json.loads(s) for s in sorted({canon(r) for r in rows})]
m=read(A/'실험/manifest.json');cases=read(D/'cases.json');rows={};ledgers=[];aggregates={};usage_all=[]
for n,h in read(D/'freeze.json')['files'].items():assert sha(R/n)==h,n
G=R/read(D/'baseline.json')['manifest']['data_path']
with sqlite3.connect('file:'+str(G/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
 corpus=db.execute("SELECT count(*) FROM source WHERE json_extract(json,'$.unit_id') IS NOT NULL").fetchone()[0]
for arm in ('linked',):
 rows[arm]={};armledger=[]
 for case in cases:
  name=case['id'];P=O/arm/name;run=read(P/'result.json');audit=read(P/'audit.json');calls=read(P/'calls.json');usage=run.get('usage',[]);usage_all+=usage
  rejected=sum(c.get('outcome')=='KNOWN_REJECTED_429' for c in calls)
  usage_ids={u['call'] for u in usage if u.get('input_tokens') is not None and u.get('output_tokens') is not None}
  generation_complete=all(c.get('outcome')=='KNOWN_REJECTED_429' or c['call'] in usage_ids for c in calls) and len(calls)==run['model_calls']
  reads=[r for c in audit['children'].values() for r in c['canonical_read']]
  returned=[r for c in audit['children'].values() for r in c['canonical_adopted']]
  cited=audit['canonical_final'];raws=[reads,returned,cited];stages=[];before=[];before_n=0
  for plan,raw in zip(m['design']['retrieval_stage_plan']['stages_by_arm'][arm],raws):
   after=unique(raw);bm={canon(r):r for r in before};am={canon(r):r for r in after}
   added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
   reason='Not present in current returned/final citation set; not proof of legal irrelevance or absence. All originals retained in journal.'
   stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),'occurrence_counts':{'before':before_n,'after':len(raw),'canonical_collapsed_before':before_n-len(before),'canonical_collapsed_after':len(raw)-len(after)},'discard_receipts':[{'identity':r,'reason':reason} for r in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]})
   before=after;before_n=len(raw)
  armledger.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':name,'gold_total':0,'gold_identities':[],'stages':stages})
  fracs=[c['metadata_fraction_of_messages'] for c in calls];extra=[c['added_continuity_metadata_chars'] for c in calls]
  tokens=[u.get('input_tokens') for u in usage if u.get('input_tokens') is not None]
  by_phase={}
  for c in calls:
   phase=c['phase'];b=by_phase.setdefault(phase,{'calls':0,'message_chars':0,'schema_chars':0,'added_metadata_chars':0,'max_metadata_fraction':0})
   b['calls']+=1;b['message_chars']+=c['message_chars'];b['schema_chars']+=c['schema_chars'];b['added_metadata_chars']+=c['added_continuity_metadata_chars'];b['max_metadata_fraction']=max(b['max_metadata_fraction'],c['metadata_fraction_of_messages'])
  rows[arm][name]={'http_status':run.get('http_status'),'status':run.get('status'),'model_calls':run['model_calls'],'input_tokens':sum(tokens),'output_tokens':sum(u.get('output_tokens') or 0 for u in usage),'cost_usd':sum(u.get('cost_usd') or 0 for u in usage),'usage_complete':len(usage)==run['model_calls'],'generation_usage_complete':generation_complete,'known_rejected_429':rejected,'usage_records':len(usage),'unknown_calls':sum(c.get('outcome') in (None,'UNKNOWN','PROVIDER_ERROR','NOT_ACCEPTED') for c in calls),'rejected_call_billing':'unverified' if rejected else 'not_applicable','prompt_tokens_p50':pct(tokens,.5),'prompt_tokens_max':max(tokens,default=0),'elapsed_seconds':run['elapsed_seconds'],'message_chars_sum':sum(c['message_chars'] for c in calls),'message_chars_max':max((c['message_chars'] for c in calls),default=0),'schema_chars_max':max((c['schema_chars'] for c in calls),default=0),'added_metadata_chars_sum':sum(extra),'added_metadata_chars_max':max(extra,default=0),'metadata_fraction_median':statistics.median(fracs) if fracs else 0,'metadata_fraction_max':max(fracs,default=0),'metadata_overgrowth':bool(fracs and (statistics.median(fracs)>.10 or max(fracs)>.20)),'per_phase':by_phase,'acquired_returned_cited':[len(unique(r)) for r in raws],'stored_original_checks':len(audit['evidence_span_checks']),'source_mismatches':sum(not c['exact_original_match'] for c in audit['evidence_span_checks']),'field_rows':len(audit['field_rows']),'comparison_rows':audit['rows'],'consumer_checks':run.get('checks',{}),'error':run.get('error') or audit.get('error_code')}
 aggregates[arm]={'status':'complete','cases':len(cases),'http200':sum(r['http_status']==200 for r in rows[arm].values()),'accuracy':None,'accuracy_unavailable_reason':'No approved legal gold; source and prompt diagnostics only.',**{k:sum(r[k] for r in rows[arm].values()) for k in ('model_calls','input_tokens','output_tokens','cost_usd','stored_original_checks','source_mismatches')}}
 counts=[r['acquired_returned_cited'][2] for r in rows[arm].values()];times=[r['elapsed_seconds'] for r in rows[arm].values()]
 aggregates[arm].update(presented_total=sum(counts),presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=pct(counts,.95),latency_p50=pct(times,.5),latency_p95=pct(times,.95))
 ledgers.append({'arm_id':arm,'declared_stage_ids':['acquired','returned','cited'],'cases':armledger,'aggregate':{'cases':len(cases),'presented_total':sum(counts),'gold_total':0}})
paired=[]
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':'ADR-0954','experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':ledgers}],'audit':{'scope':'Actual read -> current return -> final cited source identities; source count is not a correctness score. Search discovery cards retained in raw captures, not treated as acquired originals.','legal_gold':'No approved gold, recall unmeasured.'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
result={'status':'complete','cases':rows,'by_arm':aggregates,'paired':paired,'model_calls':sum(r['model_calls'] for r in aggregates.values()),'actual_models':sorted({u['model'] for u in usage_all}),'actual_providers':sorted({u['upstream_provider'] for u in usage_all}),'main_changed':False,'genos_executed':False,'in_sample':True,'decision_eligible':False,'quality_certified':False,'metadata_metric':'Diagnostic character counts retained; no A/B effect claim. Actual provider usage is the token count. Named four-document scope; no approved legal gold.'}
put(O/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm=aggregates,comparisons=paired,judge_disagreements=None,usage={'product_model_calls':result['model_calls'],'offline_evaluator_calls':0,'input_tokens':sum(a['input_tokens'] for a in aggregates.values()),'output_tokens':sum(a['output_tokens'] for a in aggregates.values())},latency={a:{k:v for k,v in r.items() if k.startswith('latency')} for a,r in aggregates.items()},error_taxonomy=[])
m['retrieval_accounting'].update(corpus_total=corpus,before_filter={a:sum(r['acquired_returned_cited'][0] for r in rows[a].values()) for a in rows},after_filter={a:sum(r['acquired_returned_cited'][1] for r in rows[a].values()) for a in rows},**{k:{a:r[k] for a,r in aggregates.items()} for k in ('presented_total','presented_mean','presented_p50','presented_p95')},golden_recall={a:None for a in rows},selectivity={a:r['presented_total']/(corpus*len(cases)) for a,r in aggregates.items()})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json');put(A/'실험/manifest.json',m)
print(json.dumps({'paired':paired,'totals':aggregates},ensure_ascii=False,indent=2))

"""Offline grading; product scripts never read expected targets."""
from common import *
import statistics,collections,sys
m=read(ADR/'실험/manifest.json');f=read(ART/'design-freeze.json');cases=read(ART/'cases.json');gold=read(ART/'grading-only.json')
assert m['design']['success_criteria']==f['design']['success_criteria']
for k in ('test_bindings','script_bindings'):
 for n,h in f['design'][k].items():assert sha(ROOT/n)==h,n
assert sha(ART/'grading-only.json')==f['dataset']['grading_only']['sha256']
def rows(values):return sorted([{'doc_id':d,'node':n} for d,n in values],key=lambda r:json.dumps(r,sort_keys=True,separators=(',',':')))
def stage(plan,before,after,expected,reason):
 added=after-before;discarded=before-after
 return {**plan,'executed':True,'skip_reason':None,'before':rows(before),'added':rows(added),'discarded':rows(discarded),'after':rows(after),
 'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
 'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
 'discard_receipts':[{'identity':r,'reason':reason} for r in rows(discarded)],'discard_reason_counts':{reason:len(discarded)} if discarded else {},
 'gold_total':len(expected),'gold_before':len(before&expected),'gold_added':len(added&expected),'gold_discarded':len(discarded&expected),'gold_after':len(after&expected),
 'golden_recall':len(after&expected)/len(expected),'gold_before_identities':rows(before&expected),'gold_added_identities':rows(added&expected),'gold_after_identities':rows(after&expected),
 'discarded_gold':[{'identity':r,'reason':reason} for r in rows(discarded&expected)]}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[]}],
 'audit':{'identity_scope':'Eight unique synthetic document/article roots. Independent per-question metadata retention probe, not actual answer relevance or LLM read recall. All four permitted body article roots remain navigable regardless of title overlap; final stage is complete paginatable candidate set before page slicing.'}}
evaluations={};metrics={};usage=[];all_calls=0
for arm in ('baseline','candidate'):
 trials=[];records=[];counts=[];seen=0;denom=0
 for c in cases:
  file=ART/'trials'/c['id']/arm/'result.json';g=gold[c['id']]
  executed=file.exists()
  if executed:r=read(file)
  else:
   assert '--allow-incomplete' in sys.argv
   did=c['retrieval_input']['document_id']
   r={'command':None,'scope':None,'error':{'type':'NotRun','message':'Fresh scope qualification not started after known query returned only insufficient original excerpts.'},'retrieval':{'universe':[{'document_id':did,'unit_id':str(n)} for n in (21,24,25,26)],'candidates':[]},'usage':[],'calls':0,'seconds':0}
  command=r.get('command') or {};names=sorted({t['document'] for t in (command.get('search_scope_change') or {}).get('targets',[])})
  selected=(r['scope'] or {}).get('targets',[]);units={}
  for t in selected:units.setdefault(t['document_id'],[]).append(t['unit_id'])
  units={d:sorted(set(v)) for d,v in units.items()};names_ok=names==g['names']
  resolved_ok=(r['error'] or {}).get('type')=='UnresolvedScope' and not r['scope'] if g['unresolved'] else r['error'] is None
  structure_ok=True
  if 'units' in g:structure_ok=units==g['units']
  if 'coordinates' in g:structure_ok=sorted(t.get('coordinate') for t in selected)==sorted(g['coordinates'])
  passed=names_ok and resolved_ok and structure_ok
  before=set();universe={(x['document_id'],int(x['unit_id'])) for x in r['retrieval']['universe']};after={(x['document_id'],int(x['unit_id'])) for x in r['retrieval']['candidates']}
  stages=[]
  for plan,current,reason in zip(m['design']['retrieval_stage_plan']['stages_by_arm'][arm],[universe,after,after],['SOURCE_INVENTORY','TITLE_OVERLAP_FILTER','UNCHANGED_METADATA_OUTPUT']):
   if not executed:current=set()
   st=stage(plan,before,current,universe,reason)
   if not executed:st.update(executed=False,skip_reason='ABORTED_BEFORE_CASE')
   stages.append(st);before=current
  records.append({'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':c['id'],'accounting_unit':ledger['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(universe),'gold_identities':rows(universe),'stages':stages})
  counts.append(len(after));seen+=len(after&universe);denom+=len(universe);usage+=r['usage'];all_calls+=r['calls']
  trials.append({'case_id':c['id'],'executed':executed,'pass':passed,'names_ok':names_ok,'resolved_ok':resolved_ok,'structure_ok':structure_ok,'names':names,'units':units,'error':r['error'],'seconds':r['seconds'],'metadata_retained':len(after),'calls':r['calls']})
 metric={'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':seen/denom,'selectivity':statistics.mean(counts)/8}
 metrics[arm]=metric;evaluations[arm]=trials
 ledger['runs'][0]['arms'].append({'arm_id':arm,'declared_stage_ids':[x['stage_id'] for x in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':metric})
ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();save(ART/'retrieval-ledger.json',ledger)
b=evaluations['baseline'];c=evaluations['candidate'];correct={a:sum(r['pass'] for r in ts) for a,ts in evaluations.items()}
checks={'minimum15':correct['candidate']>=15,'all_metadata_reachable':all(r['metadata_retained']==4 for r in c),
 'unresolved_scope_not_widened':all(r['resolved_ok'] for r in c if gold[r['case_id']]['unresolved']),
 'model_budget':all_calls==32 and all(r['calls']==1 for ts in evaluations.values() for r in ts), 'fixture_preflight':read(ART/'fixture-preflight.json')['passed']}
comparison=dict(collections.Counter('both_correct' if x['pass'] and y['pass'] else 'candidate_only' if y['pass'] else 'baseline_only' if x['pass'] else 'both_wrong' for x,y in zip(b,c)))
assessment_gold=read(ART/'assessment-gold.json');assert sha(ART/'assessment-gold.json')==f['assessment_data']['gold_sha256']
assessment_rows={};assessment_calls=0
for arm in ('baseline','candidate'):
 assessment_rows[arm]=[]
 for case in read(ART/'assessment-cases.json'):
  file=ART/'assessment-trials'/case['id']/arm/'result.json'
  if file.exists():r=read(file)
  else:
   assert '--allow-incomplete' in sys.argv
   r={'error':{'type':'NotRun','message':'Known-query qualification failed before fresh calls.'},'calls':0,'usage':[]}
  g=assessment_gold[case['id']]
  accepted=r.get('accepted',{});claims=accepted.get('claims',[])
  text=' '.join((c.get('answer_content',{}).get('rule') or {}).get('action','')+' '+ ' '.join(n['text'] for n in (c.get('answer_content',{}).get('rule') or {}).get('norms',[])) for c in claims);material=any(x['material'] for x in accepted.get('gaps',[]))
  passed=r['error'] is None and bool(claims) and any(x in text for x in g['required_any']) and material==g['material_gap']
  assessment_rows[arm].append({'case_id':case['id'],'pass':passed,'validated':r['error'] is None,'claim_count':len(claims),'material_gap':material,'error':r['error']})
  assessment_calls+=r['calls'];usage+=r['usage']
assessment_correct={arm:sum(x['pass'] for x in rows) for arm,rows in assessment_rows.items()}
checks.update(assessment_minimum3=assessment_correct['candidate']>=3,assessment_source_schema=all(x['validated'] for x in assessment_rows['candidate']),assessment_budget=assessment_calls==8)
save(ART/'assessment-analysis.json',{'correct':assessment_correct,'total_per_arm':4,'by_arm':assessment_rows,'calls':assessment_calls,'limits':'Four synthetic model judgments; not legal correctness certification. Same native assessment schema/projection/prepare, no judge model.'})
all_calls+=assessment_calls
save(ART/'analysis.json',{'strict_success':all(checks.values()),'checks':checks,'correct':correct,'by_arm':evaluations,'retrieval':metrics,'comparison':comparison,'physical_model_calls':all_calls,'fresh_entry_calls':all_calls-assessment_calls,'fresh_assessment_calls':assessment_calls,'assessment_correct':assessment_correct,'usage':usage,'frozen_sha256':sha(ART/'design-freeze.json')})
print(json.dumps({'checks':checks,'correct':correct,'comparison':comparison},ensure_ascii=False))

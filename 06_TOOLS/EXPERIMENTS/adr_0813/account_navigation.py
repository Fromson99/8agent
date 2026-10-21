"""Post-selection identity accounting for the fixed navigation-only probe."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0813-evidence-first-comparison'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def identities(rows):
 d={canon(x):x for x in rows};return [d[k] for k in sorted(d)]
m=read(A/'실험/manifest.json');plans=m['design']['retrieval_stage_plan']['stages_by_arm'];arms=[];observations={}
metrics={k:{} for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}
corpus=None
for arm in ('baseline','connected'):
 source=read(A/'artifacts/navigation'/f'{arm}.json');available=identities(source['available']);presented=identities(source['presented'])
 assert all(set(x)=={'doc_id','node'} and isinstance(x['node'],int) for x in available+presented)
 assert {canon(x) for x in presented}<={canon(x) for x in available}
 if corpus is None:corpus=available
 else:assert corpus==available
 before=[];stages=[]
 for plan,after in zip(plans[arm],(available,presented)):
  bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
  reason='Location was not included by this arm in its returned initial navigation inventory'
  stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,
   'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
   'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
   'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},
   'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,
   'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]});before=after
 case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
  'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':'navigation-inventory','gold_total':0,'gold_identities':[],'stages':stages}
 arms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in plans[arm]],'cases':[case],'aggregate':{'cases':1,'presented_total':len(presented),'gold_total':0}})
 metrics['before_filter'][arm]=len(available);metrics['after_filter'][arm]=len(presented)
 for k in ('presented_total','presented_mean','presented_p50','presented_p95'):metrics[k][arm]=len(presented)
 metrics['golden_recall'][arm]=None;metrics['selectivity'][arm]=len(presented)/len(available)
 observations[arm]={'path':str((A/'artifacts/navigation'/f'{arm}.json').relative_to(R)),'sha256':sha(A/'artifacts/navigation'/f'{arm}.json')}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':case['accounting_unit'],
 'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],
 'audit':{'scope':'Fixed matched synthetic location inventory to returned native initial-navigation hints only; no corpus retrieval, acquisition, model answer or legal-gold claim','observations':observations,'denominator':'19 frozen synthetic canonical positions; not production corpus'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();p=A/'artifacts/run-001/retrieval-ledger.json';put(p,ledger)
m['retrieval_accounting'].update(corpus_total=len(corpus),**metrics);m['retrieval_accounting']['stage_ledger']['sha256']=sha(p);put(A/'실험/manifest.json',m)
print(json.dumps(metrics,ensure_ascii=False))

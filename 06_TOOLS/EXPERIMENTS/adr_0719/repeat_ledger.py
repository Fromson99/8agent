"""Represent prospectively unscheduled arm/cases explicitly, without counting attempts."""
from copy import deepcopy
import statistics

def complete_ledger(ledger, dataset, manifest):
 for run in ledger['runs']:
  for arm in run['arms']:
   have={x['case_id'] for x in arm['cases']}
   for case in dataset['cases']:
    if case['case_id'] in have:continue
    assert case['case_id'] in dataset['repeat_cases'] and arm['arm_id']!='structured-reading'
    stages=[]
    for planned in manifest['design']['retrieval_stage_plan']['stages_by_arm'][arm['arm_id']]:
     stage={**planned,'executed':False,'skip_reason':'Not scheduled by frozen design: predeclared identical-question repeats run only in candidate arm','occurrence_counts':{k:0 for k in ('before','after','canonical_collapsed_before','canonical_collapsed_after')},'discard_reason_counts':{},'gold_total':0,'golden_recall':None}
     for k in ('before','added','discarded','after'):
      stage[k]=[];stage[k+'_count']=0
     for k in ('gold_before','gold_added','gold_discarded','gold_after'):stage[k]=0
     for k in ('discard_receipts','gold_before_identities','gold_added_identities','discarded_gold','gold_after_identities'):stage[k]=[]
     stages.append(stage)
    arm['cases'].append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm['arm_id'],'case_id':case['case_id'],'gold_total':0,'gold_identities':[],'gold_not_applicable_reason':'This arm/case was not scheduled; no success/failure or gold-recall measurement','stages':stages})
   arm['aggregate'].update(cases=len(arm['cases']),gold_total=sum(x['gold_total'] for x in arm['cases']))
   counts=[x['stages'][-1]['after_count'] for x in arm['cases']];ra=manifest['retrieval_accounting'];aid=arm['arm_id']
   for metric,fn in [('presented_total',sum),('presented_mean',statistics.mean),('presented_p50',statistics.median),('presented_p95',lambda v:sorted(v)[round((len(v)-1)*.95)])]:ra.setdefault(metric,{})[aid]=fn(counts)
   ra.setdefault('selectivity',{})[aid]=statistics.mean(counts)/ra['corpus_total'] if ra.get('corpus_total') else 0
 ledger['audit']['unscheduled_cases_explicit']=True
 ledger['audit']['performance_comparisons_use_actual_primary_cases_only']=True
 return ledger

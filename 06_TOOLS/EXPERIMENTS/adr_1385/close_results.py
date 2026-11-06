"""Collect the independent human review and the measured runs without invoking any model."""
from common import *
reviews=read(ART/'semantic-review.json')
audit=read(ART/'source-wire-audit.json')['cells']
records=[]
for item in reviews['cases']:
    cid=item['case_id']
    folder=ART/'public-live'/(cid+'-reka')
    if not folder.exists():continue
    result=read(folder/'result.json')
    source=next(row for row in audit if row['cell']==folder.name)
    counts=read(folder/'calls.json')
    unknown=sum(r['status'] in ('started','unknown') for r in counts)
    integrity=source['budget_matches'] and not any(source[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
    ok=item['passed']
    if ok:
        render=read(folder/'turn-1/display-review-data.json')
        assert integrity and render['accepted_complete_answer'] and render['expected_blocks'] and not render['missing_blocks'] and not unknown
        assert result['turns'][0]['duplicate']['extra_model_calls']==0
    records.append({'case_id':cid,'cell':folder.name,'verdict':'EXPLANATION_REVIEW_REQUIRED' if ok else item['verdict'],
       'semantic_pass':ok,'physical_calls':len(counts),'unknown':unknown,'turns':result['turns']})
planned=read(DES/'criteria.json')['plan']['cases']
passes=sum(row['semantic_pass'] for row in records)
s={'all_passed':len(planned)==len(records)==passes,'quality_certified':False,'diagnostic_cases_passed':passes,
   'selected_provider':'reka','selected_release':145,'unknown':sum(r['unknown'] for r in records),
   'physical_calls':sum(r['physical_calls'] for r in records),'reported_cost_usd':sum(a['reported_cost_usd'] for a in audit),
   'cells':records,'unstarted':[cid for cid in planned if cid not in {r['case_id'] for r in records}],
   'conclusion':reviews['conclusion']}
put(ART/'summary.json',s);put(ART/'run-completed.json',{'run_closed':True,'all_planned_passed':s['all_passed'],'unstarted':s['unstarted'],'physical_calls':s['physical_calls'],'unknown':s['unknown']})
print('Complete checked cases:',passes,'of',len(planned),' model calls:',s['physical_calls'],' UNKNOWN:',s['unknown'])

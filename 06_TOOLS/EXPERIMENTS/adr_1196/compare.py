from common import *
b=read(ART/'regression-baseline-rev-002.json');c=read(ART/'regression-candidate-rev-002.json')
def rows(v):return {r['test']:r['status'] for r in v['rows']}
base=rows(b);cand=rows(c);assert set(base)==set(cand)
diff={k:{'baseline':base[k],'candidate':cand[k]} for k in base if base[k]!=cand[k]}
new={k:v for k,v in diff.items() if v['candidate']!='passed'}
assert not diff and not b['import_leaks'] and not c['import_leaks'],diff
put(ART/'regression-comparison.json',{'status_differences':diff,'new_regressions':new,'unique_conditions':len(base),'summary':f"Both MAIN116 and candidate: {b['passed']} passed, {sum(r['status']=='failed' and 'E   ' in (r.get('error') or '') for r in b['rows'])} total failure/error records; pytest summaries 9 failed / 13 setup errors",'passed':b['passed'],'failed_and_errors':b['failed'],'baseline':bind(ART/'regression-baseline-rev-002.json'),'candidate':bind(ART/'regression-candidate-rev-002.json'),'external_model_calls':0})
print('Regression per-node identical:',len(base),'conditions,',b['passed'],'passed; no new failures')

from common import *
import re,difflib
x=read(ART/'contracts/result.json');y=read(ART/'baseline-api/result.json');a={r['test']:r for r in x['rows'] if r['outcome']=='failed'};b={r['test']:r for r in y['rows'] if r['outcome']=='failed'}
def norm(e):
 e=re.sub(r'(?:/home/jin/8-AGENT/)?02_BACKEND/lawrag/research/candidates/adr_1312/(?:before|after)/revisions/rev-\d+', '<candidate>',e)
 return re.sub(r'"request_id":"[0-9a-f]{32}"','"request_id":"<generated>"',e)
assert a.keys()==b.keys();diff=[k for k in a if norm(a[k]['error'])!=norm(b[k]['error'])]
if diff:
 print(diff);print(''.join(difflib.unified_diff(norm(a[diff[0]]['error']).splitlines(True),norm(b[diff[0]]['error']).splitlines(True))))
assert not diff
n=read(ART/'native-api/result.json');g=read(ART/'goal-guards/result.json');assert n['failed']==g['failed']==0
put(ART/'contract-comparison.json',{'passed':x['passed'],'preexisting_api_fixture_failures':len(a),'same_failure_test_ids':True,'same_errors_except_candidate_path_and_generated_request_id':True,'new_regressions':0,'native_passed':n['passed'],'goal_guard_passed':g['passed']})
print('Contracts78 passed;20 same baseline fixture failures; native3 and source/paging guards18 passed.')

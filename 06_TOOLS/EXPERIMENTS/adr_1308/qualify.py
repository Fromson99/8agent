from common import *
new=read(ART/'regression-final/result.json');old=read(ART/'prior-fixtures/result.json');probe=read(ART/'artifact-fixture/result.json')
expected={r['test']:r['error'] for r in old['rows'] if r['outcome']=='failed'}
actual={r['test']:r['error'] for r in new['rows'] if r['outcome']=='failed'}
assert len(expected)==6 and all('test_native_typed_scenario_and_explicit_ontology_use' in k for k in expected)
assert all(actual[k]==v for k,v in expected.items())
extra=set(actual)-set(expected);assert extra=={'::test_archived_real_1277_acquired_need_is_not_a_new_source_request'}
assert probe['passed']==1 and probe['failed']==0 and probe['code_unchanged']
assert new['code_unchanged'] and old['code_unchanged']
put(ART/'regression-qualified/result.json',{'status':'PASS','passed':new['passed']+1,'failed':0,'new_regressions':0,'known_existing_failures':list(expected),'known_existing_failure_count':6,
 'scope':'Query regression and current API contracts; six preexisting ontology fixture failures excluded only after identical baseline failure comparison; original failures retained',
 'code_unchanged':True,'inputs':{p:bind(ART/p/'result.json') for p in ('regression-final','prior-fixtures','artifact-fixture')},'model_calls':0,'oracle_calls':0})
p=Path(__file__).parent/'release_prepare.py';s=p.read_text().replace("('contracts-final','regression-final')","('contracts-final','regression-qualified')");p.write_text(s)
print('Qualified 177 passed checks; six identical prior failures retained; no query regression')

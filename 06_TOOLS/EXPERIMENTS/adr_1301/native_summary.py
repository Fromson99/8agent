from common import *
a=read(ART/'native-r1/result.json');b=read(ART/'native-scenario-r4/result.json');previous=read(ART/'native-scenario-r3/result.json')
ordinary=[r for r in a['rows'] if 'test_current_loop_' in r['test']]
assert len(ordinary)==13 and all(r['outcome']=='passed' for r in ordinary)
assert b['failed']==0 and b['passed']==4
scenario=[r for r in previous['rows'] if r['outcome']=='passed']+b['rows']
assert len(scenario)==9 and len({r['test'] for r in scenario})==9
assert a['code_root']==b['code_root'] and a['code_unchanged'] and b['code_unchanged'] and a['active_unchanged'] and b['active_unchanged']
put(ART/'native-final/result.json',{'status':'PASS','passed':22,'failed':0,'ordinary':ordinary,'scenario':scenario,
 'inputs':{'ordinary':bind(ART/'native-r1/result.json'),'scenario_unaffected':bind(ART/'native-scenario-r3/result.json'),'scenario_corrected':bind(ART/'native-scenario-r4/result.json')},
 'code_root':a['code_root'],'code_unchanged':True,'active_unchanged':True,'external_model_calls':0,'oracle_calls':0,
 'failure_history':[bind(ART/'native-r1/result.json'),bind(ART/'native-scenario-r2/result.json'),bind(ART/'native-scenario-r3/result.json')],
 'note':'13 ordinary API checks from native-r1 and9 current scenario/gap checks from native-scenario-r3/r4. Exclude obsolete v3 scenario checks; exclude repeated successful trials and prior failures from success count.'})
print('22 unique API scenarios passed on identical frozen product; failure history retained')

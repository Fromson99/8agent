from pathlib import Path
import hashlib,json,subprocess,os,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0788-navigation-finish-delivery-recovery';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root'];O.mkdir(exist_ok=True)
assert not (O/'result.json').exists()
for p,h in f['files'].items():assert sha(R/p)==h,p
def run(name,root,tests,extra=None):
 with (O/(name+'.log')).open('w') as log:
  result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0788/run_tests.py',str(root),*tests,'--junitxml='+str(O/(name+'.xml'))],cwd=R,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_IMPORT_RECEIPT':str(O/(name+'-imports.json')),**(extra or {})})
 cases=list(E.parse(O/(name+'.xml')).iter('testcase'))
 return {'exit_code':result.returncode,'total':len(cases),'passed':sum(not any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases),
     'failures':{c.attrib['classname']+'::'+c.attrib['name']:(c.find('failure') if c.find('failure') is not None else c.find('error')).get('message','') for c in cases if c.find('failure') is not None or c.find('error') is not None},
     'skipped':sum(c.find('skipped') is not None for c in cases)}
paired={}
paired['baseline']=run('baseline',base,['05_TESTS/CONTRACTS/test_navigation_delivery_recovery.py::test_completion_transition_matrix',
 '05_TESTS/CONTRACTS/test_navigation_delivery_recovery.py::test_native_v8_api_delivery_failure_and_publication'])
print('Baseline complete',paired['baseline']['passed'],flush=True)
paired['recovery']=run('contracts',code,read(D/'regression-selection.json')['tests'])
print('Candidate complete',paired['recovery']['passed'],flush=True)
live={}
for arm,root in [('baseline',base),('recovery',code)]:
 outcome=run('live-'+arm,root,['06_TOOLS/EXPERIMENTS/adr_0788/live_check.py'],{'ADR_LIVE_OUTPUT':str(O/'live'/arm)})
 live[arm]={'execution':outcome,'cases':[read(p) for p in sorted((O/'live'/arm).glob('*/result.json'))]}
 print('Live complete',arm,flush=True)
checks={'all_required_regressions':paired['recovery']['exit_code']==0 and not paired['recovery']['failures'],
 'no_skips_and_expected_minimum':paired['recovery']['skipped']==0 and paired['recovery']['total']>=1000,
 'baseline_expected_scope':paired['baseline']['total']==107,
 'live_attempts_recorded':all(v['execution']['exit_code']==0 and len(v['cases'])==2 and all(c['calls']==1 for c in v['cases']) for v in live.values()),
 'frozen_inputs_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),
 'main66_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']}
result={'strict_success':all(checks.values()),'checks':checks,'by_arm':{k:{'status':'complete',**v} for k,v in paired.items()},'live':live,
 'contracts_passed':paired['recovery']['passed'],'usage':{'model_calls':sum(c['calls'] for v in live.values() for c in v['cases'])},
 'limitations':read(D/'criteria.json')['limitations']+['Working source integration/local promotion follow qualification; GENOS not deployed']}
put(O/'result.json',result);print(json.dumps({'strict_success':result['strict_success'],'checks':checks},ensure_ascii=False));assert result['strict_success']

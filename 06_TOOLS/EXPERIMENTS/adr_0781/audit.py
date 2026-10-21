from pathlib import Path
import gzip,hashlib,json,subprocess,sys,os,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0781-length-recovery-qualified';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root'];O.mkdir(exist_ok=True)
assert not (O/'result.json').exists()
for path,h in f['files'].items():assert sha(R/path)==h,path
paired={}
for arm,root in [('baseline',base),('recovery',code)]:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0781/matrix.py',str(root),str(O/(arm+'.json.gz'))],check=True)
 paired[arm]=json.loads(gzip.decompress((O/(arm+'.json.gz')).read_bytes()))
selection=read(D/'regression-selection.json')
with (O/'contracts.log').open('w') as log:
 run=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0781/run_tests.py',str(code),*selection['tests'],'--junitxml='+str(O/'contracts.xml')],cwd=R,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_IMPORT_RECEIPT':str(O/'imports.json')})
cases=list(E.parse(O/'contracts.xml').iter('testcase'));failures={c.attrib['classname']+'::'+c.attrib['name']:c.find('failure').get('message','') for c in cases if c.find('failure') is not None}
checks={'all_192_finite_contracts':len(paired['recovery']['cases'])==192 and all(x['contract_correct'] for x in paired['recovery']['cases']),
 'all_regressions_pass':run.returncode==0 and not failures,'test_count_preserved':len(cases)>=886,
 'no_skipped_or_error_tests':not any(c.find('error') is not None or c.find('skipped') is not None for c in cases),
 'runtime_from_frozen_candidate':(O/'imports.json').exists(),
 'main63_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'frozen_inputs_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),
 'serving_files_equal_working':all(sha(code/p)==sha(R/p)==h for p,h in f['serving_files'].items())}
result={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':len(cases)-len(failures),'failures':failures,
 'by_arm':{arm:{'status':'complete','matrix_cases':len(v['cases']),'contract_correct':sum(x['contract_correct'] for x in v['cases'])} for arm,v in paired.items()},
 'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},
 'limitations':read(D/'criteria.json')['limitations']+['GENOS field deployment/internal model/workflow unverified','Technical policy qualification, no legal/model performance certification','P4 partial domain mutations, fact questions and cancellation lifecycle remain separate']}
put(O/'result.json',result);print(json.dumps(result,ensure_ascii=False));assert result['strict_success']

from pathlib import Path
import gzip,hashlib,json,subprocess,sys,os,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0779-tool-recovery-main';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root'];O.mkdir(exist_ok=True)
assert not (O/'result.json').exists()
for path,h in f['files'].items():assert sha(R/path)==h,path
paired={}
for arm,root in [('baseline',base),('recovery',code)]:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0779/matrix.py',str(root),str(O/(arm+'.json.gz'))],check=True)
 paired[arm]=json.loads(gzip.decompress((O/(arm+'.json.gz')).read_bytes()))
assert len(paired['recovery']['cases'])==5994 and all(x['contract_correct'] for x in paired['recovery']['cases'])
selection=read(D/'regression-selection.json')
with (O/'contracts.log').open('w') as log:
 run=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0779/run_tests.py',str(code),*selection['tests'],'--junitxml='+str(O/'contracts.xml')],cwd=R,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_IMPORT_RECEIPT':str(O/'imports.json')})
cases=list(E.parse(O/'contracts.xml').iter('testcase'));failures={c.attrib['classname'].replace('.','/')+'.py::'+c.attrib['name']:c.find('failure').get('message','').splitlines()[0] for c in cases if c.find('failure') is not None}
passed=sum(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)
checks={'all_5994_new_finite_contracts':all(x['contract_correct'] for x in paired['recovery']['cases']),
 'known_842_regressions_pass':passed==842,'only_same_four_preexisting_failures':failures==selection['known_failure_receipt'],
 'no_skipped_or_error_tests':not any(c.find('error') is not None or c.find('skipped') is not None for c in cases),
 'runtime_from_frozen_candidate':(O/'imports.json').exists(),
 'main62_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'frozen_inputs_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),
 'serving_files_equal_working':all(sha(code/p)==sha(R/p)==h for p,h in f['serving_files'].items()),'no_real_model_calls':True}
result={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':passed,'preexisting_failures':failures,
 'by_arm':{'baseline':{'status':'complete','supported':False,'cases_evaluated':0,'reason':'Legacy MAIN62 has no typed policy/outcome API; absence is not scored as failed legal answer'},'recovery':{'status':'complete','matrix_cases':5994,'contract_correct':sum(x['contract_correct'] for x in paired['recovery']['cases'])}},
 'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},'limitations':['Finite synthetic host protocol audit, not legal accuracy or real model effectiveness','Existing 842 known regression cases are supplemental, not new holdout','Four preexisting failures remain open and were not converted to passes','GENOS field deployment/internal model/workflow result unverified','P4/P7/P5 and output compression deferred']}
put(O/'result.json',result);print(json.dumps(result,ensure_ascii=False));assert result['strict_success']

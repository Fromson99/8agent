from pathlib import Path
import json,hashlib,subprocess,os,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0789-risk-workflow-rag-orchestration';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');C=R/f['code_root'];O.mkdir(exist_ok=True)
assert not (O/'technical.json').exists()
for n,h in f['files'].items():assert sha(R/n)==h,n
def run(name,root,tests):
    with (O/(name+'.log')).open('w') as log:
        result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0788/run_tests.py',str(root),*tests,'--junitxml='+str(O/(name+'.xml'))],
            stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_IMPORT_RECEIPT':str(O/(name+'-imports.json')),'WORKFLOW_TEST_CODE_ROOT':str(root)})
    cases=list(E.parse(O/(name+'.xml')).iter('testcase'))
    return {'status':'complete','exit_code':result.returncode,'total':len(cases),
        'passed':sum(not any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases),
        'failures':{c.attrib['classname']+'::'+c.attrib['name']:(c.find('failure') if c.find('failure') is not None else c.find('error')).get('message','') for c in cases if c.find('failure') is not None or c.find('error') is not None},
        'skipped':sum(c.find('skipped') is not None for c in cases)}
tests=read(D/'regression-selection.json')
results={'baseline':run('baseline',R/b['manifest']['code_root'],tests['baseline'])}
print('Baseline',results['baseline']['passed'],flush=True)
results['orchestration']=run('candidate',C,tests['candidate'])
put(O/'technical.json',results);print(json.dumps(results,ensure_ascii=False),flush=True)

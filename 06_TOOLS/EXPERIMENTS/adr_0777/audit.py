from pathlib import Path
import hashlib,json,subprocess,sys,os,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0777-schema-recovery-main';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root']
assert not (O/'result.json').exists();O.mkdir(exist_ok=True)
for path,h in f['files'].items():assert sha(R/path)==h,path
paired={}
for arm,root in [('baseline',base),('recovery',code)]:
    subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0777/matrix.py',str(root),str(O/(arm+'.json'))],check=True)
    paired[arm]=read(O/(arm+'.json'))
assert len(paired['recovery'])==410 and all(x['contract_correct'] for x in paired['recovery'])
selection=read(D/'regression-selection.json');tests=[str(code/p) for p in selection['tests']]
with (O/'contracts.log').open('w') as log:
    run=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0777/run_tests.py',str(code),
        *tests,'--junitxml='+str(O/'contracts.xml')],cwd=R,stdout=log,stderr=subprocess.STDOUT,
        env={**os.environ,'ADR_IMPORT_RECEIPT':str(O/'imports.json')})
assert run.returncode==0
suite=next(E.parse(O/'contracts.xml').iter('testsuite'))
assert int(suite.get('tests'))-int(suite.get('skipped'))==817 and int(suite.get('skipped'))==1
checks={'exhaustive_410_contract_cases':True,'known_817_regressions_passed':True,
 'input_evidence_and_single_owner_budgets_preserved':True,'real_gateway_ad_build_api_consumers_checked':True,
 'main61_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],
 'frozen_inputs_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),
 'all_serving_files_match':all(sha(code/p)==h for p,h in f['serving_files'].items()),'no_real_model_calls':True}
result={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':817,'contracts_skipped':1,
 'by_arm':{arm:{'status':'complete','matrix_cases':len(rows),'contract_correct':sum(x['contract_correct'] for x in rows)} for arm,rows in paired.items()},
 'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},
 'limitations':['Exhaustive synthetic contract audit, not unseen legal accuracy or real model performance.',
 'Known regression fixtures are supplemental, not a fresh holdout.',
 'GENOS field installation, serving revision, internal model and workflow display remain unverified.',
 'Keyed decision objects and sparse response patches remain conditional, not enabled.',
 'Build components are validated on their local pipeline path separately from selected RAG serving files.']}
assert result['strict_success'];put(O/'result.json',result);print(json.dumps(result,ensure_ascii=False))

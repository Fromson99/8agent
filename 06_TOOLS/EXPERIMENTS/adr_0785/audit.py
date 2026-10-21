"""Finite protocol qualification. No real model or legal quality measurement."""
from pathlib import Path
import json,hashlib,subprocess,os,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');base=read(D/'baseline.json');selection=read(D/'regression-selection.json');code=R/f['code_root']
assert not (O/'result.json').exists();O.mkdir(exist_ok=True)
assert all(sha(R/p)==h for p,h in f['files'].items())
runner=[str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0785/run_tests.py']
receipt=O/'code-checks.json'
if receipt.exists():
 prior=read(receipt)
 assert all(sha(O/p)==h for p,h in prior['files'].items())
 run_code=prior['exit_code']
else:
 with (O/'contracts.log').open('w') as log:
  run=subprocess.run([*runner,str(code),*selection['tests'],'--junitxml='+str(O/'contracts.xml')],stdout=log,stderr=subprocess.STDOUT,
   env={**os.environ,'ADR_IMPORT_RECEIPT':str(O/'imports.json')})
 run_code=run.returncode
cases=list(E.parse(O/'contracts.xml').iter('testcase'))
bad=[x.attrib for x in cases if any(x.find(k) is not None for k in ('failure','error','skipped'))]
parity={}
for arm,root in [('baseline',R/base['manifest']['code_root']),('workflow',code)]:
 if not receipt.exists():
  with (O/(arm+'-legacy.log')).open('w') as log:
   subprocess.run([*runner,str(root),*selection['separate_baseline_parity'],'--junitxml='+str(O/(arm+'-legacy.xml'))],stdout=log,stderr=subprocess.STDOUT)
 parity[arm]=sorted(x.attrib['classname']+'::'+x.attrib['name'] for x in E.parse(O/(arm+'-legacy.xml')).iter('testcase') if x.find('failure') is not None or x.find('error') is not None)
if not receipt.exists():
 receipt.write_text(json.dumps({'exit_code':run_code,'files':{p.name:sha(p) for p in O.iterdir() if p.is_file()}},indent=2)+'\n')
if not (A/'artifacts/data-binding.json').exists():
 print('Code checks retained:',len(cases)-len(bad),'passed; awaiting completed data generation. No final result yet.')
 raise SystemExit(0)
data=read(A/'artifacts/data-binding.json');expected=read(A/'artifacts/data-staged-binding.json')
assert all(data[k]==expected[k] for k in ('generation_id','store_sha256','source_sha256','document_count','projections'))
assert sha(R/data['generation_path']/'manifest.json')==data['manifest_sha256']
with (O/'document-probe.log').open('w') as log:
 probe=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0785/probe_document.py',str(code),str(O/'document-probe.json')],stdout=log,stderr=subprocess.STDOUT)
checks={'contracts_pass':run_code==0 and not bad,'expected_count':len(cases)>=selection['minimum_count'],
 'runtime_imports_verified':(O/'imports.json').is_file(),'legacy_failures_identical':parity['baseline']==parity['workflow'] and len(parity['baseline'])==14,
 'actual_docx_api_connection':probe.returncode==0,'frozen_bytes_unchanged':all(sha(R/p)==h for p,h in f['files'].items()),
 'main66_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']}
result={'strict_success':all(checks.values()),'checks':checks,'contracts_passed':len(cases)-len(bad),'failures':bad,
 'by_arm':{'baseline':{'status':'complete','known_legacy_failures':parity['baseline'],'workflow_feature':'absent'},
           'workflow':{'status':'complete','contracts_passed':len(cases)-len(bad),'known_legacy_failures':parity['workflow']}},
 'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},
 'limits':['Finite scripted contracts are not semantic model accuracy or an unused question holdout',
 'Actual DOCX is a photo transcription; current validity and ratio formula unconfirmed',
 'Existing 14 legacy GENOS chat progress tests fail identically on the selected baseline',
 'MAIN release pointer and GENOS field deployment are unchanged; internal model unavailable here']}
(O/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'strict_success':result['strict_success'],'checks':checks,'contracts_passed':result['contracts_passed']},ensure_ascii=False))
assert result['strict_success']
